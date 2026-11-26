"""
tests/test_top3_eliminator.py — UPG-480: the women's triangular series ends
with the 3 teams level on points, so the score difference orders the table;
1st goes straight to the final, 2nd v 3rd play an Eliminator, and its winner
meets 1st in the final. The Eliminator's loser is third. The 3 league
results stay as they are, even when a top-2 final was made first and undone.
"""
import re

import pytest

import services_sports as sports
from tests.test_sports_tournament import _play, _t, cup  # noqa: F401


def _level_series(d):
    """Shakti, Durga and Chamundi each win once: 2 points each (PKL 12); the
    score difference puts Durga 1st (+12), Shakti 2nd (+2), Chamundi 3rd (-14)."""
    event_id, ids = d['event'](['Shakti', 'Durga', 'Chamundi'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'triangular', 'rules': 'pkl12'})
    t = _t(d, event_id)
    name = sports.names(t)
    scores = {frozenset({'Shakti', 'Durga'}): {'Shakti': 30, 'Durga': 25},
              frozenset({'Durga', 'Chamundi'}): {'Durga': 40, 'Chamundi': 23},
              frozenset({'Shakti', 'Chamundi'}): {'Chamundi': 31, 'Shakti': 28}}
    for m in t['matches']:
        s = scores[frozenset({name[m['home']], name[m['away']]})]
        _play(d['owner'], event_id, m, s[name[m['home']]], s[name[m['away']]])
    t = _t(d, event_id)
    table = sports.standings(t)
    assert [r['points'] for r in table] == [2, 2, 2]
    assert [name[r['id']] for r in table] == ['Durga', 'Shakti', 'Chamundi']
    return event_id, ids


def test_level_on_points_1st_waits_in_the_final_and_2nd_v_3rd_play_the_eliminator(cup):  # noqa: F811
    d = cup
    event_id, ids = _level_series(d)
    league = [dict(m) for m in _t(d, event_id)['matches']]
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert re.search(r'<option value="3" data-top3>Top 3: Eliminator 2nd v 3rd', page)  # not pre-selected since UPG-481

    resp = d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '3'}, follow_redirects=True)
    assert 'the Eliminator, 2nd v 3rd, then its winner plays 1st in the final' in resp.get_data(as_text=True)
    t = _t(d, event_id)
    assert t['matches'][:3] == league                                # the league results are untouched
    elim, final = t['matches'][3], t['matches'][4]
    assert len(t['matches']) == 5
    assert (sports.stage_name(elim), elim['home'], elim['away']) == ('Eliminator', ids['Shakti'], ids['Chamundi'])
    assert (sports.stage_name(final), final['home'], final['away']) == ('Final', ids['Durga'], None)
    assert t['playoffs']['seeds'] == [ids['Durga'], ids['Shakti'], ids['Chamundi']]

    b = sports.bracket(t)
    assert [c['title'] for c in b['columns']] == ['Eliminator', 'Final']
    assert (b['columns'][1]['slots'][0]['home_label'], b['columns'][1]['slots'][0]['away_label']) == ('1st', 'Winner Eliminator')
    assert 'Winner Eliminator' in d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)

    _play(d['owner'], event_id, elim, 27, 27, winner=elim['away'])    # a tie: Chamundi win the tie-breaker
    final = _t(d, event_id)['matches'][4]
    assert (final['home'], final['away']) == (ids['Durga'], ids['Chamundi'])
    assert sports.placings(_t(d, event_id)) == {}
    _play(d['owner'], event_id, final, 22, 26)
    t = _t(d, event_id)
    assert sports.placings(t) == {ids['Chamundi']: 1, ids['Durga']: 2, ids['Shakti']: 3}
    assert sports.champion(t) == ids['Chamundi'] and t['matches'][:3] == league

    d['owner'].post(f'/tournament/{event_id}/publish')
    regs = {r.id: r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()}
    assert {ids[n]: regs[ids[n]].get('final_rank') for n in ('Chamundi', 'Durga', 'Shakti')} == {
        ids['Chamundi']: 1, ids['Durga']: 2, ids['Shakti']: 3}


def test_a_top_2_final_already_made_is_undone_and_made_again_as_top_3_with_no_result_lost(cup):  # noqa: F811
    d = cup
    event_id, ids = _level_series(d)
    league = [dict(m) for m in _t(d, event_id)['matches']]
    d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '2'})
    assert len(_t(d, event_id)['matches']) == 4
    d['owner'].post(f'/tournament/{event_id}/playoffs/undo')
    t = _t(d, event_id)
    assert t['matches'] == league and not sports.has_playoffs(t)
    d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '3'})
    t = _t(d, event_id)
    assert t['matches'][:3] == league and [m['stage'] for m in t['matches'][3:]] == ['eliminator', 'final']


def test_top_3_rules_and_fixes():
    teams = [{'id': f't{i}', 'name': f'Team {i}'} for i in range(1, 5)]
    t = sports.generate(teams, 'league_knockout')
    for m in t['matches']:                         # the lower number wins: Team 1 tops the table
        home_wins = int(m['home'][1:]) < int(m['away'][1:])
        t = sports.record_result(t, m['id'], 30 if home_wins else 20, 20 if home_wins else 30)
    t = sports.make_playoffs(t, 3)                 # works for any one table of 3 or more
    elim = next(m for m in t['matches'] if m['stage'] == 'eliminator')
    final = next(m for m in t['matches'] if m['stage'] == 'final')
    assert (elim['home'], elim['away'], final['home']) == ('t2', 't3', 't1')
    t = sports.record_result(t, elim['id'], 30, 20)
    assert next(m for m in t['matches'] if m['stage'] == 'final')['away'] == 't2'
    t = sports.clear_result(t, elim['id'])         # the winner comes back out of the final; 1st stays
    final = next(m for m in t['matches'] if m['stage'] == 'final')
    assert (final['home'], final['away']) == ('t1', None)
    t = sports.set_match_teams(t, elim['id'], 't3', 't4')
    assert t['playoffs']['seeds'] == ['t1', 't3', 't4']

    pooled = {'format': 'league_knockout', 'pools': ['A', 'B'], 'matches': [], 'teams': []}
    with pytest.raises(sports.TournamentError, match='without pools'):
        sports.make_playoffs(dict(pooled, matches=[{'id': 'm1', 'stage': 'league', 'status': 'played'}]), 3)
