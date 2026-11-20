"""
tests/test_live_match.py — UPG-351: a kabaddi match scored live, point by
point: raids, bonuses, tackles, super tackles and all outs add up per team and
per half; undo takes the last point back; a tap sent twice counts once. Full
time saves the result to the fixtures and moves a knockout's winner on (a tie
needs the winner chosen). Only the SPOC or an assigned coordinator scores;
anyone can watch the live scoreboard and its JSON without logging in.
"""
import itertools

import services_live_match as live
from tests.test_integration_flow import _login, _unique, _user
from tests.test_sports_tournament import _t, cup  # noqa: F401

_taps = itertools.count(1)


def _kabaddi_knockout(d):
    event_id, ids = d['event'](['Panthers', 'Bulls', 'Titans', 'Giants'])
    d['db'].collection('events').document(event_id).update({'details': {'sport': 'Kabaddi', 'format': 'Knockout'}})
    reg = d['db'].collection('registrations').document(ids['Panthers'])
    reg.update({'lead_name': 'Pawan', 'members': [{'name': 'Pawan'}, {'name': 'Naveen'}, {'name': 'Fazel'}]})
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout'})
    first = [m for m in _t(d, event_id)['matches'] if m['round'] == 1][0]
    return event_id, ids, first


def _tap(client, event_id, match_id, tap=None, **body):
    body['tap'] = tap or f'tap-{next(_taps)}'
    resp = client.post(f'/tournament/{event_id}/match/{match_id}/score', json=body)
    return resp.status_code, resp.get_json()


def test_a_match_scored_point_by_point(cup):  # noqa: F811
    d = cup
    event_id, ids, m = _kabaddi_knockout(d)
    home_is_panthers = m['home'] == ids['Panthers']
    side = 'home' if home_is_panthers else 'away'
    other = 'away' if home_is_panthers else 'home'

    page = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Super tackle +2' in html and 'Raid +4' in html and '<option value="Naveen">Naveen</option>' in html

    status, data = _tap(d['coord'], event_id, m['id'], op='point', team=side, kind='raid', points=2)
    assert status == 409 and 'Start the half' in data['error']                  # not started yet
    assert _tap(d['coord'], event_id, m['id'], op='phase', action='start')[0] == 200

    _tap(d['coord'], event_id, m['id'], op='point', team=side, kind='raid', points=2, player='Naveen')
    _tap(d['coord'], event_id, m['id'], op='point', team=other, kind='tackle')
    _tap(d['coord'], event_id, m['id'], op='point', team=side, kind='bonus', player='Fazel')
    status, data = _tap(d['coord'], event_id, m['id'], op='point', team=other, kind='super_tackle')
    assert data['state'][side]['total'] == 3 and data['state'][other]['total'] == 3
    # The same tap twice (a retry) counts once
    for _ in range(2):
        status, data = _tap(d['coord'], event_id, m['id'], tap='retry-1', op='point', team=side, kind='raid', points=1)
    assert data['state'][side]['total'] == 4

    _tap(d['coord'], event_id, m['id'], op='phase', action='half_time')
    status, data = _tap(d['coord'], event_id, m['id'], op='point', team=side, kind='raid', points=1)
    assert status == 409                                                          # no points at half time
    _tap(d['coord'], event_id, m['id'], op='phase', action='second_half')
    _tap(d['coord'], event_id, m['id'], op='point', team=side, kind='all_out')
    _tap(d['coord'], event_id, m['id'], op='point', team=other, kind='raid', points=3)
    status, data = _tap(d['coord'], event_id, m['id'], op='point', team=other, kind='technical')
    assert data['state'][other]['total'] == 7
    status, data = _tap(d['coord'], event_id, m['id'], op='undo')                 # the technical point was wrong
    s = data['state']
    assert (s[side]['total'], s[side]['halves'], s[side]['raid'], s[side]['extra']) == (6, [4, 2], 4, 2)
    assert (s[other]['total'], s[other]['halves'], s[other]['tackle'], s[other]['raid']) == (6, [3, 3], 3, 3)
    assert s['recent'][0].startswith('Raid +3')
    assert any('Naveen' in line for line in live.state(live.get(d['db'], event_id, m['id']), {}, last=20)['recent'])
    # Bad input is refused
    assert _tap(d['coord'], event_id, m['id'], op='point', team=side, kind='raid', points=9)[0] == 409
    assert _tap(d['coord'], event_id, m['id'], op='point', team=side, kind='goal')[0] == 409


def test_full_time_writes_the_result_and_a_tie_needs_a_winner(cup):  # noqa: F811
    d = cup
    event_id, ids, m = _kabaddi_knockout(d)
    d['owner'].get(f"/tournament/{event_id}/match/{m['id']}/score")
    for action in ('start', 'half_time', 'second_half'):
        _tap(d['owner'], event_id, m['id'], op='phase', action=action)
    _tap(d['owner'], event_id, m['id'], op='point', team='home', kind='raid', points=2)
    _tap(d['owner'], event_id, m['id'], op='point', team='away', kind='tackle')
    _tap(d['owner'], event_id, m['id'], op='point', team='away', kind='bonus')

    status, data = _tap(d['owner'], event_id, m['id'], op='phase', action='full_time')     # 2-2
    assert status == 409 and 'choose who goes through' in data['error']
    assert live.get(d['db'], event_id, m['id'])['phase'] == 'second_half'
    assert [x for x in _t(d, event_id)['matches'] if x['id'] == m['id']][0]['status'] == 'scheduled'

    status, data = _tap(d['owner'], event_id, m['id'], op='phase', action='full_time', winner=m['away'])
    assert status == 200 and data['state']['phase'] == 'full_time'
    t = _t(d, event_id)
    played = [x for x in t['matches'] if x['id'] == m['id']][0]
    assert (played['status'], played['home_score'], played['away_score'], played['winner']) == \
        ('played', 2, 2, m['away'])
    nxt = [x for x in t['matches'] if x['id'] == played['next']][0]
    assert nxt[played['next_side']] == m['away']                                 # moved on to the final
    # Over: no more points or undo
    assert _tap(d['owner'], event_id, m['id'], op='point', team='home', kind='bonus')[0] == 409
    assert _tap(d['owner'], event_id, m['id'], op='undo')[0] == 409


def test_only_staff_score_and_anyone_can_watch(cup):  # noqa: F811
    d = cup
    event_id, ids, m = _kabaddi_knockout(d)
    url = f"/tournament/{event_id}/match/{m['id']}/score"
    other_spoc, student = f"{_unique('ospoc')}@test.edu", f"{_unique('fan')}@test.edu"
    _user(d['db'], other_spoc, 'ClubSPOC')
    _user(d['db'], student, 'Student')
    for client in (_login(d['app'], other_spoc, 'ClubSPOC'), _login(d['app'], student, 'Student')):
        assert client.get(url).status_code == 403
        assert client.post(url, json={'op': 'phase', 'action': 'start', 'tap': 'x'}).status_code == 403
    anonymous = d['app'].test_client()
    assert anonymous.get(url).status_code in (302, 401)
    assert anonymous.post(url, json={'op': 'phase', 'action': 'start', 'tap': 'y'}).status_code in (302, 401)
    assert live.get(d['db'], event_id, m['id']) is None

    # Before it starts the board says so
    board = anonymous.get(f"/tournament/live/{event_id}/{m['id']}")
    assert board.status_code == 200 and 'The score appears here when the match starts' in board.get_data(as_text=True)

    d['coord'].get(url)
    _tap(d['coord'], event_id, m['id'], op='phase', action='start')
    _tap(d['coord'], event_id, m['id'], op='point', team='home', kind='raid', points=3)
    live._cache.clear()                                                           # another process's view
    data = anonymous.get(f"/tournament/live/{event_id}/{m['id']}/state").get_json()
    assert data['ok'] and data['state']['home']['total'] == 3 and data['state']['phase'] == 'first_half'
    assert data['state']['recent'][0].startswith('Raid +3')
    page = anonymous.get(f"/tournament/live/{event_id}/{m['id']}").get_data(as_text=True)
    assert 'LIVE' in page and 'data-live-board' in page
    fixtures = anonymous.get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert f"/tournament/live/{event_id}/{m['id']}" in fixtures and 'Watch the score' in fixtures
    assert anonymous.get(f"/tournament/live/{event_id}/nope").status_code == 404
