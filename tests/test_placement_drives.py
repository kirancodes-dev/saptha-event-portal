"""
tests/test_placement_drives.py — UPG-57 on the real database layer: the roster
import stores CGPA and backlogs; only an admin changes them; registration
refuses a student outside the drive's branch, below its CGPA or over its
backlogs (with the reason), and one not on the roster, and lets an eligible
one register; the organiser's page counts eligible against registered; moving
2 of 3 registrations into round 2 notifies each once and the round-2 export
lists exactly those 2; only the event's staff can move or export.
"""
import csv
import io
import re

import pytest
from werkzeug.security import generate_password_hash

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user


@pytest.fixture
def drive(real_app):
    flask_app, db = real_app
    spoc, admin = f"{_unique('plspoc')}@test.edu", f"{_unique('pladmin')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, admin, 'SuperAdmin')
    admin_client = flask_app.test_client()
    resp = admin_client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                             'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert resp.status_code == 302 and resp.headers['Location'] != '/login'
    owner = _login(flask_app, spoc, 'ClubSPOC')
    branch = _unique('CSE').upper()                     # this drive's branch, so other tests' students don't count
    event_id = _create_event(owner, db, _unique('Infosys Drive'), '2031-06-06', team=False)
    db.collection('events').document(event_id).update({
        'status': 'registration_open', 'is_placement': True,
        'placement': {'company': 'Infosys', 'role': 'Systems Engineer', 'branches': [branch], 'years': ['4'],
                      'min_cgpa': 7.0, 'max_backlogs': 0, 'rounds': []}})
    return {'app': flask_app, 'db': db, 'owner': owner, 'admin': admin_client, 'event_id': event_id, 'branch': branch}


def _import(d, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=['email', 'name', 'usn', 'department', 'year', 'section', 'cgpa',
                                             'backlogs'])
    writer.writeheader()
    writer.writerows(rows)
    resp = d['admin'].post('/admin/users/import_csv', data={'file': (io.BytesIO(buf.getvalue().encode()), 'roster.csv')},
                           content_type='multipart/form-data')
    assert resp.status_code == 302


def _student(d, label, department=None, year='4', cgpa='8.1', backlogs='0'):
    email = f"{_unique(label)}@test.edu"
    _import(d, [{'email': email, 'name': label.title(), 'usn': f'1SN{_unique("")[-6:].upper()}',
                 'department': department or d['branch'], 'year': year, 'section': 'A', 'cgpa': cgpa,
                 'backlogs': backlogs}])
    d['db'].collection('users').document(email).update({'password': generate_password_hash(PASSWORD)})
    return email


def _register(d, email):
    client = _login(d['app'], email, 'Student')
    resp = client.post(f"/forms/submit/{d['event_id']}", data={'privacy_consent': 'yes', 'full_name': 'Placement',
                                                               'email': email, 'phone': '9876543210'},
                       follow_redirects=True)
    regs = [r for r in d['db'].collection('registrations').where('event_id', '==', d['event_id']).stream()
            if r.to_dict().get('lead_email') == email]
    return resp.get_data(as_text=True), regs


# ── Roster and academic record ──────────────────────────────────────────────

def test_the_roster_import_stores_cgpa_and_only_an_admin_changes_it(drive):
    d = drive
    email = _student(d, 'rostered', cgpa='7.45', backlogs='1')
    user = d['db'].collection('users').document(email).get().to_dict()
    assert float(user['cgpa']) == 7.45 and int(user['backlogs']) == 1
    student = _login(d['app'], email, 'Student')
    assert student.get(f'/admin/users/{email}/academics').status_code in (302, 403)
    student.post('/profile/update', data={'cgpa': '9.9', 'backlogs': '0', 'name': 'Rostered'})
    assert float(d['db'].collection('users').document(email).get().to_dict()['cgpa']) == 7.45
    d['admin'].post(f'/admin/users/{email}/academics', data={'cgpa': '8.2', 'backlogs': '0'})
    user = d['db'].collection('users').document(email).get().to_dict()
    assert float(user['cgpa']) == 8.2 and int(user['backlogs']) == 0


# ── Criterion 1 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('label, kwargs, reason', [
    ('wrongbranch', {'department': 'MECH'}, 'students; your branch on record is MECH'),
    ('lowcgpa', {'cgpa': '6.5'}, 'needs a CGPA of at least 7; yours on record is 6.5'),
    ('backlogs', {'backlogs': '2'}, 'allows at most 0 active backlog(s); you have 2 on record'),
    ('wrongyear', {'year': '2'}, 'your year on record is 2'),
])
def test_an_ineligible_student_is_refused_with_the_reason(drive, label, kwargs, reason):
    d = drive
    page, regs = _register(d, _student(d, label, **kwargs))
    assert reason in page and regs == []


def test_someone_not_on_the_roster_is_refused_and_no_account_is_made(drive):
    d = drive
    stranger = f"{_unique('stranger')}@test.edu"
    resp = d['app'].test_client().post(f"/forms/submit/{d['event_id']}", data={
        'privacy_consent': 'yes', 'full_name': 'Stranger', 'email': stranger, 'phone': '9876543210'},
        follow_redirects=True)
    assert 'for students on the university roster' in resp.get_data(as_text=True)
    assert not d['db'].collection('users').document(stranger).get().exists


def test_an_eligible_student_registers(drive):
    d = drive
    _, regs = _register(d, _student(d, 'eligible'))
    assert len(regs) == 1


# ── Criteria 2 and 3 ────────────────────────────────────────────────────────

def test_round_2_holds_the_two_moved_and_only_staff_can_move_or_export(drive):
    d = drive
    emails = [_student(d, k) for k in ('asha', 'bala', 'chen')]
    _student(d, 'eligiblebutabsent')                  # on the roster and eligible, not registered
    reg_ids = {e: _register(d, e)[1][0].id for e in emails}
    page = d['owner'].get(f"/placement/{d['event_id']}").get_data(as_text=True)
    assert re_count(page, 'eligible', 4) and re_count(page, 'registered', 3)

    for name in ('Aptitude', 'Technical'):
        d['owner'].post(f"/placement/{d['event_id']}/rounds", data={'name': name})
    moved = [reg_ids[emails[0]], reg_ids[emails[1]]]
    for _ in range(2):                                # moving twice notifies once
        d['owner'].post(f"/placement/{d['event_id']}/move", data={'round_id': 'r2', 'status': 'shortlisted',
                                                                 'reg_ids': moved})
    export = d['owner'].get(f"/placement/{d['event_id']}/export/r2.csv?status=shortlisted")
    rows = list(csv.DictReader(io.StringIO(export.get_data(as_text=True))))
    assert sorted(r['Email'] for r in rows) == sorted(emails[:2]) and {r['Result'] for r in rows} == {'shortlisted'}
    for email in emails:
        notices = [n for n in d['db'].collection('notifications_v2').where('user_email', '==', email).stream()
                   if 'Technical' in str((n.to_dict() or {}).get('title'))]
        assert len(notices) == (1 if email in emails[:2] else 0), email
    xlsx = d['owner'].get(f"/placement/{d['event_id']}/export/r2.xlsx")
    assert xlsx.status_code == 200 and xlsx.data[:2] == b'PK'

    # Another SPOC and a student can't move or export
    other = f"{_unique('otherspoc')}@test.edu"
    _user(d['db'], other, 'ClubSPOC')
    for client in (_login(d['app'], other, 'ClubSPOC'), _login(d['app'], emails[2], 'Student')):
        assert client.post(f"/placement/{d['event_id']}/move", data={'round_id': 'r2', 'status': 'shortlisted',
                                                                     'reg_ids': [reg_ids[emails[2]]]}).status_code == 403
        assert client.get(f"/placement/{d['event_id']}/export/r2.csv").status_code == 403
        assert client.get(f"/placement/{d['event_id']}").status_code == 403
    third = d['db'].collection('registrations').document(reg_ids[emails[2]]).get().to_dict()
    assert not (third.get('placement_rounds') or {}).get('r2')


def re_count(page, word, n):
    """The page shows the number n next to the word ("4 eligible" or "Eligible: 4")."""
    text = re.sub(r'<[^>]+>', ' ', page)
    return re.search(rf'\b{n}\b\s*{word}|{word}\D{{0,40}}\b{n}\b', text, re.I) is not None
