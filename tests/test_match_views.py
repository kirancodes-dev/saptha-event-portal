"""
tests/test_match_views.py — UPG-433: how many have watched a match. Every
opening of the public match page adds a view; a browser opening it for the
first time adds a device; nothing is ever taken off. Link previews and
crawlers aren't counted. The scorer sees the counts without adding to them.
"""
import re

import services_live_match as live
from tests.test_kabaddi_premier_league import league  # noqa: F401
from tests.test_sports_tournament import cup  # noqa: F401
from tests.test_lineups_and_players import _match

PHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'


def _counts(page: str):
    line = re.search(r'data-views>(.*?)</p>', page, re.S).group(1)
    nums = [int(n.replace(',', '')) for n in re.findall(r'<strong>([\d,]+)</strong>', line)]
    return tuple(nums)


def test_every_visit_adds_a_view_and_each_browser_one_device(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    url = f"/tournament/live/{event_id}/{m['id']}"
    phone, laptop = d['app'].test_client(), d['app'].test_client()

    # 1. The first visit: 1 view, 1 device
    assert _counts(phone.get(url, headers={'User-Agent': PHONE_UA}).get_data(as_text=True)) == (1, 1)
    # 2. The same phone again, twice: views go up, the device isn't counted again
    phone.get(url, headers={'User-Agent': PHONE_UA})
    assert _counts(phone.get(url, headers={'User-Agent': PHONE_UA}).get_data(as_text=True)) == (3, 1)
    # 3. Another browser: a second device
    page = laptop.get(url, headers={'User-Agent': PHONE_UA}).get_data(as_text=True)
    assert _counts(page) == (4, 2)
    assert '4</strong> views' in page and '2</strong> devices' in page

    # 4. Link previews and crawlers aren't counted, but see the numbers
    for ua in ('WhatsApp/2.23.20.0', 'facebookexternalhit/1.1', 'Googlebot/2.1', ''):
        d['app'].test_client().get(url, headers={'User-Agent': ua})
    assert live.views(d['db'], event_id, m['id']) == {'views': 4, 'devices': 2}

    # 5. The scorer's page shows the counts and doesn't add to them
    scorer = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score",
                            headers={'User-Agent': PHONE_UA}).get_data(as_text=True)
    assert _counts(scorer) == (4, 2) and 'Public page:' in scorer
    assert live.views(d['db'], event_id, m['id']) == {'views': 4, 'devices': 2}

    # 6. Another match counts on its own; the phone is a new device there
    other = next(x for x in d['db'].collection('events').document(event_id).get().to_dict()['tournament']['matches']
                 if x['id'] != m['id'])
    assert _counts(phone.get(f"/tournament/live/{event_id}/{other['id']}",
                             headers={'User-Agent': PHONE_UA}).get_data(as_text=True)) == (1, 1)
    assert live.views(d['db'], event_id, m['id']) == {'views': 4, 'devices': 2}


def test_the_count_only_goes_up_and_the_cookie_stays_small():
    class Snap:
        def __init__(self, data):
            self.exists, self._d = data is not None, data

        def to_dict(self):
            return dict(self._d or {})

    class Doc:
        store = {}

        def __init__(self, key):
            self.key = key

        def get(self):
            return Snap(self.store.get(self.key))

        def set(self, change, merge=False):
            cur = dict(self.store.get(self.key) or {})
            for k, v in change.items():
                cur[k] = cur.get(k, 0) + v.value if type(v).__name__ == 'Increment' else v
            self.store[self.key] = cur

    class Db:
        def collection(self, name):
            return self

        def document(self, key):
            return Doc(key)

    db = Db()
    seen = ''
    for n in range(1, 4):                           # one browser, three visits
        counts, seen = live.count_view(db, 'e1', 'm1', seen)
        assert counts == {'views': n, 'devices': 1}
    counts, _ = live.count_view(db, 'e1', 'm1', '')  # a cleared cookie is a new device: still only adds
    assert counts == {'views': 4, 'devices': 2}
    for i in range(live.SEEN_MAX + 20):                # many matches: the cookie keeps the last SEEN_MAX
        _, seen = live.count_view(db, 'e1', f'x{i}', seen)
    assert len(seen.split('.')) == live.SEEN_MAX and len(seen) < 1000
    assert live.count_view(db, 'e1', 'm1', 'bad"value;')[0]['devices'] == 3   # a tampered cookie: counted, no harm
    assert live.is_person(PHONE_UA) and not live.is_person('WhatsApp/2.23') and not live.is_person('')


# ── UPG-435: the count on the big screen, in the QR code's place ─────────────

def test_the_big_screen_shows_how_many_watch_the_live_match_instead_of_the_qr(league):  # noqa: F811
    from tests.test_lineups_and_players import _started
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    screen = f'/tournament/screen/{event_id}'

    # 1. Nothing live: the QR code, no count
    page = d['app'].test_client().get(screen, headers={'User-Agent': PHONE_UA}).get_data(as_text=True)
    assert 'data-screen-watch-slot hidden' in page and re.search(r'data-screen-qr>', page)
    assert 'data-screen-watch>' not in page

    # 2. Live, watched by two phones three times: the count at the top right, the QR hidden
    _started(d, event_id, m)
    phone, other = d['app'].test_client(), d['app'].test_client()
    for c in (phone, phone, other):
        c.get(f"/tournament/live/{event_id}/{m['id']}", headers={'User-Agent': PHONE_UA})
    live._cache.clear()
    page = d['app'].test_client().get(screen, headers={'User-Agent': PHONE_UA}).get_data(as_text=True)
    assert 'data-screen-watch-slot>' in page and 'data-screen-qr hidden' in page
    head = page[page.index('data-screen-watch-slot'):page.index('data-screen-qr')]
    assert 'watching' in head and _counts_in(head) == 3 and '>3</strong>' in head
    assert 'device' not in head                                    # one number, as a streaming app shows it
    # the refreshed body carries the count too, for the script to move up
    body = d['app'].test_client().get(f'{screen}/body').get_data(as_text=True)
    assert '<template data-screen-watch>' in body and _counts_in(body.split('<template data-screen-watch>')[1]) == 3
    # the big screen itself isn't a viewer
    assert live.views(d['db'], event_id, m['id']) == {'views': 3, 'devices': 2}


def _counts_in(html):
    return int(re.search(r'data-watch-views="(\d+)"', html).group(1))


def test_the_big_screen_count_goes_up_by_itself(league):  # noqa: F811
    from urllib.parse import urlparse
    from tests.headless import ORIGIN, _serve_static, chromium
    from tests.test_lineups_and_players import _started
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    path = f'/tournament/screen/{event_id}'
    match_page = f"/tournament/live/{event_id}/{m['id']}"
    d['app'].test_client().get(match_page, headers={'User-Agent': PHONE_UA})
    p, browser = chromium()
    try:
        page = browser.new_context(viewport={'width': 1366, 'height': 768}).new_page()

        def handle(route):
            req_path = urlparse(route.request.url).path
            if req_path in (path, f'{path}/body'):
                live._cache.clear()
                resp = d['app'].test_client().get(req_path)
                return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                     headers={'Content-Type': resp.content_type})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        assert page.text_content('[data-watch-views]') == '1' and not page.is_visible('[data-screen-qr]')
        assert 'watching' in page.text_content('[data-screen-watch-slot]')
        for _ in range(4):                                       # four more phones open the match
            d['app'].test_client().get(match_page, headers={'User-Agent': PHONE_UA})
        page.wait_for_function("document.querySelector('[data-watch-views]').textContent === '5'", timeout=8000)
        box = page.locator('[data-screen-watch-slot]').bounding_box()
        assert box['x'] + box['width'] <= 1366 and box['y'] < 140                 # at the top right, on the screen
    finally:
        browser.close()
        p.stop()


def test_the_count_is_short_like_a_streaming_app():
    cases = {0: '0', 7: '7', 999: '999', 1000: '1K', 1234: '1.2K', 1299: '1.2K', 12_345: '12.3K', 99_999: '99.9K',
             100_000: '1L', 345_678: '3.4L', 9_999_999: '99.9L', 10_000_000: '1Cr', 23_456_789: '2.3Cr',
             1_234_567_890: '123Cr'}
    for n, text in cases.items():
        assert live.short_count(n) == text, n                       # rounded down: never more than there were
    assert live.short_count(None) == '0' and live.short_count(-5) == '0'
