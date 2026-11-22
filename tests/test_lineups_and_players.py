"""
tests/test_lineups_and_players.py — the players first (owner's requirements,
22 Nov 2026). UPG-417: each team's seven before the start; UPG-404: the players
on the mat and out by name, revived in order, substitutions; UPG-420: the
scorer taps the players (jersey number and name), not lists.
"""
import json
import re
from urllib.parse import urlparse

import services_live_match as live
from tests.headless import ORIGIN, _serve_static, chromium
from tests.test_kabaddi_premier_league import _generate, league  # noqa: F401
from tests.test_live_match import _tap
from tests.test_pkl_mode import _ok, _refused
from tests.test_sports_tournament import cup  # noqa: F401
from tests.test_tap_targets import PHONE

JERSEYS = ['7', '1', '3', '5', '9', '10', '11', '22', '33']
HOME = ['Arjun', 'Bharat', 'Chetan', 'Darshan', 'Eshwar', 'Farhan', 'Girish', 'Hemanth', 'Imran']
AWAY = ['Chandan', 'Deepak', 'Ganesh', 'Harish', 'Ishaan', 'Jeevan', 'Karthik', 'Lakshman', 'Mahesh']


def _roster(d, reg_id, names, numbers=JERSEYS):
    """A registered squad: the lead (captain) and the members, each with a jersey number."""
    d['db'].collection('registrations').document(reg_id).update({
        'lead_name': names[0], 'lead_jersey': numbers[0],
        'members': [{'name': n, 'jersey': j} for n, j in zip(names, numbers)]})


def _match(d, event_id, ids, home=HOME, away=AWAY):
    t = _generate(d, event_id, ids, rules='pkl12', scoring='pkl')
    m = t['matches'][0]
    _roster(d, m['home'], home)
    if away:
        _roster(d, m['away'], away)
    live._cache.clear()
    assert d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").status_code == 200
    return m


def _lineups(d, event_id, m, home=HOME[:7], away=AWAY[:7]):
    return _ok(d['coord'], event_id, m, op='lineup', home=home, away=away)


def _started(d, event_id, m, first='home'):
    _lineups(d, event_id, m)
    return _ok(d['coord'], event_id, m, op='phase', action='start', first=first)


def _players(data, side):
    p = data['state']['mat']['players'][side]
    return ([x['name'] for x in p['on']], [x['name'] for x in p['out']], [x['name'] for x in p['bench']])


def _raid(d, event_id, m, **body):
    return _ok(d['coord'], event_id, m, op='raid', **body)


# ── UPG-417: the line-ups ─────────────────────────────────────────────────────

def test_the_scorer_taps_each_teams_seven_before_the_start(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    page = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    picker = re.search(r'<div class="pkl-lineup" data-lineup>.*?data-lineup-save', page, re.S).group(0)
    buttons = re.findall(r'<button[^>]*data-lineup-pick[^>]*data-side="(\w+)" data-name="([^"]+)"[^>]*>(.*?)</button>',
                         picker, re.S)
    assert [(s, n) for s, n, _ in buttons] == [('home', n) for n in HOME] + [('away', n) for n in AWAY]
    arjun = next(html for s, n, html in buttons if n == 'Arjun')
    assert '#7' in arjun and 'Arjun' in arjun                          # the jersey number and the name
    assert '<select' not in picker                                     # buttons, not a list

    data = _lineups(d, event_id, m)
    lineup = data['state']['lineup']
    assert [p['name'] for p in lineup['home']['start']] == HOME[:7]
    assert [p['name'] for p in lineup['home']['subs']] == HOME[7:]   # the rest are the substitutes
    assert lineup['away']['start'][0] == {'name': 'Chandan', 'jersey': '7'}
    assert lineup['away']['subs'] == [{'name': 'Lakshman', 'jersey': '22'}, {'name': 'Mahesh', 'jersey': '33'}]
    assert 'data-lineup-saved' in data['panel']

    # Changed before the start: the last one saved counts
    data = _lineups(d, event_id, m, home=HOME[2:])
    assert [p['name'] for p in data['state']['lineup']['home']['subs']] == HOME[:2]


def test_a_match_with_two_full_squads_starts_only_with_both_line_ups(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _refused(d['coord'], event_id, m, "Choose each team's 7 players first", op='phase', action='start')
    _ok(d['coord'], event_id, m, op='lineup', home=HOME[:7])            # one team only
    _refused(d['coord'], event_id, m, "Choose each team's 7 players first", op='phase', action='start')
    _ok(d['coord'], event_id, m, op='lineup', away=AWAY[:7])
    data = _ok(d['coord'], event_id, m, op='phase', action='start', first='away')
    assert data['state']['phase'] == 'first_half' and data['state']['mat']['named'] is True
    assert data['state']['mat']['raider'] == 'away'


def test_a_team_short_of_seven_is_scored_by_count(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids, away=None)
    _roster(d, m['away'], AWAY[:5])
    live._cache.clear()
    page = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    assert 'data-lineup>' not in page
    data = _ok(d['coord'], event_id, m, op='phase', action='start')
    assert data['state']['mat']['named'] is False and data['state']['lineup'] is None
    data = _raid(d, event_id, m, team='home', outcome='touch', touches=2)   # by count, as before
    assert data['state']['mat']['on'] == {'home': 7, 'away': 5}
    assert 'data-touches="2"' in data['panel']


def test_a_line_up_is_seven_different_registered_players_until_the_start(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _refused(d['coord'], event_id, m, 'Choose 7 different players', op='lineup', home=HOME[:6], away=AWAY[:7])
    _refused(d['coord'], event_id, m, 'Choose 7 different players', op='lineup',
             home=HOME[:6] + ['Arjun'], away=AWAY[:7])
    _refused(d['coord'], event_id, m, "only the team's registered players", op='lineup',
             home=HOME[:6] + ['Chandan'], away=AWAY[:7])             # a player of the other team
    assert live.get(d['db'], event_id, m['id']).get('lineup') is None
    _started(d, event_id, m)
    _refused(d['coord'], event_id, m, 'The match has started', op='lineup', home=HOME[2:], away=AWAY[:7])


# ── UPG-404: the players on the mat and out, by name ──────────────────────────

def test_players_out_queue_up_and_come_back_first_out_first(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    # Arjun (#7) touches Ganesh and Ishaan: both out, in that order
    data = _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh', 'Ishaan'])
    on, out, bench = _players(data, 'away')
    assert out == ['Ganesh', 'Ishaan'] and len(on) == 5 and 'Ganesh' not in on
    assert bench == AWAY[7:]
    assert data['state']['mat']['on'] == {'home': 7, 'away': 5}
    # Chandan touches Bharat: Bharat out, and away's first out (Ganesh) comes back
    data = _raid(d, event_id, m, team='away', outcome='touch', raider='Chandan', touched=['Bharat'])
    on, out, _ = _players(data, 'away')
    assert out == ['Ishaan'] and on[-1] == 'Ganesh'
    assert _players(data, 'home')[1] == ['Bharat']
    # Chetan is tackled by Deepak: Chetan out behind Bharat, and Ishaan comes back for away
    data = _raid(d, event_id, m, team='home', outcome='tackled', raider='Chetan', touched=['Deepak'])
    assert _players(data, 'home')[1] == ['Bharat', 'Chetan'] and _players(data, 'away')[1] == []
    log = [e for e in live.get(d['db'], event_id, m['id'])['log'] if e['kind'] == 'tackle']
    assert log[-1]['player'] == 'Deepak'                                # the tackle is credited to him
    # Only the team that scores revives: away's empty raid brings nobody back, home's touch brings Bharat
    data = _raid(d, event_id, m, team='away', outcome='empty', raider='Ganesh')
    assert _players(data, 'home')[1] == ['Bharat', 'Chetan']
    data = _raid(d, event_id, m, team='home', outcome='touch', raider='Darshan', touched=['Deepak'])
    on, out, _ = _players(data, 'home')
    assert out == ['Chetan'] and on[-1] == 'Bharat'


def test_every_way_out_puts_out_the_right_player(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    # The raider out of court (home's Arjun)
    data = _raid(d, event_id, m, team='home', outcome='line_out', raider='Arjun')
    assert _players(data, 'home')[1] == ['Arjun']
    # Out of bounds: the player tapped (away's Deepak)
    data = _ok(d['coord'], event_id, m, op='call', kind='out_of_bounds', team='away', player='Deepak')
    assert _players(data, 'away')[1] == ['Deepak'] and _players(data, 'home')[1] == []    # Arjun revived
    _refused(d['coord'], event_id, m, 'Tap the player who stepped out', op='call', kind='out_of_bounds',
             team='away', player='Deepak')                              # he is out already
    # An empty do-or-die raid: the raider out (away raids now: empty, home empty, away empty, home empty, away DOD)
    for side, who in (('away', 'Chandan'), ('home', 'Bharat'), ('away', 'Chandan'), ('home', 'Bharat')):
        _raid(d, event_id, m, team=side, outcome='empty', raider=who)
    data = _raid(d, event_id, m, team='away', outcome='empty', raider='Ganesh')
    assert data['state']['mat']['empty']['away'] == 0
    assert _players(data, 'away')[1] == ['Deepak', 'Ganesh']
    # −1 on the mat names the player who goes off
    data = _ok(d['coord'], event_id, m, op='call', kind='mat', team='home', change=-1, player='Girish')
    assert _players(data, 'home')[1][-1] == 'Girish'


def test_an_all_out_brings_all_seven_back(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    data = _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=AWAY[:4])
    assert _players(data, 'away')[1] == AWAY[:4]
    _raid(d, event_id, m, team='away', outcome='empty', raider='Ishaan')
    data = _raid(d, event_id, m, team='home', outcome='touch', raider='Bharat', touched=AWAY[4:7])
    on, out, _ = _players(data, 'away')
    assert out == [] and sorted(on) == sorted(AWAY[:7])
    assert data['state']['mat']['all_outs']['home'] == 1


def test_a_substitute_takes_a_place_on_the_mat_or_in_the_out_queue(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    # Away's Lakshman (#22) for Ganesh (#3), who is out: Lakshman waits in his place
    data = _ok(d['coord'], event_id, m, op='call', kind='sub', team='away', off='Ganesh', on='Lakshman')
    on, out, bench = _players(data, 'away')
    assert out == ['Lakshman'] and 'Ganesh' in bench and 'Lakshman' not in bench
    assert data['state']['recent'][0] == 'Substitution · Vajra: #22 Lakshman for #3 Ganesh'
    # Home's Hemanth (#22) for Darshan (#5), on the mat
    data = _ok(d['coord'], event_id, m, op='call', kind='sub', team='home', off='Darshan', on='Hemanth')
    on, out, bench = _players(data, 'home')
    assert on.index('Hemanth') == HOME.index('Darshan') and 'Darshan' in bench
    assert data['state']['recent'][0] == 'Substitution · Garuda Sena: #22 Hemanth for #5 Darshan'
    _refused(d['coord'], event_id, m, 'must be a substitute', op='call', kind='sub', team='home',
             off='Arjun', on='Bharat')
    _refused(d['coord'], event_id, m, 'must be one of the seven', op='call', kind='sub', team='home',
             off='Imran', on='Darshan')
    # Away's next point revives the substitute
    data = _raid(d, event_id, m, team='away', outcome='touch', raider='Chandan', touched=['Arjun'])
    assert 'Lakshman' in _players(data, 'away')[0]


def test_undo_and_remove_work_the_names_out_again(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'], tap='r1')
    _raid(d, event_id, m, team='away', outcome='touch', raider='Chandan', touched=['Bharat', 'Chetan'])
    data = _ok(d['coord'], event_id, m, op='undo')
    assert _players(data, 'home')[1] == [] and _players(data, 'away')[1] == ['Ganesh']
    data = _ok(d['coord'], event_id, m, op='remove', entry='r1')
    assert _players(data, 'away')[1] == [] and data['state']['mat']['on'] == {'home': 7, 'away': 7}


# ── UPG-420: the scorer taps the players ──────────────────────────────────────

def test_the_raid_panel_has_a_column_of_player_buttons_a_team(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    panel = _started(d, event_id, m)['panel']
    for side, role, names in (('home', 'raider', HOME[:7]), ('away', 'defender', AWAY[:7])):
        col = re.search(rf'<div class="pkl-col[^"]*" data-col="{side}">.*?(?=<div class="pkl-col pkl-col--|\Z)', panel,
                        re.S).group(0)
        found = re.findall(rf'data-mat-player data-side="{side}" data-name="([^"]+)" data-role="{role}">(.*?)</button>',
                           col, re.S)
        assert [n for n, _ in found] == names
        assert '#7' in found[0][1] and found[0][0] in found[0][1]
    assert 'data-pkl-raider' not in panel and 'data-pkl-tackler' not in panel and '<select' not in panel


def test_the_raider_tapped_shows_at_once_until_the_raid_is_recorded(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    data = _ok(d['coord'], event_id, m, op='raider', name='Bharat')
    assert data['state']['raiding_now'] == {'team': 'home', 'team_name': 'Garuda Sena', 'name': 'Bharat',
                                            'jersey': '1', 'tag': '#1 Bharat'}
    live._cache.clear()
    assert live.public_state(d['db'], event_id, m['id'])['raiding_now']['tag'] == '#1 Bharat'
    _refused(d['coord'], event_id, m, 'raider must be a player on the mat of the raiding team',
             op='raider', name='Chandan')
    # The raid needs no raider again: the one tapped is used, and then he is cleared
    data = _raid(d, event_id, m, team='home', outcome='touch', touched=['Ganesh'])
    assert data['state']['raiding_now'] is None
    assert data['state']['recent'][0].startswith('Raid · Garuda Sena (#1 Bharat): 1 touch')


def test_touch_points_are_the_defenders_tapped(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _refused(d['coord'], event_id, m, 'Tap the raider first', op='raid', team='home', outcome='touch',
             touched=['Ganesh'])
    _refused(d['coord'], event_id, m, 'Tap the defenders he touched', op='raid', team='home', outcome='touch',
             raider='Arjun')
    _refused(d['coord'], event_id, m, 'must be players on the mat', op='raid', team='home', outcome='touch',
             raider='Arjun', touched=['Ganesh', 'Lakshman'])            # a substitute isn't on the mat
    _refused(d['coord'], event_id, m, 'must be players on the mat', op='raid', team='home', outcome='touch',
             raider='Arjun', touched=['Ganesh', 'Ganesh'])
    data = _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh', 'Ishaan', 'Karthik'],
                 bonus=True)
    assert data['state']['home']['total'] == 4                         # 3 touches + the bonus
    assert data['state']['recent'][0] == ('Raid · Garuda Sena (#7 Arjun): 3 touches + bonus · +4 · '
                                          'out #3 Ganesh, #9 Ishaan, #11 Karthik')
    log = [e for e in live.get(d['db'], event_id, m['id'])['log'] if e['counts'] == 'raid']
    assert log[-1]['player'] == 'Arjun' and log[-1]['points'] == 4


def test_the_scorer_taps_players_in_a_phone_browser(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
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

        def tap(sel):
            page.click(sel)
            page.wait_for_function("() => document.querySelector('[data-live-scorer]').getAttribute('data-busy') === 'false'")

        # The line-ups: seven a side, by tapping
        for side, names in (('home', HOME[:7]), ('away', AWAY[:7])):
            for name in names:
                page.click(f'[data-lineup-pick][data-side="{side}"][data-name="{name}"]')
        assert page.text_content('[data-lineup-count="home"]').strip() == '7'
        page.click(f'[data-lineup-pick][data-side="home"][data-name="{HOME[7]}"]')    # an eighth is refused
        assert page.locator('[data-lineup-pick][data-side="home"].is-picked').count() == 7
        tap('[data-lineup-save]')
        page.wait_for_selector('[data-lineup-saved]')
        tap('[data-phase-action="start"]')
        page.wait_for_selector('[data-pkl-panel][data-named="true"] [data-mat-player][data-role="raider"]')

        # Tap the raider, two defenders, then "touch"
        tap('[data-mat-player][data-role="raider"][data-name="Arjun"]')
        assert live.get(d['db'], event_id, m['id'])['raiding_now']['name'] == 'Arjun'
        page.click('[data-mat-player][data-role="defender"][data-name="Ganesh"]')
        page.click('[data-mat-player][data-role="defender"][data-name="Ishaan"]')
        assert '2 touches' in page.text_content('[data-touch-button]')
        tap('[data-touch-button]')
        page.wait_for_selector('[data-pkl-panel][data-raider="away"]')
        assert page.text_content('[data-score="home"]').strip() == '2'
        assert page.locator('[data-out] [data-mat-player][data-side="away"]').count() == 2

        # A substitution: Substitution, the player going off, the substitute
        page.click('[data-tool="sub"][data-side="home"]')
        page.click('[data-mat-player][data-side="home"][data-name="Darshan"]')
        tap('[data-bench][data-side="home"][data-name="Hemanth"]')
        page.wait_for_selector('[data-mat-player][data-side="home"][data-name="Hemanth"]')
        assert not errors, errors
    finally:
        browser.close()
        p.stop()
    doc = live.get(d['db'], event_id, m['id'])
    raid = doc['events'][0]
    assert raid['raider'] == 'Arjun' and raid['touched'] == ['Ganesh', 'Ishaan'] and json.dumps(doc['mat'])
    assert doc['events'][1] == dict(doc['events'][1], type='sub', team='home', off='Darshan', on='Hemanth')


# ── UPG-421: the public match page leads with the score and the players ──────

def _public(d, path):
    live._cache.clear()
    resp = d['app'].test_client().get(path)
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _box(page, side, which):
    m = re.search(rf'data-box-{which}="{side}">(.*?)</div>', page, re.S)
    assert m, (side, which)
    return re.findall(r'data-chip="([^"]+)"><b>([^<]*)</b>', m.group(1))


def test_the_match_page_shows_the_score_then_the_players_in_and_out(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh', 'Ishaan'])
    path = f"/tournament/live/{event_id}/{m['id']}"
    page = _public(d, path)
    content = page[page.index('data-live-board'):]
    assert content.index('live-board--big') < content.index('data-mat-boxes-host') < content.index('data-feed')
    assert _box(page, 'away', 'out') == [('Ganesh', '3'), ('Ishaan', '9')]
    assert [n for n, _ in _box(page, 'away', 'on')] == ['Chandan', 'Deepak', 'Harish', 'Jeevan', 'Karthik']
    assert len(_box(page, 'home', 'on')) == 7 and _box(page, 'home', 'out') == []
    # Away scores: Ganesh, the first out, leaves the out box
    _raid(d, event_id, m, team='away', outcome='touch', raider='Chandan', touched=['Bharat'])
    page = _public(d, path)
    assert _box(page, 'away', 'out') == [('Ishaan', '9')] and ('Ganesh', '3') in _box(page, 'away', 'on')
    assert _box(page, 'home', 'out') == [('Bharat', '1')]


def test_the_match_page_says_who_is_raiding_and_each_raid_by_jersey(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh', 'Ishaan'])
    _ok(d['coord'], event_id, m, op='raider', name='Chandan')
    path = f"/tournament/live/{event_id}/{m['id']}"
    page = _public(d, path)
    now = re.search(r'data-raiding-line>(.*?)</p>', page, re.S).group(1)
    assert 'Raiding now' in now and '#7' in now and 'Chandan' in now and 'Vajra' in now
    assert 'mat-chip mat-chip--raiding" data-chip="Chandan"' in page
    state = d['app'].test_client().get(f"{path}/state").get_json()['state']
    assert state['feed'][0] == 'Garuda Sena · #7 Arjun · 2 touches +2 · out #3, #9'
    assert '<li>Garuda Sena · #7 Arjun · 2 touches +2 · out #3, #9</li>' in page
    _raid(d, event_id, m, team='away', outcome='tackled', touched=['Bharat'])
    live._cache.clear()
    state = d['app'].test_client().get(f"{path}/state").get_json()['state']
    assert state['feed'][0] == 'Vajra · #7 Chandan · tackled · tackle by #1 Bharat +1'
    assert state['raiding_now'] is None


def test_below_the_score_the_split_the_players_the_line_ups_and_the_tables(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    page = _public(d, f"/tournament/live/{event_id}/{m['id']}")
    order = [page.index(x) for x in ('data-mat-boxes-host', 'data-split>', 'data-match-players', 'data-lineups',
                                      'data-tables-link')]
    assert order == sorted(order)
    lineups = re.search(r'<section class="live-lineups" data-lineups>.*?</section>', page, re.S).group(0)
    start = re.search(r'data-lineup-start="home">(.*?)</ul>', lineups, re.S).group(1)
    assert start.count('<li>') == 7 and '#7</span> Arjun' in start
    subs = re.search(r'data-lineup-subs="away">(.*?)</ul>', lineups, re.S).group(1)
    assert '#22</span> Lakshman' in subs and '#33</span> Mahesh' in subs
    assert f'href="/tournament/fixtures/{event_id}#tables"' in page
    assert 'id="tables"' in _public(d, f'/tournament/fixtures/{event_id}')


def test_the_fixtures_page_and_the_big_screen_show_the_live_boards(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    page = _public(d, f'/tournament/fixtures/{event_id}')
    board = re.search(rf'<div class="live-mini" data-live-board data-live-mini="{m["id"]}".*?data-live-now-link', page,
                      re.S).group(0)
    assert page.index('data-live-mini') < page.index('id="tables"')                   # the live boards first
    assert f'data-url="/tournament/live/{event_id}/{m["id"]}/state"' in board
    assert re.search(r'data-score="home">1<', board) and _box(board, 'away', 'out') == [('Ganesh', '3')]
    screen = _public(d, f'/tournament/screen/{event_id}/body')
    tv = re.search(r'data-screen-boxes>(.*?)</section>\s*</div>\s*</div>', screen, re.S).group(0)
    assert _box(tv, 'away', 'out') == [('Ganesh', '3')] and len(_box(tv, 'home', 'on')) == 7


def test_the_boxes_and_the_raids_update_by_themselves(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    path = f"/tournament/live/{event_id}/{m['id']}"
    p, browser = chromium()
    try:
        page = browser.new_context(viewport=PHONE).new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        def handle(route):
            req_path = urlparse(route.request.url).path
            if req_path in (path, f'{path}/state'):
                live._cache.clear()
                resp = d['app'].test_client().get(req_path)
                return route.fulfill(status=resp.status_code, body=resp.get_data(),
                                     headers={'Content-Type': resp.content_type})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        assert page.locator('[data-box-out="away"] [data-chip]').count() == 0
        _ok(d['coord'], event_id, m, op='raider', name='Arjun')
        page.wait_for_selector('[data-raiding-line]:has-text("Arjun")', timeout=6000)
        _raid(d, event_id, m, team='home', outcome='touch', touched=['Ganesh', 'Ishaan'])
        page.wait_for_selector('[data-box-out="away"] [data-chip="Ishaan"]', timeout=6000)
        assert page.locator('[data-box-out="away"] [data-chip]').count() == 2
        assert page.text_content('[data-score="home"]').strip() == '2'
        assert 'Garuda Sena · #7 Arjun · 2 touches +2 · out #3, #9' in page.text_content('[data-feed]')
        _raid(d, event_id, m, team='away', outcome='touch', raider='Chandan', touched=['Bharat'])
        page.wait_for_selector('[data-box-out="home"] [data-chip="Bharat"]', timeout=6000)
        assert page.locator('[data-box-out="away"] [data-chip="Ganesh"]').count() == 0       # revived
        assert page.locator('[data-box-on="away"] [data-chip="Ganesh"]').count() == 1
        assert not errors, errors
    finally:
        browser.close()
        p.stop()


# ── UPG-422: the player of the match ──────────────────────────────────────────

def _potm_doc(winner, *rows):
    log = [{'team': side, 'player': who, 'counts': counts, 'points': pts} for side, who, counts, pts in rows]
    return {'home': 'H', 'away': 'A', 'result': {'winner': winner}, 'log': log}


def test_full_time_names_the_player_with_the_most_points():
    pick = live.player_of_the_match
    # The most points, raid and tackle
    assert pick(_potm_doc('H', ('home', 'Arjun', 'raid', 5), ('away', 'Chandan', 'raid', 3),
                          ('away', 'Chandan', 'tackle', 1)))['name'] == 'Arjun'
    assert pick(_potm_doc('H', ('home', 'Arjun', 'raid', 3), ('away', 'Chandan', 'raid', 2),
                          ('away', 'Chandan', 'tackle', 2)))['name'] == 'Chandan'     # 4 beats 3, even losing
    # Level: the winning team's player
    assert pick(_potm_doc('A', ('home', 'Arjun', 'raid', 4), ('away', 'Chandan', 'tackle', 2),
                          ('away', 'Chandan', 'raid', 2))) == {'team': 'away', 'name': 'Chandan', 'chosen': False}
    # Level in the same team: more raid points
    assert pick(_potm_doc('A', ('away', 'Chandan', 'raid', 2), ('away', 'Chandan', 'tackle', 2),
                          ('away', 'Deepak', 'raid', 4)))['name'] == 'Deepak'
    assert pick(_potm_doc('A')) is None                                   # nobody named on a point


def _to_full_time(d, event_id, m):
    for action in ('half_time', 'second_half'):
        _ok(d['coord'], event_id, m, op='phase', action=action)
    return _ok(d['coord'], event_id, m, op='phase', action='full_time')


def test_the_scorer_names_another_player_of_the_match_after_full_time(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh', 'Ishaan'])
    _raid(d, event_id, m, team='away', outcome='tackled', raider='Chandan', touched=['Bharat'])
    _refused(d['coord'], event_id, m, 'named at full time', op='potm', team='away', name='Chandan')
    data = _to_full_time(d, event_id, m)
    pm = data['state']['potm']
    assert (pm['name'], pm['tag'], pm['points'], pm['chosen']) == ('Arjun', '#7 Arjun', 2, False)
    panel = re.search(r'<section class="pkl-panel" data-potm>.*?</section>', data['panel'], re.S).group(0)
    assert 'is-picked" data-potm-pick data-side="home" data-name="Arjun"' in panel
    assert panel.count('data-potm-pick') == len(HOME) + len(AWAY)
    # The scorer taps Bharat (one tackle point) instead
    data = _ok(d['coord'], event_id, m, op='potm', team='home', name='Bharat')
    assert data['state']['potm']['name'] == 'Bharat' and data['state']['potm']['chosen'] is True
    _refused(d['coord'], event_id, m, 'Choose a player of one of the two teams', op='potm', team='home',
             name='Chandan')
    # Reopened and ended again: the scorer's choice stays
    _ok(d['coord'], event_id, m, op='reopen')
    data = _ok(d['coord'], event_id, m, op='phase', action='full_time')
    assert data['state']['potm']['name'] == 'Bharat'


def test_the_player_of_the_match_shows_on_the_match_page(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh', 'Ishaan'])
    path = f"/tournament/live/{event_id}/{m['id']}"
    assert re.search(r'data-potm-line hidden', _public(d, path))           # not before full time
    _to_full_time(d, event_id, m)
    page = _public(d, path)
    line = re.search(r'<p class="live-potm" data-potm-line >(.*?)</p>', page, re.S).group(1)
    assert 'Player of the match' in line and '#7 Arjun' in line and 'Garuda Sena' in line and '2 points' in line


# ── UPG-419: the score sheet ──────────────────────────────────────────────────

def _pdf_text(data):
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(data)
    try:
        return '\n'.join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    finally:
        doc.close()


def _sheet(d, event_id, m):
    live._cache.clear()
    resp = d['app'].test_client().get(f"/tournament/live/{event_id}/{m['id']}/sheet.pdf")   # no login
    assert resp.status_code == 200 and resp.mimetype == 'application/pdf', resp.status_code
    return ' '.join(_pdf_text(resp.data).split())


def test_anyone_downloads_the_score_sheet_once_the_match_has_started(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    path = f"/tournament/live/{event_id}/{m['id']}"
    assert d['app'].test_client().get(f'{path}/sheet.pdf').status_code == 404          # not started
    assert re.search(r'data-sheet-link[^>]*hidden', _public(d, path))
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    text = _sheet(d, event_id, m)
    assert 'PROVISIONAL' in text
    page = _public(d, path)
    assert re.search(rf'<a href="{path}/sheet.pdf"[^>]*data-sheet-link[^>]*>', page)
    assert not re.search(r'data-sheet-link[^>]*hidden', page) and '· provisional' in page
    scorer = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    assert f'href="{path}/sheet.pdf"' in scorer                                       # the scorer's page links it
    _to_full_time(d, event_id, m)
    assert 'PROVISIONAL' not in _sheet(d, event_id, m)


def test_the_score_sheet_has_the_match_the_line_ups_and_the_points(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    t = d['db'].collection('events').document(event_id).get().to_dict()['tournament']
    t['matches'][0].update(venue='Main Ground', date='2026-11-24', time='10:00')
    d['db'].collection('events').document(event_id).update({'tournament': t})
    _started(d, event_id, m, first='away')
    _raid(d, event_id, m, team='away', outcome='touch', raider='Chandan', touched=['Bharat', 'Chetan'])
    _ok(d['coord'], event_id, m, op='call', kind='timeout', team='home')
    _ok(d['coord'], event_id, m, op='phase', action='resume')
    _ok(d['coord'], event_id, m, op='call', kind='review', team='home', upheld=True)
    _raid(d, event_id, m, team='home', outcome='tackled', raider='Arjun', touched=['Deepak'])
    _ok(d['coord'], event_id, m, op='phase', action='half_time')
    _ok(d['coord'], event_id, m, op='phase', action='second_half')
    _raid(d, event_id, m, team='home', outcome='touch', raider='Darshan', touched=AWAY[1:7])   # 6 out
    _ok(d['coord'], event_id, m, op='call', kind='sub', team='home', off='Eshwar', on='Hemanth')
    _ok(d['coord'], event_id, m, op='phase', action='full_time')
    text = _sheet(d, event_id, m)
    title = d['db'].collection('events').document(event_id).get().to_dict()['title']
    for needle in (title, 'Score sheet', 'M-01', 'Pool A', '2026-11-24 10:00', 'Main Ground', 'Garuda Sena', 'Vajra',
                   'Raided first: Vajra', 'Result: Garuda Sena won', 'Points by half', 'Raid points', 'Tackle points',
                   'All outs and extras', 'All outs (times)', 'Time-outs', 'Reviews (upheld)', 'Total',
                   'Line-ups', 'Starting seven: #7 Arjun, #1 Bharat', 'Substitutes: #22 Lakshman, #33 Mahesh',
                   'Player of the match: #5 Darshan', "Players' points", 'Scorer', 'Umpire 1', 'Umpire 2', 'Referee'):
        assert needle in text, needle
    assert re.search(r'Garuda Sena \d+ – Vajra|Garuda Sena won \d+–\d+', text)
    assert 'Tie-breaker' not in text


def test_the_score_sheet_has_the_tie_breaker(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    _started(d, event_id, m)
    _raid(d, event_id, m, team='home', outcome='touch', raider='Arjun', touched=['Ganesh'])
    _raid(d, event_id, m, team='away', outcome='touch', raider='Chandan', touched=['Bharat'])
    _ok(d['coord'], event_id, m, op='phase', action='half_time')
    _ok(d['coord'], event_id, m, op='phase', action='second_half')
    data = _ok(d['coord'], event_id, m, op='phase', action='full_time')
    assert data['state']['phase'] == 'tiebreak'
    for _ in range(12):
        sh = data['state']['shootout']
        if sh['done']:
            break
        side = sh['next'] or 'home'
        data = _ok(d['coord'], event_id, m, op='shootout', team=side,
                   outcome='touch' if side == 'home' else 'empty', touches=1)
    _ok(d['coord'], event_id, m, op='phase', action='full_time')
    text = _sheet(d, event_id, m)
    assert 'Tie-breaker' in text and 'Garuda Sena won the shootout' in text


# ── UPG-425: the points table's key ───────────────────────────────────────────

def test_the_table_key_says_what_the_letters_mean_and_why_no_rate():
    import services_sports as sports
    k = sports.table_key({'sport': 'Kabaddi', 'points': sports.PKL12_POINTS})
    meaning = dict(k['letters'])
    assert list(meaning) == ['P', 'W', 'T', 'L', 'SD', 'Pts']
    assert meaning['SD'] == 'score difference (points scored minus points conceded)'
    assert 'a win 2, a loss 0' in meaning['Pts'] and 'tie-breaker' in meaning['Pts']
    assert k['order'].startswith('Most points first; level on points, the bigger score difference, then more points scored')
    assert '40 minutes' in k['why'] and 'net run rate' in k['why']
    assert k['line'] == 'P played · W won · T tied · L lost · SD score difference · Pts points'
    old = sports.table_key({'sport': 'Kabaddi', 'points': sports.KABADDI_POINTS})
    assert '1 if lost by 7 or fewer' in dict(old['letters'])['Pts']
    foot = sports.table_key({'sport': 'Football'})
    assert [a for a, _ in foot['letters']] == ['P', 'W', 'D', 'L', 'GD', 'Pts'] and not foot['why']


def test_the_public_spoc_and_big_screen_tables_have_the_key(league):  # noqa: F811
    d, event_id, ids = league
    _match(d, event_id, ids)                                                        # the fixtures are made
    public = _public(d, f'/tournament/fixtures/{event_id}')
    key = public[public.index('data-table-key'):]
    for needle in ('<dt>P</dt><dd>played</dd>', '<dt>T</dt><dd>tied</dd>', '<dt>SD</dt>',
                   'points scored minus points conceded', 'data-table-order', 'Most points first', '40 minutes'):
        assert needle in key, needle
    assert public.index('data-pool-table') < public.index('data-table-key')       # under the tables
    spoc = d['coord'].get(f'/tournament/{event_id}').get_data(as_text=True)
    key = spoc[spoc.index('data-table-key'):]
    assert '<dt>PF</dt><dd>points scored</dd>' in key and '<dt>PA</dt>' in key and 'Most points first' in key
    screen = _public(d, f'/tournament/screen/{event_id}')
    assert re.search(r'class="tv-table-key" data-table-key>P played · W won · T tied · L lost · SD score difference · Pts points<', screen)


# ── UPG-424: find a player, and the profile ──────────────────────────────────

def _people(d, reg_id, names, tag, extra=None):
    """A squad whose players have emails: a player is the same person across events by email."""
    members = [dict({'name': n, 'jersey': j, 'email': f"{n.split()[0].lower()}.{tag}@players.test.edu",
                     'role': 'Lead' if i == 0 else 'Member'}, **((extra or {}).get(n) or {}))
               for i, (n, j) in enumerate(zip(names, JERSEYS))]
    d['db'].collection('registrations').document(reg_id).update({
        'lead_name': names[0], 'lead_email': members[0]['email'], 'lead_jersey': JERSEYS[0], 'members': members})
    return {m['name']: m['email'] for m in members}


def _fresh_index():
    import services_players
    services_players._cache.clear()
    live._cache.clear()


def _codes(page):
    return re.findall(r'href="/players/([0-9a-f]{16})"', page)


def _named_match(d, event_id, ids):
    """A match whose players have unique names (the test database keeps other tests' events)."""
    import uuid
    tag = uuid.uuid4().hex[:6]
    home, away = [f'{n} Q{tag}' for n in HOME], [f'{n} Q{tag}' for n in AWAY]
    m = _match(d, event_id, ids, home=home, away=away)
    emails = _people(d, m['home'], home, tag, extra={home[0]: {
        'dob': '2004-03-09', 'position': 'Raider', 'usn': '1SN22CS777', 'phone': '9000011111'}})
    emails.update(_people(d, m['away'], away, tag))
    _fresh_index()
    return m, tag, home, away, emails


def test_anyone_finds_a_player_by_part_of_the_name_in_any_case(league):  # noqa: F811
    d, event_id, ids = league
    m, tag, home, away, _ = _named_match(d, event_id, ids)
    page = _public(d, f'/players?q=ARJUN+Q{tag.upper()}')                  # no login, any case
    assert len(_codes(page)) == 1 and home[0] in page and '#7' in page and 'Raider' in page
    page = _public(d, f'/players?q=rjun+q{tag}')                            # part of it
    assert len(_codes(page)) == 1
    page = _public(d, f'/players?q=q{tag}')                                  # every player of both teams
    assert len(_codes(page)) == 18
    assert 'data-player-hint' in _public(d, '/players?q=a')                 # too short
    assert 'data-player-none' in _public(d, f'/players?q=nobody+q{tag}')
    # A private event's players aren't found
    d['db'].collection('events').document(event_id).update({'visibility': 'Private'})
    _fresh_index()
    assert _codes(_public(d, f'/players?q=q{tag}')) == []


def test_the_profile_shows_the_player_match_by_match_and_never_the_private_details(league):  # noqa: F811
    from routes_forms import age_on
    d, event_id, ids = league
    m, tag, home, away, emails = _named_match(d, event_id, ids)
    _lineups(d, event_id, m, home=home[:7], away=away[:7])
    _ok(d['coord'], event_id, m, op='phase', action='start', first='home')
    _raid(d, event_id, m, team='home', outcome='touch', raider=home[0], touched=away[:2])        # +2
    _raid(d, event_id, m, team='away', outcome='tackled', raider=away[2], tackler=home[1])        # +1
    for action in ('half_time', 'second_half', 'full_time'):
        _ok(d['coord'], event_id, m, op='phase', action=action)
    _fresh_index()
    [code] = _codes(_public(d, f'/players?q=arjun+q{tag}'))
    assert '@' not in code and emails[home[0]] not in code
    page = _public(d, f'/players/{code}')
    t = d['db'].collection('events').document(event_id).get().to_dict()['tournament']
    names = {x['id']: x['name'] for x in t['teams']}
    assert home[0] in page and names[m['home']] in page and '#7' in page
    assert re.search(r'data-player-position>Raider<', page)
    assert re.search(rf'data-player-age>{age_on("2004-03-09")}<', page)
    for secret in ('2004-03-09', emails[home[0]], '1SN22CS777', '9000011111'):                  # never shown
        assert secret not in page, secret
    row = re.search(rf'<tr data-player-match="{m["id"]}">.*?</tr>', page, re.S).group(0)
    assert names[m['away']] in row and 'Won' in row and 'M-01' in row and 'data-potm-badge' in row
    assert re.findall(r'<td>(\d+)</td>', row)[:2] == ['2', '0']                                  # raid 2, tackle 0
    career = dict(re.findall(r'data-stat="(\w+)"><b>(\d+)</b>', page))
    assert career['matches'] == '1' and career['raid'] == '2' and career['successful_raids'] == '1'
    assert career['potm'] == '1' and 'Player of the match · M-01' in page
    assert d['app'].test_client().get('/players/0000000000000000').status_code == 404

    # The fixtures page and the match page link the names, and have the search box
    fixtures = _public(d, f'/tournament/fixtures/{event_id}')
    assert f'href="/players/{code}"' in fixtures and 'data-player-search' in fixtures
    match_page = _public(d, f"/tournament/live/{event_id}/{m['id']}")
    lineup = re.search(r'data-lineup-start="home">(.*?)</ul>', match_page, re.S).group(1)
    assert f'href="/players/{code}"' in lineup and 'data-player-search' in match_page
    assert f'href="/players/{code}"' in match_page.split('data-match-players')[1]                # who scored


def test_a_player_is_one_person_across_events_with_the_achievements(league):  # noqa: F811
    d, event_id, ids = league
    m, tag, home, away, emails = _named_match(d, event_id, ids)
    _lineups(d, event_id, m, home=home[:7], away=away[:7])
    _ok(d['coord'], event_id, m, op='phase', action='start', first='home')
    _raid(d, event_id, m, team='home', outcome='touch', raider=home[0], touched=away[:1])        # +1 here
    # A second, finished tournament: the same email, a new team and another spelling of the name
    db = d['db']
    import uuid
    hawks, owls, cup_id = (str(uuid.uuid4()) for _ in range(3))      # the database's own kind of id
    arjun, owl = f'A. Arjun Q{tag}', f'Owl Raider Q{tag}'
    db.collection('events').document(cup_id).set({
        'title': f'Winter Cup {tag}', 'category': 'Sports', 'event_type': 'sports_tournament', 'status': 'completed',
        'date': '2099-01-10', 'tournament': {'sport': 'Kabaddi', 'format': 'knockout', 'teams': [
            {'id': hawks, 'name': 'Hawks'}, {'id': owls, 'name': 'Owls'}], 'matches': [
            {'id': 'm1', 'home': hawks, 'away': owls, 'stage': 'final', 'round': 1, 'status': 'played',
             'home_score': 40, 'away_score': 30, 'winner': hawks}]}})
    db.collection('registrations').document(hawks).set({'event_id': cup_id, 'team_name': 'Hawks', 'members': [
        {'name': arjun, 'email': emails[home[0]].upper(), 'jersey': '10', 'role': 'Lead'}]})
    db.collection('registrations').document(owls).set({'event_id': cup_id, 'team_name': 'Owls', 'members': [
        {'name': owl, 'email': f'owl.{tag}@players.test.edu', 'jersey': '4', 'role': 'Lead'}]})

    def e(i, kind, counts, pts, label, player, side='home', **more):
        return dict({'id': f'e{i}#0', 'event': f'e{i}', 'team': side, 'kind': kind, 'counts': counts,
                     'points': pts, 'label': label, 'player': player, 'half': 1}, **more)
    log = [e(1, 'raid', 'raid', 2, 'Raid', arjun), e(2, 'raid', 'raid', 2, 'Raid', arjun),
           e(3, 'raid', 'raid', 3, 'Super raid', arjun, dod=True), e(4, 'bonus', 'raid', 1, 'Bonus', arjun),
           e(5, 'raid', 'raid', 2, 'Raid', arjun),                                                # 10 raid points
           e(6, 'tackle', 'tackle', 1, 'Tackle', arjun), e(7, 'tackle', 'tackle', 1, 'Tackle', arjun),
           e(8, 'tackle', 'tackle', 1, 'Tackle', arjun), e(9, 'super_tackle', 'tackle', 2, 'Super tackle', arjun),
           e(10, 'raid', 'raid', 4, 'Super raid', owl, side='away')]
    db.collection(live.COLLECTION).document(live.doc_id(cup_id, 'm1')).set({
        'event_id': cup_id, 'match_id': 'm1', 'home': hawks, 'away': owls, 'phase': 'full_time', 'log': log,
        'potm': {'team': 'home', 'name': arjun, 'chosen': False}})
    _fresh_index()

    [code] = _codes(_public(d, f'/players?q=arjun+q{tag}'))                 # one person, two events
    page = _public(d, f'/players/{code}')
    assert f'data-player-event="{event_id}"' in page and f'data-player-event="{cup_id}"' in page
    assert '<h2 class="player-card__name">' + arjun in page and 'Hawks' in page   # the latest event's name and team
    cup = page.split(f'data-player-event="{cup_id}"')[1].split('data-player-event=')[0]
    stats = dict(re.findall(r'data-event-stat="(\w+)"><b>(\d+)</b>', cup))
    assert stats == {'matches': '1', 'total': '15', 'raid': '10', 'tackle': '5', 'successful_raids': '5',
                     'super_raids': '1', 'tackles': '4', 'super_tackles': '1', 'do_or_die': '3', 'super_10': '1',
                     'high_5': '1', 'potm': '1'}
    career = dict(re.findall(r'data-stat="(\w+)"><b>(\d+)</b>', page))
    assert career['raid'] == '11' and career['matches'] == '2'
    awards = re.findall(r'data-award="(\w+)"', page)
    for kind in ('champion', 'top_raid', 'top_tackle', 'potm', 'super_10', 'high_5'):
        assert kind in awards, kind
    assert f'Champion · Winter Cup {tag}' in page and f'Top raider · Winter Cup {tag} · 10 points' in page
    assert 'Super 10 · 10 raid points · M-01' in page and 'High 5 · 5 tackle points · M-01' in page
    [owl_code] = _codes(_public(d, f'/players?q=owl+raider+q{tag}'))
    assert f'Runner-up · Winter Cup {tag}' in _public(d, f'/players/{owl_code}')
    assert 'top_raid' not in re.findall(r'data-award="(\w+)"', _public(d, f'/players/{owl_code}'))


def test_the_scorers_steps_say_how_to_score_with_line_ups(league):  # noqa: F811
    d, event_id, ids = league
    m = _match(d, event_id, ids)
    page = d['coord'].get(f"/tournament/{event_id}/match/{m['id']}/score").get_data(as_text=True)
    howto = page[page.index('data-howto'):page.index('</details>', page.index('data-howto'))]
    for needle in ('seven', 'Save line-ups', 'who raids first', 'tap the raider', 'tap each defender he touched',
                   'Touch points', 'Substitution', 'Empty raid', 'Undo last', 'Full time: save the result',
                   'tie-breaker', "Only this event's SPOC and its coordinators can score"):
        assert needle in howto, needle
    # A team short of seven: the steps without line-ups, as before
    t = d['db'].collection('events').document(event_id).get().to_dict()['tournament']
    other = next(x for x in t['matches'] if x['id'] != m['id'] and m['home'] not in (x['home'], x['away'])
                 and m['away'] not in (x['home'], x['away']))
    live._cache.clear()
    page = d['coord'].get(f"/tournament/{event_id}/match/{other['id']}/score").get_data(as_text=True)
    howto = page[page.index('data-howto'):page.index('</details>', page.index('data-howto'))]
    assert 'pick the raider' in howto and 'Save line-ups' not in howto
