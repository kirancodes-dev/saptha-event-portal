"""
tests/test_spoc_phone_heading.py — UPG-374: on a 390 px phone the SPOC's
console opens with a heading saying where they are (and Create event) above
the search box; on a computer the overview's own heading is the only one.
Headless Chromium against the app on a local server.
"""
from tests.test_tap_targets import PHONE, people  # noqa: F401
from tests.test_phone_journey import _login_in_browser, _routes

DESKTOP = {'width': 1280, 'height': 800}

LAYOUT = """() => {
  const shown = el => { if (!el) return null; const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width && r.height && s.display !== 'none' && s.visibility !== 'hidden'
      ? {text: el.innerText.trim(), top: r.top, bottom: r.bottom} : null; };
  const headings = [...document.querySelectorAll('main h1, main h2, .container-fluid h1, .container-fluid h2')]
    .map(shown).filter(h => h && h.text).sort((a, b) => a.top - b.top);
  return {headings, search: shown(document.querySelector('#event-search')),
          create: shown(document.querySelector('[data-phone-heading] a[href="/spoc/create_event"]')),
          phoneHead: shown(document.querySelector('[data-phone-heading]'))};
}"""


def test_the_spoc_console_opens_with_a_heading_on_a_phone(people):  # noqa: F811
    from tests.headless import chromium, live_server
    flask_app, who = people
    p, browser = chromium()
    try:
        with live_server(flask_app) as server:
            for size, viewport in (('phone', PHONE), ('desktop', DESKTOP)):
                ctx = browser.new_context(viewport=viewport)
                _routes(ctx, server.url)
                page = ctx.new_page()
                _login_in_browser(page, server.url, who['ClubSPOC'], 'ClubSPOC')
                page.goto(server.url + '/spoc/dashboard')
                page.wait_for_timeout(300)
                b = page.evaluate(LAYOUT)
                assert b['headings'], (size, b)
                first = b['headings'][0]
                assert first['text'].endswith("'s console"), (size, b)
                assert first['top'] < viewport['height'] / 2, (size, b)
                if size == 'phone':
                    assert b['phoneHead'] and b['search'] and first['bottom'] <= b['search']['top'], b
                    assert b['create'], b
                else:
                    assert b['phoneHead'] is None, b           # the overview's heading only
                    assert sum(h['text'].endswith("'s console") for h in b['headings']) == 1, b
                ctx.close()
    finally:
        browser.close()
        p.stop()
