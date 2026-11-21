"""
routes_sports.py — running a sports tournament (UPG-13)

/tournament/<event_id> is the staff page: the SPOC (whoever may edit the event)
generates the fixtures from the confirmed teams, as a knockout or a league with
its win/draw/loss points, and edits dates, times and venues; the SPOC or an
assigned coordinator (whoever may manage the event's registrations) enters each
result. The public event page shows fixtures, results and the table, no login
needed (templates/includes/tournament.html). Whoever may publish the event's
results publishes the tournament's places as its result (UPG-342).

Every change is saved through `services_sports.change`, one at a time
(UPG-354). Mistakes are fixed here, without code (UPG-355 to UPG-359): clear a
result, give a walkover, withdraw or bring back a team, rename, replace or add
a team, change a match's teams, change the points rule, undo the playoffs, and
publish corrected results.

A kabaddi premier league (UPG-381 to UPG-386): two pools with seeds, each pair
once or twice (home and away), an inter-pool round, 1st A v 2nd B and 1st B v
2nd A in the semi-finals; the schedule as a file to download, fill in and
upload; a logo for each team.
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


def _back(event_id, anchor=''):
    return redirect(f'/tournament/{event_id}' + (f'#{anchor}' if anchor else ''))


def _save(event_id, fn, done, anchor='', audit=None):
    """Apply one change under the tournament's lock; flash the outcome."""
    import services_sports
    try:
        t = services_sports.change(db, event_id, fn)
    except services_sports.TournamentError as exc:
        flash(str(exc), "warning")
        return None
    if audit:
        log_action(db, audit[0], f"{session.get('user_id')} {audit[1]} ({event_id})")
    if done:
        flash(done, "success")
    return t


def _team(event_id, team_id):
    """A confirmed registration, as a fixtures team."""
    import services_sports
    return next((x for x in services_sports.confirmed_teams(db, event_id) if x['id'] == team_id), None)


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
                           pool_tables=services_sports.pool_tables(t) if t else [],
                           logos=services_sports.logos(t) if t else {},
                           start_pools=_start_pools(t, services_sports.confirmed_teams(db, event_id)),
                           champion=services_sports.champion(t) if t else None,
                           placings=services_sports.placings(t) if t else {},
                           defaults=services_sports.event_defaults(event), sports=services_sports,
                           can_generate=_allowed(event, 'edit_event'),
                           can_publish=_allowed(event, 'publish_results'), live=_live(event_id) if t else {},
                           published=services_sports.published_places(db, event_id)
                           if event.get('results_published') else {},
                           withdrawn=services_sports.withdrawn(t) if t else set(),
                           spare_teams=[x for x in services_sports.confirmed_teams(db, event_id)
                                        if x['id'] not in services_sports.names(t)] if t else [])


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
    teams = services_sports.confirmed_teams(db, event_id)
    pools = None
    if request.form.get('pools') == 'two':            # UPG-381: each team's pool and seed
        pools = {x['id']: (request.form.get(f"pool_{x['id']}", ''), _int(request.form.get(f"seed_{x['id']}"), 0))
                 for x in teams}
    old_logos = services_sports.logos(event.get('tournament') or {})
    t = _save(event_id, lambda _cur, _e: services_sports.generate(
        teams, request.form.get('format', ''), points,
        third_place=request.form.get('third_place') == 'yes', sport=defaults['sport'],
        legs=_int(request.form.get('legs'), 1), pools=pools, cross=request.form.get('cross') == 'yes'), None)
    if t is None:
        return _back(event_id)
    if old_logos:                                     # the teams keep their logos (UPG-386)
        t = services_sports.change(db, event_id, lambda cur, _e: dict(cur, teams=[
            dict(x, logo=old_logos[x['id']]) if x['id'] in old_logos else x for x in cur.get('teams') or []]))
    import services_live_match
    services_live_match.forget(db, event_id)          # the old match ids mean other matches now
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
    home, away = _int(request.form.get('home_score'), -1), _int(request.form.get('away_score'), -1)
    if _save(event_id, lambda cur, _e: services_sports.record_result(cur, match_id, home, away,
                                                                     request.form.get('winner', '')),
             "Result saved.") is not None:
        log_action(db, "MATCH_RESULT", f"{session.get('user_id')} entered {match_id} of {event_id}: "
                   f"{request.form.get('home_score')}-{request.form.get('away_score')}")
    return _back(event_id, match_id)


@sports_bp.route('/<event_id>/match/<match_id>/schedule', methods=['POST'])
@login_required
def schedule(event_id, match_id):
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event'):
        abort(403)
    _save(event_id, lambda cur, _e: services_sports.update_schedule(
        cur, match_id, request.form.get('date', ''), request.form.get('time', ''), request.form.get('venue', '')),
        "Schedule saved.")
    return _back(event_id, match_id)


@sports_bp.route('/<event_id>/playoffs', methods=['POST'])
@login_required
def playoffs(event_id):
    """A league then knockout: the league's top 4 (or 2) play off (UPG-350)."""
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event'):
        abort(403)
    t = _save(event_id, lambda cur, _e: services_sports.make_playoffs(
        cur, _int(request.form.get('size'), 4), request.form.get('third_place') == 'yes'), None)
    if t is None:
        return _back(event_id)
    log_action(db, "TOURNAMENT_PLAYOFFS", f"{session.get('user_id')} made the top-{t['playoffs']['size']} "
               f"playoffs of {event_id}")
    flash("Semi-finals made: 1st A v 2nd B and 1st B v 2nd A." if t.get('pools') and t['playoffs']['size'] == 4
          else f"Playoffs made: the top {t['playoffs']['size']} play off.", "success")
    return redirect(f'/tournament/{event_id}')


# ── Fixing mistakes from the page (UPG-355 to UPG-358) ───────────────────
@sports_bp.route('/<event_id>/match/<match_id>/clear', methods=['POST'])
@login_required
def clear_result(event_id, match_id):
    """Take a result back (and the team it sent on in a knockout)."""
    import services_live_match as live
    import services_sports
    if not _allowed(_event(event_id), 'edit_event', 'manage_registrations'):
        abort(403)
    if _save(event_id, lambda cur, _e: services_sports.clear_result(cur, match_id),
             "Result cleared. The match is to be played (or scored) again.", match_id,
             ("MATCH_RESULT_CLEARED", f"cleared the result of {match_id}")) is not None:
        live.result_cleared(db, event_id, match_id)
    return _back(event_id, match_id)


@sports_bp.route('/<event_id>/match/<match_id>/walkover', methods=['POST'])
@login_required
def walkover(event_id, match_id):
    """A team didn't turn up: the other wins the match without a score."""
    import services_sports
    if not _allowed(_event(event_id), 'edit_event', 'manage_registrations'):
        abort(403)
    winner = request.form.get('winner', '')
    _save(event_id, lambda cur, _e: services_sports.walkover(cur, match_id, winner),
          "Walkover saved.", match_id, ("MATCH_WALKOVER", f"gave {match_id} to {winner} by walkover"))
    return _back(event_id, match_id)


@sports_bp.route('/<event_id>/match/<match_id>/teams', methods=['POST'])
@login_required
def match_teams(event_id, match_id):
    """Change who plays in a match not yet played."""
    import services_live_match as live
    import services_sports
    if not _allowed(_event(event_id), 'edit_event'):
        abort(403)
    if live.has_points(db, event_id, match_id):
        flash("This match is being scored live. Remove its points on the scoring page first.", "warning")
        return _back(event_id, match_id)
    home, away = request.form.get('home', ''), request.form.get('away', '')
    if _save(event_id, lambda cur, _e: services_sports.set_match_teams(cur, match_id, home, away),
             "The match's teams are changed.", match_id,
             ("MATCH_TEAMS_CHANGED", f"set {match_id} to {home or 'TBD'} v {away or 'TBD'}")) is not None:
        live.forget(db, event_id, [match_id])
    return _back(event_id, match_id)


@sports_bp.route('/<event_id>/team/<team_id>/<action>', methods=['POST'])
@login_required
def team_action(event_id, team_id, action):
    """Withdraw, bring back, rename or replace a team in the fixtures."""
    import services_live_match as live
    import services_sports
    if not _allowed(_event(event_id), 'edit_event'):
        abort(403)
    if action == 'withdraw':
        _save(event_id, lambda cur, _e: services_sports.withdraw(cur, team_id),
              "The team is withdrawn: its matches still to play are walkovers to its opponents.", 'teams',
              ("TEAM_WITHDRAWN", f"withdrew {team_id}"))
    elif action == 'reinstate':
        _save(event_id, lambda cur, _e: services_sports.reinstate(cur, team_id),
              "The team is back. Walkovers already given stay: clear any you want played.", 'teams',
              ("TEAM_REINSTATED", f"brought back {team_id}"))
    elif action == 'rename':
        _save(event_id, lambda cur, _e: services_sports.rename_team(cur, team_id, request.form.get('name', '')),
              "Team name saved.", 'teams', ("TEAM_RENAMED", f"renamed {team_id}"))
    elif action == 'replace':
        new = _team(event_id, request.form.get('new_team', ''))
        if _save(event_id, lambda cur, _e: services_sports.replace_team(cur, team_id, new),
                 "The team is replaced everywhere in the fixtures.", 'teams',
                 ("TEAM_REPLACED", f"replaced {team_id} with {(new or {}).get('id')}")) is not None:
            live.retarget(db, event_id, team_id, new['id'])
    else:
        abort(404)
    return _back(event_id, 'teams')


@sports_bp.route('/<event_id>/teams/add', methods=['POST'])
@login_required
def add_team(event_id):
    """A late team joins the league."""
    import services_sports
    if not _allowed(_event(event_id), 'edit_event'):
        abort(403)
    new = _team(event_id, request.form.get('new_team', ''))
    _save(event_id, lambda cur, _e: services_sports.add_team(cur, new),
          "The team is added, with a match against every other team.", 'teams',
          ("TEAM_ADDED", f"added {(new or {}).get('id')} to the league"))
    return _back(event_id, 'teams')


@sports_bp.route('/<event_id>/points', methods=['POST'])
@login_required
def points_rule(event_id):
    """Change the league's points rule; the table follows."""
    import services_sports
    if not _allowed(_event(event_id), 'edit_event'):
        abort(403)
    points = {k: _int(request.form.get(f'points_{k}'), 0) for k in services_sports.DEFAULT_POINTS}
    _save(event_id, lambda cur, _e: services_sports.set_points(cur, points),
          "Points rule saved; the table is worked out again.", 'standings',
          ("TOURNAMENT_POINTS", f"set the points to {points}"))
    return _back(event_id, 'standings')


@sports_bp.route('/<event_id>/playoffs/undo', methods=['POST'])
@login_required
def undo_playoffs(event_id):
    """Take the playoffs away, to correct the league and make them again."""
    import services_live_match as live
    import services_sports
    if not _allowed(_event(event_id), 'edit_event'):
        abort(403)
    gone = services_sports.playoff_ids(_event(event_id).get('tournament') or {})
    if _save(event_id, lambda cur, _e: services_sports.undo_playoffs(cur),
             "Playoffs undone. Correct the league, then make the playoffs again.", '',
             ("TOURNAMENT_PLAYOFFS_UNDONE", "undid the playoffs")) is not None:
        live.forget(db, event_id, gone)
    return _back(event_id)


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


# ── The schedule as a file, and team logos (UPG-385, UPG-386) ────────────
@sports_bp.route('/<event_id>/schedule.csv')
@login_required
def schedule_file(event_id):
    """Every match with its date, time and venue, to fill in and upload back."""
    import csv
    import io

    from flask import Response

    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event'):
        abort(403)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(services_sports.SCHEDULE_COLUMNS)
    writer.writerows(services_sports.schedule_rows(event.get('tournament') or {}))
    return Response('\ufeff' + out.getvalue(), mimetype='text/csv',   # the BOM: Excel reads the names right
                    headers={'Content-Disposition': f'attachment; filename="schedule-{event_id}.csv"'})


@sports_bp.route('/<event_id>/schedule/upload', methods=['POST'])
@login_required
def schedule_upload(event_id):
    import csv
    import io

    import services_sports
    if not _allowed(_event(event_id), 'edit_event'):
        abort(403)
    upload = request.files.get('file')
    if not upload or not upload.filename:
        flash("Choose the schedule file to upload.", "warning")
        return _back(event_id, 'schedule')
    raw = upload.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        flash("That file is too large for a schedule.", "warning")
        return _back(event_id, 'schedule')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or 'match' not in {str(k or '').strip().lower() for k in rows[0]}:
        flash("The file needs a Match column. Download the schedule file and fill that in.", "warning")
        return _back(event_id, 'schedule')
    count = {}

    def fn(cur, _e):
        new, count['n'] = services_sports.apply_schedule(cur, rows)
        return new
    if _save(event_id, fn, None, 'schedule', ("TOURNAMENT_SCHEDULE", "uploaded the schedule")) is not None:
        flash(f"Schedule saved: {count['n']} match{'' if count['n'] == 1 else 'es'} changed.", "success")
    return _back(event_id, 'schedule')


@sports_bp.route('/<event_id>/team/<team_id>/logo', methods=['POST'])
@login_required
def team_logo(event_id, team_id):
    import secrets

    import services_sports
    from utils_storage import upload_file
    if not _allowed(_event(event_id), 'edit_event'):
        abort(403)
    url = ''
    if request.form.get('action') != 'remove':
        upload = request.files.get('logo')
        if not upload or not upload.filename:
            flash("Choose a logo to upload.", "warning")
            return _back(event_id, 'teams')
        try:
            data = services_sports.logo_webp(upload.read(services_sports.LOGO_MAX_BYTES + 1))
        except services_sports.TournamentError as exc:
            flash(str(exc), "warning")
            return _back(event_id, 'teams')
        url = upload_file(data, f'team-logos/{event_id}-{secrets.token_hex(6)}.webp', 'image/webp')
        if not url:
            flash("The logo couldn't be saved. Please try again.", "warning")
            return _back(event_id, 'teams')
        url = url[url.index('/static/uploads/'):] if '/static/uploads/' in url else url
    _save(event_id, lambda cur, _e: services_sports.set_logo(cur, team_id, url),
          "Logo saved." if url else "Logo removed.", 'teams', ("TEAM_LOGO", f"{'set' if url else 'removed'} the logo of {team_id}"))
    return _back(event_id, 'teams')


def _start_pools(t, teams):
    """The generate form's pools: as the fixtures have them, else the first half
    in pool A and the rest in pool B, seeded in registration order."""
    now = {x['id']: x for x in (t or {}).get('teams') or []}
    half = (len(teams) + 1) // 2
    out = []
    for i, x in enumerate(teams):
        had = now.get(x['id']) or {}
        pool = had.get('pool') or ('A' if i < half else 'B')
        out.append({'id': x['id'], 'name': x['name'], 'pool': pool,
                    'seed': had.get('seed') or (i + 1 if i < half else i - half + 1)})
    return out


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
                           entries=live.entries(doc, names),
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
        elif op == 'remove':
            doc = live.remove_point(db, event_id, match_id, tap, str(data.get('entry') or ''))
        elif op == 'reopen':
            doc = live.reopen(db, event_id, match_id, tap)
            log_action(db, "MATCH_RESULT_CLEARED", f"{session.get('user_id')} reopened {match_id} of {event_id}")
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
    return jsonify(ok=True, state=live.state(doc, names), entries=live.entries(doc, names))


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
                           logos=services_sports.logos(t),
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
        pool_tables=services_sports.pool_tables(t) if t else [],
        logos=services_sports.logos(t) if t else {},
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
