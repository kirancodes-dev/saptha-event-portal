import datetime
import json
import secrets
import string
import time

from flask import (Blueprint, flash, redirect, render_template,
                   request, session)
from google.cloud import firestore
from werkzeug.security import generate_password_hash

from models import db
from utils import login_required, role_required, log_action
from utils_email import send_ticket_email
from utils_whatsapp import send_ticket_whatsapp   # ← NEW

participant_bp = Blueprint('participant', __name__, url_prefix='/participant')


# =========================================================
# 1. STUDENT DASHBOARD
# =========================================================
@participant_bp.route('/dashboard')
@login_required
@role_required('Student')
def dashboard():
    user_email       = session.get('user_id')
    active_tickets   = []
    completed_events = []

    for reg in db.collection('registrations').where('lead_email', '==', user_email).stream():
        r = reg.to_dict()
        r['id'] = reg.id
        event_doc = db.collection('events').document(r['event_id']).get()
        if not event_doc.exists:
            continue
        evt = event_doc.to_dict()
        r.update({
            'event_banner': evt.get('banner_url'),
            'event_date':   evt.get('date'),
            'event_title':  evt.get('title'),
            'event_venue':  evt.get('venue', 'SNPSU Campus'),
        })
        if evt.get('status') == 'active':
            active_tickets.append(r)
        else:
            completed_events.append(r)

    calendar_events = []
    for e in db.collection('events').where('status', '==', 'active').stream():
        d = e.to_dict()
        calendar_events.append({
            'title': d.get('title'),
            'start': d.get('date'),
            'color': '#f37021' if d.get('category') == 'Technical' else '#0d2d62'
        })

    announcements = []
    try:
        ann_ref = (db.collection('announcements')
                     .order_by('timestamp', direction=firestore.Query.DESCENDING)
                     .limit(5).stream())
        announcements = [
            {'message':  a.to_dict().get('message', ''),
             'priority': a.to_dict().get('priority', 'info')}
            for a in ann_ref
        ]
    except Exception:
        pass

    return render_template(
        'participant/dashboard.html',
        active_tickets=active_tickets,
        completed_events=completed_events,
        calendar_events=json.dumps(calendar_events),
        user_name=session.get('name'),
        announcements=announcements
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
        flash("Certificates are only issued to students who attended the event.", "warning")
        return redirect('/participant/dashboard')

    event_data = db.collection('events').document(reg_data['event_id']).get().to_dict()
    return render_template('participant/certificate.html',
                            student_name=reg_data.get('lead_name'),
                            event=event_data)


# =========================================================
# 3. PUBLIC REGISTRATION
# =========================================================
@participant_bp.route('/public_register/<event_id>', methods=['POST'])
def public_register(event_id):
    try:
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists:
            flash("Event not found.", "danger")
            return redirect('/')
        event_data = event_doc.to_dict()

        full_name = request.form.get('full_name', '').strip()
        email     = request.form.get('email', '').lower().strip()
        usn       = request.form.get('usn', '').upper().strip()
        phone     = request.form.get('phone', '').strip()
        team_name = request.form.get('team_name', '').strip() or 'Individual'
        sub_link  = request.form.get('submission_link', 'N/A').strip()

        if not full_name or not email:
            flash("Name and email are required.", "warning")
            return redirect(f'/event/{event_id}')

        # Duplicate check
        existing = list(
            db.collection('registrations')
              .where('event_id', '==', event_id)
              .where('lead_email', '==', email)
              .limit(1).stream()
        )
        if existing:
            flash("🚫 You have already registered for this event.", "warning")
            return redirect('/')

        # Auto-create account if new user
        user_ref     = db.collection('users').document(email)
        is_new_user  = not user_ref.get().exists
        raw_password = ""

        if is_new_user:
            alphabet     = string.ascii_letters + string.digits
            raw_password = ''.join(secrets.choice(alphabet) for _ in range(10))
            user_ref.set({
                'email':               email,
                'name':                full_name,
                'role':                'Student',
                'category':            'General',
                'phone':               phone,           # ← store phone for WhatsApp
                'password':            generate_password_hash(raw_password),
                'created_at':          datetime.datetime.now().strftime("%Y-%m-%d"),
                'needs_password_reset': True
            })
            flash(
                f"🆕 Account created! Temporary password: <strong>{raw_password}</strong> "
                f"(also emailed to you).",
                "info"
            )

        # Build member list
        members     = [{'role': 'Team Leader', 'name': full_name,
                         'email': email, 'usn': usn, 'phone': phone}]
        m_names     = request.form.getlist('member_name[]')
        m_usns      = request.form.getlist('member_usn[]')
        m_emails    = request.form.getlist('member_email[]')
        m_whatsapps = request.form.getlist('member_whatsapp[]')

        for i, m_name in enumerate(m_names):
            if m_name.strip():
                members.append({
                    'role':     'Member',
                    'name':     m_name.strip(),
                    'usn':      m_usns[i].strip().upper()   if i < len(m_usns)      else '',
                    'email':    m_emails[i].strip().lower() if i < len(m_emails)    else '',
                    'whatsapp': m_whatsapps[i].strip()      if i < len(m_whatsapps) else '',
                })

        reg_id   = f"REG-{int(time.time() * 1000)}"
        reg_data = {
            'reg_id':          reg_id,
            'event_id':        event_id,
            'event_title':     event_data.get('title'),
            'lead_email':      email,
            'lead_name':       full_name,
            'lead_usn':        usn,
            'lead_phone':      phone,                   # ← store for WhatsApp
            'team_name':       team_name,
            'submission_link': sub_link,
            'members':         members,
            'member_count':    len(members),
            'attendance':      'Pending',
            'registered_at':   datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'is_guest':        'user_id' not in session,
            'is_eliminated':   False,
            'current_round':   1,
        }

        fee = int(event_data.get('entry_fee', 0))
        if fee > 0:
            session['pending_reg_data'] = reg_data
            return redirect(f'/payment/checkout/{event_id}')

        # Free event — save immediately
        reg_data.update({
            'status':         'Confirmed',
            'payment_status': 'Free',
            'amount_paid':    0
        })
        db.collection('registrations').document(reg_id).set(reg_data)
        db.collection('events').document(event_id).update({
            'registration_count': event_data.get('registration_count', 0) + 1
        })

        # ── NOTIFICATIONS ─────────────────────────────────
        # Email (always)
        send_ticket_email(
            email, full_name, event_data.get('title', ''),
            reg_id, is_new_user=is_new_user, raw_password=raw_password
        )
        # WhatsApp (if phone provided)
        if phone:
            send_ticket_whatsapp(
                phone=phone,
                name=full_name,
                event_title=event_data.get('title', ''),
                reg_id=reg_id,
                event_date=event_data.get('date', ''),
                venue=event_data.get('venue', '')
            )
        # ──────────────────────────────────────────────────

        log_action(db, "REGISTRATION_CONFIRMED",
                   f"{email} registered for event {event_id} (free)")

        return redirect(f'/ticket/{reg_id}')

    except Exception as exc:
        import traceback
        traceback.print_exc()
        flash(f"Registration failed: {exc}", "danger")
        return redirect('/')