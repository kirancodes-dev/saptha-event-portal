# =========================================================
# routes_profile.py
# =========================================================
import datetime
from flask import Blueprint, flash, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash
from models import db
from utils import login_required, log_action

profile_bp = Blueprint('profile', __name__, url_prefix='/profile')


@profile_bp.route('/')
@login_required
def view_profile():
    user_doc = db.collection('users').document(session['user_id']).get()
    user     = user_doc.to_dict() or {}
    my_teams = []

    if session.get('role') == 'Student':
        for r in db.collection('registrations').where('lead_email', '==', session['user_id']).stream():
            d       = r.to_dict()
            d['id'] = r.id
            my_teams.append(d)

    return render_template('profile/dashboard.html', user=user, teams=my_teams)


@profile_bp.route('/update', methods=['POST'])
@login_required
def update_profile():
    try:
        name  = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        usn   = request.form.get('usn', '').strip().upper()

        update_data = {'name': name, 'phone': phone}
        if usn:
            update_data['usn'] = usn

        db.collection('users').document(session['user_id']).update(update_data)
        session['name'] = name
        log_action(db, "PROFILE_UPDATED", f"{session['user_id']} updated profile")
        flash("✅ Profile updated!", "success")
    except Exception as exc:
        flash(f"Error: {exc}", "danger")

    return redirect('/profile/')


@profile_bp.route('/security', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw     = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')

    user_doc = db.collection('users').document(session['user_id']).get()
    user     = user_doc.to_dict() or {}

    if not check_password_hash(user.get('password', ''), current_pw):
        flash("❌ Current password is incorrect.", "danger")
        return redirect('/profile/')

    if new_pw != confirm_pw:
        flash("❌ New passwords do not match.", "danger")
        return redirect('/profile/')

    if len(new_pw) < 8:
        flash("❌ Password must be at least 8 characters.", "danger")
        return redirect('/profile/')

    db.collection('users').document(session['user_id']).update({
        'password': generate_password_hash(new_pw)
    })
    log_action(db, "PASSWORD_CHANGED", f"{session['user_id']} changed password")
    flash("🔒 Password changed successfully!", "success")
    return redirect('/profile/')