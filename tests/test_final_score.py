"""
tests/test_final_score.py — UPG-463: the scorer couldn't keep up, so the final
score is typed in: the match ends, the winner is set, the boards show it.
"""
import services_live_match as live
from tests.test_kabaddi_premier_league import league  # noqa: F401
from tests.test_lineups_and_players import _match, _raid, _started
from tests.test_sports_tournament import _t, cup  # noqa: F401


def test_the_typed_final_score_ends_the_match_and_every_board_shows_it(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    page = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    assert 'data-final-score' in page and f"/match/{m['id']}/final" in page
    resp = d['coord'].post(f"/tournament/{event_id}/match/{m['id']}/final", data={'home': '31', 'away': '28'},
                           follow_redirects=True)
    assert 'Final score saved: 31–28' in resp.get_data(as_text=True)
    played = next(x for x in _t(d, event_id)['matches'] if x['id'] == m['id'])
    assert (played['status'], played['home_score'], played['away_score'], played['winner']) == \
        ('played', 31, 28, m['home'])
    live._cache.clear()
    body = d['app'].test_client().get(f'/tournament/screen/{event_id}/body').get_data(as_text=True)
    assert 'FULL TIME' in body and 'won by 3 points (31–28)' in body
    st = d['app'].test_client().get(f"/tournament/live/{event_id}/{m['id']}/state").get_json()
    assert st['state']['home']['total'] == 31 and st['state']['away']['total'] == 28
    # Corrected the same way; a wrong number changes nothing
    d['coord'].post(f"/tournament/{event_id}/match/{m['id']}/final", data={'home': '30', 'away': '32'})
    assert next(x for x in _t(d, event_id)['matches'] if x['id'] == m['id'])['winner'] == m['away']
    resp = d['coord'].post(f"/tournament/{event_id}/match/{m['id']}/final", data={'home': 'x', 'away': '1'},
                           follow_redirects=True)
    assert 'points as a number.' in resp.get_data(as_text=True)
    assert d['app'].test_client().post(f"/tournament/{event_id}/match/{m['id']}/final",
                                       data={'home': '1', 'away': '0'}).status_code in (302, 401, 403)
    assert next(x for x in _t(d, event_id)['matches'] if x['id'] == m['id'])['away_score'] == 32
