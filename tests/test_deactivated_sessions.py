"""
tests/test_deactivated_sessions.py — UPG-76 on the real database layer: when a
Super Admin deactivates an account, that person's open session ends on their
next request, for pages and for JSON alike.
"""
from tests.test_integration_flow import PASSWORD, _login, _unique, _user


def _admin(flask_app, db):
    email = f"{_unique('deact-admin')}@test.edu"
    _user(db, email, 'SuperAdmin')
    client = flask_app.test_client()
    resp = client.post('/login', data={'role': 'SuperAdmin', 'email': email, 'password': PASSWORD,
                                       'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert resp.status_code == 302 and resp.headers['Location'] != '/login'
    return client


def test_an_open_session_ends_when_the_account_is_deactivated(real_app):
    flask_app, db = real_app
    email = f"{_unique('deact')}@test.edu"
    _user(db, email, 'Student')
    student = _login(flask_app, email, 'Student')
    assert student.get('/participant/dashboard').status_code == 200

    _admin(flask_app, db).post(f'/admin/users/{email}', data={'action': 'deactivate'})

    resp = student.get('/participant/dashboard')
    assert resp.status_code == 302 and resp.headers['Location'] == '/login'
    with student.session_transaction() as sess:
        assert 'user_id' not in sess
    assert student.get('/participant/dashboard').headers['Location'] == '/login'   # and it stays ended
    audit = [e.to_dict() for e in db.collection('audit_log').where('action', '==', 'SESSION_ENDED_DEACTIVATED').stream()]
    assert any(email in e.get('details', '') for e in audit)


def test_json_callers_get_401_and_active_accounts_are_untouched(real_app):
    flask_app, db = real_app
    gone, kept = (f"{_unique('deact-json')}@test.edu", f"{_unique('still')}@test.edu")
    for email in (gone, kept):
        _user(db, email, 'Student')
    gone_client, kept_client = _login(flask_app, gone, 'Student'), _login(flask_app, kept, 'Student')
    db.collection('users').document(gone).update({'is_active': False})

    resp = gone_client.get('/participant/waitlist_status', headers={'Accept': 'application/json'})
    assert resp.status_code == 401 and resp.get_json() == {'error': 'account_deactivated'}
    assert kept_client.get('/participant/waitlist_status').status_code == 200
