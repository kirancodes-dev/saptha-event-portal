"""
tests/test_role_migration_keeps_access.py — BLK-07 on the real SQL database
layer: migrating roles never locks anyone out.
"""
import pytest
from werkzeug.security import generate_password_hash

from tests.test_integration_flow import PASSWORD, _unique

MASTER = 'test-master-key-for-blk07'


@pytest.fixture
def admin_app(real_app, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setitem(flask_app.config, 'MASTER_SECRET_KEY', MASTER)
    return flask_app, db


def _make(db, email, role, **extra):
    db.collection('users').document(email).set(
        {'name': 'User', 'role': role, 'category': 'Technical',
         'password': generate_password_hash(PASSWORD), **extra}, merge=False)


def _log_in(flask_app, email, role):
    client = flask_app.test_client()
    resp = client.post('/login', data={'role': role, 'email': email, 'password': PASSWORD,
                                       'secret_key': MASTER})
    with client.session_transaction() as sess:
        logged_in = sess.get('user_id') == email and sess.get('role') == role
    return client, resp, logged_in


def _role(db, email):
    role = db.collection('users').document(email).get().to_dict()['role']
    return getattr(role, 'value', role)


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_viewing_org_units_never_migrates(admin_app, monkeypatch):
    flask_app, db = admin_app
    import app as app_module
    import services_permission

    calls = []
    monkeypatch.setattr(services_permission, 'migrate_roles_and_units',
                        lambda *a, **k: calls.append(1) or {})
    admin, spoc = f"{_unique('sa')}@test.edu", f"{_unique('spoc')}@test.edu"
    _make(db, admin, 'SuperAdmin')
    _make(db, spoc, 'ClubSPOC', department='cse')
    client, _, ok = _log_in(flask_app, admin, 'SuperAdmin')
    assert ok

    # The old page migrated whenever it saw no org units; show it none
    class NoUnits:
        def stream(self):
            return iter([])

    class Db:
        def __getattr__(self, name):
            return getattr(db, name)

        def collection(self, name):
            return NoUnits() if name == 'org_units' else db.collection(name)

    monkeypatch.setattr(app_module, 'db', Db())
    assert client.get('/admin/org_units').status_code == 200
    assert calls == []
    assert _role(db, admin) == 'SuperAdmin' and _role(db, spoc) == 'ClubSPOC'


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_already_migrated_accounts_log_in_with_their_old_roles(admin_app, monkeypatch):
    flask_app, db = admin_app
    migrated_admin, migrated_spoc = f"{_unique('ua')}@test.edu", f"{_unique('unit')}@test.edu"
    _make(db, migrated_admin, 'UniversityAdmin')
    _make(db, migrated_spoc, 'UnitAdmin', department='cse')

    admin, _, ok = _log_in(flask_app, migrated_admin, 'SuperAdmin')
    assert ok
    assert admin.get('/admin/dashboard').status_code == 200
    spoc, _, ok = _log_in(flask_app, migrated_spoc, 'ClubSPOC')
    assert ok
    assert spoc.get('/spoc/dashboard').status_code == 200

    # The repair also keeps a migrated admin out of the email reset path
    import routes_auth
    resets = []
    monkeypatch.setattr(routes_auth, 'send_password_reset_email',
                        lambda to, *a, **k: resets.append(to) or True)
    flask_app.test_client().post('/forgot_password', data={'email': migrated_admin})
    flask_app.test_client().post('/forgot_password', data={'email': migrated_spoc})
    assert resets == [migrated_spoc]


# ── Criterion 3 and the SuperAdmin keeping access ──────────────────────────

def test_migrate_previews_first_and_the_superadmin_keeps_access_after_confirming(admin_app):
    flask_app, db = admin_app
    admin, spoc = f"{_unique('sa')}@test.edu", f"{_unique('cse-spoc')}@test.edu"
    _make(db, admin, 'SuperAdmin')
    _make(db, spoc, 'ClubSPOC', department='cse')
    client, _, ok = _log_in(flask_app, admin, 'SuperAdmin')
    assert ok

    def grants(email):
        return [d.to_dict() for d in db.collection('role_assignments').where('user_id', '==', email).stream()]

    preview = client.post('/admin/migrate_roles')
    assert preview.status_code == 302 and 'migration_preview=1' in preview.headers['Location']
    assert _role(db, admin) == 'SuperAdmin' and _role(db, spoc) == 'ClubSPOC'
    assert grants(admin) == [] and grants(spoc) == []
    assert b'Confirm migration' in client.get(preview.headers['Location']).data

    confirmed = client.post('/admin/migrate_roles', data={'confirm': '1'})
    assert confirmed.status_code == 302
    assert [g['role'] for g in grants(admin)] == ['UniversityAdmin']
    assert [(g['role'], g['scope_id']) for g in grants(spoc)] == [('UnitAdmin', 'cse')]
    # The stored roles become the scoped names (as before) ...
    assert _role(db, admin) == 'UniversityAdmin' and _role(db, spoc) == 'UnitAdmin'

    # ... and both still log straight back in with their usual roles
    client.get('/logout')
    again, _, ok = _log_in(flask_app, admin, 'SuperAdmin')
    assert ok
    assert again.get('/admin/dashboard').status_code == 200
    assert again.get('/admin/org_units').status_code == 200
    spoc_client, _, ok = _log_in(flask_app, spoc, 'ClubSPOC')
    assert ok
    assert spoc_client.get('/spoc/dashboard').status_code == 200


def test_api_login_works_for_migrated_accounts(admin_app):
    flask_app, db = admin_app
    migrated_admin = f"{_unique('ua-api')}@test.edu"
    _make(db, migrated_admin, 'UniversityAdmin')
    resp = flask_app.test_client().post('/api/v1/auth/login', json={
        'email': migrated_admin, 'password': PASSWORD, 'role': 'SuperAdmin'})
    assert resp.status_code == 200, resp.data
