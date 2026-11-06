"""
routes_interact.py — live polls and Q&A during talks (UPG-160).

  /interact/<event_id>          attendees: answer open polls, ask and upvote questions
  /interact/<event_id>/host     the event's check-in staff: run polls, moderate questions
  /interact/<event_id>/screen   full-screen results for the projector (staff)
  /interact/<event_id>/data     its JSON snapshot; /stream the same over SSE

Only attendees checked in to the event take part. Every page and the
projector show text escaped (the projector sets textContent).
"""
import json
import time

from flask import (Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, session,
                   stream_with_context)

import services_interact as live
from models import db
from utils import log_action, login_required

interact_bp = Blueprint('interact', __name__, url_prefix='/interact')


def _event(event_id):
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    return dict(doc.to_dict() or {}, id=event_id)


def _is_host(event) -> bool:
    from services_permission import can
    return bool(session.get('user_id')) and can(session, 'check_in', event, db=db)


def _host_event_or_abort(event_id):
    event = _event(event_id)
    if not _is_host(event):
        abort(403)
    return event


def _me() -> str:
    return (session.get('user_id') or '').strip().lower()


def _back(event_id, host=False):
    return redirect(f"/interact/{event_id}" + ('/host' if host else ''))


# ── Attendees ──────────────────────────────────────────────────────────────

@interact_bp.route('/<event_id>')
@login_required
def attendee_page(event_id):
    import services_sessions
    event = _event(event_id)
    allowed = live.checked_in(db, event_id, _me())
    polls = live.polls_for(event_id, status='open') if allowed else []
    for p in polls:
        p['voted'] = live.has_voted(p['id'], _me())
    return render_template('interact/attendee.html', event=event, allowed=allowed, polls=polls,
                           questions=live.questions_for(event_id) if allowed else [],
                           sessions={s['id']: services_sessions.label(s) for s in services_sessions.sessions_for(event)},
                           is_host=_is_host(event))


def _attendee_or_refuse(event_id):
    if not live.checked_in(db, event_id, _me()):
        flash("Polls and questions are for attendees checked in to this event.", "warning")
        return False
    return True


@interact_bp.route('/poll/<poll_id>/vote', methods=['POST'])
@login_required
def vote(poll_id):
    poll = live.get_poll(poll_id)
    if poll is None:
        abort(404)
    if not live.checked_in(db, poll['event_id'], _me()):
        abort(403)
    try:
        counted = live.vote(poll, _me(), request.form.getlist('choice'))
        flash("Thanks, your answer is in." if counted else "You've already answered this poll.",
              "success" if counted else "info")
    except live.InteractError as exc:
        flash(str(exc), "warning")
    return _back(poll['event_id'])


@interact_bp.route('/<event_id>/questions', methods=['POST'])
@login_required
def ask(event_id):
    event = _event(event_id)
    if not _attendee_or_refuse(event_id):
        abort(403)
    try:
        live.ask(event_id, _me(), request.form.get('text', ''), bool(event.get('qa_moderated')),
                 session_id=(request.form.get('session_id') or '')[:64])
        flash("Question sent; the host will show it." if event.get('qa_moderated') else "Question posted.",
              "success")
    except live.InteractError as exc:
        flash(str(exc), "warning")
    return _back(event_id)


@interact_bp.route('/question/<qid>/upvote', methods=['POST'])
@login_required
def upvote(qid):
    question = live.get_question(qid)
    if question is None:
        abort(404)
    if not live.checked_in(db, question['event_id'], _me()):
        abort(403)
    try:
        if not live.upvote(question, _me()):
            flash("You've already upvoted that question.", "info")
    except live.InteractError as exc:
        flash(str(exc), "warning")
    return _back(question['event_id'])


# ── The host ───────────────────────────────────────────────────────────────

@interact_bp.route('/<event_id>/host')
@login_required
def host_page(event_id):
    import services_sessions
    event = _host_event_or_abort(event_id)
    polls = [dict(p, **live.results(p)) for p in live.polls_for(event_id)]
    return render_template('interact/host.html', event=event, polls=polls,
                           questions=live.questions_for(event_id, statuses=live.QUESTION_STATUSES),
                           sessions=services_sessions.sessions_for(event))


@interact_bp.route('/<event_id>/polls', methods=['POST'])
@login_required
def create_poll(event_id):
    _host_event_or_abort(event_id)
    try:
        options = request.form.get('options', '').splitlines()
        poll_id = live.create_poll(event_id, request.form.get('question', ''), options,
                                   multiple=request.form.get('multiple') == 'on',
                                   session_id=(request.form.get('session_id') or '')[:64])
        log_action(db, "POLL_OPENED", f"Poll {poll_id} on event {event_id}")
        flash("Poll opened.", "success")
    except live.InteractError as exc:
        flash(str(exc), "warning")
    return _back(event_id, host=True)


@interact_bp.route('/poll/<poll_id>/status', methods=['POST'])
@login_required
def poll_status(poll_id):
    poll = live.get_poll(poll_id)
    if poll is None:
        abort(404)
    _host_event_or_abort(poll['event_id'])
    try:
        live.set_poll_status(poll_id, request.form.get('status', ''))
    except live.InteractError as exc:
        flash(str(exc), "warning")
    return _back(poll['event_id'], host=True)


@interact_bp.route('/question/<qid>/status', methods=['POST'])
@login_required
def question_status(qid):
    question = live.get_question(qid)
    if question is None:
        abort(404)
    _host_event_or_abort(question['event_id'])
    try:
        live.set_question_status(qid, request.form.get('status', ''))
    except live.InteractError as exc:
        flash(str(exc), "warning")
    return _back(question['event_id'], host=True)


@interact_bp.route('/<event_id>/settings', methods=['POST'])
@login_required
def settings(event_id):
    _host_event_or_abort(event_id)
    moderated = request.form.get('qa_moderated') == 'on'
    db.collection('events').document(event_id).update({'qa_moderated': moderated})
    flash("Questions now wait for your approval." if moderated else "Questions now show straight away.", "success")
    return _back(event_id, host=True)


# ── The projector ──────────────────────────────────────────────────────────

@interact_bp.route('/<event_id>/screen')
@login_required
def screen(event_id):
    event = _host_event_or_abort(event_id)
    return render_template('interact/screen.html', event=event, snapshot=live.screen_snapshot(event_id))


@interact_bp.route('/<event_id>/data')
@login_required
def data(event_id):
    _host_event_or_abort(event_id)
    return jsonify(live.screen_snapshot(event_id))


@interact_bp.route('/<event_id>/stream')
@login_required
def stream(event_id):
    """The projector's updates every 3 s, as the live leaderboard does
    (routes_live): it ends after 5 minutes and the browser reconnects."""
    _host_event_or_abort(event_id)

    def generate():
        for _ in range(100):
            try:
                yield f"data: {json.dumps(live.screen_snapshot(event_id))}\n\n"
            except Exception:
                yield "data: {\"error\":true}\n\n"
            time.sleep(3)
        yield "event: reconnect\ndata: {}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream',  # type: ignore[arg-type]
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'})
