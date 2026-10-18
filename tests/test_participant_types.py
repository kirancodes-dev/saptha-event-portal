"""
tests/test_participant_types.py — UPG-12 on the real database layer (the
certificate part is deferred): faculty and external participants register with
their designation and institution, get an account of that type and open their
ticket; the event's allowed types are enforced; the affiliation is required only
of faculty and external participants; the department export filters by type;
the admin analytics split counts by type.
"""
import csv
import datetime
import io

import pytest
from werkzeug.security import generate_password_hash

from services_insights import build
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user


@pytest.fixture
def events(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('ptspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()

    def make(allowed):
        event_id = _create_event(owner, db, _unique('FDP'), day, team=False)
        db.collection('events').document(event_id).update({'status': 'registration_open', 'allowed_participants': allowed})
        return event_id
    return flask_app, db, make


def _register(flask_app, event_id, email, **extra):
    data = {'privacy_consent': 'yes', 'full_name': 'Dr. Asha Rao', 'email': email, 'phone': '9876543210', **extra}
    return flask_app.test_client().post(f'/forms/submit/{event_id}', data=data)


def _regs(db, event_id):
    return [d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream()]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_a_faculty_registration_makes_a_faculty_account_that_opens_its_ticket(events):
    flask_app, db, make = events
    event_id = make(['faculty'])
    email = f"{_unique('faculty')}@college.example"
    resp = _register(flask_app, event_id, email, participant_type='faculty', designation='Associate Professor',
                     institution='Sapthagiri NPS University')
    assert resp.headers['Location'] == '/registration/confirmed'
    [reg] = _regs(db, event_id)
    assert reg['participant_type'] == 'faculty' and reg['designation'] == 'Associate Professor'
    user = db.collection('users').document(email).get().to_dict()
    assert user['participant_type'] == 'faculty' and user['institution'] == 'Sapthagiri NPS University'

    # They set their password (the emailed link) and open their ticket like any participant
    db.collection('users').document(email).update({'password': generate_password_hash(PASSWORD, method='pbkdf2:sha256'),
                                                   'email_verified': True, 'needs_password_reset': False})
    client = _login(flask_app, email, user.get('role', 'Student'))
    doc_id = next(iter(db.collection('registrations').where('event_id', '==', event_id).stream())).id
    page = client.get(f'/ticket/{doc_id}')
    assert page.status_code == 200 and 'Dr. Asha Rao' in page.get_data(as_text=True)


# ── To test later: allowed types and the affiliation fields ────────────────

def test_the_events_allowed_types_are_enforced(events):
    flask_app, db, make = events
    event_id = make(['faculty'])
    resp = _register(flask_app, event_id, f"{_unique('stud')}@test.edu", participant_type='student')
    assert resp.status_code == 302 and resp.headers['Location'] == f'/forms/register/{event_id}'
    assert _regs(db, event_id) == []


def test_the_affiliation_is_required_only_for_faculty_and_external(events):
    flask_app, db, make = events
    event_id = make(['student', 'faculty', 'external'])
    for ptype in ('faculty', 'external'):
        resp = _register(flask_app, event_id, f"{_unique(ptype)}@test.edu", participant_type=ptype)
        assert resp.headers['Location'] == f'/forms/register/{event_id}', ptype      # refused without them
    assert _regs(db, event_id) == []
    ok = _register(flask_app, event_id, f"{_unique('stud')}@test.edu", participant_type='student', usn='1SN20CS015')
    assert ok.headers['Location'] == '/registration/confirmed'
    assert [r['participant_type'] for r in _regs(db, event_id)] == ['student']


def test_the_department_export_filters_by_participant_type(events):
    flask_app, db, make = events
    faculty, student = f"{_unique('fx')}@test.edu", f"{_unique('sx')}@test.edu"
    dept = _unique('DEPT').upper()
    _user(db, faculty, 'Student')
    _user(db, student, 'Student')
    db.collection('users').document(faculty).update({'participant_type': 'faculty', 'department': dept, 'email': faculty})
    db.collection('users').document(student).update({'department': dept, 'email': student})
    admin = f"{_unique('ptadmin')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    client = flask_app.test_client()
    client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})

    def emails(query):
        body = client.get(f'/admin/export/department_activity?department={dept}{query}').get_data(as_text=True)
        return {r['Email']: r['Participant Type'] for r in csv.DictReader(io.StringIO(body))}
    assert emails('') == {faculty: 'faculty', student: 'student'}
    assert emails('&participant_type=faculty') == {faculty: 'faculty'}


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_analytics_split_counts_by_participant_type():
    today = datetime.date(2030, 6, 10)
    events = [{'id': 'e1', 'title': 'FDP', 'category': 'Academic', 'date': '2030-06-05', 'status': 'completed'}]
    regs = [dict(event_id='e1', status='Confirmed', registered_at='2030-06-01', participant_type=t, attendance=a)
            for t, a in (('faculty', 'Present'), ('faculty', 'Pending'), ('external', 'Present'), (None, 'Present'))]
    split = {p['type']: (p['registered'], p['attended']) for p in build(events, regs, period='all', today=today)['participants']}
    assert split == {'Faculty': (2, 1), 'External': (1, 1), 'Students': (1, 1)}   # the page's labels


def test_the_admin_analytics_page_shows_the_split(events):
    flask_app, db, make = events
    event_id = make(['faculty'])
    _register(flask_app, event_id, f"{_unique('fac2')}@college.example", participant_type='faculty',
              designation='Professor', institution='SNPSU')
    admin = f"{_unique('ptadmin2')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    client = flask_app.test_client()
    client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    page = client.get('/admin/analytics?period=all').get_data(as_text=True)
    assert 'Who registered' in page and '<td>Faculty</td>' in page
