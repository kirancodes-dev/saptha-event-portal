"""
tests/test_triangular_series.py — UPG-473, the owner, 24 Nov 2026: "for girls
there is only 3 teams so that will be conducted as a triangle match". A
triangular series: each of the 3 teams plays the other two, then 1st and 2nd
in the table play the final, and the team that missed the final is third. It
is a league then knockout underneath, so scoring, the boards, the score sheet
and the fixture sheet work as for one. Made-up names.
"""
import re

import pytest

import services_sports as sports
from tests.test_sports_tournament import cup  # noqa: F401

TEAMS = [{'id': 'w1', 'name': 'Shakti'}, {'id': 'w2', 'name': 'Durga'}, {'id': 'w3', 'name': 'Chamundi'}]


def _league(t, scores):
    for m, (h, a) in zip([m for m in t['matches'] if m.get('stage') == 'league'], scores):
        t = sports.record_result(t, m['id'], h, a)
    return t


def test_each_team_plays_the_other_two_then_1st_v_2nd_play_the_final():
    t = sports.generate(TEAMS, 'triangular', sports.PKL12_POINTS, sport='Kabaddi', tiebreak=True)
    assert t['format'] == 'league_knockout' and t['triangular'] and sports.format_name(t) == 'Triangular series'
    pairs = {frozenset((m['home'], m['away'])) for m in t['matches']}
    assert len(t['matches']) == 3 and pairs == {frozenset(p) for p in (('w1', 'w2'), ('w1', 'w3'), ('w2', 'w3'))}
    assert all(m['stage'] == 'league' for m in t['matches'])
    # Before the league is over the road to the final names no team
    assert sports.bracket(t)['columns'][0]['slots'][0]['home'] is None
    with pytest.raises(sports.TournamentError, match='Finish the league first'):
        sports.make_playoffs(t, 2)
    t = _league(t, [(30, 20), (25, 28), (31, 22)])
    table = sports.standings(t)
    t = sports.make_playoffs(t, 2)
    [final] = [m for m in t['matches'] if m.get('stage') == 'final']
    assert (final['home'], final['away']) == (table[0]['id'], table[1]['id'])
    assert sports.placings(t) == {}                                       # not decided until the final
    t = sports.record_result(t, final['id'], 24, 27)
    assert sports.placings(t) == {table[1]['id']: 1, table[0]['id']: 2, table[2]['id']: 3}
    assert sports.champion(t) == table[1]['id']


def test_a_triangular_series_is_for_three_teams_without_pools():
    with pytest.raises(sports.TournamentError, match='exactly 3 teams; there are 4'):
        sports.generate(TEAMS + [{'id': 'w4', 'name': 'Kali'}], 'triangular')
    with pytest.raises(sports.TournamentError, match='no pools'):
        sports.generate(TEAMS, 'triangular', pools={'w1': ('A', 1), 'w2': ('A', 2), 'w3': ('B', 1)})
    twice = sports.generate(TEAMS, 'triangular', legs=2)
    assert len(twice['matches']) == 6 and twice['legs'] == 2              # each pair twice, home and away
    # Other formats are as before: a league then knockout's top-2 final still gives no third
    plain = _league(sports.generate(TEAMS, 'league_knockout'), [(30, 20), (25, 28), (31, 22)])
    plain = sports.make_playoffs(plain, 2)
    final = plain['matches'][-1]
    plain = sports.record_result(plain, final['id'], 30, 20)
    assert len(sports.placings(plain)) == 2 and sports.format_name(plain) == 'League then knockout'


def test_the_spoc_sets_up_a_triangular_series_for_three_teams(cup):  # noqa: F811
    d = cup
    event_id, ids = d['event'](['Shakti', 'Durga', 'Chamundi'])
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert re.search(r'<option value="triangular" selected data-triangular>Triangular series', page)
    resp = d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'triangular', 'rules': 'pkl12'})
    assert resp.status_code == 302
    t = d['db'].collection('events').document(event_id).get().to_dict()['tournament']
    assert t['triangular'] and len(t['matches']) == 3 and t['tiebreak']
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'Format: <strong>Triangular series</strong>' in page
    public = d['app'].test_client().get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert 'Triangular series' in public
    # The league played, the playoffs card offers the final, and its third is the table's third
    for m in t['matches']:
        d['owner'].post(f"/tournament/{event_id}/match/{m['id']}/result",
                        data={'home_score': '30', 'away_score': '20'})
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'Top 2: the final (the 3rd team in the table is third)' in page
    d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '2'})
    t = d['db'].collection('events').document(event_id).get().to_dict()['tournament']
    final = t['matches'][-1]
    assert final['stage'] == 'final' and len(t['matches']) == 4
    d['owner'].post(f"/tournament/{event_id}/match/{final['id']}/result", data={'home_score': '25', 'away_score': '21'})
    d['owner'].post(f'/tournament/{event_id}/publish')
    regs = [r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()]
    ranks = sorted(r['final_rank'] for r in regs if r.get('final_rank'))
    assert ranks == [1, 2, 3]


def test_four_teams_get_no_triangular_choice(cup):  # noqa: F811
    d = cup
    event_id, _ = d['event'](['Shakti', 'Durga', 'Chamundi', 'Kali'])
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'value="triangular"' not in page
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'triangular'})
    assert not d['db'].collection('events').document(event_id).get().to_dict().get('tournament')
