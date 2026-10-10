"""
tests/test_coordinator_authz.py — BLK-04a on the real SQL database layer:
coordinator endpoints act only on events the user is allowed to manage.
"""
import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def world(real_app):
    """An owner SPOC's event with one registration, plus outsiders and staff."""
    flask_app, db = real_app
    people = {k: f"{_unique(k)}@test.edu" for k in
              ('owner', 'other_spoc', 'coord_out', 'coord_in', 'student', 'stranger')}
    _user(db, people['owner'], 'ClubSPOC')
    _user(db, people['other_spoc'], 'ClubSPOC')
    _user(db, people['coord_out'], 'EventCoordinator')
    _user(db, people['coord_in'], 'EventCoordinator')
    _user(db, people['student'], 'Student')
    _user(db, people['stranger'], 'Student')

    owner = _login(flask_app, people['owner'], 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Authz Event'), '2030-06-01', fee=0, team=False)
    db.collection('events').document(event_id).update(
        {'staff': [{'name': 'In', 'email': people['coord_in'], 'role': 'EventCoordinator'}]})

    student = _login(flask_app, people['student'], 'Student')
    student.post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes',
        'full_name': 'Stu Dent', 'email': people['student'], 'phone': '9876543210', 'usn': '1SN20CS777'})
    regs = list(db.collection('registrations').where('event_id', '==', event_id).stream())
    assert len(regs) == 1
    return {'app': flask_app, 'db': db, 'event_id': event_id, 'reg_id': regs[0].id,
            'reg': regs[0].to_dict(), 'people': people, 'owner': owner, 'student': student}


def _client(w, who, role):
    return _login(w['app'], w['people'][who], role)


WRITE_ROUTES = [
    ('/coordinator/delete_event/{e}', {}),
    ('/coordinator/assign_staff/{e}', {'name': 'X', 'email': 'x@test.edu', 'role': 'Judge'}),
    ('/coordinator/allocate_rooms/{e}', {'room_name[]': ['R1'], 'capacity[]': ['5']}),
    ('/coordinator/trigger_reminders/{e}', {}),
    ('/coordinator/promote_round/{e}', {'cutoff_score': '0'}),
    ('/coordinator/broadcast/{e}', {'subject': 'Hi', 'message': 'spam'}),
    ('/coordinator/publish_results/{e}', {}),
]


# ── Criterion 5 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('who,role', [('coord_out', 'EventCoordinator'), ('other_spoc', 'ClubSPOC')])
def test_outsiders_get_403_on_every_coordinator_write_route(world, who, role):
    db, event_id = world['db'], world['event_id']
    client = _client(world, who, role)
    before = db.collection('events').document(event_id).get().to_dict()

    for url, data in WRITE_ROUTES:
        resp = client.post(url.format(e=event_id), data=data)
        assert resp.status_code == 403, (url, resp.status_code)

    after = db.collection('events').document(event_id).get().to_dict()
    assert after['staff'] == before['staff']
    assert after.get('status') == before.get('status')
    assert after.get('active_round') == before.get('active_round')
    reg = db.collection('registrations').document(world['reg_id']).get().to_dict()
    assert not reg.get('assigned_room')
    assert not reg.get('is_eliminated')

    hud = client.get(f'/coordinator/scan-hud/{event_id}')
    assert hud.status_code == 302 and hud.headers['Location'] == '/coordinator/scanner'


def test_state_changing_routes_refuse_get_and_the_owner_can_delete_by_post(world):
    db, event_id, owner = world['db'], world['event_id'], world['owner']
    for url in ('/coordinator/delete_event/{e}', '/coordinator/trigger_reminders/{e}', '/spoc/delete_event/{e}'):
        assert owner.get(url.format(e=event_id)).status_code == 405
    assert db.collection('events').document(event_id).get().exists

    # An assigned coordinator still can't delete: that's the owner's call
    assert _client(world, 'coord_in', 'EventCoordinator').post(
        f'/coordinator/delete_event/{event_id}').status_code == 403
    assert db.collection('events').document(event_id).get().exists

    assert owner.post(f'/spoc/delete_event/{event_id}').status_code == 302
    assert not db.collection('events').document(event_id).get().exists
    assert list(db.collection('registrations').where('event_id', '==', event_id).stream()) == []


def test_staff_form_cannot_hand_out_admin_roles(world):
    db, event_id, owner = world['db'], world['event_id'], world['owner']
    stranger = world['people']['stranger']

    resp = owner.post(f'/coordinator/assign_staff/{event_id}',
                      data={'name': 'Mallory', 'email': stranger, 'role': 'SuperAdmin'})
    assert resp.status_code == 302
    role = db.collection('users').document(stranger).get().to_dict()['role']
    assert getattr(role, 'value', role) in ('Student', 'Participant')
    assert all(s['email'] != stranger for s in db.collection('events').document(event_id).get().to_dict()['staff'])

    ok = owner.post(f'/coordinator/assign_staff/{event_id}',
                    data={'name': 'Judge Judy', 'email': stranger, 'role': 'Judge'})
    assert ok.status_code == 302
    assert any(s['email'] == stranger and s['role'] == 'Judge'
               for s in db.collection('events').document(event_id).get().to_dict()['staff'])


def test_walkins_only_for_assigned_events(world):
    db, event_id = world['db'], world['event_id']
    walkin = f"{_unique('walkin')}@test.edu"
    outsider = _client(world, 'coord_out', 'EventCoordinator')
    resp = outsider.post('/coordinator/process_walkin',
                         data={'event_id': event_id, 'email': walkin, 'name': 'Walk In'})
    assert resp.headers['Location'] == '/coordinator/on_spot'
    assert not db.collection('users').document(walkin).get().exists
    assert len(list(db.collection('registrations').where('event_id', '==', event_id).stream())) == 1


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_students_and_outsiders_get_403_on_ticket_lookup_and_attendance(world):
    db, reg_id = world['db'], world['reg_id']
    for client in (world['student'], _client(world, 'stranger', 'Student'),
                   _client(world, 'coord_out', 'EventCoordinator')):
        assert client.get(f'/coordinator/get_ticket/{reg_id}').status_code == 403
        mark = client.post('/coordinator/mark_attendance_granular',
                           json={'reg_id': reg_id, 'present_usns': ['1SN20CS777']})
        assert mark.status_code == 403
    assert db.collection('registrations').document(reg_id).get().to_dict()['attendance'] == 'Pending'


def test_assigned_staff_see_only_what_the_scanner_needs(world):
    db, reg_id = world['db'], world['reg_id']
    staff = _client(world, 'coord_in', 'EventCoordinator')

    resp = staff.get(f'/coordinator/get_ticket/{reg_id}')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'success'
    assert payload['data']['lead_name'] == 'Stu Dent'
    text = resp.get_data(as_text=True)
    assert world['people']['student'] not in text
    assert '9876543210' not in text
    assert 'form_answers' not in text

    mark = staff.post('/coordinator/mark_attendance_granular',
                      json={'reg_id': reg_id, 'present_usns': ['1SN20CS777']})
    assert mark.status_code == 200 and mark.get_json()['status'] == 'success'
    assert db.collection('registrations').document(reg_id).get().to_dict()['attendance'] == 'Present'


# ── Criterion 7 (certificate part) ─────────────────────────────────────────

def test_coordinator_certificate_needs_the_registrant_or_certificate_staff(world):
    db, reg_id = world['db'], world['reg_id']
    db.collection('registrations').document(reg_id).update({'attendance': 'Present'})
    url = f'/coordinator/certificate/{reg_id}/1SN20CS777'

    anonymous = world['app'].test_client()
    assert anonymous.get(url).status_code == 302  # login first
    assert _client(world, 'stranger', 'Student').get(url).status_code == 403
    assert _client(world, 'coord_in', 'EventCoordinator').get(url).status_code == 403  # can't issue certs
    assert world['student'].get(url).status_code == 200
    assert world['owner'].get(url).status_code == 200

