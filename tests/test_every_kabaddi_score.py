"""
tests/test_every_kabaddi_score.py — UPG-388: every way kabaddi scores has its
own button on the scorer's phone page: a raid +1 to +7 (one per defender
touched), bonus, tackle, super tackle, all out, technical point, out of bounds
and a failed do-or-die raid, in three groups, two buttons a row for each team,
both teams side by side on a 390 px phone.
"""
import re
from urllib.parse import urlparse

from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_live_match import _kabaddi_knockout, _tap
from tests.test_sports_tournament import cup  # noqa: F401
from tests.test_tap_targets import PHONE

EVERY = (['Raid +%d' % n for n in range(1, 8)] + ['Bonus +1', 'Tackle +1', 'Super tackle +2', 'All out +2',
         'Technical point +1', 'Out of bounds +1', 'Do-or-die failed +1'])


def _page(d):
    event_id, ids, m = _kabaddi_knockout(d)
    html = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    return event_id, ids, m, html


def test_every_score_has_its_own_button_for_each_team(cup):  # noqa: F811
    _e, _i, _m, html = _page(cup)
    for side in ('home', 'away'):
        texts = re.findall(rf'<button[^>]*data-team="{side}"[^>]*>([^<]+)</button>', html)
        assert texts == EVERY, (side, texts)
    for title in ('Raid points', 'Tackle points', 'Other points'):
        assert html.count(f'data-button-group="{title}"') == 2
    assert 'title="Out of bounds +1: a player of the other team stepped out"' in html


def test_the_new_scores_count_for_the_right_team_and_player(cup):  # noqa: F811
    d = cup
    event_id, ids, m = _kabaddi_knockout(d)
    side = 'home' if m['home'] == ids['Panthers'] else 'away'
    other = 'away' if side == 'home' else 'home'
    assert d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").status_code == 200   # opens the match
    _tap(d['coord'], event_id, m['id'], op='phase', action='start')
    assert _tap(d['coord'], event_id, m['id'], op='point', team=side, kind='raid', points=7, player='Naveen')[0] == 200
    _tap(d['coord'], event_id, m['id'], op='point', team=side, kind='out_of_bounds')
    status, data = _tap(d['coord'], event_id, m['id'], op='point', team=other, kind='do_or_die')
    assert status == 200
    s = data['state']
    assert (s[side]['total'], s[side]['raid'], s[side]['extra']) == (8, 7, 1)
    assert (s[other]['total'], s[other]['extra'], s[other]['tackle']) == (1, 1, 0)
    assert s['recent'][0].startswith('Do-or-die failed +1')
    assert _tap(d['coord'], event_id, m['id'], op='point', team=side, kind='raid', points=8)[0] == 409   # 7 at most


LAYOUT = """() => {
  const sides = [...document.querySelectorAll('.live-side')].map(s => s.getBoundingClientRect());
  const groups = [...document.querySelectorAll('.live-side .live-group')].map(g =>
      new Set([...g.querySelectorAll('[data-point]')].map(b => Math.round(b.getBoundingClientRect().left))).size);
  const buttons = [...document.querySelectorAll('[data-point]')];
  return {page: document.documentElement.scrollWidth,
          sides: sides.map(r => [Math.round(r.left), Math.round(r.top), Math.round(r.right)]),
          groups: groups,
          short: buttons.filter(b => b.getBoundingClientRect().height < 44).length,
          clipped: buttons.filter(b => b.scrollWidth > b.clientWidth + 1).map(b => b.textContent)};
}"""


def test_on_a_phone_the_teams_sit_side_by_side_with_two_buttons_a_row(cup):  # noqa: F811
    _e, _i, m, html = _page(cup)
    path = urlparse(f'/tournament/x/match/{m["id"]}/score').path
    p, browser = chromium()
    try:
        page = browser.new_context(viewport=PHONE).new_page()

        def handle(route):
            if urlparse(route.request.url).path == path:
                return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        page.wait_for_timeout(300)
        r = page.evaluate(LAYOUT)
    finally:
        browser.close()
        p.stop()
    assert r['page'] <= PHONE['width'], r
    (hl, ht, hr), (al, at, ar) = r['sides']
    assert ht == at and hr <= al and ar <= PHONE['width'], r        # the two teams side by side
    assert r['groups'] == [2] * 6, r                               # each group two buttons a row
    assert r['short'] == 0 and r['clipped'] == [], r               # big enough, no word cut off
