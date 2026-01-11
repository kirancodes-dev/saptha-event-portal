from flask import Blueprint, render_template, request, redirect, session, flash, Response
from models import db # Importing Firestore Client
from datetime import datetime
import csv
import io

spoc_bp = Blueprint('spoc_bp', __name__, url_prefix='/spoc')

# --- HELPER: WRAPPER FOR DOT NOTATION ---
class FirebaseWrapper:
    def __init__(self, id, data):
        self.id = id
        self._data = data
    def __getattr__(self, name):
        return self._data.get(name)

@spoc_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'ClubSPOC': return redirect('/login')
    
    spoc_id = session['user_id']
    events_ref = db.collection('events')
    
    # Query: Get events created by this SPOC
    query = events_ref.where('spoc_id', '==', spoc_id).stream()
    
    events = []
    total_regs = 0

    for doc in query:
        data = doc.to_dict()
        # Fetch team count for this event
        teams_count = len(list(db.collection('teams').where('event_id', '==', doc.id).stream()))
        total_regs += teams_count
        
        # Add team_count to data for template use
        data['teams_rel'] = range(teams_count) # Hack to make len() work in Jinja if using len(event.teams_rel)
        events.append(FirebaseWrapper(doc.id, data))

    # Helper to get Coord Name (Fetch from Users collection)
    def get_coord_name(email):
        if not email: return "Not Assigned"
        doc = db.collection('users').document(email).get()
        return doc.to_dict().get('name', 'Unknown') if doc.exists else "Not Assigned"

    return render_template('dashboard_spoc_tech.html', 
                           events=events, 
                           total_regs=total_regs,
                           get_coord_name=get_coord_name,
                           category=session.get('category', 'Tech'))

@spoc_bp.route('/create_event', methods=['POST'])
def create_event():
    if session.get('role') != 'ClubSPOC': return redirect('/login')
    
    try:
        # Form Data
        formats = request.form.getlist('sub_formats')
        submission_str = ", ".join(formats) if formats else "Any"

        event_data = {
            'name': request.form.get('name'),
            'category': 'Tech',
            'date': request.form.get('date'), # Store as string or convert to timestamp
            'reg_deadline': request.form.get('reg_deadline'),
            'spoc_id': session['user_id'],
            'event_mode': request.form.get('event_mode'),
            'venue': request.form.get('venue'),
            'time_slot': request.form.get('time_slot'),
            'event_type': request.form.get('event_type'),
            'max_participants': int(request.form.get('max_participants') or 100),
            'team_min': int(request.form.get('team_min') or 1),
            'team_max': int(request.form.get('team_max') or 1),
            'image_url': request.form.get('image_url'),
            'resource_link': request.form.get('resource_link'),
            'overview': request.form.get('overview'),
            'rules': request.form.get('rules'),
            'prizes': request.form.get('prizes'),
            'is_published': True,
            # Tech Specifics
            'tech_problem_type': request.form.get('tech_problem_type'),
            'problem_stmt_link': request.form.get('problem_stmt_link'),
            'tech_domain': request.form.get('tech_domain'),
            'tech_stack_allowed': request.form.get('tech_stack_allowed'),
            'submission_format': submission_str,
            'rounds_config': request.form.get('rounds_config'),
            # Eval
            'eval_innovation': int(request.form.get('eval_innovation') or 0),
            'eval_tech_complexity': int(request.form.get('eval_tech_complexity') or 0),
            'eval_feasibility': int(request.form.get('eval_feasibility') or 0),
            'eval_presentation': int(request.form.get('eval_presentation') or 0),
            'eval_impact': int(request.form.get('eval_impact') or 0),
            # Init empty fields
            'coord_student_id': None,
            'coord_staff_id': None,
            'judge_ids': [] 
        }

        db.collection('events').add(event_data)
        flash("Tech Event Created Successfully!", "success")
        
    except Exception as e:
        flash(f"Error creating event: {str(e)}", "danger")

    return redirect('/spoc/dashboard')

@spoc_bp.route('/toggle_publish/<event_id>', methods=['POST'])
def toggle_publish(event_id):
    ref = db.collection('events').document(event_id)
    doc = ref.get()
    if doc.exists:
        curr_status = doc.to_dict().get('is_published', False)
        ref.update({'is_published': not curr_status})
        flash("Event status changed.", "success")
    return redirect('/spoc/dashboard')

@spoc_bp.route('/assign_coordinators', methods=['POST'])
def assign_coordinators():
    try:
        event_id = request.form.get('event_id')
        
        # Helper to create user if not exists
        def ensure_user(name, email, role):
            if not email: return None
            user_ref = db.collection('users').document(email)
            if not user_ref.get().exists:
                user_ref.set({
                    'name': name,
                    'email': email,
                    'role': 'Coordinator',
                    'role_type': role,
                    'password': 'password123'
                })
            return email # ID is email

        stu_email = ensure_user(request.form.get('stu_name'), request.form.get('stu_email'), 'Student')
        staff_email = ensure_user(request.form.get('staff_name'), request.form.get('staff_email'), 'Staff')

        # Update Event
        db.collection('events').document(event_id).update({
            'coord_student_id': stu_email,
            'coord_staff_id': staff_email
        })
        flash("Coordinators assigned successfully!", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
        
    return redirect('/spoc/dashboard')

@spoc_bp.route('/assign_judge', methods=['POST'])
def assign_judge():
    try:
        event_id = request.form.get('event_id')
        email = request.form.get('email')
        name = request.form.get('name')
        expertise = request.form.get('expertise')

        # 1. Ensure Judge Exists
        user_ref = db.collection('users').document(email)
        user_ref.set({
            'name': name,
            'email': email,
            'role': 'Judge',
            'expertise': expertise,
            'password': 'password123'
        }, merge=True)

        # 2. Add Judge ID to Event
        event_ref = db.collection('events').document(event_id)
        # Firestore array union to avoid duplicates
        event_ref.update({
            'judge_ids': firestore.ArrayUnion([email])
        })
        
        flash(f"Judge {name} assigned.", "success")
    except Exception as e:
        from firebase_admin import firestore # Late import for ArrayUnion if needed
        # Retry with simpler list append if ArrayUnion fails imports
        event_ref = db.collection('events').document(event_id)
        doc = event_ref.get().to_dict()
        judges = doc.get('judge_ids', [])
        if email not in judges:
            judges.append(email)
            event_ref.update({'judge_ids': judges})
            
    return redirect('/spoc/dashboard')

@spoc_bp.route('/export_csv/<event_id>')
def export_csv(event_id):
    event_doc = db.collection('events').document(event_id).get()
    event_name = event_doc.to_dict().get('name', 'Event')

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Team Code', 'Team Name', 'Member Name', 'Member Email'])
    
    # Fetch Teams
    teams = db.collection('teams').where('event_id', '==', event_id).stream()
    
    for t_doc in teams:
        team = t_doc.to_dict()
        for member in team.get('members', []): # members is a list of dicts
            writer.writerow([team.get('code'), team.get('name'), member.get('name'), member.get('email')])
            
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename={event_name}_registrations.csv"})