"""
tests/test_kabaddi_premier_league.py — UPG-381 to UPG-386: a kabaddi premier
league like the owner's "Sapthagiri Kabaddi Premier League" sheet: 8 teams in
two pools, each pool a double league (home and away), an inter-pool round
(A1 v B1 … A4 v B4) whose points count in each team's own pool table, then
1st A v 2nd B and 1st B v 2nd A in the semi-finals and a final, 31 matches
numbered M-01 to M-31; the schedule from one file; a logo for each team.
"""
import csv
import io
import re

import pytest
from PIL import Image

import services_sports as sports
from tests.test_sports_tournament import _play, _t, cup  # noqa: F401

POOL_A = ['Garuda Sena', 'Malnad Fighters', 'Neuro Ninjas', 'Vajra']
POOL_B = ['Gaja Pade', 'Code Blue', 'Veera Yodha', 'Gandaberunda Warriors']

# The owner's printed fixture sheet, M-01 to M-28 (team 1 v team 2)
SHEET = [
    ('Garuda Sena', 'Vajra'), ('Malnad Fighters', 'Neuro Ninjas'), ('Garuda Sena', 'Neuro Ninjas'),
    ('Vajra', 'Malnad Fighters'), ('Garuda Sena', 'Malnad Fighters'), ('Neuro Ninjas', 'Vajra'),
    ('Vajra', 'Garuda Sena'), ('Neuro Ninjas', 'Malnad Fighters'), ('Neuro Ninjas', 'Garuda Sena'),
    ('Malnad Fighters', 'Vajra'), ('Malnad Fighters', 'Garuda Sena'), ('Vajra', 'Neuro Ninjas'),
    ('Gaja Pade', 'Gandaberunda Warriors'), ('Code Blue', 'Veera Yodha'), ('Gaja Pade', 'Veera Yodha'),
    ('Gandaberunda Warriors', 'Code Blue'), ('Gaja Pade', 'Code Blue'), ('Veera Yodha', 'Gandaberunda Warriors'),
    ('Gandaberunda Warriors', 'Gaja Pade'), ('Veera Yodha', 'Code Blue'), ('Veera Yodha', 'Gaja Pade'),
    ('Code Blue', 'Gandaberunda Warriors'), ('Code Blue', 'Gaja Pade'), ('Gandaberunda Warriors', 'Veera Yodha'),
    ('Garuda Sena', 'Gaja Pade'), ('Malnad Fighters', 'Code Blue'), ('Neuro Ninjas', 'Veera Yodha'),
    ('Vajra', 'Gandaberunda Warriors'),
]


def _form(ids, **extra):
    data = {'format': 'league_knockout', 'points_win': '5', 'points_draw': '3', 'points_loss': '0',
            'points_close_loss': '1', 'points_close_margin': '7', 'legs': '2', 'pools': 'two', 'cross': 'yes'}
    for pool, members in (('A', POOL_A), ('B', POOL_B)):
        for seed, name in enumerate(members, start=1):
            data[f'pool_{ids[name]}'], data[f'seed_{ids[name]}'] = pool, str(seed)
    data.update(extra)
    return data


@pytest.fixture
def league(cup):  # noqa: F811
    d = cup
    event_id, ids = d['event'](POOL_A + POOL_B)
    d['db'].collection('events').document(event_id).update(
        {'details': {'sport': 'Kabaddi', 'format': 'League then knockout', 'gender': 'Men'}})
    return d, event_id, ids


def _generate(d, event_id, ids, **extra):
    resp = d['owner'].post(f'/tournament/{event_id}/generate', data=_form(ids, **extra))
    assert resp.status_code == 302
    return _t(d, event_id)


# ── UPG-381 to UPG-383: two pools, home and away, the inter-pool round ────────

def test_the_owners_sheet_comes_out_match_for_match(league):
    d, event_id, ids = league
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'name="pools"' in page and 'Two pools, A and B' in page and 'Twice: home and away' in page
    assert 'data-pools-fields' in page and f'name="seed_{ids["Vajra"]}"' in page

    t = _generate(d, event_id, ids)
    name = sports.names(t)
    assert t['pools'] == ['A', 'B'] and t['legs'] == 2 and t['cross'] is True
    assert len(t['matches']) == 28
    assert [(name[m['home']], name[m['away']]) for m in t['matches']] == SHEET
    assert [sports.match_no(m) for m in t['matches']][:2] == ['M-01', 'M-02'] and sports.match_no(t['matches'][-1]) == 'M-28'
    assert {x['name']: f"{x['pool']}{x['seed']}" for x in t['teams']}['Gandaberunda Warriors'] == 'B4'
    for team in t['teams']:                                   # 6 in the pool + 1 inter-pool
        played = [m for m in t['matches'] if team['id'] in (m['home'], m['away'])]
        assert len(played) == 7 and sum(1 for m in played if m.get('cross')) == 1
    assert sports.stage_name(t['matches'][6]) == 'Pool A · Leg 2 · Round 4'
    assert sports.stage_name(t['matches'][24]) == 'Inter-pool'
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert 'M-01 · Pool A · Leg 1 · Round 1' in page and 'M-25 · Inter-pool' in page


def test_the_inter_pool_round_counts_in_each_teams_own_pool_table(league):
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    cross = next(m for m in t['matches'] if m.get('cross') and m['home'] == ids['Garuda Sena'])
    _play(d['owner'], event_id, cross, 32, 28)                 # Garuda Sena beat Gaja Pade by 4
    tables = dict(sports.pool_tables(_t(d, event_id)))
    assert [r['name'] for r in tables['A']][0] == 'Garuda Sena' and len(tables['A']) == 4
    gaja = next(r for r in tables['B'] if r['name'] == 'Gaja Pade')
    garuda = next(r for r in tables['A'] if r['name'] == 'Garuda Sena')
    assert (garuda['points'], garuda['played']) == (5, 1)
    assert (gaja['points'], gaja['played'], gaja['lost']) == (1, 1, 1)        # a loss by 7 or fewer: 1
    assert all(r['name'] in POOL_A for r in tables['A']) and all(r['name'] in POOL_B for r in tables['B'])
    for url in (f'/tournament/{event_id}', f'/tournament/fixtures/{event_id}', f'/event/{event_id}'):
        page = d['owner'].get(url).get_data(as_text=True)
        assert 'data-pool-table="A"' in page and 'data-pool-table="B"' in page, url


def test_home_and_away_without_pools_plays_every_pair_twice(cup):  # noqa: F811
    d = cup
    event_id, _ids = d['event'](['Ants', 'Bees', 'Cats', 'Dogs'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'league', 'legs': '2'})
    t = _t(d, event_id)
    pairs = [(m['home'], m['away']) for m in t['matches']]
    assert len(pairs) == 12 and len(set(pairs)) == 12
    assert all((away, home) in pairs for home, away in pairs)       # each pair, home and away
    assert max(m['round'] for m in t['matches']) == 6


@pytest.mark.parametrize('change, message', [
    ({'format': 'league'}, 'Pools need the format League then knockout'),
    ({'seed_dup': True}, 'the same seed number'),
    ({'one_pool': True}, 'Pool B needs at least 2 teams'),
])
def test_pools_set_up_wrongly_are_refused_in_words(league, change, message):
    d, event_id, ids = league
    extra = {k: v for k, v in change.items() if k == 'format'}
    data = _form(ids, **extra)
    if change.get('seed_dup'):
        data[f'seed_{ids["Vajra"]}'] = '1'
    if change.get('one_pool'):
        for seed, n in enumerate(POOL_B[:3], start=5):
            data[f'pool_{ids[n]}'], data[f'seed_{ids[n]}'] = 'A', str(seed)
    page = d['owner'].post(f'/tournament/{event_id}/generate', data=data, follow_redirects=True).get_data(as_text=True)
    assert message in page
    assert not _t(d, event_id)


# ── UPG-384: 1st A v 2nd B, 1st B v 2nd A ────────────────────────────────────

def test_the_semi_finals_cross_the_pools_and_the_final_decides_the_places(league):
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    rank = {n: i for i, n in enumerate(POOL_A + POOL_B)}            # the earlier seed wins every match
    for m in t['matches']:
        name = sports.names(t)
        home_wins = rank[name[m['home']]] % 4 < rank[name[m['away']]] % 4 or (
            rank[name[m['home']]] % 4 == rank[name[m['away']]] % 4 and name[m['home']] in POOL_A)
        _play(d['owner'], event_id, m, 40 if home_wins else 20, 20 if home_wins else 40)
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert '1st A v 2nd B and 1st B v 2nd A' in page
    resp = d['owner'].post(f'/tournament/{event_id}/playoffs', data={'size': '4'}, follow_redirects=True)
    assert 'Semi-finals made: 1st A v 2nd B and 1st B v 2nd A.' in resp.get_data(as_text=True)
    t = _t(d, event_id)
    name = sports.names(t)
    semis = [m for m in t['matches'] if m.get('stage') == 'semi']
    assert [sports.match_no(m) for m in semis] == ['M-29', 'M-30']
    assert [(name[m['home']], name[m['away']]) for m in semis] == [('Garuda Sena', 'Code Blue'), ('Gaja Pade', 'Malnad Fighters')]
    final = next(m for m in t['matches'] if m.get('stage') == 'final')
    assert sports.match_no(final) == 'M-31' and not any(m.get('stage') == 'third' for m in t['matches'])

    _play(d['owner'], event_id, semis[0], 35, 30)
    _play(d['owner'], event_id, semis[1], 25, 31)                   # Malnad Fighters win
    final = next(m for m in _t(d, event_id)['matches'] if m.get('stage') == 'final')
    assert (name[final['home']], name[final['away']]) == ('Garuda Sena', 'Malnad Fighters')
    _play(d['owner'], event_id, final, 30, 30, winner=final['away'])  # a tie: the SPOC names the winner
    places = {name[k]: v for k, v in sports.placings(_t(d, event_id)).items()}
    assert places == {'Malnad Fighters': 1, 'Garuda Sena': 2, 'Code Blue': 3, 'Gaja Pade': 3}


def test_a_late_team_cant_be_squeezed_into_pools(league):
    d, event_id, ids = league
    _generate(d, event_id, ids)
    with pytest.raises(sports.TournamentError, match='fixtures made again'):
        sports.add_team(_t(d, event_id), {'id': 'late', 'name': 'Late XI'})


# ── UPG-385: the schedule from one file ──────────────────────────────────────

def test_the_schedule_file_goes_out_and_comes_back_with_dates_times_and_venues(league):
    d, event_id, ids = league
    _generate(d, event_id, ids)
    resp = d['owner'].get(f'/tournament/{event_id}/schedule.csv')
    assert resp.status_code == 200 and resp.mimetype == 'text/csv'
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True).lstrip('﻿'))))
    assert rows[0] == list(sports.SCHEDULE_COLUMNS) and len(rows) == 29
    assert rows[1][:4] == ['M-01', 'Pool A · Leg 1 · Round 1', 'Garuda Sena', 'Vajra']

    rows[1][4:7] = ['28/11/2026', '3:30 PM', 'Main court']
    rows[2][4:7] = ['2026-11-28', '16:15', 'Court 2']
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    resp = d['owner'].post(f'/tournament/{event_id}/schedule/upload', data={
        'file': (io.BytesIO(out.getvalue().encode()), 'schedule.csv')},
        content_type='multipart/form-data', follow_redirects=True)
    assert 'Schedule saved: 2 matches changed.' in resp.get_data(as_text=True)
    m1, m2 = _t(d, event_id)['matches'][:2]
    assert (m1['date'], m1['time'], m1['venue']) == ('2026-11-28', '15:30', 'Main court')
    assert (m2['date'], m2['time'], m2['venue']) == ('2026-11-28', '16:15', 'Court 2')
    assert '2026-11-28 15:30' in d['owner'].get(f'/tournament/fixtures/{event_id}').get_data(as_text=True)

    rows[1][4], rows[3][5] = '31/02/2026', 'teatime'                 # two wrong rows: nothing changes
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    page = d['owner'].post(f'/tournament/{event_id}/schedule/upload', data={
        'file': (io.BytesIO(out.getvalue().encode()), 'schedule.csv')},
        content_type='multipart/form-data', follow_redirects=True).get_data(as_text=True)
    assert 'Nothing was changed.' in page and 'Row 2 (M-01)' in page and 'Row 4 (M-03)' in page
    assert _t(d, event_id)['matches'][0]['date'] == '2026-11-28'


def test_the_schedule_and_logos_are_the_spocs_the_coordinator_scores(league):
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    assert d['coord'].get(f'/tournament/{event_id}/schedule.csv').status_code == 403
    assert d['coord'].post(f'/tournament/{event_id}/team/{ids["Vajra"]}/logo', data={'action': 'remove'}).status_code == 403
    _play(d['coord'], event_id, t['matches'][0], 30, 22)               # an assigned coordinator enters results
    assert _t(d, event_id)['matches'][0]['status'] == 'played'
    assert d['coord'].get(f"/tournament/{event_id}/match/{t['matches'][1]['id']}/score").status_code == 200


# ── UPG-386: team logos ──────────────────────────────────────────────────────

@pytest.fixture
def stored(monkeypatch):
    import utils_storage
    saved = []

    def fake_upload(data, path, content_type):
        saved.append({'data': data, 'path': path, 'type': content_type})
        return f'https://cdn.example/{path}'
    monkeypatch.setattr(utils_storage, 'upload_file', fake_upload)
    return saved


def _png(width=600, height=300):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    img.paste((200, 30, 30, 255), (100, 50, 500, 250))
    out = io.BytesIO()
    img.save(out, 'PNG')
    return out.getvalue()


def test_a_team_logo_shows_in_the_fixtures_tables_and_scoreboard(league, stored):
    d, event_id, ids = league
    _generate(d, event_id, ids)
    vajra = ids['Vajra']
    resp = d['owner'].post(f'/tournament/{event_id}/team/{vajra}/logo', data={
        'logo': (io.BytesIO(_png()), 'vajra.png')}, content_type='multipart/form-data', follow_redirects=True)
    assert 'Logo saved.' in resp.get_data(as_text=True)
    assert len(stored) == 1 and stored[0]['type'] == 'image/webp' and stored[0]['path'].startswith('team-logos/')
    with Image.open(io.BytesIO(stored[0]['data'])) as img:            # square, whole logo, still transparent
        assert img.size == (256, 256) and img.mode == 'RGBA' and img.getpixel((0, 0))[3] == 0
    url = next(x for x in _t(d, event_id)['teams'] if x['id'] == vajra)['logo']
    assert url == f"https://cdn.example/{stored[0]['path']}"
    first = _t(d, event_id)['matches'][0]                               # Garuda Sena v Vajra
    for page_url in (f'/tournament/{event_id}', f'/tournament/fixtures/{event_id}', f'/event/{event_id}',
                     f"/tournament/live/{event_id}/{first['id']}"):
        assert f'src="{url}"' in d['owner'].get(page_url).get_data(as_text=True), page_url

    _generate(d, event_id, ids, confirm_replace='yes')                  # making the fixtures again keeps it
    assert next(x for x in _t(d, event_id)['teams'] if x['id'] == vajra).get('logo') == url

    resp = d['owner'].post(f'/tournament/{event_id}/team/{vajra}/logo', data={
        'logo': (io.BytesIO(b'not an image'), 'x.png')}, content_type='multipart/form-data', follow_redirects=True)
    assert "isn&#39;t an image" in resp.get_data(as_text=True) or "isn't an image" in resp.get_data(as_text=True)
    d['owner'].post(f'/tournament/{event_id}/team/{vajra}/logo', data={'action': 'remove'})
    assert 'logo' not in next(x for x in _t(d, event_id)['teams'] if x['id'] == vajra)
    assert not re.search(r'class="team-logo', d['owner'].get(f'/tournament/fixtures/{event_id}').get_data(as_text=True))
