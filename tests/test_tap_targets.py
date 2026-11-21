"""
tests/test_tap_targets.py — UPG-364: on a 390 px phone every header button,
every bottom-menu button, the sign-in page's controls and the home page's
category chips are at least 44 px to tap, their words at least 12 px, and no
page scrolls sideways. Headless Chromium against the app on a local server.
"""
import pytest

from tests.test_integration_flow import _unique, _user
from tests.test_phone_journey import _login_in_browser, _routes

PHONE = {'width': 390, 'height': 844}

# Each control the test is about: [what, width, height, font size]
MEASURE = """(groups) => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const out = [];
  for (const [group, selector] of Object.entries(groups)) {
    for (const el of document.querySelectorAll(selector)) {
      if (!vis(el)) continue;
      let r = el.getBoundingClientRect();
      if (el.type === 'checkbox' && el.labels && el.labels[0]) {      // the box and its label are one target
        const l = el.labels[0].getBoundingClientRect();
        r = {left: Math.min(r.left, l.left), right: Math.max(r.right, l.right), top: Math.min(r.top, l.top), bottom: Math.max(r.bottom, l.bottom)};
      }
      out.push({group, what: (el.innerText || el.getAttribute('aria-label') || el.name || el.id || '').trim().slice(0, 30),
                w: Math.round(r.right - r.left), h: Math.round(r.bottom - r.top),
                font: parseFloat(getComputedStyle(el).fontSize)});
    }
  }
  return {controls: out, width: document.documentElement.scrollWidth};
}"""

HEADER = {'header': '.app-bar a, .app-bar button'}
BOTTOM = {'bottom menu': '.mobile-nav-item'}
LOGIN = {'sign-in': '.pw-toggle, #rememberMe, .login-card form a:not(.btn)'}
CHIPS = {'category chips': '.hsc-cat'}


@pytest.fixture
def people(real_app):
    flask_app, db = real_app
    who = {'Student': f"{_unique('tstudent')}@test.edu", 'ClubSPOC': f"{_unique('tspoc')}@test.edu"}
    for role, email in who.items():
        _user(db, email, role, name='Asha Rao')
    return flask_app, who


def _measure(page, groups, problems, where):
    got = page.evaluate(MEASURE, groups)
    if got['width'] > PHONE['width']:
        problems.append((where, 'scrolls sideways', got['width']))
    for c in got['controls']:
        if c['h'] < 44 or c['w'] < 44:
            problems.append((where, c['group'], c['what'], f"{c['w']}x{c['h']}"))
        if c['what'] and c['font'] < 12:
            problems.append((where, c['group'], c['what'], f"{c['font']}px text"))
    return {c['group'] for c in got['controls']}


def test_every_control_is_big_enough_to_tap_on_a_phone(people):
    from tests.headless import chromium, live_server
    flask_app, who = people
    problems = []
    p, browser = chromium()
    try:
        with live_server(flask_app) as server:
            ctx = browser.new_context(viewport=PHONE)
            _routes(ctx, server.url)
            page = ctx.new_page()
            page.goto(f'{server.url}/login')
            page.wait_for_load_state('load')
            page.select_option('#roleSelect', 'Student')      # the form shows once a role is picked
            seen = _measure(page, LOGIN, problems, '/login')
            assert seen == {'sign-in'}, seen
            page.goto(f'{server.url}/')
            page.wait_for_load_state('load')
            assert _measure(page, CHIPS, problems, '/') == {'category chips'}
            ctx.close()

            for role, email in who.items():
                ctx = browser.new_context(viewport=PHONE)
                _routes(ctx, server.url)
                page = ctx.new_page()
                _login_in_browser(page, server.url, email, role)
                assert _measure(page, {**HEADER, **BOTTOM}, problems, page.url) == {'header', 'bottom menu'}, role
                ctx.close()
    finally:
        browser.close()
        p.stop()
    assert not problems, problems
