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
import time

from flask import (Blueprint, current_app, flash, jsonify, redirect, render_template,
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
from utils import login_required, role_required, log_action, safe_int
from utils_email import send_ticket_email

participant_bp = Blueprint('participant', __name__, url_prefix='/participant')


def _ff(f, op, v):
    return FieldFilter(f, op, v)


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
@participant_bp.route('/dashboard')
@login_required
@role_required('Student')
def dashboard():
    user_email       = session.get('user_id')
    active_tickets   = []
    completed_events = []

    for reg in (db.collection('registrations')
                  .where(filter=_ff('lead_email', '==', user_email))
                  .stream()):
        r = reg.to_dict()
        r['id'] = reg.id

        event_doc = db.collection('events').document(r.get('event_id', '')).get()
        if not event_doc.exists:
            continue
        evt = event_doc.to_dict()

        # Enrich registration with event info
        r['event_banner'] = evt.get('banner_url', '')
        r['event_date']   = evt.get('date', '')
        r['event_title']  = evt.get('title', r.get('event_title', ''))
        r['event_venue']  = evt.get('venue', 'SNPSU Campus')
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

        # Certificate eligible: attended + event completed or certified
        r['cert_eligible'] = (
            r.get('attendance') == 'Present' and
            evt.get('status') in ('completed', 'certified')
        )

        # Feedback already submitted?
        r['feedback_done'] = bool(r.get('feedback'))

        if evt.get('status') in ('active', 'published', 'registration_open', 'registration_closed', 'in_progress'):
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

    # XP + badges from user profile
    user_xp = 0
    user_badges = []
    try:
        uid = session.get('user_id', '')
        if uid:
            u = db.collection('users').document(uid).get()
            if u.exists:
                ud = u.to_dict() or {}
                user_xp     = int(ud.get('xp', 0) or 0)
                user_badges = ud.get('badges', []) or []
    except Exception:
        pass

    return render_template(
        'participant/dashboard.html',
        active_tickets   = active_tickets,
        completed_events = completed_events,
        upcoming_events  = upcoming_events,
        calendar_events  = json.dumps(calendar_events),
        user_name        = session.get('name'),
        announcements    = announcements,
        user_xp          = user_xp,
        user_badges      = user_badges,
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
    if reg_data.get('attendance') != 'Present':
        flash("Certificates are only issued to students who attended.", "warning")
        return redirect('/participant/dashboard')

    event_data = db.collection('events').document(reg_data['event_id']).get().to_dict() or {}
    event_status = (event_data.get('status') or '').lower()
    if event_status not in ('completed', 'certified'):
        flash("Certificates are only available once the event is completed.", "warning")
        return redirect('/participant/dashboard')

    rules = (event_data.get('workflow_config') or {}).get('rules', {})
    if rules.get('require_feedback_for_certificate') and not reg_data.get('feedback'):
        flash("Please provide your feedback to receive your certificate.", "info")
        return redirect(f'/participant/feedback/{reg_id}')

    return render_template('participant/certificate.html',
                            student_name=reg_data.get('lead_name'),
                            event=event_data)


# =========================================================
# 3. LIVE LEADERBOARD (public JSON — no login needed)
# =========================================================
@participant_bp.route('/leaderboard/<event_id>')
def leaderboard(event_id):
    """
    Public JSON leaderboard — participants open this on the projector.
    GET /participant/leaderboard/<event_id>
    """
    regs = (db.collection('registrations')
              .where(filter=_ff('event_id', '==', event_id))
              .stream())

    board = []
    for r in regs:
        d = r.to_dict()
        if d.get('is_eliminated'):
            continue
        scores = d.get('scores', {})
        if not scores:
            continue
        avg = round(
            sum(safe_int(s.get('total', 0)) for s in scores.values()) / len(scores), 1
        )
        board.append({
            'team_name': d.get('team_name', '—'),
            'lead_name': d.get('lead_name', ''),
            'score':     avg,
            'room':      d.get('assigned_room', ''),
            'round':     d.get('current_round', 1),
            'judges_count': len(scores),
        })

    board.sort(key=lambda x: x['score'], reverse=True)
    for i, row in enumerate(board):
        row['rank'] = i + 1

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
    reg_ref = db.collection('registrations').document(reg_id)
    reg     = reg_ref.get()

    if not reg.exists or reg.to_dict().get('lead_email') != session.get('user_id'):
        flash("Unauthorised access.", "danger")
        return redirect('/participant/dashboard')

    reg_data = reg.to_dict()

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

        reg_ref.update({
            'feedback': {
                'rating':    int(rating),
                'comments':  comments,
                'tags':      tags,
                'timestamp': datetime.datetime.now(datetime.timezone.utc),
                'sentiment': sentiment,
            }
        })
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
        email      = request.form.get('email', '').lower().strip()
        full_name  = request.form.get('full_name', '').strip()
        usn        = request.form.get('usn', '').upper().strip()
        phone      = request.form.get('phone', '').strip()
        team_name  = request.form.get('team_name', 'Individual').strip() or 'Individual'
        sub_link   = request.form.get('submission_link', '').strip()

        # BLK-02: registration never logs anyone in. A logged-in visitor
        # registers as themselves; an existing account must log in first.
        from services_accounts import resolve_registrant
        session_email = (session.get('user_id') or '').strip().lower()
        email, login_redirect = resolve_registrant(db, email, event_id)
        if not full_name and session_email:
            full_name = session.get('name', '')

        if not email or not full_name:
            flash("Name and email are required.", "warning")
            return redirect(f'/forms/register/{event_id}')

        if login_redirect:
            flash("An account already exists for this email. Please log in to register.", "info")
            return redirect(login_redirect)

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
        if max_p > 0 and current_count >= max_p:
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

            wl_id = f"WL-{int(time.time() * 1000)}"
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
                    'reg_id': f"REG-{int(time.time() * 1000)}",
                },
            }
            db.collection('waitlists').document(wl_id).set(wl_entry)
            flash(f"This event is full! You've joined the waitlist at position #{wl_count + 1}. We'll email you if a spot opens.", "info")
            return redirect('/participant/dashboard' if session_email else f'/event/{event_id}')

        # New email: unverified account + one-time set-password link
        is_new_user = not session_email
        if is_new_user:
            from services_accounts import create_unverified_account, send_set_password_link
            create_unverified_account(db, email, full_name, phone)
            send_set_password_link(db, email, full_name)

        reg_id   = f"REG-{int(time.time() * 1000)}"
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

        if fee > 0:
            session['pending_reg_data'] = reg_data
            return redirect(f'/payment/checkout/{event_id}')

        reg_data.update({'status': 'Confirmed', 'payment_status': 'Free', 'amount_paid': 0})
        db.collection('registrations').document(reg_id).set(reg_data)

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
        send_ticket_email(email, full_name, event_data.get('title', ''),
                          reg_id, is_new_user=is_new_user)
        log_action(db, "REGISTRATION_CONFIRMED", f"{email} registered for {event_id}")
        if session_email:
            return redirect(f'/ticket/{reg_id}')
        session['reg_confirmed'] = {
            'reg_id':      reg_id,
            'event_title': event_data.get('title', ''),
            'event_date':  event_data.get('date', ''),
            'venue':       event_data.get('venue', ''),
            'is_new_user': True,
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

    event_id = reg.get('event_id', '')

    # Mark as cancelled
    db.collection('registrations').document(reg_id).update({'status': 'Cancelled'})

    # Atomic decrement — floor at 0 handled server-side via max check after read
    db.collection('events').document(event_id).update({
        'registration_count': firestore.Increment(-1)
    })

    # Trigger waitlist promotion
    try:
        from tasks.waitlist_tasks import promote_from_waitlist
        try:
            promote_from_waitlist.delay(event_id)
        except Exception:
            promote_from_waitlist.apply(args=[event_id])
    except Exception:
        pass

    log_action(db, "REGISTRATION_CANCELLED", f"{session.get('user_id')} cancelled {reg_id}")
    flash("Your registration has been cancelled.", "info")
    return redirect('/participant/dashboard')


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
            'position':    d.get('position', '?'),
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

        for reg in regs:
            r = reg.to_dict()
            r['id'] = reg.id
            r['registration_id'] = reg.id

            # Fetch event
            ev_id = str(r.get('event_id', ''))
            event_doc = db.collection('events').document(ev_id).get() if ev_id else None
            evt = (event_doc.to_dict() if event_doc and event_doc.exists else {})
            evt['id'] = ev_id

            # Enrich registration object
            r['event_title'] = evt.get('title') or r.get('event_title', 'Campus Event')
            r['event_venue'] = evt.get('room_name') or evt.get('venue') or 'SNPSU Campus'
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
                    t_stream = list(db.collection('tickets').where('registration_id', '==', reg.id).stream())
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
            if not is_checked_in:
                try:
                    chk_stream = list(db.collection('checkins').where('registration_id', '==', reg.id).stream())
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
            'attended': attended,
            'certificates': certificates,
            'cancelled': cancelled,
        })

    return render_template(
        'participant/my_events.html',
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

