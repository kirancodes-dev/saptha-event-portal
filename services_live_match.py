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
PHASES = ('not_started', 'first_half', 'half_time', 'second_half', 'tiebreak', 'full_time')
PHASE_NAMES = {'not_started': 'Not started', 'first_half': '1st half', 'half_time': 'Half time',
               'second_half': '2nd half', 'tiebreak': 'Tie-breaker', 'full_time': 'Full time'}
IN_PLAY = ('first_half', 'half_time', 'second_half', 'tiebreak')
DEFAULT_HALF_MINUTES = 20

# kind → (label, fixed points or None when the scorer picks 1 to 7, what it counts as)
KABADDI_ACTIONS = {
    'raid': ('Raid', None, 'raid'),
    'bonus': ('Bonus', 1, 'raid'),
    'tackle': ('Tackle', 1, 'tackle'),
    'super_tackle': ('Super tackle', 2, 'tackle'),
    'all_out': ('All out', 2, 'extra'),
    'technical': ('Technical point', 1, 'extra'),
    # A player of the other team stepped out of the court; a do-or-die raid came back empty (UPG-388)
    'out_of_bounds': ('Out of bounds', 1, 'extra'),
    'do_or_die': ('Do-or-die failed', 1, 'extra'),
}
# The scorer's buttons, a group at a time, two a row (UPG-388); a raid is +1 to +7, one per defender touched
KABADDI_GROUPS = (
    ('Raid points', ('raid', 'bonus')),
    ('Tackle points', ('tackle', 'super_tackle')),
    ('Other points', ('all_out', 'technical', 'out_of_bounds', 'do_or_die')),
)
KABADDI_HELP = {
    'raid': 'defenders touched in one raid', 'bonus': 'the raider crossed the bonus line',
    'tackle': 'the raider was caught', 'super_tackle': 'caught with 3 or fewer defenders on court',
    'all_out': 'every player of the other team is out', 'technical': "the referee's technical point",
    'out_of_bounds': 'a player of the other team stepped out', 'do_or_die': 'the other team’s do-or-die raid scored nothing',
}
OTHER_ACTIONS = {'score': ('Score', None, 'score')}
MAX_PICKED_POINTS = 7
KEEP_TAPS = 500
# The public scoreboards ask every 1.5 to 2 seconds and read the database at most
# once a second per server (UPG-403)
CACHE_SECONDS = 1
SQUAD_SECONDS = 60

# ── PKL mode (UPG-397) ─────────────────────────────────────────────────────
# The scorer records each raid, not points: the score, the players on the mat,
# revivals, all outs, super tackles, do-or-die raids and the bonus line follow
# from the raids by the rules, worked out again from the start after any change
# (`replay`), so an undo or a removed raid leaves everything right.
MAT = 7                  # players on the mat
TIMEOUTS_PER_HALF = 2    # each team's time-outs in a half
BONUS_DEFENDERS = 6      # the bonus line counts with this many defenders or more
SUPER_TACKLE_DEFENDERS = 3   # a tackle by this many defenders or fewer is a super tackle (+2)
DO_OR_DIE_AFTER = 2      # a team's third raid after two empty ones is a do-or-die raid
RAID_OUTCOMES = ('touch', 'bonus', 'empty', 'tackled', 'line_out')
PKL_EVENTS = ('raid', 'technical', 'out_of_bounds', 'timeout', 'review', 'mat', 'turn')
# The tie-breaker (PKL Season 12, UPG-396): five raids a team, seven players a side, no outs
SHOOTOUT_RAIDS = 5

_locks: dict = {}
_locks_guard = threading.Lock()
_cache: dict = {}


class LiveMatchError(ValueError):
    pass


def doc_id(event_id: str, match_id: str) -> str:
    return f"{event_id}__{match_id}"


def actions(tournament: dict) -> dict:
    return KABADDI_ACTIONS if services_sports.is_kabaddi(tournament) else OTHER_ACTIONS


def button_groups(tournament: dict) -> list:
    """[(group title or '', [{'kind', 'points', 'text', 'help', 'counts'}])]: every
    score the scorer can tap, one button each — kabaddi's raid +1 to +7 (UPG-388)."""
    if not services_sports.is_kabaddi(tournament):
        return [('', [{'kind': 'score', 'points': n, 'add': n, 'text': f'Score +{n}', 'help': '', 'counts': 'score'}
                      for n in range(1, 4)])]
    out = []
    for title, kinds in KABADDI_GROUPS:
        buttons = []
        for kind in kinds:
            label, fixed, counts = KABADDI_ACTIONS[kind]
            for n in ([fixed] if fixed else range(1, MAX_PICKED_POINTS + 1)):
                buttons.append({'kind': kind, 'points': None if fixed else n, 'add': n, 'text': f'{label} +{n}',
                                'help': KABADDI_HELP.get(kind, ''), 'counts': counts})
        out.append((title, buttons))
    return out


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


def _new(event_id, match_id, m, half_minutes, mode=''):
    doc = {'event_id': event_id, 'match_id': match_id, 'home': m['home'], 'away': m['away'],
           'phase': 'not_started', 'half_minutes': half_minutes,
           'clock': {'running': False, 'since': None, 'elapsed': 0.0},
           'log': [], 'taps': [], 'result': None}
    if mode == 'pkl':
        doc.update(mode='pkl', events=[], first_raid='home')
        doc['mat'] = replay(doc)
    return doc


def pkl_mode(tournament: dict) -> bool:
    """The SPOC turned PKL mode on for this kabaddi tournament (UPG-397)."""
    return services_sports.is_kabaddi(tournament) and tournament.get('scoring') == 'pkl'


def is_pkl(doc: dict) -> bool:
    return (doc or {}).get('mode') == 'pkl'


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
        doc = _new(event_id, match_id, m, DEFAULT_HALF_MINUTES, 'pkl' if pkl_mode(t) else '')
        with _lock(doc_id(event_id, match_id)):
            if get(db, event_id, match_id) is None:
                _save(db, event_id, match_id, doc)
            doc = get(db, event_id, match_id)
    return doc


def _other(side: str) -> str:
    return 'away' if side == 'home' else 'home'


def replay(doc: dict) -> dict:
    """Play a PKL-mode match's events from the start (UPG-397). Returns the mat:
    players on it, who raids next, do-or-die, the bonus line, time-outs, reviews
    and all outs; and puts the points the events earned in `doc['_log']`."""
    on = {'home': MAT, 'away': MAT}
    empty = {'home': 0, 'away': 0}
    first = doc.get('first_raid') if doc.get('first_raid') in ('home', 'away') else 'home'
    raider, half = first, 1
    timeouts = {1: {'home': 0, 'away': 0}, 2: {'home': 0, 'away': 0}}
    reviews = {'home': {'used': 0, 'upheld': 0}, 'away': {'used': 0, 'upheld': 0}}
    raids = {'home': 0, 'away': 0}
    all_outs = {'home': 0, 'away': 0}
    log = []

    def add(ev, team, kind, points, counts, label, player=''):
        log.append({'id': f"{ev['id']}#{len(log)}", 'event': ev['id'], 'team': team, 'kind': kind, 'label': label,
                    'points': points, 'counts': counts, 'player': player or '', 'half': ev.get('half') or 1,
                    'clock': ev.get('clock') or 0, 'at': ev.get('at') or '', 'by': ev.get('by') or ''})

    def out(ev, side):
        """One player of `side` is out: the other team revives one; the last one out is an all out."""
        on[side] -= 1
        on[_other(side)] = min(MAT, on[_other(side)] + 1)
        if on[side] <= 0:
            add(ev, _other(side), 'all_out', 2, 'extra', 'All out')
            all_outs[_other(side)] += 1
            on[side] = MAT

    for ev in doc.get('events') or []:
        if int(ev.get('half') or 1) == 2 and half == 1:
            half, raider = 2, _other(first)     # the other team raids first after half time
            empty = {'home': 0, 'away': 0}
        kind, side = ev.get('type'), ev.get('team')
        if side not in ('home', 'away') and kind != 'turn':
            continue
        if kind == 'raid':
            a, d = side, _other(side)
            dod = empty[a] >= DO_OR_DIE_AFTER
            super_on = on[d] <= SUPER_TACKLE_DEFENDERS
            outcome, who = ev.get('outcome'), ev.get('raider') or ''
            bonus = bool(ev.get('bonus'))
            raids[a] += 1
            if outcome == 'touch':
                n = max(1, min(int(ev.get('touches') or 1), on[d]))
                pts = n + (1 if bonus else 0)
                add(ev, a, 'raid', pts, 'raid', ('Super raid' if pts >= 3 else 'Raid'), who)
                on[d] -= n
                on[a] = min(MAT, on[a] + n)
                empty[a] = 0
                if on[d] <= 0:
                    add(ev, a, 'all_out', 2, 'extra', 'All out')
                    all_outs[a] += 1
                    on[d] = MAT
            elif outcome == 'bonus':
                add(ev, a, 'bonus', 1, 'raid', 'Bonus', who)
                empty[a] = 0
            elif outcome == 'empty':
                if dod:
                    add(ev, d, 'do_or_die', 1, 'extra', 'Do-or-die raid failed')
                    empty[a] = 0
                    out(ev, a)
                else:
                    empty[a] += 1
            elif outcome == 'tackled':
                if bonus:
                    add(ev, a, 'bonus', 1, 'raid', 'Bonus', who)
                add(ev, d, 'super_tackle' if super_on else 'tackle', 2 if super_on else 1, 'tackle',
                    'Super tackle' if super_on else 'Tackle', ev.get('tackler') or '')
                empty[a] = 0
                out(ev, a)
            elif outcome == 'line_out':
                add(ev, d, 'out_of_bounds', 1, 'extra', 'Raider out of court')
                empty[a] = 0
                out(ev, a)
            raider = d
        elif kind == 'technical':
            add(ev, side, 'technical', 1, 'extra', 'Technical point')
        elif kind == 'out_of_bounds':           # a player of `side` stepped out: the other team +1
            add(ev, _other(side), 'out_of_bounds', 1, 'extra', 'Out of bounds')
            out(ev, side)
        elif kind == 'timeout':
            timeouts[half][side] += 1
        elif kind == 'review':
            reviews[side]['used'] += 1
            reviews[side]['upheld'] += bool(ev.get('upheld'))
        elif kind == 'mat':
            on[side] = max(1, min(MAT, on[side] + (1 if int(ev.get('change') or 0) > 0 else -1)))
        elif kind == 'turn':
            raider = _other(raider)
    if half == 1 and doc.get('phase') in ('half_time', 'second_half', 'tiebreak', 'full_time'):
        half, raider = 2, _other(first)
        empty = {'home': 0, 'away': 0}
    doc['_log'] = log
    d = _other(raider)
    return {'on': on, 'raider': raider, 'do_or_die': empty[raider] >= DO_OR_DIE_AFTER,
            'empty': empty, 'bonus_live': on[d] >= BONUS_DEFENDERS,
            'super_tackle_on': on[d] <= SUPER_TACKLE_DEFENDERS, 'raid_no': raids['home'] + raids['away'] + 1,
            'raids': raids, 'half': half, 'first_raid': first,
            'timeouts_left': {x: max(0, TIMEOUTS_PER_HALF - timeouts[half][x]) for x in ('home', 'away')},
            'reviews': reviews, 'all_outs': all_outs, 'mat_size': MAT}


def _replay_into(doc: dict) -> None:
    """Work the match out again from its events: its points log and its mat."""
    doc['mat'] = replay(doc)
    doc['log'] = doc.pop('_log', [])


def add_event(db, event_id: str, event: dict, match_id: str, tap: str, kind: str, team: str = '',
              outcome: str = '', touches=None, bonus=False, raider: str = '', tackler: str = '',
              upheld=False, change=0, by: str = '') -> dict:
    """One raid or call in a PKL-mode match (UPG-397), checked against the mat
    as it stands: the team whose raid it is, touches no more than the defenders
    on the mat, the bonus line only with 6 or more defenders, two time-outs a
    team in each half."""
    if kind not in PKL_EVENTS:
        raise LiveMatchError("That isn't a call here.")
    if kind != 'turn' and team not in ('home', 'away'):
        raise LiveMatchError("Choose the team.")

    def apply(doc):
        if not is_pkl(doc):
            raise LiveMatchError("This match is scored point by point, not in PKL mode.")
        if doc.get('phase') not in ('first_half', 'second_half'):
            raise LiveMatchError("Start the half first.")
        mat = replay(doc)
        doc.pop('_log', None)
        ev = {'id': tap, 'type': kind, 'half': _half(doc), 'clock': clock_seconds(doc), 'at': _iso(), 'by': by}
        if kind != 'turn':
            ev['team'] = team
        if kind == 'raid':
            if team != mat['raider']:
                raise LiveMatchError("It's the other team's raid. Tap \"Other team raids\" if the referee says so.")
            if outcome not in RAID_OUTCOMES:
                raise LiveMatchError("Choose how the raid ended.")
            defenders = mat['on'][_other(team)]
            ev['outcome'] = outcome
            if outcome == 'touch':
                try:
                    n = int(touches)
                except (TypeError, ValueError):
                    n = 0
                if not 1 <= n <= defenders:
                    raise LiveMatchError(f"A raid can touch 1 to {defenders} defenders now.")
                ev['touches'] = n
            wants_bonus = outcome == 'bonus' or (outcome in ('touch', 'tackled') and bool(bonus))
            if wants_bonus and not mat['bonus_live']:
                raise LiveMatchError(f"The bonus line counts only with {BONUS_DEFENDERS} or more defenders on the mat.")
            ev['bonus'] = outcome in ('touch', 'tackled') and bool(bonus)
            squad_a, squad_d = players(event, doc[team]), players(event, doc[_other(team)])
            ev['raider'] = raider if raider in squad_a else ''
            ev['tackler'] = tackler if outcome == 'tackled' and tackler in squad_d else ''
        elif kind == 'timeout':
            if mat['timeouts_left'][team] <= 0:
                raise LiveMatchError(f"That team has used both time-outs of this half ({TIMEOUTS_PER_HALF}).")
            _stop_clock(doc)                       # a time-out stops the clock; Resume starts it
        elif kind == 'review':
            ev['upheld'] = bool(upheld)
        elif kind == 'mat':
            ev['change'] = 1 if int(change or 0) > 0 else -1
            now = mat['on'][team] + ev['change']
            if not 1 <= now <= MAT:
                raise LiveMatchError(f"A team has 1 to {MAT} players on the mat.")
        doc.setdefault('events', []).append(ev)
        _replay_into(doc)
    return _change(db, event_id, match_id, tap, apply)


OUTCOME_TEXT = {'touch': '{n} touch{es}', 'bonus': 'bonus', 'empty': 'empty raid', 'tackled': 'tackled',
                'line_out': 'raider out of court'}


def event_text(ev: dict, names: dict, doc: dict) -> str:
    """One PKL-mode raid or call, as the scorer's log and the boards show it."""
    team = names.get(doc.get(ev.get('team')), '') if ev.get('team') else ''
    kind = ev.get('type')
    if kind == 'raid':
        n = int(ev.get('touches') or 0)
        how = OUTCOME_TEXT.get(ev.get('outcome'), '').format(n=n, es='' if n == 1 else 'es')
        if ev.get('bonus'):
            how += ' + bonus'
        pts = sum(e['points'] for e in doc.get('log') or [] if e.get('event') == ev.get('id') and e['team'] == ev['team'])
        given = sum(e['points'] for e in doc.get('log') or [] if e.get('event') == ev.get('id') and e['team'] != ev['team'])
        who = f" ({ev['raider']})" if ev.get('raider') else ''
        tackler = f" by {ev['tackler']}" if ev.get('tackler') else ''
        parts = [f"Raid · {team}{who}: {how}{tackler}"]
        if pts:
            parts.append(f"+{pts}")
        if given:
            parts.append(f"+{given} to the defenders")
        parts += [e['label'] for e in doc.get('log') or []
                  if e.get('event') == ev.get('id') and e['kind'] in ('all_out', 'super_tackle', 'do_or_die')]
        return ' · '.join(parts)
    if kind == 'technical':
        return f"Technical point +1 · {team}"
    if kind == 'out_of_bounds':
        return f"Out of bounds · a {team} player is out"
    if kind == 'timeout':
        return f"Time-out · {team}"
    if kind == 'review':
        return f"Review · {team}: {'upheld' if ev.get('upheld') else 'not upheld'}"
    if kind == 'mat':
        return f"Mat corrected · {team} {'+1' if int(ev.get('change') or 0) > 0 else '−1'} player"
    if kind == 'turn':
        return "Raid turn passed to the other team"
    return kind or ''


# ── The tie-breaker (PKL Season 12, UPG-396) ───────────────────────────────
def shootout_state(doc: dict, names: dict = None) -> dict:
    """The five-raid shootout: each team's points and raids, who raids next, and
    the winner once there is one (else what is still needed)."""
    sh = doc.get('shootout') or {}
    pts = {'home': 0, 'away': 0}
    raids = {'home': 0, 'away': 0}
    lines = []
    for r in sh.get('raids') or []:
        a = r['team']
        raids[a] += 1
        got, given = _shootout_points(r)
        pts[a] += got
        pts[_other(a)] += given
        if names is not None:
            lines.append(f"{names.get(doc.get(a), a)} raid {raids[a]}: "
                         f"{OUTCOME_TEXT.get(r['outcome'], '').format(n=r.get('touches') or 0, es='' if r.get('touches') == 1 else 'es')}"
                         f"{' + bonus' if r.get('bonus') else ''} (+{got}{f', +{given} to the defenders' if given else ''})")
    last = (sh.get('raids') or [{}])[-1].get('team')
    nxt = _other(last) if last else ''
    done = raids['home'] >= SHOOTOUT_RAIDS and raids['away'] >= SHOOTOUT_RAIDS
    decided, winner, needs = None, None, ''
    if done and pts['home'] != pts['away']:
        decided, winner = 'shootout', ('home' if pts['home'] > pts['away'] else 'away')
    elif done and (sh.get('decided') or {}).get('winner') in ('home', 'away'):
        decided, winner = sh['decided']['way'], sh['decided']['winner']
    elif done:
        needs = "Still level after five raids each: record the golden raid's winner (or the coin toss)."
    else:
        needs = f"The tie-breaker needs {SHOOTOUT_RAIDS} raids from each team first."
    return {'home': pts['home'], 'away': pts['away'], 'raids': raids, 'next': nxt, 'done': done,
            'level': done and pts['home'] == pts['away'], 'decided': decided, 'winner': winner, 'needs': needs,
            'lines': list(reversed(lines)), 'per_team': SHOOTOUT_RAIDS}


def _shootout_points(r: dict) -> tuple:
    """(points to the raiding team, points to the defenders) of one shootout raid;
    seven defenders always, and the baulk line is the bonus line."""
    o, bonus = r.get('outcome'), 1 if r.get('bonus') else 0
    if o == 'touch':
        return int(r.get('touches') or 0) + bonus, 0
    if o == 'bonus':
        return 1, 0
    if o == 'tackled':
        return bonus, 1
    return 0, 0


def shootout_raid(db, event_id: str, match_id: str, tap: str, team: str, outcome: str, touches=None,
                  bonus=False) -> dict:
    """One raid of the tie-breaker: the teams take turns, five raids each."""
    if team not in ('home', 'away'):
        raise LiveMatchError("Choose the raiding team.")
    if outcome not in ('touch', 'bonus', 'empty', 'tackled'):
        raise LiveMatchError("Choose how the raid ended.")

    def apply(doc):
        if doc.get('phase') != 'tiebreak':
            raise LiveMatchError("The tie-breaker starts when full time is pressed at a level score.")
        st = shootout_state(doc)
        if st['next'] and team != st['next']:
            raise LiveMatchError("The teams raid in turn: it's the other team's raid.")
        if st['raids'][team] >= SHOOTOUT_RAIDS:
            raise LiveMatchError(f"That team has had its {SHOOTOUT_RAIDS} raids.")
        r = {'id': tap, 'team': team, 'outcome': outcome, 'bonus': outcome in ('touch', 'tackled') and bool(bonus)}
        if outcome == 'touch':
            try:
                n = int(touches)
            except (TypeError, ValueError):
                n = 0
            if not 1 <= n <= MAT:
                raise LiveMatchError(f"A raid can touch 1 to {MAT} defenders.")
            r['touches'] = n
        doc.setdefault('shootout', {'raids': [], 'decided': None}).setdefault('raids', []).append(r)
    return _change(db, event_id, match_id, tap, apply)


def shootout_decide(db, event_id: str, match_id: str, tap: str, way: str, winner: str) -> dict:
    """Still level after the shootout: the golden raid's winner, or the coin toss's."""
    if way not in ('golden', 'toss') or winner not in ('home', 'away'):
        raise LiveMatchError("Choose the golden raid's or the coin toss's winner.")

    def apply(doc):
        if doc.get('phase') != 'tiebreak':
            raise LiveMatchError("There is no tie-breaker now.")
        if not shootout_state(doc)['level']:
            raise LiveMatchError("The golden raid comes only when the five raids each leave it level.")
        doc['shootout']['decided'] = {'way': way, 'winner': winner}
    return _change(db, event_id, match_id, tap, apply)


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
        if is_pkl(doc):
            raise LiveMatchError("This match is scored raid by raid (PKL mode).")
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
        if doc.get('phase') == 'tiebreak':
            sh = doc.get('shootout') or {}
            if sh.get('decided'):
                sh['decided'] = None
            elif sh.get('raids'):
                sh['raids'].pop()
            else:
                raise LiveMatchError("There's nothing to undo in the tie-breaker. Tap Back to the 2nd half.")
            return
        if is_pkl(doc):
            if not doc.get('events'):
                raise LiveMatchError("There's nothing to undo.")
            doc['events'].pop()
            _replay_into(doc)
            return
        if not doc.get('log'):
            raise LiveMatchError("There's nothing to undo.")
        doc['log'].pop()
    return _change(db, event_id, match_id, tap, apply)


def _stop_clock(doc):
    doc['clock'] = {'running': False, 'since': None, 'elapsed': float(clock_seconds(doc))}


def _start_clock(doc, reset=False):
    elapsed = 0.0 if reset else float(clock_seconds(doc))
    doc['clock'] = {'running': True, 'since': _now(), 'elapsed': elapsed}


def change_phase(db, event_id: str, event: dict, match_id: str, tap: str, action: str, winner: str = '',
                 first: str = '') -> dict:
    """start, pause, resume, half_time, second_half, full_time, back. Full time
    saves the result to the tournament; a knockout tie needs `winner` (a team
    id), unless ties go to the tie-breaker (UPG-396): then full time at a level
    score starts it, and full time again saves the result with its winner.
    `first`: who raids first, at the start of a PKL-mode match (UPG-397)."""
    t = event.get('tournament') or {}

    def apply(doc):
        phase = doc.get('phase')
        if action == 'start' and phase == 'not_started':
            doc['phase'] = 'first_half'
            if is_pkl(doc) and first in ('home', 'away'):
                doc['first_raid'] = first
                _replay_into(doc)
            _start_clock(doc, reset=True)
        elif action == 'pause' and phase in ('first_half', 'second_half'):
            _stop_clock(doc)
        elif action == 'resume' and phase in ('first_half', 'second_half'):
            if not (doc.get('clock') or {}).get('running'):
                _start_clock(doc)
        elif action == 'half_time' and phase == 'first_half':
            doc['phase'] = 'half_time'
            _stop_clock(doc)
            if is_pkl(doc):
                _replay_into(doc)          # the other team raids first in the 2nd half
        elif action == 'second_half' and phase == 'half_time':
            doc['phase'] = 'second_half'
            if is_pkl(doc):
                _replay_into(doc)
            _start_clock(doc, reset=True)
        elif action == 'full_time' and phase == 'second_half':
            totals = score(doc)
            home, away = totals['home']['total'], totals['away']['total']
            if home == away and services_sports.tiebreak_on(t):
                doc['phase'] = 'tiebreak'          # PKL Season 12: no ties (UPG-396)
                doc.setdefault('shootout', {'raids': [], 'decided': None})
                _stop_clock(doc)
                return
            _finish(doc, home, away, winner)
        elif action == 'full_time' and phase == 'tiebreak':
            totals = score(doc)
            sh = shootout_state(doc)
            if not sh['winner']:
                raise LiveMatchError(sh['needs'])
            _finish(doc, totals['home']['total'], totals['away']['total'], doc[sh['winner']],
                    {'decided': sh['decided'], 'home': sh['home'], 'away': sh['away']})
        elif action == 'back' and phase == 'tiebreak':
            if (doc.get('shootout') or {}).get('raids'):
                raise LiveMatchError("Undo the tie-breaker's raids first.")
            doc['phase'] = 'second_half'
            doc.pop('shootout', None)
        else:
            raise LiveMatchError(f"Can't {action.replace('_', ' ')} now ({PHASE_NAMES.get(phase, phase)}).")

    def _finish(doc, home, away, win, tiebreak=None):
        try:
            nt = services_sports.change(db, event_id, lambda cur, _e: services_sports.record_result(
                cur, match_id, home, away, win, tiebreak))
        except services_sports.TournamentError as exc:
            raise LiveMatchError(str(exc))
        played = _match(nt, match_id)
        doc['phase'] = 'full_time'
        _stop_clock(doc)
        doc['result'] = {'home': home, 'away': away, 'winner': played.get('winner'),
                         'tiebreak': played.get('tiebreak')}
    return _change(db, event_id, match_id, tap, apply)


def remove_point(db, event_id: str, match_id: str, tap: str, entry_id: str) -> dict:
    """Take back one point anywhere in the log (given to the wrong team or
    player, or by mistake), while the match is being played (UPG-355)."""
    def apply(doc):
        if doc.get('phase') == 'full_time':
            raise LiveMatchError("The match is over. Reopen it first to change its points.")
        if is_pkl(doc):
            events = doc.get('events') or []
            keep = [e for e in events if e.get('id') != entry_id]
            if len(keep) == len(events):
                raise LiveMatchError("That raid isn't in the log.")
            doc['events'] = keep
            _replay_into(doc)
            return
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
    return bool(doc and (doc.get('log') or doc.get('events')))


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
    """The whole log, newest first, for the scorer to remove any point (in PKL
    mode, any raid or call)."""
    if is_pkl(doc):
        return [{'id': e.get('id'), 'text': event_text(e, names, doc), 'half': e.get('half')}
                for e in reversed(doc.get('events') or [])]
    return [{'id': e.get('id'), 'text': describe(e, names, doc), 'half': e.get('half')}
            for e in reversed(doc.get('log') or [])]


def players(event: dict, team_id: str) -> list:
    """The squad's names, for the scorer to pick who scored."""
    return list((event.get('_squads') or {}).get(team_id) or [])


def squads(db, event_id: str, team_ids) -> dict:
    """Team id → its players' names: the lead, then the members. Kept a minute,
    so a tap doesn't read the registrations again (UPG-403)."""
    out = {}
    for tid in team_ids:
        if not tid:
            continue
        key = ('squad', event_id, tid)
        hit = _cache.get(key)
        if hit and hit[0] > _now():
            out[tid] = list(hit[1])
            continue
        snap = db.collection('registrations').document(tid).get()
        reg = (snap.to_dict() or {}) if snap.exists else {}
        names = []
        for name in [reg.get('lead_name')] + [m.get('name') for m in reg.get('members') or [] if isinstance(m, dict)]:
            name = ' '.join(str(name or '').split())
            if name and name not in names:
                names.append(name)
        out[tid] = names
        _cache[key] = (_now() + SQUAD_SECONDS, list(names))
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
    """What a scoreboard shows: the teams, the score, the phase, the clock, the
    last actions; in PKL mode the mat too, and the tie-breaker when there is one."""
    s = score(doc)
    mat = (doc.get('mat') or replay(doc)) if is_pkl(doc) else None
    sh = shootout_state(doc, names) if doc.get('shootout') else None
    if is_pkl(doc):
        recent = [event_text(e, names, doc) for e in reversed((doc.get('events') or [])[-last:])]
    else:
        recent = [describe(e, names, doc) for e in reversed((doc.get('log') or [])[-last:])]
    return {'phase': doc.get('phase'), 'phase_name': PHASE_NAMES.get(doc.get('phase'), ''),
            'clock': clock_seconds(doc), 'running': bool((doc.get('clock') or {}).get('running')),
            'half_minutes': doc.get('half_minutes') or DEFAULT_HALF_MINUTES,
            'home': {'id': doc.get('home'), 'name': names.get(doc.get('home'), ''), **s['home']},
            'away': {'id': doc.get('away'), 'name': names.get(doc.get('away'), ''), **s['away']},
            'result': doc.get('result'),
            'recent': recent,
            'mode': doc.get('mode') or '',
            'mat': mat,
            'mat_text': mat_text(mat, names, doc) if mat and doc.get('phase') in ('first_half', 'second_half') else '',
            'shootout': sh,
            'shootout_text': shootout_text(sh, names, doc) if sh else '',
            'updated_at': doc.get('updated_at')}


def mat_text(mat: dict, names: dict, doc: dict) -> str:
    """One line for the boards: who raids, do-or-die, the players on the mat."""
    a = mat['raider']
    parts = [f"{names.get(doc.get(a), '')} to raid"]
    if mat.get('do_or_die'):
        parts.append('DO-OR-DIE')
    parts.append(f"On the mat {mat['on']['home']}–{mat['on']['away']}")
    if mat.get('super_tackle_on'):
        parts.append('Super tackle on')
    return ' · '.join(parts)


def shootout_text(sh: dict, names: dict, doc: dict) -> str:
    """The tie-breaker for the boards: 'Tie-breaker 3–2 (raids 3/5 · 2/5)'."""
    line = (f"Tie-breaker: {names.get(doc.get('home'), '')} {sh['home']}–{sh['away']} "
            f"{names.get(doc.get('away'), '')} (raids {sh['raids']['home']}/{sh['per_team']} · "
            f"{sh['raids']['away']}/{sh['per_team']})")
    if sh.get('winner'):
        way = services_sports.TIEBREAK_WAYS.get(sh.get('decided'), 'tie-breaker')
        line += f" · {names.get(doc.get(sh['winner']), '')} won the {way}"
    return line


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


def by_team(stats: list, tournament: dict) -> list:
    """[(team name, team id, rows best first)] in the fixtures' team order, for
    "Every player's points" (UPG-395); only teams with a player who scored."""
    out = []
    for team in tournament.get('teams') or []:
        rows = [r for r in stats if r['team_id'] == team['id']]
        if rows:
            out.append((team['name'], team['id'], sorted(rows, key=lambda r: (-r['total'], r['player'].lower()))))
    return out


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
