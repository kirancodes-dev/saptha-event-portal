"""
tests/test_tenant_signup_disabled.py — BLK-14 on the real SQL database layer:
the public tenant sign-up must never create a SuperAdmin.
"""
from tests.test_integration_flow import _unique


def _signup(client, slug):
    return client.post('/onboarding/signup', data={
        'org_name': slug, 'org_domain': f'{slug}.test', 'admin_name': 'Anon',
        'email': f'{slug}@example.test', 'password': 'whatever-12345',
    })


def test_tenant_signup_is_404_unless_multi_tenancy_is_on(real_app, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setitem(flask_app.config, 'MULTI_TENANT_ENABLED', False)
    client = flask_app.test_client()
    slug = _unique('anon-org')

    assert client.get('/onboarding/signup').status_code == 404
    assert _signup(client, slug).status_code == 404
    assert client.get('/onboarding/wizard').status_code == 404

    assert not db.collection('users').document(f'{slug}@example.test').get().exists
    assert not db.collection('organizations').document(slug).get().exists
    with client.session_transaction() as sess:
        assert 'user_id' not in sess
    assert client.get('/admin/dashboard').status_code == 302  # still anonymous


def test_tenant_signup_with_the_flag_on_never_grants_superadmin(real_app, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setitem(flask_app.config, 'MULTI_TENANT_ENABLED', True)
    client = flask_app.test_client()
    slug = _unique('tenant-org')

    resp = _signup(client, slug)
    assert resp.status_code == 302

    user = db.collection('users').document(f'{slug}@example.test').get().to_dict()
    role = getattr(user['role'], 'value', user['role'])
    assert role not in ('SuperAdmin', 'Super Admin', 'UniversityAdmin')
    with client.session_transaction() as sess:
        assert sess['role'] not in ('SuperAdmin', 'Super Admin', 'UniversityAdmin')

    for url in ('/admin/dashboard', '/admin/org_units', '/admin/audit_log'):
        refused = client.get(url)
        assert refused.status_code == 302 and refused.headers['Location'] == '/login', url
