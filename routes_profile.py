from flask import Blueprint, render_template, request, redirect, session, flash
from models import db
from utils import login_required
from werkzeug.security import generate_password_hash, check_password_hash

profile_bp = Blueprint('profile', __name__, url_prefix='/profile')

# --- 1. VIEW PROFILE ---
@profile_bp.route('/')
@login_required
def view_profile():
    # Fetch User Data
    user_doc = db.collection('users').document(session['user_id']).get()
    user = user_doc.to_dict()
    
    # Fetch My Teams (For Students)
    my_teams = []
    if session['role'] == 'Student':
        regs = db.collection('registrations').where('lead_email', '==', session['user_id']).stream()
        for r in regs:
            d = r.to_dict()
            d['id'] = r.id
            my_teams.append(d)
            
    return render_template('profile/dashboard.html', user=user, teams=my_teams)

# --- 2. UPDATE DETAILS ---
@profile_bp.route('/update', methods=['POST'])
@login_required
def update_profile():
    try:
        name = request.form.get('name')
        phone = request.form.get('phone')
        usn = request.form.get('usn') # Only for students
        
        update_data = {
            'name': name,
            'phone': phone
        }
        if usn: update_data['usn'] = usn
        
        db.collection('users').document(session['user_id']).update(update_data)
        
        # Update Session Name
        session['name'] = name
        
        flash("✅ Profile updated successfully!", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    
    return redirect('/profile/')

# --- 3. CHANGE PASSWORD ---
@profile_bp.route('/security', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password')
    new_pw = request.form.get('new_password')
    confirm_pw = request.form.get('confirm_password')
    
    user_doc = db.collection('users').document(session['user_id']).get()
    user = user_doc.to_dict()
    
    # 1. Verify Current Password
    if not check_password_hash(user['password'], current_pw):
        flash("❌ Current password is incorrect.", "danger")
        return redirect('/profile/')
    
    # 2. Check Match
    if new_pw != confirm_pw:
        flash("❌ New passwords do not match.", "danger")
        return redirect('/profile/')
    
    # 3. Update Password
    hashed_pw = generate_password_hash(new_pw)
    db.collection('users').document(session['user_id']).update({'password': hashed_pw})
    
    flash("🔒 Password changed successfully!", "success")
    return redirect('/profile/')