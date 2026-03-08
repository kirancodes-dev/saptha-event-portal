from flask import Blueprint, render_template, request, redirect, session, flash
from models import db
from utils import login_required, role_required
from utils_email import send_ticket_email, send_credentials_email
from werkzeug.security import generate_password_hash
import datetime
import json
import secrets
import string
from google.cloud import firestore

participant_bp = Blueprint('participant', __name__, url_prefix='/participant')

# --- 1. STUDENT DASHBOARD ---
@participant_bp.route('/dashboard')
@login_required
@role_required('Student')
def dashboard():
    user_email = session.get('user_id')
    
    # Fetch My Registrations (Split into Active vs Completed)
    my_regs_ref = db.collection('registrations').where('lead_email', '==', user_email).stream()
    active_tickets = []
    completed_events = []
    
    for reg in my_regs_ref:
        r_data = reg.to_dict()
        r_data['id'] = reg.id
        event_doc = db.collection('events').document(r_data['event_id']).get()
        
        if event_doc.exists:
            evt = event_doc.to_dict()
            r_data['event_banner'] = evt.get('banner_url')
            r_data['event_date'] = evt.get('date')
            r_data['event_title'] = evt.get('title')
            r_data['event_venue'] = evt.get('venue', 'SNPSU Campus')
            
            if evt.get('status') == 'active':
                active_tickets.append(r_data)
            else:
                completed_events.append(r_data)

    # Fetch Upcoming Events for Calendar
    upcoming_ref = db.collection('events').where('status', '==', 'active').stream()
    calendar_events = []
    for doc in upcoming_ref:
        e = doc.to_dict()
        calendar_events.append({
            'title': e.get('title'),
            'start': e.get('date'), # Assumes date is in a parseable format
            'color': '#f37021' if e.get('category') == 'Technical' else '#0d2d62'
        })

    # Fetch Announcements
    anns_ref = db.collection('announcements').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(5).stream()
    announcements = [{'message': a.to_dict()['message'], 'priority': a.to_dict()['priority']} for a in anns_ref]

    return render_template('participant/dashboard.html', 
                           active_tickets=active_tickets,
                           completed_events=completed_events,
                           calendar_events=json.dumps(calendar_events),
                           user_name=session.get('name'),
                           announcements=announcements)

# --- 2. DIGITAL CERTIFICATE VIEWER ---
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
        flash("Unauthorized access.", "danger")
        return redirect('/participant/dashboard')

    if reg_data.get('attendance') != 'Present':
        flash("Certificates are only issued to students who physically attended the event.", "warning")
        return redirect('/participant/dashboard')
        
    event_data = db.collection('events').document(reg_data['event_id']).get().to_dict()
    return render_template('participant/certificate.html', student_name=reg_data.get('lead_name'), event=event_data)

# --- 3. SMART PUBLIC REGISTRATION (TEAM SUPPORTED) ---
@participant_bp.route('/public_register/<event_id>', methods=['POST'])
def public_register(event_id):
    try:
        # 1. Fetch Event
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists:
            flash("Event not found.", "danger")
            return redirect('/')
        event_data = event_doc.to_dict()

        # 2. Capture Lead Data
        full_name = request.form.get('full_name')
        email = request.form.get('email').lower().strip()
        usn = request.form.get('usn').upper().strip()
        phone = request.form.get('phone')
        team_name = request.form.get('team_name') or "Individual"
        submission_link = request.form.get('submission_link', 'N/A')

        # --- SMART USER CHECK (Auto-Create Account) ---
        user_ref = db.collection('users').document(email)
        if not user_ref.get().exists:
            alphabet = string.ascii_letters + string.digits
            raw_password = ''.join(secrets.choice(alphabet) for i in range(8))
            
            user_ref.set({
                'email': email, 'name': full_name, 'role': 'Student', 'category': 'General',
                'password': generate_password_hash(raw_password), 'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
            })
            send_credentials_email(email, full_name, 'Student', raw_password)
            flash(f"🆕 Account Created! Password sent to {email}", "info")

        # 3. Duplicate Check
        existing_email = db.collection('registrations').where('event_id', '==', event_id).where('lead_email', '==', email).stream()
        if any(existing_email):
            flash("🚫 You have already registered for this event. Please login to dashboard.", "warning")
            return redirect('/') 

        # 4. Build Member List
        members = [{'role': 'Team Leader', 'name': full_name, 'email': email, 'usn': usn, 'phone': phone}]
        m_names = request.form.getlist('member_name[]')
        m_usns = request.form.getlist('member_usn[]')
        m_emails = request.form.getlist('member_email[]')
        m_whatsapps = request.form.getlist('member_whatsapp[]')

        for i in range(len(m_names)):
            if m_names[i].strip():
                members.append({
                    'role': 'Member', 'name': m_names[i].strip(),
                    'usn': m_usns[i].strip().upper() if i < len(m_usns) else '',
                    'email': m_emails[i].strip().lower() if i < len(m_emails) else '',
                    'whatsapp': m_whatsapps[i].strip() if i < len(m_whatsapps) else ''
                })

        # 5. Prepare Registration Data
        reg_id = f"REG-{int(datetime.datetime.now().timestamp())}"
        reg_data = {
            'reg_id': reg_id, 'event_id': event_id, 'event_title': event_data.get('title'),
            'lead_email': email, 'lead_name': full_name, 'lead_usn': usn, 'team_name': team_name,
            'submission_link': submission_link, 'members': members, 'member_count': len(members),
            'attendance': 'Pending', 'is_guest': 'user_id' not in session,
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 6. Logic Split: Free vs Paid
        fee = int(event_data.get('entry_fee', 0))
        if fee > 0:
            session['pending_reg_data'] = reg_data
            return redirect(f'/payment/checkout/{event_id}')
        else:
            reg_data['status'] = 'Confirmed'
            reg_data['payment_status'] = 'Free'
            reg_data['amount_paid'] = 0
            
            db.collection('registrations').document(reg_id).set(reg_data)
            db.collection('events').document(event_id).update({'registration_count': event_data.get('registration_count', 0) + 1})
            send_ticket_email(email, full_name, event_data.get('title'), reg_id)
            
            return render_template('participant/success.html', event_title=event_data.get('title'))

    except Exception as e:
        print(f"Reg Error: {e}")
        flash("Registration Failed. Please try again.", "danger")
        return redirect('/')