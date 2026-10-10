"""
services_sports.py — sports tournaments: fixtures, results, standings (UPG-13).

A tournament is kept on its event as `tournament`:

    {'format': 'knockout' | 'league',
     'points': {'win': 3, 'draw': 1, 'loss': 0},          # league only
     'teams':  [{'id': <registration id>, 'name': <team or lead name>}, …],
     'matches': [{'id': 'm1', 'round': 1, 'home': id|None, 'away': id|None,
                  'date': '', 'time': '', 'venue': '',
                  'home_score': None, 'away_score': None, 'winner': None,
                  'status': 'scheduled' | 'played' | 'bye',
                  'next': 'm5', 'next_side': 'home'}, …]}  # knockout only

Teams come from the event's confirmed registrations (UPG-08 teams are
registrations with members). A knockout gets byes up to the next power of
two; a bye's team goes straight through, and each result moves the winner on.
A league plays every pair once (circle method) and its table counts played,
won, drawn, lost, goals and points.
"""
import math

DEFAULT_POINTS = {'win': 3, 'draw': 1, 'loss': 0}
FORMATS = ('knockout', 'league')


class TournamentError(ValueError):
    pass


def confirmed_teams(db, event_id: str) -> list:
    """[{'id', 'name'}] for every registration that isn't cancelled, in registration order."""
    teams = []
    regs = [(d.id, d.to_dict() or {}) for d in db.collection('registrations').where('event_id', '==', event_id).stream()]
    for rid, r in sorted(regs, key=lambda x: str(x[1].get('registered_at') or '')):
        if str(r.get('status') or '').strip().lower() in ('cancelled', 'refunded', 'waitlisted', 'pending payment'):
            continue
        name = r.get('team_name') if r.get('team_name') not in (None, '', 'Individual') else r.get('lead_name')
        teams.append({'id': rid, 'name': name or rid})
    return teams


def _match(mid, rnd, home=None, away=None):
    return {'id': mid, 'round': rnd, 'home': home, 'away': away, 'date': '', 'time': '', 'venue': '',
            'home_score': None, 'away_score': None, 'winner': None, 'status': 'scheduled',
            'next': None, 'next_side': None}


def knockout(teams: list) -> list:
    """A single-elimination bracket with byes; byes are settled at once."""
    n = len(teams)
    if n < 2:
        raise TournamentError("A knockout needs at least 2 teams.")
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


def generate(teams: list, fmt: str, points: dict = None) -> dict:
    if fmt not in FORMATS:
        raise TournamentError("Choose knockout or league.")
    return {'format': fmt, 'points': dict(DEFAULT_POINTS, **(points or {})), 'teams': teams,
            'matches': knockout(teams) if fmt == 'knockout' else league(teams)}


def _find(matches, mid):
    for m in matches:
        if m['id'] == mid:
            return m
    raise TournamentError("No such match.")


def _advance(matches, m):
    if m.get('next') and m.get('winner'):
        nxt = _find(matches, m['next'])
        nxt[m['next_side']] = m['winner']


def record_result(tournament: dict, match_id: str, home_score: int, away_score: int, winner: str = '') -> dict:
    """Enter or correct a result. A knockout needs a winner (the higher score,
    or the one chosen after a tie) and moves it on; a correction is refused
    once the next match has been played."""
    t = dict(tournament)
    matches = [dict(m) for m in t.get('matches') or []]
    m = _find(matches, match_id)
    if not m.get('home') or not m.get('away'):
        raise TournamentError("Both teams must be known before a result is entered.")
    if home_score < 0 or away_score < 0:
        raise TournamentError("Scores can't be negative.")
    m.update(home_score=home_score, away_score=away_score, status='played')
    if t.get('format') == 'knockout':
        if home_score != away_score:
            win = m['home'] if home_score > away_score else m['away']
        elif winner in (m['home'], m['away']):
            win = winner                       # decided on penalties, a tie-break, …
        else:
            raise TournamentError("It's a tie: choose who goes through.")
        if m.get('next'):
            nxt = _find(matches, m['next'])
            if nxt.get('status') == 'played' and m.get('winner') and m['winner'] != win:
                raise TournamentError("The next match is already played; correct it first.")
        m['winner'] = win
        _advance(matches, m)
    else:
        m['winner'] = (m['home'] if home_score > away_score else m['away'] if away_score > home_score else None)
    t['matches'] = matches
    return t


def update_schedule(tournament: dict, match_id: str, date: str, time: str, venue: str) -> dict:
    t = dict(tournament)
    matches = [dict(m) for m in t.get('matches') or []]
    m = _find(matches, match_id)
    m.update(date=date.strip()[:20], time=time.strip()[:10], venue=venue.strip()[:200])
    t['matches'] = matches
    return t


def standings(tournament: dict) -> list:
    """League table rows, best first: points, goal difference, goals for, name."""
    pts = dict(DEFAULT_POINTS, **(tournament.get('points') or {}))
    rows = {t['id']: {'id': t['id'], 'name': t['name'], 'played': 0, 'won': 0, 'drawn': 0, 'lost': 0,
                      'for': 0, 'against': 0, 'points': 0} for t in tournament.get('teams') or []}
    for m in tournament.get('matches') or []:
        if m.get('status') != 'played' or m['home'] not in rows or m['away'] not in rows:
            continue
        h, a = rows[m['home']], rows[m['away']]
        hs, as_ = int(m['home_score']), int(m['away_score'])
        for row, f, ag in ((h, hs, as_), (a, as_, hs)):
            row['played'] += 1
            row['for'] += f
            row['against'] += ag
        if hs > as_:
            h['won'] += 1; a['lost'] += 1; h['points'] += pts['win']; a['points'] += pts['loss']  # noqa: E702
        elif as_ > hs:
            a['won'] += 1; h['lost'] += 1; a['points'] += pts['win']; h['points'] += pts['loss']  # noqa: E702
        else:
            h['drawn'] += 1; a['drawn'] += 1; h['points'] += pts['draw']; a['points'] += pts['draw']  # noqa: E702
    return sorted(rows.values(), key=lambda r: (-r['points'], -(r['for'] - r['against']), -r['for'], r['name']))


def champion(tournament: dict):
    """The knockout's winner once the final is played, else None."""
    if tournament.get('format') != 'knockout':
        return None
    final = [m for m in tournament.get('matches') or [] if not m.get('next')]
    return final[0].get('winner') if final and final[0].get('status') in ('played', 'bye') else None


def names(tournament: dict) -> dict:
    return {t['id']: t['name'] for t in tournament.get('teams') or []}
