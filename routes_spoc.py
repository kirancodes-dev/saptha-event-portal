from flask import Blueprint, render_template, request, redirect, session, flash, Response, url_for, jsonify
from models import db, FirebaseWrapper
import datetime
import csv
import io
import json
from utils import login_required, role_required

spoc_bp = Blueprint('spoc', __name__, url_prefix='/spoc')

# --- 1. SPOC DASHBOARD ---
@spoc_bp.route('/dashboard')
@login_required
@role_required('ClubSPOC')
def dashboard():
    spoc_id = session.get('user_id')
    query = db.collection('events').where('spoc_id', '==', spoc_id).stream()

    events = []
    total_regs = 0
    present_count = 0
    chart_labels = []
    chart_regs = []

    for doc in query:
        data = doc.to_dict()
        regs = list(db.collection('registrations').where('event_id', '==', doc.id).stream())
        reg_count = len(regs)
        p_count = sum(1 for r in regs if r.to_dict().get('attendance') == 'Present')
        total_regs += reg_count
        present_count += p_count
        data['registration_count'] = reg_count
        events.append(FirebaseWrapper(doc.id, data))
        chart_labels.append(data.get('title', doc.id)[:20])
        chart_regs.append(reg_count)

    return render_template(
        'spoc/dashboard.html',
        events=events,
        stats={
            'total_events':  len(events),
            'total_regs':    total_regs,
            'present_count': present_count,
        },
        category=session.get('category', 'General'),
        chart_labels=chart_labels,
        chart_regs=chart_regs,
    )

# --- 2. CREATE EVENT (DYNAMIC BUILDER) ---
@spoc_bp.route('/create_event', methods=['GET', 'POST'])
@login_required
@role_required('ClubSPOC')
def create_event():
    if request.method == 'GET':
        return render_template('spoc/create_event.html') 

    try:
        def get_bool(key): return True if request.form.get(key) == 'on' else False
        def get_int(key, default=0): 
            try: return int(request.form.get(key, default))
            except: return default
        
        # 1. Capture Multiple Coordinators (Comma separated string -> List)
        coord_string = request.form.get('coordinators', '')
        coordinators_list = [email.strip().lower() for email in coord_string.split(',') if email.strip()]

        # 2. Dynamic Form Schema (Strictly defined by SPOC)
        form_schema = {
            'require_lead_whatsapp': get_bool('req_lead_whatsapp'),
            'require_member_usn': get_bool('req_member_usn'),
            'require_member_email': get_bool('req_member_email'),
            'require_member_whatsapp': get_bool('req_member_whatsapp'),
            'submission_type': request.form.get('submission_type', 'none') # 'github', 'drive', 'none'
        }

        # 3. Allowed Years
        allowed_years = []
        if get_bool('year_1'): allowed_years.append(1)
        if get_bool('year_2'): allowed_years.append(2)
        if get_bool('year_3'): allowed_years.append(3)
        if get_bool('year_4'): allowed_years.append(4)

        event_data = {
            'title': request.form.get('title'),
            'category': request.form.get('category'),
            'description': request.form.get('description'),
            'rules': request.form.get('rules'),
            'banner_url': request.form.get('banner_url') or 'https://placehold.co/800x400?text=Event',
            'visibility': request.form.get('visibility'),
            'date': request.form.get('date'),
            'time': request.form.get('time'),
            'reg_deadline': request.form.get('reg_deadline'),
            'venue': request.form.get('venue'),
            'participation_type': request.form.get('participation_type'),
            'is_team_event': request.form.get('participation_type') in ['Team', 'Both'],
            
            # KEY NEW FIELDS
            'coordinators': coordinators_list, # Array of emails
            'form_schema': form_schema,        # The exact form requirements
            
            'limits': {
                'team_min': get_int('team_min', 1),
                'team_max': get_int('team_max', 1),
                'max_participants': get_int('max_participants', 0),
                'allowed_years': allowed_years
            },
            'fees': {'regular': get_int('reg_fee', 0)},
            'prizes': {
                '1st': request.form.get('prize_1'),
                '2nd': request.form.get('prize_2'),
                '3rd': request.form.get('prize_3')
            },
            
            'spoc_id': session['user_id'],
            'organizer': {
                'name': session.get('name'), 
                'email': session.get('user_id'),
                'phone': '9999999999', # Placeholder, ideally fetch from profile
                'group_link': '#'
            },
            'status': 'active',
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'results_published': False
        }

        # Firestore .add() returns (timestamp, doc_ref). Capture the id so
        # we can attach an auto-generated form schema if one was provided.
        _, new_event_ref = db.collection('events').add(event_data)
        new_event_id = new_event_ref.id

        auto_form_raw = request.form.get('auto_form_json', '').strip()
        if auto_form_raw:
            try:
                auto_fields = json.loads(auto_form_raw)
            except json.JSONDecodeError:
                auto_fields = []

            if isinstance(auto_fields, list) and auto_fields:
                db.collection('event_forms').document(new_event_id).set({
                    'event_id':   new_event_id,
                    'form_type':  'custom',
                    'fields':     auto_fields,
                    'created_by': session.get('user_id'),
                    'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'source':     'ai_generated'
                })
                db.collection('events').document(new_event_id).update({'has_custom_form': True})
                flash(f"Event '{event_data['title']}' published! Review and tweak the AI-generated form below.", "success")
                return redirect(f'/forms/builder/{new_event_id}')

        flash(f"Event '{event_data['title']}' Published with Custom Rules!", "success")
        return redirect('/spoc/dashboard')
        
    except Exception as e:
        print(f"Error: {e}")
        flash(f"Error creating event: {str(e)}", "danger")
        return redirect('/spoc/create_event')

# --- 3. EXPORT CSV ---
@spoc_bp.route('/export_csv/<event_id>')
@login_required
@role_required('ClubSPOC')
def export_csv(event_id):
    try:
        event_doc = db.collection('events').document(event_id).get()
        title = event_doc.to_dict().get('title', 'Event')
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Team/Name', 'Lead Email', 'Members', 'Status', 'Attendance', 'Score', 'Date'])
        regs = db.collection('registrations').where('event_id', '==', event_id).stream()
        for doc in regs:
            r = doc.to_dict()
            member_count = len(r.get('members', []))
            scores = r.get('scores', {})
            final_score = max([v['total'] for v in scores.values()]) if scores else 0
            writer.writerow([r.get('team_name', 'Individual'), r.get('lead_email'), f"{member_count} Members", r.get('status'), r.get('attendance'), final_score, r.get('registered_at')])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename={title}_report.csv"})
    except:
        return redirect('/spoc/dashboard')

# --- 4. RESULTS DASHBOARD ---
@spoc_bp.route('/results/<event_id>')
@login_required
@role_required('ClubSPOC')
def event_results(event_id):
    # 1. Fetch Event
    event_doc = db.collection('events').document(event_id).get()
    event = event_doc.to_dict()
    event['id'] = event_id

    # 2. Fetch Registrations
    regs_ref = db.collection('registrations').where('event_id', '==', event_id).stream()
    
    leaderboard = []
    
    for r in regs_ref:
        data = r.to_dict()
        data['id'] = r.id
        
        # 3. Calculate Scores
        scores_map = data.get('scores', {})
        total_score = sum([s.get('total', 0) for s in scores_map.values()])
        judge_count = len(scores_map)
        
        avg_score = round(total_score / judge_count, 2) if judge_count > 0 else 0
        
        data['final_score'] = avg_score
        data['judge_count'] = judge_count
        
        leaderboard.append(data)

    # 4. Sort by Highest Score
    leaderboard.sort(key=lambda x: x['final_score'], reverse=True)

    return render_template('spoc/results.html', event=event, leaderboard=leaderboard)

# --- 5. QR SCANNER PAGE ---
@spoc_bp.route('/scan/<event_id>')
@login_required
@role_required('ClubSPOC')
def scan_page(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/spoc/dashboard')
    event = event_doc.to_dict()
    if event.get('spoc_id') != session.get('user_id'):
        flash("You are not authorised to scan for this event.", "danger")
        return redirect('/spoc/dashboard')
    present_count = len(list(
        db.collection('registrations')
          .where('event_id', '==', event_id)
          .where('attendance', '==', 'Present')
          .stream()
    ))
    total_count = len(list(
        db.collection('registrations')
          .where('event_id', '==', event_id)
          .stream()
    ))
    today_str      = datetime.datetime.now().strftime('%Y-%m-%d')
    event_date_str = str(event.get('date', ''))[:10]
    return render_template(
        'spoc/scan.html',
        event=FirebaseWrapper(event_id, event),
        event_id=event_id,
        present_count=present_count,
        total_count=total_count,
        event_date=event_date_str,
        today=today_str,
        scanning_open=(event_date_str == today_str),
    )


# --- 6. QR CHECK-IN API ---
@spoc_bp.route('/api/checkin/<event_id>/<reg_id>', methods=['POST'])
@login_required
@role_required('ClubSPOC')
def api_checkin(event_id, reg_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return jsonify({'status': 'invalid', 'message': 'Event not found'}), 404
    event = event_doc.to_dict()
    if event.get('spoc_id') != session.get('user_id'):
        return jsonify({'status': 'unauthorized', 'message': 'Not your event'}), 403

    today_str      = datetime.datetime.now().strftime('%Y-%m-%d')
    event_date_str = str(event.get('date', ''))[:10]
    if event_date_str and event_date_str != today_str:
        return jsonify({'status': 'locked', 'message': f'Scanning only opens on {event_date_str}'}), 403

    reg_doc = db.collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        return jsonify({'status': 'invalid', 'message': 'Ticket not found'}), 404

    reg = reg_doc.to_dict()
    if reg.get('event_id') != event_id:
        return jsonify({'status': 'invalid', 'message': 'Ticket is for a different event'}), 400

    if reg.get('attendance') == 'Present':
        return jsonify({
            'status':       'already_in',
            'message':      'Already checked in',
            'name':         reg.get('lead_name', ''),
            'team':         reg.get('team_name', ''),
            'checkin_time': reg.get('checkin_time', ''),
        }), 200

    checkin_time = datetime.datetime.now().strftime("%H:%M:%S")
    db.collection('registrations').document(reg_id).update({
        'attendance':   'Present',
        'checkin_time': checkin_time,
    })
    return jsonify({
        'status':       'success',
        'message':      'Entry granted',
        'name':         reg.get('lead_name', ''),
        'team':         reg.get('team_name', ''),
        'members':      len(reg.get('members', [])),
        'checkin_time': checkin_time,
    }), 200


# --- 7. END EVENT (send certificates + award achievements) ---
@spoc_bp.route('/end_event/<event_id>', methods=['POST'])
@login_required
@role_required('ClubSPOC')
def end_event(event_id):
    try:
        from tasks.cert_tasks import bulk_generate_certificates
        spoc_email = session.get('email', 'spoc')
        db.collection('events').document(event_id).update({
            'status': 'completed',
            'ended_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        bulk_generate_certificates.delay(event_id, triggered_by=spoc_email)
        _award_achievements(event_id)
        flash("Event ended. Certificates sent, achievements awarded!", "success")
    except Exception as e:
        flash(f"Error ending event: {e}", "danger")
    return redirect('/spoc/dashboard')


def _award_achievements(event_id: str):
    """
    Compute final rankings and write XP + badges to each participant's
    user document. Safe to call multiple times — uses set(merge=True).
    """
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return
    event = event_doc.to_dict() or {}
    category = event.get('category', 'General')

    regs = list(db.collection('registrations')
                  .where('event_id', '==', event_id).stream())

    # Build ranked list of scored attendees
    scored = []
    for r in regs:
        d = r.to_dict() or {}
        scores_map = d.get('scores', {})
        if not scores_map or d.get('attendance') != 'Present':
            continue
        avg = round(sum(float(s.get('total', 0)) for s in scores_map.values()) / len(scores_map), 1)
        scored.append({'email': d.get('lead_email', ''), 'score': avg, 'reg_id': r.id})

    scored.sort(key=lambda x: -x['score'])
    top_10_pct_idx = max(1, int(len(scored) * 0.1))

    _CAT_BADGE = {
        'Technical':  ('🔬', 'Technical Champion'),
        'Cultural':   ('🎭', 'Cultural Champion'),
        'Sports':     ('🏅', 'Sports Champion'),
        'Management': ('💼', 'Management Champion'),
    }

    for rank_0, entry in enumerate(scored):
        rank = rank_0 + 1
        email = entry['email']
        if not email:
            continue

        xp = 100  # base for attending + scored
        new_badges = []

        if rank == 1:
            xp += 500
            new_badges += [('🏆', 'Event Winner')]
            if category in _CAT_BADGE:
                new_badges.append(_CAT_BADGE[category])
        elif rank == 2:
            xp += 300
            new_badges.append(('🥈', 'Runner Up'))
        elif rank == 3:
            xp += 200
            new_badges.append(('🥉', 'Bronze Finish'))
        elif rank <= top_10_pct_idx + 3:
            xp += 150
            new_badges.append(('⭐', 'Top Performer'))

        if entry['score'] >= 99:
            new_badges.append(('🎯', 'Perfect Score'))

        user_ref  = db.collection('users').document(email)
        user_snap = user_ref.get()
        existing  = user_snap.to_dict() if user_snap.exists else {}

        total_xp       = int(existing.get('xp', 0) or 0) + xp
        events_attended = int(existing.get('events_attended', 0) or 0) + 1
        existing_badges = existing.get('badges', [])

        if events_attended >= 5:
            new_badges.append(('🎖️', 'Event Veteran'))
        if events_attended >= 1 and not any(b[1] == 'Rising Star' for b in existing_badges):
            new_badges.append(('🌟', 'Rising Star'))

        # Merge — avoid duplicate badge labels
        existing_labels = {b[1] for b in existing_badges}
        for badge in new_badges:
            if badge[1] not in existing_labels:
                existing_badges.append(badge)
                existing_labels.add(badge[1])

        user_ref.set({
            'xp':              total_xp,
            'events_attended': events_attended,
            'badges':          existing_badges,
        }, merge=True)

    # Award participation XP to attendees who weren't scored
    for r in regs:
        d = r.to_dict() or {}
        if d.get('attendance') != 'Present':
            continue
        email = d.get('lead_email', '')
        if not email or any(e['email'] == email for e in scored):
            continue
        user_ref = db.collection('users').document(email)
        snap = user_ref.get()
        ex   = snap.to_dict() if snap.exists else {}
        user_ref.set({
            'xp':              int(ex.get('xp', 0) or 0) + 50,
            'events_attended': int(ex.get('events_attended', 0) or 0) + 1,
        }, merge=True)


# --- 8. LIVE ANNOUNCEMENTS ---
@spoc_bp.route('/announce/<event_id>', methods=['POST'])
@login_required
@role_required('ClubSPOC')
def post_announcement(event_id):
    message  = request.form.get('message', '').strip()
    priority = request.form.get('priority', 'info')
    if not message:
        flash("Announcement cannot be empty.", "warning")
        return redirect('/spoc/dashboard')
    try:
        event_doc = db.collection('events').document(event_id).get()
        event_title = (event_doc.to_dict() or {}).get('title', '') if event_doc.exists else ''
        db.collection('announcements').add({
            'event_id':    event_id,
            'event_title': event_title,
            'message':     message,
            'priority':    priority,
            'spoc_email':  session.get('user_id', ''),
            'timestamp':   datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        flash("Announcement posted!", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect('/spoc/dashboard')


@spoc_bp.route('/announcements/feed')
@login_required
@role_required('ClubSPOC')
def announcements_feed():
    """JSON feed of recent announcements for SPOC's events."""
    spoc_id = session.get('user_id')
    event_ids = [
        e.id for e in db.collection('events').where('spoc_id', '==', spoc_id).stream()
    ]
    items = []
    for doc in (db.collection('announcements')
                  .order_by('timestamp', direction='DESCENDING')
                  .limit(20).stream()):
        d = doc.to_dict()
        if d.get('event_id') in event_ids:
            items.append({
                'id':          doc.id,
                'message':     d.get('message', ''),
                'priority':    d.get('priority', 'info'),
                'event_title': d.get('event_title', ''),
                'timestamp':   d.get('timestamp', ''),
            })
    return jsonify(items)


# --- 9b. PUBLIC ANNOUNCEMENTS FEED (participants poll this) ---
@spoc_bp.route('/announcements/public/<event_id>')
def public_announcements(event_id):
    """Public JSON feed of announcements for a given event (no auth needed)."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    items = []
    for doc in (db.collection('announcements')
                  .where(filter=FieldFilter('event_id', '==', event_id))
                  .order_by('timestamp', direction='DESCENDING')
                  .limit(10).stream()):
        d = doc.to_dict()
        items.append({
            'id':       doc.id,
            'message':  d.get('message', ''),
            'priority': d.get('priority', 'info'),
            'ts':       d.get('timestamp', ''),
        })
    return jsonify(items)


# --- 10. EVENT AGENDA / SCHEDULE BUILDER ---
@spoc_bp.route('/agenda/<event_id>', methods=['GET', 'POST'])
@login_required
@role_required('ClubSPOC')
def manage_agenda(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/spoc/dashboard')

    if request.method == 'POST':
        times  = request.form.getlist('time[]')
        titles = request.form.getlist('title[]')
        descs  = request.form.getlist('desc[]')
        agenda = []
        for t, ti, d in zip(times, titles, descs):
            if t.strip() and ti.strip():
                agenda.append({'time': t.strip(), 'title': ti.strip(), 'desc': d.strip()})
        db.collection('events').document(event_id).update({'agenda': agenda})
        flash("Schedule saved!", "success")
        return redirect(f'/spoc/agenda/{event_id}')

    event  = event_doc.to_dict()
    event['id'] = event_id
    return render_template('spoc/agenda.html', event=event)


# --- 11. PUBLISH RESULTS ---
@spoc_bp.route('/publish_results/<event_id>', methods=['POST'])
@login_required
@role_required('ClubSPOC')
def publish_results(event_id):
    try:
        # Mark event as "Ended" and "Results Published"
        db.collection('events').document(event_id).update({
            'status': 'completed',
            'results_published': True
        })
        flash("Results have been published to the student portal!", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
        
    return redirect(f'/spoc/results/{event_id}')


# --- 12. AI EVENT INTELLIGENCE REPORT ---
@spoc_bp.route('/ai_report/<event_id>')
@login_required
@role_required('ClubSPOC')
def ai_report(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/spoc/dashboard')

    event       = event_doc.to_dict() or {}
    event['id'] = event_id

    if event.get('spoc_id') != session.get('user_id'):
        flash("Not authorised.", "danger")
        return redirect('/spoc/dashboard')

    # ── Build stats ──────────────────────────────────────────────────
    regs = list(db.collection('registrations')
                  .where('event_id', '==', event_id).stream())

    registered  = len(regs)
    attended    = sum(1 for r in regs if r.to_dict().get('attendance') == 'Present')
    att_pct     = round(attended / registered * 100) if registered else 0

    scored_rows = []
    judge_emails = set()
    for r in regs:
        d = r.to_dict() or {}
        sm = d.get('scores', {})
        if not sm:
            continue
        judge_emails.update(sm.keys())
        avg = round(sum(float(s.get('total', 0)) for s in sm.values()) / len(sm), 1)
        scored_rows.append({
            'team':     (d.get('team_name') or d.get('lead_name') or '—').strip(),
            'lead':     (d.get('lead_name') or '').strip(),
            'score':    avg,
            'judges':   len(sm),
            'attended': d.get('attendance') == 'Present',
        })

    scored_rows.sort(key=lambda x: -x['score'])
    max_sc = scored_rows[0]['score'] if scored_rows else 100
    for row in scored_rows:
        row['score_pct'] = int(row['score'] / max_sc * 100) if max_sc else 0

    avg_sc  = round(sum(r['score'] for r in scored_rows) / len(scored_rows), 1) if scored_rows else 0
    top_sc  = scored_rows[0]['score'] if scored_rows else 0
    top3    = scored_rows[:3]

    stats = {
        'registered':    registered,
        'attended':      attended,
        'attendance_pct': att_pct,
        'judges_count':  len(judge_emails),
        'avg_score':     avg_sc,
        'top_score':     top_sc,
    }

    # ── Gemini narrative ─────────────────────────────────────────────
    narrative = _generate_ai_narrative(event, stats, scored_rows[:10])

    generated_at = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    ).strftime('%d %b %Y, %I:%M %p IST')

    return render_template(
        'spoc/ai_report.html',
        event=event,
        stats=stats,
        top3=top3,
        leaderboard=scored_rows,
        narrative=narrative,
        generated_at=generated_at,
    )


def _generate_ai_narrative(event: dict, stats: dict, top10: list) -> str:
    """Call Gemini 2.5 Flash to write a human-like event debrief."""
    from flask import current_app
    api_key = current_app.config.get('GEMINI_API_KEY', '')
    top_names = ', '.join(r['team'] for r in top10[:5]) if top10 else 'N/A'

    fallback = (
        f"<p><strong>{event.get('title','Event')}</strong> concluded with "
        f"<strong>{stats['attended']}</strong> participants present out of "
        f"{stats['registered']} registered ({stats['attendance_pct']}% attendance). "
        f"The event saw strong competition across all teams, with an average score of "
        f"<strong>{stats['avg_score']}</strong>/100 and a top score of "
        f"<strong>{stats['top_score']}</strong>/100.</p>"
        f"<p>Standout performers included: <strong>{top_names}</strong>.</p>"
        f"<p>Overall the event was a success. The organisers are encouraged to review "
        f"the score distribution and gather feedback to improve future editions.</p>"
    )

    if not api_key:
        return fallback

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = (
            f"You are an event analyst writing a concise post-event debrief for "
            f"a college event management report. Write 3 paragraphs in HTML "
            f"(only <p> and <strong> tags). Be specific and data-driven. "
            f"Do not use headings or bullet points.\n\n"
            f"Event: {event.get('title','')}\n"
            f"Category: {event.get('category','')}\n"
            f"Date: {event.get('date','')}\nVenue: {event.get('venue','')}\n"
            f"Registered: {stats['registered']}, Attended: {stats['attended']} "
            f"({stats['attendance_pct']}%)\n"
            f"Scores — Average: {stats['avg_score']}, Top: {stats['top_score']}, "
            f"Judges: {stats['judges_count']}\n"
            f"Top performers: {top_names}\n\n"
            f"Paragraph 1: Summarise the event and overall participation. "
            f"Paragraph 2: Analyse the scoring — competitiveness, standout teams, patterns. "
            f"Paragraph 3: Key takeaway and one actionable recommendation for next edition."
        )
        resp = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        text = (resp.text or '').strip()
        if '<p>' not in text:
            text = ''.join(f'<p>{para.strip()}</p>' for para in text.split('\n\n') if para.strip())
        return text or fallback
    except Exception:
        return fallback


# =========================================================
# 13. BULK EMAIL BLAST — SPOC sends custom email to all registrants
# =========================================================
@spoc_bp.route('/blast_email/<event_id>', methods=['POST'])
@login_required
@role_required('ClubSPOC')
def blast_email(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/spoc/dashboard')

    event = event_doc.to_dict() or {}
    if event.get('spoc_id') != session.get('user_id'):
        flash("Not authorised.", "danger")
        return redirect('/spoc/dashboard')

    subject  = request.form.get('subject', '').strip()
    body     = request.form.get('body', '').strip()
    audience = request.form.get('audience', 'confirmed')  # 'confirmed' | 'all'

    if not subject or not body:
        flash("Subject and message body are required.", "warning")
        return redirect('/spoc/dashboard')

    if len(body) > 5000:
        flash("Message body too long (max 5000 characters).", "warning")
        return redirect('/spoc/dashboard')

    from tasks.email_tasks import send_generic_email_task

    event_title = event.get('title', 'Event')
    regs = db.collection('registrations').where('event_id', '==', event_id).stream()
    queued = 0

    for r in regs:
        d = r.to_dict() or {}
        if audience == 'confirmed' and d.get('status') not in ('Confirmed', 'Paid', 'Free'):
            continue
        email = d.get('lead_email', '')
        name  = d.get('lead_name', 'Participant')
        if not email:
            continue

        personalised_subject = subject
        body_html = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f4f7f6;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px;">
<table width="540" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:12px;border:1px solid #e2e8f0;max-width:540px;">
  <tr><td style="background:#1a2557;padding:24px 32px;border-radius:12px 12px 0 0;">
    <h2 style="margin:0;font-size:17px;color:#fff;">{event_title}</h2>
    <p style="margin:4px 0 0;font-size:12px;color:rgba(255,255,255,.6);">
      Message from your event organiser
    </p>
  </td></tr>
  <tr><td style="padding:28px 32px;">
    <p style="font-size:15px;color:#1e293b;">Hello <strong>{name}</strong>,</p>
    <div style="font-size:14px;color:#334155;line-height:1.75;white-space:pre-wrap;">{body}</div>
  </td></tr>
  <tr><td style="background:#f8fafc;padding:14px 32px;border-top:1px solid #e2e8f0;
          border-radius:0 0 12px 12px;text-align:center;">
    <p style="margin:0;font-size:12px;color:#94a3b8;">
      SapthaEvent &middot; Sapthagiri NPS University, Bengaluru
    </p>
  </td></tr>
</table></td></tr></table>
</body></html>"""

        send_generic_email_task.delay(
            to_email=email,
            subject=personalised_subject,
            body_text=f"Hello {name},\n\n{body}\n\n— SapthaEvent, Sapthagiri NPS University",
            body_html=body_html,
        )
        queued += 1

    log_action(db, "BLAST_EMAIL",
               f"SPOC {session.get('user_id')} blasted '{subject}' to {queued} registrants "
               f"for event {event_id}")
    flash(f"✅ Email queued for {queued} registrant{'s' if queued != 1 else ''}.", "success")
    return redirect('/spoc/dashboard')


# =========================================================
# 14. CLONE EVENT — duplicate an existing event
# =========================================================
@spoc_bp.route('/clone_event/<event_id>', methods=['POST'])
@login_required
@role_required('ClubSPOC')
def clone_event(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/spoc/dashboard')

    src = event_doc.to_dict() or {}
    if src.get('spoc_id') != session.get('user_id'):
        flash("Not authorised to clone this event.", "danger")
        return redirect('/spoc/dashboard')

    # Strip run-specific fields; keep structural config
    _STRIP = {
        'registration_count', 'status', 'ended_at', 'created_at',
        'velocity_alert_sent', 'velocity_alert_sent_at',
        'results_published', 'registration_closed_at',
    }
    clone = {k: v for k, v in src.items() if k not in _STRIP}
    clone['title']               = f"Copy of {src.get('title', 'Event')}"
    clone['date']                = ''
    clone['reg_deadline']        = ''
    clone['registration_count']  = 0
    clone['status']              = 'active'
    clone['has_custom_form']     = False
    clone['created_at']          = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    _, new_ref = db.collection('events').add(clone)
    new_id = new_ref.id

    # Clone the form schema if it exists
    form_doc = db.collection('event_forms').document(event_id).get()
    if form_doc.exists:
        form_data = dict(form_doc.to_dict() or {})
        form_data['event_id'] = new_id
        db.collection('event_forms').document(new_id).set(form_data)
        db.collection('events').document(new_id).update({'has_custom_form': True})

    log_action(db, "EVENT_CLONED",
               f"SPOC {session.get('user_id')} cloned event {event_id} → {new_id}")
    flash(f"✅ Event cloned! Update the date and registration deadline before publishing.", "success")
    return redirect(f'/forms/builder/{new_id}')


