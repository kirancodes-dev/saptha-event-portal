"""
tests/test_pkl_mode_unplayed_match.py — UPG-478, the owner, 24 Nov 2026: on the
live site M-02 showed the "Raid +1 … Raid +7" buttons and a "Who scored" list
while the other matches showed the players to tap; "I need same in localhost
like that in the deployed also". M-02's scoring page was opened while PKL mode
was off, and a match kept the way it was first opened. Now a match that hasn't
started and has nothing recorded follows PKL mode when it is opened again; a
match with points kept stays as it is. Made-up names.
"""
import services_live_match as live
from tests.test_kabaddi_premier_league import _generate, league  # noqa: F401
from tests.test_live_match import _tap
from tests.test_sports_tournament import _t, cup  # noqa: F401


def _score_page(d, event_id, m):
    live._cache.clear()
    resp = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _public_mode(d, event_id, m):
    live._cache.clear()
    data = d['app'].test_client().get(f"/tournament/live/{event_id}/{m['id']}/state").get_json()
    return data['state']['mode']


def test_an_unplayed_match_opened_before_pkl_mode_is_scored_raid_by_raid(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids, rules='pkl12')                      # PKL mode off
    m = t['matches'][0]
    page = _score_page(d, event_id, m)                                  # opened: point by point
    assert 'data-pkl-panel' not in page and 'Raid +7' in page
    assert live.get(d['db'], event_id, m['id']).get('mode', '') == ''
    d['owner'].post(f'/tournament/{event_id}/scoring', data={'scoring': 'pkl'})
    assert _t(d, event_id)['scoring'] == 'pkl'

    page = _score_page(d, event_id, m)                                  # opened again
    assert 'data-pkl-panel' in page and 'Raid +7' not in page and 'Who scored (optional)' not in page
    doc = live.get(d['db'], event_id, m['id'])
    assert doc['mode'] == 'pkl' and doc['phase'] == 'not_started' and doc['events'] == [] and doc.get('mat')
    assert _public_mode(d, event_id, m) == 'pkl'                        # the public page and big screen too
    # It is scored like any PKL match: the toss, then the 1st half
    status, data = _tap(d['coord'], event_id, m['id'], op='phase', action='start', first='away')
    assert status == 200 and data['state']['phase'] == 'first_half', data


def test_a_match_with_points_keeps_its_way(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids, rules='pkl12')                      # PKL mode off
    m1, m2 = t['matches'][:2]
    _score_page(d, event_id, m1)
    assert _tap(d['coord'], event_id, m1['id'], op='phase', action='start')[0] == 200
    assert _tap(d['coord'], event_id, m1['id'], op='point', team='home', kind='raid', points=2)[0] == 200
    _score_page(d, event_id, m2)
    assert _tap(d['coord'], event_id, m2['id'], op='phase', action='start')[0] == 200   # started, nothing scored
    d['owner'].post(f'/tournament/{event_id}/scoring', data={'scoring': 'pkl'})

    for m in (m1, m2):
        page = _score_page(d, event_id, m)
        assert 'data-pkl-panel' not in page and 'Raid +7' in page, m['id']
        assert live.get(d['db'], event_id, m['id']).get('mode', '') == ''
    assert live.get(d['db'], event_id, m1['id'])['log'][0]['points'] == 2   # the point is still there
