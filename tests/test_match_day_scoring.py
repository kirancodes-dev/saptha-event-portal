"""
tests/test_match_day_scoring.py — the match day (owner's requirements, 23 Nov
2026). UPG-437: the SPOC sees each player's jersey, DOB with the age and
position, and the team logo as a picture. UPG-438: the toss before the start
and its animation. UPG-439: the half and break minutes, the time left.
UPG-413: the 30-second raid clock, Space to start and stop, the raid's time
saved; "Raid time over". UPG-440: the public page counts each phone once.
UPG-441: each team's players in a drop-down. UPG-443: every match's date in
one table. All names here are made up.
"""
import datetime
import re
from urllib.parse import urlparse

import pytest

import services_export
import services_live_match as live
import services_sports
from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_kabaddi_premier_league import _generate, league  # noqa: F401
from tests.test_lineups_and_players import _match, _public, _raid, _started
from tests.test_pkl_mode import _ok, _refused
from tests.test_sports_tournament import cup  # noqa: F401
from tests.test_tap_targets import PHONE

PHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'


class Clock:
    """The server's time, moved on by hand."""
    def __init__(self, monkeypatch, start=1_800_000_000.0):
        self.t = start
        monkeypatch.setattr(live, '_now', lambda: self.t)

    def wait(self, secs):
        self.t += secs


def _born(years_ago, days_more=10):
    today = datetime.date.today()
    return (today.replace(year=today.year - years_ago) - datetime.timedelta(days=days_more)).isoformat()


# ── UPG-438: the toss ─────────────────────────────────────────────────────────

def test_the_toss_sets_who_raids_first_and_is_only_before_the_start(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    page = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    assert 'data-before-start' in page and 'data-toss-pick="home"' in page and 'data-half-minutes' in page

    # Away won and chose to raid: away raids first
    data = _ok(d['coord'], event_id, m, op='toss', winner='away', choice='raid')
    names = services_sports.names(d['db'].collection('events').document(event_id).get().to_dict()['tournament'])
    away = names[m['away']]
    assert data['state']['toss']['text'] == f"{away} won the toss and chose to raid first"
    assert live.get(d['db'], event_id, m['id'])['first_raid'] == 'away'
    # Changed: away won and chose the court, so home raids first
    data = _ok(d['coord'], event_id, m, op='toss', winner='away', choice='court')
    assert data['state']['toss']['chose'].startswith('chose the court') and 'raid first' in data['state']['toss']['text']
    assert live.get(d['db'], event_id, m['id'])['first_raid'] == 'home'
    assert 'data-toss-saved="true"' in data['panel'] and 'set by the toss' in data['panel']

    # Wrong taps say what to do
    _refused(d['coord'], event_id, m, 'Tap the team', op='toss', winner='', choice='raid')
    _refused(d['coord'], event_id, m, 'Tap what they chose', op='toss', winner='home', choice='')

    # The public page shows the toss before the start
    path = f"/tournament/live/{event_id}/{m['id']}"
    public = _public(d, path)
    line = re.search(r'<p class="live-toss" data-toss-line\s*>(.*?)</p>', public, re.S)
    assert line and f"{away} won the toss" in line.group(1)

    # After the start: no toss, and the line goes
    _started(d, event_id, m, first='home')
    _refused(d['coord'], event_id, m, 'before the start', op='toss', winner='home', choice='raid')
    assert re.search(r'data-toss-line\s*hidden', _public(d, path))


def test_the_toss_plays_once_on_the_public_page(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _ok(d['coord'], event_id, m, op='toss', winner='home', choice='raid')
    path = f"/tournament/live/{event_id}/{m['id']}"
    p, browser = chromium()
    try:
        context = browser.new_context(viewport=PHONE)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def handle(route):
            req_path = urlparse(route.request.url).path
            if req_path.startswith(path):
                live._cache.clear()
                resp = d['app'].test_client().get(req_path, headers={'User-Agent': PHONE_UA})
                return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                     headers={'Content-Type': resp.content_type})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        # The coin, then the winner's name and "won the toss", then what they chose
        page.wait_for_selector('[data-toss-show].is-flip', timeout=8000)
        page.wait_for_selector('[data-toss-show].is-won', timeout=4000)
        assert 'won the toss' in page.text_content('.toss-show__won')
        page.wait_for_selector('[data-toss-show].is-chose', timeout=5000)
        assert 'chose to raid first' in page.text_content('.toss-show__chose')
        page.click('[data-toss-show]')                                   # a tap closes it
        assert page.locator('[data-toss-show]').count() == 0
        # Opened again on the same phone: not again
        page.reload(wait_until='load')
        page.wait_for_timeout(3500)
        assert page.locator('[data-toss-show]').count() == 0
        assert not errors, errors
    finally:
        browser.close()
        p.stop()


def test_the_big_screen_plays_a_toss_just_made(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    screen = f'/tournament/screen/{event_id}/body'
    assert 'data-screen-toss' not in d['app'].test_client().get(screen).get_data(as_text=True)
    clock = Clock(monkeypatch)
    _ok(d['coord'], event_id, m, op='toss', winner='away', choice='court')
    live._cache.clear()
    body = d['app'].test_client().get(screen).get_data(as_text=True)
    tpl = re.search(r'<template data-screen-toss([^>]*)>', body)
    assert tpl and 'data-winner="away"' in tpl.group(1) and 'chose the court' in tpl.group(1)
    # Ten minutes on, the screen no longer plays it
    clock.wait(live.TOSS_FRESH_SECONDS + 1)
    live._cache.clear()
    assert 'data-screen-toss' not in d['app'].test_client().get(screen).get_data(as_text=True)


# ── UPG-439: the timings ──────────────────────────────────────────────────────

def test_the_scorer_sets_the_halves_and_the_break_and_the_boards_show_the_time_left(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    clock = Clock(monkeypatch)
    _refused(d['coord'], event_id, m, 'A half is 1 to 60', op='timings', half_minutes=0, break_minutes=5)
    _refused(d['coord'], event_id, m, 'The break is 0 to 30', op='timings', half_minutes=15, break_minutes=45)
    _refused(d['coord'], event_id, m, 'is a number of minutes', op='timings', half_minutes='ten', break_minutes=5)
    data = _ok(d['coord'], event_id, m, op='timings', half_minutes=15, break_minutes=3)
    assert data['state']['half_minutes'] == 15 and data['state']['break_minutes'] == 3
    assert '15-minute halves, a 3-minute break' in data['panel']

    _started(d, event_id, m)
    clock.wait(60)
    st = _ok(d['coord'], event_id, m, op='raid_clock', action='clear')['state']
    assert st['half_seconds'] == 900 and st['left'] == 840 and not st['time_up']
    _refused(d['coord'], event_id, m, 'before the start or at half time', op='timings', half_minutes=20, break_minutes=5)
    path = f"/tournament/live/{event_id}/{m['id']}"
    assert re.search(r'data-clock-left>14:00 left<', _public(d, path))
    clock.wait(900)
    st = _ok(d['coord'], event_id, m, op='raid_clock', action='clear')['state']
    assert st['left'] == 0 and st['time_up'] and 'Time up' in _public(d, path)

    # Half time: the break counts down; the timings can change then too
    st = _ok(d['coord'], event_id, m, op='phase', action='half_time')['state']
    assert st['left'] is None and st['break_left'] == 180
    clock.wait(70)
    st = _ok(d['coord'], event_id, m, op='timings', half_minutes=15, break_minutes=3)['state']
    assert st['break_left'] == 110
    assert 'Break · 01:50 left' in _public(d, path)
    st = _ok(d['coord'], event_id, m, op='phase', action='second_half')['state']
    assert st['break_left'] is None and st['left'] is not None


# ── UPG-413: the raid clock ───────────────────────────────────────────────────

def test_the_raid_clock_saves_how_long_each_raid_took(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    clock = Clock(monkeypatch)
    _refused(d['coord'], event_id, m, 'Start the half first', op='raid_clock', action='start')
    _started(d, event_id, m)

    # Started, 12 seconds, stopped: back in 12 s
    st = _ok(d['coord'], event_id, m, op='raid_clock', action='start')['state']
    assert st['raid_clock'] == {'team': 'home', 'secs': 0, 'running': True, 'left': 30, 'over': False}
    clock.wait(12.4)
    st = _ok(d['coord'], event_id, m, op='raid_clock', action='stop')['state']
    assert st['raid_clock']['secs'] == 12 and not st['raid_clock']['running']
    clock.wait(5)                                            # stopped: it doesn't go on
    data = _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    doc = live.get(d['db'], event_id, m['id'])
    assert doc['events'][-1]['secs'] == 12 and 'raid_clock' not in doc
    assert data['state']['recent_secs'][0] == 'back in 12 s' and data['state']['raid_clock'] is None
    assert 'back in 12 s' not in data['state']['recent'][0]          # the raid's text stays as it was
    assert 'back in 12 s' in _public(d, f"/tournament/live/{event_id}/{m['id']}")

    # Tapping the raider starts the clock by itself; the raid saves the seconds so far
    _ok(d['coord'], event_id, m, op='raider', team='away', name='Chandan')
    clock.wait(8)
    st = live.state(live.get(d['db'], event_id, m['id']), {})
    assert st['raid_clock']['running'] and st['raid_clock']['secs'] == 8 and st['raid_clock']['team'] == 'away'
    _raid(d, event_id, m, team='away', outcome='tackled', raider='Chandan', touched=[], tackler='Arjun')
    assert live.get(d['db'], event_id, m['id'])['events'][-1]['secs'] == 8
    assert live.secs_text({'type': 'raid', 'outcome': 'tackled', 'secs': 8}) == '8 s'
    assert live.secs_text({'type': 'raid', 'outcome': 'empty', 'secs': 30}) == 'back in 30 s'
    assert live.secs_text({'type': 'raid', 'outcome': 'empty'}) == ''

    # A raid without the clock: no seconds
    _raid(d, event_id, m, team='home', outcome='empty', raider='Bharat')
    assert 'secs' not in live.get(d['db'], event_id, m['id'])['events'][-1]

    # Half time clears a running clock
    _ok(d['coord'], event_id, m, op='raid_clock', action='start')
    _ok(d['coord'], event_id, m, op='phase', action='half_time')
    assert 'raid_clock' not in live.get(d['db'], event_id, m['id'])
    _refused(d['coord'], event_id, m, 'Start the half first', op='raid_clock', action='start')


def test_raid_time_over_puts_the_raider_out_and_gives_the_defence_a_point(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    clock = Clock(monkeypatch)
    _started(d, event_id, m)
    _ok(d['coord'], event_id, m, op='raid_clock', action='start')
    clock.wait(31)
    st = live.state(live.get(d['db'], event_id, m['id']), {})
    assert st['raid_clock']['over'] and st['raid_clock']['left'] == 0
    data = _raid(d, event_id, m, team='home', outcome='time_over', raider='Arjun')
    st = data['state']
    assert st['away']['total'] == 1 and st['home']['total'] == 0 and st['away']['extra'] == 1
    assert 'Arjun' in [x['name'] for x in st['mat']['players']['home']['out']]
    assert 'raid time over' in st['recent'][0] and st['recent_secs'][0] == '31 s'
    assert st['mat']['raider'] == 'away'                                   # the turn passes
    panel = data['panel']
    assert 'data-outcome="time_over"' in panel and 'data-raid-clock-btn' in panel


def test_raid_time_over_on_a_do_or_die_raid_starts_the_count_again(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    # Two empty raids each, then home's third is do-or-die
    for _ in range(2):
        _raid(d, event_id, m, team='home', outcome='empty', raider='Arjun')
        _raid(d, event_id, m, team='away', outcome='empty', raider='Chandan')
    st = live.state(live.get(d['db'], event_id, m['id']), {})
    assert st['mat']['do_or_die']
    st = _raid(d, event_id, m, team='home', outcome='time_over', raider='Arjun')['state']
    assert st['away']['total'] == 1 and 'Arjun' in [x['name'] for x in st['mat']['players']['home']['out']]
    st = _raid(d, event_id, m, team='away', outcome='empty', raider='Chandan')['state']
    assert st['mat']['raider'] == 'home' and not st['mat']['do_or_die']           # home's count starts again


def test_space_starts_and_stops_the_raid_clock_in_the_browser(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    path = f"/tournament/{event_id}/match/{m['id']}/score"
    html = d['coord'].get(path).get_data(as_text=True)
    assert 'data-raid-clock-btn' in html and '<kbd>Space</kbd>' in html
    sent = []
    p, browser = chromium()
    try:
        page = browser.new_context(viewport={'width': 1280, 'height': 900}).new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

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
        box = '[data-raid-clock-box]'
        page.keyboard.press('Space')
        page.wait_for_selector(f'{box}.is-running')
        page.wait_for_function("document.querySelector('[data-raid-clock-text]').textContent.indexOf('29 s left') >= 0"
                               " || document.querySelector('[data-raid-clock-text]').textContent.indexOf('28 s left') >= 0",
                               timeout=4000)
        page.keyboard.press('Space')
        page.wait_for_function("document.querySelector('[data-raid-clock-text]').textContent.indexOf('Back in') === 0",
                               timeout=4000)
        assert not page.locator(f'{box}.is-running').count()
        # Space in a text box types a space; it doesn't touch the clock
        page.wait_for_timeout(300)
        before = len([b for b in sent if b.get('op') == 'raid_clock'])
        assert before == 2 and [b['action'] for b in sent if b.get('op') == 'raid_clock'] == ['start', 'stop']
        assert not errors, errors
    finally:
        browser.close()
        p.stop()
    doc = live.get(d['db'], event_id, m['id'])
    assert doc['raid_clock']['stopped'] is not None and doc['raid_clock']['stopped'] >= 1


# ── UPG-440: each phone once ──────────────────────────────────────────────────

def test_the_public_page_counts_each_phone_once_and_never_less(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    url = f"/tournament/live/{event_id}/{m['id']}"
    phone = d['app'].test_client()
    for _ in range(3):                                     # in and out three times: still one
        page = phone.get(url, headers={'User-Agent': PHONE_UA}).get_data(as_text=True)
    assert re.search(r'<strong data-watch-count>1</strong> watching', page)
    live._cache.clear()
    assert phone.get(f'{url}/state').get_json()['state']['watching'] == '1'
    d['app'].test_client().get(url, headers={'User-Agent': PHONE_UA})
    live._cache.clear()
    assert phone.get(f'{url}/state').get_json()['state']['watching'] == '2'


# ── UPG-441: each team's players ──────────────────────────────────────────────

def test_each_team_has_a_drop_down_of_its_players_without_their_contacts(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    dob = _born(20)
    d['db'].collection('registrations').document(m['home']).update({
        'lead_name': 'Arjun', 'lead_email': 'arjun@example.org',
        'members': [{'name': 'Arjun', 'jersey': '7', 'jersey_name': 'arju', 'position': 'Raider', 'dob': dob,
                     'email': 'arjun@example.org', 'phone': '9000000001', 'usn': '1XX22CS001', 'role': 'lead'},
                    {'name': 'Bharat', 'jersey': '1', 'position': 'Defender (corner)', 'dob': _born(19),
                     'email': 'bharat@example.org', 'phone': '9000000002'}]})
    live._cache.clear()
    page = _public(d, f"/tournament/live/{event_id}/{m['id']}")
    box = re.search(r'<details class="team-details__team" data-team-detail="home">(.*?)</details>', page, re.S).group(1)
    assert 'Team details' in box and '2 players' in box
    rows = re.findall(r'<tr data-roster-player>(.*?)</tr>', box, re.S)
    text = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', r)).strip() for r in rows]
    assert text[0].startswith('#7 Arjun ARJU Captain') and 'Raider' in text[0] and text[0].endswith('20')
    assert text[1].startswith('#1 Bharat') and 'Defender (corner)' in text[1] and text[1].endswith('19')
    assert 'Raider · 1' in box and 'Defender (corner) · 1' in box
    for secret in ('example.org', '9000000001', '1XX22CS001', dob):
        assert secret not in page
    assert 'data-team-detail="away"' in page


# ── UPG-437: the registration's details for the SPOC ─────────────────────────

def test_the_spoc_sees_each_players_jersey_dob_and_age_and_the_logo():
    class Snap:
        exists = True

        def to_dict(self):
            return {'form': {'fields': [{'id': 'team_logo', 'type': 'file', 'label': 'Team logo'}]}}

    reg = {'lead_name': 'Ravi Kumar', 'lead_email': 'ravi@example.org',
           'form_answers': {'lead_jersey': '9', 'lead_jersey_name': 'RAVI', 'lead_dob': '2004-05-06',
                            'lead_position': 'Raider', 'team_logo': '/uploads/logo-x.png'},
           'members': [{'name': 'Sunil', 'jersey': '4', 'jersey_name': 'SUNI', 'dob': '2005-01-02',
                        'position': 'All-rounder'}]}
    details = services_export.FormDetails.__new__(services_export.FormDetails)
    details.fields, details.usn_ids, details.phone_ids = [], [], []
    got = details.of(reg)
    lead = dict(got['lead'])
    age = services_export._age('2004-05-06')
    assert lead['Jersey number'] == '9' and lead['Jersey name'] == 'RAVI' and lead['Position'] == 'Raider'
    assert lead['Date of birth'] == f'2004-05-06 (age {age})'
    member = dict(got['members'][0])
    assert member['Jersey number'] == '4' and member['Position'] == 'All-rounder'
    assert member['Date of birth'].startswith('2005-01-02 (age ')
    assert got['logo'] == '/uploads/logo-x.png'
    assert not any('no longer on the form' in label for label, _ in got['answers'])
    assert not any(label == 'team_logo' for label, _ in got['answers'])
    # A logo that isn't a picture's address stays as typed; javascript: never becomes a picture
    reg['form_answers']['team_logo'] = 'javascript:alert(1)'
    got = details.of(reg)
    assert got['logo'] == '' and ('Team logo', 'javascript:alert(1)') in got['answers']
    assert services_export._age('2004-05-06', datetime.date(2026, 5, 5)) == 21
    assert services_export._age('2004-05-06', datetime.date(2026, 5, 6)) == 22
    assert services_export._age('') is None and services_export._age('not a date') is None


def test_the_details_panel_shows_the_logo_as_a_picture(cup):  # noqa: F811
    d = cup
    with d['app'].test_request_context('/'):
        from flask import render_template_string
        html = render_template_string(
            '{% from "coordinator/_details.html" import details_panel %}{{ details_panel(d) }}',
            d={'lead': [('Name', 'Ravi Kumar'), ('Date of birth', '2004-05-06 (age 22)')], 'members': [],
               'answers': [], 'logo': '/uploads/logo-x.png'})
    assert re.search(r'<img src="/uploads/logo-x.png" alt="Team logo"[^>]*data-detail-logo>', html)
    assert '2004-05-06 (age 22)' in html


# ── UPG-443: every match's date in one table ─────────────────────────────────

def test_the_spoc_sets_every_matchs_date_in_one_table(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    table = re.search(r'<details class="card mb-3" id="match-dates" data-match-dates open>(.*?)</details>', page, re.S)
    assert table and f'{len(t["matches"])} without a date' in table.group(1)
    assert len(re.findall(r'data-date-row=', table.group(1))) == len(t['matches'])
    first, second = t['matches'][0]['id'], t['matches'][1]['id']
    resp = d['owner'].post(f'/tournament/{event_id}/schedule/all', data={
        f'date-{first}': '2026-11-28', f'time-{first}': '16:30', f'venue-{first}': 'Court 1',
        f'date-{second}': '29/11/2026', f'time-{second}': '', f'venue-{second}': ''})
    assert resp.status_code == 302 and resp.headers['Location'].endswith('#match-dates')
    saved = {m['id']: m for m in d['db'].collection('events').document(event_id).get().to_dict()['tournament']['matches']}
    assert (saved[first]['date'], saved[first]['time'], saved[first]['venue']) == ('2026-11-28', '16:30', 'Court 1')
    assert saved[second]['date'] == '2026-11-29'
    assert not saved[t['matches'][2]['id']].get('date')                     # not sent: as it was
    # The public fixtures show them as people read them
    public = d['app'].test_client().get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)
    shown = re.sub(r'<[^>]+>', '', public)
    assert 'Sat 28 Nov · 4:30 PM · Court 1' in shown and 'Sun 29 Nov' in shown
    # ... and the exact date and time stay in the page for machines
    assert '<time datetime="2026-11-28 16:30">Sat 28 Nov · 4:30 PM</time>' in public
    assert '<time datetime="2026-11-29">Sun 29 Nov</time>' in public
    # A wrong date changes nothing and names the match
    d['owner'].post(f'/tournament/{event_id}/schedule/all', data={f'date-{first}': 'next week'})
    saved = {m['id']: m for m in d['db'].collection('events').document(event_id).get().to_dict()['tournament']['matches']}
    assert saved[first]['date'] == '2026-11-28'
    # Only the SPOC: a stranger can't
    assert d['app'].test_client().post(f'/tournament/{event_id}/schedule/all', data={}).status_code in (302, 401, 403)


@pytest.mark.parametrize('m, text', [
    ({'date': '2026-11-28', 'time': '09:05'}, 'Sat 28 Nov · 9:05 AM'),
    ({'date': '2026-11-28', 'time': '12:00'}, 'Sat 28 Nov · 12:00 PM'),
    ({'date': '2026-11-28', 'time': '00:15'}, 'Sat 28 Nov · 12:15 AM'),
    ({'date': '2026-11-28'}, 'Sat 28 Nov'),
    ({'time': '18:00'}, '6:00 PM'),
    ({'date': 'Day 2'}, 'Day 2'),
    ({}, ''),
])
def test_a_matchs_date_reads_like_a_person_wrote_it(m, text):
    assert services_sports.when(m) == text


def test_the_big_screen_shows_the_time_left_and_the_raid_clock(league, monkeypatch):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    clock = Clock(monkeypatch)
    _ok(d['coord'], event_id, m, op='timings', half_minutes=20, break_minutes=5)
    _started(d, event_id, m)
    _ok(d['coord'], event_id, m, op='raid_clock', action='start')
    clock.wait(7)
    live._cache.clear()
    body = d['app'].test_client().get(f'/tournament/screen/{event_id}/body').get_data(as_text=True)
    assert re.search(r'data-screen-left="1193" data-running="true"[^>]*>19:53 left<', body)
    assert re.search(r'data-screen-raid="7" data-running="true" data-limit="30">Raid · 23 s<', body)
    # The scorer's board hides the raid line (the scorer has the big clock); the public page shows it
    public = _public(d, f"/tournament/live/{event_id}/{m['id']}")
    assert re.search(r'data-raid-clock\s+data-secs="7" data-running="true"', public)


# ── UPG-436: who raids, said once; UPG-442: the team's name and logo ─────────

def test_who_raids_is_said_once_until_the_raider_is_tapped(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    path = f"/tournament/live/{event_id}/{m['id']}"
    page = _public(d, path)
    assert 'data-raiding-line' not in page and re.search(r'data-mat-line\s*>[^<]*to raid', page)
    live._cache.clear()
    screen = d['app'].test_client().get(f'/tournament/screen/{event_id}/body').get_data(as_text=True)
    assert 'data-raiding-line' not in screen and screen.count(' to raid') == 1
    _ok(d['coord'], event_id, m, op='raider', name='Arjun')
    page = _public(d, path)
    line = re.search(r'<p class="mat-now" data-raiding-line>(.*?)</p>', page, re.S).group(1)
    assert 'Raiding now' in line and 'Arjun' in line and '#7' in line


def test_a_team_without_a_logo_shows_its_initials_and_its_whole_name(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    t = d['db'].collection('events').document(event_id).get().to_dict()['tournament']
    names, logos = services_sports.names(t), services_sports.logos(t)
    assert not logos.get(m['home'])
    page = _public(d, f"/tournament/live/{event_id}/{m['id']}")
    initials = ''.join(w[0].upper() for w in names[m['home']].split()[:2])
    assert re.search(rf'<span class="live-board__logo live-board__initials" aria-hidden="true" data-team-initials>{initials}</span>', page)
    assert f'<div class="live-board__name" title="{names[m["home"]]}">{names[m["home"]]}</div>' in page
    assert 'data-logo-home=""' in page                                # the toss shows the initials too
    css = open('static/css/live_match.css').read() + open('static/css/tournament_screen.css').read()
    assert '.live-board__name { overflow-wrap: break-word' in css and '.tv-board__name { overflow-wrap: break-word' in css


# ── UPG-444: the match page opens at the score on a laptop or a hall screen ───

def test_the_match_page_opens_at_the_score_not_the_player_search(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    path = f"/tournament/live/{event_id}/{m['id']}"
    page = _public(d, path)
    assert re.search(r'data-player-search data-no-autofocus>', page)
    p, browser = chromium()
    try:
        tab = browser.new_context(viewport={'width': 1366, 'height': 768}).new_page()   # a mouse: autofocus applies

        def handle(route):
            req_path = urlparse(route.request.url).path
            if req_path.startswith(path):
                live._cache.clear()
                resp = d['app'].test_client().get(req_path)
                return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                     headers={'Content-Type': resp.content_type})
            return _serve_static(route)
        tab.route('**/*', handle)
        tab.goto(ORIGIN + path, wait_until='load')
        tab.wait_for_timeout(500)
        assert tab.evaluate('window.scrollY') == 0
        assert tab.evaluate("document.activeElement.id") != 'player-q-c'
    finally:
        browser.close()
        p.stop()
