"""
tests/test_scorer_full_screen.py — UPG-470, the owner, 23 Nov 2026: "the
details to display for my reference … pause and resume the time and half
time … score need to display … above me … only in that full screen option …
so I can focus on one full screen". The score, the clock and the match's
buttons sit together at the top; Full screen scoring keeps them there while
the raids are tapped below and hides the rest of the site. UPG-471: in full
screen that bar is small, and each team's time-outs sit beside its name.
Made-up names.
"""
import re
from urllib.parse import urlparse

from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_kabaddi_premier_league import league  # noqa: F401
from tests.test_lineups_and_players import _match, _started
from tests.test_sports_tournament import cup  # noqa: F401
from tests.test_tap_targets import PHONE


def test_the_score_clock_and_match_buttons_are_one_block_at_the_top(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    html = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    top = re.search(r'<div class="live-top" data-live-top>(.*?)<div data-panel>', html, re.S).group(1)
    for needle in ('data-focus-toggle', 'data-score="home"', 'data-score="away"', 'data-clock-text',
                   'data-message', 'data-phase-action="pause"', 'data-phase-action="resume"',
                   'data-phase-action="half_time"', 'data-phase-action="full_time"', 'data-undo'):
        assert needle in top, needle
    assert html.index('data-live-top') < html.index('data-howto') < html.index('data-panel')
    # UPG-471: each team's time-outs sit in its header, beside the name
    for side in ('home', 'away'):
        assert re.search(r'<div class="pkl-col__head">\s*<div class="pkl-col__name">.*?data-timeouts="' + side + '"',
                         html, re.S), side


def _open(d, event_id, m, viewport):
    path = f"/tournament/{event_id}/match/{m['id']}/score"
    html = d['coord'].get(path).get_data(as_text=True)
    p, browser = chromium()
    page = browser.new_context(viewport=viewport).new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))

    def handle(route):
        req = route.request
        if urlparse(req.url).path == path:
            if req.method == 'POST':
                resp = d['coord'].post(path, data=req.post_data, content_type='application/json')
                return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                     headers={'Content-Type': 'application/json'})
            return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
        return _serve_static(route)
    page.route('**/*', handle)
    page.goto(ORIGIN + path, wait_until='load')
    return p, browser, page, errors


def test_full_screen_scoring_keeps_the_score_and_buttons_in_sight(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    for viewport in ({'width': 1280, 'height': 800}, PHONE):
        p, browser, page, errors = _open(d, event_id, m, viewport)
        try:
            assert not page.is_visible('.live-scorer.is-focus')
            page.click('[data-focus-toggle]')
            page.wait_for_selector('.live-scorer.is-focus')
            assert page.inner_text('[data-focus-label]') == 'Exit full screen'
            assert page.is_visible('[data-live-top] [data-undo]')
            assert not page.is_visible('[data-howto]') and not page.is_visible('[data-final-score]')
            # UPG-471: the score and clock bar is small, so the teams have the room
            top = page.locator('[data-live-top]').bounding_box()
            assert top['height'] < (260 if viewport is PHONE else 160), (viewport, top)
            head = page.locator('[data-col="home"] .pkl-col__head').bounding_box()
            assert head['height'] < (120 if viewport is PHONE else 60), (viewport, head)
            # The scorer scrolls down to the players: the score and Pause clock are still at the top
            page.evaluate("document.querySelector('.live-scorer').scrollTop = 100000")
            page.wait_for_timeout(200)
            for sel in ('[data-score="home"]', '[data-clock-text]', '[data-phase-action="pause"]'):
                box = page.locator(sel).bounding_box()
                assert box and 0 <= box['y'] < viewport['height'] / 2, (viewport, sel, box)
            # Nothing of the site's page shows over it
            top = page.evaluate("document.elementFromPoint(20, 20).closest('.live-scorer') !== null")
            assert top, viewport
            # Kept on reload, until turned off
            page.reload(wait_until='load')
            assert page.is_visible('.live-scorer.is-focus')
            page.click('[data-focus-toggle]')
            assert not page.locator('.live-scorer.is-focus').count()
            assert page.inner_text('[data-focus-label]') == 'Full screen scoring'
            assert not errors, errors
        finally:
            browser.close()
            p.stop()
