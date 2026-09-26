"""
routes_feedback.py  —  Event Feedback System
=============================================
Fixes in this version
  - All .where() → filter=FieldFilter()
  - view_feedback now computes tag frequency for word-cloud display
  - Returns avg per category (organised, venue, content, overall)
  - /feedback/summary/<event_id>  — JSON for analytics chart
"""
import collections

from flask import Blueprint, jsonify, redirect, render_template
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from models import db
from utils import login_required, role_required

feedback_bp = Blueprint('feedback', __name__, url_prefix='/feedback')

COORD_ROLES = ['ClubSPOC', 'Coordinator', 'SuperAdmin', 'Super Admin', 'Admin']


def _ff(f, op, v):
    return FieldFilter(f, op, v)


@feedback_bp.route('/submit/<reg_id>', methods=['GET', 'POST'])
@login_required
def submit_feedback(reg_id):
    """Legacy URL — feedback submission lives at /participant/feedback/<reg_id>."""
    return redirect(f'/participant/feedback/{reg_id}', code=307)


@feedback_bp.route('/view/<event_id>')
@login_required
@role_required(COORD_ROLES)
def view_feedback(event_id):
    """Legacy URL — the feedback report lives at /feedback/analytics/<event_id>."""
    return redirect(f'/feedback/analytics/{event_id}')


@feedback_bp.route('/analytics/<event_id>')
@login_required
@role_required(COORD_ROLES)
def feedback_analytics(event_id):
    """Full analytics dashboard for event feedback."""
    regs        = db.collection('registrations').where(filter=FieldFilter('event_id', '==', event_id)).stream()
    reviews     = []
    total       = 0
    tag_counter = collections.Counter()
    words       = collections.Counter()

    for r in regs:
        d = r.to_dict()
        if 'feedback' not in d:
            continue
        fb = d['feedback']
        rating = fb.get('rating', 0)
        total += rating
        reviews.append({
            'user':    d.get('lead_name', 'Anonymous'),
            'rating':  rating,
            'comment': fb.get('comments', ''),
            'tags':    fb.get('tags', []),
            'sentiment': fb.get('sentiment', 'Neutral'),
        })
        for t in fb.get('tags', []):
            tag_counter[t] += 1
        for w in fb.get('comments', '').lower().split():
            w = w.strip('.,!?":;()[]')
            if len(w) > 3:
                words[w] += 1

    avg         = round(total / len(reviews), 1) if reviews else 0
    dist        = [sum(1 for r in reviews if r['rating'] == s) for s in range(1, 6)]
    promoters   = sum(1 for r in reviews if r['rating'] == 5)
    detractors  = sum(1 for r in reviews if r['rating'] <= 2)
    nps         = round((promoters - detractors) / len(reviews) * 100) if reviews else 0
    event       = db.collection('events').document(event_id).get().to_dict() or {}

    # top words excluding stopwords
    stopwords = {'this','that','was','were','the','and','for','with','have','from','they'}
    top_words = [(w, c) for w, c in words.most_common(20) if w not in stopwords][:12]

    return render_template('feedback/analytics.html',
        event=event, event_id=event_id,
        reviews=reviews, avg=avg, count=len(reviews),
        dist=dist, nps=nps, promoters=promoters, detractors=detractors,
        top_tags=tag_counter.most_common(10), top_words=top_words)


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
