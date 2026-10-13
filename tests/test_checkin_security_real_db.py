"""
tests/test_checkin_security_real_db.py — BLK-12 on the real SQL database
layer (tests/test_checkin_security.py covers the same rules on the mock DB):

  * kiosk search and confirm: logged-in staff with access to the event only,
    that event's registrations only, no emails or phone numbers;
  * ticket verify: signed tokens only, GET never marks attendance, only
    authorised staff can POST a check-in;
  * self check-in: the logged-in owner with a fresh venue code for this event.
"""
import time

import pytest
from itsdangerous import URLSafeTimedSerializer

from tests.test_integration_flow import _create_event, _login, _unique, _user

PHONE = '9876543210'


@pytest.fixture
def day(real_app):
    """An active event with one registration, staff in and out, and an attendee."""
    flask_app, db = real_app
    people = {k: f"{_unique(k)}@test.edu" for k in ('owner', 'coord_in', 'coord_out', 'student', 'other')}
    _user(db, people['owner'], 'ClubSPOC')
    _user(db, people['coord_in'], 'EventCoordinator')
    _user(db, people['coord_out'], 'EventCoordinator')
    _user(db, people['student'], 'Student')
    _user(db, people['other'], 'Student')
    owner = _login(flask_app, people['owner'], 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Gate Event'), '2030-06-01', fee=0, team=False)
    other_event = _create_event(owner, db, _unique('Other Event'), '2030-06-02', fee=0, team=False)

    student = _login(flask_app, people['student'], 'Student')
    student.post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes',
        'full_name': 'Gate Walker', 'email': people['student'], 'phone': PHONE, 'usn': '1SN20CS321'})
    other = _login(flask_app, people['other'], 'Student')
    other.post(f'/forms/submit/{other_event}', data={'privacy_consent': 'yes',
        'full_name': 'Gate Walker Twin', 'email': people['other'], 'phone': PHONE, 'usn': '1SN20CS322'})

    db.collection('events').document(event_id).update({
        'status': 'active', 'allow_self_checkin': True,
        'staff': [{'name': 'In', 'email': people['coord_in'], 'role': 'EventCoordinator'}]})
    reg_doc = next(iter(db.collection('registrations').where('event_id', '==', event_id).stream()))
    with flask_app.app_context():
        from routes_ticket import generate_ticket_token
        token = generate_ticket_token(reg_doc.id, event_id, 'Gate Walker')
    return {'app': flask_app, 'db': db, 'people': people, 'event_id': event_id,
            'other_event': other_event, 'reg_id': reg_doc.id, 'token': token,
            'owner': owner, 'student': student, 'other': other}


def _attendance(d):
    return d['db'].collection('registrations').document(d['reg_id']).get().to_dict().get('attendance')


# ── Criterion 1: kiosk ──────────────────────────────────────────────────────

def test_kiosk_needs_staff_of_the_event_and_never_leaks_contact_details(day):
    d = day
    anonymous = d['app'].test_client()
    search = anonymous.post('/checkin/kiosk/search', json={'event_id': d['event_id'], 'query': 'Gate'})
    assert search.status_code == 302 and '/login' in search.headers['Location']
    confirm = anonymous.post(f"/checkin/kiosk/confirm/{d['reg_id']}")
    assert confirm.status_code == 302 and '/login' in confirm.headers['Location']
    assert _attendance(d) == 'Pending'

    outsider = _login(d['app'], d['people']['coord_out'], 'EventCoordinator')
    assert outsider.post('/checkin/kiosk/search',
                         json={'event_id': d['event_id'], 'query': 'Gate'}).status_code == 403
    assert outsider.post(f"/checkin/kiosk/confirm/{d['reg_id']}").status_code == 403
    assert _attendance(d) == 'Pending'

    staff = _login(d['app'], d['people']['coord_in'], 'EventCoordinator')
    found = staff.post('/checkin/kiosk/search', json={'event_id': d['event_id'], 'query': 'Gate'})
    assert found.status_code == 200
    results = found.get_json()['results']
    assert [r['lead_name'] for r in results] == ['Gate Walker']  # not the other event's twin
    body = found.get_data(as_text=True)
    assert '@' not in body and PHONE not in body

    ok = staff.post(f"/checkin/kiosk/confirm/{d['reg_id']}")
    assert ok.status_code == 200 and ok.get_json()['success'] is True
    assert _attendance(d) == 'Present'


# ── Criterion 2: ticket verify ─────────────────────────────────────────────

def test_ticket_verify_takes_signed_tokens_only_and_only_staff_mark_attendance(day):
    d = day
    staff = _login(d['app'], d['people']['coord_in'], 'EventCoordinator')
    for url in (f"/ticket/verify/{d['reg_id']}", f"/ticket/api/verify/{d['reg_id']}"):
        assert staff.get(url).status_code == 400
        assert staff.post(url).status_code == 400
    assert _attendance(d) == 'Pending'

    # GET with a real token is read-only, for anyone
    for client in (d['app'].test_client(), staff):
        assert client.get(f"/ticket/verify/{d['token']}").status_code == 200
        assert client.get(f"/ticket/api/verify/{d['token']}").status_code == 200
    assert _attendance(d) == 'Pending'

    # Students and unassigned staff can't check anyone in
    outsider = _login(d['app'], d['people']['coord_out'], 'EventCoordinator')
    for client in (d['student'], outsider):
        assert client.post(f"/ticket/verify/{d['token']}").status_code == 403
        assert client.post(f"/ticket/api/verify/{d['token']}").status_code == 403
    assert _attendance(d) == 'Pending'

    assert staff.post(f"/ticket/verify/{d['token']}").status_code == 200
    assert _attendance(d) == 'Present'


# ── Criterion 3: self check-in ─────────────────────────────────────────────

def _venue_code(d, event_id, age_seconds=0):
    serializer = URLSafeTimedSerializer(d['app'].config['SECRET_KEY'], salt='venue-qr-checkin-salt')
    if not age_seconds:
        return serializer.dumps({'event_id': event_id})
    real_time = time.time
    try:
        time.time = lambda: real_time() - age_seconds
        return serializer.dumps({'event_id': event_id})
    finally:
        time.time = real_time


def test_self_checkin_needs_the_owner_and_a_fresh_code_for_this_event(day):
    d = day
    url = f"/checkin/{d['event_id']}/submit"
    good = _venue_code(d, d['event_id'])

    anonymous = d['app'].test_client()
    resp = anonymous.post(url, data={'code': good})
    assert resp.status_code == 302 and '/login' in resp.headers['Location']
    assert _attendance(d) == 'Pending'

    # Logged in, but not registered for this event
    assert d['other'].post(url, data={'code': good}).status_code == 302
    assert _attendance(d) == 'Pending'

    for code in ('', 'not-a-code', _venue_code(d, d['event_id'], age_seconds=11 * 60),
                 _venue_code(d, d['other_event'])):
        refused = d['student'].post(url, data={'code': code})
        assert refused.status_code == 302 and refused.headers['Location'] == f"/checkin/{d['event_id']}"
        assert _attendance(d) == 'Pending'

    done = d['student'].post(url, data={'code': good})
    assert done.status_code == 200
    assert _attendance(d) == 'Present'
