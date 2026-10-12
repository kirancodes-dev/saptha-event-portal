"""
tests/test_analytics_and_leaderboards.py — UPG-83 (analytics pages: real counts,
period and category filters, per-event comparison, SPOC scope, the retired
/analytics page), UPG-81 (dashboards count registrations, not the cached
counter) and UPG-84 (one ranking for every leaderboard).
"""
import datetime
import json
import re

import pytest

from services_insights import build, reg_state
from services_leaderboard import rank, score_of, score_text
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

TODAY = datetime.date(2026, 10, 12)


def _at(days_ago, hour=10):
    d = TODAY - datetime.timedelta(days=days_ago)
    return f"{d.isoformat()} {hour:02d}:15:00"


# ── services_insights ──────────────────────────────────────────────────────

def _fixture():
    events = [
        {'id': 'past', 'title': 'Past Hack', 'category': 'Technical', 'status': 'completed', 'date': '2026-10-01',
         'registration_count': 999, 'capacity': 10},
        {'id': 'next', 'title': 'Next Dance', 'category': 'Cultural', 'status': 'registration_open', 'date': '2026-11-01'},
        {'id': 'old', 'title': 'Old Quiz', 'category': 'Technical', 'status': 'completed', 'date': '2026-01-10'},
    ]
    regs = [
        # Past Hack: 3 confirmed (2 present), 1 cancelled, 1 waitlisted; one paid, one refunded
        {'event_id': 'past', 'status': 'Confirmed', 'attendance': 'Present', 'registered_at': _at(20), 'amount_paid': 200},
        {'event_id': 'past', 'status': 'confirmed', 'attendance': 'Present', 'registered_at': _at(19, 21)},
        {'event_id': 'past', 'status': 'checked_in', 'attendance': 'Absent', 'registered_at': _at(18),
         'amount_paid': 200, 'payment_status': 'refunded'},
        {'event_id': 'past', 'status': 'cancelled', 'registered_at': _at(18)},
        {'event_id': 'past', 'status': 'waitlisted', 'registered_at': _at(17)},
        # Next Dance: 2 confirmed, not held yet
        {'event_id': 'next', 'status': 'confirmed', 'registered_at': _at(2)},
        {'event_id': 'next', 'status': 'pending_payment', 'registered_at': _at(1)},
        # Old Quiz: registered last period (40 days ago) and long ago
        {'event_id': 'old', 'status': 'confirmed', 'attendance': 'Present', 'registered_at': _at(40)},
        {'event_id': 'old', 'status': 'confirmed', 'registered_at': _at(300)},
    ]
    return events, regs


def test_registration_states_fold_case_and_new_statuses():
    assert [reg_state({'status': s}) for s in ('Confirmed', 'checked_in', 'shortlisted', 'pending_payment',
                                               'Waitlisted', 'cancelled', 'refunded', None)] == \
        ['confirmed', 'confirmed', 'confirmed', 'pending', 'waitlisted', 'cancelled', 'cancelled', 'confirmed']


def test_build_counts_registrations_not_the_cached_counter_and_compares_periods():
    events, regs = _fixture()
    d = build(events, regs, period='30', today=TODAY)
    k = d['kpis']
    assert k['registrations'] == 7                       # the 7 made in the last 30 days
    assert k['registrations_delta'] == 600.0             # vs 1 in the 30 days before
    assert k['revenue'] == 200                           # the refunded payment doesn't count
    assert k['live_events'] == 1 and k['events'] == 3
    rows = {r['id']: r for r in d['events']}
    assert set(rows) == {'past', 'next'}                 # Old Quiz had nothing in the period
    past = rows['past']
    assert (past['registered'], past['confirmed'], past['attended'], past['no_show'],
            past['cancelled'], past['waitlisted']) == (5, 3, 2, 1, 1, 1)
    assert past['attendance_rate'] == 66.7 and past['fill_rate'] == 40.0
    nxt = rows['next']
    assert nxt['no_show'] == 0 and nxt['attendance_rate'] is None and nxt['upcoming'] == 1
    # The breakdown parts add up to the registrations
    for r in d['events']:
        assert r['attended'] + r['no_show'] + r['upcoming'] + r['other'] == r['registered']
    funnel = {f['stage']: f['value'] for f in d['funnel']}
    assert funnel == {'Registered': 7, 'Confirmed': 4, 'Attended': 2, 'Certified': 2}
    assert k['attendance_rate'] == 66.7                  # held events only


def test_build_filters_by_category_and_all_time():
    events, regs = _fixture()
    d = build(events, regs, period='all', category='Technical', today=TODAY)
    assert {r['id'] for r in d['events']} == {'past', 'old'}
    assert d['kpis']['registrations'] == 7 and d['kpis']['compared'] is False
    assert d['categories_available'] == ['Cultural', 'Technical']
    assert d['colour_categories'] == ['Cultural', 'Technical']
    assert d['trend']['weekly'] is True                  # 300 days of data: weekly buckets
    assert sum(d['trend']['total']) == 7


def test_heatmap_and_no_shows():
    events, regs = _fixture()
    d = build(events, regs, period='90', today=TODAY)
    cells = {(h, day): n for h, day, n in d['heatmap'] if n}
    assert sum(cells.values()) == 8 and cells[(21, (TODAY - datetime.timedelta(days=19)).weekday())] == 1
    assert d['no_shows'][0]['title'] == 'Past Hack' and d['no_shows'][0]['rate'] == 33.3


# ── services_leaderboard ───────────────────────────────────────────────────

def _reg(rid, team, *scores, **extra):
    return dict({'id': rid, 'team_name': team, 'lead_name': team + ' Lead',
                 'scores': {f'j{i}': s for i, s in enumerate(scores)}}, **extra)


def test_score_reads_both_fields_and_keeps_decimals():
    assert score_of(_reg('a', 'A', {'total': 90}, {'final_score': 89}, {'total': 90}))[0] == 89.67
    assert score_of(_reg('a', 'A', {'total': '80.5'}, {'note': 'no score'})) == (80.5, 1)
    assert score_of({'scores': {}}) == (None, 0)
    assert score_text(89.67) == '89.67' and score_text(82.3) == '82.3' and score_text(80.0) == '80'


def test_ranking_shares_places_and_leaves_out_cancelled_and_eliminated():
    rows = rank([
        _reg('a', 'Alpha', {'total': 80}),
        _reg('b', 'Bravo', {'final_score': 90}),
        _reg('c', 'Charlie', {'total': 80}),
        _reg('d', 'Delta', {'total': 70}),
        _reg('e', 'Echo', {'total': 99}, is_eliminated=True),
        _reg('f', 'Foxtrot', {'total': 98}, status='cancelled'),
        _reg('g', 'Golf'),
    ], include_unscored=True)
    assert [(r['team'], r['rank'], r['tied']) for r in rows] == [
        ('Bravo', 1, False), ('Alpha', 2, True), ('Charlie', 2, True), ('Delta', 4, False), ('Golf', None, False)]


def test_ties_are_ordered_by_criteria_then_name():
    rows = rank([_reg('a', 'Alpha', {'total': 80, 'details': {'Innovation': 20}}),
                 _reg('b', 'Bravo', {'total': 80, 'details': {'Innovation': 30}})])
    assert [r['team'] for r in rows] == ['Bravo', 'Alpha'] and {r['rank'] for r in rows} == {1}


# ── Routes ─────────────────────────────────────────────────────────────────

@pytest.fixture
def s(real_app, monkeypatch):
    flask_app, db = real_app
    import routes_admin, routes_analytics, routes_coordinator, routes_judge, routes_live, routes_participant, routes_spoc
    for mod in (routes_admin, routes_analytics, routes_coordinator, routes_judge, routes_live, routes_participant, routes_spoc):
        monkeypatch.setattr(mod, 'db', db, raising=False)
    monkeypatch.setattr(routes_coordinator, 'send_result_email', lambda *a, **k: None)
    before = {d.id for d in db.collection('users').stream()}
    people = {k: f"{_unique(k)}@test.edu" for k in ('admin', 'spoc', 'other', 'student')}
    _user(db, people['admin'], 'SuperAdmin')
    _user(db, people['spoc'], 'ClubSPOC')
    _user(db, people['other'], 'ClubSPOC')
    _user(db, people['student'], 'Student')
    admin = flask_app.test_client()
    resp = admin.post('/login', data={'role': 'SuperAdmin', 'email': people['admin'], 'password': PASSWORD,
                                      'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert resp.headers['Location'] != '/login'
    spoc = _login(flask_app, people['spoc'], 'ClubSPOC')
    other = _login(flask_app, people['other'], 'ClubSPOC')
    mine = _create_event(spoc, db, _unique('Mine Hack'), '2030-06-01', team=True)
    theirs = _create_event(other, db, _unique('Their Fest'), '2030-06-02', team=False)
    # A deliberately stale cached counter (UPG-81)
    db.collection('events').document(mine).update({'status': 'active', 'registration_count': 645})
    regs = {}
    now = datetime.datetime.now()
    for i, (team, scores, extra) in enumerate([
        ('Alpha', {'j1': {'total': 90}, 'j2': {'final_score': 89.5}}, {}),
        ('Bravo', {'j1': {'total': 89.75}}, {}),
        ('Charlie', {'j1': {'total': 89.75}}, {}),
        ('Delta', {}, {}),
        ('Echo', {'j1': {'total': 99}}, {'status': 'cancelled'}),
    ]):
        rid = _unique('reg')
        db.collection('registrations').document(rid).set(dict({
            'event_id': mine, 'team_name': team, 'lead_name': f'{team} Lead', 'lead_email': f'{team.lower()}@test.edu',
            'status': 'confirmed', 'attendance': 'Present', 'scores': scores, 'amount_paid': 100 if i < 2 else 0,
            'registered_at': (now - datetime.timedelta(days=i)).strftime('%Y-%m-%d %H:%M:%S')}, **extra))
        regs[team] = rid
    yield dict(app=flask_app, db=db, people=people, admin=admin, spoc=spoc, other=other,
               mine=mine, theirs=theirs, regs=regs)
    # Leave the user list as it was (tests/test_admin_users.py reads its first page)
    for d in db.collection('users').stream():
        if d.id not in before:
            db.collection('users').document(d.id).delete()


def _page_data(html):
    return json.loads(re.search(r'<script type="application/json" id="analytics-data">(.*?)</script>', html, re.S).group(1))


def test_admin_analytics_counts_real_registrations_and_filters(s):
    html = s['admin'].get('/admin/analytics?period=all').get_data(as_text=True)
    data = _page_data(html)
    row = next(r for r in data['events'] if r['id'] == s['mine'])
    assert row['registered'] == 5 and row['cancelled'] == 1 and row['revenue'] == 200
    assert 'echarts@5.5.1' in html and 'Compare events' in html
    one = _page_data(s['admin'].get('/admin/analytics?period=7&category=Cultural').get_data(as_text=True))
    assert one['period'] == '7' and one['category'] == 'Cultural'
    assert all(r['category'] == 'Cultural' for r in one['events'])
    assert s['spoc'].get('/admin/analytics').status_code in (302, 403)


def test_spoc_analytics_shows_only_their_events(s):
    data = _page_data(s['spoc'].get('/spoc/analytics?period=all').get_data(as_text=True))
    ids = {r['id'] for r in data['events']}
    assert s['mine'] in ids and s['theirs'] not in ids


def test_the_old_analytics_page_is_retired(s):
    assert s['admin'].get('/analytics').headers['Location'].endswith('/admin/analytics')
    assert s['spoc'].get('/analytics').headers['Location'].endswith('/spoc/analytics')
    student = _login(s['app'], s['people']['student'], 'Student')
    assert student.get('/analytics/api/stats').status_code in (302, 403)
    assert s['spoc'].get('/analytics/api/stats').status_code in (302, 403)
    assert s['admin'].get('/analytics/api/stats').status_code == 200


def test_dashboards_count_registrations_not_the_cached_counter(s):
    admin_page = s['admin'].get('/admin/dashboard').get_data(as_text=True)
    chart = json.loads(re.search(r'id="adminChartData" type="application/json">(.*?)</script>', admin_page, re.S).group(1))
    assert chart['regs'][chart['ids'].index(s['mine'])] == 5
    spoc_page = s['spoc'].get('/spoc/dashboard').get_data(as_text=True)
    data = json.loads(re.search(r'id="spoc-chart-data" type="application/json">(.*?)</script>', spoc_page, re.S).group(1))
    row = next(r for r in data['breakdown'] if r['id'] == s['mine'])
    assert row['registered'] == 5 and '645' not in spoc_page.split('id="spoc-chart-data"')[1][:400]


def test_every_board_shows_the_same_scores_and_places(s):
    eid = s['mine']
    public = s['admin'].get(f'/participant/leaderboard/{eid}', headers={'Accept': 'application/json'}).get_json()['data']
    live = s['admin'].get(f'/live/data/{eid}').get_json()['board']
    expected = [('Alpha', 89.75, 1, False), ('Bravo', 89.75, 1, False), ('Charlie', 89.75, 1, False)]
    # Alpha: (90 + 89.5) / 2 = 89.75 — the evaluation engine's final_score counts
    assert [(r['team_name'], r['score'], r['rank']) for r in public] == \
        [('Alpha', 89.75, 1), ('Bravo', 89.75, 1), ('Charlie', 89.75, 1)]
    assert all(r['tied'] for r in public) and len(expected) == len(public)
    assert [(r['team'], r['score'], r['rank']) for r in live[:3]] == [(r['team_name'], r['score'], r['rank']) for r in public]
    assert live[3]['team'] == 'Delta' and live[3]['rank'] is None        # unscored, unranked
    assert 'Echo' not in [r['team'] for r in live]                       # cancelled
    results = s['spoc'].get(f'/spoc/results/{eid}').get_data(as_text=True)
    assert 'Not scored yet · 1' in results and '3 teams evaluated' in results and 'Joint 1st place' in results


def test_publishing_results_keeps_decimals_and_shared_places(s):
    s['admin'].post(f"/coordinator/publish_results/{s['mine']}")
    reg = s['db'].collection('registrations').document(s['regs']['Alpha']).get().to_dict()
    assert reg['final_score'] == 89.75 and reg['final_rank'] == 1
    ev = s['db'].collection('events').document(s['mine']).get().to_dict()
    assert sorted(w['team_name'] for w in ev['winners']) == ['Alpha', 'Bravo', 'Charlie']
    assert {w['rank'] for w in ev['winners']} == {1}


def test_spoc_live_stats_survive_attendance_without_a_checkin_time(s):
    resp = s['spoc'].get('/spoc/api/stats')
    assert resp.status_code == 200 and resp.get_json()['total_regs'] >= 5
