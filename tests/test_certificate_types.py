"""
tests/test_certificate_types.py — UPG-122 on the real database layer: who gets
which certificate, and one record per person, event and type.

Absent people get no participation certificate; a multi-day event certifies
only those on enough of its days; each team member gets their own; published
results give position certificates; staff, organiser and speakers get theirs;
an FDP gives completion with hours and an NSS activity extension hours;
faculty carry designation and institution; issuing twice, or at once, never
duplicates (the database refuses).
"""
import threading

import pytest

import services_certificates as certs
from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def ev(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('certspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC', name='Dr. Ananya Rao')
    owner = _login(flask_app, spoc, 'ClubSPOC')

    def make(**fields):
        event_id = _create_event(owner, db, _unique('Cert Event'), '2031-08-08', team=False)
        db.collection('events').document(event_id).update(dict({'status': 'completed', 'staff': []}, **fields))
        return event_id

    def reg(event_id, name, attendance='Present', **fields):
        reg_id = _unique('REG')
        email = fields.pop('email', f"{_unique(name.split()[0].lower())}@test.edu")
        db.collection('registrations').document(reg_id).set(dict({
            'event_id': event_id, 'lead_name': name, 'lead_email': email, 'status': 'Confirmed',
            'attendance': attendance}, **fields))
        return reg_id, email
    return {'app': flask_app, 'db': db, 'spoc': spoc, 'make': make, 'reg': reg}


def _owed(d, event_id, kind=None):
    return [r for r in certs.recipients(d['db'], event_id) if kind is None or r['cert_type'] == kind]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_absent_people_and_too_few_days_get_no_participation_certificate(ev):
    d = ev
    one_day = d['make']()
    _, here = d['reg'](one_day, 'Priya Present')
    _, away = d['reg'](one_day, 'Arun Absent', attendance='Absent')
    assert {r['email'] for r in _owed(d, one_day, 'participation')} == {here}

    five_days = d['make'](date='2031-08-04', end_date='2031-08-08', cert_min_attendance_pct=80)
    days = ['2031-08-04', '2031-08-05', '2031-08-06', '2031-08-07', '2031-08-08']
    _, four = d['reg'](five_days, 'Four Days', attendance_days=days[:4])
    _, three = d['reg'](five_days, 'Three Days', attendance_days=days[:3])
    assert {r['email'] for r in _owed(d, five_days, 'participation')} == {four}
    assert certs.event_days({'date': '2031-08-04', 'end_date': '2031-08-08'}) == 5


def test_check_in_records_each_day_attended(ev):
    d = ev
    event_id = d['make'](status='in_progress')
    reg_id, _ = d['reg'](event_id, 'Daily Visitor', attendance='Pending')
    from routes_ticket import check_in
    actor = {'user_id': d['spoc'], 'role': 'ClubSPOC'}
    with d['app'].test_request_context():
        body, _ = check_in(reg_id, actor)
        assert body['status'] == 'success'
        again, _ = check_in(reg_id, actor)               # the same day: nothing new
        assert again['status'] == 'already_in'
    days = d['db'].collection('registrations').document(reg_id).get().to_dict()['attendance_days']
    assert len(days) == 1
    # The next day counts as another day
    d['db'].collection('registrations').document(reg_id).update({'attendance_days': ['2020-01-01']})
    with d['app'].test_request_context():
        next_day, _ = check_in(reg_id, actor)
    assert next_day['status'] == 'success' and 'day 2' in next_day['message']


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_every_team_member_gets_their_own_certificate(ev):
    d = ev
    event_id = d['make']()
    m1, m2, m3 = (f"{_unique(k)}@test.edu" for k in ('mem1', 'mem2', 'mem3'))
    d['reg'](event_id, 'Lead Lakshmi', team_name='Team Nova', members=[
        {'name': 'Member Manoj', 'email': m1, 'usn': '1SN20CS501'},
        {'name': 'Member Meera', 'email': m2, 'usn': '1SN20CS502'},
        {'name': 'Away Ajay', 'email': m3, 'usn': '1SN20CS503', 'attendance': 'Absent'}])
    owed = _owed(d, event_id, 'participation')
    names = sorted(r['name'] for r in owed)
    assert names == ['Lead Lakshmi', 'Member Manoj', 'Member Meera']
    assert all(r['team'] == 'Team Nova' for r in owed)
    result = certs.issue_event(d['db'], event_id, d['spoc'])
    assert result == {'issued': 4, 'already': 0, 'failed': 0}           # 3 participants + the organiser
    issued = {c['name'] for c in certs.for_event(event_id) if c['cert_type'] == 'participation'}
    assert issued == {'Lead Lakshmi', 'Member Manoj', 'Member Meera'}


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_positions_staff_organiser_and_speakers(ev):
    d = ev
    vol, coord, judge = (f"{_unique(k)}@test.edu" for k in ('vol', 'coord', 'judge'))
    event_id = d['make'](results_published=True, staff=[
        {'name': 'Val', 'email': vol, 'role': 'Volunteer'}, {'name': 'Cora', 'email': coord, 'role': 'EventCoordinator'},
        {'name': 'Jai', 'email': judge, 'role': 'Judge'}],
        details={'speaker': 'Dr. S. Murthy', 'speaker_designation': 'Professor',
                 'resource_persons': 'Prof. B. Rao, HOD CSE\nMs. K. Iyer, Industry'})
    for name, score in (('First Fatima', 9), ('Second Sam', 7), ('Third Tara', 5), ('Fourth Farah', 3)):
        d['reg'](event_id, name, scores={judge: {'total': score}})
    owed = _owed(d, event_id)
    by_type = {}
    for r in owed:
        by_type.setdefault(r['cert_type'], set()).add(r['name'])
    assert by_type['winner'] == {'First Fatima'} and by_type['runner_up'] == {'Second Sam'}
    assert by_type['position'] == {'Third Tara'}
    assert by_type['volunteer'] == {'Val'} and by_type['coordinator'] == {'Cora'} and by_type['judge'] == {'Jai'}
    assert by_type['organiser'] == {'Dr. Ananya Rao'}
    assert by_type['speaker'] == {'Dr. S. Murthy', 'Prof. B. Rao', 'Ms. K. Iyer'}
    assert len(by_type['participation']) == 4                         # the winners took part too
    third = next(r for r in owed if r['cert_type'] == 'position')
    assert certs.wording({'title': 'X'}, third)['phrase'] == 'for securing the 3rd place in'


def test_unpublished_results_give_no_position_certificates(ev):
    d = ev
    event_id = d['make'](results_published=False)
    d['reg'](event_id, 'Top Scorer', scores={'j@test.edu': {'total': 10}})
    assert not [r for r in _owed(d, event_id) if r['cert_type'] in certs.POSITION_TYPES]


def test_fdp_gives_completion_with_hours_and_nss_gives_extension_hours(ev):
    d = ev
    fdp = d['make'](event_type='fdp', activity_hours=12, activity_points=0)
    d['reg'](fdp, 'Prof. Faculty', participant_type='faculty', designation='Assistant Professor',
             institution='RV College of Engineering')
    [completion] = _owed(d, fdp, 'completion')
    assert completion['hours'] == 12.0 and not _owed(d, fdp, 'participation')
    nss = d['make'](event_type='nss_ncc', category='NSS', activity_hours=6, activity_points=5)
    d['reg'](nss, 'Volunteer Vani')
    [ext] = _owed(d, nss, 'extension')
    assert (ext['hours'], ext['points']) == (6.0, 5.0)


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_issuing_twice_never_duplicates(ev):
    d = ev
    event_id = d['make']()
    d['reg'](event_id, 'Once Only')
    first = certs.issue_event(d['db'], event_id, d['spoc'])
    second = certs.issue_event(d['db'], event_id, d['spoc'])
    assert first['issued'] == 2 and second == {'issued': 0, 'already': 2, 'failed': 0}
    assert len(certs.for_event(event_id)) == 2


def test_two_runs_at_once_leave_one_certificate_each(ev):
    d = ev
    event_id = d['make']()
    for i in range(6):
        d['reg'](event_id, f'Racer {i}')
    start, results = threading.Barrier(2), []

    def run():
        start.wait()
        results.append(certs.issue_event(d['db'], event_id, d['spoc']))
    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    rows = certs.for_event(event_id)
    assert len(rows) == 7                                             # 6 participants + the organiser
    assert len({(c['person_key'], c['cert_type']) for c in rows}) == 7
    assert sum(r['issued'] for r in results) == 7 and sum(r['failed'] for r in results) == 0


def test_the_database_refuses_a_second_current_certificate(ev):
    d = ev
    event_id = d['make']()
    who = {'person_key': 'dup@test.edu', 'email': 'dup@test.edu', 'name': 'Dup', 'cert_type': 'participation'}
    assert certs.claim(event_id, who, {}) is not None
    assert certs.claim(event_id, who, {}) is None
    numbers = {c['number'] for c in certs.for_event(event_id)}
    assert len(numbers) == 1 and all(n.startswith('SE-') and len(n) == 19 for n in numbers)


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_faculty_designation_and_event_hours_are_on_the_record(ev):
    d = ev
    event_id = d['make'](event_type='fdp', activity_hours=20, activity_points=4)
    d['reg'](event_id, 'Dr. Kavya Shetty', participant_type='faculty', designation='Associate Professor',
             institution='BMS College of Engineering')
    certs.issue_event(d['db'], event_id, d['spoc'], only=['completion'])
    [cert] = certs.for_event(event_id)
    data = cert['data']
    assert (data['designation'], data['institution']) == ('Associate Professor', 'BMS College of Engineering')
    assert (data['hours'], data['points']) == (20.0, 4.0)
    assert cert['pdf_key'] and len(cert['pdf_sha256']) == 64


def test_numbers_are_random_not_derived_from_the_person():
    numbers = {certs.new_number() for _ in range(500)}
    assert len(numbers) == 500
    assert certs.person_key('A@X.edu') == 'a@x.edu' and certs.person_key(usn='1sn20cs1') == 'usn:1SN20CS1'


def test_a_record_left_without_a_pdf_is_finished_by_a_later_run(ev):
    d = ev
    event_id = d['make']()
    d['reg'](event_id, 'Half Done')
    who = next(r for r in certs.recipients(d['db'], event_id) if r['cert_type'] == 'participation')
    left = certs.claim(event_id, who, certs.wording({}, who))            # a run that died before its PDF
    assert certs.issue_one(event_id, {}, who) is None                    # fresh: another run may be on it
    certs.update(left['id'], issued_at=left['issued_at'] - certs.STALE_AFTER * 2)
    done = certs.issue_one(event_id, {'title': 'X'}, who)
    assert done and done['number'] == left['number'] and done['pdf_sha256']
