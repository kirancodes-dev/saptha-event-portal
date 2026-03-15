from flask import Blueprint, render_template, request, redirect, session, flash, jsonify, Response
from models import db
from utils import login_required, role_required
import datetime
import csv
import random 
from io import StringIO
from werkzeug.security import generate_password_hash
from utils_email import send_credentials_email, send_broadcast_email, send_appointment_email, send_ticket_email
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter 

coord_bp = Blueprint('coordinator', __name__, url_prefix='/coordinator')

# ========================================================
# PART 1: CLUB SPOC DASHBOARD (EVENT MANAGEMENT)
# ========================================================

@coord_bp.route('/dashboard')
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def dashboard():
    club_category = session.get('category', 'General')
    user_role = session.get('role')
    user_email = session.get('user_id')
    
    # STRICT CREATOR FILTERING LOGIC
    if user_role in ['SuperAdmin', 'Super Admin'] or club_category == 'All':
        events_ref = db.collection('events').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
    else:
        events_ref = db.collection('events').where(filter=FieldFilter('created_by_email', '==', user_email)).stream()
        
    events = []
    total_regs = 0
    total_staff = 0
    
    for e in events_ref:
        d = e.to_dict()
        d['id'] = e.id
        total_regs += d.get('registration_count', 0)
        total_staff += len(d.get('staff', []))
        
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
        raw_criteria = request.form.get('criteria', 'Overall Score')
        criteria_list = [c.strip() for c in raw_criteria.split(',') if c.strip()]
        if not criteria_list: criteria_list = ['Overall Score']

        media_urls = request.form.getlist('media_urls[]')
        media_urls = [url.strip() for url in media_urls if url.strip()] 

        db.collection('events').add({
            'title': request.form.get('title'),
            'date': request.form.get('date'),
            'deadline': request.form.get('deadline'), 
            'venue': request.form.get('venue'),
            'description': overview[:120] + "..." if len(overview) > 120 else overview,
            'overview': overview,
            'rules': request.form.get('rules', ''),
            'prizes': request.form.get('prizes', ''),
            'category': session.get('category') if session.get('category') != 'All' else request.form.get('category', 'General'),
            'media_urls': media_urls,  
            'banner_url': media_urls[0] if media_urls else '', 
            'entry_fee': int(request.form.get('entry_fee', 0)),
            'is_team_event': request.form.get('is_team') == 'on',
            'judging_criteria': criteria_list,
            'status': 'active',
            'active_round': 1, # 🚀 NEW: Start at Round 1
            'registration_count': 0,
            'staff': [], 
            'created_by': session.get('name'),
            'created_by_email': session.get('user_id'), 
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
        raw_criteria = request.form.get('criteria', 'Overall Score')
        criteria_list = [c.strip() for c in raw_criteria.split(',') if c.strip()]
        if not criteria_list: criteria_list = ['Overall Score']

        media_urls = request.form.getlist('media_urls[]')
        media_urls = [url.strip() for url in media_urls if url.strip()]

        db.collection('events').document(event_id).update({
            'title': request.form.get('title'),
            'date': request.form.get('date'),
            'deadline': request.form.get('deadline'),
            'venue': request.form.get('venue'),
            'overview': overview,
            'description': overview[:120] + "..." if len(overview) > 120 else overview,
            'rules': request.form.get('rules', ''),
            'prizes': request.form.get('prizes', ''),
            'judging_criteria': criteria_list,
            'media_urls': media_urls, 
            'banner_url': media_urls[0] if media_urls else '', 
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
        
        event_doc = db.collection('events').document(event_id).get()
        event_title = event_doc.to_dict().get('title') if event_doc.exists else 'Upcoming Event'
        
        import secrets, string
        user_ref = db.collection('users').document(email)
        
        if not user_ref.get().exists:
            alphabet = string.ascii_letters + string.digits
            raw_pw = ''.join(secrets.choice(alphabet) for i in range(8))
            user_ref.set({
                'email': email, 'name': name, 'role': role, 'category': session.get('category', 'General'),
                'password': generate_password_hash(raw_pw), 
                'created_at': datetime.datetime.now().strftime("%Y-%m-%d"),
                'needs_password_reset': True 
            })
            send_credentials_email(email, name, role, raw_pw, session.get('category', 'General'))
            flash(f"✅ Account created & password emailed to {email}.", "success")
        else:
            if user_ref.get().to_dict().get('role') == 'Student': 
                user_ref.update({'role': role})
            send_appointment_email(email, name, role, event_title)
            flash(f"📩 {name} already had an account. Their role was updated and an alert email was sent!", "info")

        db.collection('events').document(event_id).update({
            'staff': firestore.ArrayUnion([{'name': name, 'email': email, 'role': role}])
        })
        flash(f"🎉 {name} officially appointed as {role}!", "success")
        
    except Exception as e:
        flash(f"Assignment Error: {e}", "danger")
    return redirect('/coordinator/dashboard')

# --- 🚀 AUTO-RANDOM ROOM & JUDGE ALLOCATION ENGINE (ROUND-AWARE) ---
@coord_bp.route('/allocate_rooms/<event_id>', methods=['POST'])
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def allocate_rooms(event_id):
    try:
        room_names = request.form.getlist('room_name[]')
        capacities = request.form.getlist('capacity[]')

        event_doc = db.collection('events').document(event_id).get().to_dict()
        
        # 1. Gather all Judges for this event and shuffle them
        judges = [s for s in event_doc.get('staff', []) if s['role'] == 'Judge']
        if len(judges) < len(room_names):
            flash(f"⚠️ You defined {len(room_names)} rooms, but only have {len(judges)} judges appointed. Please appoint more judges!", "warning")
            return redirect('/coordinator/dashboard')
            
        random.shuffle(judges) 

        # 2. 🚀 Gather and shuffle teams (ONLY THOSE NOT ELIMINATED)
        regs_ref = db.collection('registrations').where('event_id', '==', event_id).stream()
        regs = [r for r in regs_ref if r.to_dict().get('is_eliminated', False) == False]
        random.shuffle(regs)

        reg_index = 0
        for i in range(len(room_names)):
            room = room_names[i].strip()
            cap = int(capacities[i])
            assigned_judge = judges[i] 

            for _ in range(cap):
                if reg_index < len(regs):
                    reg_doc = regs[reg_index]
                    db.collection('registrations').document(reg_doc.id).update({
                        'assigned_room': room,
                        'assigned_judge_email': assigned_judge['email'],
                        'assigned_judge_name': assigned_judge['name']
                    })
                    reg_index += 1
                else:
                    break 
                    
        flash(f"✨ Successfully randomized and allocated {reg_index} active teams! Judges were automatically assigned.", "success")
    except Exception as e:
        flash(f"Allocation Error: {e}", "danger")
        
    return redirect('/coordinator/dashboard')

# ========================================================
# 🚀 NEW: PROMOTE TEAMS TO NEXT ROUND (ELIMINATION ENGINE)
# ========================================================
@coord_bp.route('/promote_round/<event_id>', methods=['POST'])
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin', 'Super Admin'])
def promote_round(event_id):
    try:
        # Get the cut-off score from the modal
        cutoff_score = float(request.form.get('cutoff_score', 0))
        
        event_ref = db.collection('events').document(event_id)
        event_doc = event_ref.get()
        
        if not event_doc.exists:
            flash("Event not found.", "danger")
            return redirect('/coordinator/dashboard')
            
        event_data = event_doc.to_dict()
        current_round = event_data.get('active_round', 1)
        next_round = current_round + 1
        
        regs_ref = db.collection('registrations').where('event_id', '==', event_id).stream()
        
        promoted_count = 0
        eliminated_count = 0
        
        for reg in regs_ref:
            reg_data = reg.to_dict()
            
            # Skip if they are already eliminated in a previous round
            if reg_data.get('is_eliminated', False):
                continue
            
            scores = reg_data.get('scores', {})
            total_score = sum([int(s['total']) for s in scores.values()]) if scores else 0
            
            reg_doc_ref = db.collection('registrations').document(reg.id)
            
            if total_score >= cutoff_score:
                # 🎉 PROMOTE! Reset their room and score for the next round
                reg_doc_ref.update({
                    'current_round': next_round,
                    'scores': firestore.DELETE_FIELD, 
                    'assigned_room': None,            
                    'assigned_judge_email': None,
                    'assigned_judge_name': None,
                    'evaluated_by': firestore.DELETE_FIELD
                })
                promoted_count += 1
            else:
                # ❌ ELIMINATE!
                reg_doc_ref.update({'is_eliminated': True})
                eliminated_count += 1
                
        event_ref.update({'active_round': next_round})
        flash(f"🏆 Round {next_round} Started! {promoted_count} teams advanced, {eliminated_count} eliminated.", "success")
        
    except Exception as e:
        flash(f"Error processing eliminations: {e}", "danger")
        
    if session.get('role') in ['SuperAdmin', 'Super Admin']:
        return redirect('/admin/dashboard')
    return redirect('/coordinator/dashboard')

# --- 🚀 SEND AUTOMATED REMINDERS (ONLY TO ACTIVE TEAMS) ---
@coord_bp.route('/trigger_reminders/<event_id>')
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def trigger_reminders(event_id):
    try:
        event_doc = db.collection('events').document(event_id).get().to_dict()
        regs_ref = db.collection('registrations').where('event_id', '==', event_id).stream()
        
        count = 0
        for r in regs_ref:
            d = r.to_dict()
            
            # 🚀 Skip eliminated teams!
            if d.get('is_eliminated', False):
                continue
                
            if d.get('assigned_room'):
                round_num = event_doc.get('active_round', 1)
                msg_body = f"URGENT EVENT ALERT - ROUND {round_num}:\n\nHello {d.get('lead_name')},\n\nYou are active in Round {round_num} of '{event_doc['title']}'!\n\nPlease report to Venue/Room: {d.get('assigned_room')}.\nYour assigned judge will be: {d.get('assigned_judge_name')}.\n\nBest of luck!"
                send_broadcast_email([d.get('lead_email')], f"Round {round_num} Details: {event_doc['title']}", msg_body, event_doc['title'])
                count += 1
                
        flash(f"📢 Successfully sent Round {event_doc.get('active_round', 1)} assignments to {count} active teams!", "success")
    except Exception as e:
        flash(f"Error sending reminders: {e}", "danger")
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
            # Only rank teams that survived until the final round!
            if d.get('is_eliminated', False):
                continue
                
            scores = d.get('scores', {})
            if scores:
                avg = round(sum([int(s['total']) for s in scores.values()]) / len(scores), 2)
                leaderboard.append({'team_name': d.get('team_name'), 'lead_name': d.get('lead_name'), 'score': avg})
        
        leaderboard.sort(key=lambda x: x['score'], reverse=True)
        event_ref.update({'status': 'completed', 'winners': leaderboard[:3], 'completed_at': datetime.datetime.now()})
        flash(f"🏆 Final Results Published!", "success")
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

@coord_bp.route('/export_registrations/<event_id>')
@login_required
@role_required(['ClubSPOC', 'Coordinator', 'SuperAdmin'])
def export_registrations(event_id):
    try:
        event_doc = db.collection('events').document(event_id).get().to_dict()
        regs = db.collection('registrations').where('event_id', '==', event_id).stream()

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Ticket ID', 'Lead Name', 'Email', 'USN', 'Phone', 'Team Name', 'Members Count', 'Assigned Room', 'Assigned Judge', 'Current Round', 'Status', 'Attendance', 'Reg Date'])

        for r in regs:
            d = r.to_dict()
            status_text = 'Eliminated' if d.get('is_eliminated', False) else 'Active'
            writer.writerow([
                d.get('reg_id', 'N/A'),
                d.get('lead_name', 'N/A'),
                d.get('lead_email', 'N/A'),
                d.get('lead_usn', 'N/A'),
                d.get('phone', 'N/A'),
                d.get('team_name', 'Individual'),
                d.get('member_count', 1),
                d.get('assigned_room', 'Unassigned'),
                d.get('assigned_judge_email', 'Unassigned'),
                d.get('current_round', 1),
                status_text,
                d.get('attendance', 'Pending'),
                d.get('registered_at', 'N/A')
            ])

        response = Response(output.getvalue(), mimetype='text/csv')
        clean_title = event_doc.get('title', 'Event').replace(" ", "_")
        response.headers["Content-Disposition"] = f"attachment; filename={clean_title}_Registrations.csv"
        return response

    except Exception as e:
        flash(f"Error exporting data: {e}", "danger")
        return redirect('/coordinator/dashboard')

# ========================================================
# PART 2: EVENT COORDINATOR (GRANULAR SCANNER)
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

@coord_bp.route('/get_ticket/<reg_id>')
@login_required
def get_ticket(reg_id):
    reg = db.collection('registrations').document(reg_id).get()
    if not reg.exists: return jsonify({'status': 'error', 'message': 'INVALID TICKET'})
    return jsonify({'status': 'success', 'data': reg.to_dict()})

@coord_bp.route('/mark_attendance_granular', methods=['POST'])
@login_required
def mark_attendance_granular():
    try:
        data = request.json
        reg_id = data.get('reg_id')
        present_usns = data.get('present_usns', []) 
        
        reg_ref = db.collection('registrations').document(reg_id)
        reg_data = reg_ref.get().to_dict()
        
        if reg_data.get('payment_status') == 'Pending': 
            return jsonify({'status': 'error', 'message': '💰 PAYMENT PENDING!'})
        
        members = reg_data.get('members', [])
        for m in members:
            if m.get('usn') in present_usns:
                m['attendance'] = 'Present'
            else:
                m['attendance'] = 'Absent'
                
        reg_ref.update({
            'members': members,
            'attendance': 'Present' if len(present_usns) > 0 else 'Absent',
            'checkin_time': datetime.datetime.now().strftime("%H:%M:%S")
        })
        
        return jsonify({'status': 'success', 'message': f"✅ ATTENDANCE LOGGED!\n{len(present_usns)} Members Present."})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

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
            user_ref.set({
                'email': email, 'name': name, 'phone': request.form.get('phone'), 'usn': request.form.get('usn').upper(), 
                'role': 'Student', 'password': generate_password_hash('welcome123'), 'created_at': datetime.datetime.now().strftime("%Y-%m-%d"),
                'needs_password_reset': True
            })
        
        reg_id = f"REG-{int(datetime.datetime.now().timestamp())}"
        event_doc = db.collection('events').document(event_id).get().to_dict()
        
        db.collection('registrations').document(reg_id).set({
            'reg_id': reg_id, 'event_id': event_id, 'event_title': event_doc.get('title'),
            'lead_name': name, 'lead_email': email, 'lead_usn': request.form.get('usn').upper(), 'team_name': 'Walk-in',
            'members': [], 'status': 'Confirmed', 'payment_status': 'Paid', 'amount_paid': event_doc.get('entry_fee', 0), 'payment_mode': request.form.get('payment_mode'),
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'attendance': 'Present', 'checkin_time': datetime.datetime.now().strftime("%H:%M:%S"),
            'is_eliminated': False, 'current_round': event_doc.get('active_round', 1)
        })
        send_ticket_email(email, name, event_doc.get('title'), reg_id)
        flash(f"✅ Walk-in Registered! Ticket sent.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect('/coordinator/on_spot')

# ========================================================
# PART 3: AUTO-CERTIFICATE GENERATOR
# ========================================================
@coord_bp.route('/certificate/<reg_id>/<usn>')
def generate_certificate(reg_id, usn):
    reg_doc = db.collection('registrations').document(reg_id).get()
    if not reg_doc.exists: return "Registration not found", 404
    
    data = reg_doc.to_dict()
    student_name = ""
    
    members = data.get('members', [])
    
    if data.get('lead_usn') == usn:
        if data.get('attendance') == 'Present':
            student_name = data.get('lead_name')
        else:
            return "<h3>Certificate Denied: You were marked Absent at the venue.</h3>", 403
    else:
        for m in members:
            if m.get('usn') == usn:
                if m.get('attendance') == 'Present':
                    student_name = m.get('name')
                else:
                    return "<h3>Certificate Denied: Student was marked Absent at the venue.</h3>", 403

    if not student_name:
        return "Student not found in this team.", 404
        
    event_doc = db.collection('events').document(data['event_id']).get().to_dict()
    
    return render_template('participant/certificate.html', student_name=student_name, event=event_doc)