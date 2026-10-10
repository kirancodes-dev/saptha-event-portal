"""
routes_sports.py — running a sports tournament (UPG-13)

/tournament/<event_id> is the staff page: the SPOC (whoever may edit the event)
generates the fixtures from the confirmed teams, as a knockout or a league with
its win/draw/loss points, and edits dates, times and venues; the SPOC or an
assigned coordinator (whoever may manage the event's registrations) enters each
result. The public event page shows fixtures, results and the table, no login
needed (templates/includes/tournament.html).
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, session

from models import db
from utils import log_action, login_required

sports_bp = Blueprint('sports', __name__, url_prefix='/tournament')


def _event(event_id):
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    return dict(doc.to_dict() or {}, id=event_id)


def _allowed(event, *permissions):
    from services_permission import can
    return any(can(session, p, event, db=db) for p in permissions)


def _int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


@sports_bp.route('/<event_id>')
@login_required
def manage(event_id):
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event', 'manage_registrations'):
        abort(403)
    t = event.get('tournament') or {}
    return render_template('spoc/tournament.html', event=event, t=t,
                           teams=services_sports.confirmed_teams(db, event_id),
                           names=services_sports.names(t), table=services_sports.standings(t) if t else [],
                           champion=services_sports.champion(t) if t else None,
                           can_generate=_allowed(event, 'edit_event'))


@sports_bp.route('/<event_id>/generate', methods=['POST'])
@login_required
def generate(event_id):
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event'):
        abort(403)
    if event.get('tournament') and request.form.get('confirm_replace') != 'yes':
        flash("Fixtures exist already. Tick the box to replace them and their results.", "warning")
        return redirect(f'/tournament/{event_id}')
    points = {k: _int(request.form.get(f'points_{k}'), services_sports.DEFAULT_POINTS[k])
              for k in ('win', 'draw', 'loss')}
    try:
        t = services_sports.generate(services_sports.confirmed_teams(db, event_id),
                                     request.form.get('format', ''), points)
    except services_sports.TournamentError as exc:
        flash(str(exc), "warning")
        return redirect(f'/tournament/{event_id}')
    db.collection('events').document(event_id).update({'tournament': t})
    log_action(db, "TOURNAMENT_GENERATED",
               f"{session.get('user_id')} generated a {t['format']} of {len(t['teams'])} teams for {event_id}")
    flash(f"{len(t['matches'])} matches generated for {len(t['teams'])} teams.", "success")
    return redirect(f'/tournament/{event_id}')


@sports_bp.route('/<event_id>/match/<match_id>/result', methods=['POST'])
@login_required
def result(event_id, match_id):
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event', 'manage_registrations'):
        abort(403)
    try:
        t = services_sports.record_result(event.get('tournament') or {}, match_id,
                                          _int(request.form.get('home_score'), -1),
                                          _int(request.form.get('away_score'), -1),
                                          request.form.get('winner', ''))
    except services_sports.TournamentError as exc:
        flash(str(exc), "warning")
        return redirect(f'/tournament/{event_id}')
    db.collection('events').document(event_id).update({'tournament': t})
    log_action(db, "MATCH_RESULT", f"{session.get('user_id')} entered {match_id} of {event_id}: "
               f"{request.form.get('home_score')}-{request.form.get('away_score')}")
    flash("Result saved.", "success")
    return redirect(f'/tournament/{event_id}#{match_id}')


@sports_bp.route('/<event_id>/match/<match_id>/schedule', methods=['POST'])
@login_required
def schedule(event_id, match_id):
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event'):
        abort(403)
    try:
        t = services_sports.update_schedule(event.get('tournament') or {}, match_id, request.form.get('date', ''),
                                            request.form.get('time', ''), request.form.get('venue', ''))
    except services_sports.TournamentError as exc:
        flash(str(exc), "warning")
        return redirect(f'/tournament/{event_id}')
    db.collection('events').document(event_id).update({'tournament': t})
    flash("Schedule saved.", "success")
    return redirect(f'/tournament/{event_id}#{match_id}')


@sports_bp.route('/fixtures/<event_id>')
def fixtures(event_id):
    """Public fixtures, results and standings page — no login required (UPG-13)."""
    import services_sports
    event = _event(event_id)
    t = event.get('tournament') or {}
    return render_template(
        'public/tournament_fixtures.html',
        event=event,
        t=t,
        names=services_sports.names(t) if t else {},
        table=services_sports.standings(t) if t else [],
        champion=services_sports.champion(t) if t else None,
    )
