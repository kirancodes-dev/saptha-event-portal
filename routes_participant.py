"""
routes_participant.py  —  Student Dashboard & Actions
======================================================
Fixes & additions in this version
  - All .where() → filter=FieldFilter()
  - /participant/dashboard   enriched: countdown days, score badge,
    certificate eligibility flag, feedback submitted flag
  - /participant/leaderboard/<event_id>  — public live leaderboard
  - /participant/feedback/<reg_id>       — submit feedback (moved here from feedback_bp)
"""
import datetime
import json

from flask import (Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template,
                   request, session)
try:
    from google.cloud import firestore
except ImportError:
    firestore = None
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

class DynamicDBProxy:
    def __getattr__(self, name):
        try:
            import app as app_module
            if hasattr(app_module, 'db') and app_module.db is not None:
                return getattr(app_module.db, name)
        except Exception:
            pass
        try:
            from models import db as models_db
            return getattr(models_db, name)
        except Exception:
            raise AttributeError(f"No DB available for attribute '{name}'")

db = DynamicDBProxy()
from utils import (login_required, role_required, log_action, safe_int, create_registration, generate_reg_id,
                   AlreadyRegistered, venue_label)
from utils_email import send_ticket_email

participant_bp = Blueprint('participant', __name__, url_prefix='/participant')


def _ff(f, op, v):
    return FieldFilter(f, op, v)


def _category_key(category) -> str:
    """A dashboard tab key for an event category: 'Technical' -> 'cat-technical' (UPG-104)."""
    slug = ''.join(ch if ch.isalnum() else '-' for ch in str(category or 'General').strip().lower()).strip('-')
    return f"cat-{slug or 'general'}"


def _days_until(date_str: str) -> "int | None":
    """Returns days until event date, or None if unparseable."""
    try:
        event_date = datetime.datetime.strptime(date_str[:10], '%Y-%m-%d').date()
        delta      = (event_date - datetime.date.today()).days
        return delta
    except Exception:
        return None


# =========================================================
# 1. STUDENT DASHBOARD  (fully enriched)
# =========================================================
def _store():
    """The database object itself, not the proxy (for the SQL-only lookup)."""
    if not isinstance(db, DynamicDBProxy):
        return db
    try:
        import app as app_module
        if getattr(app_module, 'db', None) is not None:
            return app_module.db
    except Exception:
        pass
    from models import db as models_db
    return models_db


def _mine(m, email):
    return isinstance(m, dict) and str(m.get('email') or '').strip().lower() == email


def member_registrations(email):
    """(doc_id, data) for each registration this person is listed on as a team
    member but doesn't lead (UPG-227). On the SQL layer the member rows are
    looked up by email, not every registration read."""
    email = str(email or '').strip().lower()
    if not email:
        return []
    from db_adapter import SQLFirestoreAdapter
    store = _store()
    if isinstance(store, SQLFirestoreAdapter):
        from sqlalchemy import func
        from sqlalchemy.orm import Session

        from db_pg import get_engine
        from models_pg import TeamMember
        with Session(get_engine()) as s:
            ids = {str(row[0]) for row in s.query(TeamMember.registration_id)
                   .filter(func.lower(func.trim(TeamMember.email)) == email).distinct()}
        docs = [store.collection('registrations').document(i).get() for i in sorted(ids)]
    else:
        try:
            docs = list(store.collection('registrations').stream())
        except Exception:
            docs = []
    found = []
    for doc in docs:
        if not getattr(doc, 'exists', True):
            continue
        data = doc.to_dict() or {}
        if str(data.get('lead_email') or '').strip().lower() == email:
            continue   # the lead's own, found by lead_email
        if any(_mine(m, email) for m in data.get('members') or []):
            found.append((doc.id, data))
    return found


@participant_bp.route('/dashboard')
@login_required
@role_required('Student')
def dashboard():
    user_email       = session.get('user_id')
    me               = str(user_email or '').strip().lower()
    active_tickets   = []
    completed_events = []

    led = [(reg.id, reg.to_dict()) for reg in (db.collection('registrations')
                                               .where(filter=_ff('lead_email', '==', user_email))
                                               .stream())]
    led_ids = {reg_id for reg_id, _ in led}
    # A team member sees their team's registration too (UPG-227)
    for reg_id, r in led + member_registrations(me):
        r = dict(r or {})
        r['id'] = reg_id

        event_doc = db.collection('events').document(r.get('event_id', '')).get()
        if not event_doc.exists:
            continue
        evt = event_doc.to_dict()

        # Enrich registration with event info
        r['event_banner'] = evt.get('banner_url', '')
        r['event_date']   = evt.get('date', '')
        r['event_title']  = evt.get('title', r.get('event_title', ''))
        r['event_venue']  = venue_label(evt)   # UPG-111
        r['event_cat']    = evt.get('category', 'General')
        r['days_until']   = _days_until(evt.get('date', ''))

        # Score & rank (from published results)
        scores = r.get('scores', {})
        if scores:
            all_avgs = []
            for s in scores.values():
                all_avgs.append(safe_int(s.get('total', 0)))
            r['my_avg_score'] = round(sum(all_avgs) / len(all_avgs), 1) if all_avgs else None
        else:
            r['my_avg_score'] = None

        r['final_rank']   = r.get('final_rank')
        r['final_score']  = r.get('final_score')
        r['ai_summary']   = r.get('ai_summary')   # Gemini performance summary
        from services_rounds import status_for   # "Round 2 of 3" (UPG-149)
        r['round_status'] = status_for(evt, r)
        import services_hackathon   # the team lead's hackathon page (UPG-196)
        r['is_lead'] = reg_id in led_ids
        r['hackathon_page'] = services_hackathon.is_hackathon(evt) and r['is_lead']
        # A member's own attendance where the gate recorded it, else the team's
        mine = None if r['is_lead'] else next((m for m in r.get('members') or [] if _mine(m, me)), None)
        r['my_attendance'] = str((mine or {}).get('attendance') or '').strip() or r.get('attendance')
        # What the organiser gave registered teams to read and download (UPG-239)
        import services_event_documents
        r['documents'] = services_event_documents.documents(evt)

        # Certificate eligible: attended + event completed or certified
        r['cert_eligible'] = (
            r['my_attendance'] == 'Present' and
            evt.get('status') in ('completed', 'certified')
        )

        # Feedback already submitted?
        r['feedback_done'] = bool(r.get('feedback'))

        # Upcoming: a live event dated today or later, not cancelled. A past
        # date or a cancelled registration goes to past events (UPG-104).
        r['is_cancelled'] = str(r.get('status') or '').strip().lower() in ('cancelled', 'refunded')
        import services_registration_edit   # the lead corrects the details (UPG-225)
        r['may_edit'] = r['is_lead'] and not services_registration_edit.lead_may_edit(r, evt)
        import services_team_confirm   # members confirm their email (UPG-207); a reminder below (UPG-257)
        r['confirm_on'] = services_team_confirm.enabled(evt)
        r['cat_key'] = _category_key(r['event_cat'])
        live = evt.get('status') in ('active', 'published', 'registration_open', 'registration_closed', 'in_progress')
        not_past = r['days_until'] is None or r['days_until'] >= 0
        if live and not_past and not r['is_cancelled']:
            active_tickets.append(r)
        else:
            completed_events.append(r)

    # Sort active by soonest date
    active_tickets.sort(key=lambda x: x.get('event_date', ''))

    # Upcoming events not yet registered for — exclude past events
    today = datetime.date.today().strftime('%Y-%m-%d')
    registered_event_ids = {r.get('event_id') for r in active_tickets + completed_events}
    upcoming_events = []
    calendar_events = []

    # Single query with date pushdown to avoid double table scan
    active_future_events = (
        db.collection('events')
        .where('status', '==', 'active')
        .where('date', '>=', today)
        .order_by('date')
        .limit(100)
        .stream()
    )

    for e in active_future_events:
        d = e.to_dict()
        d['id'] = e.id
        if e.id not in registered_event_ids and len(upcoming_events) < 6:
            d_copy = dict(d)
            d_copy['days_until'] = _days_until(d.get('date', ''))
            upcoming_events.append(d_copy)

        calendar_events.append({
            'title': d.get('title'),
            'start': d.get('date'),
            'color': '#f37021' if d.get('category') == 'Technical' else '#0d2d62'
        })

    # Announcements
    announcements = []
    try:
        for a in (db.collection('announcements')
                    .order_by('timestamp', direction=firestore.Query.DESCENDING)
                    .limit(5).stream()):
            ad = a.to_dict()
            announcements.append({
                'message':  ad.get('message', ''),
                'priority': ad.get('priority', 'info')
            })
    except Exception:
        pass

    # XP + badges + full profile for dashboard header
    user_xp = 0   # no made-up starting points (UPG-65)
    user_badges = []
    user_doc_data = {}
    try:
        uid = session.get('user_id', '')
        if uid:
            u = db.collection('users').document(uid).get()
            if u.exists:
                user_doc_data = u.to_dict() or {}
                user_xp     = int(user_doc_data.get('xp', 0) or user_doc_data.get('activity_points', 0) or 0)
                user_badges = user_doc_data.get('badges', []) or []
    except Exception:
        pass

    all_regs = active_tickets + completed_events
    attended_count = sum(1 for r in all_regs if r.get('my_attendance') == 'Present')
    cat_counts = {
        'technical': sum(1 for r in all_regs if r.get('event_cat') == 'Technical'),
        'cultural': sum(1 for r in all_regs if r.get('event_cat') == 'Cultural'),
        'sports': sum(1 for r in all_regs if r.get('event_cat') == 'Sports'),
        'other': sum(1 for r in all_regs if r.get('event_cat') not in ('Technical', 'Cultural', 'Sports')),
    }
    last_updated = datetime.datetime.now().strftime('%d/%m/%Y  %I:%M %p')

    # The tabs come from the student's own registrations, with counts (UPG-104)
    by_cat = {}
    for r in all_regs:
        label, n = by_cat.get(r['cat_key'], (r['event_cat'] or 'General', 0))
        by_cat[r['cat_key']] = (label, n + 1)
    ticket_tabs = [('all', 'All', len(all_regs)), ('active', 'Upcoming', len(active_tickets)),
                   ('past', 'Past', len(completed_events))]
    ticket_tabs += [(key, label, n) for key, (label, n) in sorted(by_cat.items(), key=lambda kv: (-kv[1][1], kv[0]))]
    certificates = sum(1 for r in completed_events if r.get('cert_eligible'))
    if certificates:
        ticket_tabs.append(('certificates', 'Certificates', certificates))

    # The organiser's documents for their upcoming events, one block an event (UPG-239)
    event_documents, seen = [], set()
    for r in active_tickets:
        if r.get('documents') and r.get('event_id') not in seen:
            seen.add(r.get('event_id'))
            event_documents.append({'event_id': r.get('event_id'), 'event_title': r.get('event_title'),
                                    'team_name': r.get('team_name'), 'is_lead': r.get('is_lead'),
                                    'documents': r['documents']})

    # Waitlists still open for them: waiting, or accepted with a fee to pay (UPG-236)
    my_waitlist = [w for w in _my_waitlist(user_email) if w['state'] in ('waiting', 'pay')]

    # Teams they lead with teammates who haven't confirmed: maybe a wrong email (UPG-257)
    import services_team_confirm
    unconfirmed = []
    for r in active_tickets:
        if r.get('is_lead') and r.get('team_code') and r.get('confirm_on') and services_team_confirm.active(r):
            waiting = [m.get('name') or m.get('email') for m, st in services_team_confirm.summary(r)
                       if st['key'] != 'confirmed']
            if waiting:
                unconfirmed.append({'reg_id': r.get('reg_id') or r['id'], 'team_name': r.get('team_name') or '',
                                    'event_title': r.get('event_title') or '', 'names': waiting})

    return render_template(
        'participant/dashboard.html',
        active_tickets   = active_tickets,
        completed_events = completed_events,
        upcoming_events  = upcoming_events,
        calendar_events  = json.dumps(calendar_events),
        user_name        = session.get('name') or user_doc_data.get('name', 'Student'),
        user_email       = user_email,
        user_profile     = user_doc_data,
        announcements    = announcements,
        user_xp          = user_xp,
        user_badges      = user_badges,
        attended_count   = attended_count,
        total_regs_count = len(all_regs),
        cat_counts       = cat_counts,
        last_updated     = last_updated,
        ticket_tabs      = ticket_tabs,
        my_waitlist      = my_waitlist,
        event_documents  = event_documents,
        unconfirmed      = unconfirmed,
    )


# =========================================================
# 2. CERTIFICATE VIEWER
# =========================================================
@participant_bp.route('/certificate/<reg_id>')
@login_required
@role_required('Student')
def view_certificate(reg_id):
    reg_doc = db.collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        flash("Registration not found.", "danger")
        return redirect('/participant/dashboard')

    reg_data = reg_doc.to_dict() or {}
    user_email = session.get('user_id')
    is_owner = (reg_data.get('lead_email') == user_email) or any(
        (m.get('email') or '').lower() == (user_email or '').lower()
        for m in reg_data.get('members', [])
    )
    if not is_owner:
        flash("Unauthorised access.", "danger")
        return redirect('/participant/dashboard')

    event_data = db.collection('events').document(reg_data['event_id']).get().to_dict() or {}
    event_status = (event_data.get('status') or '').lower()
    if event_status not in ('completed', 'certified'):
        flash("Certificates are only available once the event is completed.", "warning")
        return redirect('/participant/dashboard')

    if reg_data.get('attendance') != 'Present':
        flash("Certificates are only issued to students who attended.", "warning")
        return redirect('/participant/dashboard')

    rules = (event_data.get('workflow_config') or {}).get('rules', {})
    from routes_feedback import has_responded
    if rules.get('require_feedback_for_certificate') and not has_responded(
            reg_data.get('event_id', ''), reg_id, user_email or '', reg_data):
        flash("Please provide your feedback to receive your certificate.", "info")
        return redirect(f'/participant/feedback/{reg_id}')

    # The viewer's own certificate for this event (UPG-138), else an older one on the registration
    import services_certificates
    own = [c for c in services_certificates.for_person([user_email or ''])
           if str(c['event_id']) == str(reg_data.get('event_id')) and c['status'] == 'valid']
    own.sort(key=lambda c: c['cert_type'] not in services_certificates.ATTENDED_TYPES)
    return render_template('participant/certificate.html',
                            student_name=reg_data.get('lead_name'),
                            event=event_data,
                            certificate_number=own[0]['number'] if own else '',
                            certificate_id=reg_data.get('certificate_id'))


# =========================================================
# 3. LIVE LEADERBOARD (public JSON — no login needed)
# =========================================================
@participant_bp.route('/leaderboard/<event_id>')
def leaderboard(event_id):
    """
    Public JSON leaderboard — participants open this on the projector.
    GET /participant/leaderboard/<event_id>
    """
    # One ranking for every board (UPG-84)
    from services_leaderboard import for_event
    board = [{'team_name': row['team_name'], 'lead_name': row['lead_name'], 'score': row['score'],
              'score_text': row['score_text'], 'room': row['room'], 'round': row['round'],
              'judges_count': row['judges'], 'rank': row['rank'], 'tied': row['tied']}
             for row in for_event(db, event_id)]

    # Also render a nice HTML page for projector display
    if request.headers.get('Accept', '').startswith('text/html'):
        event = db.collection('events').document(event_id).get().to_dict() or {}
        return render_template('public/leaderboard.html',
                                board=board, event=event, event_id=event_id)

    return jsonify({'status': 'ok', 'data': board, 'total': len(board)})


# =========================================================
# 4. SUBMIT FEEDBACK (student rates event after attending)
# =========================================================
@participant_bp.route('/feedback/<reg_id>', methods=['GET', 'POST'])
@login_required
@role_required('Student')
def submit_feedback(reg_id):
    from flask import abort
    from routes_feedback import RESPONSES, has_responded, response_id
    reg_ref = db.collection('registrations').document(reg_id)
    reg     = reg_ref.get()
    me      = (session.get('user_id') or '').lower()
    if not reg.exists:
        abort(404)
    reg_data = reg.to_dict() or {}
    is_lead  = (reg_data.get('lead_email') or '').lower() == me
    member   = next((m for m in reg_data.get('members') or [] if (m.get('email') or '').lower() == me), None)
    if not (is_lead or member):
        abort(403)  # the lead or a team member, nobody else (UPG-05)

    # Feedback opens once the attendee checked in, and each person answers once
    if reg_data.get('attendance') != 'Present' or (member and member.get('attendance') == 'Absent'):
        flash("Feedback opens once you've been checked in at the event.", "info")
        return redirect('/participant/dashboard')
    event_id = str(reg_data.get('event_id', ''))
    if has_responded(event_id, reg_id, me, reg_data):
        flash("You've already sent your feedback for this event. Thank you!", "info")
        return redirect('/participant/dashboard')

    if request.method == 'POST':
        rating   = request.form.get('rating', '0')
        comments = request.form.get('comments', '').strip()
        tags     = request.form.getlist('tags')      # e.g. ['Well organised', 'Good venue']

        if not rating.isdigit() or not (1 <= int(rating) <= 5):
            flash("Please select a valid rating (1–5).", "warning")
            return redirect(f'/participant/feedback/{reg_id}')

        sentiment = "Neutral"
        try:
            rating_val = int(rating)
            if rating_val >= 4:
                sentiment = "Positive"
            elif rating_val <= 2:
                sentiment = "Negative"
        except ValueError:
            pass

        api_key = current_app.config.get('GEMINI_API_KEY', '')
        if api_key and comments:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                prompt = (
                    f"Perform sentiment analysis on the following feedback comments: '{comments}'\n"
                    f"Classify the sentiment strictly as one of: 'Positive', 'Neutral', or 'Negative'.\n"
                    f"Respond ONLY with the sentiment label and nothing else."
                )
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                res_text = response.text.strip()
                if res_text in ('Positive', 'Neutral', 'Negative'):
                    sentiment = res_text
            except Exception as e:
                pass

        now = datetime.datetime.now(datetime.timezone.utc)
        response = {'rating': int(rating), 'comments': comments, 'tags': tags, 'sentiment': sentiment}
        name = reg_data.get('lead_name', '') if is_lead else (member or {}).get('name', '')
        db.collection(RESPONSES).document(response_id(event_id, reg_id, me)).set(dict(
            response, event_id=event_id, reg_id=reg_id, email=me, name=name,
            team=reg_data.get('team_name', ''), submitted_at=now.isoformat()))
        if is_lead:  # where the certificate rule and older reports look for it
            reg_ref.update({'feedback': dict(response, timestamp=now)})
        flash("Thank you for your feedback!", "success")
        return redirect('/participant/dashboard')

    event = db.collection('events').document(reg_data.get('event_id', '')).get().to_dict() or {}
    return render_template('participant/feedback_form.html',
                            reg=reg_data, reg_id=reg_id, event=event)


# =========================================================
# 5. PUBLIC REGISTRATION (legacy — kept for back-compat)
# =========================================================
@participant_bp.route('/public_register/<event_id>', methods=['POST'])
def public_register(event_id):
    try:
        event_doc  = db.collection('events').document(event_id).get()
        if not event_doc.exists:
            flash("Event not found.", "danger")
            return redirect('/')

        event_data = event_doc.to_dict()
        # The same check as the registration form (UPG-34)
        from routes_forms import registration_closed
        if registration_closed(event_data):
            flash("Registration is closed for this event.", "warning")
            return redirect(f'/event/{event_id}')

        email      = request.form.get('email', '').lower().strip()
        full_name  = request.form.get('full_name', '').strip()
        usn        = request.form.get('usn', '').upper().strip()
        phone      = request.form.get('phone', '').strip()
        team_name  = request.form.get('team_name', 'Individual').strip() or 'Individual'
        sub_link   = request.form.get('submission_link', '').strip()

        # BLK-02: registration never logs anyone in. A logged-in visitor
        # registers as themselves; an existing account's email registers
        # without logging in and is emailed a cancel link (UPG-97).
        from services_accounts import cancel_url_for, resolve_registrant
        session_email = (session.get('user_id') or '').strip().lower()
        email, without_login = resolve_registrant(db, email)
        if not full_name and session_email:
            full_name = session.get('name', '')

        if not email or not full_name:
            flash("Name and email are required.", "warning")
            return redirect(f'/forms/register/{event_id}')

        # Duplicate check — redirect to their ticket if already registered
        existing = list(
            db.collection('registrations')
              .where(filter=_ff('event_id',   '==', event_id))
              .where(filter=_ff('lead_email', '==', email))
              .limit(1).stream()
        )
        if existing:
            flash("You are already registered for this event. Here is your ticket.", "info")
            return redirect(f"/ticket/{existing[0].id}")

        fee = safe_int(event_data.get('entry_fee', 0))

        # Waitlist check — if event is at capacity, add to waitlist instead
        max_p = int((event_data.get('limits') or {}).get('max_participants', 0) or
                    event_data.get('max_participants', 0) or 0)
        current_count = int(event_data.get('registration_count', 0))
        from services_waitlist import joins_waitlist   # also while teams wait for the SPOC (UPG-243)
        if joins_waitlist(db, event_id, event_data, current_count, max_p):
            # Check if already on waitlists
            wl_existing = list(
                db.collection('waitlists')
                  .where(filter=_ff('event_id', '==', event_id))
                  .where(filter=_ff('email', '==', email))
                  .where(filter=_ff('status', '==', 'waiting'))
                  .limit(1).stream()
            )
            if wl_existing:
                flash("You are already on the waitlist for this event.", "info")
                return redirect('/participant/dashboard')

            # Count existing waitlist to get position
            wl_count = 0
            for _ in (
                db.collection('waitlists')
                  .where(filter=_ff('event_id', '==', event_id))
                  .where(filter=_ff('status', '==', 'waiting'))
                  .stream()
            ):
                wl_count += 1

            wl_id = generate_reg_id('WL')
            wl_entry = {
                'id':            wl_id,
                'event_id':      event_id,
                'event_title':   event_data.get('title', ''),
                'email':         email,
                'user_email':    email,
                'name':          full_name,
                'phone':         phone,
                'payment_status': 'Free' if not fee else 'Pending',
                'amount_paid':   0,
                'joined_at':     datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'status':        'waiting',
                'position':      wl_count + 1,
                'reg_data':      {
                    'event_id': event_id, 'event_title': event_data.get('title'),
                    'lead_email': email, 'lead_name': full_name, 'lead_usn': usn,
                    'lead_phone': phone, 'team_name': team_name,
                    'members': [{'role': 'Team Leader', 'name': full_name, 'email': email, 'usn': usn}],
                    'member_count': 1, 'attendance': 'Pending',
                    'registered_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'is_eliminated': False, 'current_round': 1,
                    'reg_id': generate_reg_id(),
                },
            }
            create_registration(db, wl_id, wl_entry, collection='waitlists')
            from services_waitlist import place_in_line
            place = place_in_line(db, event_id, email) or wl_count + 1   # join order (UPG-114)
            flash(f"This event is full! You've joined the waitlist at position #{place}. We'll email you if a spot opens.", "info")
            return redirect('/participant/dashboard' if session_email else f'/event/{event_id}')

        # New email: unverified account + one-time set-password link
        is_new_user = not session_email and not without_login
        if is_new_user:   # the link goes in the registration's one email below (UPG-152)
            from services_accounts import create_unverified_account, send_set_password_link
            create_unverified_account(db, email, full_name, phone, from_registration=True)

        reg_id   = generate_reg_id()   # UPG-95
        members  = [{'role': 'Team Leader', 'name': full_name,
                      'email': email, 'usn': usn, 'phone': phone}]
        for i, m_name in enumerate(request.form.getlist('member_name[]')):
            if m_name.strip():
                m_usns  = request.form.getlist('member_usn[]')
                m_emails= request.form.getlist('member_email[]')
                m_wapps = request.form.getlist('member_whatsapp[]')
                members.append({
                    'role':     'Member',
                    'name':     m_name.strip(),
                    'usn':      m_usns[i].strip().upper()    if i < len(m_usns)   else '',
                    'email':    m_emails[i].strip().lower()  if i < len(m_emails) else '',
                    'whatsapp': m_wapps[i].strip()           if i < len(m_wapps)  else '',
                })

        reg_data = {
            'reg_id':          reg_id,
            'event_id':        event_id,
            'event_title':     event_data.get('title'),
            'lead_email':      email,
            'lead_name':       full_name,
            'lead_usn':        usn,
            'lead_phone':      phone,
            'team_name':       team_name,
            'submission_link': sub_link,
            'members':         members,
            'member_count':    len(members),
            'attendance':      'Pending',
            'registered_at':   datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'is_eliminated':   False,
            'current_round':   1,
        }
        if without_login:
            reg_data['registered_without_login'] = True   # its emails carry a cancel link (UPG-97)

        if fee > 0:
            session['pending_reg_data'] = reg_data
            if is_new_user:
                send_set_password_link(db, email, full_name)
            return redirect(f'/payment/checkout/{event_id}')

        reg_data.update({'status': 'Confirmed', 'payment_status': 'Free', 'amount_paid': 0})
        try:
            create_registration(db, reg_id, reg_data)
        except AlreadyRegistered:   # another form for this person got there first (UPG-115)
            flash("You're already registered for this event.", "info")
            return redirect('/participant/dashboard' if session_email else f'/event/{event_id}')

        # Award +50 XP for registration
        try:
            from routes_gamification import award_xp
            award_xp(email, 50)
        except Exception as e:
            pass

        # Atomic increment — safe under concurrent registrations
        db.collection('events').document(event_id).update({
            'registration_count': firestore.Increment(1)
        })
        import services_hackathon   # a portal-mode hackathon: the instructions, no ticket email (UPG-195)
        instructions = services_hackathon.registration_instructions(event_data, event_id)
        if is_new_user:   # one email: the set-password link with the registration (UPG-152)
            send_set_password_link(db, email, full_name, registration={
                'event_title': event_data.get('title', ''), 'event_date': event_data.get('date', ''),
                'venue': event_data.get('venue', ''), 'reg_id': reg_id, 'instructions': instructions})
        elif instructions:
            from utils_email import send_registration_confirmed_email
            send_registration_confirmed_email(email, full_name, event_data.get('title', ''),
                                              event_date=event_data.get('date', ''),
                                              venue=event_data.get('venue', ''),
                                              cancel_url=cancel_url_for(reg_data), instructions=instructions)
        else:
            send_ticket_email(email, full_name, event_data.get('title', ''),
                              reg_id, cancel_url=cancel_url_for(reg_data))
        # Each member the lead listed: a link to confirm and set a password (UPG-207)
        import services_team_confirm
        services_team_confirm.after_registration(db, reg_id, reg_data, event_data)
        log_action(db, "REGISTRATION_CONFIRMED", f"{email} registered for {event_id}")
        if session_email:
            return redirect(f'/ticket/{reg_id}')
        session['reg_confirmed'] = {
            'reg_id':      reg_id,
            'event_title': event_data.get('title', ''),
            'event_date':  event_data.get('date', ''),
            'venue':       event_data.get('venue', ''),
            'is_new_user': is_new_user,
            'user_email':  email,
        }
        return redirect('/registration/confirmed')

    except Exception as exc:
        import traceback; traceback.print_exc()
        flash(f"Registration failed: {exc}", "danger")
        return redirect('/')


# =========================================================
# 6. CANCEL REGISTRATION (triggers waitlist promotion)
# =========================================================
@participant_bp.route('/cancel/<reg_id>', methods=['POST'])
@login_required
@role_required('Student')
def cancel_registration(reg_id):
    reg_doc = db.collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        flash("Registration not found.", "danger")
        return redirect('/participant/dashboard')

    reg = reg_doc.to_dict()
    if reg.get('lead_email') != session.get('user_id'):
        flash("Unauthorised.", "danger")
        return redirect('/participant/dashboard')

    cancel_registration_record(reg_id, reg, session.get('user_id'))
    flash("Your registration has been cancelled.", "info")
    return redirect('/participant/dashboard')


def cancel_registration_record(reg_id, reg, actor, reason=''):
    """Cancel one registration: free its seat and promote the waitlist. The
    participant's own cancel and the emailed cancel link share it (UPG-97)."""
    event_id = reg.get('event_id', '')

    # Mark as cancelled
    updates = {'status': 'Cancelled'}
    if reason:
        updates['cancel_reason'] = reason
    db.collection('registrations').document(reg_id).update(updates)

    # Atomic decrement — floor at 0 handled server-side via max check after read
    db.collection('events').document(event_id).update({
        'registration_count': firestore.Increment(-1)
    })

    # Its ticket type's seat is free again (UPG-155)
    if reg.get('ticket_type_id'):
        try:
            import services_ticket_types
            services_ticket_types.give_back_seat(event_id, reg['ticket_type_id'])
        except Exception:
            current_app.logger.warning("Could not free the ticket-type seat of %s", reg_id, exc_info=True)

    # Trigger waitlist promotion
    try:
        from tasks.waitlist_tasks import promote_from_waitlist
        try:
            promote_from_waitlist.delay(event_id)
        except Exception:
            promote_from_waitlist.apply(args=[event_id])
    except Exception:
        pass

    log_action(db, "REGISTRATION_CANCELLED", f"{actor} cancelled {reg_id}" + (f": {reason}" if reason else ''))


# =========================================================
# 6b. CORRECT A REGISTRATION'S DETAILS (UPG-225)
# =========================================================
@participant_bp.route('/registration/<reg_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_registration(reg_id):
    """The team lead corrects their own registration, until the team is
    checked in or the event is over."""
    import services_registration_edit as edit
    doc = db.collection('registrations').document(reg_id).get()
    reg = (doc.to_dict() or {}) if doc.exists else {}
    me = str(session.get('user_id') or '').strip().lower()
    if not reg or str(reg.get('lead_email') or '').strip().lower() != me:
        flash("Only the team lead can change this registration's details.", "warning")
        return redirect('/participant/dashboard')
    event_id = str(reg.get('event_id') or '')
    ev = db.collection('events').document(event_id).get()
    event = dict((ev.to_dict() or {}) if ev.exists else {}, id=event_id)
    back = f'/teams/{reg_id}' if reg.get('team_code') else '/participant/dashboard'
    why_not = edit.lead_may_edit(reg, event)
    if why_not:
        flash(why_not, "warning")
        return redirect(back)
    return registration_edit_page(reg_id, reg, event, organiser=False, back=back)


def registration_edit_page(reg_id, reg, event, organiser, back, member_email_action='', lead_email_action=''):
    """The edit page for the lead and the organiser (UPG-225): GET shows the
    details, POST saves what changed, or shows each problem beside its field."""
    import services_registration_edit as edit
    if request.method == 'POST':
        result = edit.apply(db, reg_id, event['id'], event, request.form, session.get('user_id', ''), organiser)
        if not result['errors']:
            if result['changed']:
                flash(edit.message(result, organiser),
                      'warning' if result['certificates'] or result['gone'] else 'success')
            else:
                flash("Nothing was changed.", "info")
            return redirect(back)
        flash("Some details need correcting; nothing was saved.", "danger")
        page, values, errors = result['page'], result['values'], result['errors']
    else:
        page = edit.build(db, event['id'], event, reg)
        values, errors = page['values'], {}
    return render_template('registration_edit.html', reg=reg, reg_id=reg_id, event=event, page=page,
                           values=values, errors=errors, organiser=organiser, back=back,
                           member_email_action=member_email_action, lead_email_action=lead_email_action)


@participant_bp.route('/event/<event_id>/document/<doc_id>')
@login_required
def event_document(event_id, doc_id):
    """An organiser's PDF (UPG-239): for everyone on a registration for the
    event that isn't cancelled (the lead and the members), and its staff."""
    import services_event_documents as docs
    from services_permission import can
    from utils_storage import StorageError, get_private
    ev = db.collection('events').document(event_id).get()
    if not ev.exists:
        abort(404)
    event = dict(ev.to_dict() or {}, id=event_id)
    doc = docs.find(event, doc_id)
    if not doc or not doc.get('pdf_key'):
        abort(404)
    me = str(session.get('user_id') or '').strip().lower()
    if not can(session, 'manage_registrations', event, db=db):
        led = [(s.id, s.to_dict() or {}) for s in db.collection('registrations')
               .where(filter=_ff('lead_email', '==', me)).stream()]
        if not any(str(r.get('event_id') or '') == str(event_id)
                   and str(r.get('status') or '').strip().lower() not in ('cancelled', 'refunded')
                   for _, r in led + member_registrations(me)):
            abort(403)
    try:
        raw = get_private(doc['pdf_key'])
    except StorageError:
        abort(404)
    name = docs.safe_name(doc.get('pdf_name'))
    return Response(raw, mimetype='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="{name}"',
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})


def _my_waitlist(email) -> list:
    """services_waitlist.standing for this person; [] if it can't be read, so
    the page still opens (UPG-236)."""
    try:
        import services_waitlist
        return services_waitlist.standing(db, email)
    except Exception:
        current_app.logger.warning("Could not read the waitlist standing of %s", email, exc_info=True)
        return []


# =========================================================
# 7. WAITLIST STATUS (JSON — for dashboard badge)
# =========================================================
@participant_bp.route('/waitlist_status')
@login_required
@role_required('Student')
def waitlist_status():
    email = session.get('user_id')
    entries = list(
        db.collection('waitlists')
          .where(filter=_ff('email', '==', email))
          .where(filter=_ff('status', '==', 'waiting'))
          .stream()
    )
    from services_waitlist import place_in_line
    result = []
    for e in entries:
        d = e.to_dict()
        event_id = d.get('event_id', '')
        event_title = d.get('event_title', '')
        if event_id:
            event_doc = db.collection('events').document(event_id).get()
            if event_doc.exists:
                event_title = event_doc.to_dict().get('title', event_title)
        result.append({
            'event_title': event_title,
            'event_id':    event_id,
            'position':    place_in_line(db, event_id, d.get('user_email') or d.get('email', '')) or '?',   # UPG-114
        })
    return jsonify(result)


# =========================================================
# 8. PARTICIPANT BADGE CARD
# =========================================================
@participant_bp.route('/badge/<reg_id>')
@login_required
@role_required('Student')
def badge_card(reg_id):
    reg_doc = db.collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        flash("Registration not found.", "danger")
        return redirect('/participant/dashboard')

    reg = reg_doc.to_dict() or {}
    user_email = session.get('user_id')
    is_owner = (reg.get('lead_email') == user_email) or any(
        (m.get('email') or '').lower() == (user_email or '').lower()
        for m in reg.get('members', [])
    )
    if not is_owner:
        flash("Unauthorised.", "danger")
        return redirect('/participant/dashboard')

    event = db.collection('events').document(reg['event_id']).get().to_dict() or {}
    return render_template('participant/badge.html', reg=reg, event=event, reg_id=reg_id)


# =========================================================
# 9. MY EVENTS (Upcoming, Registered, Waitlisted, Attended, Certificates, Cancelled)
# =========================================================
@participant_bp.route('/my_events')
@login_required
def my_events():
    user_email = (session.get('user_id') or '').strip().lower()
    today_str = datetime.date.today().strftime('%Y-%m-%d')

    upcoming = []
    registered = []
    waitlisted = []
    attended = []
    certificates = []
    cancelled = []

    try:
        # Find registrations for user
        regs = list(db.collection('registrations').where('lead_email', '==', user_email).stream())
        if not regs:
            regs = list(db.collection('registrations').where('student_email', '==', user_email).stream())
        pairs = [(reg.id, reg.to_dict() or {}) for reg in regs]
        seen = {reg_id for reg_id, _ in pairs}
        # A team member's team registrations too (UPG-227)
        pairs += [(reg_id, data) for reg_id, data in member_registrations(user_email) if reg_id not in seen]

        for reg_id, data in pairs:
            r = dict(data)
            r['id'] = reg_id
            r['registration_id'] = reg_id
            # A member's own attendance, where the gate recorded it, decides for them
            mine = next((m for m in r.get('members') or [] if _mine(m, user_email)), None) \
                if str(r.get('lead_email') or '').strip().lower() != user_email else None
            own = str((mine or {}).get('attendance') or '').strip()

            # Fetch event
            ev_id = str(r.get('event_id', ''))
            event_doc = db.collection('events').document(ev_id).get() if ev_id else None
            evt = (event_doc.to_dict() if event_doc and event_doc.exists else {})
            evt['id'] = ev_id

            # Enrich registration object
            r['event_title'] = evt.get('title') or r.get('event_title', 'Campus Event')
            r['event_venue'] = venue_label(evt)   # UPG-111
            r['event_date'] = evt.get('date') or ''
            r['event_start'] = evt.get('start_datetime') or evt.get('date') or ''
            r['event_category'] = evt.get('category') or 'General'
            r['event_status'] = evt.get('status') or 'active'
            r['banner_url'] = evt.get('banner_url') or evt.get('poster_url') or ''
            r['slug'] = evt.get('slug') or ev_id

            # Fetch ticket if any
            ticket = None
            ticket_id = r.get('ticket_id')
            if ticket_id:
                tdoc = db.collection('tickets').document(ticket_id).get()
                if tdoc.exists:
                    ticket = tdoc.to_dict()
            if not ticket and ev_id:
                try:
                    t_stream = list(db.collection('tickets').where('registration_id', '==', reg_id).stream())
                    if t_stream:
                        ticket = t_stream[0].to_dict()
                except Exception:
                    pass
            r['ticket'] = ticket
            r['ticket_code'] = ticket.get('ticket_code') if ticket else r.get('ticket_code')

            # Check check-in status
            is_checked_in = (
                r.get('attendance') == 'Present' or
                r.get('status') == 'checked_in' or
                bool(r.get('checked_in')) or
                bool(r.get('checkin_time')) or
                bool(ticket and ticket.get('checked_in_at'))
            )
            if own:
                is_checked_in = own == 'Present'
            elif not is_checked_in:
                try:
                    chk_stream = list(db.collection('checkins').where('registration_id', '==', reg_id).stream())
                    if not chk_stream and user_email and ev_id:
                        chk_stream = list(db.collection('checkins').where('attendee_email', '==', user_email).where('event_id', '==', ev_id).stream())
                    if chk_stream:
                        is_checked_in = True
                except Exception:
                    pass
            r['is_checked_in'] = is_checked_in

            # Check certificate status
            has_certificate = (
                r.get('certificate_issued') is True or
                bool(r.get('certificate_url')) or
                (is_checked_in and evt.get('status') in ('completed', 'certified'))
            )
            r['has_certificate'] = has_certificate

            # Google calendar URL & .ics
            from services_venue import get_google_calendar_url
            r['google_calendar_url'] = get_google_calendar_url(evt)
            r['ics_url'] = f"/events/{r['slug']}/calendar.ics"

            # Categorize into tabs
            reg_status = (r.get('status') or 'confirmed').strip().lower()
            ev_status = (evt.get('status') or 'active').strip().lower()

            # 1. Cancelled
            if reg_status == 'cancelled' or ev_status == 'cancelled':
                cancelled.append(r)
                continue

            # 2. Waitlisted
            if reg_status in ('waitlist', 'waitlisted'):
                waitlisted.append(r)
                continue

            # 3. Attended
            if is_checked_in:
                attended.append(r)

            # 4. Certificates
            if has_certificate:
                certificates.append(r)

            # 5. Registered (all active registrations)
            registered.append(r)

            # 6. Upcoming (event date is in future / today or later, event is active/published)
            ev_date = r['event_date']
            if ev_date >= today_str or not ev_date:
                upcoming.append(r)

        # Also retrieve standalone certificates from certificates collection
        try:
            certs_stream = db.collection('certificates').where('recipient_email', '==', user_email).stream()
            existing_cert_ids = {c.get('id') for c in certificates if c.get('id')}
            for cdoc in certs_stream:
                cd = cdoc.to_dict()
                cd['id'] = cdoc.id
                if cd['id'] not in existing_cert_ids:
                    certificates.append(cd)
                    existing_cert_ids.add(cd['id'])
        except Exception:
            pass

    except Exception as exc:
        current_app.logger.error("Error loading my_events: %s", exc)

    # Where they stand on each waitlist they or their team joined (UPG-236)
    my_waitlist = _my_waitlist(user_email)

    is_json = (
        request.path.endswith('/api/my_events') or
        request.args.get('format') == 'json' or
        request.headers.get('Accept') == 'application/json'
    )
    if is_json:
        return jsonify({
            'upcoming': upcoming,
            'registered': registered,
            'waitlisted': waitlisted,
            'waitlist': my_waitlist,
            'attended': attended,
            'certificates': certificates,
            'cancelled': cancelled,
        })

    return render_template(
        'participant/my_events.html',
        my_waitlist=my_waitlist,
        upcoming=upcoming,
        registered=registered,
        waitlisted=waitlisted,
        attended=attended,
        certificates=certificates,
        cancelled=cancelled,
        active_tab=request.args.get('tab', 'upcoming'),
    )


@participant_bp.route('/api/my_events')
@login_required
def api_my_events():
    return my_events()


# =========================================================
# 11. PARTICIPATION LEDGER (ACTIVITY POINTS & HOURS - UPG-11)
# =========================================================
@participant_bp.route('/ledger')
@participant_bp.route('/activity_points')
@participant_bp.route('/api/ledger')
@login_required
def participation_ledger():
    user_email = (session.get('user_id') or '').strip().lower()

    # User's registrations
    regs_stream = db.collection('registrations').where('lead_email', '==', user_email).stream()
    registrations = [(r.id, r.to_dict() or {}) for r in regs_stream]

    # Also check if participant is in team members of other registrations
    all_regs = db.collection('registrations').stream()
    found_ids = {r[0] for r in registrations}
    for r in all_regs:
        if r.id in found_ids:
            continue
        data = r.to_dict() or {}
        members = data.get('members') or []
        if any((m.get('email') or '').strip().lower() == user_email for m in members):
            registrations.append((r.id, data))
            found_ids.add(r.id)

    events_map = {}
    for e in db.collection('events').stream():
        events_map[str(e.id)] = e.to_dict() or {}

    entries = []
    total_points = 0.0
    total_hours = 0.0

    # The person's certificates, one per event for the ledger (the attendance one first, UPG-125)
    import services_certificates
    issued = {}
    for c in sorted(services_certificates.for_person([user_email]),
                    key=lambda c: c['cert_type'] not in services_certificates.ATTENDED_TYPES):
        issued.setdefault(str(c['event_id']), c)

    for reg_id, reg in sorted(registrations, key=lambda x: str(x[1].get('registered_at') or ''), reverse=True):
        event_id = str(reg.get('event_id') or '')
        event = events_map.get(event_id, {})

        attendance = str(reg.get('attendance') or '').strip()
        is_present = attendance.lower() == 'present'

        ev_points = float(event.get('activity_points') or 0.0)
        ev_hours = float(event.get('activity_hours') or 0.0)

        # Once per registration, from its current attendance (services_ledger)
        from services_ledger import credit_for
        points_earned, hours_earned = credit_for(reg, event, reg_id)

        total_points += points_earned
        total_hours += hours_earned

        entries.append({
            'reg_id': reg_id,
            'event_id': event_id,
            'event_title': event.get('title') or reg.get('event_title', 'Event'),
            'category': event.get('category', 'General'),
            'date': str(event.get('date') or reg.get('registered_at', '')),
            'attendance': attendance or 'Pending',
            'is_present': is_present,
            'event_points': ev_points,
            'event_hours': ev_hours,
            'points_earned': points_earned,
            'hours_earned': hours_earned,
            'certificate_id': reg.get('certificate_id', ''),
            'certificate_number': (issued.get(event_id) or {}).get('number', ''),
        })

    is_json = (
        request.path.endswith('/api/ledger') or
        request.args.get('format') == 'json' or
        request.headers.get('Accept') == 'application/json' or
        request.is_json
    )
    if is_json:
        return jsonify({
            'user_email': user_email,
            'total_points': total_points,
            'total_hours': total_hours,
            'entries': entries,
        })

    user_doc = db.collection('users').document(user_email).get()
    user_data = (user_doc.to_dict() or {}) if user_doc.exists else {}

    return render_template(
        'participant/ledger.html',
        user_email=user_email,
        user_data=user_data,
        total_points=total_points,
        total_hours=total_hours,
        entries=entries,
        current_page='ledger',
    )



# ── My agenda: starred sessions (UPG-159) ──────────────────────────────────

def _agenda_event_or_404(event_id):
    """The event, if the signed-in user may see it: it's listed for them, or
    they registered for it."""
    from services_event_types import is_listed
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = dict(doc.to_dict() or {}, id=event_id)
    email = (session.get('user_id') or '').lower()
    user = db.collection('users').document(email).get()
    dept = ((user.to_dict() or {}).get('department') or '') if user.exists else ''
    if not is_listed(event, viewer_dept=dept):
        mine = db.collection('registrations').where('event_id', '==', event_id) \
                 .where('lead_email', '==', email).limit(1).stream()
        if not list(mine):
            abort(404)
    return event


@participant_bp.route('/agenda/<event_id>')
@login_required
def my_agenda(event_id):
    import services_sessions
    event = _agenda_event_or_404(event_id)
    sessions = services_sessions.sessions_for(event)
    starred = services_sessions.starred(session.get('user_id'), event_id)
    return render_template('participant/my_agenda.html', event=event,
                           mine=[s for s in sessions if s['id'] in starred],
                           others=[s for s in sessions if s['id'] not in starred])


@participant_bp.route('/agenda/<event_id>/star', methods=['POST'])
@login_required
def star_session(event_id):
    import services_sessions
    event = _agenda_event_or_404(event_id)
    sess = services_sessions.find(event, request.form.get('session_id'))
    if sess is None:
        abort(404)
    services_sessions.star(session.get('user_id'), event_id, sess['id'], on=request.form.get('on') != '0')
    return redirect(f'/participant/agenda/{event_id}')


@participant_bp.route('/agenda/<event_id>.ics')
@login_required
def my_agenda_ics(event_id):
    import services_sessions
    from flask import Response
    event = _agenda_event_or_404(event_id)
    starred = services_sessions.starred(session.get('user_id'), event_id)
    body = services_sessions.ics(event_id, event, [s for s in services_sessions.sessions_for(event) if s['id'] in starred])
    return Response(body, mimetype='text/calendar',
                    headers={'Content-Disposition': f'attachment; filename=my-agenda-{event_id}.ics'})


# ── Transfer a ticket (UPG-161) ────────────────────────────────────────────

@participant_bp.route('/transfer/<reg_id>', methods=['GET', 'POST'])
@login_required
def transfer_ticket(reg_id):
    import services_transfer as transfers
    reg_doc = db.collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        abort(404)
    reg = reg_doc.to_dict() or {}
    me = (session.get('user_id') or '').strip().lower()
    people = {(reg.get('lead_email') or '').lower()} | {(m.get('email') or '').lower() for m in reg.get('members') or []}
    if me not in people:
        abort(403)
    event_id = str(reg.get('event_id') or '')
    ev_doc = db.collection('events').document(event_id).get()
    event = dict(ev_doc.to_dict() or {}, id=event_id) if ev_doc.exists else {}
    allowed, reason = transfers.open_for(event, reg, me)

    if request.method == 'POST':
        if not allowed:
            flash(reason, 'danger')
            return redirect(f'/participant/transfer/{reg_id}'), 303
        if request.form.get('confirm') != 'yes':
            flash("Tick the box to confirm: your ticket stops working once it's transferred.", 'danger')
            return redirect(f'/participant/transfer/{reg_id}'), 303
        try:
            recipient = transfers.check_recipient(db, event_id, event, reg, request.form.get('email', ''))
        except transfers.TransferRefused as exc:
            flash(str(exc), 'danger')
            return redirect(f'/participant/transfer/{reg_id}'), 303
        new = transfers.transfer(db, reg_id, reg, event, recipient, me)
        transfers.notify(reg_id, event, me, reg.get('lead_name', ''), new['lead_email'], new['lead_name'])
        flash(f"Done: your ticket now belongs to {new['lead_name']}. We've emailed you both.", 'success')
        return redirect('/participant/dashboard')

    limit = transfers.cutoff(event)
    return render_template('participant/transfer.html', reg=reg, reg_id=reg_id, event=event,
                           allowed=allowed, reason=reason,
                           closes=limit.strftime('%d %b %Y, %H:%M') if limit else '')
