from flask import Blueprint, render_template, session, redirect, request, flash
from models import db
from datetime import datetime

participant_bp = Blueprint('participant_bp', __name__, url_prefix='/participant')

# Wrapper for Dot Notation compatibility
class FirebaseWrapper:
    def __init__(self, id, data):
        self.id = id
        self._data = data
    def __getattr__(self, name):
        val = self._data.get(name)
        return val if val is not None else ''

@participant_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'Participant': return redirect('/login')
    
    user_email = session.get('user_id') # In Firebase, we use Email as ID
    user_doc = db.collection('users').document(user_email).get()
    
    if not user_doc.exists:
        session.clear()
        return redirect('/login')
    
    participant = FirebaseWrapper(user_email, user_doc.to_dict())

    # --- 1. BUILD SMART EVENT DATA ---
    my_events_data = []
    
    # Fetch teams where this user is a member
    # Note: 'members' in team doc should be list of emails or objects containing email
    # Assuming 'members' is a list of objects: [{'email': '...', 'name': '...'}]
    # We query strictly: Does the 'member_emails' array contain this email?
    teams_query = db.collection('teams').where('member_emails', 'array_contains', user_email).stream()
    
    registered_event_ids = []

    for t_doc in teams_query:
        team_data = t_doc.to_dict()
        event_id = team_data.get('event_id')
        registered_event_ids.append(event_id)
        
        # Fetch Event Data
        event_doc = db.collection('events').document(event_id).get()
        if event_doc.exists:
            event_data = event_doc.to_dict()
            event_obj = FirebaseWrapper(event_id, event_data)
            team_obj = FirebaseWrapper(t_doc.id, team_data)
            
            # Status Logic
            status = "Registered"
            status_class = "primary"
            
            # Date Comparison (Assuming string YYYY-MM-DD stored)
            today_str = datetime.now().strftime('%Y-%m-%d')
            evt_date = event_data.get('date', '3000-01-01')
            
            if team_data.get('project_link'):
                status = "Submitted"
                status_class = "success"
            elif evt_date < today_str:
                status = "Completed"
                status_class = "dark"
            
            my_events_data.append({
                'event': event_obj,
                'team': team_obj,
                'status': status,
                'status_class': status_class,
                'has_submission': bool(team_data.get('project_link'))
            })

    # --- 2. NOTIFICATIONS ---
    notifications = []
    ann_query = db.collection('announcements').order_by('timestamp', direction=db.Query.DESCENDING).limit(5).stream()
    for doc in ann_query:
        ann = doc.to_dict()
        if ann.get('event_id') in registered_event_ids:
            notifications.append(FirebaseWrapper(doc.id, ann))

    # --- 3. UPCOMING EVENTS ---
    upcoming_events = []
    all_events = db.collection('events').where('is_published', '==', True).stream()
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    for doc in all_events:
        if doc.id not in registered_event_ids:
            data = doc.to_dict()
            if data.get('date') > today_str:
                upcoming_events.append(FirebaseWrapper(doc.id, data))

    return render_template('dashboard_participant.html', 
                           participant=participant, 
                           my_events_data=my_events_data, 
                           notifications=notifications,
                           upcoming_events=upcoming_events)

@participant_bp.route('/register_event', methods=['POST'])
def register_event():
    try:
        user_email = session.get('user_id')
        event_id = request.form.get('event_id')
        team_name = request.form.get('team_name')

        # Check existing registration
        existing = db.collection('teams').where('event_id', '==', event_id).where('member_emails', 'array_contains', user_email).get()
        if len(existing) > 0:
            flash("Already registered!", "warning")
            return redirect('/participant/dashboard')

        # Prepare Members List
        members = []
        member_emails = []
        
        # Add Self
        me = db.collection('users').document(user_email).get().to_dict()
        members.append({'name': me['name'], 'email': user_email})
        member_emails.append(user_email)
        
        # Add Teammates
        others = request.form.getlist('member_emails')
        for email in others:
            if email and email.strip():
                clean_email = email.strip()
                user_doc = db.collection('users').document(clean_email).get()
                if user_doc.exists:
                    members.append({'name': user_doc.to_dict()['name'], 'email': clean_email})
                    member_emails.append(clean_email)

        # Create Team
        team_code = f"T-{str(hash(team_name))[-6:]}"
        
        team_data = {
            'name': team_name,
            'code': team_code,
            'event_id': event_id,
            'members': members,
            'member_emails': member_emails, # Helper field for queries
            'approval_status': 'Pending',
            'attendance_status': 'Absent',
            'project_link': ''
        }
        
        db.collection('teams').add(team_data)
        flash("Registered successfully!", "success")

    except Exception as e:
        flash(f"Error: {e}", "danger")

    return redirect('/participant/dashboard')

@participant_bp.route('/submit_project', methods=['POST'])
def submit_project():
    team_id = request.form.get('team_id')
    link = request.form.get('project_link')
    
    db.collection('teams').document(team_id).update({'project_link': link})
    flash("Project submitted!", "success")
    return redirect('/participant/dashboard')