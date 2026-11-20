"""
tests/test_live_match_stats.py — UPG-352: each player's raid and tackle points
add up across the matches scored live, with a Super 10 (10+ raid points in a
match) and a High 5 (5+ tackle points) counted; the public fixtures page lists
the top raiders and defenders, and a match's scoreboard who scored in it.
"""
import services_live_match as live
from tests.test_live_match import _kabaddi_knockout, _tap
from tests.test_sports_tournament import _t, cup  # noqa: F401


def _squad(d, reg_id, names):
    d['db'].collection('registrations').document(reg_id).update(
        {'lead_name': names[0], 'members': [{'name': n} for n in names]})


def _score(d, event_id, m, taps):
    d['owner'].get(f"/tournament/{event_id}/match/{m['id']}/score")
    _tap(d['owner'], event_id, m['id'], op='phase', action='start')
    for side, kind, points, player in taps:
        status, _ = _tap(d['owner'], event_id, m['id'], op='point', team=side, kind=kind, points=points, player=player)
        assert status == 200


def test_stats_add_up_across_two_matches_with_super_10s_and_high_5s(cup):  # noqa: F811
    d = cup
    event_id, ids, first = _kabaddi_knockout(d)
    t = _t(d, event_id)
    second = [m for m in t['matches'] if m['round'] == 1][1]
    names = {v: k for k, v in ids.items()}
    for m in (first, second):
        for side in ('home', 'away'):
            team = names[m[side]]
            _squad(d, m[side], [f'{team} Raider', f'{team} Corner'])
    h1, a1 = names[first['home']], names[first['away']]
    h2 = names[second['home']]

    # Match 1: the home raider makes a Super 10 (4+4+2 raid, +1 bonus = 11), the away corner a High 5 (1+2+2)
    _score(d, event_id, first, [('home', 'raid', 4, f'{h1} Raider'), ('home', 'raid', 4, f'{h1} Raider'),
                                ('home', 'raid', 2, f'{h1} Raider'), ('home', 'bonus', None, f'{h1} Raider'),
                                ('away', 'tackle', None, f'{a1} Corner'), ('away', 'super_tackle', None, f'{a1} Corner'),
                                ('away', 'super_tackle', None, f'{a1} Corner'),
                                ('home', 'tackle', None, f'{h1} Corner'),
                                ('away', 'all_out', None, ''),            # a team's points, nobody's
                                ('away', 'raid', 1, '')])                 # not recorded against a player
    # Match 2: the home raider gets 6, the corner 2
    _score(d, event_id, second, [('home', 'raid', 3, f'{h2} Raider'), ('home', 'raid', 3, f'{h2} Raider'),
                                 ('home', 'tackle', None, f'{h2} Corner'), ('home', 'tackle', None, f'{h2} Corner')])
    # The first match's raider and corner also play in a third live document (the final, say)
    final = [m for m in _t(d, event_id)['matches'] if m.get('stage') == 'final'][0]
    tourn = _t(d, event_id)
    tourn['matches'] = [dict(m, home=first['home'], away=second['home']) if m['id'] == final['id'] else m
                        for m in tourn['matches']]
    d['db'].collection('events').document(event_id).update({'tournament': tourn})
    final = dict(final, home=first['home'], away=second['home'])
    _score(d, event_id, final, [('home', 'raid', 2, f'{h1} Raider'), ('away', 'tackle', None, f'{h2} Corner')])

    live._cache.clear()
    import services_sports
    stats = {(r['team'], r['player']): r for r in
             live.event_stats(d['db'], event_id, services_sports.names(_t(d, event_id)))}
    raider = stats[(h1, f'{h1} Raider')]
    assert (raider['raid'], raider['tackle'], raider['total'], raider['matches'], raider['super_10']) == (13, 0, 13, 2, 1)
    corner = stats[(a1, f'{a1} Corner')]
    assert (corner['tackle'], corner['matches'], corner['high_5'], corner['super_10']) == (5, 1, 1, 0)
    other = stats[(h2, f'{h2} Raider')]
    assert (other['raid'], other['super_10']) == (6, 0)
    assert stats[(h2, f'{h2} Corner')]['tackle'] == 3 and stats[(h2, f'{h2} Corner')]['matches'] == 2
    assert all(p for _, p in stats)                                     # unnamed points aren't anyone's
    assert [r['player'] for r in live.top(list(stats.values()), 'raid')] == [f'{h1} Raider', f'{h2} Raider']
    assert [r['player'] for r in live.top(list(stats.values()), 'tackle')][:2] == [f'{a1} Corner', f'{h2} Corner']


def test_the_public_pages_list_the_leaders(cup):  # noqa: F811
    d = cup
    event_id, ids, m = _kabaddi_knockout(d)          # Panthers' squad: Pawan, Naveen, Fazel
    panthers = 'home' if m['home'] == ids['Panthers'] else 'away'
    _score(d, event_id, m, [(panthers, 'raid', 4, 'Naveen'), (panthers, 'raid', 3, 'Naveen'),
                            (panthers, 'raid', 3, 'Naveen'), (panthers, 'tackle', None, 'Fazel')])
    live._cache.clear()
    anonymous = d['app'].test_client()
    page = anonymous.get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    stats = page[page.index('data-player-stats'):]
    assert 'Top raiders' in stats and 'Top defenders' in stats
    raiders = stats[stats.index('Top raiders'):stats.index('Top defenders')]
    assert 'Naveen' in raiders and '<strong>10</strong>' in raiders and 'Panthers' in raiders
    assert 'Fazel' in stats[stats.index('Top defenders'):]

    board = anonymous.get(f"/tournament/live/{event_id}/{m['id']}").get_data(as_text=True)
    rows = board[board.index('data-match-players'):]
    assert 'Naveen <span class="badge bg-primary">Super 10</span>' in rows and 'Fazel' in rows
