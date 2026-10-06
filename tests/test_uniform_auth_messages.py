"""
tests/test_uniform_auth_messages.py — UPG-35 on the real database layer:
login and password-reset answers don't reveal whether an email has an
account. Sign-up and registration still tell an existing email to log in
first (owner decision D-3).
"""
import pytest

from tests.test_integration_flow import PASSWORD, _unique, _user
from tests.test_registration_no_auto_login import _form, _spoc_event

LOGIN_FAILED = 'Email or password is incorrect.'
RESET_SENT = "If an account exists for this email, we've sent a reset link."


@pytest.fixture
def accounts(real_app, monkeypatch):
    """An existing student, an account with an old unhashed password, a
    SuperAdmin, an unknown email; every email the app sends is captured."""
    flask_app, db = real_app
    import utils_email
    mails = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: mails.append(to) or True)
    student, legacy, admin = (f"{_unique(p)}@test.edu" for p in ('known', 'legacy', 'boss'))
    _user(db, student, 'Student')
    _user(db, admin, 'SuperAdmin')
    db.collection('users').document(legacy).set({'name': 'Old', 'role': 'Student', 'password': 'plain-old-pass'})
    return flask_app, db, mails, {'student': student, 'legacy': legacy, 'admin': admin,
                                  'unknown': f"{_unique('nobody')}@test.edu"}


def _flashes(client):
    with client.session_transaction() as sess:
        return [message for _, message in sess.get('_flashes', [])]


def _web_login(flask_app, email, password, role='Student'):
    client = flask_app.test_client()
    resp = client.post('/login', data={'role': role, 'email': email, 'password': password},
                       environ_base={'REMOTE_ADDR': f'198.18.0.{abs(hash(email)) % 250 + 1}'})
    return resp, _flashes(client)


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_web_login_answers_alike_for_unknown_emails_wrong_and_old_passwords(accounts):
    flask_app, db, _, who = accounts
    answers = [_web_login(flask_app, who['unknown'], 'whatever-1'),
               _web_login(flask_app, who['student'], 'wrong-password'),
               _web_login(flask_app, who['legacy'], 'plain-old-pass')]
    for resp, flashes in answers:
        assert (resp.status_code, resp.headers['Location'], flashes) == (302, '/login', [LOGIN_FAILED])

    # Only someone with the right password learns the role was wrong (D-3)
    resp, flashes = _web_login(flask_app, who['student'], PASSWORD, role='ClubSPOC')
    assert resp.headers['Location'] == '/login' and 'Wrong role' in flashes[0]


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_api_login_answers_alike_for_the_same_three_cases(accounts):
    flask_app, db, _, who = accounts
    bodies = []
    for email, password in ((who['unknown'], 'whatever-1'), (who['student'], 'wrong-password'),
                            (who['legacy'], 'plain-old-pass')):
        resp = flask_app.test_client().post('/api/v1/auth/login', json={'email': email, 'password': password},
                                            environ_base={'REMOTE_ADDR': f'198.18.1.{len(bodies) + 1}'})
        bodies.append((resp.status_code, resp.get_json()))
    assert bodies[0] == bodies[1] == bodies[2]
    assert bodies[0] == (401, {'status': 'error', 'error': 'invalid_credentials', 'message': LOGIN_FAILED})


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_reset_requests_answer_alike_and_only_the_real_account_gets_a_link(accounts):
    flask_app, db, mails, who = accounts
    for key in ('unknown', 'student', 'admin'):
        client = flask_app.test_client()
        resp = client.post('/forgot_password', data={'email': who[key]})
        assert (resp.status_code, resp.headers['Location'], _flashes(client)) == (302, '/forgot_password', [RESET_SENT])
    assert mails == [who['student']]  # SuperAdmins reset with the master key, never by email


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_sign_up_and_registration_still_tell_an_existing_email_to_log_in(accounts):
    flask_app, db, _, who = accounts
    client = flask_app.test_client()
    client.post('/register', data={'name': 'Again', 'email': who['student'], 'password': 'Brand-new-pass-42',
                                   'confirm_password': 'Brand-new-pass-42', 'usn': '1SN20CS001'})
    assert any('already exists' in f and 'log in' in f for f in _flashes(client))

    api = flask_app.test_client().post('/api/v1/auth/register', json={
        'email': who['student'], 'password': 'Brand-new-pass-42', 'name': 'Again'})
    assert api.status_code == 409 and api.get_json()['error'] == 'email_exists'

    event_id = _spoc_event(flask_app, db)
    visitor = flask_app.test_client()
    resp = visitor.post(f'/forms/submit/{event_id}', data=_form(who['student']))
    assert resp.headers['Location'] == f'/login?next=/forms/register/{event_id}'
    assert any('already exists' in f and 'log in' in f for f in _flashes(visitor))
