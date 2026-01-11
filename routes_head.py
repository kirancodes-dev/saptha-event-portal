from flask import Blueprint, render_template, session, redirect, request, flash, Response
from models import db, Event, ProblemStatement, Coordinator, Team, Announcement, Fixture, Performance
import csv
import io
from datetime import datetime

head_bp = Blueprint('head_bp', __name__, url_prefix='/event_head')

@head_bp.route('/dashboard')
def dashboard():
    # 1. Security Check
    if session.get('role') != 'Coordinator': 
        return redirect('/login')
    
    # 2. Identify Coordinator & Event
    coord_id = session.get('user_id')
    
    # SEARCH LOGIC: Find event where this user ID matches either student or staff column
    event = Event.query.filter(
        (Event.coord_student_id == coord_id) | 
        (Event.coord_staff_id == coord_id)
    ).first()
    
    if not event:
        # Debugging: Show ID if no event found
        return render_template('dashboard_head.html', event=None, analytics=None, user_id=coord_id)
    
    # Save event ID to session for easier updates later
    session['event_id'] = event.id
    
    # 3. Calculate Operational Analytics
    teams = event.teams_rel
    analytics = {
        'total_teams': len(teams),
        'pending': len([t for t in teams if t.approval_status == 'Pending']),
        'approved': len([t for t in teams if t.approval_status == 'Approved']),
        'present': len([t for t in teams if t.attendance_status == 'Present']),
        'submissions': len([t for t in teams if t.project_link])
    }

    return render_template('dashboard_head.html', 
                           event=event, 
                           analytics=analytics,
                           teams=teams)

# --- 1. REGISTRATION MANAGEMENT (Approve/Reject) ---
@head_bp.route('/manage_registration/<int:team_id>/<string:action>', methods=['POST'])
def manage_registration(team_id, action):
    if session.get('role') != 'Coordinator': return redirect('/login')
    
    team = Team.query.get(team_id)
    if team:
        if action == 'approve':
            team.approval_status = 'Approved'
            flash(f"Team {team.name} Approved!", "success")
        elif action == 'reject':
            team.approval_status = 'Rejected'
            flash(f"Team {team.name} Rejected.", "danger")
        db.session.commit()
    return redirect('/event_head/dashboard')

# --- 2. EVENT DAY: ATTENDANCE ---
@head_bp.route('/mark_attendance/<int:team_id>', methods=['POST'])
def mark_attendance(team_id):
    if session.get('role') != 'Coordinator': return redirect('/login')
    
    team = Team.query.get(team_id)
    if team:
        # Toggle Attendance
        if team.attendance_status == 'Present':
            team.attendance_status = 'Absent'
        else:
            team.attendance_status = 'Present'
        db.session.commit()
        
    return redirect('/event_head/dashboard')

# --- 3. COMMUNICATION ---
@head_bp.route('/add_announcement', methods=['POST'])
def add_announcement():
    if session.get('role') != 'Coordinator': return redirect('/login')
    
    msg = request.form.get('message')
    if msg:
        new_ann = Announcement(message=msg, event_id=session['event_id'])
        db.session.add(new_ann)
        db.session.commit()
        flash("Announcement broadcasted!", "success")
    return redirect('/event_head/dashboard')

# --- 4. REPORTING ---
@head_bp.route('/download_report')
def download_report():
    if session.get('role') != 'Coordinator': return redirect('/login')
    
    event = Event.query.get(session['event_id'])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Team Code', 'Team Name', 'Members', 'Approval Status', 'Attendance', 'Submission Link'])
    
    for team in event.teams_rel:
        members_txt = ", ".join([m.name for m in team.members])
        writer.writerow([team.code, team.name, members_txt, team.approval_status, team.attendance_status, team.project_link])
        
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename={event.name}_Report.csv"})

# --- 5. EVENT MANAGEMENT (Tech/Sports) ---
@head_bp.route('/add_problem', methods=['POST'])
def add_problem():
    import random
    title = request.form.get('ps_title')
    desc = request.form.get('ps_desc')
    uid = f"PS-{random.randint(100, 999)}"
    new_ps = ProblemStatement(uid=uid, title=title, description=desc, event_id=session['event_id'])
    db.session.add(new_ps)
    db.session.commit()
    return redirect('/event_head/dashboard')

@head_bp.route('/delete_problem/<int:id>', methods=['POST'])
def delete_problem(id):
    ProblemStatement.query.filter_by(id=id).delete()
    db.session.commit()
    return redirect('/event_head/dashboard')