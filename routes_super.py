from flask import Blueprint, render_template, session, redirect, flash, request
from models import db, FirebaseWrapper
import logging

super_bp = Blueprint('super_bp', __name__, url_prefix='/super_admin')
logger = logging.getLogger(__name__)

@super_bp.route('/dashboard')
def dashboard():
    """
    The Ultimate Super Admin Dashboard.
    Fetches data from ALL collections to provide a complete system overview.
    """
    if session.get('role') != 'SuperAdmin': return redirect('/login')
    
    try:
        # 1. Fetch ALL User Types
        users_ref = db.collection('users')
        
        # Stream all users once (More efficient than 4 queries if user base is small < 1000)
        # For larger apps, use separate queries or Algolia
        all_users = users_ref.stream()
        
        spocs, students, judges, coords = [], [], [], []
        
        for doc in all_users:
            u = FirebaseWrapper(doc.id, doc.to_dict())
            role = u.role
            if role == 'ClubSPOC': spocs.append(u)
            elif role == 'Participant': students.append(u)
            elif role == 'Judge': judges.append(u)
            elif role == 'Coordinator': coords.append(u)

        # 2. Fetch ALL Events
        event_docs = db.collection('events').stream()
        events = [FirebaseWrapper(d.id, d.to_dict()) for d in event_docs]
        
        # 3. Stats Calculation
        stats = {
            'total_users': len(spocs) + len(students) + len(judges) + len(coords),
            'total_events': len(events),
            'total_spocs': len(spocs),
            'total_students': len(students),
            'total_judges': len(judges),
            'active_events': sum(1 for e in events if e.is_published)
        }

        return render_template('dashboard_super.html', 
                               spocs=spocs, 
                               events=events, 
                               students=students, 
                               judges=judges,
                               coords=coords,
                               stats=stats)
                               
    except Exception as e:
        logger.error(f"Super Admin Error: {e}")
        flash("System Error: Unable to load dashboard data.", "danger")
        return redirect('/')

@super_bp.route('/create_user', methods=['POST'])
def create_user():
    """
    Universal User Creator.
    Allows Super Admin to create ANY role manually.
    """
    if session.get('role') != 'SuperAdmin': return redirect('/login')
    
    try:
        # Extract Form Data
        role = request.form.get('role')
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password') or "welcome123"
        
        # Optional fields based on role
        category = request.form.get('category') # For SPOCs
        usn = request.form.get('usn') # For Students
        dept = request.form.get('department') # For Students
        
        # 1. Check Duplicate
        if db.collection('users').document(email).get().exists:
            flash(f"User with email {email} already exists.", "warning")
            return redirect('/super_admin/dashboard')
            
        # 2. Build Data Object
        user_data = {
            'name': name,
            'email': email,
            'password': password, # In production, hash this!
            'role': role,
            'created_by': 'SuperAdmin'
        }
        
        # Add Role-Specific Data
        if role == 'ClubSPOC':
            user_data['category'] = category
        elif role == 'Participant':
            user_data['usn'] = usn
            user_data['department'] = dept
            
        # 3. Save to Firestore
        db.collection('users').document(email).set(user_data)
        flash(f"Successfully created {role}: {name}", "success")
        
    except Exception as e:
        logger.error(f"Create User Error: {e}")
        flash("Failed to create user. Check logs.", "danger")
        
    return redirect('/super_admin/dashboard')

@super_bp.route('/delete_entity/<entity_type>/<entity_id>', methods=['POST'])
def delete_entity(entity_type, entity_id):
    """
    Universal Delete Handler.
    """
    if session.get('role') != 'SuperAdmin': return redirect('/login')
    
    try:
        collection = 'events' if entity_type == 'event' else 'users'
        db.collection(collection).document(entity_id).delete()
        flash(f"{entity_type.capitalize()} deleted successfully.", "info")
    except Exception as e:
        flash("Delete failed.", "danger")
        
    return redirect('/super_admin/dashboard')

@super_bp.route('/system_reset', methods=['POST'])
def system_reset():
    """
    Safe System Reset (Actually just deletes data, keeps Admins).
    """
    if session.get('role') != 'SuperAdmin': return redirect('/login')
    
    confirm_text = request.form.get('confirm_text')
    if confirm_text != 'DELETE':
        flash("Reset cancelled. You must type 'DELETE'.", "warning")
        return redirect('/super_admin/dashboard')
        
    # Logic to delete collections would go here (omitted for safety in demo)
    flash("System Reset Simulated. (Data protected in demo mode)", "info")
    return redirect('/super_admin/dashboard')