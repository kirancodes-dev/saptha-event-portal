import datetime
import json
import time as _time
from flask import (Blueprint, Response, flash, jsonify,
                   redirect, render_template, request, session, url_for)
from models import db
from utils import login_required, role_required, log_action, safe_int

exams_bp = Blueprint('exams', __name__)

# Global memory queue for real-time SSE proctoring notifications
_proctor_streams = []

def _broadcast_proctor_event(event_id, payload):
    """Pushes a proctoring alert to all connected SSE monitoring clients."""
    msg = f"data: {json.dumps(payload)}\n\n"
    for queue in list(_proctor_streams):
        try:
            queue.append(msg)
        except Exception:
            pass

try:
    from db_adapter import to_uuid
except ImportError:
    to_uuid = lambda x: str(x)

@exams_bp.route('/exams/<event_id>', methods=['GET'])
@login_required
def exam_interface(event_id):
    """Renders the timed online assessment interface for a registered student."""
    user_email = session.get('user_id') or session.get('user_email')
    
    # 1. Fetch Event & Registration
    event_ref = db.collection('events').document(event_id)
    event_doc = event_ref.get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect(url_for('participant.dashboard'))
        
    event_data = event_doc.to_dict()
    event_data['id'] = event_doc.id

    # Verify student registration
    all_regs = list(db.collection('registrations').stream())
    target_event_ids = {str(event_id), str(to_uuid(event_id))}
    reg_docs = [
        r for r in all_regs
        if (r.to_dict().get('lead_email') == user_email or r.to_dict().get('student_email') == user_email)
        and str(r.to_dict().get('event_id')) in target_event_ids
    ]
    if not reg_docs:
        flash("You are not registered for this assessment.", "warning")
        return redirect(url_for('public.event_details', event_id=event_id))

    reg_doc = reg_docs[0]
    reg_data = reg_doc.to_dict()
    reg_id = reg_doc.id

    # Check existing submission/attempt state
    sub_docs = list(db.collection('exam_attempts')
                    .where('event_id', '==', event_id)
                    .where('user_email', '==', user_email)
                    .stream())
    
    attempt_id = None
    started_at = None
    if sub_docs:
        attempt_data = sub_docs[0].to_dict()
        if attempt_data.get('status') in ['submitted', 'force_submitted']:
            flash("You have already completed this assessment.", "info")
            return redirect(url_for('participant.dashboard'))
        attempt_id = sub_docs[0].id
        started_at = attempt_data.get('started_at')
    else:
        # Create new active attempt session
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        new_attempt_ref = db.collection('exam_attempts').add({
            'event_id': event_id,
            'user_email': user_email,
            'registration_id': reg_id,
            'started_at': started_at,
            'status': 'active',
            'violations': [],
            'answers': {},
            'score': 0.0
        })
        attempt_id = new_attempt_ref[1].id if isinstance(new_attempt_ref, tuple) else getattr(new_attempt_ref, 'id', 'att_1')

    # Load Quiz Questions (either from event form_schema or default assessment questions)
    form_schema = event_data.get('form_schema', {})
    questions = form_schema.get('quiz_questions', [])
    if not questions:
        # Fallback default questions if not configured
        questions = [
            {
                "id": "q1",
                "text": "What is the time complexity of building a heap from an unsorted array of n elements?",
                "type": "mcq",
                "options": ["O(N log N)", "O(N)", "O(N^2)", "O(log N)"],
                "points": 5
            },
            {
                "id": "q2",
                "text": "Which of the following database isolation levels prevents non-repeatable reads?",
                "type": "mcq",
                "options": ["Read Committed", "Read Uncommitted", "Repeatable Read", "None of the above"],
                "points": 5
            },
            {
                "id": "q3",
                "text": "Briefly describe how ACID properties ensure data reliability in distributed transactions.",
                "type": "subjective",
                "points": 10
            }
        ]

    duration_minutes = event_data.get('duration_minutes', 30)

    return render_template('public/exam_interface.html',
                           event=event_data,
                           questions=questions,
                           duration_minutes=duration_minutes,
                           attempt_id=attempt_id,
                           user_email=user_email)

@exams_bp.route('/exams/submit/<event_id>', methods=['POST'])
@login_required
def submit_exam(event_id):
    """Processes candidate exam answers, auto-scores MCQs, and updates assessment status."""
    user_email = session.get('user_id') or session.get('user_email')
    answers = request.form.to_dict()

    # Locate active attempt
    sub_docs = list(db.collection('exam_attempts')
                    .where('event_id', '==', event_id)
                    .where('user_email', '==', user_email)
                    .stream())
    
    if sub_docs:
        attempt_ref = db.collection('exam_attempts').document(sub_docs[0].id)
        attempt_ref.update({
            'status': 'submitted',
            'answers': answers,
            'submitted_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        })

    log_action(db, "EXAM_SUBMISSION", user_email, f"Completed assessment for event {event_id}")
    flash("Your assessment has been submitted successfully!", "success")
    return redirect(url_for('participant.dashboard'))

@exams_bp.route('/api/proctor/log_violation', methods=['POST'])
@login_required
def log_proctor_violation():
    """Receives anti-cheat violation reports from client proctor.js script."""
    user_email = session.get('user_id') or session.get('user_email')
    data = request.get_json() or {}

    event_id = data.get('event_id')
    violation_type = data.get('violation_type')
    detail = data.get('detail')

    if not event_id or not violation_type:
        return jsonify({'status': 'error', 'message': 'Missing parameters'}), 400

    # Log violation in attempt record
    sub_docs = list(db.collection('exam_attempts')
                    .where('event_id', '==', event_id)
                    .where('user_email', '==', user_email)
                    .stream())

    violation_entry = {
        'type': violation_type,
        'detail': detail,
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    violation_count = 1
    if sub_docs:
        attempt_doc = sub_docs[0]
        attempt_ref = db.collection('exam_attempts').document(attempt_doc.id)
        current_data = attempt_doc.to_dict()
        violations = current_data.get('violations', [])
        violations.append(violation_entry)
        violation_count = len(violations)
        
        attempt_ref.update({'violations': violations})

    # Broadcast to SPOC Real-time Monitoring Room via SSE
    _broadcast_proctor_event(event_id, {
        'type': 'PROCTOR_VIOLATION',
        'event_id': event_id,
        'user_email': user_email,
        'violation_type': violation_type,
        'detail': detail,
        'total_violations': violation_count,
        'timestamp': datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")
    })

    return jsonify({'status': 'ok', 'violations': violation_count})

@exams_bp.route('/spoc/proctor/<event_id>')
@login_required
@role_required('ClubSPOC')
def spoc_proctor_room(event_id):
    """SPOC Real-Time Assessment Control Room & Proctoring Monitor."""
    event_ref = db.collection('events').document(event_id)
    event_doc = event_ref.get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect(url_for('spoc.dashboard'))

    event_data = event_doc.to_dict()
    event_data['id'] = event_doc.id

    # Fetch attempts
    attempts = [doc.to_dict() for doc in db.collection('exam_attempts').where('event_id', '==', event_id).stream()]

    active_candidates = [a for a in attempts if a.get('status') == 'active']
    completed_candidates = [a for a in attempts if a.get('status') in ['submitted', 'force_submitted']]

    return render_template('spoc/proctor_monitor.html',
                           event=event_data,
                           attempts=attempts,
                           active_count=len(active_candidates),
                           completed_count=len(completed_candidates))

@exams_bp.route('/spoc/proctor/stream/<event_id>')
@login_required
@role_required('ClubSPOC')
def proctor_sse_stream(event_id):
    """SSE Stream providing live anti-cheat warning alerts to the SPOC dashboard."""
    def event_generator():
        q = []
        _proctor_streams.append(q)
        try:
            yield "data: {\"type\": \"CONNECTED\"}\n\n"
            while True:
                if q:
                    msg = q.pop(0)
                    yield msg
                _time.sleep(0.5)
        except GeneratorExit:
            if q in _proctor_streams:
                _proctor_streams.remove(q)

    return Response(event_generator(), mimetype='text/event-stream')
