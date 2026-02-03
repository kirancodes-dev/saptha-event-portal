from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from models import db, FirebaseWrapper
from firebase_admin import firestore
import datetime

participant_bp = Blueprint('participant', __name__, url_prefix='/participant')

# --- 1. STUDENT DASHBOARD ---
@participant_bp.route('/dashboard')
def dashboard():
    if session.get('role') not in ['Student', 'Participant']:
        return redirect('/login')

    user_email = session.get('user_id')
    
    # Fetch registrations where user is the Team Lead
    # (To show member registrations, we'd need to store a separate array of emails in the doc)
    query = db.collection('registrations').where('lead_email', '==', user_email).stream()
    
    my_regs = []
    for doc in query:
        data = doc.to_dict()
        data['id'] = doc.id
        my_regs.append(data)
        
    return render_template('participant/dashboard.html', registrations=my_regs)

# --- 2. REGISTER EVENT (Existing Logic) ---
@participant_bp.route('/register_event/<event_id>', methods=['GET', 'POST'])
def register_event(event_id):
    if session.get('role') not in ['Student', 'Participant']:
        flash("Please login to register.", "warning")
        return redirect('/login')

    user_email = session.get('user_id')
    
    # Get Event
    event_ref = db.collection('events').document(event_id)
    doc = event_ref.get()
    if not doc.exists: return redirect('/')
    event_data = FirebaseWrapper(event_id, doc.to_dict())

    if request.method == 'GET':
        user_info = {'name': session.get('name'), 'email': user_email}
        return render_template('participant/event_register.html', event=event_data, event_id=event_id, user=user_info)

    try:
        # Check Duplicate
        existing = db.collection('registrations').where('event_id', '==', event_id).where('lead_email', '==', user_email).stream()
        if any(existing):
            flash("Already registered!", "info")
            return redirect('/participant/dashboard')

        # Collect Data
        lead_details = {
            'name': session.get('name'),
            'email': user_email,
            'usn': request.form.get('lead_usn'),
            'phone': request.form.get('lead_phone'),
            'role': 'Team Lead'
        }
        
        members = [lead_details]
        
        # Add Members
        if getattr(event_data, 'is_team_event', False):
            for i in range(1, 4):
                m_name = request.form.get(f'member_{i}_name')
                m_usn = request.form.get(f'member_{i}_usn')
                if m_name and m_usn:
                    members.append({'name': m_name, 'usn': m_usn, 'role': 'Member'})

        reg_data = {
            'event_id': event_id,
            'event_title': event_data.title,
            'event_date': event_data.date, # Store date for easy display
            'team_name': request.form.get('team_name', 'Individual'),
            'problem_statement': request.form.get('problem_statement', 'N/A'),
            'lead_email': user_email,
            'members': members,
            'status': 'Approved', # Auto-approve for now
            'attendance': 'Pending',
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d")
        }
        
        db.collection('registrations').add(reg_data)
        flash("Registration Successful!", "success")
        return redirect('/participant/dashboard')

    except Exception as e:
        flash(f"Error: {e}", "danger")
        return redirect(request.url)