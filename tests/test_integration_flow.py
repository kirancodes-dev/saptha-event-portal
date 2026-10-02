"""
tests/test_integration_flow.py — End-to-end HTTP flows against the real SQL
database layer (temporary SQLite set up in conftest.py; no mocked db).

Covers the paths the frontend drives: login, SPOC event creation, student
registration through the dynamic form, paid-event checkout, SPOC check-in,
coordinator views, and SPOC data isolation.
"""
import datetime
import uuid

import pytest
from werkzeug.security import generate_password_hash

PASSWORD = 'Str0ng!Pass#1'

# real_app (the real SQL adapter, no outbound mail) lives in tests/conftest.py

def _user(db, email, role, name='Test User'):
    db.collection('users').document(email).set({
        'name': name, 'role': role, 'category': 'Technical',
        'password': generate_password_hash(PASSWORD),
    }, merge=False)


def _login(flask_app, email, role):
    client = flask_app.test_client()
    resp = client.post('/login', data={'role': role, 'email': email, 'password': PASSWORD})
    assert resp.status_code == 302, resp.data[:300]
    # A failed login also redirects (back to /login); make sure this one worked
    assert resp.headers['Location'] != '/login', f"login failed for {email} as {role}"
    with client.session_transaction() as sess:
        assert sess.get('user_id') == email
    return client


def _create_event(client, db, title, date, fee=0, team=True):
    resp = client.post('/spoc/create_event', data={
        'title': title, 'category': 'Technical', 'description': 'desc', 'rules': 'rules',
        'date': date, 'time': '10:00', 'reg_deadline': date, 'venue': 'Hall A',
        'participation_type': 'Team' if team else 'Individual',
        'team_min': '2' if team else '1', 'team_max': '4' if team else '1',
        'max_participants': '50', 'reg_fee': str(fee),
        'prize_1': '5000', 'prize_2': '3000', 'prize_3': '1000', 'visibility': 'public',
    })
    assert resp.status_code == 302
    matches = [d for d in db.collection('events').where('title', '==', title).stream()]
    assert len(matches) == 1
    return matches[0].id


def _unique(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def test_spoc_event_keeps_all_settings_and_is_isolated(real_app):
    flask_app, db = real_app
    spoc_a, spoc_b = f"{_unique('spoca')}@test.edu", f"{_unique('spocb')}@test.edu"
    _user(db, spoc_a, 'ClubSPOC')
    _user(db, spoc_b, 'ClubSPOC')
    client_a = _login(flask_app, spoc_a, 'ClubSPOC')
    client_b = _login(flask_app, spoc_b, 'ClubSPOC')

    title_a, title_b = _unique('Hack A'), _unique('Hack B')
    event_a = _create_event(client_a, db, title_a, '2030-05-05', fee=100)
    event_b = _create_event(client_b, db, title_b, '2030-05-06')

    ev = db.collection('events').document(event_a).get().to_dict()
    assert ev['spoc_id'] == spoc_a
    assert ev['entry_fee'] == 100.0
    assert ev['fees'] == {'regular': 100}
    assert ev['is_team_event'] is True
    assert ev['limits']['team_max'] == 4
    assert ev['reg_deadline'] == '2030-05-05'
    assert ev['prizes']['1st'] == '5000'

    dashboard = client_a.get('/spoc/dashboard')
    assert dashboard.status_code == 200
    assert title_a.encode() in dashboard.data
    assert title_b.encode() not in dashboard.data

    assert client_a.get(f'/spoc/scan/{event_a}').status_code == 200
    assert client_a.get(f'/spoc/scan/{event_b}').status_code == 403  # not their event (scoped can() check)


def test_student_registers_for_free_team_event_and_spoc_checks_in(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('spoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    spoc_client = _login(flask_app, spoc, 'ClubSPOC')
    today = datetime.date.today().isoformat()
    event_id = _create_event(spoc_client, db, _unique('Free Hack'), today, fee=0)

    student = flask_app.test_client()
    form = student.get(f'/forms/register/{event_id}')
    assert form.status_code == 200
    assert b'name="team_name"' in form.data  # team event renders team fields

    email = f"{_unique('stu')}@test.edu"
    resp = student.post(f'/forms/submit/{event_id}', data={
        'full_name': 'Stu Dent', 'email': email, 'phone': '9876543210',
        'usn': '1SN20CS001', 'team_name': 'Team Rocket',
    })
    assert resp.status_code == 302

    regs = list(db.collection('registrations').where('event_id', '==', event_id).stream())
    assert len(regs) == 1
    reg = regs[0].to_dict()
    assert reg['lead_email'] == email
    assert reg['team_name'] == 'Team Rocket'
    assert reg['status'] == 'Confirmed'
    assert db.collection('events').document(event_id).get().to_dict()['registration_count'] == 1
    assert db.collection('users').document(email).get().to_dict()['role'] == 'Student'

    # Duplicate registration is rejected
    student.post(f'/forms/submit/{event_id}', data={
        'full_name': 'Stu Dent', 'email': email, 'phone': '9876543210',
        'usn': '1SN20CS001', 'team_name': 'Team Rocket',
    })
    assert len(list(db.collection('registrations').where('event_id', '==', event_id).stream())) == 1

    # SPOC check-in at the gate
    checkin = spoc_client.post(f'/spoc/api/checkin/{event_id}/{regs[0].id}', json={'round': 1})
    assert checkin.status_code == 200, checkin.data
    assert checkin.get_json()['status'] in ('success', 'ok', 'checked_in')
    assert db.collection('registrations').document(regs[0].id).get().to_dict()['attendance'] == 'Present'


def test_paid_event_sends_student_to_checkout(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('spoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    spoc_client = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(spoc_client, db, _unique('Paid Hack'), '2030-06-01', fee=250, team=False)

    student = flask_app.test_client()
    resp = student.post(f'/forms/submit/{event_id}', data={
        'full_name': 'Pay Er', 'email': f"{_unique('payer')}@test.edu",
        'phone': '9876543210', 'usn': '1SN20CS002',
    })
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith(f'/payment/checkout/{event_id}')
    # Nothing is confirmed until payment succeeds
    assert list(db.collection('registrations').where('event_id', '==', event_id).stream()) == []


def test_unassigned_judge_gets_403_and_nothing_is_saved(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('spoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Judge Hack'), '2030-08-01')
    reg_id = f"REG-{_unique('j')}"
    db.collection('registrations').document(reg_id).set({
        'event_id': event_id, 'lead_email': 'team@test.edu', 'lead_name': 'Team', 'attendance': 'Present'})

    judge = f"{_unique('judge')}@test.edu"
    _user(db, judge, 'Judge')
    judge_client = _login(flask_app, judge, 'Judge')
    assert judge_client.post(f'/judge/submit_score/{reg_id}', data={'score_overall_score': '9'}).status_code == 403
    assert judge_client.post(f'/judge/score_inline/{reg_id}', json={'scores': {'Overall Score': 9}}).status_code == 403
    assert not db.collection('registrations').document(reg_id).get().to_dict().get('scores')


def test_coordinator_and_shared_pages_render(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('spoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    spoc_client = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(spoc_client, db, _unique('Coord Hack'), '2030-07-01')

    coord = f"{_unique('coord')}@test.edu"
    _user(db, coord, 'Coordinator')
    coord_client = _login(flask_app, coord, 'EventCoordinator')
    # Registrations are scoped: a coordinator sees only events they are assigned to
    assert coord_client.get(f'/coordinator/registrations/{event_id}').status_code == 403
    spoc_client.post(f'/spoc/assign_coordinator/{event_id}', data={'coordinator_email': coord})
    page = coord_client.get(f'/coordinator/registrations/{event_id}')
    assert page.status_code == 200
    assert b'Registrations' in page.data

    assert spoc_client.get('/dashboard').headers['Location'].endswith('/spoc/dashboard')
    assert flask_app.test_client().get('/dashboard').headers['Location'].endswith('/login')
    assert flask_app.test_client().get('/payment/failed?reason=declined').status_code == 200
    assert spoc_client.get(f'/feedback/view/{event_id}').headers['Location'].endswith(f'/feedback/analytics/{event_id}')


def test_email_diagnostic_requires_super_admin(real_app):
    flask_app, db = real_app
    assert flask_app.test_client().get('/diag/email?to=x@example.com').status_code == 403
    spoc = f"{_unique('spoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    assert _login(flask_app, spoc, 'ClubSPOC').get('/diag/email?to=x@example.com').status_code == 403


def test_removed_debug_and_legacy_endpoints(real_app):
    flask_app, _ = real_app
    client = flask_app.test_client()
    assert client.get('/debug-modal').status_code == 404
    assert client.post('/api/auth/login', json={}).status_code in (404, 405)


def test_production_config_requires_real_secrets():
    from config import validate_production_config
    with pytest.raises(RuntimeError):
        validate_production_config({'FLASK_ENV': 'production', 'SECRET_KEY': '', 'MASTER_SECRET_KEY': ''})
    with pytest.raises(RuntimeError):
        validate_production_config({'FLASK_ENV': 'production', 'SECRET_KEY': 'x' * 64,
                                    'MASTER_SECRET_KEY': 'SAPTHA@2026'})
    validate_production_config({'FLASK_ENV': 'production', 'SECRET_KEY': 'x' * 64,
                                'MASTER_SECRET_KEY': 'a-long-master-key'})
    validate_production_config({'FLASK_ENV': 'development'})
