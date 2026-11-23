"""
tests/test_kabaddi_match_day.py — UPG-392 to UPG-395, for the owner's kabaddi
league on match day: the big screen for a monitor (UPG-392), the road to the
final as a map (UPG-393), a match postponed and back on (UPG-394), and every
player's points team by team (UPG-395).
"""
import re
import time
from urllib.parse import urlparse

import services_live_match as live
import services_sports as sports
from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_kabaddi_premier_league import _generate, league  # noqa: F401
from tests.test_live_match import _tap
from tests.test_match_day_scoring import Clock
from tests.test_sports_tournament import _play, _t, cup  # noqa: F401
from tests.test_tap_targets import PHONE


def _squad(d, reg_id, names):
    d['db'].collection('registrations').document(reg_id).update(
        {'lead_name': names[0], 'members': [{'name': n} for n in names]})


def _start(d, event_id, m, taps=()):
    assert d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").status_code == 200
    assert _tap(d['coord'], event_id, m['id'], op='phase', action='start')[0] == 200
    for side, kind, points, player in taps:
        status, _ = _tap(d['coord'], event_id, m['id'], op='point', team=side, kind=kind, points=points, player=player)
        assert status == 200
    live._cache.clear()


def _finish_league(d, event_id):
    """Every league match won by the first-named team, saved straight to the store."""
    t = _t(d, event_id)
    for m in t['matches']:
        t = sports.record_result(t, m['id'], 30, 20)
    d['db'].collection('events').document(event_id).update({'tournament': t})
    return t


def _anon(d):
    return d['app'].test_client()


# ── UPG-393: the road to the final ──────────────────────────────────────────

def test_the_road_to_the_final_before_and_after_the_playoffs(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    b = sports.bracket(t)
    assert b['projected'] and [c['title'] for c in b['columns']] == ['Semi-finals', 'Final']
    sf1, sf2 = b['columns'][0]['slots']
    assert (sf1['home_label'], sf1['away_label'], sf2['home_label'], sf2['away_label']) == \
        ('1st Pool A', '2nd Pool B', '1st Pool B', '2nd Pool A')
    assert sf1['home'] is None                                    # nothing played: no names guessed

    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'data-bracket' in page and 'when every league match is over' in page and 'Road to the final' in page
    assert f'/tournament/screen/{event_id}' in page
    public = _anon(d).get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert 'data-bracket' in public and public.count('pool-row--through') == 4   # the top two of each pool

    _play(d['owner'], event_id, t['matches'][0], 30, 22)          # Garuda Sena beat Vajra
    sf1 = sports.bracket(_t(d, event_id))['columns'][0]['slots'][0]
    # UPG-467 (the owner, 23 Nov 2026): no team named until every league match is over
    assert sf1['projected'] and sf1['home'] is None and sf1['away'] is None
    assert sf1['home_label'] == '1st Pool A'
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    board = re.search(r'data-bracket.*?data-bracket-champion', page, re.S).group(0)
    assert 'Garuda Sena' not in board

    _finish_league(d, event_id)
    b = sports.bracket(_t(d, event_id))
    assert b['settled'] and b['columns'][0]['slots'][0]['home']   # now the semi-finals are named
    d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '4'})
    t = _t(d, event_id)
    b = sports.bracket(t)
    assert not b['projected']
    (sf1, sf2), (final,) = b['columns'][0]['slots'], b['columns'][1]['slots'][:1]
    assert sf1['no'] == 'M-29' and sf1['home'] and sf1['home_label'] == '1st Pool A'
    assert final['home'] is None and final['home_label'] == 'Winner SF1'
    _play(d['owner'], event_id, next(m for m in t['matches'] if m['id'] == sf1['id']), 40, 30)
    _play(d['owner'], event_id, next(m for m in t['matches'] if m['id'] == sf2['id']), 25, 35)
    t = _t(d, event_id)
    final = sports.bracket(t)['columns'][1]['slots'][0]
    assert final['home'] == sf1['home'] and final['away'] == sf2['away']
    _play(d['owner'], event_id, next(m for m in t['matches'] if m['id'] == final['id']), 33, 31)
    b = sports.bracket(_t(d, event_id))
    assert b['champion'] == sf1['home']
    page = _anon(d).get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert 'data-bracket-champion' in page and sports.names(t)[sf1['home']] in page


# ── UPG-394: postponed, and back on ─────────────────────────────────────────

def test_a_match_is_postponed_and_comes_back(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    m1, m2, m3 = t['matches'][:3]
    _play(d['coord'], event_id, m1, 30, 22)
    assert sports.up_next(_t(d, event_id))['id'] == m2['id']

    d['coord'].post(f"/tournament/{event_id}/match/{m2['id']}/postpone")   # a coordinator can
    t = _t(d, event_id)
    assert t['matches'][1]['postponed'] is True and sports.up_next(t)['id'] == m3['id']
    assert 'data-postponed' in _anon(d).get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'Back on: play it now' in page and 'data-postpone-form' in page
    screen = _anon(d).get(f'/tournament/screen/{event_id}').get_data(as_text=True)
    assert 'data-screen-next' in screen and 'M-03' in screen

    d['owner'].post(f"/tournament/{event_id}/match/{m2['id']}/postpone", data={'action': 'resume'})
    assert 'postponed' not in _t(d, event_id)['matches'][1]

    page = d['owner'].post(f"/tournament/{event_id}/match/{m1['id']}/postpone", follow_redirects=True)
    assert "has a result, so it can" in page.get_data(as_text=True)               # a played match can't be
    assert 'postponed' not in _t(d, event_id)['matches'][0]

    d['owner'].post(f"/tournament/{event_id}/match/{m2['id']}/postpone")
    _play(d['owner'], event_id, m2, 28, 28)                                        # played after all
    assert 'postponed' not in _t(d, event_id)['matches'][1]
    d['owner'].post(f"/tournament/{event_id}/match/{m3['id']}/postpone")
    assert d['coord'].get(f"/tournament/{event_id}/match/{m3['id']}/score").status_code == 200
    assert 'postponed' not in _t(d, event_id)['matches'][2]                       # opened for live scoring

    assert _anon(d).post(f"/tournament/{event_id}/match/{m3['id']}/postpone").status_code in (302, 401, 403)


# ── UPG-392: the big screen ─────────────────────────────────────────────────

def test_the_big_screen_follows_the_live_match_with_tables_and_leaders(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    m1 = t['matches'][0]
    names = sports.names(t)
    _squad(d, m1['home'], [f"{names[m1['home']]} Raider", f"{names[m1['home']]} Corner"])

    resp = _anon(d).get(f'/tournament/screen/{event_id}')                       # no login
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200 and '/static/js/tournament_screen.js' in html and 'data-fullscreen' in html
    assert 'data-screen-pool="A"' in html and 'data-screen-pool="B"' in html and 'data-bracket' in html
    assert 'data-screen-next' in html and 'M-01' in html and 'data-screen-board' not in html

    raider = f"{names[m1['home']]} Raider"
    _start(d, event_id, m1, [('home', 'raid', 3, raider), ('home', 'bonus', None, raider)])
    html = _anon(d).get(f'/tournament/screen/{event_id}/body').get_data(as_text=True)
    assert f'data-screen-board="{m1["id"]}"' in html and 'LIVE' in html and 'data-screen-clock' in html
    assert 'data-screen-score="home">4<' in html and 'Raid 4' in html   # a bonus is a raid point
    assert 'data-screen-leaders="raid"' in html and raider in html

    clock = Clock(monkeypatch, start=time.time())
    assert _tap(d['coord'], event_id, m1['id'], op='phase', action='half_time')[0] == 200
    _tap(d['coord'], event_id, m1['id'], op='phase', action='second_half')
    _tap(d['coord'], event_id, m1['id'], op='phase', action='full_time')
    live._cache.clear()
    html = _anon(d).get(f'/tournament/screen/{event_id}/body').get_data(as_text=True)
    assert f'data-screen-board="{m1["id"]}"' in html and 'data-screen-ft>FULL TIME<' in html   # stays with who won (UPG-456)
    clock.wait(live.RESULT_SHOW_SECONDS + 1)
    live._cache.clear()
    html = _anon(d).get(f'/tournament/screen/{event_id}/body').get_data(as_text=True)
    assert 'data-screen-board' not in html and 'data-screen-last' in html and 'data-screen-next' in html

    assert 'data-screen-link' in _anon(d).get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert 'data-screen-link' in d['coord'].get(f"/tournament/{event_id}/match/{t['matches'][1]['id']}/score").get_data(as_text=True)


SCREEN = """() => {
  const clock = document.querySelector('[data-screen-clock]');
  return {page: document.documentElement.scrollWidth, width: window.innerWidth,
          clock: clock ? clock.textContent : null,
          score: (document.querySelector('[data-screen-score="home"]') || {}).textContent,
          scoreSize: parseFloat(getComputedStyle(document.querySelector('[data-screen-score="home"]')).fontSize)};
}"""


def test_the_big_screen_fits_a_tv_and_a_phone_ticks_the_clock_and_refreshes(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    m1 = t['matches'][0]
    _start(d, event_id, m1, [('home', 'raid', 2, '')])
    first = _anon(d).get(f'/tournament/screen/{event_id}').get_data(as_text=True)
    _tap(d['coord'], event_id, m1['id'], op='point', team='home', kind='raid', points=5)
    live._cache.clear()
    later = _anon(d).get(f'/tournament/screen/{event_id}/body').get_data(as_text=True)
    path, body_path = f'/tournament/screen/{event_id}', f'/tournament/screen/{event_id}/body'
    results = {}
    p, browser = chromium()
    try:
        for name, viewport in (('tv', {'width': 1920, 'height': 1080}), ('phone', PHONE)):
            page = browser.new_context(viewport=viewport).new_page()

            def handle(route):
                url = urlparse(route.request.url).path
                if url == path:
                    return route.fulfill(status=200, body=first, headers={'Content-Type': 'text/html; charset=utf-8'})
                if url == body_path:
                    return route.fulfill(status=200, body=later, headers={'Content-Type': 'text/html; charset=utf-8'})
                return _serve_static(route)
            page.route('**/*', handle)
            page.goto(ORIGIN + path, wait_until='load')
            page.wait_for_timeout(200)
            before = page.evaluate(SCREEN)
            page.wait_for_timeout(1300)                       # the clock ticks between refreshes
            ticked = page.evaluate(SCREEN)
            page.wait_for_timeout(1500)                       # a refresh (every 2 s, UPG-403) has come in
            results[name] = (before, ticked, page.evaluate(SCREEN))
    finally:
        browser.close()
        p.stop()
    (tv0, tv1, tv2), (ph0, _ph1, ph2) = results['tv'], results['phone']
    assert tv0['page'] <= 1920 and ph0['page'] <= PHONE['width'] and ph2['page'] <= PHONE['width'], results
    assert tv0['score'] == '2' and tv2['score'] == '7' and ph2['score'] == '7', results   # the new score came in
    assert tv0['clock'] == '00:00' and tv1['clock'] in ('00:01', '00:02'), results       # the clock runs
    assert tv0['scoreSize'] >= 120, results                                    # readable across a hall


# ── UPG-395: every player's points ──────────────────────────────────────────

def test_every_players_points_team_by_team(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    m1 = t['matches'][0]
    names = sports.names(t)
    home, away = names[m1['home']], names[m1['away']]
    _squad(d, m1['home'], [f'{home} Raider', f'{home} Corner'])
    _squad(d, m1['away'], [f'{away} Raider', f'{away} Corner'])
    _start(d, event_id, m1, [('home', 'raid', 3, f'{home} Raider'), ('home', 'tackle', None, f'{home} Corner'),
                             ('away', 'raid', 2, f'{away} Raider'), ('away', 'super_tackle', None, f'{away} Corner')])
    live._cache.clear()
    page = _anon(d).get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert 'data-team-players' in page and "Every player&#39;s points" in page or "Every player's points" in page
    assert f'data-team-player-list="{m1["home"]}"' in page and f'data-team-player-list="{m1["away"]}"' in page
    for player in (f'{home} Raider', f'{home} Corner', f'{away} Raider', f'{away} Corner'):
        assert player in page
    groups = live.by_team(live.event_stats(d['db'], event_id, names), t)
    assert [g[0] for g in groups] == [x['name'] for x in t['teams'] if x['id'] in (m1['home'], m1['away'])]
    rows = {r['player']: r for g in groups for r in g[2]}
    assert (rows[f'{away} Corner']['tackle'], rows[f'{home} Raider']['raid']) == (2, 3)
