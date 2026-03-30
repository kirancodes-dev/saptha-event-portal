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
import secrets
import string
import time

from flask import (Blueprint, flash, jsonify, redirect, render_template,
                   request, session)
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from werkzeug.security import generate_password_hash

from models import db
from utils import login_required, role_required, log_action, safe_int
from utils_email import send_ticket_email

participant_bp = Blueprint('participant', __name__, url_prefix='/participant')


def _ff(f, op, v):
    return FieldFilter(f, op, v)


def _days_until(date_str: str) -> int | None:
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

        r['final_rank']   = r.get('final_rank')   # set by publish_results
        r['final_score']  = r.get('final_score')  # set by publish_results

        # Certificate eligible: attended + event completed
        r['cert_eligible'] = (
            r.get('attendance') == 'Present' and
            evt.get('status') == 'completed'
        )

        # Feedback already submitted?
        r['feedback_done'] = bool(r.get('feedback'))

        if evt.get('status') == 'active':
            active_tickets.append(r)
        else:
            completed_events.append(r)

    # Sort active by soonest date
    active_tickets.sort(key=lambda x: x.get('event_date', ''))

    # Calendar feed
    calendar_events = []
    for e in (db.collection('events')
                .where(filter=_ff('status', '==', 'active'))
                .stream()):
        d = e.to_dict()
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

    return render_template(
        'participant/dashboard.html',
        active_tickets   = active_tickets,
        completed_events = completed_events,
        calendar_events  = json.dumps(calendar_events),
        user_name        = session.get('name'),
        announcements    = announcements,
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

    reg_data = reg_doc.to_dict()
    if reg_data.get('lead_email') != session.get('user_id'):
        flash("Unauthorised access.", "danger")
        return redirect('/participant/dashboard')
    if reg_data.get('attendance') != 'Present':
        flash("Certificates are only issued to students who attended.", "warning")
        return redirect('/participant/dashboard')

    event_data = db.collection('events').document(reg_data['event_id']).get().to_dict()
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

        reg_ref.update({
            'feedback': {
                'rating':    int(rating),
                'comments':  comments,
                'tags':      tags,
                'timestamp': datetime.datetime.utcnow(),
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

        if not email or not full_name:
            flash("Name and email are required.", "warning")
            return redirect(f'/forms/register/{event_id}')

        # Duplicate check
        existing = list(
            db.collection('registrations')
              .where(filter=_ff('event_id',   '==', event_id))
              .where(filter=_ff('lead_email', '==', email))
              .limit(1).stream()
        )
        if existing:
            flash("You have already registered for this event.", "warning")
            return redirect('/')

        # Auto-create account
        user_ref     = db.collection('users').document(email)
        is_new_user  = not user_ref.get().exists
        raw_password = ''
        if is_new_user:
            alphabet     = string.ascii_letters + string.digits
            raw_password = ''.join(secrets.choice(alphabet) for _ in range(10))
            user_ref.set({
                'email':               email,
                'name':                full_name,
                'role':                'Student',
                'category':            'General',
                'password':            generate_password_hash(raw_password),
                'created_at':          datetime.datetime.now().strftime('%Y-%m-%d'),
                'needs_password_reset': True,
            })

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

        fee = safe_int(event_data.get('entry_fee', 0))
        if fee > 0:
            session['pending_reg_data'] = reg_data
            return redirect(f'/payment/checkout/{event_id}')

        reg_data.update({'status': 'Confirmed', 'payment_status': 'Free', 'amount_paid': 0})
        db.collection('registrations').document(reg_id).set(reg_data)
        db.collection('events').document(event_id).update({
            'registration_count': event_data.get('registration_count', 0) + 1
        })
        send_ticket_email(email, full_name, event_data.get('title', ''),
                          reg_id, is_new_user=is_new_user, raw_password=raw_password)
        session['user_id']  = email
        session['name']     = full_name
        session['role']     = 'Student'
        session['category'] = 'General'
        log_action(db, "REGISTRATION_CONFIRMED", f"{email} registered for {event_id}")
        return redirect(f'/ticket/{reg_id}')

    except Exception as exc:
        import traceback; traceback.print_exc()
        flash(f"Registration failed: {exc}", "danger")
        return redirect('/')