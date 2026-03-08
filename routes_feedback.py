from flask import Blueprint, render_template, request, redirect, session, flash
from models import db
from utils import login_required, role_required
import datetime

feedback_bp = Blueprint('feedback', __name__, url_prefix='/feedback')

# --- 1. SUBMIT FEEDBACK (Student) ---
@feedback_bp.route('/submit/<reg_id>', methods=['GET', 'POST'])
@login_required
def submit_feedback(reg_id):
    # Security: Ensure user owns this registration
    reg_ref = db.collection('registrations').document(reg_id)
    reg = reg_ref.get()
    
    if not reg.exists or reg.to_dict().get('lead_email') != session['user_id']:
        flash("Unauthorized access.", "danger")
        return redirect('/participant/dashboard')

    if request.method == 'POST':
        rating = request.form.get('rating')
        comments = request.form.get('comments')
        
        reg_ref.update({
            'feedback': {
                'rating': int(rating),
                'comments': comments,
                'timestamp': datetime.datetime.now()
            }
        })
        flash("Thank you for your feedback!", "success")
        return redirect('/participant/dashboard')

    return render_template('feedback/form.html', reg=reg.to_dict(), reg_id=reg_id)

# --- 2. VIEW FEEDBACK (Admin/SPOC) ---
@feedback_bp.route('/view/<event_id>')
@login_required
@role_required(['Admin', 'ClubSPOC', 'SuperAdmin'])
def view_feedback(event_id):
    # Fetch all registrations with feedback
    regs = db.collection('registrations').where('event_id', '==', event_id).stream()
    reviews = []
    total_rating = 0
    count = 0
    
    for r in regs:
        d = r.to_dict()
        if 'feedback' in d:
            fb = d['feedback']
            reviews.append({
                'user': d['lead_name'],
                'rating': fb.get('rating'),
                'comment': fb.get('comments')
            })
            total_rating += fb.get('rating', 0)
            count += 1
            
    avg_rating = round(total_rating / count, 1) if count > 0 else 0
    event = db.collection('events').document(event_id).get().to_dict()
    
    return render_template('feedback/view.html', reviews=reviews, avg=avg_rating, count=count, event=event)