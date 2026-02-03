from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from models import db
import datetime

super_bp = Blueprint('super_admin', __name__, url_prefix='/super_admin')

# --- 1. DASHBOARD ---
@super_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'SuperAdmin': return redirect('/login')

    try:
        # Stats Logic
        users_ref = db.collection('users')
        spocs = list(users_ref.where('role', '==', 'ClubSPOC').stream())
        
        # Safe counts
        active_events = len(list(db.collection('events').where('status', '==', 'active').stream()))
        students = len(list(users_ref.where('role', 'in', ['Student', 'Participant']).stream()))
        
        spoc_list = [{'id': d.id, **d.to_dict()} for d in spocs]

        return render_template(
            'super_admin/dashboard.html', 
            stats={'spocs': len(spoc_list), 'events': active_events, 'students': students},
            spocs=spoc_list
        )
    except Exception as e:
        print(f"Dashboard Error: {e}")
        return "System Error", 500

# --- 2. MANAGE EVENTS (NEW ROUTE) ---
@super_bp.route('/events')
def events():
    # Placeholder: In future, make a 'manage_events.html'
    flash("Event Management Module loaded.", "info")
    return redirect(url_for('super_admin.dashboard')) 

# --- 3. USER ROLES (NEW ROUTE) ---
@super_bp.route('/users')
def users():
    flash("User Role Management loaded.", "info")
    return redirect(url_for('super_admin.dashboard'))

# --- 4. ANALYTICS (NEW ROUTE) ---
@super_bp.route('/analytics')
def analytics():
    flash("Analytics Module loaded.", "info")
    return redirect(url_for('super_admin.dashboard'))

# --- 5. CREATE SPOC ---
@super_bp.route('/create_spoc', methods=['POST'])
def create_spoc():
    if session.get('role') != 'SuperAdmin': return redirect('/login')

    try:
        email = request.form.get('spoc_email')
        if db.collection('users').document(email).get().exists:
            flash("User already exists!", "warning")
            return redirect(url_for('super_admin.dashboard'))

        user_data = {
            'name': request.form.get('spoc_name'),
            'email': email,
            'password': request.form.get('spoc_password'),
            'role': 'ClubSPOC',
            'club_name': request.form.get('club_name'),
            'category': request.form.get('club_category'),
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
        }
        db.collection('users').document(email).set(user_data)
        flash("Club Lead appointed successfully!", "success")
        
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")

    return redirect(url_for('super_admin.dashboard'))

# --- 6. DELETE USER ---
@super_bp.route('/delete_user/<user_id>')
def delete_user(user_id):
    if session.get('role') != 'SuperAdmin': return redirect('/login')
    try:
        db.collection('users').document(user_id).delete()
        flash("User removed.", "success")
    except:
        flash("Error deleting user.", "danger")
    return redirect(url_for('super_admin.dashboard'))