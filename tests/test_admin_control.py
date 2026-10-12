"""
tests/test_admin_control.py — UPG-75: the Super Admin can see and control
everything: every event (approve, change status, hand to another SPOC), every
account (add any role, change role and department, deactivate), every
registration (find, attendance, cancel), the system's state, and announcements
in the app.
"""
import pytest

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user


@pytest.fixture
def admin(real_app, monkeypatch):
    flask_app, db = real_app
    import routes_admin
    import routes_spoc
    monkeypatch.setattr(routes_spoc, 'db', db)
    sent = []
    monkeypatch.setattr(routes_admin, 'send_set_password_link',
                        lambda d, email, name, reason='': sent.append(email) or True)
    email = f"{_unique('superadmin')}@test.edu"
    _user(db, email, 'SuperAdmin', name='Root Admin')
    client = flask_app.test_client()
    resp = client.post('/login', data={'role': 'SuperAdmin', 'email': email, 'password': PASSWORD,
                                       'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert resp.status_code == 302 and resp.headers['Location'] != '/login'
    spoc = f"{_unique('ctlspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC', name='Club Lead')
    before = {d.id for d in db.collection('users').stream()}
    yield {'app': flask_app, 'db': db, 'client': client, 'email': email, 'spoc': spoc, 'sent': sent}
    # Remove the accounts these tests made, so later tests see the same user list
    # (tests/test_admin_users.py reads the first page of users)
    for d in db.collection('users').stream():
        if d.id not in before or d.id in (email, spoc):
            db.collection('users').document(d.id).delete()


def _event(d, status=None):
    spoc_client = _login(d['app'], d['spoc'], 'ClubSPOC')
    import datetime
    event_id = _create_event(spoc_client, d['db'], _unique('Ctl Event'),
                             (datetime.date.today() + datetime.timedelta(days=10)).isoformat(), team=False)
    if status:
        d['db'].collection('events').document(event_id).update({'status': status})
    return event_id


def _get(d, coll, doc_id):
    return d['db'].collection(coll).document(doc_id).get().to_dict() or {}


# ── Criterion 1: every event ───────────────────────────────────────────────

def test_all_events_lists_every_status_and_is_admin_only(admin):
    draft = _event(admin, 'draft')
    pending = _event(admin, 'pending_approval')
    live = _event(admin)
    page = admin['client'].get('/admin/events?per_page=100').get_data(as_text=True)
    for eid in (draft, pending, live):
        assert eid in page
    assert 'Waiting for your approval' in page
    student = f"{_unique('ctlstudent')}@test.edu"
    _user(admin['db'], student, 'Student')
    resp = _login(admin['app'], student, 'Student').get('/admin/events')
    assert resp.status_code in (302, 403)


def test_admin_approves_changes_status_and_hands_over_an_event(admin):
    pending = _event(admin, 'pending_approval')
    admin['client'].post(f'/admin/events/approve/{pending}', data={'next': '/admin/events'})
    assert _get(admin, 'events', pending)['status'] == 'published'
    admin['client'].post(f'/admin/events/{pending}/status', data={'target_state': 'registration_open'})
    assert _get(admin, 'events', pending)['status'] == 'registration_open'

    other = f"{_unique('newowner')}@test.edu"
    _user(admin['db'], other, 'ClubSPOC', name='New Owner')
    admin['client'].post(f'/admin/events/{pending}/owner', data={'spoc_email': other})
    ev = _get(admin, 'events', pending)
    assert ev['spoc_id'] == other and ev['organizer']['email'] == other
    # Only to a Club SPOC account
    student = f"{_unique('notspoc')}@test.edu"
    _user(admin['db'], student, 'Student')
    admin['client'].post(f'/admin/events/{pending}/owner', data={'spoc_email': student})
    assert _get(admin, 'events', pending)['spoc_id'] == other


# ── Criterion 2: accounts ──────────────────────────────────────────────────

def test_admin_adds_edits_and_deactivates_an_account(admin):
    client, db = admin['client'], admin['db']
    email = f"{_unique('newjudge')}@test.edu"
    resp = client.post('/admin/users/add', data={'name': 'New Judge', 'email': email, 'role': 'Judge',
                                                 'category': 'Technical'})
    assert resp.status_code == 302 and email in resp.headers['Location']
    user = _get(admin, 'users', email)
    assert user['role'] == 'Judge' and user['category'] == 'Technical'
    assert email in admin['sent']
    assert client.get(f'/admin/users/{email}').status_code == 200

    client.post(f'/admin/users/{email}', data={'action': 'save', 'name': 'New Coordinator',
                                               'role': 'EventCoordinator', 'department': 'CSE', 'category': 'Sports'})
    user = _get(admin, 'users', email)
    assert (user['role'], user['department'], user['category'], user['name']) == \
           ('EventCoordinator', 'CSE', 'Sports', 'New Coordinator')

    # Give them a real password, then deactivate: login is refused; reactivate: it works
    from werkzeug.security import generate_password_hash
    db.collection('users').document(email).update({'password': generate_password_hash(PASSWORD),
                                                   'needs_password_reset': False})
    client.post(f'/admin/users/{email}', data={'action': 'deactivate'})
    assert _get(admin, 'users', email)['is_active'] is False
    blocked = admin['app'].test_client().post('/login', data={'role': 'EventCoordinator', 'email': email,
                                                              'password': PASSWORD})
    assert blocked.headers['Location'].endswith('/login')
    client.post(f'/admin/users/{email}', data={'action': 'activate'})
    _login(admin['app'], email, 'EventCoordinator')


def test_an_admin_cant_lock_themselves_out(admin):
    client = admin['client']
    client.post(f"/admin/users/{admin['email']}", data={'action': 'deactivate'})
    assert _get(admin, 'users', admin['email']).get('is_active', True) is not False
    client.post(f"/admin/users/{admin['email']}", data={'action': 'save', 'name': 'Root', 'role': 'Student'})
    assert _get(admin, 'users', admin['email'])['role'] == 'SuperAdmin'
    client.post(f"/admin/delete_user/{admin['email']}")
    assert admin['db'].collection('users').document(admin['email']).get().exists


def test_adding_a_duplicate_or_invalid_account_is_refused(admin):
    client = admin['client']
    client.post('/admin/users/add', data={'name': 'Dup', 'email': admin['spoc'], 'role': 'Judge'})
    assert _get(admin, 'users', admin['spoc'])['role'] == 'ClubSPOC'
    bad = f"{_unique('badrole')}@test.edu"
    client.post('/admin/users/add', data={'name': 'Bad', 'email': bad, 'role': 'Overlord'})
    assert not admin['db'].collection('users').document(bad).get().exists


# ── Criterion 3: registrations ─────────────────────────────────────────────

def _registration(d, event_id, email, usn, name):
    reg_id = _unique('reg')
    d['db'].collection('registrations').document(reg_id).set({
        'event_id': event_id, 'lead_email': email, 'lead_name': name, 'usn': usn,
        'status': 'confirmed', 'attendance': 'Pending', 'registered_at': '2026-10-01 10:00:00'})
    return reg_id


def test_admin_finds_registrations_and_marks_and_cancels_them(admin):
    client = admin['client']
    a, b = _event(admin), _event(admin)
    email = f"{_unique('asha')}@test.edu"
    usn = _unique('USN').upper()
    first, second = _unique('Asha First'), _unique('Asha Second')
    r1 = _registration(admin, a, email, usn, first)
    r2 = _registration(admin, b, email, usn, second)
    by_email = client.get(f'/admin/registrations?q={email}').get_data(as_text=True)
    by_usn = client.get(f'/admin/registrations?q={usn}').get_data(as_text=True)
    for page in (by_email, by_usn):          # found across both events
        assert first in page and second in page
    client.post(f'/admin/registrations/{r1}/attendance', data={'attendance': 'Present'})
    assert _get(admin, 'registrations', r1)['attendance'] == 'Present'
    client.post(f'/admin/registrations/{r2}/cancel', data={'reason': ''})
    assert _get(admin, 'registrations', r2)['status'] == 'confirmed'      # a reason is required
    client.post(f'/admin/registrations/{r2}/cancel', data={'reason': 'Duplicate entry'})
    reg = _get(admin, 'registrations', r2)
    assert reg['status'] == 'cancelled' and reg['cancel_reason'] == 'Duplicate entry'
    actions = {(d.to_dict() or {}).get('action') for d in admin['db'].collection('audit_log').stream()}
    assert {'ADMIN_ATTENDANCE', 'REGISTRATION_CANCELLED'} <= actions


# ── Criterion 4: system ────────────────────────────────────────────────────

def test_system_page_shows_status_but_never_secrets(admin, monkeypatch):
    monkeypatch.setenv('RAZORPAY_KEY_ID', 'rzp_live_SECRETVALUE123')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'topsecretvalue')
    page = admin['client'].get('/admin/system').get_data(as_text=True)
    assert 'Payments (Razorpay)' in page and 'Set up' in page
    assert 'rzp_live_SECRETVALUE123' not in page and 'topsecretvalue' not in page


def test_failed_background_jobs_are_listed(admin):
    import services_outbox
    services_outbox.store('tasks.email_tasks.send_generic_email_task', ['x@test.edu'], {}, 'SMTP refused')
    page = admin['client'].get('/admin/system').get_data(as_text=True)
    assert 'send generic email task' in page and 'SMTP refused' in page


# ── Criterion 5: announcements in the app ──────────────────────────────────

def test_announcement_can_go_to_the_in_app_bell(admin):
    db = admin['db']
    judges = [f"{_unique('annjudge')}@test.edu" for _ in range(2)]
    for j in judges:
        _user(db, j, 'Judge')
    title = _unique('Briefing')
    admin['client'].post('/admin/send_email', data={'audience': 'role_filter', 'role_filter': 'Judge',
                                                    'subject': title, 'message': 'Room 3 at 9am', 'channel': 'app'})
    got = {(d.to_dict() or {}).get('user_email') for d in
           db.collection('notifications_v2').where('title', '==', title).stream()}
    assert set(judges) <= got
