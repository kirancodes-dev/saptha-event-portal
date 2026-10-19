"""
tests/test_certificate_verification.py — on the real database layer:
UPG-126 (the public page of a certificate number: valid, not found, revoked,
replaced; no personal data; rate limits; the lookup form and the legacy check
lead to it), UPG-134 (SUPPORT_EMAIL on every verification page, nothing
hard-coded) and UPG-135 (the legacy registration check and its preview show
the lead's name on seeded rows; the old hash's documentation says how it's made).
"""
import datetime
import hashlib
import uuid

import pytest

import services_certificates as certs
from tests.test_certificate_types import _signature
from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def site(real_app, monkeypatch):
    flask_app, db = real_app
    import routes_coordinator
    monkeypatch.setattr(routes_coordinator, 'db', db, raising=False)
    monkeypatch.delenv('SUPPORT_EMAIL', raising=False)
    owner_email = f"{_unique('verowner')}@test.edu"
    _user(db, owner_email, 'ClubSPOC')
    owner = _login(flask_app, owner_email, 'ClubSPOC')

    def issued(name='Vani Verified', **reg_fields):
        import services_signatories
        event_id = _create_event(owner, db, _unique('Verified Event'), '2031-04-04', team=False)
        db.collection('events').document(event_id).update({'status': 'completed', 'staff': [], 'end_date': '2031-04-05'})
        services_signatories.add(db, event_id, name='Dr. A. Kumar', title='Principal', image=_signature(), actor=owner_email)
        email = f"{_unique('vani')}@test.edu"
        reg_id = _unique('REG')
        db.collection('registrations').document(reg_id).set(dict({
            'event_id': event_id, 'lead_name': name, 'lead_email': email, 'lead_phone': '9876501234',
            'lead_usn': '1SN21CS042', 'status': 'Confirmed', 'attendance': 'Present',
            'attendance_days': ['2031-04-04', '2031-04-05']}, **reg_fields))      # both days of a two-day event
        certs.issue_event(db, event_id, owner_email, only=['participation'])
        [cert] = [c for c in certs.for_event(event_id) if c['name'] == name]
        title = db.collection('events').document(event_id).get().to_dict()['title']
        return {'event_id': event_id, 'reg_id': reg_id, 'email': email, 'cert': cert, 'title': title}
    return {'app': flask_app, 'db': db, 'owner': owner, 'owner_email': owner_email, 'issued': issued,
            'visitor': flask_app.test_client()}


# ── UPG-126 criterion 1 ─────────────────────────────────────────────────────

def test_a_valid_certificate_shows_its_facts_and_no_personal_data(site):
    d = site
    got = d['issued']()
    number = got['cert']['number']
    resp = d['visitor'].get(f'/verify/{number}')
    page = resp.get_data(as_text=True)
    assert resp.status_code == 200 and 'Valid certificate' in page
    for fact in ('Vani Verified', got['title'], '04 April 2031 to 05 April 2031', 'Certificate of Participation',
                 'Sapthagiri NPS University', number):
        assert fact in page, fact
    for private in (got['email'], '9876501234', '1SN21CS042', got['reg_id']):
        assert private not in page, private
    assert d['visitor'].get(f'/verify/{number.lower()}').status_code == 200      # typed in lower case


def test_an_unknown_number_is_not_found(site):
    resp = site['visitor'].get('/verify/SE-AAAA-BBBB-CCCC-D')
    assert resp.status_code == 404 and 'Certificate not found' in resp.get_data(as_text=True)


def test_a_revoked_certificate_shows_revoked_and_the_date(site):
    d = site
    cert = d['issued']()['cert']
    certs.update(cert['id'], status='revoked', revoked_at=datetime.datetime(2031, 6, 1, tzinfo=datetime.timezone.utc),
                 revoked_reason='Issued in error')
    page = d['visitor'].get(f"/verify/{cert['number']}").get_data(as_text=True)
    assert 'Revoked certificate' in page and 'revoked on 01 June 2031' in page and 'Valid certificate' not in page
    assert 'Issued in error' not in page                                       # the reason stays internal


def test_a_replaced_version_says_it_was_replaced(site):
    from db_pg import get_session
    from models_pg import Certificate
    d = site
    cert = d['issued']()['cert']
    certs.update(cert['id'], is_current=False, status='superseded')
    with get_session() as s:
        s.add(Certificate(number=cert['number'], version=2, is_current=True, status='valid', event_id=cert['event_id'],
                          person_key=cert['person_key'], recipient_email=cert['email'], recipient_name='Vani Verified-Rao',
                          reg_id=cert['reg_id'], cert_type=cert['cert_type'], data_json='{"event_title": "Corrected"}'))
    old = d['visitor'].get(f"/verify/{cert['number']}/v1").get_data(as_text=True)
    assert 'Replaced certificate' in old and 'replaced by version 2' in old and 'Valid certificate' not in old
    now = d['visitor'].get(f"/verify/{cert['number']}").get_data(as_text=True)
    assert 'Valid certificate' in now and 'Vani Verified-Rao' in now and 'version 2' in now
    assert d['visitor'].get(f"/verify/{cert['number']}/v7").status_code == 404


# ── UPG-126 criterion 2 ─────────────────────────────────────────────────────

def test_lookups_past_the_limit_get_429(site, monkeypatch):
    from extensions import limiter
    d = site
    number = d['issued']()['cert']['number']
    monkeypatch.setattr(limiter, 'enabled', True, raising=False)
    monkeypatch.setenv('VERIFY_RATE_LIMIT', '5 per minute')
    limiter.reset()
    try:
        assert [d['visitor'].get(f'/verify/{number}').status_code for _ in range(5)] == [200] * 5
        assert d['visitor'].get(f'/verify/{number}').status_code == 429
        assert d['visitor'].get('/verify/SE-AAAA-BBBB-CCCC-D').status_code == 429      # any number
        limiter.reset()
        for _ in range(5):
            assert d['visitor'].post('/verify', data={'cert_id': number}).status_code == 302
        assert d['visitor'].post('/verify', data={'cert_id': number}).status_code == 429
        assert d['visitor'].get('/verify').status_code == 200                           # the form itself isn't counted
    finally:
        limiter.reset()


# ── UPG-126 criterion 3 ─────────────────────────────────────────────────────

def test_the_lookup_form_and_the_legacy_check_lead_to_the_new_page(site):
    d = site
    got = d['issued']()
    number = got['cert']['number']
    resp = d['visitor'].post('/verify', data={'cert_id': f'  {number.lower()} '})
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/verify/{number}')
    _user(d['db'], got['email'], 'Student')
    student = _login(d['app'], got['email'], 'Student')
    resp = student.get(f"/coordinator/certificate/{got['reg_id']}/1SN21CS042")
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/verify/{number}')
    # Older IDs keep their pages at the address printed on older certificates
    old_hash = uuid.uuid4().hex + uuid.uuid4().hex
    d['db'].collection('verified_certificates').document(old_hash).set({
        'hash': old_hash, 'student_name': 'Olden Days', 'event_title': 'Old Event', 'cert_type': 'participation',
        'issued_at': '2025-01-01T10:00:00', 'status': 'Verified'})
    assert 'Olden Days' in d['visitor'].get(f'/verify/{old_hash}').get_data(as_text=True)


# ── UPG-134 ─────────────────────────────────────────────────────────────────

def test_upg134_verification_pages_show_support_email_or_none(site, monkeypatch):
    d = site
    got = d['issued']()
    old_hash = uuid.uuid4().hex + uuid.uuid4().hex
    d['db'].collection('verified_certificates').document(old_hash).set({
        'hash': old_hash, 'student_name': 'Olden Days', 'event_title': 'Old Event', 'cert_type': 'participation',
        'issued_at': '2025-01-01T10:00:00', 'status': 'Verified'})
    pages = (f"/verify/{got['cert']['number']}", f'/verify/{old_hash}', f"/verify/{got['reg_id']}",
             '/verify/SE-AAAA-BBBB-CCCC-D')
    monkeypatch.setenv('SUPPORT_EMAIL', 'events@example.edu')
    for path in pages:
        assert 'mailto:events@example.edu' in d['visitor'].get(path).get_data(as_text=True), path
    monkeypatch.delenv('SUPPORT_EMAIL')
    for path in pages:
        page = d['visitor'].get(path).get_data(as_text=True)
        assert 'mailto:' not in page and 'snpsu.edu.in' not in page, path
    import glob
    for template in glob.glob('templates/public/verify_*.html') + ['templates/certificates/verify.html']:
        assert 'support@' not in open(template, encoding='utf-8').read(), template


# ── UPG-135 ─────────────────────────────────────────────────────────────────

def test_upg135_the_legacy_check_shows_the_leads_name_on_a_seeded_row(site):
    from db_adapter import to_uuid
    from db_pg import get_session
    from models_pg import Registration
    d = site
    event_id = _create_event(d['owner'], d['db'], _unique('Seeded Check'), '2030-03-03', team=False)
    reg_uuid = uuid.uuid4()
    with get_session() as s:      # the columns only, no stored document: what seed.py writes
        s.add(Registration(id=reg_uuid, event_id=to_uuid(event_id), lead_name='Seeded Sita',
                           lead_email=f"{_unique('sita')}@test.edu", lead_phone='9876543210'))
    d['db'].collection('registrations').document(str(reg_uuid)).update({'attendance': 'Present'})
    page = d['visitor'].get(f'/verify/{reg_uuid}').get_data(as_text=True)
    assert 'Congratulations, Seeded Sita!' in page
    assert 'Seeded Sita' in d['visitor'].get(f'/verify/{reg_uuid}/preview').get_data(as_text=True)


def test_upg135_the_old_hash_is_documented_as_it_is_made():
    from services_certificate import CertificateService, _get_cert_secret
    doc = CertificateService.generate_verification_hash.__doc__
    assert 'not an HMAC' in doc and 'first 24 hex characters of a SHA-256' in doc
    expected = hashlib.sha256(f"c1:e1:ann@x.edu:{_get_cert_secret()}".encode()).hexdigest()[:24]
    assert CertificateService.generate_verification_hash('c1', 'e1', ' Ann@x.edu ') == expected
    assert 'random' in certs.new_number.__doc__


def test_the_verification_limits_work_without_flask_limiter_too(monkeypatch):
    """extensions.py falls back to a no-op limiter when flask-limiter isn't installed;
    the verification routes' shared limit must exist there too. The module's code
    runs in its own namespace, so the app's limiter is untouched."""
    import builtins
    real_import = builtins.__import__

    def no_limiter(name, *a, **k):
        if name.startswith('flask_limiter'):
            raise ImportError(name)
        return real_import(name, *a, **k)
    namespace = {'__name__': 'extensions_without_flask_limiter'}
    with open('extensions.py', encoding='utf-8') as fh:
        code = compile(fh.read(), 'extensions.py', 'exec')
    monkeypatch.setattr(builtins, '__import__', no_limiter)
    exec(code, namespace)   # nosec B102 (the repo's own module, run to test its fallback)
    monkeypatch.setattr(builtins, '__import__', real_import)
    fallback = namespace['limiter']
    view = fallback.shared_limit('5 per minute', scope='certificate-verify')(lambda: 'page')
    assert type(fallback).__name__ == 'DummyLimiter' and view() == 'page'
