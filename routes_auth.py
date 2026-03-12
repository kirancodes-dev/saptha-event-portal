from flask import Blueprint, render_template, request, redirect, session, flash
from models import db
from werkzeug.security import check_password_hash, generate_password_hash
import datetime

auth_bp = Blueprint('auth', __name__)

# ========================================================
# 👑 DEVELOPER HANDOVER: SUPER ADMIN CREDENTIALS
# ========================================================
SUPER_ADMIN_EMAIL = "admin@snpsu.edu.in"
SUPER_ADMIN_DEFAULT_PASS = "Saptha@Admin2026"
MASTER_SECRET_KEY = "SAPTHA@2026"
# ========================================================

# --- 1. LOGIN ROUTE ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # .strip() removes any accidental blank spaces typed by the user
        role = request.form.get('role').strip() 
        
        # Normalize the Space for HTML forms
        if role == 'Super Admin':
            role = 'SuperAdmin'
            
        email = request.form.get('email').lower().strip()
        password = request.form.get('password')
        secret_key = request.form.get('secret_key')

        if role == 'SuperAdmin' and secret_key != MASTER_SECRET_KEY:
            flash('🔒 Invalid Master Security Key! Access Denied.', 'danger')
            return redirect('/login')

        try:
            user_doc = db.collection('users').document(email).get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                db_role = user_data.get('role', '').strip()
                
                # Fix space matching from old database entries
                if db_role == 'Super Admin':
                    db_role = 'SuperAdmin'
                
                # --- NEW: INDESTRUCTIBLE PASSWORD CHECK ---
                stored_password = user_data.get('password', '')
                is_valid_password = False
                
                # 1. If it's a raw number in Firebase, force it to be a string
                if isinstance(stored_password, int) or isinstance(stored_password, float):
                    stored_password = str(int(stored_password))
                    
                # 2. Check if it's a secure hash
                if stored_password.startswith('scrypt:') or stored_password.startswith('pbkdf2:'):
                    is_valid_password = check_password_hash(stored_password, password)
                else:
                    # 3. Fallback for old accounts saved in plain text
                    is_valid_password = (stored_password == str(password))
                
                # Check Password and Match Role
                if db_role == role and is_valid_password:
                    
                    # Lock Session Data
                    session['user_id'] = email
                    session['name'] = user_data.get('name')
                    session['role'] = role
                    session['category'] = user_data.get('category', 'General')
                    
                    flash(f"Welcome back, {user_data.get('name')}!", "success")
                    
                    # Routing Logic
                    if role == 'Student': 
                        return redirect('/participant/dashboard')
                    elif role == 'Coordinator': 
                        return redirect('/coordinator/dashboard') 
                    elif role == 'EventCoordinator': 
                        return redirect('/coordinator/scanner') 
                    elif role == 'SuperAdmin': 
                        return redirect('/admin/dashboard')
                    elif role == 'Judge': 
                        return redirect('/judge/dashboard')
                    else:
                        flash(f"Login successful, but no dashboard found for role: {role}", "warning")
                        return redirect('/')
                else:
                    flash('Invalid password or you selected the wrong role.', 'danger')
            else:
                # Auto-Create Super Admin Logic
                if role == 'SuperAdmin' and email == SUPER_ADMIN_EMAIL and password == SUPER_ADMIN_DEFAULT_PASS:
                    db.collection('users').document(email).set({
                        'email': email, 'name': 'System Super Admin', 'role': 'SuperAdmin',
                        'category': 'All', 'password': generate_password_hash(password),
                        'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
                    })
                    session['user_id'] = email
                    session['name'] = 'System Super Admin'
                    session['role'] = 'SuperAdmin'
                    flash("👑 Super Admin account successfully initialized!", "success")
                    return redirect('/admin/dashboard')
                
                flash('Account not found. Please register.', 'warning')
                
        except Exception as e:
            flash(f"Login Error: {e}", "danger")

    return render_template('login.html')

# --- 2. LOGOUT ROUTE ---
@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect('/')  # <-- Changed from /login to / (Home Page)