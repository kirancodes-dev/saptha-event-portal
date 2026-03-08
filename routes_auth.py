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
                
                # Check Password and Match Role
                if db_role == role and check_password_hash(user_data.get('password'), password):
                    
                    # Lock Session Data
                    session['user_id'] = email
                    session['name'] = user_data.get('name')
                    session['role'] = role
                    session['category'] = user_data.get('category', 'General')
                    
                    flash(f"Welcome back, {user_data.get('name')}!", "success")
                    
                    # --- ROBUST ROUTING LOGIC ---
                    if role == 'Student': 
                        return redirect('/participant/dashboard')
                    elif role == 'Coordinator': 
                        return redirect('/coordinator/dashboard') 
                    elif role == 'EventCoordinator': 
                        return redirect('/coordinator/scanner') 
                    elif role in ['Admin', 'SuperAdmin']: 
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

# --- 2. REGISTER ROUTE ---
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email').lower().strip()
        usn = request.form.get('usn').upper().strip()
        phone = request.form.get('phone')
        password = request.form.get('password')

        try:
            if db.collection('users').document(email).get().exists:
                flash("Email is already registered! Please login.", "warning")
                return redirect('/login')

            db.collection('users').document(email).set({
                'email': email,
                'name': name,
                'usn': usn,
                'phone': phone,
                'role': 'Student',
                'category': 'General',
                'password': generate_password_hash(password),
                'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
            })

            flash("Account created successfully! You can now login.", "success")
            return redirect('/login')

        except Exception as e:
            flash(f"Registration Error: {e}", "danger")

    return render_template('register.html')

# --- 3. LOGOUT ROUTE ---
@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect('/login')