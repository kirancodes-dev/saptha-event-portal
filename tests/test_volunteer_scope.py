"""
tests/test_volunteer_scope.py — BLK-18 on the real database layer: a Volunteer
may check in only at events they're staff on. Before, `can()` gave every
Volunteer `check_in` on every event, so any volunteer could mark attendance
and open anyone's ticket and QR.
"""
import datetime

from services_permission import PERMISSIONS, can
from tests.test_integration_flow import _create_event, _login, _unique, _user


def _event_with_registration(flask_app, db):
    spoc = f"{_unique('volspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(client, db, _unique('Volunteer Event'), datetime.date.today().isoformat(), team=False)
    reg_id = _unique('REG')
    db.collection('registrations').document(reg_id).set({
        'event_id': event_id, 'lead_name': 'Asha Attendee', 'lead_email': f"{_unique('asha')}@test.edu",
        'lead_usn': '1SN21CS001', 'payment_status': 'Free', 'attendance': 'Pending',
        'members': [{'name': 'Asha Attendee', 'usn': '1SN21CS001', 'email': 'asha@test.edu'}]})
    return event_id, reg_id


def _volunteer(flask_app, db, event_id=None):
    email = f"{_unique('vol')}@test.edu"
    _user(db, email, 'Volunteer')
    if event_id:
        db.collection('events').document(event_id).update({
            'staff': [{'email': email, 'name': 'Val Volunteer', 'role': 'Volunteer'}]})
    return email, _login(flask_app, email, 'Volunteer')


def test_an_unassigned_volunteer_cant_check_in_or_see_tickets(real_app):
    flask_app, db = real_app
    event_id, reg_id = _event_with_registration(flask_app, db)
    _, client = _volunteer(flask_app, db)

    resp = client.post('/coordinator/mark_attendance_granular', json={'reg_id': reg_id, 'present_usns': ['1SN21CS001']})
    assert resp.status_code == 403
    assert db.collection('registrations').document(reg_id).get().to_dict()['attendance'] == 'Pending'
    assert client.get(f'/coordinator/get_ticket/{reg_id}').status_code == 403
    assert client.get(f'/ticket/qr/{reg_id}').status_code == 403
    resp = client.get(f'/ticket/{reg_id}')
    assert resp.status_code == 302 and 'Asha' not in resp.get_data(as_text=True)


def test_a_volunteer_on_the_events_staff_still_checks_in(real_app):
    flask_app, db = real_app
    event_id, reg_id = _event_with_registration(flask_app, db)
    _, client = _volunteer(flask_app, db, event_id)

    resp = client.get(f'/coordinator/get_ticket/{reg_id}')
    assert resp.status_code == 200 and resp.get_json()['data']['lead_name'] == 'Asha Attendee'
    resp = client.post('/coordinator/mark_attendance_granular', json={'reg_id': reg_id, 'present_usns': ['1SN21CS001']})
    assert resp.status_code == 200 and resp.get_json()['status'] == 'success'
    assert db.collection('registrations').document(reg_id).get().to_dict()['attendance'] == 'Present'


def test_a_volunteer_has_check_in_only_and_only_where_assigned(real_app):
    flask_app, db = real_app
    event_id, _ = _event_with_registration(flask_app, db)
    email, _ = _volunteer(flask_app, db, event_id)
    other_event, _ = _event_with_registration(flask_app, db)
    user = {'user_id': email, 'role': 'Volunteer'}
    with flask_app.app_context():
        assigned = dict(db.collection('events').document(event_id).get().to_dict(), id=event_id)
        other = dict(db.collection('events').document(other_event).get().to_dict(), id=other_event)
        assert can(user, 'check_in', assigned, db=db)
        assert not can(user, 'check_in', other, db=db)
        assert not can(user, 'check_in', other_event, db=db)  # by event id too
        for permission in PERMISSIONS - {'check_in'}:
            assert not can(user, permission, assigned, db=db), permission
