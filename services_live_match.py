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
# The scorer sets each match's half and break before the start (UPG-439)
DEFAULT_BREAK_MINUTES = 5
HALF_MINUTES_RANGE = (1, 60)
BREAK_MINUTES_RANGE = (0, 30)
# The toss before the start (UPG-438): the winner raids first or takes the court
TOSS_CHOICES = {'raid': 'to raid first', 'court': 'the court'}

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
FEED = 12          # raids the public page lists, the latest first (UPG-421)

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
RAID_OUTCOMES = ('touch', 'bonus', 'empty', 'tackled', 'line_out', 'time_over')
# The raid clock (UPG-413): a raid lasts 30 seconds; a raider not back by then is out, +1 to the defence
RAID_SECONDS = 30
TOSS_FRESH_SECONDS = 600     # a toss is played on screens opening this long after it (UPG-438)
RESULT_SHOW_SECONDS = 600    # the big screen keeps a finished match's board, with who won, this long (UPG-456)
PKL_EVENTS = ('raid', 'technical', 'out_of_bounds', 'timeout', 'review', 'mat', 'turn', 'sub', 'card', 'stoppage')
# Cards (UPG-447): green a warning; yellow off the mat for 2 minutes of play; red
# off for the rest of the match. A card gives no point by itself: the referee
# gives a technical point when one is due.
CARDS = {'green': 'Green card', 'yellow': 'Yellow card', 'red': 'Red card'}
CARD_EFFECT = {'green': 'warning', 'yellow': 'off for 2 min', 'red': 'off for the match'}
YELLOW_SECONDS = 120
# The clock stopped without a team's time-out (UPG-449)
STOPPAGES = {'injury': 'Injury break', 'official': 'Official time-out'}
# Why the referee gave a technical point (UPG-450)
TECH_REASONS = {'late_sub': 'late or wrong substitution', 'coach': 'coach or official on the court',
                'delay': 'delaying the game', 'conduct': 'bad conduct', 'raid_rule': 'a raid rule broken',
                'other': 'another rule'}
# Line-ups (UPG-417): each team's seven starters, tapped before the start; the
# rest of the squad are the substitutes. With both line-ups the players on the
# mat and out are kept by name, revived first out, first in (UPG-404).
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


# ── How many have watched a match (UPG-433) ─────────────────────────────────
VIEWS = 'match_views'
SEEN_COOKIE = 'sv_seen'        # the matches this browser has opened, to count each device once
SEEN_MAX = 80                  # matches remembered per browser (a cookie stays small)
NOT_PEOPLE = ('bot', 'crawl', 'spider', 'slurp', 'preview', 'facebookexternalhit', 'whatsapp', 'telegram',
              'discord', 'skype', 'headless', 'curl', 'wget', 'python-requests')


def is_person(user_agent: str) -> bool:
    """A browser, not a link preview or a crawler: only people are counted."""
    ua = (user_agent or '').lower()
    return bool(ua) and not any(x in ua for x in NOT_PEOPLE)


def views(db, event_id: str, match_id: str) -> dict:
    snap = db.collection(VIEWS).document(doc_id(event_id, match_id)).get()
    d = (snap.to_dict() or {}) if snap.exists else {}
    return {'views': int(d.get('views') or 0), 'devices': int(d.get('devices') or 0)}


def short_count(n: int) -> str:
    """A count as a streaming app shows it (UPG-435): 999, 1.2K, 3.4L, 1.1Cr;
    rounded down, so it never shows more than there were."""
    n = max(0, int(n or 0))
    for size, unit in ((10_000_000, 'Cr'), (100_000, 'L'), (1_000, 'K')):
        if n >= size:
            whole, tenth = divmod(n * 10 // size, 10)
            return f"{whole}{'.' + str(tenth) if tenth and whole < 100 else ''}{unit}"
    return str(n)


def count_view(db, event_id: str, match_id: str, seen: str) -> tuple:
    """Every opening of the match page adds a view; a browser opening it for
    the first time adds a device. Nothing is ever taken off. `seen` is the
    browser's cookie; returns (the counts, the cookie to set)."""
    from google.cloud.firestore_v1 import Increment
    import hashlib
    key = hashlib.sha1(doc_id(event_id, match_id).encode(), usedforsecurity=False).hexdigest()[:10]
    known = [k for k in (seen or '').split('.') if k.isalnum()][-SEEN_MAX:]
    first = key not in known
    change = {'event_id': event_id, 'match_id': match_id, 'views': Increment(1), 'updated_at': _iso()}
    if first:
        change['devices'] = Increment(1)
        known.append(key)
    db.collection(VIEWS).document(doc_id(event_id, match_id)).set(change, merge=True)
    return views(db, event_id, match_id), '.'.join(known[-SEEN_MAX:])


def _save(db, event_id, match_id, doc):
    doc['updated_at'] = _iso()
    db.collection(COLLECTION).document(doc_id(event_id, match_id)).set(doc, merge=False)
    _cache.pop(('state', event_id, match_id), None)
    _cache.pop(('live', event_id), None)
    _cache.pop(('toss', event_id), None)
    _cache.pop(('done', event_id), None)
    _cache.pop(('stats', event_id), None)


def _new(event_id, match_id, m, half_minutes, mode=''):
    doc = {'event_id': event_id, 'match_id': match_id, 'home': m['home'], 'away': m['away'],
           'phase': 'not_started', 'half_minutes': half_minutes, 'break_minutes': DEFAULT_BREAK_MINUTES,
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
    elif pkl_mode(t) and not is_pkl(doc) and _untouched(doc):
        # Opened while PKL mode was off, PKL mode on since, nothing played yet:
        # it is scored raid by raid like the rest (UPG-478)
        with _lock(doc_id(event_id, match_id)):
            doc = get(db, event_id, match_id)
            if not is_pkl(doc) and _untouched(doc):
                doc.update(mode='pkl', events=[], first_raid=doc.get('first_raid') or 'home')
                doc['mat'] = replay(doc)
                _save(db, event_id, match_id, doc)
    return doc


def _untouched(doc: dict) -> bool:
    """Not started and not a point, tap or raid recorded (UPG-478)."""
    return (doc.get('phase') == 'not_started' and not doc.get('log') and not doc.get('taps')
            and not doc.get('events') and not doc.get('result'))


def _other(side: str) -> str:
    return 'away' if side == 'home' else 'home'


def named(doc: dict) -> bool:
    """Both teams have their seven (UPG-417): the mat is kept by name (UPG-404)."""
    lineup = (doc or {}).get('lineup') or {}
    return all(len((lineup.get(side) or {}).get('start') or []) == MAT for side in ('home', 'away'))


def squad_of(doc: dict, side: str) -> list:
    """[{'name', 'jersey'}] of a side's squad as saved with its line-up."""
    return list(((doc.get('lineup') or {}).get(side) or {}).get('squad') or [])


def jersey_of(doc: dict, side: str, name: str) -> str:
    for p in squad_of(doc, side):
        if p.get('name') == name:
            return str(p.get('jersey') or '')
    return ''


def tag(doc: dict, side: str, name: str) -> str:
    """'#7 Arjun', or the name when he has no number."""
    if not name:
        return ''
    number = jersey_of(doc, side, name) if side in ('home', 'away') else ''
    return f"#{number} {name}" if number else name


def replay(doc: dict, clock: Optional[int] = None) -> dict:
    """Play a PKL-mode match's events from the start (UPG-397). Returns the mat:
    players on it, who raids next, do-or-die, the bonus line, time-outs, reviews
    and all outs; and puts the points the events earned in `doc['_log']`.
    With both line-ups (UPG-417) the players on the mat and out are kept by
    name, in the order they went out (UPG-404). A yellow or red card takes a
    player off (UPG-447); a yellow card's player comes back after
    YELLOW_SECONDS of play, by the events' clock and, when given, `clock` (the
    match clock now)."""
    on = {'home': MAT, 'away': MAT}
    by_name = named(doc)
    lineup = doc.get('lineup') or {}
    on_n = {s: list(lineup[s]['start']) for s in ('home', 'away')} if by_name else {'home': [], 'away': []}
    out_n = {'home': [], 'away': []}
    carded = {'home': [], 'away': []}       # off for a card: {name, card, from, half, clock}
    half_len = int(doc.get('half_minutes') or DEFAULT_HALF_MINUTES) * 60
    subs = []

    def served(c, at_half, at_clock):
        """Seconds of play since the card, across half time too."""
        if at_half == c['half']:
            return max(0, at_clock - c['clock'])
        return max(0, half_len - c['clock']) + max(0, at_clock)

    def release(at_half, at_clock):
        """Yellow cards whose 2 minutes are over: the player comes back where he was."""
        for side in ('home', 'away'):
            for c in [c for c in carded[side] if c['card'] == 'yellow'
                      and served(c, at_half, at_clock) >= YELLOW_SECONDS]:
                carded[side].remove(c)
                (on_n if c['from'] == 'on' and len(on_n[side]) < MAT else out_n)[side].append(c['name'])
                on[side] = len(on_n[side])
    empty = {'home': 0, 'away': 0}
    first = doc.get('first_raid') if doc.get('first_raid') in ('home', 'away') else 'home'
    raider, half = first, 1
    timeouts = {1: {'home': 0, 'away': 0}, 2: {'home': 0, 'away': 0}}
    reviews = {'home': {'used': 0, 'upheld': 0}, 'away': {'used': 0, 'upheld': 0}}
    raids = {'home': 0, 'away': 0}
    all_outs = {'home': 0, 'away': 0}
    log = []

    def add(ev, team, kind, points, counts, label, player='', dod=False):
        log.append({'id': f"{ev['id']}#{len(log)}", 'event': ev['id'], 'team': team, 'kind': kind, 'label': label,
                    'points': points, 'counts': counts, 'player': player or '', 'half': ev.get('half') or 1,
                    'clock': ev.get('clock') or 0, 'at': ev.get('at') or '', 'by': ev.get('by') or '',
                    **({'dod': True} if dod else {})})   # a do-or-die raid's points, for the profile (UPG-424)

    def put_out(side, who=''):
        """One player of `side` leaves the mat: the one named, else the last on it."""
        if by_name:
            if who in on_n[side]:
                on_n[side].remove(who)
            elif on_n[side]:
                who = on_n[side].pop()
            else:
                return
            out_n[side].append(who)
            on[side] = len(on_n[side])
        else:
            on[side] -= 1

    def revive(side, k):
        """`k` players of `side` come back, the first out first."""
        if by_name:
            for _ in range(k):
                if out_n[side]:
                    on_n[side].append(out_n[side].pop(0))
            on[side] = len(on_n[side])
        else:
            on[side] = min(MAT, on[side] + k)

    def all_back(side):
        if by_name:
            on_n[side] += out_n[side]
            out_n[side] = []
            on[side] = len(on_n[side])      # a carded player stays off (UPG-447)
        else:
            on[side] = MAT

    def out(ev, side, who=''):
        """One player of `side` is out: the other team revives one; the last one out is an all out."""
        put_out(side, who)
        revive(_other(side), 1)
        if on[side] <= 0:
            add(ev, _other(side), 'all_out', 2, 'extra', 'All out')
            all_outs[_other(side)] += 1
            all_back(side)

    for ev in doc.get('events') or []:
        if by_name:
            release(int(ev.get('half') or 1), int(ev.get('clock') or 0))
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
                touched = [x for x in ev.get('touched') or [] if x in on_n[d]] if by_name else []
                n = len(touched) if touched else max(1, min(int(ev.get('touches') or 1), on[d]))
                if by_name and not touched:      # no names given: the last on the mat
                    touched = on_n[d][-n:]
                pts = n + (1 if bonus else 0)
                add(ev, a, 'raid', pts, 'raid', ('Super raid' if pts >= 3 else 'Raid'), who, dod)
                for x in (touched or [''] * n):
                    put_out(d, x)
                revive(a, n)
                empty[a] = 0
                if on[d] <= 0:
                    add(ev, a, 'all_out', 2, 'extra', 'All out')
                    all_outs[a] += 1
                    all_back(d)
            elif outcome == 'bonus':
                add(ev, a, 'bonus', 1, 'raid', 'Bonus', who, dod)
                empty[a] = 0
            elif outcome == 'empty':
                if dod:
                    add(ev, d, 'do_or_die', 1, 'extra', 'Do-or-die raid failed')
                    empty[a] = 0
                    out(ev, a, who)
                else:
                    empty[a] += 1
            elif outcome == 'tackled':
                if bonus:
                    add(ev, a, 'bonus', 1, 'raid', 'Bonus', who, dod)
                add(ev, d, 'super_tackle' if super_on else 'tackle', 2 if super_on else 1, 'tackle',
                    'Super tackle' if super_on else 'Tackle', ev.get('tackler') or '')
                if ev.get('assists'):            # the others who caught him (UPG-448)
                    log[-1]['assists'] = list(ev['assists'])
                empty[a] = 0
                out(ev, a, who)
            elif outcome == 'line_out':
                add(ev, d, 'out_of_bounds', 1, 'extra', 'Raider out of court')
                empty[a] = 0
                out(ev, a, who)
            elif outcome == 'time_over':         # not back in 30 seconds (UPG-413): as a raider out
                add(ev, d, 'time_over', 1, 'extra', 'Raid time over')
                empty[a] = 0
                out(ev, a, who)
            raider = d
        elif kind == 'technical':
            add(ev, side, 'technical', 1, 'extra', 'Technical point')
        elif kind == 'out_of_bounds':           # a player of `side` stepped out: the other team +1
            add(ev, _other(side), 'out_of_bounds', 1, 'extra', 'Out of bounds')
            out(ev, side, ev.get('player') or '')
        elif kind == 'timeout':
            timeouts[half][side] += 1
        elif kind == 'review':
            reviews[side]['used'] += 1
            reviews[side]['upheld'] += bool(ev.get('upheld'))
        elif kind == 'mat':
            if int(ev.get('change') or 0) > 0:
                if on[side] < MAT:
                    revive(side, 1)
            elif on[side] > 1:
                put_out(side, ev.get('player') or '')
        elif kind == 'sub' and by_name:          # a substitute takes the place of one of the seven
            off, new = ev.get('off') or '', ev.get('on') or ''
            for group in (on_n[side], out_n[side]):
                if off in group and new not in on_n[side] + out_n[side]:
                    group[group.index(off)] = new
                    subs.append({'team': side, 'off': off, 'on': new, 'half': ev.get('half') or 1})
                    break
        elif kind == 'card' and by_name and ev.get('card') in ('yellow', 'red'):   # UPG-447
            who = ev.get('player') or ''
            already = next((c for c in carded[side] if c['name'] == who), None)
            if already:                          # a yellow, then a red: off for the match
                already['card'] = 'red' if ev['card'] == 'red' else already['card']
            elif who in on_n[side] or who in out_n[side]:
                where = 'on' if who in on_n[side] else 'out'
                (on_n if where == 'on' else out_n)[side].remove(who)
                on[side] = len(on_n[side])
                carded[side].append({'name': who, 'card': ev['card'], 'from': where,
                                     'half': int(ev.get('half') or 1), 'clock': int(ev.get('clock') or 0)})
        elif kind == 'turn':
            raider = _other(raider)
    now_half = _half(doc)
    if by_name and clock is not None:
        release(now_half, int(clock))
    if half == 1 and doc.get('phase') in ('half_time', 'second_half', 'tiebreak', 'full_time'):
        half, raider = 2, _other(first)
        empty = {'home': 0, 'away': 0}
    doc['_log'] = log
    d = _other(raider)
    players = None
    if by_name:
        def row(side, name):
            return {'name': name, 'jersey': jersey_of(doc, side, name)}

        def card_row(side, c):
            left = None
            if c['card'] == 'yellow':
                at = int(clock) if clock is not None else c['clock']
                left = max(0, YELLOW_SECONDS - served(c, now_half, at))
            return dict(row(side, c['name']), card=c['card'], left=left)
        players = {}
        for side in ('home', 'away'):
            seven = set(on_n[side] + out_n[side] + [c['name'] for c in carded[side]])
            players[side] = {'on': [row(side, x) for x in on_n[side]], 'out': [row(side, x) for x in out_n[side]],
                             'carded': [card_row(side, c) for c in carded[side]],
                             'bench': [row(side, p['name']) for p in squad_of(doc, side) if p['name'] not in seven]}
    return {'on': on, 'raider': raider, 'do_or_die': empty[raider] >= DO_OR_DIE_AFTER,
            'empty': empty, 'bonus_live': on[d] >= BONUS_DEFENDERS,
            'super_tackle_on': on[d] <= SUPER_TACKLE_DEFENDERS, 'raid_no': raids['home'] + raids['away'] + 1,
            'raids': raids, 'half': half, 'first_raid': first,
            'timeouts_left': {x: max(0, TIMEOUTS_PER_HALF - timeouts[half][x]) for x in ('home', 'away')},
            # Each half's time-outs taken, for the boxes beside each team (UPG-469)
            'timeouts_used': {x: [timeouts[1][x], timeouts[2][x]] for x in ('home', 'away')},
            'timeouts_per_half': TIMEOUTS_PER_HALF,
            'reviews': reviews, 'all_outs': all_outs, 'mat_size': MAT,
            'named': by_name, 'players': players, 'subs': subs}


def _replay_into(doc: dict) -> None:
    """Work the match out again from its events: its points log and its mat."""
    doc['mat'] = replay(doc, clock_seconds(doc))
    doc['log'] = doc.pop('_log', [])


def _cards_running(mat: Optional[dict]) -> bool:
    """A yellow card is still counting down: the mat must be worked out at the clock now."""
    return bool(mat and mat.get('players') and any(
        c.get('left') is not None for side in ('home', 'away') for c in (mat['players'][side].get('carded') or [])))


def add_event(db, event_id: str, event: dict, match_id: str, tap: str, kind: str, team: str = '',
              outcome: str = '', touches=None, bonus=False, raider: str = '', tackler: str = '',
              upheld=False, change=0, by: str = '', touched=None, player: str = '', off: str = '',
              on: str = '', reason: str = '', card: str = '', where: str = '', bonus_missed=False) -> dict:
    """One raid or call in a PKL-mode match (UPG-397), checked against the mat
    as it stands: the team whose raid it is, touches no more than the defenders
    on the mat, the bonus line only with 6 or more defenders, two time-outs a
    team in each half. With line-ups (UPG-417) a raid names its raider and the
    defenders touched, out of bounds and −1 on the mat name the player, and a
    substitution (`off`, `on`) is a call too (UPG-404). Also: cards (UPG-447),
    every defender in a tackle (UPG-448), an injury break or official time-out
    (`stoppage`, UPG-449), a technical point's `reason` (UPG-450), the lobby
    (`where='lobby'`, UPG-451) and a bonus tried and not given (UPG-452)."""
    if kind not in PKL_EVENTS:
        raise LiveMatchError("That isn't a call here.")
    if kind not in ('turn', 'stoppage') and team not in ('home', 'away'):
        raise LiveMatchError("Choose the team.")
    if kind == 'stoppage' and (reason not in STOPPAGES or (team and team not in ('home', 'away'))):
        raise LiveMatchError("Choose an injury break or an official time-out.")
    if kind == 'card' and card not in CARDS:
        raise LiveMatchError("Choose a green, yellow or red card.")
    if kind == 'technical' and reason and reason not in TECH_REASONS:
        raise LiveMatchError("Choose the reason from the list.")
    touched = [str(x) for x in touched] if isinstance(touched, (list, tuple)) else []

    def apply(doc):
        if not is_pkl(doc):
            raise LiveMatchError("This match is scored point by point, not in PKL mode.")
        allowed = (('first_half', 'half_time', 'second_half') if kind in ('sub', 'card')
                   else ('first_half', 'second_half'))
        if doc.get('phase') not in allowed:
            raise LiveMatchError("Start the half first.")
        mat = replay(doc, clock_seconds(doc))
        doc.pop('_log', None)
        by_name = mat['named']
        ev = {'id': tap, 'type': kind, 'half': _half(doc), 'clock': clock_seconds(doc), 'at': _iso(), 'by': by}
        if kind not in ('turn', 'stoppage') or team in ('home', 'away'):
            ev['team'] = team
        on_mat = ({s: [p['name'] for p in mat['players'][s]['on']] for s in ('home', 'away')} if by_name
                  else {'home': [], 'away': []})
        who, tk = raider, tackler
        if kind == 'raid':
            if team != mat['raider']:
                raise LiveMatchError("It's the other team's raid. Tap \"Other team raids\" if the referee says so.")
            if outcome not in RAID_OUTCOMES:
                raise LiveMatchError("Choose how the raid ended.")
            defenders = mat['on'][_other(team)]
            ev['outcome'] = outcome
            if by_name:
                who = who or (doc.get('raiding_now') or {}).get('name') or ''
                if who not in on_mat[team]:
                    raise LiveMatchError("Tap the raider first: one of the players on the mat.")
            if outcome == 'touch':
                if by_name:
                    if not touched:
                        raise LiveMatchError("Tap the defenders he touched.")
                    if len(set(touched)) != len(touched) or any(x not in on_mat[_other(team)] for x in touched):
                        raise LiveMatchError("The defenders touched must be players on the mat.")
                    ev['touched'] = touched
                    n = len(touched)
                else:
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
            if bonus_missed:                       # tried the bonus, the referee didn't give it (UPG-452)
                if wants_bonus:
                    raise LiveMatchError("Tick the bonus as given or as not given, not both.")
                if not mat['bonus_live']:
                    raise LiveMatchError(f"The bonus line counts only with {BONUS_DEFENDERS} or more defenders on the mat.")
                ev['bonus_missed'] = True
            if by_name:
                ev['raider'] = who
                caught = []
                if outcome == 'tackled':           # every defender in the tackle; the first made the catch (UPG-448)
                    caught = [x for x in dict.fromkeys(([tk] if tk else []) + touched) if x in on_mat[_other(team)]]
                ev['tackler'] = caught[0] if caught else ''
                if len(caught) > 1:
                    ev['assists'] = caught[1:]
            else:
                squad_a, squad_d = players(event, doc[team]), players(event, doc[_other(team)])
                ev['raider'] = who if who in squad_a else ''
                ev['tackler'] = tk if outcome == 'tackled' and tk in squad_d else ''
            secs = raid_seconds(doc)
            if secs is not None:                   # how long the raid took (UPG-413)
                ev['secs'] = secs
            doc.pop('raiding_now', None)
            doc.pop('raid_clock', None)
        elif kind == 'timeout':
            if mat['timeouts_left'][team] <= 0:
                raise LiveMatchError(f"That team has used both time-outs of this half ({TIMEOUTS_PER_HALF}).")
            _stop_clock(doc)                       # a time-out stops the clock; Resume starts it
            doc.pop('raid_clock', None)
        elif kind == 'review':
            ev['upheld'] = bool(upheld)
        elif kind == 'mat':
            ev['change'] = 1 if int(change or 0) > 0 else -1
            now = mat['on'][team] + ev['change']
            if not 1 <= now <= MAT:
                raise LiveMatchError(f"A team has 1 to {MAT} players on the mat.")
            if by_name and ev['change'] < 0:
                if player not in on_mat[team]:
                    raise LiveMatchError("Tap the player who goes off the mat.")
                ev['player'] = player
        elif kind == 'out_of_bounds' and by_name:
            if player not in on_mat[team]:
                raise LiveMatchError("Tap the player who went into the lobby." if where == 'lobby'
                                     else "Tap the player who stepped out.")
            ev['player'] = player
        elif kind == 'technical' and reason:
            ev['reason'] = reason
        elif kind == 'stoppage':                   # the clock stops; no team's time-out is used (UPG-449)
            ev['reason'] = reason
            if team in ('home', 'away') and player and player in players(event, doc[team]):
                ev['player'] = player
            _stop_clock(doc)
            doc.pop('raid_clock', None)
        elif kind == 'card':
            if by_name:
                seven = (on_mat[team] + [p['name'] for p in mat['players'][team]['out']])
                yellow = [c['name'] for c in mat['players'][team].get('carded') or [] if c['card'] == 'yellow']
                if player not in seven and not (card == 'red' and player in yellow):
                    raise LiveMatchError("Tap a player of the seven for the card.")
            elif player and player not in players(event, doc[team]):
                raise LiveMatchError("Choose a player of that team.")
            ev.update(card=card, player=player)
            if card in ('yellow', 'red') and (doc.get('raiding_now') or {}).get('name') == player:
                doc.pop('raiding_now', None)
        elif kind == 'sub':
            if not by_name:
                raise LiveMatchError("Substitutions need both teams' line-ups.")
            seven = on_mat[team] + [p['name'] for p in mat['players'][team]['out']]
            bench = [p['name'] for p in mat['players'][team]['bench']]
            if off not in seven:
                raise LiveMatchError("The player going off must be one of the seven.")
            if on not in bench:
                raise LiveMatchError("The player coming on must be a substitute.")
            ev.update(off=off, on=on)
            if (doc.get('raiding_now') or {}).get('name') == off:
                doc.pop('raiding_now', None)
        if kind == 'out_of_bounds' and where == 'lobby':   # into the lobby before a struggle (UPG-451)
            ev['where'] = 'lobby'
        if kind == 'turn':
            doc.pop('raiding_now', None)
            doc.pop('raid_clock', None)
        doc.setdefault('events', []).append(ev)
        _replay_into(doc)
    return _change(db, event_id, match_id, tap, apply)


def set_lineup(db, event_id: str, event: dict, match_id: str, tap: str, sides: dict, numbers: dict) -> dict:
    """Each team's seven starters, before the start (UPG-417). `sides`:
    {'home': [names], 'away': [names]} (either or both); `numbers`: {'home':
    {name: jersey}, 'away': …}. The rest of the squad are the substitutes."""
    def apply(doc):
        if not is_pkl(doc):
            raise LiveMatchError("Line-ups are for PKL mode.")
        if doc.get('phase') != 'not_started':
            raise LiveMatchError("The match has started: change players with a substitution.")
        for side, chosen in (sides or {}).items():
            if side not in ('home', 'away') or not isinstance(chosen, (list, tuple)):
                continue
            squad = players(event, doc[side])
            chosen = [str(x) for x in chosen]
            if len(chosen) != MAT or len(set(chosen)) != MAT:
                raise LiveMatchError(f"Choose {MAT} different players for each team.")
            if any(x not in squad for x in chosen):
                raise LiveMatchError("A line-up has only the team's registered players.")
            jersey = (numbers or {}).get(side) or {}
            doc.setdefault('lineup', {})[side] = {
                'start': chosen, 'squad': [{'name': p, 'jersey': str(jersey.get(p) or '')} for p in squad]}
        _replay_into(doc)
    return _change(db, event_id, match_id, tap, apply)


def needs_lineup(event: dict, doc: dict) -> bool:
    """Both teams have seven registered players (UPG-417): the match starts with line-ups."""
    return is_pkl(doc) and all(len(players(event, doc[side])) >= MAT for side in ('home', 'away'))


def raiding_now(db, event_id: str, match_id: str, tap: str, name: str) -> dict:
    """The scorer tapped the raider (UPG-420): the boards show him raiding at once."""
    def apply(doc):
        if not is_pkl(doc) or doc.get('phase') not in ('first_half', 'second_half'):
            raise LiveMatchError("Start the half first.")
        mat = replay(doc)
        doc.pop('_log', None)
        if not mat['named']:
            raise LiveMatchError("Choose the line-ups first.")
        side = mat['raider']
        if name and name not in [p['name'] for p in mat['players'][side]['on']]:
            raise LiveMatchError("The raider must be a player on the mat of the raiding team.")
        if name:
            doc['raiding_now'] = {'team': side, 'name': name}
            if not raid_running(doc) and not doc.get('raid_clock_off'):   # his 30 seconds start (UPG-413)
                _start_raid(doc, side)
        else:
            doc.pop('raiding_now', None)
    return _change(db, event_id, match_id, tap, apply)


# ── The raid clock (UPG-413) ───────────────────────────────────────────────
# A stopwatch: started when the raider goes (the scorer's Space key, or the
# raider tapped), stopped when he is back (Space again). The raid saved next
# keeps its seconds ("back in 12 s").
def _start_raid(doc, side):
    doc['raid_clock'] = {'team': side, 'since': _now(), 'stopped': None}


def raid_running(doc: dict) -> bool:
    rc = doc.get('raid_clock') or {}
    return bool(rc.get('since')) and rc.get('stopped') is None


def raid_seconds(doc: dict, now: Optional[float] = None) -> Optional[int]:
    """The raid's seconds so far (or when stopped), None when its clock never started."""
    rc = doc.get('raid_clock') or {}
    if not rc.get('since'):
        return None
    if rc.get('stopped') is not None:
        return int(rc['stopped'])
    return int(max(0.0, (now or _now()) - float(rc['since'])))


def raid_clock(db, event_id: str, match_id: str, tap: str, action: str) -> dict:
    """start (again from 0) or stop the raid clock of the team whose raid it is;
    off and on (UPG-464): a scorer who doesn't time the raids turns it off, and
    neither the scorer's page nor the boards show it until it is on again."""
    def apply(doc):
        if is_pkl(doc) and action in ('off', 'on'):
            if action == 'off':
                doc['raid_clock_off'] = True
                doc.pop('raid_clock', None)
            else:
                doc.pop('raid_clock_off', None)
            return
        if not is_pkl(doc) or doc.get('phase') not in ('first_half', 'second_half'):
            raise LiveMatchError("Start the half first.")
        if doc.get('raid_clock_off'):
            raise LiveMatchError("The raid clock is off: turn it on first.")
        if action == 'start':
            mat = replay(doc)
            doc.pop('_log', None)
            _start_raid(doc, mat['raider'])
        elif action == 'stop':
            if raid_running(doc):
                doc['raid_clock']['stopped'] = raid_seconds(doc)
        elif action == 'clear':
            doc.pop('raid_clock', None)
        else:
            raise LiveMatchError("Start or stop the raid clock.")
    return _change(db, event_id, match_id, tap, apply)


def _raid_state(doc: dict) -> Optional[dict]:
    if doc.get('phase') not in ('first_half', 'second_half') or doc.get('raid_clock_off'):
        return None
    secs = raid_seconds(doc)
    if secs is None:
        return None
    return {'team': (doc.get('raid_clock') or {}).get('team'), 'secs': secs, 'running': raid_running(doc),
            'left': max(0, RAID_SECONDS - secs), 'over': secs >= RAID_SECONDS}


# ── Before the start: the toss (UPG-438) and the match's timings (UPG-439) ──
def set_toss(db, event_id: str, match_id: str, tap: str, winner: str, choice: str) -> dict:
    """Who won the toss and what they chose. In PKL mode it says who raids
    first: the winner if they chose to raid, else the other team."""
    def apply(doc):
        if doc.get('phase') != 'not_started':
            raise LiveMatchError("The toss is before the start.")
        if winner not in ('home', 'away'):
            raise LiveMatchError("Tap the team that won the toss.")
        if choice not in TOSS_CHOICES:
            raise LiveMatchError("Tap what they chose: to raid first or the court.")
        doc['toss'] = {'winner': winner, 'choice': choice, 'at': _iso(), 'ts': _now()}
        if is_pkl(doc):
            doc['first_raid'] = winner if choice == 'raid' else _other(winner)
            _replay_into(doc)
    return _change(db, event_id, match_id, tap, apply)


def set_timings(db, event_id: str, match_id: str, tap: str, half_minutes, break_minutes) -> dict:
    """The length of each half and of the break, in minutes, before the start
    (the break's again at half time)."""
    def number(value, low, high, what):
        try:
            n = int(str(value).strip())
        except (TypeError, ValueError):
            raise LiveMatchError(f"{what} is a number of minutes.")
        if not low <= n <= high:
            raise LiveMatchError(f"{what} is {low} to {high} minutes.")
        return n

    def apply(doc):
        phase = doc.get('phase')
        if phase not in ('not_started', 'half_time'):
            raise LiveMatchError("Set the timings before the start or at half time.")
        doc['half_minutes'] = number(half_minutes, *HALF_MINUTES_RANGE, 'A half')
        doc['break_minutes'] = number(break_minutes, *BREAK_MINUTES_RANGE, 'The break')
    return _change(db, event_id, match_id, tap, apply)


def _toss_state(doc: dict, names: dict) -> Optional[dict]:
    toss = doc.get('toss') or {}
    side = toss.get('winner')
    if side not in ('home', 'away'):
        return None
    team = names.get(doc.get(side), '')
    if toss.get('choice') == 'raid':
        chose = 'chose to raid first'
    else:
        chose = f"chose the court · {names.get(doc.get(_other(side)), '')} raid first"
    return {'winner': side, 'team_id': doc.get(side), 'team_name': team, 'choice': toss.get('choice'),
            'chose': chose, 'text': f"{team} won the toss and {chose}", 'at': toss.get('at') or '',
            'age': int(max(0.0, _now() - float(toss.get('ts') or 0))) if toss.get('ts') else None}


def _half_seconds(doc):
    return int(doc.get('half_minutes') or DEFAULT_HALF_MINUTES) * 60


def _break_left(doc, now=None):
    """Seconds left of the break at half time, None outside it."""
    if doc.get('phase') != 'half_time':
        return None
    since = (doc.get('break') or {}).get('since')
    minutes = doc.get('break_minutes')
    total = int(DEFAULT_BREAK_MINUTES if minutes is None else minutes) * 60
    if not since:
        return total
    return int(max(0.0, total - ((now or _now()) - float(since))))


OUTCOME_TEXT = {'touch': '{n} touch{es}', 'bonus': 'bonus', 'empty': 'empty raid', 'tackled': 'tackled',
                'line_out': 'raider out of court', 'time_over': 'raid time over'}


def secs_text(ev: dict) -> str:
    """How long a raid took (UPG-413): 'back in 12 s', or '31 s' when he didn't get back."""
    if ev.get('type') != 'raid' or ev.get('secs') is None:
        return ''
    back = ev.get('outcome') in ('touch', 'bonus', 'empty')
    return f"{'back in ' if back else ''}{int(ev['secs'])} s"


def event_text(ev: dict, names: dict, doc: dict) -> str:
    """One PKL-mode raid or call, as the scorer's log and the boards show it."""
    team = names.get(doc.get(ev.get('team')), '') if ev.get('team') else ''
    kind = ev.get('type')
    if kind == 'raid':
        n = int(ev.get('touches') or len(ev.get('touched') or []) or 0)
        how = OUTCOME_TEXT.get(ev.get('outcome'), '').format(n=n, es='' if n == 1 else 'es')
        if ev.get('bonus'):
            how += ' + bonus'
        if ev.get('bonus_missed'):
            how += ', bonus not given'
        pts = sum(e['points'] for e in doc.get('log') or [] if e.get('event') == ev.get('id') and e['team'] == ev['team'])
        given = sum(e['points'] for e in doc.get('log') or [] if e.get('event') == ev.get('id') and e['team'] != ev['team'])
        side, d = ev.get('team'), _other(ev.get('team') or 'home')
        who = f" ({tag(doc, side, ev['raider'])})" if ev.get('raider') else ''
        tackler = f" by {_caught_by(doc, d, ev)}" if ev.get('tackler') else ''
        parts = [f"Raid · {team}{who}: {how}{tackler}"]
        if pts:
            parts.append(f"+{pts}")
        if given:
            parts.append(f"+{given} to the defenders")
        if ev.get('touched'):
            parts.append('out ' + ', '.join(tag(doc, d, x) for x in ev['touched']))
        elif ev.get('raider') and ev.get('outcome') == 'tackled':
            parts.append(f"{tag(doc, side, ev['raider'])} out")
        parts += [e['label'] for e in doc.get('log') or []
                  if e.get('event') == ev.get('id') and e['kind'] in ('all_out', 'super_tackle', 'do_or_die')]
        return ' · '.join(parts)
    return _call_text(ev, team, kind, doc)


def feed_text(ev: dict, names: dict, doc: dict) -> str:
    """One raid as the public follows it (UPG-421): 'Garuda Sena · #7 Arjun ·
    2 touches +2 · out #3, #9'; a call as the scorer's log says it."""
    if ev.get('type') != 'raid':
        return event_text(ev, names, doc)
    side, d = ev.get('team'), _other(ev.get('team') or 'home')
    n = int(ev.get('touches') or len(ev.get('touched') or []) or 0)
    how = OUTCOME_TEXT.get(ev.get('outcome'), '').format(n=n, es='' if n == 1 else 'es')
    if ev.get('bonus'):
        how += ' + bonus'
    if ev.get('bonus_missed'):
        how += ', bonus not given'
    mine = sum(e['points'] for e in doc.get('log') or [] if e.get('event') == ev.get('id') and e['team'] == side)
    given = sum(e['points'] for e in doc.get('log') or [] if e.get('event') == ev.get('id') and e['team'] != side)
    parts = [names.get(doc.get(side), '')]
    if ev.get('raider'):
        parts.append(tag(doc, side, ev['raider']))
    parts.append(f"{how} +{mine}" if mine else how)
    if ev.get('touched'):
        parts.append('out ' + ', '.join(_number_or_name(doc, d, x) for x in ev['touched']))
    if ev.get('outcome') == 'tackled' and ev.get('tackler'):     # "caught by" (UPG-453)
        parts.append(f"caught by {_caught_by(doc, d, ev)} +{given}")
    elif given:
        parts.append(f"+{given} to {names.get(doc.get(d), '')}")
    parts += [e['label'] for e in doc.get('log') or []
              if e.get('event') == ev.get('id') and e['kind'] in ('all_out', 'super_tackle', 'do_or_die')]
    return ' · '.join(p for p in parts if p)


def _number_or_name(doc, side, name):
    number = jersey_of(doc, side, name)
    return f"#{number}" if number else name


def _caught_by(doc, side, ev):
    """'#1 Bharat', or '#1 Bharat with #5 Kiran' when more caught him (UPG-448)."""
    text = tag(doc, side, ev['tackler'])
    if ev.get('assists'):
        text += ' with ' + ', '.join(tag(doc, side, x) for x in ev['assists'])
    return text


def stop_text(ev: dict, team: str, doc: dict) -> str:
    """An injury break or official time-out (UPG-449): 'Injury break · #4 Arjun (Garuda Sena)'."""
    label = STOPPAGES.get(ev.get('reason'), 'Clock stopped')
    if ev.get('player'):
        return f"{label} · {tag(doc, ev.get('team'), ev['player'])} ({team})"
    return f"{label} · {team}" if team else label


def _call_text(ev: dict, team: str, kind: str, doc: dict) -> str:
    if kind == 'technical':
        why = TECH_REASONS.get(ev.get('reason') or '')
        return f"Technical point +1 · {team}" + (f" · {why}" if why else '')
    if kind == 'card':                            # UPG-447
        who = tag(doc, ev.get('team'), ev['player']) + f" ({team})" if ev.get('player') else f"a {team} player"
        return f"{CARDS.get(ev.get('card'), 'Card')} · {who} · {CARD_EFFECT.get(ev.get('card'), '')}"
    if kind == 'stoppage':
        return stop_text(ev, team, doc) + ' · clock stopped'
    if kind == 'out_of_bounds' and ev.get('where') == 'lobby':     # UPG-451
        if ev.get('player'):
            return f"Lobby · {tag(doc, ev.get('team'), ev['player'])} ({team}) went into the lobby before a struggle: out"
        return f"Lobby · a {team} player went into the lobby before a struggle: out"
    if kind == 'out_of_bounds':
        if ev.get('player'):
            return f"Out of bounds · {tag(doc, ev.get('team'), ev['player'])} ({team}) is out"
        return f"Out of bounds · a {team} player is out"
    if kind == 'timeout':
        return f"Time-out · {team}"
    if kind == 'review':
        return f"Review · {team}: {'upheld' if ev.get('upheld') else 'not upheld'}"
    if kind == 'mat':
        return f"Mat corrected · {team} {'+1' if int(ev.get('change') or 0) > 0 else '−1'} player"
    if kind == 'sub':
        return f"Substitution · {team}: {tag(doc, ev.get('team'), ev.get('on'))} for {tag(doc, ev.get('team'), ev.get('off'))}"
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
    final = doc.get('final')
    if isinstance(final, dict):          # the final score typed in by the scorer (UPG-463)
        for side in ('home', 'away'):
            out[side]['total'] = int(final.get(side) or 0)
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
            if needs_lineup(event, doc) and not named(doc):
                raise LiveMatchError(f"Choose each team's {MAT} players first, then save the line-ups.")
            doc['phase'] = 'first_half'
            if is_pkl(doc) and first in ('home', 'away'):
                doc['first_raid'] = first
                _replay_into(doc)
            _start_clock(doc, reset=True)
        elif action == 'pause' and phase in ('first_half', 'second_half'):
            _stop_clock(doc)
            doc.pop('raid_clock', None)
        elif action == 'resume' and phase in ('first_half', 'second_half'):
            if not (doc.get('clock') or {}).get('running'):
                _start_clock(doc)
        elif action == 'half_time' and phase == 'first_half':
            doc['phase'] = 'half_time'
            doc.pop('raiding_now', None)
            doc.pop('raid_clock', None)
            doc['break'] = {'since': _now()}       # the break counts down (UPG-439)
            _stop_clock(doc)
            if is_pkl(doc):
                _replay_into(doc)          # the other team raids first in the 2nd half
        elif action == 'second_half' and phase == 'half_time':
            doc['phase'] = 'second_half'
            doc.pop('break', None)
            _start_clock(doc, reset=True)  # first: a yellow card counts the 2nd half from 0 (UPG-447)
            if is_pkl(doc):
                _replay_into(doc)
        elif action == 'full_time' and phase == 'second_half':
            doc.pop('raiding_now', None)
            doc.pop('raid_clock', None)
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
                         'tiebreak': played.get('tiebreak'), 'ts': _now()}
        if not (doc.get('potm') or {}).get('chosen'):     # the scorer's own choice stays (UPG-422)
            doc['potm'] = player_of_the_match(doc)
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


def player_of_the_match(doc: dict) -> Optional[dict]:
    """The match's best player at full time (UPG-422): the most points, raid and
    tackle; level, the winning team's player, then more raid points (then the
    name, so it is always the same one). None when no points name a player."""
    winner = (doc.get('result') or {}).get('winner')
    rows = []
    for (team_id, player), pts in _match_players(doc).items():
        side = 'home' if team_id == doc.get('home') else 'away'
        rows.append((-(pts['raid'] + pts['tackle']), team_id != winner, -pts['raid'], player.lower(), side, player))
    if not rows:
        return None
    best = min(rows)
    return {'team': best[4], 'name': best[5], 'chosen': False}


def set_potm(db, event_id: str, event: dict, match_id: str, tap: str, side: str, name: str) -> dict:
    """The scorer names another player of the match after full time (UPG-422)."""
    def apply(doc):
        if doc.get('phase') != 'full_time':
            raise LiveMatchError("The player of the match is named at full time.")
        if side not in ('home', 'away') or name not in players(event, doc[side]):
            raise LiveMatchError("Choose a player of one of the two teams.")
        doc['potm'] = {'team': side, 'name': name, 'chosen': True}
    return _change(db, event_id, match_id, tap, apply)


def _potm(doc: dict, names: dict) -> Optional[dict]:
    """The player of the match for the pages: name, jersey, team and his points."""
    p = doc.get('potm') or {}
    side = p.get('team')
    if not p.get('name') or side not in ('home', 'away') or doc.get('phase') != 'full_time':
        return None
    pts = _match_players(doc).get((doc.get(side), p['name'])) or {'raid': 0, 'tackle': 0}
    number = jersey_of(doc, side, p['name'])
    return {'team': side, 'team_name': names.get(doc.get(side), ''), 'name': p['name'], 'jersey': number,
            'tag': f"#{number} {p['name']}" if number else p['name'], 'raid': pts['raid'], 'tackle': pts['tackle'],
            'points': pts['raid'] + pts['tackle'], 'chosen': bool(p.get('chosen'))}


def _reopen(doc):
    doc['phase'] = 'second_half'
    doc['result'] = None
    doc.pop('final', None)                # back to the raids' own score (UPG-463)
    _stop_clock(doc)


def final_score(db, event_id: str, match_id: str, tap: str, home, away, winner: str = '') -> dict:
    """The scorer couldn't keep up (the owner, UPG-463): each team's final
    points typed in. The match ends with that score at once, in any phase (a
    finished one is corrected): the fixtures and tables take the result, and
    the boards, the public pages and the big screen show it. `winner`
    ('home', 'away' or a team id) only for a level score that needs one."""
    try:
        home, away = int(str(home).strip()), int(str(away).strip())
    except (TypeError, ValueError):
        raise LiveMatchError("Type each team's points as a number.")
    if not (0 <= home <= 999 and 0 <= away <= 999):
        raise LiveMatchError("Points are 0 to 999.")

    def apply(doc):
        win = doc.get(winner) if winner in ('home', 'away') else winner
        win = win if win in (doc.get('home'), doc.get('away')) else ''
        try:
            nt = services_sports.change(db, event_id, lambda cur, _e: services_sports.record_result(
                cur, match_id, home, away, win))
        except services_sports.TournamentError as exc:
            raise LiveMatchError(str(exc))
        played = _match(nt, match_id)
        doc['final'] = {'home': home, 'away': away}
        doc['phase'] = 'full_time'
        for key in ('raiding_now', 'raid_clock', 'break', 'shootout'):
            doc.pop(key, None)
        _stop_clock(doc)
        doc['result'] = {'home': home, 'away': away, 'winner': played.get('winner'),
                         'tiebreak': played.get('tiebreak'), 'ts': _now(), 'typed': True}
        if not (doc.get('potm') or {}).get('chosen'):
            doc['potm'] = player_of_the_match(doc)
    return _change(db, event_id, match_id, tap, apply)


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


def _squad(db, event_id: str, tid: str) -> tuple:
    """(names, {name: jersey number}) of a team: the lead, then the members.
    Kept a minute, so a tap doesn't read the registrations again (UPG-403)."""
    key = ('squad', event_id, tid)
    hit = _cache.get(key)
    if hit and hit[0] > _now():
        return hit[1]
    snap = db.collection('registrations').document(tid).get()
    reg = (snap.to_dict() or {}) if snap.exists else {}
    rows = [{'name': reg.get('lead_name'), 'jersey': reg.get('lead_jersey')}] + [
        m for m in reg.get('members') or [] if isinstance(m, dict)]
    names, numbers = [], {}
    for row in rows:
        name = ' '.join(str(row.get('name') or '').split())
        if not name:
            continue
        if name not in names:
            names.append(name)
        number = str(row.get('jersey') or '').strip()
        if number and not numbers.get(name):   # the lead's own row has it (UPG-405)
            numbers[name] = number
    value = (tuple(names), dict(numbers))
    _cache[key] = (_now() + SQUAD_SECONDS, value)
    return value


def roster(db, event_id: str, tid: str) -> list:
    """A team's players for the public page's team details (UPG-441): the lead
    first, then the members; each one's jersey number and name, position and
    age. Never the date of birth, email, phone or USN. Kept a minute."""
    import services_export
    key = ('roster', event_id, tid)
    hit = _cache.get(key)
    if hit and hit[0] > _now():
        return hit[1]
    snap = db.collection('registrations').document(tid).get() if tid else None
    reg = (snap.to_dict() or {}) if snap is not None and snap.exists else {}
    answers = reg.get('form_answers') if isinstance(reg.get('form_answers'), dict) else {}
    lead_row = services_export._lead_row(reg)
    lead = {k: lead_row.get(k) or answers.get(f'lead_{k}') or reg.get(f'lead_{k}')
            for k in ('jersey', 'jersey_name', 'dob', 'position')}
    rows = [dict(lead, name=reg.get('lead_name'), lead=True)] + [
        dict(m, lead=False) for m in reg.get('members') or [] if isinstance(m, dict) and m is not lead_row]
    out, seen = [], set()
    for row in rows:
        name = ' '.join(str(row.get('name') or '').split())
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({'name': name, 'jersey': str(row.get('jersey') or '').strip(),
                    'jersey_name': str(row.get('jersey_name') or '').strip().upper(),
                    'position': str(row.get('position') or '').strip(),
                    'age': services_export._age(row.get('dob')), 'lead': bool(row.get('lead'))})
    _cache[key] = (_now() + SQUAD_SECONDS, out)
    return out


def squads(db, event_id: str, team_ids) -> dict:
    """Team id → its players' names: the lead, then the members."""
    return {tid: list(_squad(db, event_id, tid)[0]) for tid in team_ids if tid}


def jerseys(db, event_id: str, team_ids) -> dict:
    """Team id → {player's name: jersey number} (UPG-405), from the same cache as `squads`."""
    return {tid: dict(_squad(db, event_id, tid)[1]) for tid in team_ids if tid}


def refresh_jerseys(db, event_id: str, team_ids) -> int:
    """After the SPOC changes jersey numbers (UPG-461): the teams' squads are
    read again, and each line-up saved for a match not yet over takes the new
    numbers (a finished match keeps the ones it was played in). How many
    matches changed."""
    team_ids = {t for t in team_ids if t}
    for key in [k for k in list(_cache) if isinstance(k, tuple) and len(k) == 3
                and k[0] in ('squad', 'roster') and k[1] == event_id and k[2] in team_ids]:
        _cache.pop(key, None)
    _cache.pop(('screen', event_id), None)
    changed = 0
    for snap in list(db.collection(COLLECTION).where('event_id', '==', event_id).stream()):
        d = snap.to_dict() or {}
        match_id = d.get('match_id')
        if not match_id or d.get('phase') == 'full_time' or not any(
                d.get(side) in team_ids and squad_of(d, side) for side in ('home', 'away')):
            continue
        with _lock(doc_id(event_id, match_id)):
            doc = get(db, event_id, match_id) or {}
            moved = False
            for side in ('home', 'away'):
                if doc.get(side) not in team_ids:
                    continue
                numbers = _squad(db, event_id, doc[side])[1]
                for p in squad_of(doc, side):
                    number = str(numbers.get(p.get('name')) or '')
                    if str(p.get('jersey') or '') != number:
                        p['jersey'], moved = number, True
            if moved:
                _save(db, event_id, match_id, doc)
                changed += 1
    return changed


def with_jerseys(rows: list, numbers: dict) -> list:
    """Player-stat rows (player_stats) with each player's jersey number, '' when none."""
    return [dict(r, jersey=(numbers.get(r.get('team_id')) or {}).get(r.get('player'), '')) for r in rows]


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
    if _cards_running(mat):                  # a yellow card's 2 minutes count down (UPG-447)
        mat = replay(doc, clock_seconds(doc))
        doc.pop('_log', None)
    sh = shootout_state(doc, names) if doc.get('shootout') else None
    if is_pkl(doc):
        recent = [event_text(e, names, doc) for e in reversed((doc.get('events') or [])[-last:])]
        recent_secs = [secs_text(e) for e in reversed((doc.get('events') or [])[-last:])]
        feed_secs = [secs_text(e) for e in reversed((doc.get('events') or [])[-FEED:])]
    else:
        recent = [describe(e, names, doc) for e in reversed((doc.get('log') or [])[-last:])]
        recent_secs = feed_secs = [''] * len(recent)
    clock = clock_seconds(doc)
    half = _half_seconds(doc)
    breaking = doc.get('break_minutes')
    return {'phase': doc.get('phase'), 'phase_name': PHASE_NAMES.get(doc.get('phase'), ''),
            'clock': clock, 'running': bool((doc.get('clock') or {}).get('running')),
            'half_minutes': doc.get('half_minutes') or DEFAULT_HALF_MINUTES,
            # The half's time left and the break's (UPG-439); the raid clock (UPG-413); the toss (UPG-438)
            'break_minutes': DEFAULT_BREAK_MINUTES if breaking is None else int(breaking),
            'half_seconds': half,
            'left': max(0, half - clock) if doc.get('phase') in ('first_half', 'second_half') else None,
            'time_up': doc.get('phase') in ('first_half', 'second_half') and clock >= half,
            'break_left': _break_left(doc),
            'raid_clock': _raid_state(doc) if is_pkl(doc) else None,
            'raid_seconds': RAID_SECONDS,
            'raid_clock_on': not doc.get('raid_clock_off'),
            'toss': _toss_state(doc, names),
            'stopped_for': _stopped_for(doc, names),
            'result_text': _result_text(doc, names),
            'recent_secs': recent_secs,
            'feed_secs': feed_secs,
            'home': {'id': doc.get('home'), 'name': names.get(doc.get('home'), ''), **s['home']},
            'away': {'id': doc.get('away'), 'name': names.get(doc.get('away'), ''), **s['away']},
            'result': doc.get('result'),
            'recent': recent,
            'mode': doc.get('mode') or '',
            'mat': mat,
            'mat_text': mat_text(mat, names, doc) if mat and doc.get('phase') in ('first_half', 'second_half') else '',
            'shootout': sh,
            'shootout_text': shootout_text(sh, names, doc) if sh else '',
            'raiding_now': _raiding_now(doc, names),
            'lineup': lineups(doc),
            'potm': _potm(doc, names),
            'feed': ([feed_text(e, names, doc) for e in reversed((doc.get('events') or [])[-FEED:])]
                     if is_pkl(doc) else recent),
            'updated_at': doc.get('updated_at')}


def _result_text(doc: dict, names: dict) -> str:
    """Who won, once the match is over (UPG-456): 'Garuda Sena won by 4 points (24–20)'."""
    r = doc.get('result') or {}
    if doc.get('phase') != 'full_time' or not r:
        return ''
    return services_sports.result_text({'status': 'played', 'home': doc.get('home'), 'away': doc.get('away'),
                                        'home_score': r.get('home'), 'away_score': r.get('away'),
                                        'winner': r.get('winner'), 'tiebreak': r.get('tiebreak')}, names)


def _stopped_for(doc: dict, names: dict) -> str:
    """Why the clock is stopped, for the boards (UPG-449): 'Injury break · #4
    Arjun (Garuda Sena)' or 'Time-out · Vajra'; '' while it runs."""
    if doc.get('phase') not in ('first_half', 'second_half') or (doc.get('clock') or {}).get('running'):
        return ''
    last = (doc.get('events') or [{}])[-1] if is_pkl(doc) else {}
    team = names.get(doc.get(last.get('team')), '') if last.get('team') else ''
    if last.get('type') == 'stoppage':
        return stop_text(last, team, doc)
    if last.get('type') == 'timeout':
        return f"Time-out · {team}"
    return ''


def _raiding_now(doc: dict, names: dict) -> Optional[dict]:
    """The raider the scorer tapped, until the raid is recorded (UPG-420)."""
    now = doc.get('raiding_now') or {}
    if not now.get('name') or doc.get('phase') not in ('first_half', 'second_half'):
        return None
    side = now.get('team')
    return {'team': side, 'team_name': names.get(doc.get(side), ''), 'name': now['name'],
            'jersey': jersey_of(doc, side, now['name']), 'tag': tag(doc, side, now['name'])}


def lineups(doc: dict) -> Optional[dict]:
    """{'home': {'start': [{name, jersey}], 'subs': [...]}, 'away': …} once saved (UPG-417)."""
    lineup = doc.get('lineup') or {}
    if not lineup:
        return None
    out = {}
    for side in ('home', 'away'):
        start = (lineup.get(side) or {}).get('start') or []
        out[side] = {'start': [{'name': x, 'jersey': jersey_of(doc, side, x)} for x in start],
                     'subs': [p for p in squad_of(doc, side) if p['name'] not in start]}
    return out


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
        try:      # how many watch (UPG-440): each phone once, short like a streaming app
            value['watching'] = short_count(views(db, event_id, match_id).get('devices', 0))
        except Exception:
            value['watching'] = ''
    _cache[key] = (_now() + CACHE_SECONDS, value)
    return value


def live_matches(db, event_id: str) -> dict:
    """Match id → phase, for the event's matches being played now (cached a few seconds)."""
    key = ('live', event_id)
    hit = _cache.get(key)
    if hit and hit[0] > _now():
        return hit[1]
    value, toss, done = {}, None, {}
    for snap in db.collection(COLLECTION).where('event_id', '==', event_id).stream():
        d = snap.to_dict() or {}
        if d.get('phase') in IN_PLAY:
            value[d.get('match_id')] = d['phase']
        # Just finished: the big screen keeps its board with who won (UPG-456)
        ts = (d.get('result') or {}).get('ts')
        if d.get('phase') == 'full_time' and ts and _now() - float(ts) <= RESULT_SHOW_SECONDS:
            done[d.get('match_id')] = float(ts)
        # The newest toss of a match about to start, for the big screen (UPG-438)
        t = d.get('toss') or {}
        if d.get('phase') == 'not_started' and t.get('ts') and _now() - float(t['ts']) <= TOSS_FRESH_SECONDS:
            if toss is None or float(t['ts']) > float(toss['toss']['ts']):
                toss = {'match_id': d.get('match_id'), 'home': d.get('home'), 'away': d.get('away'), 'toss': t}
    _cache[key] = (_now() + CACHE_SECONDS, value)
    _cache[('toss', event_id)] = (_now() + CACHE_SECONDS, toss)
    _cache[('done', event_id)] = (_now() + CACHE_SECONDS, done)
    return value


def just_finished(db, event_id: str) -> dict:
    """Match id → when it ended, for the matches over in the last RESULT_SHOW_SECONDS (UPG-456)."""
    hit = _cache.get(('done', event_id))
    if not (hit and hit[0] > _now()):
        _cache.pop(('live', event_id), None)
        live_matches(db, event_id)
        hit = _cache.get(('done', event_id))
    return dict(hit[1]) if hit else {}


GENDER_LABELS = ('Men', 'Women', 'Mixed')


def watchable(db, events: list) -> list:
    """The tournaments a visitor can watch from the home page (UPG-457): listed
    events with fixtures and a match still to play (or being played), live ones
    first. Each is {id, label, title, live}; the label is the gender category
    ("Men", "Women") when that tells them apart, else the event's title."""
    found = []
    for ev in events or []:
        # An event whose fields aren't what a tournament keeps is skipped, not
        # the whole box (UPG-462)
        if not isinstance(ev, dict) or not ev.get('id'):
            continue
        t = ev.get('tournament') if isinstance(ev.get('tournament'), dict) else {}
        raw = t.get('matches')
        matches = [m for m in raw if isinstance(m, dict)] if isinstance(raw, list) else []
        if not matches:
            continue
        try:
            playing = live_matches(db, ev['id'])
        except Exception:
            playing = {}
        playing = [m for m in matches if m.get('id') in (playing or {})]   # this sheet's matches only
        if not playing and all(m.get('status') == 'played' for m in matches):
            continue                                    # the season is over
        details = ev.get('details') if isinstance(ev.get('details'), dict) else {}
        gender = str(details.get('gender') or '').strip()
        found.append({'id': ev['id'], 'title': str(ev.get('title') or 'Tournament'),
                      'gender': gender if gender in GENDER_LABELS else '', 'live': bool(playing)})
    genders = [w['gender'] for w in found]
    for w in found:
        unique = w['gender'] and genders.count(w['gender']) == 1
        w['label'] = w.pop('gender') if unique else w['title']
    found.sort(key=lambda w: (not w['live'], w['label']))
    return found


def toss_show(db, event_id: str, names: dict) -> Optional[dict]:
    """The toss just made in this event (the last TOSS_FRESH_SECONDS), for the
    big screen to play once: {key, home, away, toss (as _toss_state)}; else None."""
    hit = _cache.get(('toss', event_id))
    if not (hit and hit[0] > _now()):
        _cache.pop(('live', event_id), None)
        live_matches(db, event_id)
        hit = _cache.get(('toss', event_id))
    found = hit[1] if hit else None
    if not found:
        return None
    shown = _toss_state(found, names)
    if not shown:
        return None
    return {'key': f"{doc_id(event_id, found['match_id'])}:{found['toss'].get('at', '')}",
            'home': found['home'], 'away': found['away'], 'toss': shown}


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
