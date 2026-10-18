"""
tests/test_venue_booking_on_create.py — UPG-09 on the real database layer: the
create form's room picker refuses a room already booked for an overlapping time
(no event is made); a free room gets a tentative booking that approval confirms;
the calendar shows the room's name for the event.
"""
import pytest

from tests.test_integration_flow import PASSWORD, _login, _unique, _user

DAY = '2031-03-14'


@pytest.fixture
def venue(real_app):
    flask_app, db = real_app
    spoc, admin = f"{_unique('roomspoc')}@test.edu", f"{_unique('roomadmin')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, admin, 'SuperAdmin')
    campus_id, building_id, room_id = _unique('campus'), _unique('bldg'), _unique('room')
    db.collection('campuses').document(campus_id).set({'name': 'Test Campus', 'slug': campus_id})
    db.collection('buildings').document(building_id).set({'campus_id': campus_id, 'name': 'Block T', 'code': building_id})
    db.collection('rooms').document(room_id).set({'building_id': building_id, 'name': f'Seminar Hall {room_id[-4:]}',
                                                  'capacity': 120})
    admin_client = flask_app.test_client()
    resp = admin_client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                             'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert resp.status_code == 302 and resp.headers['Location'] != '/login'
    return {'app': flask_app, 'db': db, 'spoc': _login(flask_app, spoc, 'ClubSPOC'), 'admin': admin_client,
            'room_id': room_id}


def _create(d, title, time='10:00'):
    return d['spoc'].post('/spoc/create_event', data={
        'title': title, 'category': 'Technical', 'description': 'desc', 'rules': 'rules',
        'date': DAY, 'time': time, 'reg_deadline': DAY, 'participation_type': 'Individual',
        'team_min': '1', 'team_max': '1', 'max_participants': '50', 'reg_fee': '0',
        'visibility': 'public', 'room_id': d['room_id']})


def _events(d, title):
    return [dict(e.to_dict(), id=e.id) for e in d['db'].collection('events').where('title', '==', title).stream()]


def _bookings(d, event_id):
    return [b.to_dict() for b in d['db'].collection('venue_bookings').where('event_id', '==', event_id).stream()]


def test_a_room_booked_for_an_overlapping_time_is_refused_and_no_event_is_made(venue):
    d = venue
    d['db'].collection('venue_bookings').document(_unique('VB')).set({
        'room_id': d['room_id'], 'start_time': f'{DAY} 09:00', 'end_time': f'{DAY} 12:00', 'status': 'confirmed'})
    title = _unique('Clashing Talk')
    resp = _create(d, title, time='10:00')
    assert resp.status_code == 400
    assert 'already booked' in resp.get_data(as_text=True)
    assert _events(d, title) == []


def test_approval_turns_the_tentative_booking_into_confirmed(venue):
    d = venue
    title = _unique('Booked Talk')
    assert _create(d, title).status_code == 302
    [event] = _events(d, title)
    assert event['room_id'] == d['room_id']
    assert [b['status'] for b in _bookings(d, event['id'])] == ['tentative']

    d['admin'].post(f"/admin/events/approve/{event['id']}")
    assert d['db'].collection('events').document(event['id']).get().to_dict()['status'] == 'published'
    assert [b['status'] for b in _bookings(d, event['id'])] == ['confirmed']

    # The confirmed booking now holds the room: a second event at that time is refused
    second = _unique('Second Talk')
    assert _create(d, second).status_code == 400 and _events(d, second) == []


def test_the_calendar_shows_the_room_name_for_the_event(venue):
    d = venue
    title = _unique('Calendar Talk')
    _create(d, title)
    [event] = _events(d, title)
    d['admin'].post(f"/admin/events/approve/{event['id']}")
    room_name = d['db'].collection('rooms').document(d['room_id']).get().to_dict()['name']

    [entry] = [e for e in d['app'].test_client().get('/api/calendar').get_json() if e['id'] == event['id']]
    assert entry['venue'] == room_name
    assert room_name in d['app'].test_client().get('/calendar').get_data(as_text=True)
