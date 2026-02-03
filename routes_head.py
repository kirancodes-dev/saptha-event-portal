from flask import Blueprint, render_template, request, redirect, session, flash
from models import db, FirebaseWrapper

head_bp = Blueprint('head', __name__, url_prefix='/event_head')

@head_bp.route('/dashboard')
def dashboard():
    # 1. Security Check
    if session.get('role') != 'Coordinator':
        flash("Access Denied: Coordinators only.", "warning")
        return redirect('/login')

    user_email = session.get('user_id')

    # 2. Find the Event assigned to this Coordinator
    # We check if their email matches either the Student OR Staff coordinator field
    events_ref = db.collection('events')
    
    # Query for Student Coordinator
    query_stu = events_ref.where('coord_student_id', '==', user_email).stream()
    # Query for Staff Coordinator
    query_staff = events_ref.where('coord_staff_id', '==', user_email).stream()

    # Combine results (Usually a coord has only 1 active event, but we handle lists)
    my_events = []
    event_ids = []

    for doc in query_stu:
        data = doc.to_dict()
        my_events.append(FirebaseWrapper(doc.id, data))
        event_ids.append(doc.id)
        
    for doc in query_staff:
        # Avoid duplicates if someone is somehow both (unlikely)
        if doc.id not in event_ids:
            data = doc.to_dict()
            my_events.append(FirebaseWrapper(doc.id, data))

    # 3. Fetch Registrations for these events
    # We create a dictionary where Key = EventID, Value = List of Teams
    registrations_map = {}
    
    for event in my_events:
        regs = db.collection('registrations').where('event_id', '==', event.id).stream()
        team_list = []
        for r_doc in regs:
            r_data = r_doc.to_dict()
            r_data['id'] = r_doc.id # Capture doc ID for updates
            team_list.append(r_data)
        registrations_map[event.id] = team_list

    return render_template(
        'head/dashboard.html', 
        events=my_events, 
        registrations=registrations_map
    )

@head_bp.route('/mark_attendance/<reg_id>/<status>')
def mark_attendance(reg_id, status):
    # status should be 'Present' or 'Absent'
    if session.get('role') != 'Coordinator': return redirect('/login')
    
    try:
        db.collection('registrations').document(reg_id).update({
            'attendance': status
        })
        flash(f"Team marked as {status}", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
        
    return redirect('/event_head/dashboard')