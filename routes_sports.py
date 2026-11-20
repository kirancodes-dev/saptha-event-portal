"""
routes_sports.py — running a sports tournament (UPG-13)

/tournament/<event_id> is the staff page: the SPOC (whoever may edit the event)
generates the fixtures from the confirmed teams, as a knockout or a league with
its win/draw/loss points, and edits dates, times and venues; the SPOC or an
assigned coordinator (whoever may manage the event's registrations) enters each
result. The public event page shows fixtures, results and the table, no login
needed (templates/includes/tournament.html). Whoever may publish the event's
results publishes the tournament's places as its result (UPG-342).
"""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session

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
                           placings=services_sports.placings(t) if t else {},
                           defaults=services_sports.event_defaults(event), sports=services_sports,
                           can_generate=_allowed(event, 'edit_event'),
                           can_publish=_allowed(event, 'publish_results'), live=_live(event_id) if t else {})


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
    defaults = services_sports.event_defaults(event)
    points = {k: max(0, _int(request.form.get(f'points_{k}'), defaults['points'][k]))
              for k in ('win', 'draw', 'loss', 'close_loss', 'close_margin')}
    try:
        t = services_sports.generate(services_sports.confirmed_teams(db, event_id),
                                     request.form.get('format', ''), points,
                                     third_place=request.form.get('third_place') == 'yes',
                                     sport=defaults['sport'])
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


@sports_bp.route('/<event_id>/playoffs', methods=['POST'])
@login_required
def playoffs(event_id):
    """A league then knockout: the league's top 4 (or 2) play off (UPG-350)."""
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event'):
        abort(403)
    try:
        t = services_sports.make_playoffs(event.get('tournament') or {}, _int(request.form.get('size'), 4),
                                          request.form.get('third_place') == 'yes')
    except services_sports.TournamentError as exc:
        flash(str(exc), "warning")
        return redirect(f'/tournament/{event_id}')
    db.collection('events').document(event_id).update({'tournament': t})
    log_action(db, "TOURNAMENT_PLAYOFFS", f"{session.get('user_id')} made the top-{t['playoffs']['size']} "
               f"playoffs of {event_id}")
    flash(f"Playoffs made: the top {t['playoffs']['size']} play off.", "success")
    return redirect(f'/tournament/{event_id}')


@sports_bp.route('/<event_id>/publish', methods=['POST'])
@login_required
def publish(event_id):
    """The tournament's places become the event's result (UPG-342)."""
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'publish_results'):
        abort(403)
    try:
        for note in services_sports.publish(db, event_id, session.get('user_id', '')):
            flash(note, 'success')
    except services_sports.TournamentError as exc:
        flash(str(exc), 'warning')
    return redirect(f'/tournament/{event_id}')


# ── Live scoring (UPG-351) ────────────────────────────────────────────────
@sports_bp.route('/<event_id>/match/<match_id>/score')
@login_required
def scorer(event_id, match_id):
    """The scorer's page for one match: the SPOC or an assigned coordinator, on a phone."""
    import services_live_match as live
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event', 'manage_registrations'):
        abort(403)
    try:
        doc = live.open_match(db, event_id, event, match_id)
    except live.LiveMatchError as exc:
        flash(str(exc), "warning")
        return redirect(f'/tournament/{event_id}#{match_id}')
    t = event.get('tournament') or {}
    full = live.with_squads(db, event_id, event, match_id)
    names = services_sports.names(t)
    return render_template('spoc/live_scorer.html', event=event, match=live._match(t, match_id), doc=doc,
                           state=live.state(doc, names), actions=live.actions(t), names=names,
                           squads={'home': live.players(full, doc['home']), 'away': live.players(full, doc['away'])},
                           knockout=services_sports.knockout_match(t, live._match(t, match_id)),
                           stage=services_sports.stage_name(live._match(t, match_id)),
                           max_points=live.MAX_PICKED_POINTS)


@sports_bp.route('/<event_id>/match/<match_id>/score', methods=['POST'])
@login_required
def score_tap(event_id, match_id):
    """One tap from the scorer: a point, an undo, or a change of phase. JSON in and out."""
    import services_live_match as live
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event', 'manage_registrations'):
        abort(403)
    data = request.get_json(silent=True) or request.form
    op, tap = data.get('op'), data.get('tap')
    try:
        if op == 'point':
            doc = live.add_point(db, event_id, live.with_squads(db, event_id, event, match_id), match_id, tap,
                                 data.get('team'), data.get('kind'), data.get('points'),
                                 str(data.get('player') or ''), session.get('user_id', ''))
        elif op == 'undo':
            doc = live.undo(db, event_id, match_id, tap)
        elif op == 'phase':
            doc = live.change_phase(db, event_id, event, match_id, tap, str(data.get('action') or ''),
                                    str(data.get('winner') or ''))
            if doc.get('phase') == 'full_time' and data.get('action') == 'full_time':
                log_action(db, "MATCH_RESULT", f"{session.get('user_id')} ended {match_id} of {event_id} live: "
                           f"{doc['result']['home']}-{doc['result']['away']}")
        else:
            return jsonify(ok=False, error="Unknown action."), 400
    except live.LiveMatchError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    names = services_sports.names((_event(event_id).get('tournament') or {}))
    return jsonify(ok=True, state=live.state(doc, names))


@sports_bp.route('/live/<event_id>/<match_id>')
def live_board(event_id, match_id):
    """The public live scoreboard for one match — no login (UPG-351)."""
    import services_live_match as live
    import services_sports
    event = _event(event_id)
    t = event.get('tournament') or {}
    try:
        m = live._match(t, match_id)
    except live.LiveMatchError:
        abort(404)
    names = services_sports.names(t)
    doc = live.get(db, event_id, match_id)
    return render_template('public/live_match.html', event=event, match=m, names=names,
                           stage=services_sports.stage_name(m), state=live.public_state(db, event_id, match_id),
                           players=live.player_stats([doc], names) if doc else [])


@sports_bp.route('/live/<event_id>/<match_id>/state')
def live_state(event_id, match_id):
    """The scoreboard's JSON, polled every few seconds; cached, no login."""
    import services_live_match as live
    value = live.public_state(db, event_id, match_id)
    if value is None:
        return jsonify(ok=False, phase='not_started'), 404
    resp = jsonify(ok=True, state=value)
    resp.headers['Cache-Control'] = f'public, max-age={live.CACHE_SECONDS}'
    return resp


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
        sports=services_sports,
        live=_live(event_id) if t else {},
        **_leaders(event_id, t),
    )


def _leaders(event_id, t):
    """The top raiders and defenders from the live-scored matches (UPG-352)."""
    import services_live_match as live
    import services_sports
    if not t:
        return {'raiders': [], 'defenders': []}
    try:
        stats = live.event_stats(db, event_id, services_sports.names(t))
    except Exception:
        stats = []
    return {'raiders': live.top(stats, 'raid'), 'defenders': live.top(stats, 'tackle')}


def _live(event_id):
    import services_live_match
    try:
        return services_live_match.live_matches(db, event_id)
    except Exception:
        return {}
