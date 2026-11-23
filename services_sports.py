"""
services_sports.py — sports tournaments: fixtures, results, standings (UPG-13).

A tournament is kept on its event as `tournament`:

    {'format': 'knockout' | 'league' | 'league_knockout',
     'sport': 'Kabaddi',                                    # optional
     'points': {'win': 3, 'draw': 1, 'loss': 0,             # league only
                'close_loss': 0, 'close_margin': 0},        # kabaddi: 1 within 7
     'playoffs': {'size': 4, 'seeds': [...]},               # league then knockout
     'legs': 2,                                             # each pair plays twice, home and away
     'pools': ['A', 'B'], 'cross': True,                    # two pools, an inter-pool round
     'teams':  [{'id': <registration id>, 'name': <team or lead name>,
                 'pool': 'A', 'seed': 1, 'logo': <url>}, …],
     'matches': [{'id': 'm1', 'round': 1, 'home': id|None, 'away': id|None,
                  'date': '', 'time': '', 'venue': '',
                  'home_score': None, 'away_score': None, 'winner': None,
                  'status': 'scheduled' | 'played' | 'bye',
                  'next': 'm5', 'next_side': 'home',        # knockout only
                  'stage': 'final' | 'third' | …,           # where it is in the draw
                  'loser_next': 'm8', 'loser_side': 'home',  # a semi-final's loser to the third-place match
                  'pool': 'A', 'leg': 2, 'cross': True}, …]}  # a pool match, its leg; an inter-pool match

Teams come from the event's confirmed registrations (UPG-08 teams are
registrations with members). A knockout gets byes up to the next power of
two; a bye's team goes straight through, and each result moves the winner on.
A league plays every pair once (circle method) and its table counts played,
won, drawn, lost, scored, conceded and points. A league then knockout plays
the league, then its top 4 (or 2) play off (UPG-350).

A league then knockout may have two pools, A and B (UPG-381), like a
kabaddi premier league: each pool plays its own league, once or twice
(home and away, UPG-382), then an inter-pool round, A1 v B1, A2 v B2, …,
whose points count in each team's own pool table (UPG-383), and then 1st A
v 2nd B and 1st B v 2nd A in the semi-finals (UPG-384). The matches are
numbered M-01, M-02, … pool A first, then pool B, then the inter-pool round,
then the playoffs; a schedule file sets every date, time and venue at once
(UPG-385); each team may have a logo (UPG-386).

Once the deciding matches are played, `placings` gives each team's place and
`publish` makes it the event's result (UPG-342): places on the registrations,
the result email and WhatsApp to the placed teams, a push to everyone, and the
position certificates.

Every change to the fixtures goes through `change`, which holds a short lock
across every copy of the app while it reads the tournament, changes it and
writes it back, so two results saved at the same moment both stay (UPG-354).

Mistakes are fixed from the page, not in code (UPG-355 to UPG-359): a result
cleared (and the knockout winner taken back), a walkover, a team withdrawn or
brought back, renamed, replaced or added late, a match's teams changed, the
points rule changed, the playoffs undone, and corrected results published again.
"""
import contextlib
import datetime
import logging
import math
import threading
import time

log = logging.getLogger(__name__)

DEFAULT_POINTS = {'win': 3, 'draw': 1, 'loss': 0, 'close_loss': 0, 'close_margin': 0}
# A kabaddi league (UPG-350): 5 a win, 3 a tie, 1 for losing by 7 points or fewer
KABADDI_POINTS = {'win': 5, 'draw': 3, 'loss': 0, 'close_loss': 1, 'close_margin': 7}
# PKL Season 12 (2025) (UPG-396): 2 a win, 0 a loss, and no ties: a match level at
# full time goes to a tie-breaker (a five-raid shootout, then a golden raid, then
# a coin toss), whose winner takes the win; the match keeps its full-time score.
PKL12_POINTS = {'win': 2, 'draw': 0, 'loss': 0, 'close_loss': 0, 'close_margin': 0}
RULES = {'pkl12': 'PKL Season 12: win 2, loss 0, a tie goes to the tie-breaker',
         'classic': 'Older PKL: win 5, tie 3, lost by 7 or fewer 1, loss 0'}
TIEBREAK_WAYS = {'shootout': 'shootout', 'golden': 'golden raid', 'toss': 'coin toss'}
FORMATS = ('knockout', 'league', 'league_knockout')
POOLS = ('A', 'B')                       # two pools (UPG-381)
FORMAT_NAMES = {'knockout': 'Knockout', 'league': 'League', 'league_knockout': 'League then knockout'}
KNOCKOUT_STAGES = ('semi', 'final', 'third')
STAGE_NAMES = {'final': 'Final', 'semi': 'Semi-final', 'third': 'Third place'}


class TournamentError(ValueError):
    pass


# ── One change at a time (UPG-354) ─────────────────────────────────────────
LOCK_SECONDS = 10        # a lock older than this is taken over (its holder died)
LOCK_WAIT = 8.0
_plocks: dict = {}
_plocks_guard = threading.Lock()


def _process_lock(event_id):
    with _plocks_guard:
        return _plocks.setdefault(event_id, threading.Lock())


@contextlib.contextmanager
def _tournament_lock(event_id: str):
    """A lease in the shared counter table (one conditional UPDATE takes it),
    so two copies of the app never change one tournament at once."""
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError
    from db_pg import get_session
    from models_pg import TicketTypeSale
    key = f"{event_id}:tournament-lock"
    try:
        with get_session(primary=True) as s:
            if s.get(TicketTypeSale, key) is None:
                s.add(TicketTypeSale(key=key, sold=0))
    except IntegrityError:
        pass                                   # another copy made it first
    deadline = time.time() + LOCK_WAIT
    while True:
        now = int(time.time())
        with get_session(primary=True) as s:
            taken = s.execute(update(TicketTypeSale)
                              .where(TicketTypeSale.key == key, TicketTypeSale.sold < now - LOCK_SECONDS)
                              .values(sold=now)).rowcount == 1
        if taken:
            break
        if time.time() > deadline:
            raise TournamentError("Someone else is saving a change to this tournament. Try again in a moment.")
        time.sleep(0.05)
    try:
        yield
    finally:
        with get_session(primary=True) as s:
            s.execute(update(TicketTypeSale).where(TicketTypeSale.key == key, TicketTypeSale.sold == now)
                      .values(sold=0))


def change(db, event_id: str, fn) -> dict:
    """Read the event's tournament afresh, apply `fn(tournament, event)` (which
    returns the new tournament or raises TournamentError) and save it, all under
    the lock. Returns the saved tournament."""
    with _process_lock(event_id), _tournament_lock(event_id):
        ref = db.collection('events').document(event_id)
        snap = ref.get()
        event = dict(snap.to_dict() or {}, id=event_id)
        t = fn(event.get('tournament') or {}, event)
        ref.update({'tournament': t})
        return t


def confirmed_teams(db, event_id: str) -> list:
    """[{'id', 'name'}] for every registration that isn't cancelled, in registration order;
    with 'logo' when the lead uploaded the team's logo at registration (UPG-405)."""
    teams = []
    regs = [(d.id, d.to_dict() or {}) for d in db.collection('registrations').where('event_id', '==', event_id).stream()]
    for rid, r in sorted(regs, key=lambda x: str(x[1].get('registered_at') or '')):
        if str(r.get('status') or '').strip().lower() in ('cancelled', 'refunded', 'waitlisted', 'pending payment'):
            continue
        name = r.get('team_name') if r.get('team_name') not in (None, '', 'Individual') else r.get('lead_name')
        team = {'id': rid, 'name': name or rid}
        if r.get('team_logo'):
            team['logo'] = r['team_logo']
        teams.append(team)
    return teams


def _match(mid, rnd, home=None, away=None):
    return {'id': mid, 'round': rnd, 'home': home, 'away': away, 'date': '', 'time': '', 'venue': '',
            'home_score': None, 'away_score': None, 'winner': None, 'status': 'scheduled',
            'next': None, 'next_side': None}


def knockout(teams: list, third_place: bool = False) -> list:
    """A single-elimination bracket with byes; byes are settled at once. With
    `third_place`, the semi-finals' losers meet for third (UPG-342)."""
    n = len(teams)
    if n < 2:
        raise TournamentError("A knockout needs at least 2 teams.")
    if third_place and n < 4:
        raise TournamentError("A third-place match needs at least 4 teams.")
    size = 2 ** math.ceil(math.log2(n))
    byes = size - n
    rounds = int(math.log2(size))
    matches, counter, by_round = [], 0, []
    for rnd in range(1, rounds + 1):
        row = []
        for _ in range(size // (2 ** rnd)):
            counter += 1
            m = _match(f"m{counter}", rnd)
            row.append(m)
            matches.append(m)
        by_round.append(row)
    for rnd in range(rounds - 1):           # where each winner goes next
        for i, m in enumerate(by_round[rnd]):
            m['next'] = by_round[rnd + 1][i // 2]['id']
            m['next_side'] = 'home' if i % 2 == 0 else 'away'
    queue = list(teams)
    for i, m in enumerate(by_round[0]):     # the first `byes` matches get one team
        m['home'] = queue.pop(0)['id']
        m['away'] = None if i < byes else queue.pop(0)['id']
    by_round[-1][0]['stage'] = 'final'
    if rounds >= 2:
        for m in by_round[-2]:
            m['stage'] = 'semi'
    if third_place:
        counter += 1
        third = dict(_match(f"m{counter}", rounds), stage='third')
        matches.append(third)
        for i, m in enumerate(by_round[-2]):
            m.update(loser_next=third['id'], loser_side='home' if i % 2 == 0 else 'away')
    for m in by_round[0]:
        if m['away'] is None:
            m.update(status='bye', winner=m['home'])
            _advance(matches, m)
    return matches


def league(teams: list) -> list:
    """Every pair once, in rounds (circle method)."""
    if len(teams) < 2:
        raise TournamentError("A league needs at least 2 teams.")
    ids = [t['id'] for t in teams]
    if len(ids) % 2:
        ids.append(None)                      # a resting team each round
    n, matches, counter = len(ids), [], 0
    for rnd in range(1, n):
        for i in range(n // 2):
            home, away = ids[i], ids[n - 1 - i]
            if home is not None and away is not None:
                counter += 1
                matches.append(_match(f"m{counter}", rnd, home, away))
        ids = [ids[0]] + [ids[-1]] + ids[1:-1]
    return matches


def _legs(matches: list, legs: int) -> list:
    """Leg 2 plays every leg-1 match again with home and away swapped, in
    rounds after leg 1's (UPG-382)."""
    if legs != 2:
        return matches
    last = max([m['round'] for m in matches] or [0])
    for m in matches:
        m['leg'] = 1
    again = [dict(_match('', m['round'] + last, m['away'], m['home']), leg=2) for m in matches]
    return matches + again


def _number(matches: list) -> list:
    for i, m in enumerate(matches, start=1):
        m['id'] = f"m{i}"
    return matches


def _pooled(teams: list, legs: int, cross: bool) -> list:
    """Each pool's league (pool A's matches first, then pool B's), then the
    inter-pool round: the same seed from each pool (UPG-381 to UPG-383)."""
    by_pool = {p: sorted([x for x in teams if x.get('pool') == p], key=lambda x: x.get('seed') or 0) for p in POOLS}
    for p, members in by_pool.items():
        if len(members) < 2:
            raise TournamentError(f"Pool {p} needs at least 2 teams.")
    matches = []
    for p in POOLS:
        for m in _legs(league(by_pool[p]), legs):
            m.update(pool=p, stage='league')
            matches.append(m)
    if cross:
        rnd = max(m['round'] for m in matches) + 1
        for a, b in zip(by_pool['A'], by_pool['B']):
            matches.append(dict(_match('', rnd, a['id'], b['id']), stage='league', cross=True))
    return _number(matches)


def generate(teams: list, fmt: str, points: dict = None, third_place: bool = False, sport: str = '',
             legs: int = 1, pools: dict = None, cross: bool = False, tiebreak: bool = False) -> dict:
    """`pools` maps a team id to ('A' or 'B', seed); only a league then knockout has pools.
    `tiebreak`: a match level at full time is decided by a tie-breaker (PKL Season 12, UPG-396)."""
    if fmt not in FORMATS:
        raise TournamentError("Choose knockout, league, or league then knockout.")
    legs = 2 if str(legs) == '2' else 1
    if pools and fmt != 'league_knockout':
        raise TournamentError("Pools need the format League then knockout: the pools' top teams play the semi-finals.")
    if pools:
        teams = [dict(x, pool=(pools.get(x['id']) or ('', 0))[0], seed=(pools.get(x['id']) or ('', 0))[1])
                 for x in teams]
        if any(x['pool'] not in POOLS for x in teams):
            raise TournamentError("Put every team in pool A or pool B.")
        for p in POOLS:
            seeds = [x['seed'] for x in teams if x['pool'] == p]
            if len(set(seeds)) != len(seeds):
                raise TournamentError(f"Two teams in pool {p} have the same seed number.")
        matches = _pooled(teams, legs, cross)
    elif fmt == 'knockout':
        matches = knockout(teams, third_place)
    else:
        matches = _number(_legs(league(teams), legs))
        if fmt == 'league_knockout':
            if len(teams) < 3:
                raise TournamentError("A league then knockout needs at least 3 teams.")
            for m in matches:
                m['stage'] = 'league'
    t = {'format': fmt, 'points': dict(DEFAULT_POINTS, **(points or {})), 'teams': teams, 'matches': matches}
    if sport:
        t['sport'] = sport
    if fmt == 'league_knockout':
        t['third_place'] = bool(third_place)
    if legs == 2 and fmt != 'knockout':
        t['legs'] = 2
    if pools:
        t['pools'] = list(POOLS)
        t['cross'] = bool(cross)
    if tiebreak:
        t['tiebreak'] = True
    return t


def tiebreak_on(tournament: dict) -> bool:
    """Ties go to a tie-breaker (UPG-396)."""
    return bool(tournament.get('tiebreak'))


def needs_winner(tournament: dict, m: dict) -> bool:
    """A level score needs a winner: every knockout match, and every match when ties go to a tie-breaker."""
    return knockout_match(tournament, m) or tiebreak_on(tournament)


def tiebreak_text(m: dict, names: dict) -> str:
    """'Vajra won the shootout 4–3' for a match decided by the tie-breaker, else ''."""
    tb = m.get('tiebreak') or {}
    if not tb or not m.get('winner'):
        return ''
    way = TIEBREAK_WAYS.get(tb.get('decided'), 'tie-breaker')
    score = f" {tb['home']}–{tb['away']}" if tb.get('decided') == 'shootout' and tb.get('home') is not None else ''
    return f"{names.get(m['winner'], '')} won the {way}{score}"


def preset_points(sport: str) -> dict:
    """The points a sport's league uses by default (UPG-350)."""
    return dict(KABADDI_POINTS if str(sport or '').strip().lower() == 'kabaddi' else DEFAULT_POINTS)


def event_defaults(event: dict) -> dict:
    """The generate form's starting format, sport and points, from the event's own details."""
    details = event.get('details') or {}
    sport = str(details.get('sport') or '').strip()
    fmt = {'knockout': 'knockout', 'league': 'league', 'league then knockout': 'league_knockout'}.get(
        str(details.get('format') or '').strip().lower(), 'knockout')
    t = event.get('tournament') or {}
    return {'sport': t.get('sport') or sport, 'format': t.get('format') or fmt,
            'points': dict(DEFAULT_POINTS, **(t.get('points') or {})) if t.get('points') else preset_points(sport)}


def is_kabaddi(tournament: dict) -> bool:
    return str(tournament.get('sport') or '').strip().lower() == 'kabaddi'


def knockout_match(tournament: dict, m: dict) -> bool:
    """A match someone has to win: every knockout match, and a league then knockout's playoffs."""
    return tournament.get('format') == 'knockout' or (
        tournament.get('format') == 'league_knockout' and m.get('stage') in KNOCKOUT_STAGES)


def league_done(tournament: dict) -> bool:
    league_matches = [m for m in tournament.get('matches') or [] if m.get('stage') not in KNOCKOUT_STAGES]
    return bool(league_matches) and all(m.get('status') in ('played', 'bye') for m in league_matches)


def has_playoffs(tournament: dict) -> bool:
    return any(m.get('stage') in KNOCKOUT_STAGES for m in tournament.get('matches') or [])


def make_playoffs(tournament: dict, size: int = 4, third_place: bool = None) -> dict:
    """After the league stage: the top 4 play semi-finals (1 v 4, 2 v 3) and a
    final, and a third-place match if wanted; or the top 2 play the final (UPG-350)."""
    t = dict(tournament)
    if t.get('format') != 'league_knockout':
        raise TournamentError("Only a league then knockout has playoffs.")
    if has_playoffs(t):
        raise TournamentError("The playoffs are made already.")
    if not league_done(t):
        raise TournamentError("Finish the league first: every league match needs a result.")
    if size not in (2, 4):
        raise TournamentError("The playoffs take the top 2 or the top 4.")
    if t.get('pools'):                        # 1st A v 2nd B, 1st B v 2nd A (UPG-384)
        a, b = standings(t, 'A'), standings(t, 'B')
        need = size // 2
        if len(a) < need or len(b) < need:
            raise TournamentError(f"Each pool needs at least {need} teams.")
        seeds = [a[0]['id'], b[1]['id'], b[0]['id'], a[1]['id']] if size == 4 else [a[0]['id'], b[0]['id']]
    else:
        table = standings(t)
        if len(table) < size:
            raise TournamentError(f"The top {size} need at least {size} teams.")
        seeds = [row['id'] for row in table[:size]]
    third_place = t.get('third_place') if third_place is None else third_place
    matches = [dict(m) for m in t.get('matches') or []]
    counter = max(int(str(m['id']).lstrip('m') or 0) for m in matches)
    rnd = max(int(m.get('round') or 0) for m in matches) + 1

    def new(stage, rnd_, home=None, away=None):
        nonlocal counter
        counter += 1
        m = dict(_match(f"m{counter}", rnd_, home, away), stage=stage)
        matches.append(m)
        return m

    if size == 4 and t.get('pools'):
        semi1 = new('semi', rnd, seeds[0], seeds[1])
        semi2 = new('semi', rnd, seeds[2], seeds[3])
    elif size == 4:
        semi1 = new('semi', rnd, seeds[0], seeds[3])
        semi2 = new('semi', rnd, seeds[1], seeds[2])
    if size == 4:
        final = new('final', rnd + 1)
        semi1.update(next=final['id'], next_side='home')
        semi2.update(next=final['id'], next_side='away')
        if third_place:
            third = new('third', rnd + 1)
            semi1.update(loser_next=third['id'], loser_side='home')
            semi2.update(loser_next=third['id'], loser_side='away')
    else:
        new('final', rnd, seeds[0], seeds[1])
    t['matches'] = matches
    t['playoffs'] = {'size': size, 'seeds': seeds}
    return t


def stage_name(m: dict) -> str:
    if m.get('stage') in STAGE_NAMES:
        return STAGE_NAMES[m['stage']]
    if m.get('cross'):
        return 'Inter-pool'
    if m.get('pool'):
        return f"Pool {m['pool']} · {'Leg ' + str(m['leg']) + ' · ' if m.get('leg') else ''}Round {m.get('round')}"
    return f"{'League round' if m.get('stage') == 'league' else 'Round'} {m.get('round')}"


def _find(matches, mid):
    for m in matches:
        if m['id'] == mid:
            return m
    raise TournamentError("No such match.")


def _advance(matches, m):
    if m.get('next') and m.get('winner'):
        nxt = _find(matches, m['next'])
        nxt[m['next_side']] = m['winner']
    if m.get('loser_next') and m.get('winner') and m.get('status') == 'played':
        loser = m['away'] if m['winner'] == m['home'] else m['home']
        _find(matches, m['loser_next'])[m['loser_side']] = loser


def _loser(m):
    if m.get('status') != 'played' or not m.get('winner'):
        return None
    return m['away'] if m['winner'] == m['home'] else m['home']


def record_result(tournament: dict, match_id: str, home_score: int, away_score: int, winner: str = '',
                  tiebreak: dict = None) -> dict:
    """Enter or correct a result. A knockout needs a winner (the higher score,
    or the one chosen after a tie) and moves it on; a correction is refused
    once the next match has been played. When ties go to a tie-breaker (PKL
    Season 12, UPG-396) a league match level at full time needs its winner too;
    `tiebreak` is how it was decided ({'decided', 'home', 'away'}: a shootout's score)."""
    t = dict(tournament)
    matches = [dict(m) for m in t.get('matches') or []]
    m = _find(matches, match_id)
    if not m.get('home') or not m.get('away'):
        raise TournamentError("Both teams must be known before a result is entered.")
    if home_score < 0 or away_score < 0:
        raise TournamentError("Scores can't be negative.")
    if m.get('stage') == 'league' and has_playoffs(t):
        raise TournamentError("The playoffs were seeded from the league table, so its results can't change now.")
    m.update(home_score=home_score, away_score=away_score, status='played', played_at=_stamp())
    m.pop('walkover', None)
    m.pop('postponed', None)                   # played after all (UPG-394)
    m.pop('tiebreak', None)
    if home_score == away_score and needs_winner(t, m):
        if winner not in (m['home'], m['away']):
            raise TournamentError("It's a tie: choose who won the tie-breaker." if tiebreak_on(t)
                                  else "It's a tie: choose who goes through.")
        tb = dict(tiebreak or {})
        way = tb.get('decided') if tb.get('decided') in TIEBREAK_WAYS else 'tiebreak'
        m['tiebreak'] = {'decided': way, 'home': tb.get('home'), 'away': tb.get('away')}
    if knockout_match(t, m):
        if home_score != away_score:
            win = m['home'] if home_score > away_score else m['away']
        elif winner in (m['home'], m['away']):
            win = winner                       # decided on penalties, a tie-break, …
        else:
            raise TournamentError("It's a tie: choose who goes through.")
        _check_next(matches, m, win)
        m['winner'] = win
        _advance(matches, m)
        _settle_withdrawn(t, matches)
    elif home_score == away_score and tiebreak_on(t):
        m['winner'] = winner                   # the tie-breaker's winner takes the win (UPG-396)
    else:
        m['winner'] = (m['home'] if home_score > away_score else m['away'] if away_score > home_score else None)
    t['matches'] = matches
    return t


def _check_next(matches, m, win):
    """A knockout result that changes who goes through is refused once the
    match they went on to is played: clear that one first."""
    for key in ('next', 'loser_next'):
        if m.get(key):
            nxt = _find(matches, m[key])
            if nxt.get('status') == 'played' and m.get('winner') and m['winner'] != win:
                raise TournamentError(f"{stage_name(nxt)} (match {nxt['id'].upper()}) is already played with the "
                                      "team that went through. Clear that result first, then correct this one.")


# ── Fixing mistakes (UPG-355 to UPG-358) ───────────────────────────────────
def _copy(tournament):
    t = dict(tournament)
    t['matches'] = [dict(m) for m in t.get('matches') or []]
    t['teams'] = [dict(x) for x in t.get('teams') or []]
    return t, t['matches']


def clear_result(tournament: dict, match_id: str) -> dict:
    """Take a match's result back: it is to be played again, and in a knockout
    the team it sent on (and the loser sent to the third-place match) is taken
    back out. Refused while that next match has a result (UPG-355)."""
    t, matches = _copy(tournament)
    m = _find(matches, match_id)
    if m.get('status') == 'bye':
        raise TournamentError("A bye has no result to clear.")
    if m.get('status') != 'played':
        raise TournamentError("This match has no result yet.")
    if m.get('stage') == 'league' and has_playoffs(t):
        raise TournamentError("The playoffs were made from the league table. Undo the playoffs first.")
    for key, side in (('next', 'next_side'), ('loser_next', 'loser_side')):
        if m.get(key):
            nxt = _find(matches, m[key])
            if nxt.get('status') == 'played':
                raise TournamentError(f"{stage_name(nxt)} (match {nxt['id'].upper()}) is already played. "
                                      "Clear that result first.")
            nxt[m[side]] = None
    m.update(home_score=None, away_score=None, winner=None, status='scheduled')
    m.pop('walkover', None)
    m.pop('tiebreak', None)
    t['matches'] = matches
    return t


def walkover(tournament: dict, match_id: str, winner: str) -> dict:
    """A team didn't turn up or gave the match away: the other wins with no
    score. In a league it counts as a win and a loss (no close-loss point)."""
    t, matches = _copy(tournament)
    m = _find(matches, match_id)
    if not m.get('home') or not m.get('away'):
        raise TournamentError("Both teams must be known before a walkover is given.")
    if m.get('status') == 'bye':
        raise TournamentError("A bye isn't played.")
    if winner not in (m['home'], m['away']):
        raise TournamentError("Choose the team that gets the walkover.")
    if m.get('stage') == 'league' and has_playoffs(t):
        raise TournamentError("The playoffs were made from the league table. Undo the playoffs first.")
    _check_next(matches, m, winner)
    m.update(home_score=None, away_score=None, status='played', winner=winner, walkover=True, played_at=_stamp())
    m.pop('postponed', None)
    m.pop('tiebreak', None)
    _advance(matches, m)
    _settle_withdrawn(t, matches)
    t['matches'] = matches
    return t


def withdrawn(tournament: dict) -> set:
    return {x['id'] for x in tournament.get('teams') or [] if x.get('withdrawn')}


def _settle_withdrawn(t, matches):
    """Every match still to play against a withdrawn team is a walkover to
    the other team (a knockout's next round included, as teams reach it)."""
    out = {x['id'] for x in t.get('teams') or [] if x.get('withdrawn')}
    changed = True
    while out and changed:
        changed = False
        for m in matches:
            if m.get('status') != 'scheduled' or not m.get('home') or not m.get('away'):
                continue
            if m.get('stage') == 'league' and has_playoffs(dict(t, matches=matches)):
                continue
            gone = [side for side in ('home', 'away') if m[side] in out]
            if len(gone) == 1:
                win = m['away'] if gone[0] == 'home' else m['home']
                m.update(home_score=None, away_score=None, status='played', winner=win, walkover=True)
                _advance(matches, m)
                changed = True


def withdraw(tournament: dict, team_id: str) -> dict:
    """The team pulls out: its matches still to play become walkovers to its
    opponents; results it already has stay (UPG-356)."""
    t, matches = _copy(tournament)
    team = next((x for x in t['teams'] if x['id'] == team_id), None)
    if team is None:
        raise TournamentError("That team isn't in the fixtures.")
    if team.get('withdrawn'):
        raise TournamentError("That team has withdrawn already.")
    team['withdrawn'] = True
    _settle_withdrawn(t, matches)
    t['matches'] = matches
    return t


def reinstate(tournament: dict, team_id: str) -> dict:
    """Bring a withdrawn team back. Walkovers already given stay; clear any of
    them to have that match played."""
    t, _ = _copy(tournament)
    team = next((x for x in t['teams'] if x['id'] == team_id), None)
    if team is None or not team.get('withdrawn'):
        raise TournamentError("That team hasn't withdrawn.")
    team.pop('withdrawn', None)
    return t


def rename_team(tournament: dict, team_id: str, name: str) -> dict:
    t, _ = _copy(tournament)
    name = ' '.join(str(name or '').split())[:120]
    if not name:
        raise TournamentError("Give the team a name.")
    team = next((x for x in t['teams'] if x['id'] == team_id), None)
    if team is None:
        raise TournamentError("That team isn't in the fixtures.")
    team['name'] = name
    return t


def replace_team(tournament: dict, old_id: str, new_team: dict) -> dict:
    """Another registration takes a team's place everywhere in the fixtures,
    its results included (registered under the wrong team, a late swap) (UPG-357)."""
    t, matches = _copy(tournament)
    if not any(x['id'] == old_id for x in t['teams']):
        raise TournamentError("That team isn't in the fixtures.")
    if not new_team or any(x['id'] == new_team['id'] for x in t['teams']):
        raise TournamentError("Choose a confirmed team that isn't in the fixtures yet.")
    keep = lambda old: {k: old[k] for k in ('pool', 'seed') if k in old}   # noqa: E731  its place in its pool
    t['teams'] = [dict(new_team, **keep(x)) if x['id'] == old_id else x for x in t['teams']]
    for m in matches:
        for key in ('home', 'away', 'winner'):
            if m.get(key) == old_id:
                m[key] = new_team['id']
    if t.get('playoffs'):
        t['playoffs'] = dict(t['playoffs'], seeds=[new_team['id'] if x == old_id else x
                                                   for x in t['playoffs'].get('seeds') or []])
    return t


def add_team(tournament: dict, new_team: dict) -> dict:
    """A late team joins a league (before any playoffs): it gets a match
    against every other team, in new rounds after the last one (UPG-357)."""
    t, matches = _copy(tournament)
    if t.get('format') not in ('league', 'league_knockout'):
        raise TournamentError("A knockout's draw is fixed. Replace a team, or make the fixtures again.")
    if has_playoffs(t):
        raise TournamentError("The playoffs are made. Undo the playoffs first.")
    if t.get('pools') or t.get('legs') == 2:
        raise TournamentError("With pools or home-and-away matches, a late team needs the fixtures made again "
                              "(or Replace a team that pulled out).")
    if not new_team or any(x['id'] == new_team['id'] for x in t['teams']):
        raise TournamentError("Choose a confirmed team that isn't in the fixtures yet.")
    counter = max([int(str(m['id']).lstrip('m') or 0) for m in matches] or [0])
    rnd = max([int(m.get('round') or 0) for m in matches] or [0])
    for other in t['teams']:
        counter += 1
        rnd += 1
        m = _match(f"m{counter}", rnd, other['id'], new_team['id'])
        if t.get('format') == 'league_knockout':
            m['stage'] = 'league'
        matches.append(m)
    t['teams'].append(dict(new_team))
    _settle_withdrawn(t, matches)
    t['matches'] = matches
    return t


def set_match_teams(tournament: dict, match_id: str, home: str, away: str) -> dict:
    """Change who plays in a match not yet played: a seeding decided by a
    toss, a team put in the wrong slot (UPG-357)."""
    t, matches = _copy(tournament)
    m = _find(matches, match_id)
    if m.get('status') in ('played', 'bye'):
        raise TournamentError("Clear this match's result first.")
    ids = {x['id'] for x in t['teams']}
    home, away = (home or None), (away or None)
    if (home and home not in ids) or (away and away not in ids):
        raise TournamentError("Choose teams from the fixtures.")
    if home and home == away:
        raise TournamentError("A team can't play itself.")
    for other in matches:                     # one match a round: swapping two matches goes through TBD
        if other is not m and other.get('round') == m.get('round') and other.get('stage') == m.get('stage'):
            clash = {home, away} & {other.get('home'), other.get('away')} - {None}
            if clash:
                raise TournamentError(
                    f"{names(t).get(clash.pop(), 'That team')} already plays in match {other['id'].upper()} "
                    "in this round. Set that side to TBD there first.")
    m.update(home=home, away=away)
    if t.get('playoffs'):                     # the seeds are whoever starts the playoffs now
        first = 'semi' if t['playoffs'].get('size') == 4 else 'final'
        t['playoffs'] = dict(t['playoffs'], seeds=[x for mm in matches if mm.get('stage') == first
                                                   for x in (mm.get('home'), mm.get('away')) if x])
    _settle_withdrawn(t, matches)
    t['matches'] = matches
    return t


def set_points(tournament: dict, points: dict, tiebreak: bool = None) -> dict:
    """Change the league's points rule; the table is worked out again from the
    results (UPG-358). Refused once the playoffs were seeded from it. `tiebreak`
    turns the tie-breaker on or off (UPG-396); None leaves it as it is."""
    t, _ = _copy(tournament)
    if t.get('format') not in ('league', 'league_knockout'):
        raise TournamentError("Only a league has a points rule.")
    if has_playoffs(t):
        raise TournamentError("The playoffs were made from the table. Undo the playoffs first.")
    t['points'] = dict(DEFAULT_POINTS, **{k: max(0, int(v)) for k, v in (points or {}).items() if k in DEFAULT_POINTS})
    if tiebreak is not None:
        if tiebreak:
            t['tiebreak'] = True
        else:
            t.pop('tiebreak', None)
    return t


def undo_playoffs(tournament: dict) -> dict:
    """Take the playoffs away (none of them played yet), so the league can be
    corrected and the playoffs made again (UPG-358)."""
    t, matches = _copy(tournament)
    if not has_playoffs(t):
        raise TournamentError("There are no playoffs to undo.")
    if any(m.get('stage') in KNOCKOUT_STAGES and m.get('status') == 'played' for m in matches):
        raise TournamentError("A playoff match has a result. Clear the playoff results first (the final first).")
    t['matches'] = [m for m in matches if m.get('stage') not in KNOCKOUT_STAGES]
    t.pop('playoffs', None)
    return t


def playoff_ids(tournament: dict) -> list:
    return [m['id'] for m in tournament.get('matches') or [] if m.get('stage') in KNOCKOUT_STAGES]


def _stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


# ── Postponed matches, what's next, the bracket (UPG-392 to UPG-394) ────────
def postpone(tournament: dict, match_id: str, on: bool = True) -> dict:
    """Mark a match postponed (it keeps its place and plays later) or back on.
    A result, live or typed, takes the mark off by itself (UPG-394)."""
    t, matches = _copy(tournament)
    m = _find(matches, match_id)
    if on and m.get('status') in ('played', 'bye'):
        raise TournamentError("This match has a result, so it can't be postponed.")
    if on:
        m['postponed'] = True
    else:
        m.pop('postponed', None)
    return t


def up_next(tournament: dict, live=()) -> 'dict | None':
    """The first match in order that can be played now: both teams known, no
    result, not being played, not postponed (UPG-392)."""
    for m in tournament.get('matches') or []:
        if (m.get('home') and m.get('away') and m.get('status') not in ('played', 'bye')
                and m['id'] not in live and not m.get('postponed')):
            return m
    return None


def last_result(tournament: dict) -> 'dict | None':
    """The match most recently given a result (UPG-392)."""
    played = [(m.get('played_at') or '', i, m) for i, m in enumerate(tournament.get('matches') or [])
              if m.get('status') == 'played']
    return max(played, key=lambda x: (x[0], x[1]))[2] if played else None


def _slot(m: dict = None, home_label: str = '', away_label: str = '', title: str = '', **extra) -> dict:
    m = m or {}
    return {'id': m.get('id'), 'no': match_no(m) if m.get('id') else '', 'title': title or (stage_name(m) if m else ''),
            'home': m.get('home'), 'away': m.get('away'), 'home_label': home_label, 'away_label': away_label,
            'home_score': m.get('home_score'), 'away_score': m.get('away_score'), 'winner': m.get('winner'),
            'status': m.get('status') or '', 'walkover': bool(m.get('walkover')),
            'postponed': bool(m.get('postponed')), 'tiebreak': m.get('tiebreak'), 'projected': False, **extra}


ROUND_TITLES = {1: 'Final', 2: 'Semi-finals', 3: 'Quarter-finals'}


def bracket(tournament: dict) -> dict:
    """The road to the title, for the map on the SPOC's page, the fixtures page
    and the big screen (UPG-393): {'columns': [{'title', 'slots'}], 'champion',
    'projected'}. In a league then knockout, before the playoffs are made the
    semi-finals show who would play if the league ended now (1st A v 2nd B,
    1st B v 2nd A with pools; 1 v 4, 2 v 3 without). {} for a plain league."""
    t = tournament or {}
    matches = t.get('matches') or []
    fmt = t.get('format')
    if not matches or fmt not in ('knockout', 'league_knockout'):
        return {}
    if fmt == 'knockout':
        rounds = {}
        for m in matches:
            rounds.setdefault(int(m.get('round') or 0), []).append(m)
        cols = []
        for i, rnd in enumerate(sorted(rounds)):
            left = len(rounds) - i
            cols.append({'title': ROUND_TITLES.get(left, f'Round {rnd}'),
                         'slots': [_slot(m) for m in rounds[rnd]]})
        return {'columns': cols, 'champion': champion(t), 'projected': False}
    pools = bool(t.get('pools'))
    ko = [m for m in matches if m.get('stage') in KNOCKOUT_STAGES]
    if ko:
        semis = [m for m in ko if m['stage'] == 'semi']
        finals = [m for m in ko if m['stage'] == 'final']
        third = [m for m in ko if m['stage'] == 'third']
        labels = ((('1st Pool A', '2nd Pool B'), ('1st Pool B', '2nd Pool A')) if pools
                  else (('1st', '4th'), ('2nd', '3rd')))
        cols = []
        if semis:
            cols.append({'title': 'Semi-finals', 'slots': [_slot(m, *labels[i], title=f'Semi-final {i + 1}')
                                                           for i, m in enumerate(semis[:2])]})
        final_labels = ('Winner SF1', 'Winner SF2') if semis else (('1st Pool A', '1st Pool B') if pools else ('1st', '2nd'))
        cols.append({'title': 'Final', 'slots': [_slot(m, *final_labels, title='Final') for m in finals]
                     + [_slot(m, 'Loser SF1', 'Loser SF2', title='Third place') for m in third]})
        return {'columns': cols, 'champion': champion(t), 'projected': False}
    # Not made yet: today's table positions (a pool none of whose teams has
    # played names nobody), settled once the league is over
    def ranked(rows):
        return rows if any(r['played'] for r in rows) else [{'id': None}] * len(rows)
    if pools:
        a, b = ranked(standings(t, 'A')), ranked(standings(t, 'B'))
        size = 4 if len(a) >= 2 and len(b) >= 2 else 2
        pick = {'1st Pool A': a[:1], '2nd Pool A': a[1:2], '1st Pool B': b[:1], '2nd Pool B': b[1:2]}
        pairs = ((('1st Pool A', '2nd Pool B'), ('1st Pool B', '2nd Pool A')) if size == 4
                 else (('1st Pool A', '1st Pool B'),))
    else:
        table = ranked(standings(t))
        size = 4 if len(table) >= 4 else 2
        pick = {label: table[i:i + 1] for i, label in enumerate(('1st', '2nd', '3rd', '4th'))}
        pairs = (('1st', '4th'), ('2nd', '3rd')) if size == 4 else (('1st', '2nd'),)

    def team(label):
        rows = pick.get(label) or []
        return rows[0]['id'] if rows else None

    def projected(h, a_, title):
        return dict(_slot(None, h, a_, title=title), home=team(h), away=team(a_), projected=True)

    if size == 4:
        cols = [{'title': 'Semi-finals', 'slots': [projected(*pairs[0], 'Semi-final 1'), projected(*pairs[1], 'Semi-final 2')]},
                {'title': 'Final', 'slots': [dict(_slot(None, 'Winner SF1', 'Winner SF2', title='Final'), projected=True)]}]
    else:
        cols = [{'title': 'Final', 'slots': [projected(*pairs[0], 'Final')]}]
    return {'columns': cols, 'champion': None, 'projected': True, 'settled': league_done(t)}


def update_schedule(tournament: dict, match_id: str, date: str, time: str, venue: str) -> dict:
    t = dict(tournament)
    matches = [dict(m) for m in t.get('matches') or []]
    m = _find(matches, match_id)
    m.update(date=date.strip()[:20], time=time.strip()[:10], venue=venue.strip()[:200])
    t['matches'] = matches
    return t


def when(m: dict) -> str:
    """A match's date and time as people read it (UPG-443): "Sat 28 Nov · 4:30 PM";
    whatever was typed if it isn't a date; '' when there's neither."""
    date, time = str(m.get('date') or '').strip(), str(m.get('time') or '').strip()
    try:
        d = datetime.date.fromisoformat(date)
        date = f"{d:%a} {d.day} {d:%b}"
    except ValueError:
        pass
    try:
        hh, mm = (int(x) for x in time.split(':')[:2])
        time = f"{(hh % 12) or 12}:{mm:02d} {'AM' if hh < 12 else 'PM'}"
    except ValueError:
        pass
    return ' · '.join(x for x in (date, time) if x)


def update_schedules(tournament: dict, rows: dict) -> dict:
    """Every match's date, time and venue at once (UPG-443): rows is match id →
    (date, time, venue). Matches not in rows stay as they are. A wrong date
    changes nothing and says which match."""
    t = dict(tournament)
    matches = [dict(m) for m in t.get('matches') or []]
    for m in matches:
        if m['id'] not in rows:
            continue
        date, time, venue = (str(x or '') for x in rows[m['id']])
        try:
            date = _clean_date(date)
        except ValueError as exc:
            raise TournamentError(f"{match_no(m)}: {exc}.")
        m.update(date=date[:20], time=time.strip()[:10], venue=venue.strip()[:200])
    t['matches'] = matches
    return t


SCHEDULE_COLUMNS = ('Match', 'Stage', 'Team 1', 'Team 2', 'Date', 'Time', 'Venue')


def schedule_rows(tournament: dict) -> list:
    """The fixture list as rows for the schedule file (UPG-385)."""
    n = names(tournament)
    return [[match_no(m), stage_name(m), n.get(m.get('home'), 'TBD'), n.get(m.get('away'), 'TBD'),
             m.get('date') or '', m.get('time') or '', m.get('venue') or ''] for m in tournament.get('matches') or []]


def _clean_date(value: str) -> str:
    """2026-11-28, 28-11-2026, 28/11/2026 or 28.11.2026 → 2026-11-28; '' stays ''."""
    value = str(value or '').strip()
    if not value:
        return ''
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d.%m.%Y', '%d-%m-%y', '%d/%m/%y', '%Y/%m/%d'):
        try:
            return datetime.datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"date \"{value}\" isn't a date like 28-11-2026")


def _clean_time(value: str) -> str:
    """15:30, 15:30:00, 3:30 PM or 3 PM → 15:30; '' stays ''."""
    value = ' '.join(str(value or '').upper().replace('.', ':').split())
    if not value:
        return ''
    for fmt in ('%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M%p', '%I %p', '%I%p'):
        try:
            return datetime.datetime.strptime(value, fmt).strftime('%H:%M')
        except ValueError:
            continue
    raise ValueError(f"time \"{value}\" isn't a time like 15:30 or 3:30 PM")


# Other headings people use for the same columns, as on a printed fixture sheet (UPG-391)
COLUMN_NAMES = {
    'match': ('match', 'match no', 'match no.', 'match number', 'm.no', 'm no', 'no', 'no.', '#', 'sl no', 'sl. no.'),
    'team 1': ('team 1', 'team1', 'team a', 'home', 'home team'),
    'team 2': ('team 2', 'team2', 'team b', 'away', 'away team'),
    'date': ('date', 'day'),
    'time': ('time', 'start time', 'start'),
    'venue': ('venue', 'court', 'ground', 'place'),
}


def _column(head) -> str:
    head = ' '.join(str(head or '').strip().lower().split())
    return next((key for key, names_ in COLUMN_NAMES.items() if head in names_), head)


def _match_key(value: str) -> str:
    """'M-01', 'M1', 'm 1', 'Match 1' or '1' → 'M-01'; anything else as typed."""
    key = str(value or '').upper().replace(' ', '').replace('MATCH', 'M')
    digits = key.lstrip('M-').lstrip('.')
    if digits.isdigit() and (key.isdigit() or key.startswith('M')):
        return f"M-{int(digits):02d}"
    return key


def _team_key(name: str) -> str:
    return ' '.join(str(name or '').lower().split())


def apply_schedule(tournament: dict, rows: list, skipped: 'list | None' = None) -> tuple:
    """Every match's date, time and venue — and its two teams, if the file
    names them (UPG-391) — from the schedule file's rows; all or nothing: one
    wrong row and nothing changes, every problem listed (UPG-385). A row for a
    playoff match not made yet is passed over and named in `skipped`.
    Returns (tournament, count of matches changed)."""
    t, matches = _copy(tournament)
    by_no = {match_no(m): m for m in matches}
    by_name = {_team_key(x['name']): x['id'] for x in t.get('teams') or []}
    out = withdrawn(t)
    problems, changed = [], 0
    for line, row in enumerate(rows, start=2):
        line = row.get('_row') or line                 # the sheet's own row number
        row = {_column(k): str(v if v is not None else '').strip() for k, v in row.items() if k != '_row'}
        key = _match_key(row.get('match', ''))
        if not key:
            continue
        m = by_no.get(key)
        if m is None:
            if key.startswith('M-') and key[2:].isdigit() and int(key[2:]) > len(matches):
                if skipped is not None:
                    skipped.append(key)            # a semi-final or final the playoffs will make
                continue
            problems.append(f"Row {line}: there is no match {row.get('match')}.")
            continue
        try:
            date, time_ = _clean_date(row.get('date', '')), _clean_time(row.get('time', ''))
        except ValueError as exc:
            problems.append(f"Row {line} ({key}): {exc}.")
            continue
        new = {'date': date, 'time': time_, 'venue': row.get('venue', '')[:200]}
        sides, bad = {}, False
        for side, col in (('home', 'team 1'), ('away', 'team 2')):
            typed = row.get(col, '')
            if not typed or typed.upper() == 'TBD' or by_name.get(_team_key(typed)) == m.get(side):
                continue
            team_id = by_name.get(_team_key(typed))
            if team_id is None:
                if m.get('stage') in KNOCKOUT_STAGES:
                    continue                       # "1st A", "Winner SF1": the playoffs fill these
                problems.append(f"Row {line} ({key}): no team is called \"{typed}\"; use the names on the teams list.")
                bad = True
            elif team_id in out:
                problems.append(f"Row {line} ({key}): {typed} was withdrawn.")
                bad = True
            else:
                sides[side] = team_id
        if bad:
            continue
        if sides:
            if m.get('status') == 'played':
                problems.append(f"Row {line} ({key}): it has been played; clear its result before changing its teams.")
                continue
            home, away = sides.get('home', m.get('home')), sides.get('away', m.get('away'))
            if home and home == away:
                problems.append(f"Row {line} ({key}): a team can't play itself.")
                continue
            new.update(sides)
        if any((m.get(k) or '') != v for k, v in new.items()):
            changed += 1
        m.update(new)
    if problems:
        raise TournamentError("Nothing was changed. " + ' '.join(problems[:8])
                              + (f" And {len(problems) - 8} more." if len(problems) > 8 else ''))
    t['matches'] = matches
    return t, changed


def read_sheet(raw: bytes, filename: str) -> list:
    """The rows of an uploaded fixture sheet, CSV or Excel (.xlsx), as dicts
    keyed by the header row: the first row, within the top 10, that has a
    Match column (a printed sheet may start with a title) (UPG-391)."""
    import csv
    import io
    if str(filename or '').lower().endswith(('.xlsx', '.xlsm')):
        from openpyxl import load_workbook
        try:
            book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception as exc:
            raise TournamentError("That Excel file couldn't be read. Save it again as .xlsx (or CSV).") from exc
        grid = []
        for values in book.worksheets[0].iter_rows(values_only=True):
            grid.append([_cell(v) for v in values])
            if len(grid) > 2000:
                break
    else:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
        grid = [list(r) for r in csv.reader(io.StringIO(text))]
    for start, head in enumerate(grid[:10]):
        cols = [_column(h) for h in head]
        if 'match' in cols:
            return [dict(zip(cols, r), _row=n) for n, r in enumerate(grid[start + 1:], start=start + 2)
                    if any(str(c or '').strip() for c in r)]
    return []


def _cell(value) -> str:
    """An Excel cell as the text a person would type: a date as 2026-11-24, a time as 15:30."""
    if value is None:
        return ''
    if isinstance(value, datetime.datetime):
        return value.strftime('%H:%M') if value.date() == datetime.date(1899, 12, 30) else value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.strftime('%H:%M')
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def set_logo(tournament: dict, team_id: str, url: str) -> dict:
    """A team's logo (or none), shown in the fixtures, tables and scoreboard (UPG-386)."""
    t, _ = _copy(tournament)
    team = next((x for x in t['teams'] if x['id'] == team_id), None)
    if team is None:
        raise TournamentError("That team isn't in the fixtures.")
    if url:
        team['logo'] = url
    else:
        team.pop('logo', None)
    return t


LOGO_SIZE = 256
LOGO_MAX_BYTES = 2 * 1024 * 1024


def logo_webp(data: bytes, min_side: int = 0) -> bytes:
    """Check an uploaded logo and return it as a square WebP, transparency kept,
    the whole logo shown (not cropped), metadata dropped. `min_side`: a logo
    smaller than this on its shorter side is refused as too small to show
    clearly (the registration form's 200, UPG-405)."""
    import io
    from PIL import Image, ImageOps, UnidentifiedImageError
    if len(data) > LOGO_MAX_BYTES:
        raise TournamentError("That logo is larger than 2 MB.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise TournamentError("That file isn't an image we can read. Use a PNG, JPG or WebP logo.")
    if fmt not in ('JPEG', 'PNG', 'WEBP'):
        raise TournamentError("Use a PNG, JPG or WebP logo.")
    with Image.open(io.BytesIO(data)) as img:
        if img.width > 6000 or img.height > 6000:
            raise TournamentError("That logo is too large (at most 6000 pixels on a side).")
        if min_side and min(img.width, img.height) < min_side:
            raise TournamentError(f"That logo is too small to show clearly ({img.width} × {img.height} pixels): "
                                  f"use one at least {min_side} pixels on each side.")
        img = ImageOps.exif_transpose(img).convert('RGBA')
        img = ImageOps.contain(img, (LOGO_SIZE, LOGO_SIZE), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (LOGO_SIZE, LOGO_SIZE), (0, 0, 0, 0))
        canvas.paste(img, ((LOGO_SIZE - img.width) // 2, (LOGO_SIZE - img.height) // 2), img)
        out = io.BytesIO()
        canvas.save(out, 'WEBP', quality=88)
        return out.getvalue()


def store_logo(event_id: str, data: bytes, min_side: int = 0) -> str:
    """Check, convert and save a team's logo; its address (UPG-386, UPG-405).
    Raises TournamentError when the file isn't a usable logo or can't be saved."""
    import secrets
    from utils_storage import upload_file
    webp = logo_webp(data, min_side)
    url = upload_file(webp, f'team-logos/{event_id}-{secrets.token_hex(6)}.webp', 'image/webp')
    if not url:
        raise TournamentError("The logo couldn't be saved. Please try again.")
    return url[url.index('/static/uploads/'):] if '/static/uploads/' in url else url


def _loss_points(pts: dict, margin: int) -> int:
    """A loss's points: the close-loss point when within the margin (kabaddi: 7)."""
    close = int(pts.get('close_margin') or 0)
    return int(pts.get('close_loss') or 0) if close and margin <= close else int(pts.get('loss') or 0)


def standings(tournament: dict, pool: str = None) -> list:
    """League table rows, best first: points, score (goal) difference, scored, name.
    A league then knockout's table counts its league matches only. With a
    pool, that pool's teams only, counting every league match they played,
    the inter-pool round included (UPG-383)."""
    pts = dict(DEFAULT_POINTS, **(tournament.get('points') or {}))
    rows = {t['id']: {'id': t['id'], 'name': t['name'], 'played': 0, 'won': 0, 'drawn': 0, 'lost': 0,
                      'for': 0, 'against': 0, 'points': 0} for t in tournament.get('teams') or []}
    for m in tournament.get('matches') or []:
        if m.get('status') != 'played' or m['home'] not in rows or m['away'] not in rows:
            continue
        if m.get('stage') in KNOCKOUT_STAGES:
            continue
        h, a = rows[m['home']], rows[m['away']]
        if m.get('walkover'):                 # a win and a loss, no score (UPG-356)
            win, lose = (h, a) if m.get('winner') == m['home'] else (a, h)
            win['played'] += 1; lose['played'] += 1; win['won'] += 1; lose['lost'] += 1  # noqa: E702
            win['points'] += pts['win']; lose['points'] += pts['loss']  # noqa: E702
            continue
        hs, as_ = int(m['home_score']), int(m['away_score'])
        for row, f, ag in ((h, hs, as_), (a, as_, hs)):
            row['played'] += 1
            row['for'] += f
            row['against'] += ag
        if hs == as_ and m.get('tiebreak') and m.get('winner') in (m['home'], m['away']):
            win, lose = (h, a) if m['winner'] == m['home'] else (a, h)      # won the tie-breaker (UPG-396)
            win['won'] += 1; lose['lost'] += 1; win['points'] += pts['win']; lose['points'] += pts['loss']  # noqa: E702
        elif hs > as_:
            h['won'] += 1; a['lost'] += 1; h['points'] += pts['win']; a['points'] += _loss_points(pts, hs - as_)  # noqa: E702,E501
        elif as_ > hs:
            a['won'] += 1; h['lost'] += 1; a['points'] += pts['win']; h['points'] += _loss_points(pts, as_ - hs)  # noqa: E702,E501
        else:
            h['drawn'] += 1; a['drawn'] += 1; h['points'] += pts['draw']; a['points'] += pts['draw']  # noqa: E702
    if pool:
        in_pool = {x['id'] for x in tournament.get('teams') or [] if x.get('pool') == pool}
        rows = {k: v for k, v in rows.items() if k in in_pool}
    return sorted(rows.values(), key=lambda r: (-r['points'], -(r['for'] - r['against']), -r['for'], r['name']))


def table_key(tournament: dict) -> dict:
    """What the points table's letters mean, how it is ordered, and why kabaddi
    has no rate like cricket's net run rate (UPG-425)."""
    kab = is_kabaddi(tournament or {})
    pts = dict(DEFAULT_POINTS, **((tournament or {}).get('points') or {}))
    diff, scored = ('SD', 'score difference') if kab else ('GD', 'goal difference')
    tie = ('T', 'tied') if kab else ('D', 'drawn')
    against = 'points scored minus points conceded' if kab else 'goals scored minus goals conceded'
    rule = f"a win {pts['win']}, {'a tie' if kab else 'a draw'} {pts['draw']}, a loss {pts['loss']}"
    if pts.get('close_margin') and pts.get('close_loss'):
        rule += f" ({pts['close_loss']} if lost by {pts['close_margin']} or fewer)"
    if kab and not pts['draw'] and not pts['loss'] and pts['win'] == 2:
        rule = 'a win 2, a loss 0; a match level at full time goes to the tie-breaker and its winner takes the win'
    letters = [('P', 'played'), ('W', 'won'), tie, ('L', 'lost'), (diff, f'{scored} ({against})'),
               ('Pts', f'points: {rule}')]
    order = (f"Most points first; level on points, the bigger {scored}, then more "
             f"{'points' if kab else 'goals'} scored, then the team's name.")
    why = ("Why the score difference and not a rate: every kabaddi match lasts the same 40 minutes, "
           "so there is nothing to divide by. Cricket works out a net run rate because teams face "
           "different numbers of overs.") if kab else ''
    extra = [('PF', 'points scored'), ('PA', 'points conceded')] if kab else [('GF', 'goals for'), ('GA', 'goals against')]
    return {'letters': letters, 'extra': extra, 'order': order, 'why': why,
            'line': ' · '.join(f'{a} {b.split(" (")[0].split(":")[0]}' for a, b in letters)}


def pool_tables(tournament: dict) -> list:
    """[(pool, rows)] for a tournament with pools, else [] (UPG-381)."""
    return [(p, standings(tournament, p)) for p in tournament.get('pools') or []]


def pool_teams(tournament: dict) -> list:
    """[(pool, teams by seed)] for a tournament with pools, else []: which team
    is in which pool, for the audience (UPG-407)."""
    teams = tournament.get('teams') or []
    return [(p, sorted([x for x in teams if x.get('pool') == p], key=lambda x: (x.get('seed') or 99, x['name'].lower())))
            for p in tournament.get('pools') or []]


def match_no(m: dict) -> str:
    """M-01, M-02, … as on a printed fixture sheet (UPG-385)."""
    digits = str(m.get('id') or '').lstrip('m')
    return f"M-{int(digits):02d}" if digits.isdigit() else str(m.get('id') or '').upper()


def logos(tournament: dict) -> dict:
    return {x['id']: x['logo'] for x in tournament.get('teams') or [] if x.get('logo')}


def _final(tournament: dict):
    """The knockout's last match (not the third-place match), or None."""
    matches = tournament.get('matches') or []
    final = [m for m in matches if m.get('stage') == 'final'] or \
        [m for m in matches if not m.get('next') and m.get('stage') not in ('third', 'league')]
    return final[0] if len(final) == 1 else None


def champion(tournament: dict):
    """The knockout's (or the playoffs') winner once the final is played, else None."""
    if tournament.get('format') not in ('knockout', 'league_knockout'):
        return None
    final = _final(tournament)
    return final.get('winner') if final and final.get('status') in ('played', 'bye') else None


def placings(tournament: dict) -> dict:
    """Team id → place (1, 2, 3; two thirds when no third-place match is
    played), once the deciding matches are played; {} while undecided (UPG-342)."""
    matches = tournament.get('matches') or []
    if not matches:
        return {}
    if tournament.get('format') == 'league':
        if any(m.get('status') not in ('played', 'bye') for m in matches):
            return {}
        return {row['id']: place for place, row in enumerate(standings(tournament)[:3], start=1)}
    final = _final(tournament)
    if not final or final.get('status') != 'played' or not final.get('winner'):
        return {}
    places = {final['winner']: 1, _loser(final): 2}
    third = [m for m in matches if m.get('stage') == 'third']
    if third:
        if third[0].get('status') != 'played' or not third[0].get('winner'):
            return {}
        places[third[0]['winner']] = 3
    else:
        for m in matches:
            if m.get('next') == final['id'] and _loser(m):
                places[_loser(m)] = 3
    return {team: place for team, place in places.items() if team}


def _registrations(db, event_id):
    return [(d.id, d.to_dict() or {}) for d in db.collection('registrations').where('event_id', '==', event_id).stream()]


def published_places(db, event_id: str) -> dict:
    """Registration id → the place it was given when the results were published."""
    return {rid: r['final_rank'] for rid, r in _registrations(db, event_id) if r.get('final_rank')}


def publish(db, event_id: str, actor: str) -> list:
    """Make the tournament's places the event's result (UPG-342). Returns notes
    for the publisher; raises TournamentError while the places aren't known.

    Pressed again after a result was corrected (UPG-359), it changes only what
    changed: the teams whose place changed are told their new place, and the
    position certificates issued for an old place are revoked before the right
    ones are issued."""
    ref = db.collection('events').document(event_id)
    event = ref.get().to_dict() or {}
    places = placings(event.get('tournament') or {})
    if not places:
        raise TournamentError("The places aren't known yet: play the final (and the third-place match) first.")
    again = bool(event.get('results_published'))
    import services_hackathon
    portal = services_hackathon.portal_only(event)
    title = event.get('title', 'Event')
    winners, changed = [], set()
    for reg_id, reg in _registrations(db, event_id):
        place = places.get(reg_id)
        if (reg.get('final_rank') or None) != place:
            changed.add(reg_id)
            db.collection('registrations').document(reg_id).update({'final_rank': place})
        if place:
            team = reg.get('team_name') if reg.get('team_name') not in (None, '', 'Individual') else ''
            winners.append({'team_name': team or reg.get('lead_name') or '', 'lead_name': reg.get('lead_name') or '',
                            'email': reg.get('lead_email') or '', 'phone': reg.get('lead_phone') or reg.get('phone') or '',
                            'rank': place, 'score': None, 'reg_id': reg_id})
    if again and not changed:
        return ["The published places already match the fixtures; nothing was changed."]
    winners.sort(key=lambda w: (w['rank'], w['team_name'].lower()))
    ref.update({'status': 'completed', 'winners': [{k: v for k, v in w.items() if k != 'reg_id'} for w in winners],
                'results_published': True,
                **({} if again else {'completed_at': datetime.datetime.now(datetime.timezone.utc)})})
    podium = ', '.join(_ordinal(w['rank']) + ' ' + w['team_name'] for w in winners)
    notes = [f"{'Corrected results' if again else 'Results'} published: {podium}."]
    told = 0
    for w in winners:                       # the place only, never a score
        if again and w['reg_id'] not in changed:
            continue
        told += 1
        if w['email'] and not portal:
            try:
                from utils_email import send_result_email
                send_result_email(str(w['email']), str(w['lead_name']), title, w['rank'], None)
            except Exception:
                log.warning("Result email to %s failed", w['email'], exc_info=True)
        if w['phone']:
            try:
                from utils_whatsapp import send_result_whatsapp
                send_result_whatsapp(w['phone'], w['lead_name'], title, w['rank'], None)
            except Exception:
                log.warning("Result WhatsApp for %s failed", event_id, exc_info=True)
    if again:
        notes.append(f"{told} team{'s' if told != 1 else ''} told {'their' if told != 1 else 'its'} new place.")
        revoked = _revoke_old_places(db, event_id, changed, actor)
        if revoked:
            notes.append(f"{revoked} position certificate{'s' if revoked != 1 else ''} for the old places revoked.")
    try:
        import services_push
        services_push.push_to_registrants(db, event_id, 'results',
                                          f"Results {'corrected' if again else 'are out'}: {title}",
                                          "See where your team placed.", f"/tournament/fixtures/{event_id}")
    except Exception:
        log.warning("Results push failed for %s", event_id, exc_info=True)
    from utils import log_action
    log_action(db, "RESULTS_REPUBLISHED" if again else "RESULTS_PUBLISHED",
               f"Tournament {event_id} by {actor}" + (f": {len(changed)} places changed" if again else ''))
    from services_certificate_runs import on_results_published   # position certificates (UPG-124)
    note = on_results_published(db, event_id, actor)
    if note:
        notes.append(note)
    return notes


def _revoke_old_places(db, event_id: str, reg_ids: set, actor: str) -> int:
    """Revoke the valid winner, runner-up and third-place certificates of the
    registrations whose place changed (UPG-359)."""
    if not reg_ids:
        return 0
    try:
        import services_certificates as certs
        import services_certificate_changes as changes
        count = 0
        for cert in certs.for_event(event_id):
            if cert['cert_type'] in certs.POSITION_TYPES and cert['status'] == 'valid' and cert['reg_id'] in reg_ids:
                changes.revoke(db, cert['number'], actor, "The tournament's result was corrected.")
                count += 1
        return count
    except Exception:
        log.warning("Revoking old position certificates for %s failed", event_id, exc_info=True)
        return 0


def has_tournament(event: dict) -> bool:
    return bool((event.get('tournament') or {}).get('matches'))


def _ordinal(n: int) -> str:
    return {1: '1st', 2: '2nd', 3: '3rd'}.get(n, f'{n}th')


def names(tournament: dict) -> dict:
    return {t['id']: t['name'] for t in tournament.get('teams') or []}
