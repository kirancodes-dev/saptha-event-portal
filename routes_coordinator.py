from flask import Blueprint, render_template, request, redirect, session, flash, jsonify
from models import db
from utils import login_required, role_required
import datetime
from werkzeug.security import generate_password_hash
from utils_email import send_credentials_email, send_broadcast_email, send_appointment_email, send_ticket_email
from google.cloud import firestore

coord_bp = Blueprint('coordinator', __name__, url_prefix='/coordinator')

# ========================================================
# PART 1: CLUB SPOC DASHBOARD (EVENT MANAGEMENT)
# ========================================================

@coord_bp.route('/dashboard')
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def dashboard():
    club_category = session.get('category', 'General')
    
    if club_category == 'All' or session.get('role') == 'SuperAdmin':
        events_ref = db.collection('events').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
    else:
        events_ref = db.collection('events').where('category', '==', club_category).stream()
        
    events = []
    total_regs = 0
    total_staff = 0
    
    for e in events_ref:
        d = e.to_dict()
        d['id'] = e.id
        total_regs += d.get('registration_count', 0)
        total_staff += len(d.get('staff', []))
        
        # Calculate judged teams
        regs = db.collection('registrations').where('event_id', '==', e.id).stream()
        d['scored_teams'] = sum(1 for r in regs if r.to_dict().get('scores'))
        events.append(d)
        
    return render_template('coordinator/dashboard.html', events=events, club_category=club_category, total_regs=total_regs, total_staff=total_staff, user_name=session.get('name'))

@coord_bp.route('/create_event', methods=['POST'])
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def create_event():
    try:
        overview = request.form.get('overview', '')
        db.collection('events').add({
            'title': request.form.get('title'),
            'date': request.form.get('date'),
            'venue': request.form.get('venue'),
            'description': overview[:120] + "..." if len(overview) > 120 else overview,
            'overview': overview,
            'rules': request.form.get('rules', ''),
            'prizes': request.form.get('prizes', ''),
            'category': session.get('category') if session.get('category') != 'All' else request.form.get('category', 'General'),
            'banner_url': request.form.get('banner_url'),
            'entry_fee': int(request.form.get('entry_fee', 0)),
            'is_team_event': request.form.get('is_team') == 'on',
            'status': 'active',
            'registration_count': 0,
            'staff': [], 
            'created_by': session.get('name'),
            'created_at': datetime.datetime.now()
        })
        flash(f"✅ Event created successfully!", "success")
    except Exception as e:
        flash(f"Error creating event: {e}", "danger")
    return redirect('/coordinator/dashboard')

@coord_bp.route('/edit_event/<event_id>', methods=['POST'])
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def edit_event(event_id):
    try:
        overview = request.form.get('overview', '')
        db.collection('events').document(event_id).update({
            'title': request.form.get('title'),
            'date': request.form.get('date'),
            'venue': request.form.get('venue'),
            'overview': overview,
            'description': overview[:120] + "..." if len(overview) > 120 else overview,
            'rules': request.form.get('rules', ''),
            'prizes': request.form.get('prizes', ''),
            'banner_url': request.form.get('banner_url'),
            'entry_fee': int(request.form.get('entry_fee', 0)),
            'is_team_event': request.form.get('is_team') == 'on'
        })
        flash(f"✅ Event updated successfully!", "success")
    except Exception as e:
        flash(f"Error updating event: {e}", "danger")
    return redirect('/coordinator/dashboard')

@coord_bp.route('/assign_staff/<event_id>', methods=['POST'])
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def assign_staff(event_id):
    try:
        name = request.form.get('name')
        email = request.form.get('email').lower().strip()
        role = request.form.get('role')
        
        # Get Event Title for email notification
        event_doc = db.collection('events').document(event_id).get()
        event_title = event_doc.to_dict().get('title') if event_doc.exists else 'Upcoming Event'
        
        import secrets, string
        user_ref = db.collection('users').document(email)
        
        # 1. IF NEW USER -> Create account and email password
        if not user_ref.get().exists:
            alphabet = string.ascii_letters + string.digits
            raw_pw = ''.join(secrets.choice(alphabet) for i in range(8))
            user_ref.set({
                'email': email, 'name': name, 'role': role, 'category': session.get('category', 'General'),
                'password': generate_password_hash(raw_pw), 'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
            })
            send_credentials_email(email, name, role, raw_pw, session.get('category', 'General'))
            flash(f"✅ Account created & password emailed to {email}.", "success")
            
        # 2. IF EXISTING USER -> Promote them and notify via email
        else:
            if user_ref.get().to_dict().get('role') == 'Student': 
                user_ref.update({'role': role})
            send_appointment_email(email, name, role, event_title)
            flash(f"📩 {name} already had an account. Their role was updated and an alert email was sent!", "info")

        # 3. Add to event's staff list
        db.collection('events').document(event_id).update({
            'staff': firestore.ArrayUnion([{'name': name, 'email': email, 'role': role}])
        })
        flash(f"🎉 {name} officially appointed as {role}!", "success")
        
    except Exception as e:
        flash(f"Assignment Error: {e}", "danger")
    return redirect('/coordinator/dashboard')

@coord_bp.route('/broadcast/<event_id>', methods=['POST'])
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def broadcast_message(event_id):
    try:
        subject = request.form.get('subject')
        message = request.form.get('message')
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists: return redirect('/coordinator/dashboard')
        
        regs = db.collection('registrations').where('event_id', '==', event_id).stream()
        email_list = list(set([r.to_dict().get('lead_email') for r in regs if r.to_dict().get('lead_email')]))

        if send_broadcast_email(email_list, subject, message, event_doc.to_dict().get('title')):
            flash(f"📢 Broadcast sent to {len(email_list)} participants!", "success")
        else:
            flash("❌ Failed to send broadcast.", "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect('/coordinator/dashboard')

@coord_bp.route('/publish_results/<event_id>', methods=['POST'])
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def publish_results(event_id):
    try:
        event_ref = db.collection('events').document(event_id)
        regs = db.collection('registrations').where('event_id', '==', event_id).stream()
        leaderboard = []
        for r in regs:
            d = r.to_dict()
            scores = d.get('scores', {})
            if scores:
                avg = round(sum([int(s['total']) for s in scores.values()]) / len(scores), 2)
                leaderboard.append({'team_name': d.get('team_name'), 'lead_name': d.get('lead_name'), 'score': avg})
        
        leaderboard.sort(key=lambda x: x['score'], reverse=True)
        event_ref.update({'status': 'completed', 'winners': leaderboard[:3], 'completed_at': datetime.datetime.now()})
        flash(f"🏆 Results Published!", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect('/coordinator/dashboard')

@coord_bp.route('/delete_event/<event_id>')
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def delete_event(event_id):
    db.collection('events').document(event_id).delete()
    regs = db.collection('registrations').where('event_id', '==', event_id).stream()
    for r in regs: r.reference.delete()
    flash("Event deleted.", "danger")
    return redirect('/coordinator/dashboard')


# ========================================================
# PART 2: EVENT COORDINATOR (SCANNER & HELPDESK)
# ========================================================

@coord_bp.route('/scanner')
@login_required
@role_required(['EventCoordinator', 'SuperAdmin'])
def scanner_selector():
    events_ref = db.collection('events').where('status', '==', 'active').stream()
    events = [{'id': e.id, 'title': e.to_dict().get('title')} for e in events_ref]
    return render_template('coordinator/scanner_selector.html', events=events)

@coord_bp.route('/scan/<event_id>')
@login_required
@role_required(['EventCoordinator', 'SuperAdmin'])
def scan_page(event_id):
    doc = db.collection('events').document(event_id).get()
    if not doc.exists: return redirect('/coordinator/scanner')
    return render_template('coordinator/scan.html', event_id=event_id, event_title=doc.to_dict().get('title'))

@coord_bp.route('/mark_attendance', methods=['POST'])
@login_required
def mark_attendance():
    try:
        data = request.json
        reg_ref = db.collection('registrations').document(data.get('reg_id'))
        reg = reg_ref.get()
        if not reg.exists: return jsonify({'status': 'error', 'message': '❌ INVALID TICKET'})
        
        reg_data = reg.to_dict()
        if reg_data.get('event_id') != data.get('event_id'): return jsonify({'status': 'error', 'message': '⚠️ WRONG EVENT!'})
        if reg_data.get('payment_status') == 'Pending': return jsonify({'status': 'error', 'message': '💰 PAYMENT PENDING!'})
        if reg_data.get('attendance') == 'Present': return jsonify({'status': 'warning', 'message': f"⚠️ ALREADY SCANNED!\nStudent: {reg_data['lead_name']}"})
        
        reg_ref.update({'attendance': 'Present', 'checkin_time': datetime.datetime.now().strftime("%H:%M:%S")})
        return jsonify({'status': 'success', 'message': f"✅ VERIFIED!\nWelcome, {reg_data['lead_name']}", 'usn': reg_data.get('lead_usn', 'N/A')})
    except Exception:
        return jsonify({'status': 'error', 'message': 'Server Error'})

@coord_bp.route('/on_spot')
@login_required
@role_required(['EventCoordinator', 'SuperAdmin'])
def on_spot_form():
    events_ref = db.collection('events').where('status', '==', 'active').stream()
    events = [{'id': e.id, 'title': e.to_dict().get('title')} for e in events_ref]
    return render_template('coordinator/on_spot.html', events=events)

@coord_bp.route('/process_walkin', methods=['POST'])
@login_required
def process_walkin():
    try:
        event_id = request.form.get('event_id')
        email = request.form.get('email').lower().strip()
        name = request.form.get('name')
        
        user_ref = db.collection('users').document(email)
        if not user_ref.get().exists:
            user_ref.set({'email': email, 'name': name, 'phone': request.form.get('phone'), 'usn': request.form.get('usn').upper(), 'role': 'Student', 'password': generate_password_hash('welcome123'), 'created_at': datetime.datetime.now().strftime("%Y-%m-%d")})
        
        reg_id = f"REG-{int(datetime.datetime.now().timestamp())}"
        event_doc = db.collection('events').document(event_id).get().to_dict()
        
        db.collection('registrations').document(reg_id).set({
            'reg_id': reg_id, 'event_id': event_id, 'event_title': event_doc.get('title'),
            'lead_name': name, 'lead_email': email, 'lead_usn': request.form.get('usn').upper(), 'team_name': 'Walk-in',
            'members': [], 'status': 'Confirmed', 'payment_status': 'Paid', 'amount_paid': event_doc.get('entry_fee', 0), 'payment_mode': request.form.get('payment_mode'),
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'attendance': 'Present', 'checkin_time': datetime.datetime.now().strftime("%H:%M:%S")
        })
        send_ticket_email(email, name, event_doc.get('title'), reg_id)
        flash(f"✅ Walk-in Registered! Ticket sent.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect('/coordinator/on_spot')