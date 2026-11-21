"""
tests/test_welcome_toast.py — UPG-363: the "Welcome back" message after
signing in never covers the page's heading. On a phone it sits at the bottom,
above the bottom menu, and goes by itself; on a computer it stays top right,
clear of the title. Headless Chromium against the app on a local server.
"""
import pytest

from tests.test_integration_flow import _unique, _user
from tests.test_phone_journey import _login_in_browser, _routes

PHONE = {'width': 390, 'height': 844}
DESKTOP = {'width': 1280, 'height': 800}

# The toast, the first visible heading, and the bottom menu, as boxes
BOXES = """() => {
  const box = el => { if (!el) return null; const r = el.getBoundingClientRect();
    return r.width && r.height ? {top: r.top, bottom: r.bottom, left: r.left, right: r.right, text: el.innerText.trim()} : null; };
  const heading = [...document.querySelectorAll('h1, h2')].find(h => box(h) && h.innerText.trim());
  const nav = document.querySelector('.mobile-nav-bar');
  return {toast: box(document.querySelector('.se-toast.is-shown')), heading: box(heading),
          nav: nav && getComputedStyle(nav).display !== 'none' ? box(nav) : null,
          height: window.innerHeight};
}"""


def _overlap(a, b):
    return not (a['bottom'] <= b['top'] or b['bottom'] <= a['top'] or a['right'] <= b['left'] or b['right'] <= a['left'])


@pytest.fixture
def people(real_app):
    flask_app, db = real_app
    who = {'Student': f"{_unique('wstudent')}@test.edu", 'ClubSPOC': f"{_unique('wspoc')}@test.edu"}
    for role, email in who.items():
        _user(db, email, role, name='Asha Rao')
    return flask_app, who


@pytest.mark.parametrize('size', ['phone', 'desktop'])
def test_the_welcome_message_never_covers_the_heading(people, size):
    from tests.headless import chromium, live_server
    flask_app, who = people
    viewport = PHONE if size == 'phone' else DESKTOP
    p, browser = chromium()
    try:
        with live_server(flask_app) as server:
            for role, email in who.items():
                ctx = browser.new_context(viewport=viewport)
                _routes(ctx, server.url)
                page = ctx.new_page()
                _login_in_browser(page, server.url, email, role)
                page.wait_for_selector('.se-toast.is-shown', timeout=5000)
                page.wait_for_timeout(300)                      # the slide-in has finished
                b = page.evaluate(BOXES)
                assert 'Welcome back' in b['toast']['text'], (role, b)
                # The SPOC's console opens on its event list on a phone, with no heading on screen;
                # there the toast must still be in the bottom half, clear of the top of the page
                assert b['heading'] or size == 'phone', (role, size, 'no heading')
                if b['heading']:
                    assert not _overlap(b['toast'], b['heading']), (role, size, b)
                if size == 'phone':
                    assert b['toast']['top'] > b['height'] / 2, (role, b)   # at the bottom
                    if b['nav']:
                        assert b['toast']['bottom'] <= b['nav']['top'], (role, b)
                    # and it goes by itself
                    page.wait_for_selector('.se-toast', state='detached', timeout=8000)
                ctx.close()
    finally:
        browser.close()
        p.stop()
