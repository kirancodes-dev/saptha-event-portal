"""
services_live_match.py — scoring a match live, point by point (UPG-351).

Each match being scored has its own document in `live_matches`
(`<event id>__<match id>`), not on the event: two courts can be scored at
once without one overwriting the other. The document keeps the phase (first
half, half time, second half, full time), a pausable clock, and the log of
every point: who scored it, how (a raid, a bonus, a tackle, a super tackle,
an all out, a technical point; or plain points in another sport), and the
player when the scorer picked one.

Every tap carries an id made on the scorer's phone, so a tap sent twice (a
retry on a weak connection) counts once. The scorer's page sends one tap at a
time, and a lock per match keeps one process from interleaving two writes.

Full time saves the score as the match's result in the tournament, which moves
a knockout's winner on (a tie in a knockout needs the winner chosen).

The public scoreboard reads `public_state`, cached for a few seconds, so a
crowd watching one match costs one database read every few seconds.

The logs also give each player's raid and tackle points across the
tournament: the top raiders and defenders, Super 10s and High 5s (UPG-352).

Mistakes are fixed on the scorer's page (UPG-355): any point in the log can be
removed, and a match ended by mistake is reopened (its result is taken back).
Fixtures made again, playoffs undone or a team replaced keep the live records
in step (`forget`, `retarget`).
"""
import datetime
import threading
import time
from typing import Optional

import services_sports

COLLECTION = 'live_matches'
PHASES = ('not_started', 'first_half', 'half_time', 'second_half', 'full_time')
PHASE_NAMES = {'not_started': 'Not started', 'first_half': '1st half', 'half_time': 'Half time',
               'second_half': '2nd half', 'full_time': 'Full time'}
IN_PLAY = ('first_half', 'half_time', 'second_half')
DEFAULT_HALF_MINUTES = 20

# kind → (label, fixed points or None when the scorer picks 1 to 7, what it counts as)
KABADDI_ACTIONS = {
    'raid': ('Raid', None, 'raid'),
    'bonus': ('Bonus', 1, 'raid'),
    'tackle': ('Tackle', 1, 'tackle'),
    'super_tackle': ('Super tackle', 2, 'tackle'),
    'all_out': ('All out', 2, 'extra'),
    'technical': ('Technical point', 1, 'extra'),
}
OTHER_ACTIONS = {'score': ('Score', None, 'score')}
MAX_PICKED_POINTS = 7
KEEP_TAPS = 500
CACHE_SECONDS = 3

_locks: dict = {}
_locks_guard = threading.Lock()
_cache: dict = {}


class LiveMatchError(ValueError):
    pass


def doc_id(event_id: str, match_id: str) -> str:
    return f"{event_id}__{match_id}"


def actions(tournament: dict) -> dict:
    return KABADDI_ACTIONS if services_sports.is_kabaddi(tournament) else OTHER_ACTIONS


def _lock(key):
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _now():
    return time.time()


def _iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _match(tournament: dict, match_id: str) -> dict:
    for m in tournament.get('matches') or []:
        if m.get('id') == match_id:
            return m
    raise LiveMatchError("No such match.")


def get(db, event_id: str, match_id: str) -> Optional[dict]:
    snap = db.collection(COLLECTION).document(doc_id(event_id, match_id)).get()
    return (snap.to_dict() or {}) if snap.exists else None


def _save(db, event_id, match_id, doc):
    doc['updated_at'] = _iso()
    db.collection(COLLECTION).document(doc_id(event_id, match_id)).set(doc, merge=False)
    _cache.pop(('state', event_id, match_id), None)
    _cache.pop(('live', event_id), None)
    _cache.pop(('stats', event_id), None)


def _new(event_id, match_id, m, half_minutes):
    return {'event_id': event_id, 'match_id': match_id, 'home': m['home'], 'away': m['away'],
            'phase': 'not_started', 'half_minutes': half_minutes,
            'clock': {'running': False, 'since': None, 'elapsed': 0.0},
            'log': [], 'taps': [], 'result': None}


def open_match(db, event_id: str, event: dict, match_id: str) -> dict:
    """The match's live document, made when first opened."""
    t = event.get('tournament') or {}
    m = _match(t, match_id)
    if not m.get('home') or not m.get('away'):
        raise LiveMatchError("Both teams must be known before the match is scored.")
    doc = get(db, event_id, match_id)
    if doc is None:
        if m.get('status') == 'bye':
            raise LiveMatchError("A bye isn't played.")
        if m.get('status') == 'played':
            raise LiveMatchError("This match already has a result. Correct it on the tournament page.")
        doc = _new(event_id, match_id, m, DEFAULT_HALF_MINUTES)
        with _lock(doc_id(event_id, match_id)):
            if get(db, event_id, match_id) is None:
                _save(db, event_id, match_id, doc)
            doc = get(db, event_id, match_id)
    return doc


def clock_seconds(doc: dict, now: float = None) -> int:
    c = doc.get('clock') or {}
    elapsed = float(c.get('elapsed') or 0)
    if c.get('running') and c.get('since'):
        elapsed += max(0.0, (now or _now()) - float(c['since']))
    return int(elapsed)


def _half(doc):
    return 2 if doc.get('phase') in ('second_half', 'full_time') else 1


def score(doc: dict) -> dict:
    """Each side's total, its halves, and its raid, tackle and extra points."""
    out = {side: {'total': 0, 'halves': [0, 0], 'raid': 0, 'tackle': 0, 'extra': 0, 'score': 0}
           for side in ('home', 'away')}
    for e in doc.get('log') or []:
        side = out[e['team']]
        side['total'] += e['points']
        side['halves'][int(e.get('half') or 1) - 1] += e['points']
        side[e.get('counts', 'score')] = side.get(e.get('counts', 'score'), 0) + e['points']
    return out


def _change(db, event_id, match_id, tap, fn):
    """Apply `fn(doc)` to the match's document once per tap id."""
    tap = str(tap or '').strip()[:64]
    if not tap:
        raise LiveMatchError("Each tap needs an id.")
    with _lock(doc_id(event_id, match_id)):
        doc = get(db, event_id, match_id)
        if doc is None:
            raise LiveMatchError("Open the match's scoring page first.")
        if tap in (doc.get('taps') or []):
            return doc                       # sent twice: counted once
        fn(doc)
        doc['taps'] = ((doc.get('taps') or []) + [tap])[-KEEP_TAPS:]
        _save(db, event_id, match_id, doc)
        return doc


def add_point(db, event_id: str, event: dict, match_id: str, tap: str, team: str, kind: str,
              points=None, player: str = '', by: str = '') -> dict:
    """One scoring action for `team` ('home' or 'away')."""
    if team not in ('home', 'away'):
        raise LiveMatchError("Choose the team that scored.")
    known = actions(event.get('tournament') or {})
    if kind not in known:
        raise LiveMatchError("That isn't a scoring action here.")
    label, fixed, counts = known[kind]
    if fixed is None:
        try:
            fixed = int(points)
        except (TypeError, ValueError):
            fixed = 0
        if not 1 <= fixed <= MAX_PICKED_POINTS:
            raise LiveMatchError(f"Points must be 1 to {MAX_PICKED_POINTS}.")

    def apply(doc):
        if doc.get('phase') not in ('first_half', 'second_half'):
            raise LiveMatchError("Points are scored during a half. Start the half first.")
        squad = players(event, doc[team]) if player else []
        doc['log'].append({'id': tap, 'team': team, 'kind': kind, 'label': label, 'points': fixed,
                           'counts': counts, 'player': player if player in squad else '',
                           'half': _half(doc), 'clock': clock_seconds(doc), 'at': _iso(), 'by': by})
    return _change(db, event_id, match_id, tap, apply)


def undo(db, event_id: str, match_id: str, tap: str) -> dict:
    """Take back the last point."""
    def apply(doc):
        if doc.get('phase') == 'full_time':
            raise LiveMatchError("The match is over; correct the result on the tournament page.")
        if not doc.get('log'):
            raise LiveMatchError("There's nothing to undo.")
        doc['log'].pop()
    return _change(db, event_id, match_id, tap, apply)


def _stop_clock(doc):
    doc['clock'] = {'running': False, 'since': None, 'elapsed': float(clock_seconds(doc))}


def _start_clock(doc, reset=False):
    elapsed = 0.0 if reset else float(clock_seconds(doc))
    doc['clock'] = {'running': True, 'since': _now(), 'elapsed': elapsed}


def change_phase(db, event_id: str, event: dict, match_id: str, tap: str, action: str, winner: str = '') -> dict:
    """start, pause, resume, half_time, second_half, full_time. Full time saves
    the result to the tournament; a knockout tie needs `winner` (a team id)."""
    def apply(doc):
        phase = doc.get('phase')
        if action == 'start' and phase == 'not_started':
            doc['phase'] = 'first_half'
            _start_clock(doc, reset=True)
        elif action == 'pause' and phase in ('first_half', 'second_half'):
            _stop_clock(doc)
        elif action == 'resume' and phase in ('first_half', 'second_half'):
            if not (doc.get('clock') or {}).get('running'):
                _start_clock(doc)
        elif action == 'half_time' and phase == 'first_half':
            doc['phase'] = 'half_time'
            _stop_clock(doc)
        elif action == 'second_half' and phase == 'half_time':
            doc['phase'] = 'second_half'
            _start_clock(doc, reset=True)
        elif action == 'full_time' and phase == 'second_half':
            totals = score(doc)
            home, away = totals['home']['total'], totals['away']['total']
            try:
                t = services_sports.change(db, event_id, lambda cur, _e: services_sports.record_result(
                    cur, match_id, home, away, winner))
            except services_sports.TournamentError as exc:
                raise LiveMatchError(str(exc))
            played = _match(t, match_id)
            doc['phase'] = 'full_time'
            _stop_clock(doc)
            doc['result'] = {'home': home, 'away': away, 'winner': played.get('winner')}
        else:
            raise LiveMatchError(f"Can't {action.replace('_', ' ')} now ({PHASE_NAMES.get(phase, phase)}).")
    return _change(db, event_id, match_id, tap, apply)


def remove_point(db, event_id: str, match_id: str, tap: str, entry_id: str) -> dict:
    """Take back one point anywhere in the log (given to the wrong team or
    player, or by mistake), while the match is being played (UPG-355)."""
    def apply(doc):
        if doc.get('phase') == 'full_time':
            raise LiveMatchError("The match is over. Reopen it first to change its points.")
        log = doc.get('log') or []
        keep = [e for e in log if e.get('id') != entry_id]
        if len(keep) == len(log):
            raise LiveMatchError("That point isn't in the log.")
        doc['log'] = keep
    return _change(db, event_id, match_id, tap, apply)


def _reopen(doc):
    doc['phase'] = 'second_half'
    doc['result'] = None
    _stop_clock(doc)


def reopen(db, event_id: str, match_id: str, tap: str) -> dict:
    """Full time was pressed by mistake: the result comes off the fixtures and
    the second half goes on (the clock paused) (UPG-355)."""
    def apply(doc):
        if doc.get('phase') != 'full_time':
            raise LiveMatchError("The match isn't over.")
        try:
            services_sports.change(db, event_id, lambda cur, _e: services_sports.clear_result(cur, match_id)
                                   if _match(cur, match_id).get('status') == 'played' else cur)
        except services_sports.TournamentError as exc:
            raise LiveMatchError(str(exc))
        _reopen(doc)
    return _change(db, event_id, match_id, tap, apply)


def result_cleared(db, event_id: str, match_id: str) -> None:
    """The result was cleared on the tournament page: a match scored live goes
    back to its second half, so it can be finished again."""
    with _lock(doc_id(event_id, match_id)):
        doc = get(db, event_id, match_id)
        if doc and doc.get('phase') == 'full_time':
            _reopen(doc)
            _save(db, event_id, match_id, doc)


def forget(db, event_id: str, match_ids=None) -> int:
    """Delete the live records of these matches (every match when None): the
    fixtures were made again, or the playoffs undone, so the ids mean other
    matches now."""
    count = 0
    for snap in list(db.collection(COLLECTION).where('event_id', '==', event_id).stream()):
        d = snap.to_dict() or {}
        if match_ids is None or d.get('match_id') in match_ids:
            db.collection(COLLECTION).document(snap.id).delete()
            count += 1
    for key in [k for k in _cache if len(k) > 1 and k[1] == event_id]:
        _cache.pop(key, None)
    return count


def has_points(db, event_id: str, match_id: str) -> bool:
    doc = get(db, event_id, match_id)
    return bool(doc and doc.get('log'))


def retarget(db, event_id: str, old_id: str, new_id: str) -> None:
    """A team was replaced in the fixtures: its live records follow."""
    for snap in list(db.collection(COLLECTION).where('event_id', '==', event_id).stream()):
        d = snap.to_dict() or {}
        if old_id in (d.get('home'), d.get('away')):
            for side in ('home', 'away'):
                if d.get(side) == old_id:
                    d[side] = new_id
            _save(db, event_id, d.get('match_id'), d)


def entries(doc: dict, names: dict) -> list:
    """The whole log, newest first, for the scorer to remove any point."""
    return [{'id': e.get('id'), 'text': describe(e, names, doc), 'half': e.get('half')}
            for e in reversed(doc.get('log') or [])]


def players(event: dict, team_id: str) -> list:
    """The squad's names, for the scorer to pick who scored."""
    return list((event.get('_squads') or {}).get(team_id) or [])


def squads(db, event_id: str, team_ids) -> dict:
    """Team id → its players' names: the lead, then the members."""
    out = {}
    for tid in team_ids:
        if not tid:
            continue
        snap = db.collection('registrations').document(tid).get()
        reg = (snap.to_dict() or {}) if snap.exists else {}
        names = []
        for name in [reg.get('lead_name')] + [m.get('name') for m in reg.get('members') or [] if isinstance(m, dict)]:
            name = ' '.join(str(name or '').split())
            if name and name not in names:
                names.append(name)
        out[tid] = names
    return out


def with_squads(db, event_id: str, event: dict, match_id: str) -> dict:
    """The event, with the match's two squads attached for `players`."""
    m = _match(event.get('tournament') or {}, match_id)
    return dict(event, _squads=squads(db, event_id, [m.get('home'), m.get('away')]))


def describe(entry: dict, names: dict, doc: dict) -> str:
    team = names.get(doc.get(entry['team']), entry['team'])
    who = f" · {entry['player']}" if entry.get('player') else ''
    return f"{entry['label']} +{entry['points']} · {team}{who}"


def state(doc: dict, names: dict, last: int = 8) -> dict:
    """What a scoreboard shows: the teams, the score, the phase, the clock, the last actions."""
    s = score(doc)
    return {'phase': doc.get('phase'), 'phase_name': PHASE_NAMES.get(doc.get('phase'), ''),
            'clock': clock_seconds(doc), 'running': bool((doc.get('clock') or {}).get('running')),
            'half_minutes': doc.get('half_minutes') or DEFAULT_HALF_MINUTES,
            'home': {'id': doc.get('home'), 'name': names.get(doc.get('home'), ''), **s['home']},
            'away': {'id': doc.get('away'), 'name': names.get(doc.get('away'), ''), **s['away']},
            'result': doc.get('result'),
            'recent': [describe(e, names, doc) for e in reversed((doc.get('log') or [])[-last:])],
            'updated_at': doc.get('updated_at')}


def public_state(db, event_id: str, match_id: str) -> Optional[dict]:
    """state() for the public scoreboard, read at most once every few seconds."""
    key = ('state', event_id, match_id)
    hit = _cache.get(key)
    if hit and hit[0] > _now():
        return hit[1]
    doc = get(db, event_id, match_id)
    if doc is None:
        value = None
    else:
        snap = db.collection('events').document(event_id).get()
        names = services_sports.names((snap.to_dict() or {}).get('tournament') or {}) if snap.exists else {}
        value = state(doc, names)
    _cache[key] = (_now() + CACHE_SECONDS, value)
    return value


def live_matches(db, event_id: str) -> dict:
    """Match id → phase, for the event's matches being played now (cached a few seconds)."""
    key = ('live', event_id)
    hit = _cache.get(key)
    if hit and hit[0] > _now():
        return hit[1]
    value = {}
    for snap in db.collection(COLLECTION).where('event_id', '==', event_id).stream():
        d = snap.to_dict() or {}
        if d.get('phase') in IN_PLAY:
            value[d.get('match_id')] = d['phase']
    _cache[key] = (_now() + CACHE_SECONDS, value)
    return value


# ── Player stats (UPG-352) ─────────────────────────────────────────────────
SUPER_10 = 10      # raid points in one match
HIGH_5 = 5         # tackle points in one match
STATS_SECONDS = 15


def _match_players(doc: dict) -> dict:
    """(team side, player) → {'raid', 'tackle'} for one match's log."""
    out = {}
    for e in doc.get('log') or []:
        if not e.get('player') or e.get('counts') not in ('raid', 'tackle'):
            continue
        row = out.setdefault((doc.get(e['team']), e['player']), {'raid': 0, 'tackle': 0})
        row[e['counts']] += e['points']
    return out


def player_stats(docs, names: dict) -> list:
    """Each player's raid points, tackle points, total, matches, Super 10s and
    High 5s across the given live matches; best total first."""
    rows = {}
    for doc in docs:
        for (team, player), pts in _match_players(doc).items():
            row = rows.setdefault((team, player), {'player': player, 'team_id': team, 'team': names.get(team, ''),
                                                   'raid': 0, 'tackle': 0, 'matches': 0, 'super_10': 0,
                                                   'high_5': 0})
            row['raid'] += pts['raid']
            row['tackle'] += pts['tackle']
            row['matches'] += 1
            row['super_10'] += pts['raid'] >= SUPER_10
            row['high_5'] += pts['tackle'] >= HIGH_5
    for row in rows.values():
        row['total'] = row['raid'] + row['tackle']
    return sorted(rows.values(), key=lambda r: (-r['total'], r['player'].lower()))


def top(stats: list, kind: str, n: int = 5) -> list:
    """The top raiders ('raid') or defenders ('tackle'), with at least a point."""
    return sorted([r for r in stats if r[kind] > 0], key=lambda r: (-r[kind], r['player'].lower()))[:n]


def event_stats(db, event_id: str, names: dict) -> list:
    """player_stats over every match of the event scored live (cached a little)."""
    key = ('stats', event_id)
    hit = _cache.get(key)
    if hit and hit[0] > _now():
        return hit[1]
    docs = [snap.to_dict() or {} for snap in db.collection(COLLECTION).where('event_id', '==', event_id).stream()]
    value = player_stats(docs, names)
    _cache[key] = (_now() + STATS_SECONDS, value)
    return value
