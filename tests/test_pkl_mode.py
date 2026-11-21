"""
tests/test_pkl_mode.py — the owner's kabaddi league played by the PKL's rules:
Season 12 points and the tie-breaker (UPG-396), PKL mode scored raid by raid
(UPG-397), the college logo, a QR code and link previews on the public pages
(UPG-402), and a big screen and scoreboard that keep up (UPG-403).
"""
import json
from urllib.parse import urlparse

import routes_sports
import services_live_match as live
import services_sports as sports
from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_kabaddi_premier_league import _generate, league  # noqa: F401
from tests.test_live_match import _tap
from tests.test_sports_tournament import _play, _t, cup  # noqa: F401
from tests.test_tap_targets import PHONE


def _pkl(d, event_id, ids, **extra):
    return _generate(d, event_id, ids, rules='pkl12', **extra)


def _ok(client, event_id, m, **body):
    status, data = _tap(client, event_id, m['id'], **body)
    assert status == 200, data
    return data


def _refused(client, event_id, m, needle, **body):
    status, data = _tap(client, event_id, m['id'], **body)
    assert status == 409 and needle in data['error'], data
    return data


def _anon(d):
    return d['app'].test_client()


# ── UPG-396: PKL Season 12 points, and no ties ──────────────────────────────

def test_season_12_points_and_a_tie_settled_on_the_tournament_page(league):  # noqa: F811
    d, event_id, ids = league
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'name="rules"' in page and sports.RULES['pkl12'] in page and 'name="scoring"' in page
    t = _pkl(d, event_id, ids)
    assert t['points'] == sports.PKL12_POINTS and t['tiebreak'] is True
    m1, m2 = t['matches'][:2]

    # A level score needs the tie-breaker's winner
    page = d['owner'].post(f"/tournament/{event_id}/match/{m1['id']}/result",
                           data={'home_score': '30', 'away_score': '30'}, follow_redirects=True)
    assert "choose who won the tie-breaker" in page.get_data(as_text=True)
    assert _t(d, event_id)['matches'][0]['status'] != 'played'
    d['owner'].post(f"/tournament/{event_id}/match/{m1['id']}/result",
                    data={'home_score': '30', 'away_score': '30', 'winner': m1['away'],
                          'tb_way': 'shootout', 'tb_home': '3', 'tb_away': '4'})
    _play(d['owner'], event_id, m2, 28, 20)
    t = _t(d, event_id)
    played = t['matches'][0]
    assert played['winner'] == m1['away'] and played['tiebreak'] == {'decided': 'shootout', 'home': 3, 'away': 4}
    names = sports.names(t)
    assert sports.tiebreak_text(played, names) == f"{names[m1['away']]} won the shootout 3–4"

    rows = {r['id']: r for _pool, table in sports.pool_tables(t) for r in table}
    assert rows[m1['away']]['won'] == 1 and rows[m1['away']]['points'] == 2       # a win is 2
    assert rows[m1['home']]['lost'] == 1 and rows[m1['home']]['points'] == 0      # a loss is 0, even 30-30
    assert rows[m2['home']]['points'] == 2 and rows[m2['away']]['points'] == 0
    assert not any(r['drawn'] for r in rows.values())

    for page in (_anon(d).get(f'/tournament/fixtures/{event_id}'), d['owner'].get(f'/tournament/{event_id}')):
        text = page.get_data(as_text=True)
        assert 'data-tiebreak' in text and 'won the shootout 3–4' in text
    assert 'name="tb_way"' in d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)


def test_the_older_rule_switches_to_season_12_without_new_fixtures(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids, rules='classic')
    assert t['points'] == sports.KABADDI_POINTS and not t.get('tiebreak')
    _play(d['owner'], event_id, t['matches'][0], 30, 30)                 # the older rule allows a tie
    assert _t(d, event_id)['matches'][0]['winner'] is None
    d['owner'].post(f'/tournament/{event_id}/points', data={'rules': 'pkl12'})
    t = _t(d, event_id)
    assert t['points'] == sports.PKL12_POINTS and t['tiebreak'] is True
    d['owner'].post(f'/tournament/{event_id}/points', data={**{f'points_{k}': str(v) for k, v in sports.KABADDI_POINTS.items()},
                                                            'tiebreak_field': '1'})
    assert not _t(d, event_id).get('tiebreak')


# ── UPG-397: the PKL rules, played out from the raids ───────────────────────

def _doc(events, first='home', phase='first_half'):
    doc = live._new('e', 'm', {'home': 'H', 'away': 'A'}, 20, 'pkl')
    doc.update(first_raid=first, phase=phase,
               events=[dict(e, id=f'e{i}', half=e.get('half', 1)) for i, e in enumerate(events)])
    live._replay_into(doc)
    return doc


def _points(doc):
    s = live.score(doc)
    return s['home']['total'], s['away']['total']


def _raid(team, outcome, touches=None, bonus=False, half=1):
    return {'type': 'raid', 'team': team, 'outcome': outcome, 'touches': touches, 'bonus': bonus, 'half': half}


def test_do_or_die_raids_the_mat_and_revivals():
    doc = _doc([_raid('home', 'empty'), _raid('away', 'empty'), _raid('home', 'empty'), _raid('away', 'touch', 1)])
    mat = doc['mat']
    assert mat['raider'] == 'home' and mat['do_or_die'] and mat['empty']['home'] == 2      # the third raid
    assert mat['on'] == {'home': 6, 'away': 7} and _points(doc) == (0, 1)
    doc = _doc([_raid('home', 'empty'), _raid('away', 'empty'), _raid('home', 'empty'), _raid('away', 'touch', 1),
                _raid('home', 'empty')])
    assert _points(doc) == (0, 2)                         # an empty do-or-die raid: the raider out, +1 to the defence
    assert doc['mat']['on'] == {'home': 5, 'away': 7} and not doc['mat']['do_or_die']
    assert any(e['label'] == 'Do-or-die raid failed' for e in doc['log'])


def test_all_outs_super_tackles_and_the_bonus_line():
    doc = _doc([_raid('home', 'touch', 3),               # home +3; away down to 4
                _raid('away', 'tackled'),                # home +1 (7 defenders: a plain tackle); away down to 3
                _raid('home', 'tackled')])               # away has 3 defenders: a super tackle, +2
    assert _points(doc) == (4, 2) and doc['mat']['on'] == {'home': 6, 'away': 4}
    assert [e['label'] for e in doc['log']][-1] == 'Super tackle'
    assert doc['mat']['raider'] == 'away' and doc['mat']['bonus_live']   # home defends with 6: the bonus line counts
    doc = _doc([_raid('home', 'touch', 3), _raid('away', 'tackled'), _raid('home', 'tackled'),
                _raid('away', 'touch', 2),               # away +2; home down to 4, away revives 2 → 6
                _raid('home', 'touch', 6, bonus=True)])  # every defender out: +6, +1 bonus, +2 all out
    assert _points(doc) == (13, 4)
    assert doc['mat']['on'] == {'home': 7, 'away': 7} and doc['mat']['all_outs']['home'] == 1
    assert 'All out' in [e['label'] for e in doc['log']]


def test_the_second_half_starts_with_the_other_team_and_fresh_counts():
    doc = _doc([_raid('home', 'empty'), {'type': 'timeout', 'team': 'home'}], phase='second_half')
    mat = doc['mat']
    assert mat['raider'] == 'away' and mat['empty'] == {'home': 0, 'away': 0} and mat['half'] == 2
    assert mat['timeouts_left'] == {'home': 2, 'away': 2}
    doc = _doc([_raid('away', 'empty', half=1), _raid('home', 'touch', 1, half=2)], first='away', phase='second_half')
    assert doc['mat']['raider'] == 'away' and _points(doc) == (1, 0)


def test_pkl_mode_scored_raid_by_raid_on_the_scorers_phone(league):  # noqa: F811
    d, event_id, ids = league
    t = _pkl(d, event_id, ids, scoring='pkl')
    assert t['scoring'] == 'pkl'
    m = t['matches'][0]
    page = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    assert 'data-pkl-panel' in page and 'data-point ' not in page and 'Who raids first' in page
    assert live.get(d['db'], event_id, m['id'])['mode'] == 'pkl'

    _ok(d['coord'], event_id, m, op='phase', action='start', first='away')
    _refused(d['coord'], event_id, m, "other team's raid", op='raid', team='home', outcome='empty')
    r = _ok(d['coord'], event_id, m, op='raid', team='away', outcome='touch', touches=2)
    assert r['state']['away']['total'] == 2 and r['state']['mat']['on'] == {'home': 5, 'away': 7}
    assert 'Raid 2' in r['panel'] and 'data-raider="home"' in r['panel'] and len(r['entries']) == 1
    status, data = _tap(d['coord'], event_id, m['id'], op='point', team='away', kind='raid', points=1)
    assert status == 409 and 'raid by raid' in data['error']

    r = _ok(d['coord'], event_id, m, op='raid', team='home', outcome='bonus')            # away has 7 defenders
    assert r['state']['home']['total'] == 1
    _refused(d['coord'], event_id, m, 'bonus line counts only', op='raid', team='away', outcome='touch',
             touches=1, bonus=True)                                                      # home has 5
    _refused(d['coord'], event_id, m, 'touch 1 to 5', op='raid', team='away', outcome='touch', touches=6)
    r = _ok(d['coord'], event_id, m, op='raid', team='away', outcome='touch', touches=1)
    assert r['state']['away']['total'] == 3

    for _ in range(2):
        r = _ok(d['coord'], event_id, m, op='call', kind='timeout', team='home')
    assert r['state']['running'] is False and r['state']['mat']['timeouts_left']['home'] == 0
    _refused(d['coord'], event_id, m, 'both time-outs', op='call', kind='timeout', team='home')
    _ok(d['coord'], event_id, m, op='phase', action='resume')

    r = _ok(d['coord'], event_id, m, op='undo')                         # the last call: a time-out
    assert r['state']['mat']['timeouts_left']['home'] == 1
    bonus = next(e for e in r['entries'] if 'bonus' in e['text'])
    r = _ok(d['coord'], event_id, m, op='remove', entry=bonus['id'])    # a wrong call, anywhere in the log
    assert (r['state']['home']['total'], r['state']['away']['total']) == (0, 3)
    r = _ok(d['coord'], event_id, m, op='call', kind='mat', team='home', change=-1)
    assert r['state']['mat']['on']['home'] == 3

    live._cache.clear()
    board = _anon(d).get(f"/tournament/live/{event_id}/{m['id']}/state").get_json()['state']
    assert 'to raid' in board['mat_text'] and board['recent'][0].startswith('Mat corrected')
    page = _anon(d).get(f"/tournament/live/{event_id}/{m['id']}").get_data(as_text=True)
    assert 'data-mat-line' in page and 'to raid' in page

    _ok(d['coord'], event_id, m, op='phase', action='half_time')
    r = _ok(d['coord'], event_id, m, op='phase', action='second_half')
    assert r['state']['mat']['raider'] == 'home'                        # the other team raids first
    r = _ok(d['coord'], event_id, m, op='phase', action='full_time')
    assert r['state']['result']['winner'] == m['away']
    assert _t(d, event_id)['matches'][0]['away_score'] == 3


# ── UPG-396: the tie-breaker on the scorer's phone ──────────────────────────

def test_a_level_match_goes_to_the_shootout_and_the_golden_raid(league):  # noqa: F811
    d, event_id, ids = league
    t = _pkl(d, event_id, ids)                       # Season 12, scored point by point
    m = t['matches'][0]
    d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score")
    _ok(d['coord'], event_id, m, op='phase', action='start')
    for side in ('home', 'away'):
        _ok(d['coord'], event_id, m, op='point', team=side, kind='raid', points=3)
    _ok(d['coord'], event_id, m, op='phase', action='half_time')
    _ok(d['coord'], event_id, m, op='phase', action='second_half')
    r = _ok(d['coord'], event_id, m, op='phase', action='full_time')
    assert r['state']['phase'] == 'tiebreak' and 'data-shootout-panel' in r['panel']
    assert _t(d, event_id)['matches'][0]['status'] != 'played'
    _refused(d['coord'], event_id, m, '5 raids from each team', op='phase', action='full_time')
    r = _ok(d['coord'], event_id, m, op='phase', action='back')         # pressed by mistake
    assert r['state']['phase'] == 'second_half'
    _ok(d['coord'], event_id, m, op='phase', action='full_time')

    _ok(d['coord'], event_id, m, op='shootout', team='home', outcome='touch', touches=1)
    _refused(d['coord'], event_id, m, 'in turn', op='shootout', team='home', outcome='empty')
    _refused(d['coord'], event_id, m, 'Undo the tie-breaker', op='phase', action='back')
    for i in range(9):
        _ok(d['coord'], event_id, m, op='shootout', team='away' if i % 2 == 0 else 'home', outcome='touch', touches=1)
    _refused(d['coord'], event_id, m, 'had its 5 raids', op='shootout', team='home', outcome='empty')
    r = _ok(d['coord'], event_id, m, op='undo')
    assert r['state']['shootout']['raids'] == {'home': 5, 'away': 4}
    r = _ok(d['coord'], event_id, m, op='shootout', team='away', outcome='touch', touches=1)
    sh = r['state']['shootout']
    assert (sh['home'], sh['away'], sh['level']) == (5, 5, True) and 'Golden raid won by' in r['panel']
    _refused(d['coord'], event_id, m, 'golden raid', op='phase', action='full_time')

    _ok(d['coord'], event_id, m, op='decide', way='toss', winner='home')
    _ok(d['coord'], event_id, m, op='undo')                             # the wrong button
    _ok(d['coord'], event_id, m, op='decide', way='golden', winner='away')
    live._cache.clear()
    board = _anon(d).get(f"/tournament/live/{event_id}/{m['id']}/state").get_json()['state']
    assert 'Tie-breaker' in board['shootout_text'] and 'won the golden raid' in board['shootout_text']
    r = _ok(d['coord'], event_id, m, op='phase', action='full_time')
    assert r['state']['phase'] == 'full_time' and r['state']['result']['tiebreak']['decided'] == 'golden'
    played = _t(d, event_id)['matches'][0]
    assert (played['home_score'], played['away_score'], played['winner']) == (3, 3, m['away'])
    assert 'won the golden raid' in _anon(d).get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)


def test_the_shootout_is_won_on_points():
    doc = {'home': 'H', 'away': 'A', 'shootout': {'raids': [], 'decided': None}}
    for i in range(10):
        team = 'home' if i % 2 == 0 else 'away'
        r = {'team': team, 'outcome': 'empty'}
        if i == 0:
            r = {'team': 'home', 'outcome': 'touch', 'touches': 2, 'bonus': True}     # +3
        if i == 3:
            r = {'team': 'away', 'outcome': 'tackled'}                                # home +1
        doc['shootout']['raids'].append(r)
    sh = live.shootout_state(doc, {'H': 'Vajra', 'A': 'Code Blue'})
    assert (sh['home'], sh['away'], sh['winner'], sh['decided']) == (4, 0, 'home', 'shootout')
    assert sh['lines'][-1].startswith('Vajra raid 1: 2 touches + bonus (+3')


# ── UPG-397: the switch ─────────────────────────────────────────────────────

def test_pkl_mode_is_turned_on_and_off_for_matches_opened_after(league):  # noqa: F811
    d, event_id, ids = league
    t = _pkl(d, event_id, ids)
    m1, m2 = t['matches'][:2]
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'data-scoring-mode' in page and 'Turn on PKL mode' in page
    assert d['coord'].post(f'/tournament/{event_id}/scoring', data={'scoring': 'pkl'}).status_code == 403
    d['owner'].post(f'/tournament/{event_id}/scoring', data={'scoring': 'pkl'})
    assert _t(d, event_id)['scoring'] == 'pkl'
    assert 'data-pkl-panel' in d['coord'].get(f"/tournament/{event_id}/match/{m1['id']}/score").get_data(as_text=True)
    d['owner'].post(f'/tournament/{event_id}/scoring', data={'scoring': ''})
    assert 'scoring' not in _t(d, event_id)
    again = d['coord'].get(f"/tournament/{event_id}/match/{m1['id']}/score").get_data(as_text=True)
    assert 'data-pkl-panel' in again                                    # opened in PKL mode: stays so
    other = d['coord'].get(f"/tournament/{event_id}/match/{m2['id']}/score").get_data(as_text=True)
    assert 'data-pkl-panel' not in other and 'data-point ' in other


# ── UPG-402: the college logo, the QR code, link previews ───────────────────

def test_the_big_screen_shows_the_college_logo_and_a_qr_code_for_phones(league):  # noqa: F811
    d, event_id, ids = league
    t = _pkl(d, event_id, ids)
    screen = _anon(d).get(f'/tournament/screen/{event_id}').get_data(as_text=True)
    assert 'data-college-logo' in screen and '/static/img/snpsu-logo-reversed.png' in screen
    assert 'data-screen-qr' in screen and f'/tournament/screen/{event_id}/qr.svg' in screen
    assert f'/tournament/fixtures/{event_id}' in screen
    qr = _anon(d).get(f'/tournament/screen/{event_id}/qr.svg')
    assert qr.status_code == 200 and qr.mimetype == 'image/svg+xml' and b'<svg' in qr.data
    assert _anon(d).get('/tournament/screen/no-such-event/qr.svg').status_code == 404

    m = t['matches'][0]
    for path in (f'/tournament/screen/{event_id}', f'/tournament/fixtures/{event_id}',
                 f"/tournament/live/{event_id}/{m['id']}"):
        page = _anon(d).get(path).get_data(as_text=True)
        assert 'property="og:image" content="http' in page and 'snpsu-logo.png' in page, path
        assert 'brand-logo' in page or 'data-college-logo' in page, path              # the logo on the page

    d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score")
    _ok(d['coord'], event_id, m, op='phase', action='start')
    live._cache.clear()
    fixtures = _anon(d).get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    assert 'data-live-now' in fixtures and f"/tournament/live/{event_id}/{m['id']}" in fixtures


# ── UPG-403: fewer reads, quicker updates ───────────────────────────────────

def test_the_big_screen_is_rendered_once_for_everyone_and_says_when_unchanged(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    t = _pkl(d, event_id, ids)
    m = t['matches'][0]
    d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score")
    _ok(d['coord'], event_id, m, op='phase', action='start')
    live._cache.clear()
    reads = []
    real = routes_sports._event
    monkeypatch.setattr(routes_sports, '_event', lambda eid: reads.append(eid) or real(eid))
    url = f'/tournament/screen/{event_id}/body'
    first = _anon(d).get(url)
    tag = first.headers['ETag']
    assert first.status_code == 200 and tag
    for _ in range(5):                                       # five more screens and phones, at once
        assert _anon(d).get(url).headers['ETag'] == tag
    assert len(reads) == 1
    same = _anon(d).get(url, headers={'If-None-Match': tag})
    assert same.status_code == 304 and not same.data

    _ok(d['coord'], event_id, m, op='point', team='home', kind='raid', points=4)   # shows at the next ask
    changed = _anon(d).get(url, headers={'If-None-Match': tag})
    assert changed.status_code == 200 and changed.headers['ETag'] != tag


def test_a_tap_reads_the_event_once_and_the_squads_are_kept(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    t = _pkl(d, event_id, ids)
    m = t['matches'][0]
    d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score")
    _ok(d['coord'], event_id, m, op='phase', action='start')
    reads = []
    real = routes_sports._event
    monkeypatch.setattr(routes_sports, '_event', lambda eid: reads.append(eid) or real(eid))
    _ok(d['coord'], event_id, m, op='point', team='home', kind='raid', points=2)
    assert len(reads) == 1

    reg = d['db'].collection('registrations').document(m['home'])
    reg.update({'lead_name': 'First Name', 'members': []})
    live._cache.clear()
    assert live.squads(d['db'], event_id, [m['home']])[m['home']] == ['First Name']
    reg.update({'lead_name': 'Changed Name'})
    assert live.squads(d['db'], event_id, [m['home']])[m['home']] == ['First Name']      # kept a minute
    live._cache.clear()
    assert live.squads(d['db'], event_id, [m['home']])[m['home']] == ['Changed Name']


# ── The scorer's page in a browser ──────────────────────────────────────────

def test_the_scorer_taps_raids_in_the_browser(league):  # noqa: F811
    d, event_id, ids = league
    t = _pkl(d, event_id, ids, scoring='pkl')
    m = t['matches'][0]
    path = f"/tournament/{event_id}/match/{m['id']}/score"
    html = d['coord'].get(path).get_data(as_text=True)
    p, browser = chromium()
    try:
        page = browser.new_context(viewport=PHONE).new_page()
        page.on('dialog', lambda dialog: dialog.accept())
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def handle(route):
            req = route.request
            if urlparse(req.url).path == path:
                if req.method == 'POST':
                    resp = d['coord'].post(path, data=req.post_data, content_type='application/json')
                    return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                         headers={'Content-Type': 'application/json'})
                return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        page.select_option('[data-first]', 'away')
        page.click('[data-phase-action="start"]')
        page.wait_for_selector('[data-pkl-panel][data-raider="away"] [data-raid][data-touches="2"]')
        page.click('[data-raid][data-touches="2"]')
        page.wait_for_selector('[data-pkl-panel][data-raider="home"]')
        assert page.text_content('[data-score="away"]').strip() == '2'
        assert 'Raid 2' in page.text_content('.pkl-raid-head')
        touches = '[data-pkl-panel] [data-raid][data-outcome="touch"]'
        assert page.locator(touches).count() == 7                  # home raids into 7 defenders
        page.click('[data-raid][data-outcome="empty"]')
        page.wait_for_selector('[data-pkl-panel][data-raider="away"]')
        assert page.locator(touches).count() == 5                  # away raids into the 5 home has left
        assert 'empty raid' in page.text_content('[data-recent]')
        assert not errors, errors
    finally:
        browser.close()
        p.stop()
    doc = live.get(d['db'], event_id, m['id'])
    assert [e['outcome'] for e in doc['events']] == ['touch', 'empty'] and json.dumps(doc['mat'])


def test_the_score_goes_up_at_the_tap_before_the_server_answers(league):  # noqa: F811
    d, event_id, ids = league
    t = _pkl(d, event_id, ids)
    m = t['matches'][0]
    path = f"/tournament/{event_id}/match/{m['id']}/score"
    d['coord'].get(path)
    _ok(d['coord'], event_id, m, op='phase', action='start')
    html = d['coord'].get(path).get_data(as_text=True)
    held = []
    p, browser = chromium()
    try:
        page = browser.new_context(viewport=PHONE).new_page()

        def handle(route):
            if urlparse(route.request.url).path == path:
                if route.request.method == 'POST':
                    held.append(route)                    # a slow connection: no answer yet
                    return None
                return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        page.click('[data-point][data-team="home"][data-kind="raid"][data-points="3"]')
        page.wait_for_function("document.querySelector('[data-score=\"home\"]').textContent.trim() === '3'")
        assert len(held) == 1 and 'Sending' in page.text_content('[data-message]')
        resp = d['coord'].post(path, data=held[0].request.post_data, content_type='application/json')
        held[0].fulfill(status=resp.status_code, body=resp.get_data(), headers={'Content-Type': 'application/json'})
        page.wait_for_function("document.querySelector('[data-message]').textContent === ''")
        assert page.text_content('[data-score="home"]').strip() == '3'
    finally:
        browser.close()
        p.stop()
