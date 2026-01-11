from flask import Blueprint, render_template, request, redirect, session, flash, jsonify, current_app
from models import db

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    role = request.form.get('role')
    email = request.form.get('email')
    password = request.form.get('password')
    secret_key = request.form.get('secret_key')

    # Firebase: Fetch User by Email (User ID is Email)
    user_ref = db.collection('users').document(email)
    user_doc = user_ref.get()

    if not user_doc.exists:
        flash("User not found", "danger")
        return redirect('/login')

    user_data = user_doc.to_dict()

    # Verify Password (In production, hash this!)
    if user_data.get('password') != password:
        flash("Invalid Password", "danger")
        return redirect('/login')

    # --- ROLE ROUTING ---
    redirect_url = '/login'
    
    # 1. SUPER ADMIN (Special Case - maybe stored in users or checks code)
    if role == 'super_admin':
        if user_data.get('role') == 'SuperAdmin' and secret_key == 'SuperSecret123': # Hardcoded for now
            session['role'] = 'SuperAdmin'
            session['user_id'] = email
            redirect_url = '/super_admin/dashboard'
    
    # 2. GENERAL ROLES
    elif role == 'club_spoc' and user_data.get('role') == 'ClubSPOC':
        session['role'] = 'ClubSPOC'
        session['user_id'] = email
        session['category'] = user_data.get('category')
        redirect_url = '/spoc/dashboard'
        
    elif role == 'event_head' and user_data.get('role') == 'Coordinator':
        session['role'] = 'Coordinator'
        session['user_id'] = email
        session['coord_type'] = user_data.get('role_type')
        redirect_url = '/event_head/dashboard'
        
    elif role == 'judge' and user_data.get('role') == 'Judge':
        session['role'] = 'Judge'
        session['user_id'] = email
        redirect_url = '/judge/dashboard'
        
    elif role == 'participant' and user_data.get('role') == 'Participant':
        session['role'] = 'Participant'
        session['user_id'] = email
        redirect_url = '/participant/dashboard'
    
    else:
        flash("Role mismatch or invalid credentials", "danger")
        return redirect('/login')

    # Success Session Set
    session['email'] = email
    session['name'] = user_data.get('name')
    return redirect(redirect_url)

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@auth_bp.route('/register', methods=['POST'])
def register():
    # Only for Participants
    email = request.form.get('reg_email')
    
    # Check if exists
    if db.collection('users').document(email).get().exists:
        return jsonify({'status': 'error', 'message': 'Email exists'})
        
    data = {
        'name': request.form.get('reg_name'),
        'email': email,
        'password': request.form.get('reg_password'),
        'phone': request.form.get('phone'),
        'usn': request.form.get('usn'),
        'college': request.form.get('college'),
        'role': 'Participant'
    }
    
    db.collection('users').document(email).set(data)
    flash("Account Created", "success")
    return jsonify({'status': 'success', 'redirect': '/login'})