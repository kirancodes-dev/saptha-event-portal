"""
tests/test_screen_layout.py — UPG-434: on the big screen a live match takes the
whole width; the points tables and the top players go under it, side by side.
With no match live the screen keeps its two columns.
"""
from urllib.parse import urlparse

from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_kabaddi_premier_league import league  # noqa: F401
from tests.test_lineups_and_players import _match, _raid, _started
from tests.test_sports_tournament import cup  # noqa: F401

TV = {'width': 1920, 'height': 1080}


LAPTOP = {'width': 1366, 'height': 768}

# Each team cell on one line; no panel over another; none past the screen's edge
LAYOUT = '''() => {
  const lines = [...document.querySelectorAll('.tv-right .tv-table__team')].map(el => {
    const size = parseFloat(getComputedStyle(el).fontSize);
    return {name: el.textContent.trim(), lines: el.getBoundingClientRect().height / size,
            cut: el.scrollWidth > el.clientWidth + 1};
  });
  const panels = [...document.querySelectorAll('.tv-right > .tv-panel')].map(el => el.getBoundingClientRect());
  const overlap = panels.some((a, i) => panels.some((b, j) => i < j && a.left < b.right - 1 && b.left < a.right - 1
                                                     && a.top < b.bottom - 1 && b.top < a.bottom - 1));
  const tooWide = panels.some(r => r.right > document.documentElement.clientWidth + 1)
                  || [...document.querySelectorAll('.tv-right > .tv-panel')].some(el => el.scrollWidth > el.clientWidth + 1);
  return {lines, overlap, tooWide, rightmost: Math.max(...panels.map(r => r.right)),
          main: document.querySelector('.tv-grid').getBoundingClientRect().right};
}'''


def _boxes(d, event_id, viewport=TV) -> dict:
    """The big screen in a browser: where the score, the tables and the leaders sit."""
    path = f'/tournament/screen/{event_id}'
    p, browser = chromium()
    try:
        page = browser.new_context(viewport=viewport).new_page()

        def handle(route):
            req_path = urlparse(route.request.url).path
            if req_path in (path, f'{path}/body'):
                resp = d['app'].test_client().get(req_path)
                return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                     headers={'Content-Type': resp.content_type})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        box = {}
        for name, sel in (('main', '.tv-grid'), ('board', '[data-screen-board]'), ('next', '[data-screen-next]'),
                          ('pool_a', '[data-screen-pool="A"]'), ('pool_b', '[data-screen-pool="B"]'),
                          ('raiders', '[data-screen-leaders="raid"]'), ('bracket', '.tv-bracket')):
            loc = page.locator(sel)
            box[name] = loc.first.bounding_box() if loc.count() else None
        box['layout'] = page.evaluate(LAYOUT)
        return box
    finally:
        browser.close()
        p.stop()


def test_a_live_match_fills_the_screen_and_the_tables_go_under_it(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    b = _boxes(d, event_id)
    assert b['board']['width'] >= b['main']['width'] - 2                     # the whole width
    board_bottom = b['board']['y'] + b['board']['height']
    for name in ('pool_a', 'pool_b', 'raiders'):                              # all under the score
        assert b[name]['y'] >= board_bottom, name
    assert abs(b['pool_a']['y'] - b['pool_b']['y']) < 2                       # side by side
    assert b['pool_b']['x'] > b['pool_a']['x'] + b['pool_a']['width'] - 2
    assert b['bracket']['y'] >= b['pool_a']['y'] + b['pool_a']['height']      # the bracket after the tables


def test_with_no_match_live_the_screen_keeps_two_columns(league):  # noqa: F811
    d, event_id, ids = league
    _match(d, event_id, ids)                                                   # fixtures made, none started
    b = _boxes(d, event_id)
    assert b['board'] is None and b['next']
    assert b['pool_a']['x'] > b['next']['x'] + b['next']['width']             # the tables on the right
    assert b['pool_a']['y'] < b['next']['y'] + b['next']['height']


def test_on_the_screen_each_name_shows_whole_and_nothing_overlaps(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    for viewport in (TV, LAPTOP):
        lay = _boxes(d, event_id, viewport)['layout']
        names = [x['name'] for x in lay['lines']]
        assert 'Gandaberunda Warriors' in names and 'Malnad Fighters' in names
        for x in lay['lines']:
            assert x['lines'] < 2 and not x['cut'], (viewport, x)            # "Fighter s" was 3 lines
        assert not lay['overlap'] and not lay['tooWide'], viewport
        assert lay['rightmost'] >= lay['main'] - 2, viewport                 # the panels fill the width
