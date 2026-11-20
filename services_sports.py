"""
services_sports.py — sports tournaments: fixtures, results, standings (UPG-13).

A tournament is kept on its event as `tournament`:

    {'format': 'knockout' | 'league' | 'league_knockout',
     'sport': 'Kabaddi',                                    # optional
     'points': {'win': 3, 'draw': 1, 'loss': 0,             # league only
                'close_loss': 0, 'close_margin': 0},        # kabaddi: 1 within 7
     'playoffs': {'size': 4, 'seeds': [...]},               # league then knockout
     'teams':  [{'id': <registration id>, 'name': <team or lead name>}, …],
     'matches': [{'id': 'm1', 'round': 1, 'home': id|None, 'away': id|None,
                  'date': '', 'time': '', 'venue': '',
                  'home_score': None, 'away_score': None, 'winner': None,
                  'status': 'scheduled' | 'played' | 'bye',
                  'next': 'm5', 'next_side': 'home',        # knockout only
                  'stage': 'final' | 'third' | …,           # where it is in the draw
                  'loser_next': 'm8', 'loser_side': 'home'}, …]}  # a semi-final's loser to the third-place match

Teams come from the event's confirmed registrations (UPG-08 teams are
registrations with members). A knockout gets byes up to the next power of
two; a bye's team goes straight through, and each result moves the winner on.
A league plays every pair once (circle method) and its table counts played,
won, drawn, lost, scored, conceded and points. A league then knockout plays
the league, then its top 4 (or 2) play off (UPG-350).

Once the deciding matches are played, `placings` gives each team's place and
`publish` makes it the event's result (UPG-342): places on the registrations,
the result email and WhatsApp to the placed teams, a push to everyone, and the
position certificates.
"""
import datetime
import logging
import math

log = logging.getLogger(__name__)

DEFAULT_POINTS = {'win': 3, 'draw': 1, 'loss': 0, 'close_loss': 0, 'close_margin': 0}
# A kabaddi league (UPG-350): 5 a win, 3 a tie, 1 for losing by 7 points or fewer
KABADDI_POINTS = {'win': 5, 'draw': 3, 'loss': 0, 'close_loss': 1, 'close_margin': 7}
FORMATS = ('knockout', 'league', 'league_knockout')
FORMAT_NAMES = {'knockout': 'Knockout', 'league': 'League', 'league_knockout': 'League then knockout'}
KNOCKOUT_STAGES = ('semi', 'final', 'third')
STAGE_NAMES = {'final': 'Final', 'semi': 'Semi-final', 'third': 'Third place'}


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


def generate(teams: list, fmt: str, points: dict = None, third_place: bool = False, sport: str = '') -> dict:
    if fmt not in FORMATS:
        raise TournamentError("Choose knockout, league, or league then knockout.")
    if fmt == 'knockout':
        matches = knockout(teams, third_place)
    else:
        matches = league(teams)
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
    return t


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

    if size == 4:
        semi1 = new('semi', rnd, seeds[0], seeds[3])
        semi2 = new('semi', rnd, seeds[1], seeds[2])
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
    if m.get('stage') == 'league' and has_playoffs(t):
        raise TournamentError("The playoffs were seeded from the league table, so its results can't change now.")
    m.update(home_score=home_score, away_score=away_score, status='played')
    if knockout_match(t, m):
        if home_score != away_score:
            win = m['home'] if home_score > away_score else m['away']
        elif winner in (m['home'], m['away']):
            win = winner                       # decided on penalties, a tie-break, …
        else:
            raise TournamentError("It's a tie: choose who goes through.")
        for key in ('next', 'loser_next'):
            if m.get(key):
                nxt = _find(matches, m[key])
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


def _loss_points(pts: dict, margin: int) -> int:
    """A loss's points: the close-loss point when within the margin (kabaddi: 7)."""
    close = int(pts.get('close_margin') or 0)
    return int(pts.get('close_loss') or 0) if close and margin <= close else int(pts.get('loss') or 0)


def standings(tournament: dict) -> list:
    """League table rows, best first: points, score (goal) difference, scored, name.
    A league then knockout's table counts its league matches only."""
    pts = dict(DEFAULT_POINTS, **(tournament.get('points') or {}))
    rows = {t['id']: {'id': t['id'], 'name': t['name'], 'played': 0, 'won': 0, 'drawn': 0, 'lost': 0,
                      'for': 0, 'against': 0, 'points': 0} for t in tournament.get('teams') or []}
    for m in tournament.get('matches') or []:
        if m.get('status') != 'played' or m['home'] not in rows or m['away'] not in rows:
            continue
        if m.get('stage') in KNOCKOUT_STAGES:
            continue
        h, a = rows[m['home']], rows[m['away']]
        hs, as_ = int(m['home_score']), int(m['away_score'])
        for row, f, ag in ((h, hs, as_), (a, as_, hs)):
            row['played'] += 1
            row['for'] += f
            row['against'] += ag
        if hs > as_:
            h['won'] += 1; a['lost'] += 1; h['points'] += pts['win']; a['points'] += _loss_points(pts, hs - as_)  # noqa: E702,E501
        elif as_ > hs:
            a['won'] += 1; h['lost'] += 1; a['points'] += pts['win']; h['points'] += _loss_points(pts, as_ - hs)  # noqa: E702,E501
        else:
            h['drawn'] += 1; a['drawn'] += 1; h['points'] += pts['draw']; a['points'] += pts['draw']  # noqa: E702
    return sorted(rows.values(), key=lambda r: (-r['points'], -(r['for'] - r['against']), -r['for'], r['name']))


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


def publish(db, event_id: str, actor: str) -> list:
    """Make the tournament's places the event's result (UPG-342). Returns notes
    for the publisher; raises TournamentError while the places aren't known."""
    ref = db.collection('events').document(event_id)
    event = ref.get().to_dict() or {}
    places = placings(event.get('tournament') or {})
    if not places:
        raise TournamentError("The places aren't known yet: play the final (and the third-place match) first.")
    import services_hackathon
    portal = services_hackathon.portal_only(event)
    title = event.get('title', 'Event')
    winners = []
    for reg_id, reg in _registrations(db, event_id):
        place = places.get(reg_id)
        if reg.get('final_rank') != place:
            db.collection('registrations').document(reg_id).update({'final_rank': place})
        if place:
            team = reg.get('team_name') if reg.get('team_name') not in (None, '', 'Individual') else ''
            winners.append({'team_name': team or reg.get('lead_name') or '', 'lead_name': reg.get('lead_name') or '',
                            'email': reg.get('lead_email') or '', 'phone': reg.get('lead_phone') or reg.get('phone') or '',
                            'rank': place, 'score': None})
    winners.sort(key=lambda w: (w['rank'], w['team_name'].lower()))
    ref.update({'status': 'completed', 'winners': winners, 'results_published': True,
                'completed_at': datetime.datetime.now(datetime.timezone.utc)})
    podium = ', '.join(_ordinal(w['rank']) + ' ' + w['team_name'] for w in winners)
    notes = [f"Results published: {podium}."]
    for w in winners:                       # the place only, never a score
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
    try:
        import services_push
        services_push.push_to_registrants(db, event_id, 'results', f"Results are out: {title}",
                                          "See where your team placed.", f"/tournament/fixtures/{event_id}")
    except Exception:
        log.warning("Results push failed for %s", event_id, exc_info=True)
    from utils import log_action
    log_action(db, "RESULTS_PUBLISHED", f"Tournament {event_id} by {actor}")
    from services_certificate_runs import on_results_published   # position certificates (UPG-124)
    note = on_results_published(db, event_id, actor)
    if note:
        notes.append(note)
    return notes


def has_tournament(event: dict) -> bool:
    return bool((event.get('tournament') or {}).get('matches'))


def _ordinal(n: int) -> str:
    return {1: '1st', 2: '2nd', 3: '3rd'}.get(n, f'{n}th')


def names(tournament: dict) -> dict:
    return {t['id']: t['name'] for t in tournament.get('teams') or []}
