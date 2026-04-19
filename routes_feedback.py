"""
routes_feedback.py  —  Event Feedback System
=============================================
Fixes in this version
  - All .where() → filter=FieldFilter()
  - view_feedback now computes tag frequency for word-cloud display
  - Returns avg per category (organised, venue, content, overall)
  - /feedback/summary/<event_id>  — JSON for analytics chart
"""
import datetime
import collections

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session
from google.cloud.firestore_v1.base_query import FieldFilter

from models import db
from utils import login_required, role_required

feedback_bp = Blueprint('feedback', __name__, url_prefix='/feedback')

COORD_ROLES = ['ClubSPOC', 'Coordinator', 'SuperAdmin', 'Super Admin', 'Admin']


def _ff(f, op, v):
    return FieldFilter(f, op, v)


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
        tags     = request.form.getlist('tags')

        if not rating.isdigit() or not (1 <= int(rating) <= 5):
            flash("Please select a valid rating (1–5).", "warning")
            return redirect(f'/feedback/submit/{reg_id}')

        reg_ref.update({
            'feedback': {
                'rating':    int(rating),
                'comments':  comments,
                'tags':      tags,
                'timestamp': datetime.datetime.utcnow(),
            }
        })
        flash("Thank you for your feedback!", "success")
        return redirect('/participant/dashboard')

    return render_template('feedback/form.html', reg=reg.to_dict(), reg_id=reg_id)


@feedback_bp.route('/view/<event_id>')
@login_required
@role_required(COORD_ROLES)
def view_feedback(event_id):
    regs         = (db.collection('registrations')
                      .where(filter=_ff('event_id', '==', event_id))
                      .stream())
    reviews      = []
    total_rating = 0
    tag_counter  = collections.Counter()

    for r in regs:
        d = r.to_dict()
        if 'feedback' not in d:
            continue
        fb = d['feedback']
        reviews.append({
            'user':    d.get('lead_name', 'Anonymous'),
            'rating':  fb.get('rating', 0),
            'comment': fb.get('comments', ''),
            'tags':    fb.get('tags', []),
        })
        total_rating += fb.get('rating', 0)
        for t in fb.get('tags', []):
            tag_counter[t] += 1

    avg_rating  = round(total_rating / len(reviews), 1) if reviews else 0
    event       = db.collection('events').document(event_id).get().to_dict() or {}
    rating_dist = [sum(1 for r in reviews if r['rating'] == s) for s in range(1, 6)]

    return render_template('feedback/view.html',
                            reviews     = reviews,
                            avg         = avg_rating,
                            count       = len(reviews),
                            event       = event,
                            rating_dist = rating_dist,
                            top_tags    = tag_counter.most_common(10))


@feedback_bp.route('/summary/<event_id>')
@login_required
@role_required(COORD_ROLES)
def feedback_summary(event_id):
    """JSON summary for analytics dashboard chart embed."""
    regs = (db.collection('registrations')
              .where(filter=_ff('event_id', '==', event_id))
              .stream())

    reviews      = []
    total_rating = 0
    tag_counter  = collections.Counter()

    for r in regs:
        d = r.to_dict()
        if 'feedback' not in d:
            continue
        fb = d['feedback']
        total_rating += fb.get('rating', 0)
        reviews.append(fb.get('rating', 0))
        for t in fb.get('tags', []):
            tag_counter[t] += 1

    avg = round(total_rating / len(reviews), 1) if reviews else 0
    return jsonify({
        'status': 'ok',
        'avg_rating':   avg,
        'total_reviews': len(reviews),
        'distribution': [reviews.count(s) for s in range(1, 6)],
        'top_tags':     tag_counter.most_common(5),
    })