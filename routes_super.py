from flask import Blueprint, render_template, session, redirect, flash, request
from models import db, SuperAdmin, ClubSPOC, Event, Participant, Coordinator, Team

super_bp = Blueprint('super_bp', __name__, url_prefix='/super_admin')

@super_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'SuperAdmin': return redirect('/login')
    
    # 1. FETCH ALL DATA
    spocs = ClubSPOC.query.all()
    events = Event.query.all()
    participants = Participant.query.all()
    
    # 2. CALCULATE GLOBAL STATS
    stats = {
        'total_users': len(spocs) + len(participants), # Total users in system
        'total_events': len(events),
        'total_spocs': len(spocs),
        'total_students': len(participants)
    }

    return render_template('dashboard_super.html', 
                           spocs=spocs, 
                           events=events,
                           participants=participants,
                           stats=stats)

# --- ACTION: CREATE SPOC ---
@super_bp.route('/create_spoc', methods=['POST'])
def create_spoc():
    if session.get('role') != 'SuperAdmin': return redirect('/login')
    
    name = request.form.get('name')
    email = request.form.get('email')
    category = request.form.get('category')
    password = request.form.get('password') or "spoc123"
    
    # Check duplicate
    if ClubSPOC.query.filter_by(email=email).first():
        flash(f"Error: Email {email} already exists!", "danger")
        return redirect('/super_admin/dashboard')

    # Create new SPOC
    new_spoc = ClubSPOC(name=name, email=email, password=password, category=category)
    db.session.add(new_spoc)
    db.session.commit()
    
    flash(f"Success! {name} added as {category} Lead.", "success")
    return redirect('/super_admin/dashboard')

# --- ACTION: DELETE ENTITIES (Unified Route) ---
@super_bp.route('/delete_user/<user_type>/<int:id>', methods=['POST'])
def delete_user(user_type, id):
    if session.get('role') != 'SuperAdmin': return redirect('/login')
    
    item = None
    item_name = "Item"

    # Identify the object to delete
    if user_type == 'spoc':
        item = ClubSPOC.query.get(id)
        item_name = "Club SPOC"
    elif user_type == 'participant':
        item = Participant.query.get(id)
        item_name = "Student"
    elif user_type == 'event':
        item = Event.query.get(id)
        item_name = "Event"
    
    # Execute Delete
    if item:
        try:
            db.session.delete(item)
            db.session.commit()
            flash(f"{item_name} deleted successfully.", "warning")
        except Exception as e:
            db.session.rollback()
            flash(f"Error deleting {item_name}: {str(e)}", "danger")
    else:
        flash(f"{item_name} not found.", "danger")
        
    return redirect('/super_admin/dashboard')