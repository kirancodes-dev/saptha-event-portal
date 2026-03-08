from flask import Blueprint, render_template, request, redirect, session, flash, send_file, jsonify
from models import db
from utils import login_required, role_required
from werkzeug.security import generate_password_hash
import pandas as pd
import io
import secrets
import string
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from utils_email import send_credentials_email, send_broadcast_email
from google.cloud import firestore

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# --- 1. DASHBOARD ---
@admin_bp.route('/dashboard')
@login_required
@role_required(['Admin', 'SuperAdmin']) 
def dashboard():
    events_ref = db.collection('events').stream()
    events = [{'id': e.id, 'title': e.to_dict().get('title')} for e in events_ref]
    
    users_count = len(list(db.collection('users').stream()))
    regs_count = len(list(db.collection('registrations').stream()))
    
    # Corrected Sorting: Use firestore.Query.DESCENDING for bulletproof sorting
    anns = db.collection('announcements').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
    announcements = [{'id': a.id, **a.to_dict()} for a in anns]

    return render_template('admin/dashboard.html', events=events, stats={'users': users_count, 'regs': regs_count}, announcements=announcements)

# --- 2. USER MANAGEMENT ---
@admin_bp.route('/users')
@login_required
@role_required(['Admin', 'SuperAdmin'])
def manage_users():
    users_ref = db.collection('users').stream()
    users = [{'id': u.id, **u.to_dict()} for u in users_ref]
    return render_template('admin/users.html', users=users)

# --- 3. ADD USER (With Email Error Handling) ---
@admin_bp.route('/add_user', methods=['POST'])
@login_required
@role_required(['Admin', 'SuperAdmin'])
def add_user():
    try:
        email = request.form.get('email').lower().strip()
        name = request.form.get('name')
        role = request.form.get('role')
        category = request.form.get('category', 'General') 

        # 1. Check if user exists
        if db.collection('users').document(email).get().exists:
            flash("User already exists!", "warning")
            return redirect('/admin/users')

        # 2. Generate Password
        alphabet = string.ascii_letters + string.digits
        raw_password = ''.join(secrets.choice(alphabet) for i in range(8))
        
        # 3. Create User in DB
        db.collection('users').document(email).set({
            'email': email,
            'name': name,
            'role': role,
            'category': category,
            'password': generate_password_hash(raw_password), 
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
        })

        # 4. SEND EMAIL & CHECK SUCCESS
        email_sent, error_message = send_credentials_email(email, name, role, raw_password, category)

        if email_sent:
            flash(f"✅ User created! Password sent to {email}.", "success")
        else:
            # Show the actual error so we can fix it
            flash(f"⚠️ User created, BUT EMAIL FAILED. Error: {error_message}", "warning")

    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect('/admin/users')

@admin_bp.route('/delete_user/<user_id>')
@login_required
@role_required(['Admin', 'SuperAdmin'])
def delete_user(user_id):
    if user_id == session.get('user_id'):
        flash("You cannot delete your own account!", "danger")
        return redirect('/admin/users')
        
    db.collection('users').document(user_id).delete()
    flash("User deleted permanently.", "danger")
    return redirect('/admin/users')

# --- 4. EVENT MANAGEMENT ---
@admin_bp.route('/manage_events')
@login_required
@role_required(['Admin', 'SuperAdmin'])
def manage_events():
    events_ref = db.collection('events').stream()
    events = [{'id': e.id, **e.to_dict()} for e in events_ref]
    return render_template('admin/events.html', events=events)

@admin_bp.route('/delete_event/<event_id>')
@login_required
@role_required(['Admin', 'SuperAdmin'])
def delete_event(event_id):
    db.collection('events').document(event_id).delete()
    regs = db.collection('registrations').where('event_id', '==', event_id).stream()
    for r in regs: r.reference.delete()
    flash("Event deleted.", "success")
    return redirect('/admin/manage_events')

# --- 5. EXPORT DATA ---
@admin_bp.route('/export/<fmt>/<event_id>')
@login_required
@role_required(['Admin', 'SuperAdmin'])
def export_data(fmt, event_id):
    try:
        regs = db.collection('registrations').where('event_id', '==', event_id).stream()
        data = []
        for r in regs:
            d = r.to_dict()
            row = {
                'Team Name': d.get('team_name'),
                'Lead Name': d.get('lead_name'),
                'Email': d.get('lead_email'),
                'Phone': d.get('members', [{}])[0].get('phone', 'N/A') if d.get('members') else 'N/A',
                'Status': d.get('status'),
                'Payment': d.get('payment_status', 'Free')
            }
            data.append(row)

        if not data:
            flash("No data to export.", "warning")
            return redirect('/admin/dashboard')

        if fmt == 'excel':
            df = pd.DataFrame(data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Registrations')
            output.seek(0)
            return send_file(output, download_name=f"Event_{event_id}.xlsx", as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        elif fmt == 'pdf':
            buffer = io.BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)
            p.drawString(100, 750, f"Report for Event: {event_id}")
            y = 700
            for row in data:
                p.drawString(50, y, f"{row['Lead Name']} - {row['Email']}")
                y -= 20
                if y < 50: p.showPage(); y = 750
            p.save()
            buffer.seek(0)
            return send_file(buffer, download_name=f"Event_{event_id}.pdf", as_attachment=True, mimetype='application/pdf')

    except Exception as e:
        flash(f"Export Failed: {str(e)}", "danger")
        return redirect('/admin/dashboard')
    return redirect('/admin/dashboard')

# --- 6. BROADCAST ---
@admin_bp.route('/broadcast', methods=['POST'])
@login_required
@role_required(['Admin', 'SuperAdmin'])
def broadcast_message():
    try:
        event_id = request.form.get('event_id')
        subject = request.form.get('subject')
        message = request.form.get('message')
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists: return redirect('/admin/dashboard')
        
        regs = db.collection('registrations').where('event_id', '==', event_id).stream()
        email_list = list(set([r.to_dict().get('lead_email') for r in regs if r.to_dict().get('lead_email')]))

        if send_broadcast_email(email_list, subject, message, event_doc.to_dict().get('title')):
            flash(f"✅ Sent to {len(email_list)} participants!", "success")
        else:
            flash("❌ Failed to send emails.", "danger")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    return redirect('/admin/dashboard')

# --- 7. ANNOUNCEMENTS ---
@admin_bp.route('/announce', methods=['POST'])
@login_required
@role_required(['Admin', 'SuperAdmin'])
def post_announcement():
    try:
        db.collection('announcements').add({
            'message': request.form.get('message'),
            'priority': request.form.get('priority'),
            'posted_by': session['name'],
            'timestamp': datetime.datetime.now(),
            'active': True
        })
        flash("Announcement Posted!", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect('/admin/dashboard')

@admin_bp.route('/delete_announcement/<ann_id>')
@login_required
@role_required(['Admin', 'SuperAdmin'])
def delete_announcement(ann_id):
    db.collection('announcements').document(ann_id).delete()
    flash("Deleted.", "info")
    return redirect('/admin/dashboard')

# --- 8. SEARCH ---
@admin_bp.route('/search', methods=['GET'])
@login_required
@role_required(['Admin', 'SuperAdmin'])
def global_search():
    query = request.args.get('q', '').lower()
    if not query: return jsonify({'results': []})
    results = []
    
    users = db.collection('users').stream()
    for u in users:
        d = u.to_dict()
        if query in d.get('name', '').lower() or query in d.get('email', '').lower():
            results.append({'category': 'User', 'title': d.get('name'), 'desc': d.get('email'), 'link': '/admin/users'})
            
    return jsonify({'results': results[:10]})

# --- 9. LEADERBOARD ---
@admin_bp.route('/leaderboard/<event_id>')
def live_leaderboard(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists: return "Event not found", 404
    regs = db.collection('registrations').where('event_id', '==', event_id).stream()
    leaderboard = []
    for r in regs:
        d = r.to_dict()
        scores = d.get('scores', {})
        if scores:
            total = sum([int(s['total']) for s in scores.values()])
            leaderboard.append({'team': d.get('team_name'), 'score': round(total/len(scores), 2)})
    leaderboard.sort(key=lambda x: x['score'], reverse=True)
    return render_template('admin/leaderboard.html', teams=leaderboard, event_title=event_doc.to_dict().get('title'))