from flask import Blueprint, render_template, request, redirect, session, flash
from models import db
from utils import login_required, role_required
from werkzeug.security import generate_password_hash
import datetime
from utils_email import send_credentials_email
from google.cloud import firestore

# Create the blueprint for all /admin routes
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ========================================================
# 1. SUPER ADMIN DASHBOARD
# ========================================================
@admin_bp.route('/dashboard')
@login_required
@role_required(['SuperAdmin', 'Super Admin'])
def dashboard():
    # Super Admins bypass division filters and see EVERY event in the university
    events_ref = db.collection('events').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
    
    events = []
    total_regs = 0
    total_staff = 0
    
    for e in events_ref:
        d = e.to_dict()
        d['id'] = e.id
        total_regs += d.get('registration_count', 0)
        total_staff += len(d.get('staff', []))
        
        # Calculate how many active teams have been judged in the CURRENT round
        regs = db.collection('registrations').where('event_id', '==', e.id).stream()
        
        scored_count = 0
        for r in regs:
            reg_data = r.to_dict()
            # 🚀 NEW: Only count scores if the team is NOT eliminated!
            if not reg_data.get('is_eliminated', False) and reg_data.get('scores'):
                scored_count += 1
                
        d['scored_teams'] = scored_count
        events.append(d)
        
    return render_template('admin/dashboard.html', events=events, total_regs=total_regs, total_staff=total_staff, user_name=session.get('name'))

# ========================================================
# 2. APPOINT CLUB SPOC (WITH SECURITY LOCK)
# ========================================================
@admin_bp.route('/appoint_spoc', methods=['POST'])
@login_required
@role_required(['SuperAdmin', 'Super Admin'])
def appoint_spoc():
    try:
        # Capture form data
        name = request.form.get('name')
        email = request.form.get('email').lower().strip()
        password = request.form.get('password')
        category = request.form.get('category')
        
        user_ref = db.collection('users').document(email)
        
        # Check if this email is already registered
        if user_ref.get().exists:
            flash(f"⚠️ A user with the email {email} already exists!", "warning")
        else:
            # 🚀 INJECT THE SPOC INTO FIREBASE WITH A PASSWORD RESET LOCK
            user_ref.set({
                'email': email,
                'name': name,
                'role': 'ClubSPOC', # Officially designate them as a SPOC
                'category': category,
                'password': generate_password_hash(password),
                'created_at': datetime.datetime.now().strftime("%Y-%m-%d"),
                'needs_password_reset': True # <--- FORCES THEM TO SECURE THEIR ACCOUNT ON FIRST LOGIN!
            })
            
            # Fire the email to the new SPOC with their temporary credentials
            try:
                send_credentials_email(email, name, f'Club SPOC ({category} Division)', password, category)
            except Exception as email_err:
                print(f"Non-fatal error sending email: {email_err}")
            
            flash(f"✅ SPOC Account for {name} ({category} Division) created successfully! Credentials emailed.", "success")
            
    except Exception as e:
        flash(f"Error appointing SPOC: {e}", "danger")
        
    return redirect('/admin/dashboard')