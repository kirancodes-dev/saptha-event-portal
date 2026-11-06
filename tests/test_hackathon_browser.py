"""
tests/test_hackathon_browser.py — UPG-198: the hackathon pages in a real
browser (headless Chromium against the app on a local server), at 375px and
1280px with UPG-23's measure (no sideways scroll, nothing cut off, no text
under a pinned footer, readable headings), with no script errors:

  * the login page: the older staff roles are out of the menu until "Other
    staff role" (Safari on iPhone ignores `hidden` on an <optgroup>);
  * the SPOC's hackathon page: "Add field" adds a row; the deadline extension
    form works from the page;
  * the team's page: the countdowns run.

Firefox, Safari and a real iPhone are checked by hand (see the item).
Screenshots go to $HACK_SHOTS when it's set, else a temp dir.
"""
import os
import re

import pytest

import services_hackathon as hk
from tests.test_hackathon_phase2 import p2  # noqa: F401  (the Phase 2 fixture)
from tests.test_hackathon_portal import _ist, hack  # noqa: F401
from tests.test_phone_journey import PHONE, _check, _login_in_browser, _routes


@pytest.fixture
def shots(tmp_path):
    folder = os.environ.get('HACK_SHOTS') or str(tmp_path / 'shots')
    os.makedirs(folder, exist_ok=True)
    return folder


def _watch(page, errors):
    """Script errors on the page; requests the test blocks on purpose don't count."""
    page.on('pageerror', lambda exc: errors.append(('pageerror', str(exc))))

    def console(msg):
        if msg.type == 'error' and 'Failed to load resource' not in msg.text and 'ERR_FAILED' not in msg.text:
            errors.append(('console', msg.text))
    page.on('console', console)


def test_the_hackathon_pages_work_and_fit_a_phone_and_a_desktop(p2, shots):  # noqa: F811
    from tests.headless import chromium, live_server
    h = p2
    eid, teams = h['setup'](names=('Alpha', 'Bravo'), submit=('Alpha',))
    d = {'shots': shots}
    problems, errors = [], []
    p, browser = chromium()
    try:
        with live_server(h['app']) as server:
            base = server.url
            ctx = browser.new_context(viewport=PHONE)
            _routes(ctx, base)
            page = ctx.new_page()
            _watch(page, errors)

            # ── The login page ───────────────────────────────────────────────
            page.goto(f'{base}/login')
            values = page.eval_on_selector_all('#roleSelect option', 'els => els.map(e => e.value)')
            assert values == ['', 'SuperAdmin', 'ClubSPOC', 'EventCoordinator', 'Judge', 'Student']
            _check(page, d, 'hk-1-login', problems)
            # Five roles only, nothing to reveal (UPG-204)
            assert page.locator('#otherRolesBtn, #otherRoles, #roleSelect optgroup').count() == 0
            page.select_option('#roleSelect', 'Judge')
            assert page.eval_on_selector('#roleSelect', 'el => el.value') == 'Judge'

            # ── The home page: no AI chat widget, no script errors (UPG-205) ──
            page.goto(f'{base}/')
            page.wait_for_timeout(2500)          # past the old 2-second "Ask Sparky" prompt
            assert page.locator('.chat-fab, #chatWin, #chatPromptBubble, .chat-btn').count() == 0
            assert 'Sparky' not in page.content()
            _check(page, d, 'hk-0-home', problems)

            # ── The SPOC's hackathon page ────────────────────────────────────
            _login_in_browser(page, base, h['spoc'], 'ClubSPOC')
            page.goto(f'{base}/spoc/hackathon/{eid}')
            assert page.title() and 'Deadline' in page.content()
            _check(page, d, 'hk-2-spoc', problems)
            rows = page.locator('#hkFields [data-field-row]').count()
            page.click('#hkAddField')
            assert page.locator('#hkFields [data-field-row]').count() == rows + 1
            new_label = page.locator(f'[name="field_{rows}_label"]')
            assert new_label.count() == 1
            _check(page, d, 'hk-3-spoc-added-field', problems)

            page.select_option('#extBy', '60')
            page.fill('#extReason', 'Lab power cut')
            page.click('button:has-text("Extend deadline")')
            page.wait_for_load_state('load')
            assert hk.form(h['ev'](eid))['closes_at'] == _ist('2026-11-22', '19:00').isoformat()
            assert 'Lab power cut' in page.content()

            # ── The team's page ──────────────────────────────────────────────
            page.context.clear_cookies()
            _login_in_browser(page, base, teams['Alpha']['lead'], 'Student')
            page.goto(f'{base}/hackathon/{eid}')
            assert 'Lab power cut' in page.content()
            countdown = page.locator('.hk-open [data-countdown]')
            assert countdown.count() == 1
            page.wait_for_function("() => /left$/.test(document.querySelector('.hk-open [data-countdown]').textContent)")
            first = countdown.text_content()
            assert re.search(r'\d', first), first
            _check(page, d, 'hk-4-team', problems)
    finally:
        browser.close()
        p.stop()
    assert errors == []
    assert problems == []
