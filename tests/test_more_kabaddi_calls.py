"""
tests/test_more_kabaddi_calls.py — the rest of the Kabaddi scoring sheet
(owner's list, 23 Nov 2026). UPG-447: green, yellow and red cards. UPG-448:
more than one defender in a tackle ("caught by #1 Bharat with #3 Chetan") and
tackle assists on the profile. UPG-449: an injury break or official time-out
stops the clock without a team's time-out, and the boards say why. UPG-450: a
technical point's reason. UPG-451: the lobby. UPG-452: a bonus tried and not
given. UPG-453: "caught by" in the public feed. All names here are made up.
"""
import re
from urllib.parse import urlparse

import services_live_match as live
from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_kabaddi_premier_league import _generate, league  # noqa: F401
from tests.test_lineups_and_players import (_codes, _fresh_index, _lineups, _match, _named_match,
                                            _public, _raid, _started)
from tests.test_match_day_scoring import Clock
from tests.test_pkl_mode import _ok, _refused
from tests.test_sports_tournament import cup  # noqa: F401


def _call(d, event_id, m, **body):
    return _ok(d['coord'], event_id, m, op='call', **body)


def _carded(st, side):
    return [(c['name'], c['card'], c['left']) for c in st['mat']['players'][side]['carded']]


def _on(st, side):
    return [x['name'] for x in st['mat']['players'][side]['on']]


def _state(d, event_id, m):
    doc = live.get(d['db'], event_id, m['id'])
    return live.state(doc, {doc['home']: 'Garuda Sena', doc['away']: 'Vajra'})


def _card_box(page, side):
    box = re.search(rf'data-box-card="{side}">(.*?)</div>', page, re.S)
    return box.group(1) if box else ''


# ── UPG-447: cards ────────────────────────────────────────────────────────────

def test_a_yellow_card_takes_the_player_off_for_two_minutes_of_play(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    clock = Clock(monkeypatch)
    _started(d, event_id, m)
    clock.wait(30)
    data = _call(d, event_id, m, kind='card', card='yellow', team='home', player='Chetan')
    st = data['state']
    home = st['home']['name']
    assert st['recent'][0] == f'Yellow card · #3 Chetan ({home}) · off for 2 min'
    assert _carded(st, 'home') == [('Chetan', 'yellow', 120)]
    assert 'Chetan' not in _on(st, 'home') and st['mat']['on']['home'] == 6
    assert st['home']['total'] == 0 and st['away']['total'] == 0                    # no point by itself
    assert 'data-carded="home"' in data['panel'] and '2:00 left' in data['panel']

    # The public page shows him off, with the time left
    path = f"/tournament/live/{event_id}/{m['id']}"
    clock.wait(60)
    box = _card_box(_public(d, path), 'home')
    assert 'data-chip="Chetan"' in box and '01:00 left' in box and 'mat-chip--yellow' in box
    assert _carded(_state(d, event_id, m), 'home') == [('Chetan', 'yellow', 60)]

    # The clock stopped (a time-out): his time stops too
    _call(d, event_id, m, kind='timeout', team='away')
    clock.wait(300)
    assert _carded(_state(d, event_id, m), 'home') == [('Chetan', 'yellow', 60)]
    _ok(d['coord'], event_id, m, op='phase', action='resume')

    # Two minutes of play: he is back on the mat
    clock.wait(61)
    st = _state(d, event_id, m)
    assert _carded(st, 'home') == [] and 'Chetan' in _on(st, 'home') and st['mat']['on']['home'] == 7
    assert _card_box(_public(d, path), 'home') == ''
    # And the next tap keeps him on
    st = _raid(d, event_id, m, team='home', outcome='empty', raider='Arjun')['state']
    assert 'Chetan' in _on(st, 'home') and _carded(st, 'home') == []


def test_a_yellow_card_late_in_the_first_half_ends_in_the_second(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    clock = Clock(monkeypatch)
    _ok(d['coord'], event_id, m, op='timings', half_minutes=15, break_minutes=3)
    _started(d, event_id, m)
    clock.wait(860)
    _call(d, event_id, m, kind='card', card='yellow', team='away', player='Ganesh')
    clock.wait(100)                                         # 40 s of the half were left
    _ok(d['coord'], event_id, m, op='phase', action='half_time')
    clock.wait(180)
    _ok(d['coord'], event_id, m, op='phase', action='second_half')
    clock.wait(70)
    assert _carded(_state(d, event_id, m), 'away') == [('Ganesh', 'yellow', 10)]
    clock.wait(11)
    st = _state(d, event_id, m)
    assert _carded(st, 'away') == [] and 'Ganesh' in _on(st, 'away')


def test_a_red_card_is_off_for_the_match_and_a_red_after_a_yellow_too(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    clock = Clock(monkeypatch)
    _started(d, event_id, m)
    st = _call(d, event_id, m, kind='card', card='red', team='home', player='Darshan')['state']
    assert st['recent'][0].startswith('Red card · #5 Darshan (') and st['recent'][0].endswith('off for the match')
    assert _carded(st, 'home') == [('Darshan', 'red', None)]
    clock.wait(600)
    st = _state(d, event_id, m)
    assert _carded(st, 'home') == [('Darshan', 'red', None)] and st['mat']['on']['home'] == 6
    assert 'Red card' in _card_box(_public(d, f"/tournament/live/{event_id}/{m['id']}"), 'home')
    # Not substituted, not brought back by a point, nor by an all out
    _refused(d['coord'], event_id, m, 'one of the seven', op='call', kind='sub', team='home', off='Darshan', on='Hemanth')
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    _raid(d, event_id, m, team='away', outcome='touch', raider='Chandan', touched=['Arjun', 'Bharat'])
    st = _raid(d, event_id, m, team='home', outcome='touch', raider='Chetan', touched=['Ishaan'])['state']
    assert 'Darshan' not in _on(st, 'home') and 'Darshan' not in [x['name'] for x in st['mat']['players']['home']['bench']]
    # A red card for him again: refused
    _refused(d['coord'], event_id, m, 'of the seven', op='call', kind='card', card='red', team='home', player='Darshan')

    # A yellow, then a red: off for the match
    _call(d, event_id, m, kind='card', card='yellow', team='away', player='Deepak')
    clock.wait(30)
    st = _call(d, event_id, m, kind='card', card='red', team='away', player='Deepak')['state']
    assert _carded(st, 'away') == [('Deepak', 'red', None)]
    clock.wait(200)
    assert _carded(_state(d, event_id, m), 'away') == [('Deepak', 'red', None)]


def test_a_green_card_is_a_warning_and_a_card_names_a_player_of_the_seven(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    st = _call(d, event_id, m, kind='card', card='green', team='away', player='Harish')['state']
    assert st['recent'][0] == f"Green card · #5 Harish ({st['away']['name']}) · warning"
    assert _carded(st, 'away') == [] and st['mat']['on']['away'] == 7 and st['away']['total'] == st['home']['total'] == 0
    _refused(d['coord'], event_id, m, 'green, yellow or red', op='call', kind='card', card='blue', team='away', player='Harish')
    _refused(d['coord'], event_id, m, 'of the seven', op='call', kind='card', card='yellow', team='away', player='Mahesh')
    # One who is out can be carded too
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ishaan'])
    st = _call(d, event_id, m, kind='card', card='yellow', team='away', player='Ishaan')['state']
    assert _carded(st, 'away')[0][:2] == ('Ishaan', 'yellow') and 'Ishaan' not in [x['name'] for x in st['mat']['players']['away']['out']]


def test_without_line_ups_a_card_is_recorded_as_text(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids, home=['Arjun', 'Bharat', 'Chetan'])        # short of seven: scored by count
    _ok(d['coord'], event_id, m, op='phase', action='start', first='home')
    st = _call(d, event_id, m, kind='card', card='yellow', team='home')['state']
    assert st['recent'][0] == f"Yellow card · a {st['home']['name']} player · off for 2 min"
    st = _call(d, event_id, m, kind='card', card='red', team='away', player='Chandan')['state']
    assert st['recent'][0] == f"Red card · Chandan ({st['away']['name']}) · off for the match"   # no line-ups: no jersey numbers
    _refused(d['coord'], event_id, m, 'player of that team', op='call', kind='card', card='green', team='away', player='Nobody Else')
    panel = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    assert 'data-card-player="home"' in panel and 'data-kind="card" data-card="yellow"' in panel


# ── UPG-448 / UPG-453: everyone who caught him ────────────────────────────────

def test_every_defender_in_a_tackle_is_saved_and_the_feed_says_caught_by(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='empty', raider='Arjun')
    st = _raid(d, event_id, m, team='away', outcome='tackled', raider='Chandan',
               touched=['Bharat', 'Chetan', 'Darshan'], tackler='Bharat')['state']
    ev = live.get(d['db'], event_id, m['id'])['events'][-1]
    assert ev['tackler'] == 'Bharat' and ev['assists'] == ['Chetan', 'Darshan']
    assert st['home']['tackle'] == 1 and st['home']['total'] == 1                       # one point, to the first
    assert st['feed'][0] == f"{st['away']['name']} · #7 Chandan · tackled · caught by #1 Bharat with #3 Chetan, #5 Darshan +1"
    assert st['recent'][0].startswith(f"Raid · {st['away']['name']} (#7 Chandan): tackled by #1 Bharat with #3 Chetan, #5 Darshan")
    log = [e for e in live.get(d['db'], event_id, m['id'])['log'] if e.get('event') == ev['id']]
    assert log[0]['player'] == 'Bharat' and log[0]['assists'] == ['Chetan', 'Darshan']
    # Tapped without a tackler: the first tapped made the catch; a name not on the mat is dropped
    _raid(d, event_id, m, team='home', outcome='empty', raider='Arjun')
    _raid(d, event_id, m, team='away', outcome='tackled', raider='Deepak', touched=['Eshwar', 'Nobody', 'Farhan'])
    ev = live.get(d['db'], event_id, m['id'])['events'][-1]
    assert ev['tackler'] == 'Eshwar' and ev['assists'] == ['Farhan']
    # One defender: no assists
    _raid(d, event_id, m, team='home', outcome='empty', raider='Arjun')
    _raid(d, event_id, m, team='away', outcome='tackled', raider='Ganesh', touched=['Girish'])
    ev = live.get(d['db'], event_id, m['id'])['events'][-1]
    assert ev['tackler'] == 'Girish' and 'assists' not in ev


def test_the_profile_counts_tackle_assists(league):  # noqa: F811
    d, event_id, ids = league
    m, tag, home, away, _ = _named_match(d, event_id, ids)
    _lineups(d, event_id, m, home=home[:7], away=away[:7])
    _ok(d['coord'], event_id, m, op='phase', action='start', first='away')
    _raid(d, event_id, m, team='away', outcome='tackled', raider=away[0], touched=[home[1], home[0]])
    _fresh_index()
    [code] = _codes(_public(d, f'/players?q=arjun+q{tag}'))
    career = dict(re.findall(r'data-stat="(\w+)"><b>(\d+)</b>', _public(d, f'/players/{code}')))
    assert career['assists'] == '1' and career['tackle'] == '0'
    assert 'Tackle assists' in _public(d, f'/players/{code}')
    [bharat] = _codes(_public(d, f'/players?q=bharat+q{tag}'))
    career = dict(re.findall(r'data-stat="(\w+)"><b>(\d+)</b>', _public(d, f'/players/{bharat}')))
    assert career['tackle'] == '1' and career['assists'] == '0'


# ── UPG-449: injury break, official time-out ─────────────────────────────────

def test_an_injury_break_stops_the_clock_without_a_time_out_and_the_boards_say_why(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    clock = Clock(monkeypatch)
    _started(d, event_id, m)
    _ok(d['coord'], event_id, m, op='raid_clock', action='start')
    clock.wait(40)
    st = _call(d, event_id, m, kind='stoppage', reason='injury', team='home', player='Arjun')['state']
    home, away = st['home']['name'], st['away']['name']
    assert not st['running'] and st['raid_clock'] is None
    assert st['mat']['timeouts_left'] == {'home': 2, 'away': 2}
    assert st['stopped_for'] == f'Injury break · #7 Arjun ({home})'
    assert st['recent'][0] == f'Injury break · #7 Arjun ({home}) · clock stopped'
    left = st['left']
    clock.wait(120)
    assert _state(d, event_id, m)['left'] == left                 # stopped: the half's time doesn't run
    path = f"/tournament/live/{event_id}/{m['id']}"
    line = re.search(r'<p class="live-stop" data-stop-line\s*>(.*?)</p>', _public(d, path), re.S)
    assert line and f'Injury break · #7 Arjun ({home})' in line.group(1)
    live._cache.clear()
    screen = d['app'].test_client().get(f'/tournament/screen/{event_id}/body').get_data(as_text=True)
    assert re.search(rf'data-screen-stop>Injury break · #7 Arjun \({re.escape(home)}\)<', screen)
    # Resume: the line goes
    st = _ok(d['coord'], event_id, m, op='phase', action='resume')['state']
    assert st['stopped_for'] == '' and re.search(r'data-stop-line\s*hidden', _public(d, path))

    # The official time-out names no team; a team's time-out says whose
    st = _call(d, event_id, m, kind='stoppage', reason='official')['state']
    assert st['stopped_for'] == 'Official time-out' and st['recent'][0] == 'Official time-out · clock stopped'
    _ok(d['coord'], event_id, m, op='phase', action='resume')
    st = _call(d, event_id, m, kind='timeout', team='away')['state']
    assert st['stopped_for'] == f'Time-out · {away}' and st['mat']['timeouts_left']['away'] == 1
    _ok(d['coord'], event_id, m, op='phase', action='resume')
    _refused(d['coord'], event_id, m, 'injury break or an official time-out', op='call', kind='stoppage', reason='rain')


# ── UPG-450: why the technical point ─────────────────────────────────────────

def test_a_technical_point_can_say_why(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    st = _call(d, event_id, m, kind='technical', team='away', reason='coach')['state']
    assert st['recent'][0] == f"Technical point +1 · {st['away']['name']} · coach or official on the court"
    assert st['away']['total'] == 1
    st = _call(d, event_id, m, kind='technical', team='home')['state']
    assert st['recent'][0] == f"Technical point +1 · {st['home']['name']}"
    _refused(d['coord'], event_id, m, 'reason from the list', op='call', kind='technical', team='home', reason='weather')
    panel = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    assert re.search(r'data-kind="technical" data-reason="late_sub" data-team="home">Late or wrong substitution<', panel)


# ── UPG-451: the lobby ───────────────────────────────────────────────────────

def test_a_player_in_the_lobby_is_out_and_the_other_team_gets_a_point(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    st = _call(d, event_id, m, kind='out_of_bounds', where='lobby', team='away', player='Ganesh')['state']
    assert st['recent'][0] == f"Lobby · #3 Ganesh ({st['away']['name']}) went into the lobby before a struggle: out"
    assert st['home']['total'] == 1 and 'Ganesh' in [x['name'] for x in st['mat']['players']['away']['out']]
    _refused(d['coord'], event_id, m, 'went into the lobby', op='call', kind='out_of_bounds', where='lobby',
             team='away', player='Ganesh')
    # A plain out of bounds still reads as before
    st = _call(d, event_id, m, kind='out_of_bounds', team='away', player='Harish')['state']
    assert st['recent'][0] == f"Out of bounds · #5 Harish ({st['away']['name']}) is out"


def test_without_line_ups_the_lobby_is_a_call_for_the_team(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids, home=['Arjun', 'Bharat', 'Chetan'])        # short of seven: scored by count
    _ok(d['coord'], event_id, m, op='phase', action='start', first='home')
    st = _call(d, event_id, m, kind='out_of_bounds', where='lobby', team='home')['state']
    assert st['recent'][0] == f"Lobby · a {st['home']['name']} player went into the lobby before a struggle: out"
    assert st['away']['total'] == 1


# ── UPG-452: a bonus tried and not given ──────────────────────────────────────

def test_a_bonus_tried_and_not_given_is_said_and_scores_nothing(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    st = _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'], bonus_missed=True)['state']
    assert st['home']['total'] == 1
    assert ', bonus not given' in st['recent'][0] and st['feed'][0].endswith('1 touch, bonus not given +1 · out #3')
    _refused(d['coord'], event_id, m, 'not both', op='raid', team='away', outcome='touch', raider='Chandan',
             touched=['Bharat'], bonus=True, bonus_missed=True)
    # Under six defenders the bonus line isn't live
    _raid(d, event_id, m, team='away', outcome='empty', raider='Chandan')
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Harish'])
    _raid(d, event_id, m, team='away', outcome='empty', raider='Chandan')
    _refused(d['coord'], event_id, m, 'bonus line counts only', op='raid', team='home', outcome='empty',
             raider='Arjun', bonus_missed=True)


# ── The scorer's taps, in the browser ────────────────────────────────────────

def test_the_scorer_taps_cards_the_lobby_an_injury_and_a_reason_in_the_browser(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    path = f"/tournament/{event_id}/match/{m['id']}/score"
    html = d['coord'].get(path).get_data(as_text=True)
    for tool in ('card_green', 'card_yellow', 'card_red', 'lobby', 'injury'):
        assert f'data-tool="{tool}" data-side="home"' in html, tool
    assert 'data-pkl-bonus-missed' in html and 'data-reason="official"' in html
    sent = []
    p, browser = chromium()
    try:
        page = browser.new_context(viewport={'width': 1280, 'height': 900}).new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('dialog', lambda dlg: dlg.accept())

        def handle(route):
            req = route.request
            if urlparse(req.url).path == path:
                if req.method == 'POST':
                    sent.append(req.post_data_json)
                    resp = d['coord'].post(path, data=req.post_data, content_type='application/json')
                    return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                         headers={'Content-Type': 'application/json'})
                return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')

        def calls():
            return [b for b in sent if b.get('op') in ('call', 'raid')]

        def wait_for(n):
            for _ in range(40):
                if len(calls()) >= n:
                    break
                page.wait_for_timeout(100)
            page.wait_for_timeout(300)

        # A yellow card: the tool, then the player
        page.click('[data-tool="card_yellow"][data-side="home"]')
        assert 'Yellow card' in page.inner_text('[data-guide-text]')
        page.click('[data-mat-player][data-side="home"][data-name="Chetan"]')
        wait_for(1)
        page.wait_for_selector('[data-carded="home"] [data-name="Chetan"]')
        # The lobby
        page.click('[data-tool="lobby"][data-side="away"]')
        page.click('[data-mat-player][data-side="away"][data-name="Ganesh"]')
        wait_for(2)
        # A raid with the bonus tried, not given
        page.click('[data-mat-player][data-role="raider"][data-name="Arjun"]')
        page.click('[data-mat-player][data-role="defender"][data-name="Harish"]')
        page.check('[data-pkl-bonus-missed]')
        page.click('[data-touch-button]')
        wait_for(3)
        # A technical point with its reason
        page.click('details.pkl-calls > summary')
        page.click('[data-call][data-kind="technical"][data-reason="delay"][data-team="away"]')
        wait_for(4)
        # An injury break by tap
        page.click('[data-tool="injury"][data-side="away"]')
        page.click('[data-mat-player][data-side="away"][data-name="Deepak"]')
        wait_for(5)
        assert not errors, errors
    finally:
        browser.close()
        p.stop()
    got = calls()
    assert {k: got[0][k] for k in ('kind', 'card', 'team', 'player')} == {
        'kind': 'card', 'card': 'yellow', 'team': 'home', 'player': 'Chetan'}
    assert {k: got[1][k] for k in ('kind', 'where', 'team', 'player')} == {
        'kind': 'out_of_bounds', 'where': 'lobby', 'team': 'away', 'player': 'Ganesh'}
    assert got[2]['op'] == 'raid' and got[2]['bonus_missed'] is True and got[2]['touched'] == ['Harish']
    assert got[3]['kind'] == 'technical' and got[3]['reason'] == 'delay'
    assert {k: got[4][k] for k in ('kind', 'reason', 'team', 'player')} == {
        'kind': 'stoppage', 'reason': 'injury', 'team': 'away', 'player': 'Deepak'}
    doc = live.get(d['db'], event_id, m['id'])
    assert [e['type'] for e in doc['events']] == ['card', 'out_of_bounds', 'raid', 'technical', 'stoppage']
