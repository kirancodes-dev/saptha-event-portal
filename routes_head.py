from flask import Blueprint, render_template, session, redirect, request, flash, Response
from models import db
from datetime import datetime
import csv
import io

head_bp = Blueprint('head_bp', __name__, url_prefix='/event_head')

class FirebaseWrapper:
    def __init__(self, id, data):
        self.id = id
        self._data = data
    def __getattr__(self, name):
        return self._data.get(name)

@head_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'Coordinator': return redirect('/login')
    
    coord_email = session['user_id']
    
    # FIND EVENT
    # We query events where coord_student_id OR coord_staff_id matches
    # Firestore doesn't support logical OR directly in one query efficiently.
    # We check student column first, then staff.
    
    query = db.collection('events').where('coord_student_id', '==', coord_email).get()
    if not query:
        query = db.collection('events').where('coord_staff_id', '==', coord_email).get()
    
    if not query:
        return render_template('dashboard_head.html', event=None, analytics=None, teams=[])
    
    event_doc = query[0]
    session['event_id'] = event_doc.id
    event_obj = FirebaseWrapper(event_doc.id, event_doc.to_dict())
    
    # FETCH TEAMS
    teams_query = db.collection('teams').where('event_id', '==', event_doc.id).stream()
    teams = [FirebaseWrapper(t.id, t.to_dict()) for t in teams_query]
    
    # ANALYTICS
    analytics = {
        'total_teams': len(teams),
        'pending': len([t for t in teams if t.approval_status == 'Pending']),
        'approved': len([t for t in teams if t.approval_status == 'Approved']),
        'present': len([t for t in teams if t.attendance_status == 'Present']),
        'submissions': len([t for t in teams if t.project_link])
    }

    return render_template('dashboard_head.html', event=event_obj, analytics=analytics, teams=teams)

@head_bp.route('/manage_registration/<team_id>/<action>', methods=['POST'])
def manage_registration(team_id, action):
    status = 'Approved' if action == 'approve' else 'Rejected'
    db.collection('teams').document(team_id).update({'approval_status': status})
    flash(f"Team {status}", "info")
    return redirect('/event_head/dashboard')

@head_bp.route('/mark_attendance/<team_id>', methods=['POST'])
def mark_attendance(team_id):
    doc_ref = db.collection('teams').document(team_id)
    doc = doc_ref.get().to_dict()
    new_status = 'Absent' if doc.get('attendance_status') == 'Present' else 'Present'
    doc_ref.update({'attendance_status': new_status})
    return redirect('/event_head/dashboard')

@head_bp.route('/add_announcement', methods=['POST'])
def add_announcement():
    msg = request.form.get('message')
    if msg:
        db.collection('announcements').add({
            'message': msg,
            'event_id': session['event_id'],
            'timestamp': datetime.now(),
            'type': 'Info'
        })
        flash("Broadcast sent", "success")
    return redirect('/event_head/dashboard')

@head_bp.route('/download_report')
def download_report():
    event_id = session.get('event_id')
    event_name = db.collection('events').document(event_id).get().to_dict().get('name')
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Team Code', 'Team Name', 'Members', 'Approval Status', 'Attendance', 'Submission'])
    
    teams = db.collection('teams').where('event_id', '==', event_id).stream()
    for t in teams:
        d = t.to_dict()
        # d['members'] is a list of dicts [{'name':'..', 'email':'..'}]
        members_str = ", ".join([m['name'] for m in d.get('members', [])])
        writer.writerow([d.get('code'), d.get('name'), members_str, d.get('approval_status'), d.get('attendance_status'), d.get('project_link')])
        
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename={event_name}_Report.csv"})

@head_bp.route('/add_problem', methods=['POST'])
def add_problem():
    import random
    db.collection('problem_statements').add({
        'uid': f"PS-{random.randint(100,999)}",
        'title': request.form.get('ps_title'),
        'description': request.form.get('ps_desc'),
        'event_id': session['event_id']
    })
    return redirect('/event_head/dashboard')