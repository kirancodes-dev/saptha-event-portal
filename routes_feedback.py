import datetime
from flask import Blueprint, flash, redirect, render_template, request, session
from models import db
from utils import login_required, role_required

feedback_bp = Blueprint('feedback', __name__, url_prefix='/feedback')


@feedback_bp.route('/submit/<reg_id>', methods=['GET', 'POST'])
@login_required
def submit_feedback(reg_id):
    reg_ref = db.collection('registrations').document(reg_id)
    reg     = reg_ref.get()

    if not reg.exists or reg.to_dict().get('lead_email') != session['user_id']:
        flash("Unauthorised access.", "danger")
        return redirect('/participant/dashboard')

    if request.method == 'POST':
        rating   = request.form.get('rating', '0')
        comments = request.form.get('comments', '').strip()

        if not rating.isdigit() or not (1 <= int(rating) <= 5):
            flash("Please select a valid rating (1–5).", "warning")
            return redirect(f'/feedback/submit/{reg_id}')

        reg_ref.update({
            'feedback': {
                'rating':    int(rating),
                'comments':  comments,
                'timestamp': datetime.datetime.utcnow()
            }
        })
        flash("🙏 Thank you for your feedback!", "success")
        return redirect('/participant/dashboard')

    return render_template('feedback/form.html', reg=reg.to_dict(), reg_id=reg_id)


@feedback_bp.route('/view/<event_id>')
@login_required
@role_required(['Admin', 'ClubSPOC', 'SuperAdmin', 'Coordinator', 'Super Admin'])
def view_feedback(event_id):
    regs        = db.collection('registrations').where('event_id', '==', event_id).stream()
    reviews     = []
    total_rating = 0

    for r in regs:
        d = r.to_dict()
        if 'feedback' not in d:
            continue
        fb = d['feedback']
        reviews.append({
            'user':    d.get('lead_name', 'Anonymous'),
            'rating':  fb.get('rating', 0),
            'comment': fb.get('comments', '')
        })
        total_rating += fb.get('rating', 0)

    avg_rating = round(total_rating / len(reviews), 1) if reviews else 0
    event      = db.collection('events').document(event_id).get().to_dict()

    return render_template('feedback/view.html',
                            reviews=reviews,
                            avg=avg_rating,
                            count=len(reviews),
                            event=event)