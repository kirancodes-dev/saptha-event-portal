"""
tests/test_db_documents_newer_tables.py — BLK-06b on the real SQL database
layer: documents in the newer tables, team members and judges' scores read
back exactly as written.
"""
import uuid

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def db(real_app):
    return real_app[1]


def _id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _assert_round_trip(db, collection, doc_id, written):
    stored = db.collection(collection).document(doc_id).get().to_dict()
    for key, value in written.items():
        assert stored.get(key) == value, (collection, key, stored.get(key), value)


# ── Criterion 1 (second half) ──────────────────────────────────────────────

def test_newer_tables_and_tickets_keep_every_field(db):
    extra = {'notes': 'Ground floor, near the lift', 'contact': {'name': 'Estate Office', 'ext': '2201'},
             'tags': ['accessible', 'projector']}
    _, ev = db.collection('events').add({'title': 'Round-trip', 'date': '2030-01-01'})
    unit, campus, building, room, booking, ra = (_id('unit'), _id('campus'), _id('block'),
                                                 _id('room'), _id('booking'), _id('ra'))
    docs = [
        ('org_units', unit, {'organization_id': 'default', 'parent_id': 'central', 'type': 'club',
                             'name': 'Robotics Club', 'slug': unit, **extra}),
        ('role_assignments', ra, {'user_id': 'spoc@test.edu', 'role': 'UnitAdmin', 'scope_type': 'unit',
                                  'scope_id': unit, 'granted_by': 'admin@test.edu', **extra}),
        ('campuses', campus, {'name': 'North Campus', 'slug': campus, **extra}),
        ('buildings', building, {'campus_id': campus, 'name': 'Block N', **extra}),
        ('rooms', room, {'building_id': building, 'name': 'Lab N1', 'room_number': 'N1', 'capacity': 40, **extra}),
        ('venue_bookings', booking, {'room_id': room, 'event_id': ev.id, 'purpose': 'Hackathon finals',
                                     'start_time': '2030-01-01T10:00:00', 'end_time': '2030-01-01T12:00:00',
                                     **extra}),
    ]
    for collection, doc_id, data in docs:
        db.collection(collection).document(doc_id).set(data)
    for collection, doc_id, data in docs:
        _assert_round_trip(db, collection, doc_id, {k: data[k] for k in ('notes', 'contact', 'tags')})
    _assert_round_trip(db, 'role_assignments', ra, {'granted_by': 'admin@test.edu'})
    _assert_round_trip(db, 'venue_bookings', booking, {'purpose': 'Hackathon finals'})

    # Updates merge into the shadow instead of dropping it
    db.collection('rooms').document(room).update({'capacity': 45, 'last_inspected': '2030-01-02'})
    _assert_round_trip(db, 'rooms', room, {'capacity': 45, 'last_inspected': '2030-01-02', 'notes': extra['notes']})

    reg = db.collection('registrations').document(_id('REG'))
    reg.set({'event_id': ev.id, 'lead_email': 's@test.edu', 'lead_name': 'Stu Dent'})
    ticket = _id('TKT')
    ticket_data = {'event_id': ev.id, 'registration_id': reg.id, 'user_email': 's@test.edu',
                   'ticket_type': 'VIP', 'ticket_code': ticket, 'status': 'active',
                   'lead_name': 'Stu Dent', 'perks': ['lounge', 'front row']}
    db.collection('tickets').document(ticket).set(ticket_data)
    _assert_round_trip(db, 'tickets', ticket, {k: ticket_data[k] for k in ('ticket_type', 'lead_name', 'perks')})
    fresh = db.collection('tickets').document(ticket).get().to_dict()
    assert fresh['checked_in'] is False and fresh['checked_in_at'] is None  # a new ticket isn't checked in


def test_team_members_keep_their_role_and_attendance(db):
    _, ev = db.collection('events').add({'title': 'Team event', 'date': '2030-01-01'})
    reg = db.collection('registrations').document(_id('REG'))
    members = [
        {'role': 'Lead', 'name': 'Asha', 'email': 'asha@test.edu', 'usn': '1SN20CS001', 'phone': '9000000001'},
        {'role': 'Member', 'name': 'Ravi', 'email': 'ravi@test.edu', 'usn': '1SN20CS002', 'whatsapp': '9000000002'},
    ]
    reg.set({'event_id': ev.id, 'lead_email': 'asha@test.edu', 'lead_name': 'Asha', 'members': members})
    assert sorted(reg.get().to_dict()['members'], key=lambda m: m['name']) == members

    # Granular attendance (coordinator scanner) writes per-member attendance
    marked = [dict(m, attendance='Present' if m['usn'] == '1SN20CS001' else 'Absent') for m in members]
    reg.update({'members': marked, 'attendance': 'Present'})
    back = {m['usn']: m for m in reg.get().to_dict()['members']}
    assert back['1SN20CS001']['attendance'] == 'Present'
    assert back['1SN20CS002']['attendance'] == 'Absent'
    assert back['1SN20CS002']['whatsapp'] == '9000000002'


# ── Criterion 9 ─────────────────────────────────────────────────────────────

def test_scores_read_back_with_the_keys_the_judge_route_wrote(real_app):
    flask_app, db = real_app
    spoc, judges, student = (f"{_unique('spoc')}@test.edu",
                             [f"{_unique('judge')}@test.edu" for _ in range(2)],
                             f"{_unique('stu')}@test.edu")
    _user(db, spoc, 'ClubSPOC')
    _user(db, student, 'Student')
    for j in judges:
        _user(db, j, 'Judge')
    spoc_client = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(spoc_client, db, _unique('Score Keys'), '2030-06-01', fee=0, team=False)
    db.collection('events').document(event_id).update({
        'judging_criteria': ['Innovation', 'Execution'], 'open_hall_mode': True,
        'staff': [{'name': 'J', 'email': j, 'role': 'Judge'} for j in judges]})
    _login(flask_app, student, 'Student').post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes',
        'full_name': 'Stu Dent', 'email': student, 'phone': '9876543210', 'usn': '1SN20CS200'})
    reg_id = next(iter(db.collection('registrations').where('event_id', '==', event_id).stream())).id
    db.collection('registrations').document(reg_id).update({'attendance': 'Present'})

    for judge, (a, b) in zip(judges, [(8, 6), (9, 9)]):
        assert _login(flask_app, judge, 'Judge').post(f'/judge/submit_score/{reg_id}', data={
            'score_innovation': str(a), 'score_execution': str(b), 'remarks': f'by {judge}'}).status_code == 302

    scores = db.collection('registrations').document(reg_id).get().to_dict()['scores']
    assert set(scores) == set(judges)  # the second judge didn't replace the first
    first = scores[judges[0]]
    assert set(first) == {'details', 'total', 'raw_total', 'remarks', 'judge_name', 'submitted_at'}
    assert first['details'] == {'Innovation': 8, 'Execution': 6}
    assert first['total'] == 7.0 and first['raw_total'] == 14
    assert first['remarks'] == f'by {judges[0]}'
    assert scores[judges[1]]['details'] == {'Innovation': 9, 'Execution': 9}
