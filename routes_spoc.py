from flask import Blueprint, render_template, request, redirect, session, flash, Response
from models import db, Event, Coordinator, Judge, Team
from datetime import datetime
import csv
import io

spoc_bp = Blueprint('spoc_bp', __name__, url_prefix='/spoc')

@spoc_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'ClubSPOC': return redirect('/login')
    
    events = Event.query.filter_by(spoc_id=session['user_id']).all()
    total_regs = sum([len(e.teams_rel) for e in events]) 
    
    # Helper to safely get Coordinator Name
    def get_coord_name(cid):
        if not cid: return "Not Assigned"
        c = Coordinator.query.get(cid)
        return c.name if c else "Not Assigned"

    # Route to Tech Dashboard
    if session.get('category') == 'Tech':
        return render_template('dashboard_spoc_tech.html', 
                               events=events, 
                               total_regs=total_regs,
                               get_coord_name=get_coord_name,
                               category='Tech')
    
    # Fallback / Placeholders
    return render_template('dashboard_spoc_tech.html', events=events, total_regs=total_regs, get_coord_name=get_coord_name, category=session.get('category', 'General'))

# --- CREATE EVENT ---
@spoc_bp.route('/create_event', methods=['POST'])
def create_event():
    if session.get('role') != 'ClubSPOC': return redirect('/login')
    
    try:
        # Date Handling
        date_obj = datetime.strptime(request.form.get('date'), '%Y-%m-%dT%H:%M')
        deadline_str = request.form.get('reg_deadline')
        deadline_obj = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M') if deadline_str else date_obj
        
        # Submission Formats
        formats = request.form.getlist('sub_formats')
        submission_str = ", ".join(formats) if formats else "Any"

        new_event = Event(
            name=request.form.get('name'), 
            category='Tech', 
            date=date_obj, 
            spoc_id=session['user_id'],
            event_mode=request.form.get('event_mode'),
            venue=request.form.get('venue'),
            time_slot=request.form.get('time_slot'),
            reg_deadline=deadline_obj,
            event_type=request.form.get('event_type'), 
            max_participants=request.form.get('max_participants'),
            team_min=request.form.get('team_min') or 1, 
            team_max=request.form.get('team_max') or 1,
            image_url=request.form.get('image_url'), 
            resource_link=request.form.get('resource_link'),
            overview=request.form.get('overview'), 
            rules=request.form.get('rules'), 
            prizes=request.form.get('prizes'), 
            is_published=True,
            
            # Tech Specifics
            tech_problem_type=request.form.get('tech_problem_type'),
            problem_stmt_link=request.form.get('problem_stmt_link'),
            tech_domain=request.form.get('tech_domain'),
            tech_stack_allowed=request.form.get('tech_stack_allowed'),
            submission_format=submission_str,
            rounds_config=request.form.get('rounds_config'),
            
            # Eval
            eval_innovation=request.form.get('eval_innovation'),
            eval_tech_complexity=request.form.get('eval_tech_complexity'),
            eval_feasibility=request.form.get('eval_feasibility'),
            eval_presentation=request.form.get('eval_presentation'),
            eval_impact=request.form.get('eval_impact')
        )

        db.session.add(new_event)
        db.session.commit()
        flash("Tech Event Created Successfully!", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error creating event: {str(e)}", "danger")

    return redirect('/spoc/dashboard')

# --- EDIT EVENT ---
@spoc_bp.route('/edit_event/<int:event_id>', methods=['POST'])
def edit_event(event_id):
    if session.get('role') != 'ClubSPOC': return redirect('/login')
    event = Event.query.get_or_404(event_id)
    
    # Update Basic
    event.name = request.form.get('name')
    event.event_mode = request.form.get('event_mode')
    event.venue = request.form.get('venue')
    event.time_slot = request.form.get('time_slot')
    event.overview = request.form.get('overview')
    event.image_url = request.form.get('image_url')
    event.resource_link = request.form.get('resource_link')
    event.max_participants = request.form.get('max_participants')
    
    # Tech Updates
    event.tech_problem_type = request.form.get('tech_problem_type')
    event.problem_stmt_link = request.form.get('problem_stmt_link')
    event.tech_domain = request.form.get('tech_domain')
    event.tech_stack_allowed = request.form.get('tech_stack_allowed')
    event.rounds_config = request.form.get('rounds_config')
    
    # Eval
    event.eval_innovation = request.form.get('eval_innovation')
    event.eval_tech_complexity = request.form.get('eval_tech_complexity')
    event.eval_feasibility = request.form.get('eval_feasibility')
    event.eval_presentation = request.form.get('eval_presentation')
    event.eval_impact = request.form.get('eval_impact')

    # Date Updates
    try:
        date_str = request.form.get('date')
        if date_str: event.date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        deadline_str = request.form.get('reg_deadline')
        if deadline_str: event.reg_deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
    except: pass

    # Checkboxes
    formats = request.form.getlist('sub_formats')
    if formats: event.submission_format = ", ".join(formats)

    db.session.commit()
    flash("Event Updated!", "success")
    return redirect('/spoc/dashboard')

# --- TOGGLE PUBLISH ---
@spoc_bp.route('/toggle_publish/<int:event_id>', methods=['POST'])
def toggle_publish(event_id):
    if session.get('role') != 'ClubSPOC': return redirect('/login')
    event = Event.query.get_or_404(event_id)
    event.is_published = not event.is_published
    db.session.commit()
    flash(f"Event status changed.", "success")
    return redirect('/spoc/dashboard')

# --- ASSIGN COORDINATORS (FIXED) ---
@spoc_bp.route('/assign_coordinators', methods=['POST'])
def assign_coordinators():
    if session.get('role') != 'ClubSPOC': return redirect('/login')
    
    try:
        event_id = request.form.get('event_id')
        event = Event.query.get(event_id)
        
        def get_or_create_coord(name, email, role):
            if not email: return None
            # Check if coordinator exists
            c = Coordinator.query.filter_by(email=email).first()
            if c:
                # Update name if exists
                c.name = name
                c.role_type = role
            else:
                # Create new
                c = Coordinator(name=name, email=email, password="password123", role_type=role)
                db.session.add(c)
            db.session.commit() # Commit immediately to get ID
            return c

        stu = get_or_create_coord(request.form.get('stu_name'), request.form.get('stu_email'), 'Student')
        staff = get_or_create_coord(request.form.get('staff_name'), request.form.get('staff_email'), 'Staff')

        if stu: event.coord_student_id = stu.id
        if staff: event.coord_staff_id = staff.id
        
        db.session.commit()
        flash("Coordinators assigned successfully!", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error assigning coordinators: {str(e)}", "danger")
        
    return redirect('/spoc/dashboard')

# --- ASSIGN JUDGE (FIXED) ---
@spoc_bp.route('/assign_judge', methods=['POST'])
def assign_judge():
    if session.get('role') != 'ClubSPOC': return redirect('/login')
    
    try:
        event_id = request.form.get('event_id')
        name = request.form.get('name')
        email = request.form.get('email')
        expertise = request.form.get('expertise')
        
        # Check if judge exists
        judge = Judge.query.filter_by(email=email).first()
        
        if judge:
            # Re-assign existing judge to this event
            judge.event_id = event_id
            judge.name = name # Update name just in case
            judge.expertise = expertise
            flash(f"Existing Judge {name} reassigned to this event.", "info")
        else:
            # Create new judge
            new_judge = Judge(name=name, email=email, password="password123", expertise=expertise, event_id=event_id)
            db.session.add(new_judge)
            flash(f"New Judge {name} created and assigned.", "success")
            
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error assigning judge: {str(e)}", "danger")
        
    return redirect('/spoc/dashboard')

# --- REMOVE JUDGE ---
@spoc_bp.route('/remove_judge', methods=['POST'])
def remove_judge():
    if session.get('role') != 'ClubSPOC': return redirect('/login')
    
    judge_id = request.form.get('judge_id')
    judge = Judge.query.get(judge_id)
    
    if judge:
        # We delete the judge entry entirely for this specific event context
        db.session.delete(judge)
        db.session.commit()
        flash("Judge removed from event.", "warning")
        
    return redirect('/spoc/dashboard')

# --- EXPORT ---
@spoc_bp.route('/export_csv/<int:event_id>')
def export_csv(event_id):
    if session.get('role') != 'ClubSPOC': return redirect('/login')
    event = Event.query.get_or_404(event_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Team Code', 'Team Name', 'Member Name', 'Member Email'])
    for team in event.teams_rel:
        for member in team.members:
            writer.writerow([team.code, team.name, member.name, member.email])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename={event.name}_registrations.csv"})