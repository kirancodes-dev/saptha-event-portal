"""
tests/test_pool_view_and_scorer_steps.py — UPG-407: the audience (the big
screen's QR code lands on the fixtures page) sees which team is in which pool
and picks Pool A or Pool B for its table and matches; UPG-408: the scorer's
page shows the steps, and only the event's SPOC and its coordinators score.
"""
import re

import services_live_match as live
import services_sports as sports
from tests.test_integration_flow import _login, _unique, _user
from tests.test_kabaddi_match_day import _finish_league, _squad, _start
from tests.test_kabaddi_premier_league import POOL_A, POOL_B, _generate, league  # noqa: F401
from tests.test_live_match import _tap
from tests.test_sports_tournament import _t, cup  # noqa: F401


def _page(d, event_id, query=''):
    resp = d['app'].test_client().get(f'/tournament/fixtures/{event_id}{query}')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _section(page, attr, value):
    m = re.search(rf'<section[^>]*{attr}="{value}".*?</section>', page, re.S)
    assert m, (attr, value)
    return m.group(0)


def _cards(page):
    return re.findall(r'data-match-card="(m\d+)"', page)


# ── UPG-407: which team is in which pool; pick a pool ─────────────────────────

def test_the_audience_sees_each_pools_teams_and_picks_a_pool(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    by_pool = {p: {m['id'] for m in t['matches'] if m.get('pool') == p} for p in 'AB'}
    cross = {m['id'] for m in t['matches'] if m.get('cross')}
    assert len(by_pool['A']) == 12 and len(by_pool['B']) == 12 and len(cross) == 4

    # Everything: both pools' teams in seed order, both tables, all 28 matches
    page = _page(d, event_id)
    assert 'data-pool-picker' in page and 'Choose a pool' in page
    assert re.search(r'data-pool-tab=""[^>]*>All<|aria-current="page" data-pool-tab="">All<', page)
    assert 'data-pool-tab="A">Pool A<' in page and 'data-pool-tab="B">Pool B<' in page
    for pool, members in (('A', POOL_A), ('B', POOL_B)):
        sec = _section(page, 'data-pool-teams', pool)
        assert [sec.index(n) for n in members] == sorted(sec.index(n) for n in members)   # seed order
        assert f'{pool}1' in sec and f'{pool}4' in sec
        assert not any(n in sec for n in (POOL_B if pool == 'A' else POOL_A))
        assert f'data-pool-table="{pool}"' in page
    assert len(_cards(page)) == 28

    # Pool A: its teams, its table, its 12 matches and the inter-pool round
    page = _page(d, event_id, '?pool=A')
    assert 'aria-current="page" data-pool-tab="A"' in page
    assert 'data-pool-teams="A"' in page and 'data-pool-teams="B"' not in page
    assert 'data-pool-table="A"' in page and 'data-pool-table="B"' not in page
    assert set(_cards(page)) == by_pool['A'] | cross
    assert "Showing Pool A's table and matches" in page
    # Pool B, typed in small letters
    page = _page(d, event_id, '?pool=b')
    assert 'data-pool-teams="B"' in page and 'data-pool-table="B"' in page and 'data-pool-table="A"' not in page
    assert set(_cards(page)) == by_pool['B'] | cross
    # A pool that doesn't exist shows everything
    page = _page(d, event_id, '?pool=Z')
    assert len(_cards(page)) == 28 and 'data-pool-table="A"' in page and 'data-pool-table="B"' in page

    # The playoffs show under both pools
    _finish_league(d, event_id)
    assert d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '4'}).status_code == 302
    knockout = {m['id'] for m in _t(d, event_id)['matches'] if m.get('stage') in sports.KNOCKOUT_STAGES}
    assert len(knockout) == 3
    for pool in 'AB':
        assert knockout <= set(_cards(_page(d, event_id, f'?pool={pool}')))


def test_a_pools_page_lists_only_its_players_points(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    names = sports.names(t)
    first_a = next(m for m in t['matches'] if m.get('pool') == 'A')
    first_b = next(m for m in t['matches'] if m.get('pool') == 'B')
    for m in (first_a, first_b):
        home = names[m['home']]
        _squad(d, m['home'], [f'{home} Raider'])
        _start(d, event_id, m, [('home', 'raid', 2, f'{home} Raider')])
    live._cache.clear()
    page = _page(d, event_id)
    assert f'data-team-player-list="{first_a["home"]}"' in page and f'data-team-player-list="{first_b["home"]}"' in page
    page = _page(d, event_id, '?pool=A')
    assert f'data-team-player-list="{first_a["home"]}"' in page
    assert f'data-team-player-list="{first_b["home"]}"' not in page


def test_a_tournament_without_pools_has_no_pool_picker(cup):  # noqa: F811
    d = cup
    event_id, ids = d['event'](['Panthers', 'Bulls', 'Titans', 'Giants'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league'})
    page = _page(d, event_id, '?pool=A')
    assert 'data-pool-picker' not in page and len(_cards(page)) == 6


# ── UPG-408: the scorer's steps; only the SPOC and its coordinators score ─────

def test_the_scorers_page_shows_the_steps_for_its_mode(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    m1, m2 = t['matches'][0], t['matches'][1]

    assert d['owner'].post(f'/tournament/{event_id}/scoring', data={'scoring': 'pkl'}).status_code == 302
    page = d['coord'].get(f"/tournament/{event_id}/match/{m1['id']}/score").get_data(as_text=True)
    howto = re.search(r'<details class="live-howto".*?</details>', page, re.S).group(0)
    assert 'data-howto open' in howto and 'How to score this match' in howto           # open before the start
    assert 'who raids first' in howto and 'Empty raid' in howto and 'Undo last' in howto
    assert 'Full time: save the result' in howto and 'tie-breaker' in howto
    assert "Only this event's SPOC and its coordinators can score" in howto

    assert d['owner'].post(f'/tournament/{event_id}/scoring', data={'scoring': ''}).status_code == 302
    page = d['owner'].get(f"/tournament/{event_id}/match/{m2['id']}/score").get_data(as_text=True)
    howto = re.search(r'<details class="live-howto".*?</details>', page, re.S).group(0)
    assert 'Raid +2' in howto and 'Bonus +1' in howto and 'who raids first' not in howto

    # Once the match has started the steps fold away
    assert _tap(d['owner'], event_id, m2['id'], op='phase', action='start')[0] == 200
    page = d['owner'].get(f"/tournament/{event_id}/match/{m2['id']}/score").get_data(as_text=True)
    assert 'data-howto>' in page and 'data-howto open' not in page


def test_only_the_events_spoc_and_coordinators_score(league):  # noqa: F811
    d, event_id, ids = league
    m = _generate(d, event_id, ids)['matches'][0]
    url = f"/tournament/{event_id}/match/{m['id']}/score"
    outsiders = []
    for role in ('Volunteer', 'Judge', 'EventCoordinator', 'Student'):
        email = f"{_unique(role.lower())}@test.edu"
        _user(d['db'], email, role)
        outsiders.append(_login(d['app'], email, role))        # the coordinator isn't on this event
    for client in outsiders:
        assert client.get(url).status_code == 403
        assert client.post(url, json={'op': 'phase', 'action': 'start', 'tap': _unique('t')}).status_code == 403
    assert live.get(d['db'], event_id, m['id']) is None
    assert d['coord'].get(url).status_code == 200 and d['owner'].get(url).status_code == 200
    assert _tap(d['coord'], event_id, m['id'], op='phase', action='start')[0] == 200
