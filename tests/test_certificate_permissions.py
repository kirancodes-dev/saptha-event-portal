"""
tests/test_certificate_permissions.py — UPG-129 on the real database layer:
who may issue, revoke and approve corrections, and who may download. Only the
event's owner, a Super Admin and someone holding `issue_certificates` on that
event may issue, revoke or approve; another SPOC, the event's coordinator,
judge and volunteer, and students may not. A student downloads their own
certificate and gets 403 for someone else's.
"""
import pytest

import services_certificate_changes as changes
import services_certificate_runs as runs
import services_certificates as certs
from tests.test_certificate_types import _signature
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

ALLOWED = ('owner', 'admin', 'holder')
DENIED = ('other_spoc', 'coordinator', 'judge', 'volunteer', 'student')


@pytest.fixture
def world(real_app, monkeypatch):
    import services_signatories
    flask_app, db = real_app
    monkeypatch.setenv('TASK_INLINE_TIMEOUT', '120')
    roles = {'owner': 'ClubSPOC', 'other_spoc': 'ClubSPOC', 'coordinator': 'EventCoordinator', 'judge': 'Judge',
             'volunteer': 'Volunteer', 'student': 'Student', 'holder': 'ClubSPOC', 'admin': 'SuperAdmin'}
    email = {k: f"{_unique('perm' + k)}@test.edu" for k in roles}
    for key, role in roles.items():
        _user(db, email[key], role)
    owner = _login(flask_app, email['owner'], 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Guarded Event'), '2030-10-10', team=False)
    db.collection('events').document(event_id).update({'status': 'completed', 'staff': [
        {'name': 'Cora', 'email': email['coordinator'], 'role': 'EventCoordinator'},
        {'name': 'Jai', 'email': email['judge'], 'role': 'Judge'},
        {'name': 'Vik', 'email': email['volunteer'], 'role': 'Volunteer'}]})
    # issue_certificates on this event only, through an event-scoped role (services_permission)
    db.collection('role_assignments').document(_unique('ra')).set({
        'user_id': email['holder'], 'role': 'EventOrganizer', 'scope_type': 'event', 'scope_id': event_id})
    services_signatories.add(db, event_id, name='Dr. A. Kumar', title='Principal', image=_signature(),
                             actor=email['owner'])
    students = []
    for i in range(20):                              # two each for 8 roles to revoke and correct
        addr = email['student'] if i == 0 else f"{_unique('permp')}@test.edu"
        db.collection('registrations').document(_unique('REG')).set({
            'event_id': event_id, 'lead_name': f'Person {i:02d}', 'lead_email': addr, 'status': 'Confirmed',
            'attendance': 'Present'})
        students.append(addr)
    certs.issue_event(db, event_id, email['owner'], only=['participation'])
    runs.start(db, event_id, email['owner'])            # a run on record, to try retrying

    clients = {}
    for key, role in roles.items():
        if key == 'admin':
            c = flask_app.test_client()
            c.post('/login', data={'role': 'SuperAdmin', 'email': email['admin'], 'password': PASSWORD,
                                   'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
            clients[key] = c
        else:
            clients[key] = _login(flask_app, email[key], role)
    by_email = {c['email']: c for c in certs.for_event(event_id)}
    return {'db': db, 'event_id': event_id, 'clients': clients, 'email': email,
            'certs': [by_email[a] for a in students]}


def test_only_the_owner_an_admin_and_an_issue_certificates_holder_issue_revoke_and_approve(world):
    d = world
    event_id, clients, db = d['event_id'], d['clients'], d['db']
    pool = iter(d['certs'][1:])          # a certificate each to revoke or correct (not the student's own)

    for who in DENIED + ALLOWED:
        client = clients[who]
        allowed = who in ALLOWED
        runs_before = len(runs.for_event(db, event_id))
        resp = client.post(f'/certificates/events/{event_id}/issue')
        assert (resp.status_code != 403) == allowed, (who, 'issue', resp.status_code)
        assert len(runs.for_event(db, event_id)) == runs_before + (1 if allowed else 0), (who, 'issue')

        retry_run = runs.for_event(db, event_id)[0]['id']
        assert (client.post(f'/certificates/events/{event_id}/runs/{retry_run}/retry').status_code != 403) == allowed, who

        owed = next(r for r in certs.recipients(db, event_id) if r['cert_type'] == 'organiser')
        resp = client.post(f'/certificates/events/{event_id}/issue_one',
                           data={'pair': f"{owed['person_key']}|organiser"})
        assert (resp.status_code != 403) == allowed, (who, 'issue_one')

        target = next(pool)
        resp = client.post(f'/certificates/events/{event_id}/revoke', data={'number': target['number'], 'reason': 'test'})
        assert (resp.status_code != 403) == allowed, (who, 'revoke')
        assert certs.by_number(target['number'])['status'] == ('revoked' if allowed else 'valid'), (who, 'revoke')

        target = next(pool)
        request = changes.request_correction(db, target['number'], target['email'], target['name'] + ' Fixed')
        resp = client.post(f"/certificates/events/{event_id}/corrections/{request['id']}/approve")
        assert (resp.status_code != 403) == allowed, (who, 'approve')
        assert certs.by_number(target['number'])['version'] == (2 if allowed else 1), (who, 'approve')

        resp = client.post(f"/certificates/events/{event_id}/auto", data={'auto': 'off'})
        assert (resp.status_code != 403) == allowed, (who, 'auto')

        page = client.get(f'/certificates/events/{event_id}')
        assert (page.status_code == 200) == allowed, (who, 'page')


def test_a_student_downloads_only_their_own(world):
    d = world
    own, someone_else = d['certs'][0], d['certs'][1]
    student = d['clients']['student']
    for kind in ('pdf', 'png'):
        assert student.get(f"/certificates/c/{own['number']}/{kind}").status_code == 200
        assert student.get(f"/certificates/c/{someone_else['number']}/{kind}").status_code == 403
    for who in ('other_spoc', 'coordinator', 'judge', 'volunteer'):
        assert d['clients'][who].get(f"/certificates/c/{own['number']}/pdf").status_code == 403, who
    for who in ALLOWED:
        assert d['clients'][who].get(f"/certificates/c/{own['number']}/pdf").status_code == 200, who
