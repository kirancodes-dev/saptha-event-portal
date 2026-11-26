"""
tests/test_league_again.py — UPG-481: the women's 3 teams finished level after
one round, so every pair plays once more: M-04 to M-06, home and away swapped.
The 3 matches already played keep their results; the table counts all 6; then
the final as before (1st v 2nd, the 3rd team in the table third).
"""
import pytest

import services_sports as sports
from tests.test_sports_tournament import _play, _t, cup  # noqa: F401


def test_three_more_matches_then_the_final_with_no_result_lost(cup):  # noqa: F811
    d = cup
    event_id, ids = d['event'](['Shakti', 'Durga', 'Chamundi'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'triangular', 'rules': 'pkl12'})
    for m in _t(d, event_id)['matches']:                         # each team wins once: level on points
        _play(d['owner'], event_id, m, 30, 25)
    played = [dict(m) for m in _t(d, event_id)['matches']]
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'data-league-again' in page and '(3 more matches)' in page
    # The final is pre-selected again (not Top 3)
    assert '<option value="3" data-top3>' in page

    assert d['coord'].post(f'/tournament/{event_id}/league_again').status_code == 403
    resp = d['owner'].post(f'/tournament/{event_id}/league_again', follow_redirects=True)
    assert '3 more league matches: M-04, M-05, M-06.' in resp.get_data(as_text=True)
    t = _t(d, event_id)
    assert t['matches'][:3] == played                              # nothing already there changed
    new = t['matches'][3:]
    assert [sports.match_no(m) for m in new] == ['M-04', 'M-05', 'M-06']
    assert [(m['home'], m['away']) for m in new] == [(m['away'], m['home']) for m in played]
    assert all(m['stage'] == 'league' and m['status'] == 'scheduled' and m['leg'] == 2 for m in new)
    assert min(m['round'] for m in new) > max(m['round'] for m in played)
    assert not sports.league_done(t)
    assert 'data-league-again' not in d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)

    name = sports.names(t)
    wins = {'Durga': 40, 'Shakti': 33, 'Chamundi': 20}              # Durga top, Shakti 2nd, Chamundi 3rd
    for m in new:
        _play(d['owner'], event_id, m, wins[name[m['home']]], wins[name[m['away']]])
    t = _t(d, event_id)
    table = sports.standings(t)
    assert [r['played'] for r in table] == [4, 4, 4]
    assert [name[r['id']] for r in table] == ['Durga', 'Shakti', 'Chamundi']
    d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '2'})
    t = _t(d, event_id)
    final = t['matches'][-1]
    assert (sports.match_no(final), final['stage'], final['home'], final['away']) == (
        'M-07', 'final', ids['Durga'], ids['Shakti'])
    assert t['matches'][:3] == played
    _play(d['owner'], event_id, final, 22, 30)
    assert sports.placings(_t(d, event_id)) == {ids['Shakti']: 1, ids['Durga']: 2, ids['Chamundi']: 3}


def test_the_league_again_is_refused_after_the_playoffs_with_pools_or_twice():
    teams = [{'id': f't{i}', 'name': f'Team {i}'} for i in range(1, 4)]
    t = sports.generate(teams, 'triangular')
    for m in t['matches']:
        t = sports.record_result(t, m['id'], 30, 20)
    with pytest.raises(sports.TournamentError, match='Undo the playoffs first'):
        sports.play_league_again(sports.make_playoffs(t, 2))
    again = sports.play_league_again(t)
    assert len(again['matches']) == 6 and again['legs'] == 2
    with pytest.raises(sports.TournamentError, match='already plays twice'):
        sports.play_league_again(again)
    with pytest.raises(sports.TournamentError, match='pools'):
        sports.play_league_again(dict(t, pools=['A', 'B']))
    with pytest.raises(sports.TournamentError, match='Only a league'):
        sports.play_league_again(dict(t, format='knockout'))
