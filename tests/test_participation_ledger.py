"""
tests/test_participation_ledger.py — UPG-11 on the real database layer: an event
worth 2 hours / 5 points (set on the create form) credits a Present attendee and
not an Absent one; the ledger adds up three events; the department export lists
every student in the department with their totals. (The hours on the
certificate are deferred with the rest of the certificate work.)
"""
import csv
import datetime
import io

import pytest

from tests.test_integration_flow import PASSWORD, _login, _unique, _user


@pytest.fixture
def ledger(real_app):
    flask_app, db = real_app
    spoc, admin = f"{_unique('ledspoc')}@test.edu", f"{_unique('ledadmin')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, admin, 'SuperAdmin')
    admin_client = flask_app.test_client()
    resp = admin_client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                             'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert resp.status_code == 302 and resp.headers['Location'] != '/login'
    dept = _unique('Dept')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = datetime.date.today().isoformat()          # scanning opens on the event day

    def event(points, hours):
        title = _unique('Ledger Drive')
        resp = owner.post('/spoc/create_event', data={
            'title': title, 'category': 'Technical', 'description': 'desc', 'rules': 'rules',
            'date': day, 'time': '10:00', 'reg_deadline': day, 'venue': 'Hall A',
            'participation_type': 'Individual', 'team_min': '1', 'team_max': '1', 'max_participants': '50',
            'reg_fee': '0', 'visibility': 'public', 'activity_points': str(points), 'activity_hours': str(hours)})
        assert resp.status_code == 302
        [doc] = db.collection('events').where('title', '==', title).stream()
        db.collection('events').document(doc.id).update({'status': 'registration_open'})
        return doc.id

    def student(name, usn, department=dept):
        email = f"{_unique('ledstu')}@test.edu"
        _user(db, email, 'Student', name=name)
        db.collection('users').document(email).update({'department': department, 'usn': usn, 'email': email})
        return email, _login(flask_app, email, 'Student')

    def register(email, client, event_id, usn):
        client.post(f'/forms/submit/{event_id}', data={
            'privacy_consent': 'yes', 'full_name': 'Led Ger', 'email': email, 'phone': '9876543210', 'usn': usn})
        [reg] = db.collection('registrations').where('event_id', '==', event_id).where('lead_email', '==', email).stream()
        return reg.id

    def present(event_id, reg_id):
        resp = owner.post(f'/spoc/api/checkin/{event_id}/{reg_id}', json={'round': 1})
        assert resp.status_code == 200, resp.data

    def absent(reg_id):
        admin_client.post(f'/admin/registrations/{reg_id}/attendance', data={'attendance': 'absent'})

    return {'app': flask_app, 'db': db, 'dept': dept, 'admin': admin_client, 'owner': owner, 'event': event,
            'student': student, 'register': register, 'present': present, 'absent': absent}


def _ledger(client):
    return client.get('/participant/api/ledger').get_json()


def test_a_present_attendee_is_credited_and_an_absent_one_is_not(ledger):
    d = ledger
    event_id = d['event'](5, 2)
    assert d['db'].collection('events').document(event_id).get().to_dict()['activity_points'] == 5
    here, here_client = d['student']('Priya Present', '1SN20CS101')
    away, away_client = d['student']('Arun Absent', '1SN20CS102')
    here_reg = d['register'](here, here_client, event_id, '1SN20CS101')
    d['present'](event_id, here_reg)
    d['absent'](d['register'](away, away_client, event_id, '1SN20CS102'))

    got = _ledger(here_client)
    assert (got['total_points'], got['total_hours']) == (5.0, 2.0)
    missed = _ledger(away_client)
    assert (missed['total_points'], missed['total_hours']) == (0.0, 0.0)
    assert [e['attendance'] for e in missed['entries']] == ['Absent']

    # A second scan of the same ticket doesn't credit it twice
    d['owner'].post(f'/spoc/api/checkin/{event_id}/{here_reg}', json={'round': 1})
    assert _ledger(here_client)['total_points'] == 5.0


def test_the_ledger_adds_up_three_events(ledger):
    d = ledger
    email, client = d['student']('Tara Three', '1SN20CS103')
    for points, hours in ((5, 2), (3, 1.5), (10, 4)):
        event_id = d['event'](points, hours)
        d['present'](event_id, d['register'](email, client, event_id, '1SN20CS103'))
    skipped = d['event'](7, 3)                       # registered, never attended
    d['register'](email, client, skipped, '1SN20CS103')

    got = _ledger(client)
    assert (got['total_points'], got['total_hours']) == (18.0, 7.5)
    assert len(got['entries']) == 4
    page = client.get('/participant/ledger').get_data(as_text=True)
    assert '>18.0<' in page and '>7.5<' in page


def test_the_department_export_lists_every_student_with_totals(ledger):
    d = ledger
    event_id = d['event'](5, 2)
    busy, busy_client = d['student']('Bina Busy', '1SN20CS104')
    idle, _ = d['student']('Ivan Idle', '1SN20CS105')
    other, other_client = d['student']('Omar Other', '1SN20CS106', department=_unique('OtherDept'))
    d['present'](event_id, d['register'](busy, busy_client, event_id, '1SN20CS104'))
    d['present'](event_id, d['register'](other, other_client, event_id, '1SN20CS106'))

    resp = d['admin'].get(f"/admin/export/department_activity?department={d['dept']}")
    assert resp.status_code == 200
    rows = {r['Email']: r for r in csv.DictReader(io.StringIO(resp.get_data(as_text=True)))}
    assert set(rows) == {busy, idle}                 # every student in the department, no one else
    assert (rows[busy]['Events Attended'], float(rows[busy]['Total Activity Points']),
            float(rows[busy]['Total Activity Hours'])) == ('1', 5.0, 2.0)
    assert (rows[idle]['Events Attended'], float(rows[idle]['Total Activity Points'])) == ('0', 0.0)
