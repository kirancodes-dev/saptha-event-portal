"""
tests/test_match_result.py — UPG-456: once the 2nd half is over, who won is
said in words wherever the match shows: the public match page, the scorer's
page, the big screen (the finished match's board stays up for a few minutes,
then the Last result card), and the fixtures page. All names here are made up.
"""
import re
from urllib.parse import urlparse

import services_live_match as live
import services_sports
from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_kabaddi_premier_league import league  # noqa: F401
from tests.test_lineups_and_players import _match, _public, _raid, _started
from tests.test_match_day_scoring import Clock
from tests.test_pkl_mode import _ok
from tests.test_sports_tournament import cup  # noqa: F401


def _to_full_time(d, event_id, m):
    for action in ('half_time', 'second_half', 'full_time'):
        data = _ok(d['coord'], event_id, m, op='phase', action=action)
    return data


def _names(d, event_id):
    return services_sports.names(d['db'].collection('events').document(event_id).get().to_dict()['tournament'])


def test_the_words_for_each_kind_of_result():
    names = {'a': 'Garuda Sena', 'b': 'Vajra'}
    played = {'status': 'played', 'home': 'a', 'away': 'b'}
    assert services_sports.result_text(dict(played, home_score=24, away_score=20, winner='a'), names) == \
        'Garuda Sena won by 4 points (24–20)'
    assert services_sports.result_text(dict(played, home_score=20, away_score=21, winner='b'), names) == \
        'Vajra won by 1 point (21–20)'
    assert services_sports.result_text(dict(played, home_score=2, away_score=0, winner='a'), names, kabaddi=False) == \
        'Garuda Sena won by 2 goals (2–0)'
    assert services_sports.result_text(dict(played, home_score=18, away_score=18, winner=None), names) == 'Match tied 18–18'
    assert services_sports.result_text(dict(played, home_score=1, away_score=1, winner=None), names, kabaddi=False) == \
        'Match drawn 1–1'
    assert services_sports.result_text(dict(played, home_score=None, away_score=None, winner='b', walkover=True), names) == \
        'Vajra won by walkover'
    assert services_sports.result_text(dict(played, home_score=20, away_score=20, winner='b',
                                            tiebreak={'decided': 'golden'}), names) == \
        'Vajra won the golden raid (20–20 at full time)'
    assert services_sports.result_text({'status': 'scheduled', 'home': 'a', 'away': 'b'}, names) == ''


def test_at_full_time_the_public_page_and_the_scorer_say_who_won(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh', 'Ishaan'])
    path = f"/tournament/live/{event_id}/{m['id']}"
    assert re.search(r'data-result-line\s*hidden', _public(d, path))           # not before full time
    data = _to_full_time(d, event_id, m)
    names = _names(d, event_id)
    said = f"{names[m['home']]} won by 2 points (2–0)"
    assert data['state']['result_text'] == said
    line = re.search(r'<p class="live-result" data-result-line\s*>(.*?)</p>', _public(d, path), re.S)
    assert line and said in line.group(1)
    scorer = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    assert re.search(rf'data-result-line\s*><i[^>]*></i> <span data-result-text>{re.escape(said)}</span>', scorer)
    # The fixtures page's card says it too
    fixtures = _public(d, f'/tournament/fixtures/{event_id}')
    card = re.search(rf'data-match-card="{m["id"]}">.*?data-match-result>(.*?)</div>', fixtures, re.S)
    assert card and said in card.group(1)


def test_the_big_screen_keeps_the_finished_match_up_with_who_won_then_the_last_result(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    clock = Clock(monkeypatch)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    _to_full_time(d, event_id, m)
    said = f"{_names(d, event_id)[m['home']]} won by 1 point (1–0)"
    screen = f'/tournament/screen/{event_id}/body'
    live._cache.clear()
    body = d['app'].test_client().get(screen).get_data(as_text=True)
    assert f'data-screen-board="{m["id"]}"' in body and 'data-screen-ft>FULL TIME<' in body
    assert re.search(rf'data-screen-result><span aria-hidden="true">🏆</span> {re.escape(said)}<', body)
    # Ten minutes on, the board goes; the Last result card says who won
    clock.wait(live.RESULT_SHOW_SECONDS + 1)
    live._cache.clear()
    body = d['app'].test_client().get(screen).get_data(as_text=True)
    assert 'data-screen-board=' not in body
    assert re.search(rf'data-screen-last-result>🏆 {re.escape(said)}<', body)


def test_a_live_match_takes_the_screen_from_one_just_finished(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])   # 0–0 would go to a tie-breaker
    _to_full_time(d, event_id, m)
    t = d['db'].collection('events').document(event_id).get().to_dict()['tournament']
    other = t['matches'][1]
    d['coord'].get(f"/tournament/{event_id}/match/{other['id']}/score")
    _ok(d['coord'], event_id, other, op='phase', action='start')
    live._cache.clear()
    body = d['app'].test_client().get(f'/tournament/screen/{event_id}/body').get_data(as_text=True)
    assert f'data-screen-board="{other["id"]}"' in body and f'data-screen-board="{m["id"]}"' not in body


def test_the_open_public_page_shows_who_won_when_full_time_is_tapped(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    for action in ('half_time', 'second_half'):
        _ok(d['coord'], event_id, m, op='phase', action=action)
    path = f"/tournament/live/{event_id}/{m['id']}"
    html = _public(d, path)
    anon = d['app'].test_client()
    p, browser = chromium()
    try:
        page = browser.new_context(viewport={'width': 1280, 'height': 900}).new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def handle(route):
            url = urlparse(route.request.url)
            if url.path == path:
                return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
            if url.path == f'{path}/state':
                live._cache.clear()
                resp = anon.get(url.path)
                return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                     headers={'Content-Type': 'application/json'})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        assert page.locator('[data-result-line]').is_hidden()
        _ok(d['coord'], event_id, m, op='phase', action='full_time')
        page.wait_for_selector('[data-result-line]:not([hidden])', timeout=15000)
        assert 'won by 1 point (1–0)' in page.inner_text('[data-result-line]')
        assert not errors, errors
    finally:
        browser.close()
        p.stop()
