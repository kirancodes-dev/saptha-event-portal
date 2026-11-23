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
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for

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
    _fresh(event_id)
    if audit:
        log_action(db, audit[0], f"{session.get('user_id')} {audit[1]} ({event_id})")
    if done:
        flash(done, "success")
    return t


def _fresh(event_id):
    """A change on this instance shows on its big screen at the next ask."""
    import services_live_match as live
    live._cache.pop(('screen', event_id), None)


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
                           bracket=services_sports.bracket(t) if t else {},
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
    tiebreak = request.form.get('rules') == 'pkl12'       # PKL Season 12 (UPG-396)
    if tiebreak:
        points = dict(services_sports.PKL12_POINTS)
    scoring = 'pkl' if request.form.get('scoring') == 'pkl' else ''   # PKL mode (UPG-397)
    teams = services_sports.confirmed_teams(db, event_id)
    pools = None
    if request.form.get('pools') == 'two':            # UPG-381: each team's pool and seed
        pools = {x['id']: (request.form.get(f"pool_{x['id']}", ''), _int(request.form.get(f"seed_{x['id']}"), 0))
                 for x in teams}
    old_logos = services_sports.logos(event.get('tournament') or {})
    def made(_cur, _e):
        new = services_sports.generate(
            teams, request.form.get('format', ''), points,
            third_place=request.form.get('third_place') == 'yes', sport=defaults['sport'],
            legs=_int(request.form.get('legs'), 1), pools=pools, cross=request.form.get('cross') == 'yes',
            tiebreak=tiebreak)
        if scoring:
            new['scoring'] = scoring
        return new
    t = _save(event_id, made, None)
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
    tiebreak = None
    if request.form.get('tb_way') in services_sports.TIEBREAK_WAYS:      # how a tie was decided (UPG-396)
        tb_home, tb_away = _int(request.form.get('tb_home'), -1), _int(request.form.get('tb_away'), -1)
        tiebreak = {'decided': request.form['tb_way'], 'home': tb_home if tb_home >= 0 else None,
                    'away': tb_away if tb_away >= 0 else None}
    if _save(event_id, lambda cur, _e: services_sports.record_result(cur, match_id, home, away,
                                                                     request.form.get('winner', ''), tiebreak),
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


@sports_bp.route('/<event_id>/schedule/all', methods=['POST'])
@login_required
def schedule_all(event_id):
    """Every match's date, time and venue from one table, one Save (UPG-443)."""
    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event'):
        abort(403)
    ids = {m['id'] for m in (event.get('tournament') or {}).get('matches') or []}
    rows = {mid: (request.form.get(f'date-{mid}', ''), request.form.get(f'time-{mid}', ''),
                  request.form.get(f'venue-{mid}', ''))
            for mid in ids if f'date-{mid}' in request.form}
    if _save(event_id, lambda cur, _e: services_sports.update_schedules(cur, rows),
             f"Dates saved for {len(rows)} match{'' if len(rows) == 1 else 'es'}.") is not None:
        log_action(db, "TOURNAMENT_SCHEDULE", f"{session.get('user_id')} set the dates of {len(rows)} matches of {event_id}")
    return _back(event_id, 'match-dates')


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
@sports_bp.route('/<event_id>/match/<match_id>/postpone', methods=['POST'])
@login_required
def postpone(event_id, match_id):
    """Postpone a match, or put it back on (UPG-394): the SPOC or a coordinator."""
    import services_sports
    if not _allowed(_event(event_id), 'edit_event', 'manage_registrations'):
        abort(403)
    on = request.form.get('action') != 'resume'
    _save(event_id, lambda cur, _e: services_sports.postpone(cur, match_id, on),
          "Match postponed: it keeps its number and plays when you start it." if on else "The match is back on.",
          match_id, ("MATCH_POSTPONED" if on else "MATCH_RESUMED",
                     f"{'postponed' if on else 'put back on'} {match_id}"))
    return _back(event_id, match_id)


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
    tiebreak = request.form.get('tiebreak') == 'yes' if 'tiebreak_field' in request.form else None
    if request.form.get('rules') == 'pkl12':                # the PKL Season 12 preset (UPG-396)
        points, tiebreak = dict(services_sports.PKL12_POINTS), True
    _save(event_id, lambda cur, _e: services_sports.set_points(cur, points, tiebreak),
          "Points rule saved; the table is worked out again.", 'standings',
          ("TOURNAMENT_POINTS", f"set the points to {points}"))
    return _back(event_id, 'standings')


@sports_bp.route('/<event_id>/scoring', methods=['POST'])
@login_required
def scoring_mode(event_id):
    """PKL mode on or off (UPG-397): matches opened for live scoring after this
    are scored raid by raid; a match already being scored keeps its way."""
    import services_sports
    if not _allowed(_event(event_id), 'edit_event'):
        abort(403)
    on = request.form.get('scoring') == 'pkl'

    def fn(cur, _e):
        if not services_sports.is_kabaddi(cur):
            raise services_sports.TournamentError("PKL mode is for a kabaddi tournament.")
        new = dict(cur)
        if on:
            new['scoring'] = 'pkl'
        else:
            new.pop('scoring', None)
        return new
    _save(event_id, fn, "PKL mode is on: matches opened for scoring from now are scored raid by raid."
          if on else "PKL mode is off: matches opened from now are scored point by point.", 'scoring',
          ("TOURNAMENT_SCORING", f"turned PKL mode {'on' if on else 'off'}"))
    return _back(event_id, 'scoring')


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


@sports_bp.route('/<event_id>/schedule.xlsx')
@login_required
def schedule_excel(event_id):
    """The same fixture list as an Excel file (UPG-391)."""
    import io

    from flask import Response
    from openpyxl import Workbook

    import services_sports
    event = _event(event_id)
    if not _allowed(event, 'edit_event'):
        abort(403)
    book = Workbook()
    sheet = book.active
    sheet.title = 'Fixtures'
    sheet.append(list(services_sports.SCHEDULE_COLUMNS))
    for row in services_sports.schedule_rows(event.get('tournament') or {}):
        sheet.append(row)
    for col, width in zip('ABCDEFG', (8, 22, 24, 24, 12, 8, 20)):
        sheet.column_dimensions[col].width = width
    out = io.BytesIO()
    book.save(out)
    return Response(out.getvalue(), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="fixtures-{event_id}.xlsx"'})


@sports_bp.route('/<event_id>/schedule/upload', methods=['POST'])
@login_required
def schedule_upload(event_id):
    """The fixture sheet back, CSV or Excel: each match's teams, date, time and
    venue (UPG-385, UPG-391)."""
    import services_sports
    if not _allowed(_event(event_id), 'edit_event'):
        abort(403)
    upload = request.files.get('file')
    if not upload or not upload.filename:
        flash("Choose the fixture sheet to upload.", "warning")
        return _back(event_id, 'schedule')
    raw = upload.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        flash("That file is too large for a fixture sheet.", "warning")
        return _back(event_id, 'schedule')
    try:
        rows = services_sports.read_sheet(raw, upload.filename)
    except services_sports.TournamentError as exc:
        flash(str(exc), "warning")
        return _back(event_id, 'schedule')
    if not rows:
        flash("The file needs a Match column (M-01, M-02, …). Download the fixture sheet and fill that in.", "warning")
        return _back(event_id, 'schedule')
    count, skipped = {}, []

    def fn(cur, _e):
        skipped.clear()
        new, count['n'] = services_sports.apply_schedule(cur, rows, skipped)
        return new
    if _save(event_id, fn, None, 'schedule', ("TOURNAMENT_SCHEDULE", "uploaded the fixture sheet")) is not None:
        msg = f"Schedule saved: {count['n']} match{'' if count['n'] == 1 else 'es'} changed."
        if skipped:
            msg += (f" {', '.join(skipped)} will be made by Make the playoffs; set {'its' if len(skipped) == 1 else 'their'}"
                    " date and venue after that.")
        flash(msg, "success")
    return _back(event_id, 'schedule')


@sports_bp.route('/<event_id>/team/<team_id>/logo', methods=['POST'])
@login_required
def team_logo(event_id, team_id):
    import services_sports
    if not _allowed(_event(event_id), 'edit_event'):
        abort(403)
    url = ''
    if request.form.get('action') != 'remove':
        upload = request.files.get('logo')
        if not upload or not upload.filename:
            flash("Choose a logo to upload.", "warning")
            return _back(event_id, 'teams')
        try:
            url = services_sports.store_logo(event_id, upload.read(services_sports.LOGO_MAX_BYTES + 1))
        except services_sports.TournamentError as exc:
            flash(str(exc), "warning")
            return _back(event_id, 'teams')
    _save(event_id, lambda cur, _e: services_sports.set_logo(cur, team_id, url),
          "Logo saved." if url else "Logo removed.", 'teams', ("TEAM_LOGO", f"{'set' if url else 'removed'} the logo of {team_id}"))
    return _back(event_id, 'teams')


@sports_bp.route('/<event_id>/jerseys', methods=['GET', 'POST'])
@login_required
def jerseys(event_id):
    """Every team's jersey numbers on one page, saved at once (UPG-461)."""
    import services_jerseys
    event = _event(event_id)
    if not _allowed(event, 'edit_event', 'manage_registrations'):
        abort(403)
    values, errors = {}, {}
    if request.method == 'POST':
        done = services_jerseys.save(db, event_id, event, request.form, session.get('user_id', ''))
        if not done['errors']:
            if done['players']:
                log_action(db, "JERSEYS_EDITED", f"{session.get('user_id')} changed {done['players']} jersey "
                                                 f"number(s) of {', '.join(done['teams'])} ({event_id})")
                text = (f"Saved {done['players']} jersey number{'s' if done['players'] != 1 else ''}: "
                        f"{', '.join(done['teams'])}.")
                if done['lineups']:
                    text += f" {done['lineups']} match line-up{'s' if done['lineups'] != 1 else ''} updated too."
                if done['shared']:
                    text += f" Note: {'; '.join(done['shared'])}."
                flash(text, 'success')
            else:
                flash("Nothing was changed.", 'info')
            return redirect(f'/tournament/{event_id}/jerseys')
        flash("A jersey number is a whole number from 0 to 999; nothing was saved.", 'danger')
        values, errors = done['values'], done['errors']
    return render_template('spoc/jerseys.html', event=event, teams=services_jerseys.sheet(db, event_id, event),
                           values=values, errors=errors)


@sports_bp.route('/<event_id>/match/<match_id>/final', methods=['POST'])
@login_required
def final_score(event_id, match_id):
    """The final score typed in when the raids couldn't be scored (UPG-463):
    the match ends with it and every board shows it."""
    import secrets
    import services_live_match as live
    event = _event(event_id)
    if not _allowed(event, 'edit_event', 'manage_registrations'):
        abort(403)
    page = f'/tournament/{event_id}/match/{match_id}/score'
    try:
        live.open_match(db, event_id, event, match_id)
        doc = live.final_score(db, event_id, match_id, 'final-' + secrets.token_hex(6),
                               request.form.get('home'), request.form.get('away'),
                               str(request.form.get('winner') or ''))
    except live.LiveMatchError as exc:
        flash(str(exc), "warning")
        return redirect(page)
    _fresh(event_id)
    live._cache.pop(('state', event_id, match_id), None)
    log_action(db, "MATCH_RESULT", f"{session.get('user_id')} typed the final score of {match_id} of {event_id}: "
               f"{doc['result']['home']}-{doc['result']['away']}")
    flash(f"Final score saved: {doc['result']['home']}–{doc['result']['away']}. The match is over; "
          "the big screen and the public pages show it.", "success")
    return redirect(page)


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
    if live._match(t, match_id).get('postponed'):           # being played after all (UPG-394)
        t = _save(event_id, lambda cur, _e: services_sports.postpone(cur, match_id, False), None) or t
    full = live.with_squads(db, event_id, event, match_id)
    names = services_sports.names(t)
    return render_template('spoc/live_scorer.html', event=event, match=live._match(t, match_id), doc=doc,
                           watched=live.views(db, event_id, match_id),   # UPG-433: seen, not counted
                           state=live.state(doc, names), actions=live.actions(t), names=names,
                           groups=live.button_groups(t),
                           entries=live.entries(doc, names),
                           squads={'home': live.players(full, doc['home']), 'away': live.players(full, doc['away'])},
                           jerseys=_side_jerseys(event_id, doc), logos=services_sports.logos(t),
                           knockout=services_sports.knockout_match(t, live._match(t, match_id)),
                           stage=services_sports.stage_name(live._match(t, match_id)),
                           max_points=live.MAX_PICKED_POINTS, tiebreak=services_sports.tiebreak_on(t), live=live)


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
        elif op == 'state':                           # after a refused tap: the match as it is
            doc = live.get(db, event_id, match_id)
            if doc is None:
                raise live.LiveMatchError("Open the match's scoring page first.")
        elif op == 'raid' or op == 'call':           # PKL mode (UPG-397)
            doc = live.add_event(db, event_id, live.with_squads(db, event_id, event, match_id), match_id, tap,
                                 'raid' if op == 'raid' else str(data.get('kind') or ''), str(data.get('team') or ''),
                                 str(data.get('outcome') or ''), data.get('touches'), _yes(data.get('bonus')),
                                 str(data.get('raider') or ''), str(data.get('tackler') or ''),
                                 _yes(data.get('upheld')), _int(data.get('change'), 0), session.get('user_id', ''),
                                 data.get('touched') if isinstance(data.get('touched'), list) else None,
                                 str(data.get('player') or ''), str(data.get('off') or ''), str(data.get('on') or ''),
                                 reason=str(data.get('reason') or ''), card=str(data.get('card') or ''),
                                 where=str(data.get('where') or ''), bonus_missed=_yes(data.get('bonus_missed')))
        elif op == 'lineup':                          # each team's seven, before the start (UPG-417)
            doc = live.get(db, event_id, match_id) or {}
            sides = {side: data.get(side) for side in ('home', 'away') if isinstance(data.get(side), list)}
            doc = live.set_lineup(db, event_id, live.with_squads(db, event_id, event, match_id), match_id, tap,
                                  sides, _side_jerseys(event_id, doc))
        elif op == 'raider':                          # the raider tapped: the boards show him at once (UPG-420)
            doc = live.raiding_now(db, event_id, match_id, tap, str(data.get('name') or ''))
        elif op == 'raid_clock':                      # the 30-second raid clock: Space (UPG-413)
            doc = live.raid_clock(db, event_id, match_id, tap, str(data.get('action') or ''))
        elif op == 'toss':                            # who won the toss and chose what (UPG-438)
            doc = live.set_toss(db, event_id, match_id, tap, str(data.get('winner') or ''),
                                str(data.get('choice') or ''))
        elif op == 'timings':                         # the half's and the break's minutes (UPG-439)
            doc = live.set_timings(db, event_id, match_id, tap, data.get('half_minutes'), data.get('break_minutes'))
        elif op == 'potm':                            # another player of the match, after full time (UPG-422)
            doc = live.set_potm(db, event_id, live.with_squads(db, event_id, event, match_id), match_id, tap,
                                str(data.get('team') or ''), str(data.get('name') or ''))
        elif op == 'shootout':                        # the tie-breaker (UPG-396)
            doc = live.shootout_raid(db, event_id, match_id, tap, str(data.get('team') or ''),
                                     str(data.get('outcome') or ''), data.get('touches'), _yes(data.get('bonus')))
        elif op == 'decide':
            doc = live.shootout_decide(db, event_id, match_id, tap, str(data.get('way') or ''),
                                       str(data.get('winner') or ''))
        elif op == 'phase':
            doc = live.change_phase(db, event_id, live.with_squads(db, event_id, event, match_id), match_id, tap,
                                    str(data.get('action') or ''),
                                    str(data.get('winner') or ''), str(data.get('first') or ''))
            if doc.get('phase') == 'full_time' and data.get('action') == 'full_time':
                log_action(db, "MATCH_RESULT", f"{session.get('user_id')} ended {match_id} of {event_id} live: "
                           f"{doc['result']['home']}-{doc['result']['away']}")
        else:
            return jsonify(ok=False, error="Unknown action."), 400
    except live.LiveMatchError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    _fresh(event_id)
    live._cache.pop(('state', event_id, match_id), None)
    names = services_sports.names(event.get('tournament') or {})   # names don't change with a tap (UPG-403)
    st = live.state(doc, names)
    return jsonify(ok=True, state=st, entries=live.entries(doc, names),
                   panel=_scorer_panel(event, match_id, doc, st, names))


def _yes(value) -> bool:
    return value is True or str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _scorer_panel(event, match_id, doc, st, names):
    """The PKL-mode raid panel and the tie-breaker, rendered again after each tap."""
    import services_live_match as live
    full = live.with_squads(db, event['id'], event, match_id)
    return render_template('spoc/_pkl_panel.html', event=event, doc=doc, state=st, names=names,
                           squads={'home': live.players(full, doc['home']), 'away': live.players(full, doc['away'])},
                           jerseys=_side_jerseys(event['id'], doc), live=live)


def _side_jerseys(event_id, doc):
    """{'home': {name: jersey number}, 'away': …} for the scorer's player lists (UPG-405)."""
    import services_live_match as live
    numbers = live.jerseys(db, event_id, [doc.get('home'), doc.get('away')])
    return {side: numbers.get(doc.get(side)) or {} for side in ('home', 'away')}


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
    # How many have watched (UPG-433): every opening adds a view, a new browser a device
    seen = None
    try:
        if live.is_person(request.headers.get('User-Agent', '')):
            watched, seen = live.count_view(db, event_id, match_id, request.cookies.get(live.SEEN_COOKIE, ''))
        else:
            watched = live.views(db, event_id, match_id)
    except Exception as exc:   # a count never stops the scoreboard
        current_app.logger.warning("Match view count failed: %s", exc)
        watched = None
    # Each team's players, for its Team details drop-down (UPG-441)
    teams = []
    for side in ('home', 'away'):
        if m.get(side):
            try:
                players_of = live.roster(db, event_id, m[side])
            except Exception:
                current_app.logger.warning("Team details for %s failed", m[side], exc_info=True)
                players_of = []
            teams.append({'side': side, 'id': m[side], 'name': names.get(m[side], 'TBD'), 'players': players_of})
    resp = current_app.make_response(render_template(
        'public/live_match.html', event=event, match=m, names=names, teams=teams,
        logos=services_sports.logos(t),
        stage=services_sports.stage_name(m), state=live.public_state(db, event_id, match_id),
        players=live.with_jerseys(live.player_stats([doc], names),
                                  live.jerseys(db, event_id, [m.get('home'), m.get('away')]))
        if doc else [],
        player_links=_player_links(event_id), watched=watched,
        watching=live.short_count(watched.get('devices', 0)) if watched else ''))   # UPG-440: each phone once
    if seen is not None:
        resp.set_cookie(live.SEEN_COOKIE, seen, max_age=365 * 24 * 3600, httponly=True, samesite='Lax',
                        secure=request.is_secure)
    return resp


@sports_bp.route('/live/<event_id>/<match_id>/sheet.pdf')
def score_sheet(event_id, match_id):
    """The match's score sheet (UPG-419): anyone, once the match has started;
    "Provisional" until full time. No login."""
    import services_live_match as live
    import services_score_sheet
    import services_sports
    event = _event(event_id)
    t = event.get('tournament') or {}
    try:
        m = live._match(t, match_id)
    except live.LiveMatchError:
        abort(404)
    doc = live.get(db, event_id, match_id)
    if not doc or doc.get('phase') == 'not_started':
        abort(404)
    names = services_sports.names(t)
    data = services_score_sheet.sheet_data(event, m, doc, names, live.jerseys(db, event_id, [doc.get('home'),
                                                                                         doc.get('away')]))
    resp = current_app.response_class(services_score_sheet.render(data), mimetype='application/pdf')
    resp.headers['Content-Disposition'] = (f'inline; filename="score-sheet-{services_sports.match_no(m)}.pdf"')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


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
    # The audience picks a pool: its teams, table and matches (UPG-407)
    pools = list(t.get('pools') or [])
    pool = str(request.args.get('pool') or '').strip().upper()
    pool = pool if pool in pools else ''
    leaders = _leaders(event_id, t)
    playing = _live(event_id) if t else {}
    if pool:
        in_pool = {x['id'] for x in t.get('teams') or [] if x.get('pool') == pool}
        leaders['team_players'] = [row for row in leaders.get('team_players') or [] if row[1] in in_pool]
    return render_template(
        'public/tournament_fixtures.html',
        event=event,
        t=t,
        pool_view=pool,
        pool_teams=services_sports.pool_teams(t) if t else [],
        names=services_sports.names(t) if t else {},
        table=services_sports.standings(t) if t else [],
        pool_tables=services_sports.pool_tables(t) if t else [],
        logos=services_sports.logos(t) if t else {},
        champion=services_sports.champion(t) if t else None,
        bracket=services_sports.bracket(t) if t else {},
        sports=services_sports,
        live=playing,
        live_states=_live_states(event_id, playing),
        player_links=_player_links(event_id),
        **leaders,
    )


def _player_links(event_id):
    """The players' profile codes, so their names link to the profiles (UPG-424)."""
    import services_players
    try:
        return services_players.links(db, event_id)
    except Exception:   # a page still shows without the links
        current_app.logger.warning("Player links for %s failed", event_id, exc_info=True)
        return {}


@sports_bp.route('/watch')
def watch():
    """The home page's Watch live picker (UPG-457): to the chosen tournament's
    big screen, which also fits a phone."""
    import re
    event_id = (request.args.get('event') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', event_id):
        return redirect('/')
    return redirect(url_for('sports.screen', event_id=event_id))


@sports_bp.route('/screen/<event_id>')
def screen(event_id):
    """The big screen for a monitor or projector (UPG-392): no login; it
    follows the match being played, the pool tables, the bracket and the top
    players, and refreshes by itself."""
    event = _event(event_id)
    return render_template('public/tournament_screen.html', event=event, **_screen(event),
                           fixtures_url=f"{public_base()}/tournament/fixtures/{event_id}")


SCREEN_SECONDS = 1.5      # one render serves every screen and phone asking in this time (UPG-403)


@sports_bp.route('/screen/<event_id>/body')
def screen_body(event_id):
    """The big screen's contents, fetched every two seconds. Rendered at most
    once a second and a half per event, and only sent when it changed (ETag)."""
    import hashlib
    import services_live_match as live
    key = ('screen', event_id)
    hit = live._cache.get(key)
    if not hit or hit[0] <= live._now():
        event = _event(event_id)
        html = render_template('public/_screen_body.html', event=event, **_screen(event))
        tag = '"' + hashlib.sha1(html.encode('utf-8'), usedforsecurity=False).hexdigest()[:20] + '"'
        hit = (live._now() + SCREEN_SECONDS, tag, html)
        live._cache[key] = hit
    _, tag, html = hit
    if request.headers.get('If-None-Match') == tag:
        resp = current_app.response_class(status=304)
    else:
        resp = current_app.response_class(html, mimetype='text/html')
    resp.headers['ETag'] = tag
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


_qr_cache = {}


def public_base() -> str:
    """The address people open: the institution's public URL, else the trusted
    base address (BASE_URL, or a trusted host this request came in on; never a
    forged Host header). Also the link previews' address (og_sports.html)."""
    import services_institution
    from utils_email import _base_url
    try:
        base = services_institution.profile(db).get('public_url') or ''
    except Exception:
        base = ''
    return (base or _base_url()).rstrip('/')


sports_bp.add_app_template_global(public_base, 'sports_public_base')


def _match_when(m):
    import services_sports
    return services_sports.when(m or {})


sports_bp.add_app_template_filter(_match_when, 'match_when')   # UPG-443: "Sat 28 Nov · 4:30 PM"


def _match_result(m, names, t=None):
    import services_sports
    return services_sports.result_text(m or {}, names or {}, services_sports.is_kabaddi(t) if t else True)


sports_bp.add_app_template_filter(_match_result, 'match_result')   # UPG-456: "Garuda Sena won by 4 points (24–20)"


@sports_bp.route('/screen/<event_id>/qr.svg')
def screen_qr(event_id):
    """The QR code on the big screen (UPG-402): the audience scan it to open
    the fixtures and live scores on their phones. No login."""
    import io
    import qrcode
    import qrcode.image.svg
    _event(event_id)                                  # 404 for an unknown event
    target = f"{public_base()}/tournament/fixtures/{event_id}"
    svg = _qr_cache.get(target)
    if svg is None:
        out = io.BytesIO()
        qrcode.make(target, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2).save(out)
        svg = _qr_cache[target] = out.getvalue()
    resp = current_app.response_class(svg, mimetype='image/svg+xml')
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


def _screen(event):
    import services_live_match as live_match
    import services_sports
    t = event.get('tournament') or {}
    live = _live(event['id']) if t else {}
    try:
        done = live_match.just_finished(db, event['id']) if t else {}
    except Exception:
        done = {}
    boards = []
    for m in t.get('matches') or []:
        if m['id'] in live or m['id'] in done:          # a match just over stays up with who won (UPG-456)
            try:
                state = live_match.public_state(db, event['id'], m['id'])
            except Exception:
                state = None
            boards.append({'match': m, 'state': state})
    if any(b['match']['id'] in live for b in boards):   # a finished match only while no other is live
        boards = [b for b in boards if b['match']['id'] in live]
    watched = None                       # how many watch the live matches' pages (UPG-435)
    if boards:
        try:
            counts = [live_match.views(db, event['id'], b['match']['id']) for b in boards]
            watched = {k: sum(c.get(k, 0) for c in counts) for k in ('views', 'devices')}
            watched['short'] = live_match.short_count(watched['devices'])   # UPG-440: each phone once
        except Exception:
            current_app.logger.warning("View counts for %s failed", event['id'], exc_info=True)
    toss_show = None                     # a toss just made, played once on the screen (UPG-438)
    if t:
        try:
            toss_show = live_match.toss_show(db, event['id'], services_sports.names(t))
        except Exception:
            current_app.logger.warning("Toss for %s failed", event['id'], exc_info=True)
    return dict(watched=watched, toss_show=toss_show, t=t, names=services_sports.names(t) if t else {}, logos=services_sports.logos(t) if t else {},
                pool_tables=services_sports.pool_tables(t) if t else [],
                table=services_sports.standings(t) if t and not t.get('pools') else [],
                bracket=services_sports.bracket(t) if t else {}, champion=services_sports.champion(t) if t else None,
                boards=boards, next_match=services_sports.up_next(t, live) if t else None,
                last_match=services_sports.last_result(t) if t else None, live=live,
                sports=services_sports, **_leaders(event['id'], t))


def _leaders(event_id, t):
    """The top raiders and defenders from the live-scored matches (UPG-352)."""
    import services_live_match as live
    import services_sports
    if not t:
        return {'raiders': [], 'defenders': [], 'team_players': []}
    try:
        stats = live.event_stats(db, event_id, services_sports.names(t))
        stats = live.with_jerseys(stats, live.jerseys(db, event_id, [x['id'] for x in t.get('teams') or []]))
    except Exception:
        stats = []
    return {'raiders': live.top(stats, 'raid'), 'defenders': live.top(stats, 'tackle'),
            'team_players': live.by_team(stats, t)}


def _live(event_id):
    import services_live_match
    try:
        return services_live_match.live_matches(db, event_id)
    except Exception:
        return {}


def _live_states(event_id, playing):
    """The boards of the matches being played (UPG-421), from the same short cache as the match pages."""
    import services_live_match
    return {mid: services_live_match.public_state(db, event_id, mid) for mid in playing or {}}
