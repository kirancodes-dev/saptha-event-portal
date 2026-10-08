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

from flask import Blueprint, Response, abort, jsonify, redirect, render_template, session
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


# ── One response per person (UPG-05) ───────────────────────────────────────
# Each attendee's response is its own document, so a team's members each
# answer once. The lead's is also kept on the registration (`feedback`),
# where the certificate rule and older responses look for it.
RESPONSES = 'feedback_responses'


def response_id(event_id, reg_id, email):
    return f"{event_id}:{reg_id}:{(email or '').lower()}"


def has_responded(event_id, reg_id, email, reg=None):
    if db.collection(RESPONSES).document(response_id(event_id, reg_id, email)).get().exists:
        return True
    reg = reg or {}
    return (reg.get('lead_email') or '').lower() == (email or '').lower() and bool(reg.get('feedback'))


def event_responses(event_id):
    """Every response for the event: one per person, plus responses stored
    only on a registration before UPG-05."""
    responses = [d.to_dict() for d in db.collection(RESPONSES).where('event_id', '==', str(event_id)).stream()]
    answered = {(r.get('reg_id'), (r.get('email') or '').lower()) for r in responses}
    for doc in db.collection('registrations').where(filter=_ff('event_id', '==', event_id)).stream():
        reg = doc.to_dict() or {}
        fb = reg.get('feedback')
        lead = (reg.get('lead_email') or '').lower()
        if fb and (reg.get('reg_id') or doc.id, lead) not in answered and (doc.id, lead) not in answered:
            responses.append(dict(fb, reg_id=reg.get('reg_id') or doc.id, email=lead, name=reg.get('lead_name', ''),
                                  team=reg.get('team_name', ''), submitted_at=str(fb.get('timestamp', ''))))
    return responses


def _event_or_abort(event_id, permission):
    from services_permission import can
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = dict(doc.to_dict() or {}, id=event_id)
    if not can(session, permission, event, db=db):
        abort(403)
    return event


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
    """Full analytics dashboard for event feedback: the event's own staff only (UPG-05)."""
    event       = _event_or_abort(event_id, 'view_analytics')
    reviews     = []
    total       = 0
    tag_counter = collections.Counter()
    words       = collections.Counter()

    for fb in event_responses(event_id):
        rating = fb.get('rating', 0)
        total += rating
        reviews.append({
            'user':    fb.get('name') or 'Anonymous',
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
    _event_or_abort(event_id, 'view_analytics')
    reviews      = []
    total_rating = 0
    tag_counter  = collections.Counter()

    for fb in event_responses(event_id):
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


@feedback_bp.route('/export/<event_id>')
@login_required
def export_feedback(event_id):
    """One CSV row per response, for those who may export the event's data (UPG-05)."""
    import services_export
    event = _event_or_abort(event_id, 'export_data')
    columns = ['Submitted At', 'Name', 'Email', 'Team', 'Rating', 'Sentiment', 'Tags', 'Comments']
    rows = [[r.get('submitted_at', ''), r.get('name', ''), r.get('email', ''), r.get('team', ''), r.get('rating', ''),
             r.get('sentiment', ''), '; '.join(r.get('tags') or []), r.get('comments', '')]
            for r in sorted(event_responses(event_id), key=lambda r: str(r.get('submitted_at', '')))]
    name = ''.join(c if c.isalnum() else '_' for c in str(event.get('title', 'Event'))).strip('_') or 'Event'
    return Response(services_export.to_csv(rows, columns), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={name}_Feedback.csv'})
