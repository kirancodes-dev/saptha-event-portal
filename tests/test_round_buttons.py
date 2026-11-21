"""
tests/test_round_buttons.py — UPG-368: on a 390 px phone the round floating
buttons (the SPOC console's quick-actions button, back to top, the chat
button) sit above the bottom menu, never on it. Headless Chromium against the
app on a local server.
"""
from tests.test_tap_targets import PHONE, people  # noqa: F401
from tests.test_phone_journey import _login_in_browser, _routes

BOXES = """() => {
  const box = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width && r.height && s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0'
      ? {what: el.id || el.className.toString(), top: r.top, bottom: r.bottom, left: r.left, right: r.right} : null; };
  const nav = document.querySelector('.mobile-nav-bar');
  return {nav: nav && box(nav),
          round: [...document.querySelectorAll('.speed-dial-trigger, #sp-btt, .chat-fab')].map(box).filter(Boolean)};
}"""


def test_the_round_buttons_sit_above_the_bottom_menu(people):  # noqa: F811
    from tests.headless import chromium, live_server
    flask_app, who = people
    problems, seen = [], set()
    p, browser = chromium()
    try:
        with live_server(flask_app) as server:
            for role, path in (('ClubSPOC', '/spoc/dashboard'), ('ClubSPOC', '/spoc/create_event'),
                               ('Student', '/participant/dashboard')):
                ctx = browser.new_context(viewport=PHONE)
                _routes(ctx, server.url)
                page = ctx.new_page()
                _login_in_browser(page, server.url, who[role], role)
                page.goto(server.url + path)
                page.evaluate('window.scrollTo(0, 600)')        # back to top shows once the page is scrolled
                page.wait_for_timeout(500)
                b = page.evaluate(BOXES)
                assert b['nav'], (role, path, 'no bottom menu')
                for r in b['round']:
                    seen.add(r['what'].split()[0])
                    if r['bottom'] > b['nav']['top']:
                        problems.append((path, r['what'], round(r['bottom']), 'menu at', round(b['nav']['top'])))
                ctx.close()
    finally:
        browser.close()
        p.stop()
    assert 'speed-dial-trigger' in seen, seen
    assert not problems, problems
