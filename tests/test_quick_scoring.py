"""
tests/test_quick_scoring.py — the owner, 23 Nov 2026: "I am unable to score
fast". UPG-464: the 30-second raid clock can be turned off and on. UPG-465:
the bonus is a button, not a tick box, and stays chosen while the panel
redraws. UPG-466: the most-used scores sit under each team's players. All
names here are made up.
"""
import re
from urllib.parse import urlparse

import services_live_match as live
from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_kabaddi_premier_league import league  # noqa: F401
from tests.test_lineups_and_players import _match, _started
from tests.test_pkl_mode import _ok, _refused
from tests.test_sports_tournament import cup  # noqa: F401


def _path(event_id, m):
    return f"/tournament/{event_id}/match/{m['id']}/score"


def test_the_raid_clock_turns_off_and_on(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    html = d['coord'].get(_path(event_id, m)).get_data(as_text=True)
    assert 'data-raid-clock-box' in html and 'data-raid-clock-switch="off"' in html

    data = _ok(d['coord'], event_id, m, op='raid_clock', action='off')
    assert data['state']['raid_clock_on'] is False and data['state']['raid_clock'] is None
    assert 'data-raid-clock-off' in data['panel'] and 'data-raid-clock-btn' not in data['panel']
    assert 'data-raid-clock-switch="on"' in data['panel']
    # Off: tapping the raider starts nothing, Space's start is refused, the boards show no clock
    data = _ok(d['coord'], event_id, m, op='raider', name='Arjun')
    assert data['state']['raid_clock'] is None
    assert 'raid_clock' not in live.get(d['db'], event_id, m['id'])
    _refused(d['coord'], event_id, m, 'raid clock is off', op='raid_clock', action='start')

    # On again: it works as before
    data = _ok(d['coord'], event_id, m, op='raid_clock', action='on')
    assert data['state']['raid_clock_on'] is True and 'data-raid-clock-btn' in data['panel']
    data = _ok(d['coord'], event_id, m, op='raid_clock', action='start')
    assert data['state']['raid_clock']['running']


def test_bonus_buttons_and_the_quick_row_beside_each_team(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    html = d['coord'].get(_path(event_id, m)).get_data(as_text=True)
    assert not re.search(r'type="checkbox"[^>]*data-pkl-bonus', html)          # no tick boxes
    assert 'data-bonus-toggle="given"' in html and 'data-bonus-toggle="missed"' in html
    home = re.search(r'data-quick="home">(.*?)</div>', html, re.S).group(1)     # home raids first
    away = re.search(r'data-quick="away">(.*?)</div>', html, re.S).group(1)
    for needle in ('data-touch-button', 'data-bonus-toggle="given"', 'data-bonus-toggle="missed"',
                   'data-outcome="empty"', 'data-kind="technical" data-team="home"'):
        assert needle in home, needle
    for needle in ('data-outcome="tackled"', 'data-outcome="line_out"', 'data-outcome="time_over"',
                   'data-kind="technical" data-team="away"'):
        assert needle in away, needle
    assert 'data-outcome="tackled"' not in home and 'data-touch-button' not in away
    # UPG-468: the Step 3 list below the teams is gone; each button is once, in its team's row
    assert 'pkl-guide__step--end' not in html
    for needle in ('data-outcome="time_over"', 'data-touch-button', 'data-outcome="tackled"',
                   'data-bonus-toggle="given"', 'data-bonus-toggle="missed"'):
        assert html.count(needle) == 1, needle


def _boxes(html, side):
    return re.search(rf'data-timeouts="{side}">(.*?)</div>', html, re.S).group(1)


def test_time_outs_as_boxes_beside_each_team(league):  # noqa: F811
    """UPG-469 (the owner): two time-outs a half for each team, as boxes to tap; how many are left."""
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    html = d['coord'].get(_path(event_id, m)).get_data(as_text=True)
    home = _boxes(html, 'home')
    assert home.count('data-kind="timeout" data-team="home"') == 2 and '4 left' in home
    assert home.count('is-later') == 2                                     # the 2nd half's, not yet
    data = _ok(d['coord'], event_id, m, op='call', kind='timeout', team='home')
    assert data['state']['mat']['timeouts_used']['home'] == [1, 0]
    _ok(d['coord'], event_id, m, op='phase', action='resume')
    home = _boxes(data['panel'], 'home')
    assert home.count('is-used') == 1 and home.count('data-kind="timeout"') == 1 and '3 left' in home
    away = _boxes(data['panel'], 'away')
    assert away.count('data-kind="timeout" data-team="away"') == 2 and '4 left' in away


def test_fast_scoring_in_the_browser(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    path = _path(event_id, m)
    html = d['coord'].get(path).get_data(as_text=True)
    sent = []
    p, browser = chromium()
    try:
        page = browser.new_context(viewport={'width': 1280, 'height': 900}).new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('dialog', lambda dlg: dlg.accept())

        def handle(route):
            req = route.request
            if urlparse(req.url).path == path:
                if req.method == 'POST':
                    sent.append(req.post_data_json)
                    resp = d['coord'].post(path, data=req.post_data, content_type='application/json')
                    return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                         headers={'Content-Type': 'application/json'})
                return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')

        def wait_for(op, n):
            for _ in range(50):
                if len([b for b in sent if b.get('op') == op]) >= n:
                    break
                page.wait_for_timeout(100)
            page.wait_for_timeout(400)

        # The bonus first, then the raider (the panel redraws): the bonus stays chosen
        page.click('[data-quick="home"] [data-bonus-toggle="given"]')
        page.click('[data-mat-player][data-role="raider"][data-name="Arjun"]')
        wait_for('raider', 1)
        assert page.get_attribute('[data-quick="home"] [data-bonus-toggle="given"]', 'aria-pressed') == 'true'
        page.click('[data-mat-player][data-role="defender"][data-name="Harish"]')
        page.click('[data-quick="home"] [data-touch-button]')
        wait_for('raid', 1)
        raid = [b for b in sent if b.get('op') == 'raid'][0]
        assert raid['outcome'] == 'touch' and raid['bonus'] is True and raid['touched'] == ['Harish']
        assert raid['bonus_missed'] is False
        st = live.state(live.get(d['db'], event_id, m['id']), {})
        assert st['home']['total'] == 2                                          # touch +1, bonus +1
        # The bonus is cleared for the next raid; away raids, home tackles from its own row
        assert page.get_attribute('[data-quick="away"] [data-bonus-toggle="given"]', 'aria-pressed') == 'false'
        page.click('[data-mat-player][data-role="raider"][data-name="Deepak"]')
        wait_for('raider', 2)
        page.click('[data-mat-player][data-role="defender"][data-name="Bharat"]')
        page.click('[data-quick="home"] [data-outcome="tackled"]')
        wait_for('raid', 2)
        raid = [b for b in sent if b.get('op') == 'raid'][1]
        assert raid['outcome'] == 'tackled' and raid['tackler'] == 'Bharat' and raid['bonus'] is False
        # The raid clock off: its box goes, Space does nothing
        page.click('[data-raid-clock-switch="off"]')
        wait_for('raid_clock', 1)
        page.wait_for_selector('[data-raid-clock-off]')
        page.keyboard.press('Space')
        page.wait_for_timeout(400)
        assert [b['action'] for b in sent if b.get('op') == 'raid_clock'] == ['off']
        assert not errors, errors
    finally:
        browser.close()
        p.stop()
    st = live.state(live.get(d['db'], event_id, m['id']), {})
    assert st['home']['total'] == 3 and st['raid_clock_on'] is False
