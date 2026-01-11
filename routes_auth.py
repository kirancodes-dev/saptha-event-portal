from flask import Blueprint, render_template, request, redirect, session, flash, jsonify, current_app
from models import db, SuperAdmin, ClubSPOC, Coordinator, Judge, Participant, Event

auth_bp = Blueprint('auth_bp', __name__)

# --- LOGIN ROUTE ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # 1. GET Request: Render Login Page
    if request.method == 'GET':
        response = current_app.make_response(render_template('login.html'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    # 2. POST Request: Handle Login Logic
    role = request.form.get('role')
    email = request.form.get('email')
    password = request.form.get('password')
    secret_key = request.form.get('secret_key')

    user = None
    redirect_url = '/login'

    # --- ROLE BASED AUTHENTICATION ---

    # A. SUPER ADMIN
    if role == 'super_admin':
        user = SuperAdmin.query.filter_by(email=email).first()
        if user and user.password == password and user.secret_key == secret_key:
            session['role'] = 'SuperAdmin'
            session['user_id'] = user.id
            redirect_url = '/super_admin/dashboard'
    
    # B. CLUB SPOC
    elif role == 'club_spoc':
        user = ClubSPOC.query.filter_by(email=email).first()
        if user and user.password == password:
            session['role'] = 'ClubSPOC'
            session['user_id'] = user.id
            session['category'] = user.category
            redirect_url = '/spoc/dashboard'
            
    # C. COORDINATOR (EVENT HEAD) - [FIXED HERE]
    elif role == 'event_head':
        user = Coordinator.query.filter_by(email=email).first()
        if user and user.password == password:
            session['role'] = 'Coordinator'
            session['user_id'] = user.id  # <--- CRITICAL FIX: This was missing!
            session['coord_type'] = user.role_type
            
            # Helper: Check if event is already assigned to redirect smoothly
            if user.role_type == 'Student':
                event = Event.query.filter_by(coord_student_id=user.id).first()
            else:
                event = Event.query.filter_by(coord_staff_id=user.id).first()
            
            if event:
                session['event_id'] = event.id
            
            redirect_url = '/event_head/dashboard'

    # D. JUDGE
    elif role == 'judge':
        user = Judge.query.filter_by(email=email).first()
        if user and user.password == password:
            session['role'] = 'Judge'
            session['user_id'] = user.id
            redirect_url = '/judge/dashboard'
            
    # E. PARTICIPANT
    elif role == 'participant':
        user = Participant.query.filter_by(email=email).first()
        if user and user.password == password:
            session['role'] = 'Participant'
            session['user_id'] = user.id
            redirect_url = '/participant/dashboard'

    # --- FINAL SESSION SETTING ---
    if user:
        session['email'] = user.email
        session['name'] = getattr(user, 'name', 'User')
        return redirect(redirect_url)
    
    flash("Invalid Credentials or Role Selection", "danger")
    return redirect('/login')

# --- LOGOUT ---
@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect('/login')

# --- OTP (MOCK) ---
@auth_bp.route('/send_otp', methods=['POST'])
def send_otp():
    email = request.form.get('email')
    # In production, send real email here
    session['registration_otp'] = "123456"
    session['registration_email'] = email
    return jsonify({'success': True, 'message': 'OTP Sent (Use 123456)'})

# --- REGISTER (PARTICIPANT) ---
@auth_bp.route('/register', methods=['POST'])
def register():
    user_otp = request.form.get('otp')
    if user_otp != "123456":
        return jsonify({'status': 'error', 'message': 'Invalid OTP'})

    email = request.form.get('reg_email')
    if Participant.query.filter_by(email=email).first():
        return jsonify({'status': 'error', 'message': 'Email already exists'})

    # Create Participant
    new_user = Participant(
        name=request.form.get('reg_name'),
        email=email,
        password=request.form.get('reg_password'),
        phone=request.form.get('phone'),
        usn=request.form.get('usn'),
        college=request.form.get('college'),
        department=request.form.get('department'),
        year=request.form.get('year')
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    flash("Account Created! Please Login.", "success")
    return jsonify({'status': 'success', 'redirect': '/login'})