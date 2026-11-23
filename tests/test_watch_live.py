"""
tests/test_watch_live.py — UPG-457: the home page's Watch live box (a Men /
Women pick, at the top, a phone included) leads to the tournament's big
screen, which fits a phone. All names here are made up.
"""
import re
from urllib.parse import urlparse

import services_live_match as live
from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_kabaddi_premier_league import POOL_A, POOL_B, _generate, league  # noqa: F401
from tests.test_lineups_and_players import _match, _started
from tests.test_pkl_mode import _ok
from tests.test_sports_tournament import cup  # noqa: F401

PHONE = {'width': 390, 'height': 844}


def _home(d):
    live._cache.clear()
    return d['app'].test_client().get('/').get_data(as_text=True)


def _box(html):
    found = re.search(r'<form class="watch-live".*?</form>', html, re.S)
    return found.group(0) if found else ''


def test_the_home_page_offers_men_and_women_to_watch_and_leads_to_the_big_screen(league):  # noqa: F811
    d, men, ids = league
    _generate(d, men, ids)
    women, wids = d['event'](POOL_A + POOL_B)
    d['db'].collection('events').document(women).update(
        {'details': {'sport': 'Kabaddi', 'format': 'League then knockout', 'gender': 'Women'}})
    _generate(d, women, wids)
    box = _box(_home(d))
    assert 'action="/tournament/watch"' in box and 'data-watch-pick' in box and 'Watch live scoring' in box
    assert f'<option value="{men}"' in box and f'<option value="{women}"' in box
    # Named by the gender category when that tells them apart, else by the title
    evs = [dict(d['db'].collection('events').document(e).get().to_dict(), id=e) for e in (men, women)]
    assert [(w['id'], w['label']) for w in live.watchable(d['db'], evs)] == [(men, 'Men'), (women, 'Women')]
    evs[1]['details'] = {'gender': 'Men'}
    assert {w['label'] for w in live.watchable(d['db'], evs)} == {evs[0]['title'], evs[1]['title']}
    # The pick goes to that tournament's big screen; nothing else gets through
    anon = d['app'].test_client()
    resp = anon.get(f'/tournament/watch?event={women}')
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/tournament/screen/{women}')
    assert anon.get('/tournament/watch?event=../admin').headers['Location'].endswith('/')
    assert anon.get('/tournament/watch').headers['Location'].endswith('/')


def test_a_live_match_comes_first_and_says_live(league):  # noqa: F811
    d, men, ids = league
    m = _match(d, men, ids)
    women, wids = d['event'](POOL_A + POOL_B)
    d['db'].collection('events').document(women).update({'details': {'sport': 'Kabaddi', 'gender': 'Women'}})
    _generate(d, women, wids)
    _started(d, men, m)
    box = _box(_home(d))
    assert 'Live now' in box and 'watch-live__dot' in box
    options = re.findall(r'<option value="([^"]+)"[^>]*>([^<]*)</option>', box)
    ours = [o for o in options if o[0] in (men, women)]
    assert ours[0][0] == men and ours[0][1].endswith(' · live') and not ours[1][1].endswith(' · live')
    assert options[0][1].endswith(' · live')               # live ones first


def test_one_tournament_is_a_single_button_and_none_or_a_finished_season_shows_no_box(league):  # noqa: F811
    d, men, ids = league
    assert men not in _box(_home(d))                       # no fixtures yet
    t = _generate(d, men, ids)
    box = _box(_home(d))
    if 'data-watch-pick' not in box:                      # the only tournament on the site
        assert f'name="event" value="{men}"' in box
    # Every match played: the season is over and it leaves the box
    for m in t['matches']:
        m['status'] = 'played'
    d['db'].collection('events').document(men).update({'tournament': t})
    assert men not in _box(_home(d))


def test_the_box_is_at_the_top_of_a_phone_and_the_big_screen_fits_a_phone(league):  # noqa: F811
    d, men, ids = league
    m = _match(d, men, ids)
    _started(d, men, m)
    _ok(d['coord'], men, m, op='raid', team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    home = _home(d)
    live._cache.clear()
    anon = d['app'].test_client()
    screen = anon.get(f'/tournament/screen/{men}').get_data(as_text=True)
    p, browser = chromium()
    try:
        page = browser.new_context(viewport=PHONE, is_mobile=True, has_touch=True).new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def handle(route):
            path = urlparse(route.request.url).path
            if path == '/':
                return route.fulfill(status=200, body=home, headers={'Content-Type': 'text/html; charset=utf-8'})
            if path == f'/tournament/screen/{men}':
                return route.fulfill(status=200, body=screen, headers={'Content-Type': 'text/html; charset=utf-8'})
            if path.startswith(f'/tournament/screen/{men}/'):
                live._cache.clear()
                resp = anon.get(path)
                return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                     headers={'Content-Type': resp.headers.get('Content-Type', 'text/html')})
            return _serve_static(route)
        page.route('**/*', handle)

        page.goto(ORIGIN + '/', wait_until='load')
        box = page.locator('[data-watch-live]').bounding_box()
        assert box and box['y'] + box['height'] <= PHONE['height'] and box['x'] >= 0 and box['x'] + box['width'] <= PHONE['width']
        go = page.locator('.watch-live__go').bounding_box()
        assert go['height'] >= 44 and go['x'] + go['width'] <= PHONE['width']

        page.goto(ORIGIN + f'/tournament/screen/{men}', wait_until='load')
        page.wait_for_selector('[data-screen-board]')
        fits = page.evaluate("""() => {
          const out = [...document.querySelectorAll('.tv-head *, .tv-board, .tv-card')]
            .filter(e => e.offsetParent !== null)
            .filter(e => e.getBoundingClientRect().right > window.innerWidth + 1).map(e => e.className);
          return {page: document.documentElement.scrollWidth, width: window.innerWidth, out,
                  qr: getComputedStyle(document.querySelector('[data-screen-qr]')).display,
                  score: document.querySelector('[data-screen-score="home"]').textContent};
        }""")
        assert fits['page'] <= fits['width'] and fits['out'] == [], fits
        assert fits['qr'] == 'none' and fits['score'] == '1'
        assert not errors, errors
    finally:
        browser.close()
        p.stop()
