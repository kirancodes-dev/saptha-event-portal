from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from models import db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('public/login.html')

    # POST Logic
    role_selected = request.form.get('role')
    email = request.form.get('email')
    password = request.form.get('password')
    admin_key = request.form.get('admin_key')

    try:
        user_ref = db.collection('users').document(email)
        doc = user_ref.get()

        if not doc.exists:
            flash("Account not found. Students please register first.", "danger")
            return redirect(url_for('auth.login'))

        user_data = doc.to_dict()
        
        # Verify Password
        if user_data.get('password') != password:
            flash("Incorrect Password", "danger")
            return redirect(url_for('auth.login'))

        # Verify Role Logic
        db_role = user_data.get('role')
        
        # Super Admin Special Check
        if role_selected == 'SuperAdmin':
            if db_role != 'SuperAdmin' or admin_key != 'SuperSecret123':
                flash("Invalid Admin Credentials", "danger")
                return redirect(url_for('auth.login'))
            redirect_url = '/super_admin/dashboard'
        
        # General Role Check
        elif role_selected == 'ClubSPOC' and db_role == 'ClubSPOC':
            session['category'] = user_data.get('category')
            redirect_url = '/spoc/dashboard'
            
        elif role_selected == 'Coordinator' and db_role == 'Coordinator':
            redirect_url = '/event_head/dashboard'
            
        elif role_selected == 'Student' and db_role in ['Student', 'Participant']:
            redirect_url = '/' # Go to Home Page after login
            
        else:
            flash("Role mismatch. Please select the correct role.", "warning")
            return redirect(url_for('auth.login'))

        # Set Session
        session['user_id'] = email
        session['role'] = db_role
        session['name'] = user_data.get('name')
        return redirect(redirect_url)

    except Exception as e:
        print(f"Login Error: {e}")
        return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Only for Student/Participant Account Creation"""
    if request.method == 'GET':
        return render_template('public/register.html')

    try:
        name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        usn = request.form.get('usn')

        if password != confirm:
            flash("Passwords do not match", "danger")
            return redirect(url_for('auth.register'))

        if db.collection('users').document(email).get().exists:
            flash("Email already registered", "warning")
            return redirect(url_for('auth.login'))

        db.collection('users').document(email).set({
            'name': name,
            'email': email,
            'password': password,
            'role': 'Student',
            'usn': usn,
            'created_at': '2026-01-30'
        })

        flash("Account created! Please login.", "success")
        return redirect(url_for('auth.login'))

    except Exception as e:
        print(f"Reg Error: {e}")
        return redirect(url_for('auth.register'))

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))