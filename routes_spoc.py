from flask import Blueprint, render_template, request, redirect, session, flash, Response, url_for
from models import db, FirebaseWrapper
from firebase_admin import firestore
import datetime
import csv
import io

spoc_bp = Blueprint('spoc', __name__, url_prefix='/spoc')

# --- 1. SPOC DASHBOARD ---
@spoc_bp.route('/dashboard')
def dashboard():
    # Security Check
    if session.get('role') != 'ClubSPOC': 
        flash("Access Denied.", "warning")
        return redirect('/login')
    
    spoc_id = session.get('user_id')
    
    # Fetch Events created by this SPOC
    query = db.collection('events').where('spoc_id', '==', spoc_id).stream()
    
    events = []
    total_regs = 0

    for doc in query:
        data = doc.to_dict()
        # Count registrations for this event
        reg_count = len(list(db.collection('registrations').where('event_id', '==', doc.id).stream()))
        total_regs += reg_count
        
        # Add to event object
        data['registration_count'] = reg_count 
        events.append(FirebaseWrapper(doc.id, data))

    # Helper to get Coordinator Names
    def get_coord_name(email):
        if not email: return "Not Assigned"
        doc = db.collection('users').document(email).get()
        return doc.to_dict().get('name', 'Unknown') if doc.exists else "Not Assigned"

    return render_template(
        'spoc/dashboard.html', 
        events=events, 
        stats={'total_events': len(events), 'total_regs': total_regs},
        get_coord_name=get_coord_name,
        category=session.get('category', 'General')
    )

# --- 2. CREATE EVENT (MOBILE COMPACT FORM) ---
@spoc_bp.route('/create_event', methods=['GET', 'POST'])
def create_event():
    # 1. Security Check
    if session.get('role') != 'ClubSPOC': 
        return redirect('/login')

    # 2. GET: Show the New Mobile-Friendly Page
    if request.method == 'GET':
        return render_template('spoc/create_event.html')

    # 3. POST: Save Data
    try:
        # Determine Team Logic
        participation_type = request.form.get('participation_type')
        is_team = True if participation_type == 'Team' else False
        
        event_data = {
            # Basic Info
            'title': request.form.get('title'),
            'category': session.get('category', 'Tech'),
            'date': request.form.get('date'),
            'time': request.form.get('time'),
            'venue': request.form.get('venue'),
            'description': request.form.get('description'),
            
            # Rules
            'reg_deadline': request.form.get('reg_deadline'),
            'max_participants': int(request.form.get('max_limit') or 0),
            'is_team_event': is_team,
            'team_min': int(request.form.get('team_min') or 1),
            'team_max': int(request.form.get('team_max') or 1),
            
            # Resources
            'prizes': request.form.get('prizes'),
            'group_link': request.form.get('group_link'),
            'problem_statement_link': request.form.get('problem_link'),
            
            # System Metadata
            'spoc_id': session['user_id'],
            'created_by': session['user_id'],
            'status': 'active',
            'is_published': True,
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d"),
            
            # Empty Placeholders
            'coord_student_id': None,
            'coord_staff_id': None,
            'judge_ids': []
        }

        db.collection('events').add(event_data)
        flash("Event Published Successfully!", "success")
        return redirect('/spoc/dashboard')
        
    except Exception as e:
        print(f"Error: {e}")
        flash(f"Error creating event: {str(e)}", "danger")
        return redirect('/spoc/create_event')

# --- 3. ASSIGN COORDINATORS ---
@spoc_bp.route('/assign_coordinators', methods=['POST'])
def assign_coordinators():
    try:
        event_id = request.form.get('event_id')
        
        # Helper to create user instantly if they don't exist
        def ensure_user(name, email, role):
            if not email: return None
            user_ref = db.collection('users').document(email)
            if not user_ref.get().exists:
                user_ref.set({
                    'name': name,
                    'email': email,
                    'role': 'Coordinator',
                    'role_type': role,
                    'password': 'password123',
                    'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
                })
            return email

        stu = ensure_user(request.form.get('stu_name'), request.form.get('stu_email'), 'Student')
        staff = ensure_user(request.form.get('staff_name'), request.form.get('staff_email'), 'Staff')

        db.collection('events').document(event_id).update({
            'coord_student_id': stu,
            'coord_staff_id': staff
        })
        flash("Coordinators assigned.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
        
    return redirect('/spoc/dashboard')

# --- 4. EXPORT CSV (ENHANCED) ---
@spoc_bp.route('/export_csv/<event_id>')
def export_csv(event_id):
    try:
        event_doc = db.collection('events').document(event_id).get()
        title = event_doc.to_dict().get('title', 'Event')
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Team/Name', 'Lead Email', 'Members', 'Status', 'Attendance', 'Score', 'Date'])
        
        regs = db.collection('registrations').where('event_id', '==', event_id).stream()
        
        for doc in regs:
            r = doc.to_dict()
            member_count = len(r.get('members', []))
            
            # Get max score from any judge
            scores = r.get('scores', {})
            final_score = 0
            if scores:
                final_score = max([v['total'] for v in scores.values()])

            writer.writerow([
                r.get('team_name', 'Individual'),
                r.get('lead_email'),
                f"{member_count} Members",
                r.get('status', 'Pending'),
                r.get('attendance', 'Pending'),
                final_score,
                r.get('registered_at')
            ])
            
        return Response(
            output.getvalue(), 
            mimetype="text/csv", 
            headers={"Content-disposition": f"attachment; filename={title}_report.csv"}
        )
    except:
        return redirect('/spoc/dashboard')