"""
services_rounds.py — competitions with qualifying rounds (UPG-149).

A hackathon, quiz or any competition can run in rounds (the wizard's "Number of
rounds", saved as `total_rounds`). The event keeps `active_round`; each team's
registration keeps `current_round`. Judges score the current round's present
teams (routes_judge). Advancing a round, from the SPOC's round panel or the
coordinator's dashboard, goes through `advance()`:

- every team in the round gets its result added to `round_history`
  (round, score, judges, the judges' scores, result) before its scores are
  cleared for the next round, so nothing a judge entered is lost;
- teams go through by top N (everyone tied with the Nth goes through too) or by
  a cut-off on the average judge score, the same score every board shows
  (services_leaderboard.score_of);
- the rest are eliminated with `eliminated_in_round`; a team that was never
  marked present and has no score is eliminated as absent; a present team with
  no score stops the advance unless the organiser chooses to eliminate it;
- the final round can't be advanced (results are published instead), and a form
  posted for a round the event has already left changes nothing;
- each person on an advancing or eliminated team gets one email.
"""
import datetime
import logging

from google.cloud import firestore   # a pinned requirement; the adapter honours its sentinels

from services_leaderboard import score_of

log = logging.getLogger(__name__)

MAX_ROUNDS = 10


def _int(value, default=1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def total_rounds(event: dict) -> int:
    """The event's number of rounds (1 when it never said)."""
    n = _int((event or {}).get('total_rounds'), 1)
    return n if 1 <= n <= MAX_ROUNDS else 1


def round_info(event: dict) -> dict:
    """{'current', 'total', 'is_final', 'multi'} for an event."""
    total = total_rounds(event)
    current = max(_int((event or {}).get('active_round'), 1), 1)
    total = max(total, current)   # an event advanced before `total_rounds` existed
    return {'current': current, 'total': total, 'is_final': current >= total,
            'multi': total > 1}


def _out(reg: dict) -> bool:
    return str(reg.get('status') or '').lower() in ('cancelled', 'refunded')


def round_teams(db, event_id: str, event: dict) -> list:
    """The teams still in the event's current round, with their score:
    [{'id', 'reg', 'score', 'judges', 'present'}]."""
    cur = round_info(event)['current']
    rows = []
    for doc in db.collection('registrations').where('event_id', '==', event_id).stream():
        reg = doc.to_dict() or {}
        if reg.get('is_eliminated') or _out(reg) or _int(reg.get('current_round'), 1) != cur:
            continue
        score, judges = score_of(reg)
        rows.append({'id': doc.id, 'reg': reg, 'score': score, 'judges': judges,
                     'present': reg.get('attendance') == 'Present'})
    return rows


def history(db, event_id: str) -> list:
    """Earlier rounds' results for the round panel:
    [{'round', 'qualified', 'eliminated', 'absent', 'top'}], oldest first."""
    by_round: dict = {}
    for doc in db.collection('registrations').where('event_id', '==', event_id).stream():
        reg = doc.to_dict() or {}
        name = reg.get('team_name') or reg.get('lead_name') or '—'
        for entry in reg.get('round_history') or []:
            if not isinstance(entry, dict):
                continue
            r = by_round.setdefault(_int(entry.get('round'), 1),
                                    {'qualified': 0, 'eliminated': 0, 'absent': 0, 'rows': []})
            result = entry.get('result')
            if result == 'qualified':
                r['qualified'] += 1
            elif result == 'absent':
                r['absent'] += 1
            else:
                r['eliminated'] += 1
            r['rows'].append({'team': name, 'score': entry.get('score'), 'result': result})
    out = []
    for n in sorted(by_round):
        r = by_round[n]
        r['rows'].sort(key=lambda x: (x['score'] is None, -(x['score'] or 0), x['team'].lower()))
        out.append({'round': n, 'qualified': r['qualified'], 'eliminated': r['eliminated'],
                    'absent': r['absent'], 'top': r['rows'][:10]})
    return out


def status_for(event: dict, reg: dict):
    """What a student sees for a multi-round event, or None for a one-round one:
    {'label', 'tone'}."""
    info = round_info(event)
    if not info['multi'] or not reg:
        return None
    if reg.get('is_eliminated'):
        n = _int(reg.get('eliminated_in_round'), _int(reg.get('current_round'), 1))
        return {'label': f"Not qualified after round {n} of {info['total']}", 'tone': 'muted'}
    mine = _int(reg.get('current_round'), 1)
    if mine > 1:
        return {'label': f"Qualified for round {mine} of {info['total']}", 'tone': 'success'}
    return {'label': f"Round {mine} of {info['total']}", 'tone': 'info'}


def _parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def advance(db, *, event_id: str, event: dict, mode: str, top_n=0, cutoff=None,
            expected_round=None, eliminate_unscored: bool = False, actor: str = '') -> dict:
    """Close the current round and open the next. Returns
    {'ok', 'message', 'round', 'advanced': [...], 'eliminated': [...]}; when
    `ok` is False nothing was changed."""
    info = round_info(event)
    cur, nxt = info['current'], info['current'] + 1
    refused = {'ok': False, 'round': cur, 'advanced': [], 'eliminated': []}

    if expected_round not in (None, ''):
        if _int(expected_round, -1) != cur:
            return {**refused, 'message': f"This page was for round {expected_round}, but the event is "
                                          f"now on round {cur}. Nothing changed; reload to see the latest."}
    if info['is_final']:
        return {**refused, 'message': f"Round {cur} is the final round. Publish the results instead."}

    teams = round_teams(db, event_id, event)
    scored = sorted([t for t in teams if t['score'] is not None], key=lambda t: -t['score'])
    present_unscored = [t for t in teams if t['score'] is None and t['present']]
    absent = [t for t in teams if t['score'] is None and not t['present']]

    if not scored:
        return {**refused, 'message': "No team has a score in this round yet. Judges must score before you advance."}
    if present_unscored and not eliminate_unscored:
        return {**refused, 'message': f"{len(present_unscored)} present team(s) have no score yet. Wait for "
                                      "the judges, or tick “eliminate unscored teams”."}

    if mode == 'top_n':
        n = _int(top_n, 0)
        if n <= 0:
            return {**refused, 'message': "Enter how many teams go through (Top N)."}
        mark = scored[min(n, len(scored)) - 1]['score']
        go = [t for t in scored if t['score'] >= mark]   # ties at the cut all go through
    elif mode == 'cutoff':
        mark = _parse_float(cutoff)
        if mark is None or mark < 0:
            return {**refused, 'message': "Enter a score cut-off of 0 or more."}
        go = [t for t in scored if t['score'] >= mark]
    else:
        return {**refused, 'message': "Choose Top N or a score cut-off."}
    if not go:
        return {**refused, 'message': "No team reaches that mark, so nobody would go through. Nothing changed."}

    go_ids = {t['id'] for t in go}
    results = {}
    for t in teams:
        if t['id'] in go_ids:
            results[t['id']] = 'qualified'
        elif t['score'] is None and not t['present']:
            results[t['id']] = 'absent'
        else:
            results[t['id']] = 'eliminated'   # scored below the mark, or present and unscored

    # The event moves first, so a second submit of the same page is refused
    # by the round check above.
    db.collection('events').document(event_id).update({'active_round': nxt, 'scoring_locked': False})
    advanced, eliminated = _apply(db, teams, results, cur, nxt, actor)

    portal = _notify(event, advanced, eliminated, cur, nxt, db=db, event_id=event_id)
    note = f" {len(absent)} absent." if absent else ''
    told = ("Every team sees the result on its hackathon page." if portal
            else "Every team has been emailed.")
    return {'ok': True, 'round': nxt, 'advanced': advanced, 'eliminated': eliminated,
            'message': f"Round {nxt} of {info['total']} started: {len(advanced)} team(s) went through, "
                       f"{len(eliminated)} didn't.{note} {told}"}


def advance_to(db, *, event_id: str, event: dict, go_ids, scores: dict | None = None,
               expected_round=None, actor: str = '', texts: dict | None = None,
               event_fields: dict | None = None) -> dict:
    """Close the current round with a list of teams the organiser chose (the
    hackathon shortlist, UPG-193): those go through, the rest of the round is
    eliminated, with round history and the same notices as `advance`. The
    event gets a round more when it had none left. `scores` is what the
    history records as each team's score (the ranking the choice was made on).
    Returns the same dict as `advance`; when `ok` is False nothing changed."""
    info = round_info(event)
    cur, nxt = info['current'], info['current'] + 1
    refused = {'ok': False, 'round': cur, 'advanced': [], 'eliminated': []}
    if expected_round not in (None, '') and _int(expected_round, -1) != cur:
        return {**refused, 'message': f"This page was for round {expected_round}, but the event is "
                                      f"now on round {cur}. Nothing changed; reload to see the latest."}
    teams = round_teams(db, event_id, event)
    go_ids = {str(i) for i in go_ids or ()}
    if not any(t['id'] in go_ids for t in teams):
        return {**refused, 'message': "Choose at least one team that is still in this round."}
    results = {t['id']: 'qualified' if t['id'] in go_ids else 'eliminated' for t in teams}

    fields = {'active_round': nxt, 'scoring_locked': False, **(event_fields or {})}
    if info['total'] < nxt:
        fields['total_rounds'] = nxt
    db.collection('events').document(event_id).update(fields)
    advanced, eliminated = _apply(db, teams, results, cur, nxt, actor, scores=scores or {}, kind='shortlist')

    portal = _notify(event, advanced, eliminated, cur, nxt, db=db, event_id=event_id, texts=texts)
    told = ("Every team sees the result on its hackathon page." if portal
            else "Every team has been emailed.")
    return {'ok': True, 'round': nxt, 'advanced': advanced, 'eliminated': eliminated,
            'message': f"{len(advanced)} team(s) go through to round {nxt}; {len(eliminated)} didn't. {told}"}


def _apply(db, teams, results, cur, nxt, actor, scores=None, kind=''):
    """Write each team's result: history first, then through or out."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    advanced, eliminated = [], []
    for t in teams:
        reg, result = t['reg'], results[t['id']]
        entry = {'round': cur, 'score': t['score'] if scores is None else scores.get(t['id']),
                 'judges': t['judges'], 'scores': reg.get('scores') or {}, 'result': result,
                 'at': now, 'by': actor}
        if kind:
            entry['kind'] = kind
        past = [h for h in (reg.get('round_history') or []) if isinstance(h, dict)]
        update: dict = {'round_history': past + [entry]}
        if result == 'qualified':
            # DELETE_FIELD, not {}: the SQL adapter keeps scores in their own
            # table, and an empty map would leave the old rows (UPG-151)
            update.update({'current_round': nxt, 'scores': firestore.DELETE_FIELD, 'assigned_room': None,
                           'assigned_judge_email': None, 'assigned_judge_name': None})
            advanced.append(t)
        else:
            update.update({'is_eliminated': True, 'eliminated_in_round': cur})
            eliminated.append(t)
        db.collection('registrations').document(t['id']).update(update)
    return advanced, eliminated


def _notify(event, advanced, eliminated, cur, nxt, db=None, event_id='', texts=None):
    """One email per person on each team (services_recipients); for a
    portal-only event, a portal notice per person and a line on the
    hackathon's updates instead (UPG-195). Returns True when no email went.
    `texts` replaces the portal wording: {'through': (title, message),
    'out': (title, message), 'update': (title, message)}."""
    import services_hackathon
    title = event.get('title', 'Event')
    if db is not None and not services_hackathon.email_allowed(event, 'round'):
        link = f"/hackathon/{event_id}"
        texts = texts or {}
        through = texts.get('through') or (f"Through to round {nxt}: {title}",
                                           f"Your team is through to round {nxt}. Check the hackathon page for what's next.")
        out = texts.get('out') or (f"Round {cur} result: {title}",
                                   f"Your team didn't go through after round {cur}. Thank you for taking part.")
        update = texts.get('update') or (f"Round {cur} results are out",
                                         f"{len(advanced)} team(s) are through to round {nxt}. "
                                         "Your page shows your team's result.")
        for t in advanced:
            services_hackathon.notify(db, {**event, 'id': event_id}, t['reg'], through[0], through[1], link=link)
        for t in eliminated:
            services_hackathon.notify(db, {**event, 'id': event_id}, t['reg'], out[0], out[1], link=link)
        services_hackathon.post_update(db, event_id, event, update[0], update[1], kind='round')
        return True
    from services_recipients import registration_people
    from utils_email import send_advancement_email, send_round_not_qualified_email
    for t in advanced:
        for email, name, _ in registration_people(t['reg']):
            try:
                send_advancement_email(to_email=email, name=name, event_title=title, next_round=nxt)
            except Exception as exc:   # one failed email doesn't stop the round
                log.warning("Advancement email to %s failed: %s", email, exc)
    for t in eliminated:
        absent = t['score'] is None and not t['present']
        for email, name, _ in registration_people(t['reg']):
            try:
                send_round_not_qualified_email(email, name, title, cur, absent=absent)
            except Exception as exc:
                log.warning("Round result email to %s failed: %s", email, exc)


def can_score(event: dict, reg: dict) -> bool:
    """A judge may score only a team that's still in the event's current round."""
    if not reg or reg.get('is_eliminated') or _out(reg):
        return False
    return _int(reg.get('current_round'), 1) == round_info(event)['current']
