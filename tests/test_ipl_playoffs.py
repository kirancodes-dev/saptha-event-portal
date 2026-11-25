"""
tests/test_ipl_playoffs.py — UPG-479: IPL-style playoffs for a league then
knockout. Qualifier 1 is 1st A v 1st B (1st v 2nd without pools), the
Eliminator 2nd A v 2nd B (3rd v 4th); Qualifier 2 is Q1's loser v the
Eliminator's winner; the final is Q1's winner v Q2's winner: 4 matches.
Choosing it changes no match or result; the semi-finals stay the default.
"""
import pytest

import services_sports as sports
from tests.test_kabaddi_premier_league import POOL_A, POOL_B, _generate, league  # noqa: F401
from tests.test_sports_tournament import _play, _t, cup  # noqa: F401


def _stage(t, stage):
    return next(m for m in t['matches'] if m.get('stage') == stage)


def _play_pools(d, event_id, t):
    """The earlier seed wins every match: 1st A Garuda Sena, 2nd A Malnad
    Fighters, 1st B Gaja Pade, 2nd B Code Blue."""
    rank = {n: i for i, n in enumerate(POOL_A + POOL_B)}
    name = sports.names(t)
    for m in t['matches']:
        home_wins = rank[name[m['home']]] % 4 < rank[name[m['away']]] % 4 or (
            rank[name[m['home']]] % 4 == rank[name[m['away']]] % 4 and name[m['home']] in POOL_A)
        _play(d['owner'], event_id, m, 40 if home_wins else 20, 20 if home_wins else 40)


def test_choosing_ipl_style_changes_no_match_and_the_map_shows_it(league):  # noqa: F811
    d, event_id, ids = league
    before = _generate(d, event_id, ids)
    _play(d['owner'], event_id, before['matches'][0], 30, 20)       # a league result already in
    before = _t(d, event_id)
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'data-playoff-style' in page and 'Semi-final 1' in page

    assert d['coord'].post(f'/tournament/{event_id}/playoff_style', data={'style': 'ipl'}).status_code == 403
    resp = d['owner'].post(f'/tournament/{event_id}/playoff_style', data={'style': 'ipl'}, follow_redirects=True)
    assert 'Playoff format: IPL style' in resp.get_data(as_text=True)
    after = _t(d, event_id)
    assert after['playoff_style'] == 'ipl'
    assert after['matches'] == before['matches'] and after['teams'] == before['teams']
    assert sports.standings(after, 'A') == sports.standings(before, 'A')

    b = sports.bracket(after)
    assert [c['title'] for c in b['columns']] == ['Qualifier 1 & Eliminator', 'Qualifier 2', 'Final']
    q1, elim = b['columns'][0]['slots']
    assert (q1['title'], q1['home_label'], q1['away_label']) == ('Qualifier 1', '1st Pool A', '1st Pool B')
    assert (elim['title'], elim['home_label'], elim['away_label']) == ('Eliminator', '2nd Pool A', '2nd Pool B')
    q2, final = b['columns'][1]['slots'][0], b['columns'][2]['slots'][0]
    assert (q2['home_label'], q2['away_label']) == ('Loser Q1', 'Winner Eliminator')
    assert (final['home_label'], final['away_label']) == ('Winner Q1', 'Winner Q2')
    for page in (f'/tournament/{event_id}', f'/tournament/screen/{event_id}'):
        html = d['owner'].get(page).get_data(as_text=True)
        assert 'Qualifier 1 &amp; Eliminator' in html and 'Winner Eliminator' in html

    # Back to the semi-finals: still nothing else changes
    d['owner'].post(f'/tournament/{event_id}/playoff_style', data={'style': 'semis'})
    back = _t(d, event_id)
    assert 'playoff_style' not in back and back['matches'] == before['matches']
    assert [c['title'] for c in sports.bracket(back)['columns']] == ['Semi-finals', 'Final']


def test_ipl_playoffs_with_pools_play_four_matches_and_place_the_teams(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    d['owner'].post(f'/tournament/{event_id}/playoff_style', data={'style': 'ipl'})
    _play_pools(d, event_id, t)
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'IPL style: Qualifier 1 (1st A v 1st B)' in page
    resp = d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '4'}, follow_redirects=True)
    assert 'Playoffs made, IPL style: Qualifier 1 (1st A v 1st B), the Eliminator (2nd A v 2nd B)' in resp.get_data(as_text=True)

    t = _t(d, event_id)
    name = sports.names(t)
    ko = [m for m in t['matches'] if m.get('stage') in sports.KNOCKOUT_STAGES]
    assert [(sports.match_no(m), sports.stage_name(m)) for m in ko] == [
        ('M-29', 'Qualifier 1'), ('M-30', 'Eliminator'), ('M-31', 'Qualifier 2'), ('M-32', 'Final')]
    q1, elim = _stage(t, 'qualifier1'), _stage(t, 'eliminator')
    assert (name[q1['home']], name[q1['away']]) == ('Garuda Sena', 'Gaja Pade')
    assert (name[elim['home']], name[elim['away']]) == ('Malnad Fighters', 'Code Blue')
    assert t['playoffs']['seeds'] == [ids['Garuda Sena'], ids['Gaja Pade'], ids['Malnad Fighters'], ids['Code Blue']]

    _play(d['owner'], event_id, q1, 25, 31)                           # Gaja Pade straight to the final
    _play(d['owner'], event_id, elim, 33, 28)                         # Code Blue out
    t = _t(d, event_id)
    q2, final = _stage(t, 'qualifier2'), _stage(t, 'final')
    assert (name[q2['home']], name[q2['away']]) == ('Garuda Sena', 'Malnad Fighters')
    assert final['home'] == ids['Gaja Pade'] and final['away'] is None
    assert sports.placings(t) == {}
    _play(d['owner'], event_id, q2, 30, 30, winner=q2['home'])        # a tie: Garuda Sena go through
    final = _stage(_t(d, event_id), 'final')
    assert (name[final['home']], name[final['away']]) == ('Gaja Pade', 'Garuda Sena')
    _play(d['owner'], event_id, final, 29, 34)
    t = _t(d, event_id)
    assert {name[k]: v for k, v in sports.placings(t).items()} == {'Garuda Sena': 1, 'Gaja Pade': 2, 'Malnad Fighters': 3}
    assert sports.champion(t) == ids['Garuda Sena'] and sports.bracket(t)['champion'] == ids['Garuda Sena']

    with pytest.raises(sports.TournamentError, match='Undo the playoffs first'):
        sports.set_playoff_style(t, 'semis')


def _table_league(n=5):
    teams = [{'id': f't{i}', 'name': f'Team {i}'} for i in range(1, n + 1)]
    t = sports.generate(teams, 'league_knockout')
    for m in t['matches']:                         # the lower number wins: Team 1 tops the table
        home_wins = int(m['home'][1:]) < int(m['away'][1:])
        t = sports.record_result(t, m['id'], 30 if home_wins else 20, 20 if home_wins else 30)
    return t


def test_ipl_playoffs_without_pools_are_1_v_2_and_3_v_4_and_can_be_cleared_and_undone():
    t = sports.set_playoff_style(_table_league(), 'ipl')
    t = sports.make_playoffs(t, 4, third_place=True)                 # IPL has no third-place match
    assert [m['stage'] for m in t['matches'] if m.get('stage') in sports.KNOCKOUT_STAGES] == [
        'qualifier1', 'eliminator', 'qualifier2', 'final']
    q1, elim = _stage(t, 'qualifier1'), _stage(t, 'eliminator')
    assert (q1['home'], q1['away'], elim['home'], elim['away']) == ('t1', 't2', 't3', 't4')

    t = sports.record_result(t, q1['id'], 30, 20)                    # Team 1 to the final, Team 2 to Q2
    assert _stage(t, 'final')['home'] == 't1' and _stage(t, 'qualifier2')['home'] == 't2'
    t = sports.clear_result(t, q1['id'])                             # taken back out of both
    assert _stage(t, 'final')['home'] is None and _stage(t, 'qualifier2')['home'] is None

    # A seeding changed by hand keeps the seeds as the first two matches
    t = sports.set_match_teams(t, elim['id'], 't4', 't3')
    assert t['playoffs']['seeds'] == ['t1', 't2', 't4', 't3']
    with pytest.raises(sports.TournamentError, match='already plays'):
        sports.set_match_teams(t, elim['id'], 't1', 't3')

    t = sports.undo_playoffs(t)
    assert not sports.has_playoffs(t) and t['playoff_style'] == 'ipl'
    t = sports.make_playoffs(sports.set_playoff_style(t, 'semis'), 4)
    semis = [m for m in t['matches'] if m.get('stage') == 'semi']
    assert [(m['home'], m['away']) for m in semis] == [('t1', 't4'), ('t2', 't3')]


def test_a_triangular_series_has_no_ipl_style():
    teams = [{'id': f't{i}', 'name': f'Team {i}'} for i in range(1, 4)]
    with pytest.raises(sports.TournamentError, match='final only'):
        sports.set_playoff_style(sports.generate(teams, 'triangular'), 'ipl')
