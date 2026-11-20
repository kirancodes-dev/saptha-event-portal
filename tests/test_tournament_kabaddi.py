"""
tests/test_tournament_kabaddi.py — UPG-350: a kabaddi league's points (5 a win,
3 a tie, 1 for losing by 7 or fewer, 0 otherwise), its table ordered by points,
score difference and points scored, and the "League then knockout" format: the
league, then the top 4 play semi-finals 1 v 4 and 2 v 3, a final and a
third-place match, whose results are the event's places.
"""
import re

import services_sports as sports
from tests.test_sports_tournament import _play, _t, cup  # noqa: F401


def _kabaddi(d, names, fmt='League then knockout'):
    event_id, ids = d['event'](names)
    d['db'].collection('events').document(event_id).update(
        {'details': {'sport': 'Kabaddi', 'format': fmt, 'gender': 'Men'}})
    return event_id, ids


def test_the_kabaddi_table_gives_5_3_1_0_and_orders_by_score_difference(cup):  # noqa: F811
    d = cup
    event_id, ids = _kabaddi(d, ['Ants', 'Bees', 'Cats', 'Dogs'], fmt='League')
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert re.search(r'<option value="league" selected>', page)            # the event's own format
    for field, value in (('win', 5), ('draw', 3), ('loss', 0), ('close_loss', 1), ('close_margin', 7)):
        assert re.search(rf'name="points_{field}" class="form-control" value="{value}"', page), field

    d['owner'].post(f'/tournament/{event_id}/generate', data={
        'format': 'league', 'points_win': '5', 'points_draw': '3', 'points_loss': '0',
        'points_close_loss': '1', 'points_close_margin': '7'})
    t = _t(d, event_id)
    assert t['sport'] == 'Kabaddi' and t['points']['close_margin'] == 7
    name = {v: k for k, v in ids.items()}
    scores = {('Ants', 'Bees'): (30, 25),       # Bees lose by 5: 1 point
              ('Ants', 'Cats'): (30, 30),       # a tie: 3 each
              ('Ants', 'Dogs'): (40, 20),       # Dogs lose by 20: nothing
              ('Bees', 'Cats'): (28, 21),       # Cats lose by exactly 7: 1 point
              ('Bees', 'Dogs'): (33, 30),
              ('Cats', 'Dogs'): (35, 34)}
    for m in t['matches']:
        home, away = name[m['home']], name[m['away']]
        h, a = scores[(home, away)] if (home, away) in scores else scores[(away, home)][::-1]
        _play(d['coord'], event_id, m, h, a)
    table = [(r['name'], r['won'], r['drawn'], r['lost'], r['points']) for r in sports.standings(_t(d, event_id))]
    assert table == [('Ants', 2, 1, 0, 13), ('Bees', 2, 0, 1, 11), ('Cats', 1, 1, 1, 9), ('Dogs', 0, 0, 3, 2)]

    page = d['app'].test_client().get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert '>SD</abbr>' in page and '>T</abbr>' in page and 'Kabaddi' in page

    # Level on points: the score difference decides, then the points scored
    teams = [{'id': x, 'name': x} for x in 'XYZ']
    for (xz, yz, xy), order in ((((30, 20), (25, 20), (20, 20)), ['X', 'Y', 'Z']),     # SD +10 v +5
                                (((30, 20), (20, 10), (25, 25)), ['X', 'Y', 'Z'])):    # SD level, scored 55 v 45
        t = sports.generate(teams, 'league', sports.KABADDI_POINTS, sport='Kabaddi')
        pairs = {('X', 'Z'): xz, ('Y', 'Z'): yz, ('X', 'Y'): xy}
        for m in t['matches']:
            key = (m['home'], m['away'])
            h, a = pairs[key] if key in pairs else pairs[key[::-1]][::-1]
            t = sports.record_result(t, m['id'], h, a)
        rows = sports.standings(t)
        assert [r['id'] for r in rows] == order and rows[0]['points'] == rows[1]['points'] == 8


def test_a_six_team_league_then_knockout(cup):  # noqa: F811
    d = cup
    names = [f'Team {i}' for i in range(1, 7)]
    event_id, ids = _kabaddi(d, names)
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert re.search(r'<option value="league_knockout" selected>', page)

    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league_knockout', 'third_place': 'yes'})
    t = _t(d, event_id)
    assert t['format'] == 'league_knockout' and len(t['matches']) == 15
    assert all(m['stage'] == 'league' for m in t['matches'])
    assert t['points'] == sports.KABADDI_POINTS                         # the kabaddi preset
    seed = {v: int(k.split()[1]) for k, v in ids.items() if k in names}

    # The playoffs wait for the league
    d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '4', 'third_place': 'yes'})
    assert not sports.has_playoffs(_t(d, event_id))
    assert 'Once every league match has a result' in d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)

    for m in t['matches']:                                              # the lower number wins: 1, 2, … 6
        home_wins = seed[m['home']] < seed[m['away']]
        _play(d['coord'], event_id, m, 30 if home_wins else 20, 20 if home_wins else 30)
    assert [r['name'] for r in sports.standings(_t(d, event_id))] == names
    assert 'Make the playoffs' in d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    # Only the SPOC makes them
    assert d['coord'].post(f'/tournament/{event_id}/playoffs', data={'size': '4'}).status_code == 403

    d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '4', 'third_place': 'yes'})
    t = _t(d, event_id)
    semis = [m for m in t['matches'] if m.get('stage') == 'semi']
    assert [(seed[m['home']], seed[m['away']]) for m in semis] == [(1, 4), (2, 3)]
    assert sports.placings(t) == {}
    league_match = t['matches'][0]                                       # the table is fixed now
    _play(d['coord'], event_id, league_match, 0, 50)
    assert _t(d, event_id)['matches'][0]['home_score'] == league_match['home_score']

    # Semi-final 1 is tied 30-30: someone must go through, here Team 4
    _play(d['coord'], event_id, semis[0], 30, 30)
    assert [m for m in _t(d, event_id)['matches'] if m['id'] == semis[0]['id']][0]['status'] == 'scheduled'
    _play(d['coord'], event_id, semis[0], 30, 30, winner=ids['Team 4'])
    _play(d['coord'], event_id, semis[1], 35, 25)                        # Team 2 beats Team 3
    t = _t(d, event_id)
    final = [m for m in t['matches'] if m.get('stage') == 'final'][0]
    third = [m for m in t['matches'] if m.get('stage') == 'third'][0]
    assert (seed[final['home']], seed[final['away']]) == (4, 2)
    assert (seed[third['home']], seed[third['away']]) == (1, 3)
    _play(d['coord'], event_id, final, 22, 31)                           # Team 2 wins the final
    _play(d['coord'], event_id, third, 40, 30)                           # Team 1 is third
    t = _t(d, event_id)
    assert sports.champion(t) == ids['Team 2']
    assert sports.placings(t) == {ids['Team 2']: 1, ids['Team 4']: 2, ids['Team 1']: 3}

    page = d['app'].test_client().get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert 'Semi-final' in page and 'Third place' in page and 'League round 1' in page
    assert 'Champion: Team 2' in page

    d['owner'].post(f'/tournament/{event_id}/publish')
    regs = [r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()]
    assert {r['team_name']: r.get('final_rank') for r in regs if r.get('final_rank')} == \
        {'Team 2': 1, 'Team 4': 2, 'Team 1': 3}


def test_the_top_two_play_the_final_alone():
    teams = [{'id': f'k{i}', 'name': f'K{i}'} for i in range(1, 4)]
    t = sports.generate(teams, 'league_knockout', sports.KABADDI_POINTS, sport='Kabaddi')
    for m in t['matches']:
        home_wins = m['home'] < m['away']
        t = sports.record_result(t, m['id'], 30 if home_wins else 20, 20 if home_wins else 30)
    t = sports.make_playoffs(t, size=2)
    [final] = [m for m in t['matches'] if m.get('stage') == 'final']
    assert (final['home'], final['away']) == ('k1', 'k2') and len(t['matches']) == 4
    t = sports.record_result(t, final['id'], 20, 25)
    assert sports.placings(t) == {'k2': 1, 'k1': 2}                     # no semi-finals: no third
