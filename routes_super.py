from flask import Blueprint, render_template, session, redirect, flash, request
from models import db

super_bp = Blueprint('super_bp', __name__, url_prefix='/super_admin')

# --- HELPER CLASS FOR HTML COMPATIBILITY ---
class FirebaseWrapper:
    def __init__(self, id, data):
        self.id = id
        self._data = data
    def __getattr__(self, name):
        return self._data.get(name)

@super_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'SuperAdmin': return redirect('/login')
    
    # 1. FETCH SPOCS (Users with role='ClubSPOC')
    spoc_query = db.collection('users').where('role', '==', 'ClubSPOC').stream()
    spocs = [FirebaseWrapper(doc.id, doc.to_dict()) for doc in spoc_query]

    # 2. FETCH PARTICIPANTS (Users with role='Participant')
    part_query = db.collection('users').where('role', '==', 'Participant').stream()
    participants = [FirebaseWrapper(doc.id, doc.to_dict()) for doc in part_query]

    # 3. FETCH EVENTS
    event_query = db.collection('events').stream()
    events = [FirebaseWrapper(doc.id, doc.to_dict()) for doc in event_query]
    
    # 4. CALCULATE GLOBAL STATS
    stats = {
        'total_users': len(spocs) + len(participants),
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
    
    # Check duplicate (Check if document with this email exists)
    user_ref = db.collection('users').document(email)
    if user_ref.get().exists:
        flash(f"Error: Email {email} already exists!", "danger")
        return redirect('/super_admin/dashboard')

    # Create new SPOC in 'users' collection
    spoc_data = {
        'name': name, 
        'email': email, 
        'password': password, 
        'role': 'ClubSPOC', # Important: This defines them as a SPOC
        'category': category
    }
    
    user_ref.set(spoc_data)
    
    flash(f"Success! {name} added as {category} Lead.", "success")
    return redirect('/super_admin/dashboard')

# --- ACTION: DELETE ENTITIES ---
# Note: Firebase IDs are strings (emails or auto-generated ids), so we removed 'int:'
@super_bp.route('/delete_user/<user_type>/<id>', methods=['POST'])
def delete_user(user_type, id):
    if session.get('role') != 'SuperAdmin': return redirect('/login')
    
    try:
        if user_type == 'spoc' or user_type == 'participant':
            # Both are stored in 'users' collection
            db.collection('users').document(id).delete()
            flash("User deleted successfully.", "warning")
            
        elif user_type == 'event':
            # Delete the event
            db.collection('events').document(id).delete()
            
            # Optional: Delete associated teams/scores if you want a clean db
            # (Firestore requires manual deletion of sub-collections or related docs)
            flash("Event deleted successfully.", "warning")
            
    except Exception as e:
        flash(f"Error deleting: {str(e)}", "danger")
        
    return redirect('/super_admin/dashboard')