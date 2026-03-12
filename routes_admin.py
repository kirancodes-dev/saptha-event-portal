from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from werkzeug.security import generate_password_hash
from google.cloud.firestore_v1.base_query import FieldFilter
import datetime
from models import db 

# Define Blueprint with the /admin prefix
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# --- 1. SUPER ADMIN DASHBOARD ---
@admin_bp.route('/dashboard')
def admin_dashboard():
    # Security Check
    if session.get('role') not in ['Admin', 'SuperAdmin']:
        flash("Unauthorized access!", "danger")
        return redirect('/login')

    try:
        # Fetch Stats for the Dashboard
        events_ref = db.collection('events').stream()
        users_ref = db.collection('users').stream()
        regs_ref = db.collection('registrations').stream()

        events = []
        for e in events_ref:
            d = e.to_dict()
            d['id'] = e.id
            events.append(d)

        # Count Staff (Coordinators and Judges)
        staff_count = 0
        for u in users_ref:
            if u.to_dict().get('role') in ['Coordinator', 'Judge', 'EventCoordinator']:
                staff_count += 1

        total_regs = len(list(regs_ref))

        return render_template('admin/dashboard.html', 
                               events=events, 
                               total_staff=staff_count, 
                               total_regs=total_regs,
                               user_name=session.get('name'))
    except Exception as e:
        flash(f"Dashboard Error: {e}", "danger")
        return redirect('/')

# --- 2. APPOINT CLUB SPOC (The Fix) ---
@admin_bp.route('/appoint_spoc', methods=['POST'])
def appoint_spoc():
    """
    Since this is inside admin_bp with url_prefix='/admin', 
    the full URL for the HTML form is: /admin/appoint_spoc
    """
    if session.get('role') != 'SuperAdmin':
        flash("Only Super Admins can appoint SPOCs!", "danger")
        return redirect('/login')

    name = request.form.get('name')
    email = request.form.get('email').lower().strip()
    password = request.form.get('password')
    category = request.form.get('category')

    try:
        # Check for existing user
        if db.collection('users').document(email).get().exists:
            flash(f"The email {email} is already in use!", "warning")
            return redirect('/admin/dashboard')

        # Create Coordinator Account
        db.collection('users').document(email).set({
            'name': name,
            'email': email,
            'role': 'Coordinator',
            'category': category,
            'password': generate_password_hash(password),
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
        })

        flash(f"👑 Success! {name} is now the {category} Club SPOC.", "success")
        
    except Exception as e:
        flash(f"Error: {e}", "danger")

    return redirect('/admin/dashboard')