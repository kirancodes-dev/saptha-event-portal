from flask import request, redirect, flash, session, Blueprint
from werkzeug.security import generate_password_hash
import datetime
from models import db # Make sure your database is imported!

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/appoint_spoc', methods=['POST'])
def appoint_spoc():
    # Security check: Only Super Admin can do this!
    if session.get('role') != 'SuperAdmin':
        flash("Unauthorized access!", "danger")
        return redirect('/login')

    name = request.form.get('name')
    email = request.form.get('email').lower().strip()
    password = request.form.get('password')
    category = request.form.get('category') # Tech, Cultural, or Sports

    try:
        # Check if email is already taken
        if db.collection('users').document(email).get().exists:
            flash(f"Account for {email} already exists!", "warning")
            return redirect('/admin/dashboard')

        # Create the SPOC in Firebase Database
        db.collection('users').document(email).set({
            'name': name,
            'email': email,
            'role': 'Coordinator',  # Maps directly to your login dashboard logic!
            'category': category,
            'password': generate_password_hash(password),
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
        })

        flash(f"Successfully appointed {name} as the SPOC for {category} Division!", "success")
        
    except Exception as e:
        flash(f"Error creating SPOC: {e}", "danger")

    return redirect('/admin/dashboard')


