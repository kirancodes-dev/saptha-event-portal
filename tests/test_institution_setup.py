"""
tests/test_institution_setup.py — UPG-268: the Super Admin sets the deployment
up for its institution on one page: validated details that the footer, the
help address and the certificate then use; the first administrators invited
through the existing add-user flow; a checklist read from the deployment; an
audit entry for every save. Nobody else opens or changes it, and a made-up
tenant header changes nothing (real database layer).
"""
import pytest

import services_institution as institution
from tests.test_integration_flow import _login, _unique, _user

GOOD = {'name': 'Riverbend Institute of Technology', 'short_name': 'RIT', 'public_url': 'https://events.riverbend.example',
        'support_email': 'help@riverbend.example', 'primary_color': '#112233', 'accent_color': '#aa8800'}


@pytest.fixture
def site(real_app):
    flask_app, db = real_app
    admin = f"{_unique('instadmin')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    institution.forget()
    yield {'app': flask_app, 'db': db, 'admin': admin, 'client': _login(flask_app, admin, 'SuperAdmin')}
    # the next test starts from the built-in defaults again
    db.collection(institution.COLLECTION).document(institution.DOCUMENT).delete()
    institution.forget()


def _audit(db, action):
    return [e.to_dict() for e in db.collection('audit_log').stream() if e.to_dict().get('action') == action]


# ── Criterion 1: only the Super Admin ───────────────────────────────────────

def test_only_a_super_admin_opens_or_saves_it(site):
    d = site
    assert d['client'].get('/admin/institution').status_code == 200
    anonymous = d['app'].test_client()
    assert anonymous.get('/admin/institution').status_code == 302
    for role in ('Student', 'ClubSPOC', 'EventCoordinator'):
        email = f"{_unique('instother')}@test.edu"
        _user(d['db'], email, role)
        other = _login(d['app'], email, role)
        assert other.get('/admin/institution').status_code == 302
        assert other.post('/admin/institution', data=GOOD).status_code == 302
    assert anonymous.post('/admin/institution', data=GOOD).status_code in (302, 400, 403)
    assert institution.saved(d['db']) == {}
    # a made-up tenant header or path gives nobody a way in
    assert anonymous.get('/admin/institution', headers={'X-Tenant-Domain': 'riverbend.example'}).status_code == 302
    assert anonymous.get('/org/riverbend/admin/institution').status_code in (302, 404)


# ── Criterion 2: validation ─────────────────────────────────────────────────

@pytest.mark.parametrize('field,value', [
    ('name', ''), ('name', 'x'), ('short_name', 'x' * 21),
    ('public_url', 'events.riverbend.example'), ('public_url', 'http://events.riverbend.example'),
    ('public_url', 'https://events.riverbend.example/portal'), ('public_url', 'javascript:alert(1)'),
    ('support_email', 'not-an-email'), ('primary_color', 'navy'), ('accent_color', '#12345'),
])
def test_a_wrong_value_is_refused_with_the_reason_and_nothing_is_saved(site, field, value):
    d = site
    resp = d['client'].post('/admin/institution', data=dict(GOOD, **{field: value}))
    body = resp.get_data(as_text=True)
    assert resp.status_code == 400 and f'data-problem="{field}"' in body
    assert body.count('data-problem=') == 1           # only the wrong field is marked
    assert 'value="RIT"' in body or field == 'short_name'   # what was typed is kept
    assert not [e for e in _audit(d['db'], 'INSTITUTION_DETAILS_SAVED') if d['admin'] in e.get('details', '')]
    assert institution.saved(d['db']) == {}


def test_a_local_address_may_be_http_and_optional_fields_may_be_empty(site):
    clean, problems = institution.validate(dict(GOOD, public_url='http://127.0.0.1:5000/', support_email='', short_name=''))
    assert problems == {} and clean['public_url'] == 'http://127.0.0.1:5000'


# ── Criterion 3: saved details are used, and the save is audited ────────────

def test_saved_details_reach_the_footer_the_help_address_and_the_certificate(site):
    import certificate_pdf
    d = site
    before = d['app'].test_client().get('/privacy').get_data(as_text=True)
    assert 'Riverbend' not in before and certificate_pdf.branding()['name'] != GOOD['name']

    resp = d['client'].post('/admin/institution', data=GOOD)
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/admin/institution')
    kept = institution.saved(d['db'])
    assert {k: kept[k] for k in GOOD} == GOOD and kept['updated_by'] == d['admin']

    page = d['app'].test_client().get('/privacy').get_data(as_text=True)
    assert '© 2026 Riverbend Institute of Technology' in page
    assert 'help@riverbend.example' in page
    brand = certificate_pdf.branding()
    assert (brand['name'], brand['primary'], brand['accent']) == (GOOD['name'], '#112233', '#aa8800')

    entries = [e for e in _audit(d['db'], 'INSTITUTION_DETAILS_SAVED') if d['admin'] in e.get('details', '')]
    assert len(entries) == 1 and 'name' in entries[0]['details'] and 'public_url' in entries[0]['details']

    # saving the same again changes nothing and writes no second entry
    d['client'].post('/admin/institution', data=GOOD)
    assert len([e for e in _audit(d['db'], 'INSTITUTION_DETAILS_SAVED') if d['admin'] in e.get('details', '')]) == 1
    # one field changed: the entry names it
    d['client'].post('/admin/institution', data=dict(GOOD, short_name='RBIT'))
    last = [e for e in _audit(d['db'], 'INSTITUTION_DETAILS_SAVED') if d['admin'] in e.get('details', '')]
    assert len(last) == 2 and any(e['details'].endswith("institution's short_name") for e in last)
    form = d['client'].get('/admin/institution').get_data(as_text=True)
    assert 'value="RBIT"' in form and 'value="https://events.riverbend.example"' in form


# ── Criterion 4: the first administrators ───────────────────────────────────

def test_the_first_administrator_is_invited_through_the_add_user_flow(site):
    d = site
    page = d['client'].get('/admin/institution').get_data(as_text=True)
    assert 'action="/admin/users/add"' in page and 'name="role" value="SuperAdmin"' in page
    assert f'data-admin="{d["admin"]}"' in page

    invited = f"{_unique('registrar')}@riverbend.example"
    resp = d['client'].post('/admin/users/add', data={'name': 'Registrar R', 'email': invited, 'role': 'SuperAdmin'})
    assert resp.status_code == 302
    user = d['db'].collection('users').document(invited).get().to_dict()
    assert user['role'] == 'SuperAdmin' and user['needs_password_reset'] is True   # locked until they set a password
    listed = {a['email']: a for a in institution.administrators(d['db'])}
    assert listed[invited]['active'] is False and listed[d['admin']]['active'] is True
    page = d['client'].get('/admin/institution').get_data(as_text=True)
    assert f'data-admin="{invited}"' in page and "hasn&#39;t set a password yet" in page
    assert any(invited in e.get('details', '') for e in _audit(d['db'], 'ADMIN_USER_ADDED'))


# ── Criterion 5: the checklist is read from the deployment ──────────────────

def test_the_checklist_says_what_is_and_is_not_ready(site, monkeypatch):
    d = site
    for name in ('BREVO_API_KEY', 'MAIL_USER', 'MAIL_PASS', 'MAIL_PASSWORD', 'CRON_SECRET', 'STORAGE_TYPE', 'SUPPORT_EMAIL'):
        monkeypatch.delenv(name, raising=False)
    institution.forget()
    items = {i['key']: i for i in institution.checklist(d['db'], 'https://events.riverbend.example/')}
    assert not items['details']['done'] and not items['mail']['done'] and not items['jobs']['done']
    assert not items['storage']['done'] and not items['support']['done']

    d['client'].post('/admin/institution', data=GOOD)
    monkeypatch.setenv('BREVO_API_KEY', 'set-for-this-test')
    monkeypatch.setenv('CRON_SECRET', 'set-for-this-test')
    monkeypatch.setenv('STORAGE_TYPE', 'gcs')
    items = {i['key']: i for i in institution.checklist(d['db'], 'https://events.riverbend.example/')}
    for key in ('details', 'address', 'support', 'mail', 'jobs', 'storage'):
        assert items[key]['done'], key
    # opened at another address than the saved one: said, not hidden
    other = {i['key']: i for i in institution.checklist(d['db'], 'https://old-name.example/')}
    assert not other['address']['done'] and 'https://old-name.example' in other['address']['detail']

    page = d['client'].get('/admin/institution').get_data(as_text=True)
    assert 'data-check="details" data-done="yes"' in page and 'data-check="mail" data-done="yes"' in page
    assert 'set-for-this-test' not in page          # yes or no, never a secret's value
