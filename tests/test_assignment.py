"""
tests/test_assignment.py — UPG-29 on the real database layer: a SPOC assigns
a coordinator and a judge to their own event, each sees it, nobody else can
change the event's staff, and removing someone ends their access.
"""
import datetime

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def staffed(real_app):
    flask_app, db = real_app
    p = {k: f"{_unique(k)}@test.edu" for k in ('owner', 'other', 'coord', 'judge')}
    _user(db, p['owner'], 'ClubSPOC')
    _user(db, p['other'], 'ClubSPOC')
    _user(db, p['coord'], 'EventCoordinator')
    _user(db, p['judge'], 'Judge')
    owner = _login(flask_app, p['owner'], 'ClubSPOC')
    title = _unique('Staffed Event')
    event_id = _create_event(owner, db, title, datetime.date.today().isoformat(), team=False)
    # The judge dashboard lists only 'active' events until UPG-04 criterion 3
    db.collection('events').document(event_id).update({'status': 'active', 'judging_criteria': ['Overall Score']})
    reg_id = _unique('REG')
    db.collection('registrations').document(reg_id).set({
        'reg_id': reg_id, 'event_id': event_id, 'lead_name': 'Team Lead', 'lead_email': 'lead@test.edu',
        'team_name': 'Alpha', 'attendance': 'Present', 'payment_status': 'Free', 'members': [],
        'assigned_judge_email': p['judge']})  # allocated to the judge, as room allocation does
    return {'app': flask_app, 'db': db, 'p': p, 'owner': owner, 'event_id': event_id, 'title': title, 'reg_id': reg_id}


def _event(d):
    return d['db'].collection('events').document(d['event_id']).get().to_dict()


def _assign_both(d):
    e = d['event_id']
    assert d['owner'].post(f'/spoc/assign_coordinator/{e}', data={
        'coordinator_email': d['p']['coord'], 'coordinator_name': 'Cora'}).status_code == 302
    assert d['owner'].post(f'/spoc/add_judge/{e}', data={
        'judge_name': 'Jude', 'judge_email': d['p']['judge']}).status_code == 302


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_owner_assigns_a_coordinator_and_a_judge_and_each_sees_the_event(staffed):
    d = staffed
    _assign_both(d)
    event = _event(d)
    assert d['p']['coord'] in event['coordinators']
    assert {s['email']: s['role'] for s in event['staff']} == {d['p']['coord']: 'EventCoordinator', d['p']['judge']: 'Judge'}

    coord = _login(d['app'], d['p']['coord'], 'EventCoordinator')
    assert d['title'] in coord.get('/coordinator/dashboard').get_data(as_text=True)
    assert coord.get(f"/coordinator/registrations/{d['event_id']}").status_code == 200

    judge = _login(d['app'], d['p']['judge'], 'Judge')
    assert d['title'] in judge.get('/judge/dashboard').get_data(as_text=True)
    assert 'Alpha' in judge.get(f"/judge/event/{d['event_id']}").get_data(as_text=True)

    # The owner's dashboard lists them, with a way to remove each
    page = d['owner'].get('/spoc/dashboard').get_data(as_text=True)
    assert f'action="/spoc/remove_staff/{d["event_id"]}"' in page
    assert f'name="email" value="{d["p"]["coord"]}"' in page and f'name="email" value="{d["p"]["judge"]}"' in page


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_another_spoc_cant_assign_or_remove_and_nothing_changes(staffed):
    d = staffed
    _assign_both(d)
    before = _event(d)
    other = _login(d['app'], d['p']['other'], 'ClubSPOC')
    newcomer = f"{_unique('newcoord')}@test.edu"
    e = d['event_id']

    assert other.post(f'/spoc/assign_coordinator/{e}', data={'coordinator_email': newcomer}).status_code == 403
    assert other.post(f'/spoc/add_judge/{e}', data={'judge_name': 'X', 'judge_email': newcomer}).status_code == 403
    assert other.post(f'/spoc/remove_staff/{e}', data={'email': d['p']['coord']}).status_code == 403
    after = _event(d)
    assert after['staff'] == before['staff'] and after['coordinators'] == before['coordinators']
    assert not d['db'].collection('users').document(newcomer).get().exists


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_removing_someone_ends_their_access(staffed):
    d = staffed
    _assign_both(d)
    e = d['event_id']
    coord = _login(d['app'], d['p']['coord'], 'EventCoordinator')
    judge = _login(d['app'], d['p']['judge'], 'Judge')
    assert coord.get(f'/coordinator/registrations/{e}').status_code == 200
    assert judge.get(f'/judge/event/{e}').status_code == 200

    for email in (d['p']['coord'], d['p']['judge']):
        assert d['owner'].post(f'/spoc/remove_staff/{e}', data={'email': email}).status_code == 302
    event = _event(d)
    assert event['staff'] == [] and event['coordinators'] == []

    # The coordinator: no registrations, exports or check-in, and the dashboard drops the event
    assert coord.get(f'/coordinator/registrations/{e}').status_code == 403
    assert coord.get(f'/coordinator/export_registrations/{e}').status_code == 403
    assert coord.post('/coordinator/mark_attendance_granular',
                      json={'reg_id': d['reg_id'], 'present_usns': []}).status_code == 403
    assert d['title'] not in coord.get('/coordinator/dashboard').get_data(as_text=True)

    # The judge: no team list, no scoring, and the dashboard drops the event
    resp = judge.get(f'/judge/event/{e}')
    assert resp.status_code in (302, 403) and 'Alpha' not in resp.get_data(as_text=True)
    assert judge.post(f"/judge/submit_score/{d['reg_id']}", data={'score_overall_score': '9'}).status_code == 403
    assert not (d['db'].collection('registrations').document(d['reg_id']).get().to_dict().get('scores') or {})
    assert d['title'] not in judge.get('/judge/dashboard').get_data(as_text=True)

    # Their accounts stay
    assert d['db'].collection('users').document(d['p']['coord']).get().exists


def test_removing_someone_who_isnt_staff_changes_nothing(staffed):
    d = staffed
    _assign_both(d)
    before = _event(d)
    resp = d['owner'].post(f"/spoc/remove_staff/{d['event_id']}", data={'email': 'stranger@test.edu'})
    assert resp.status_code == 302
    assert _event(d)['staff'] == before['staff']
