"""
tests/test_certificate_phone.py — UPG-125 criterion 4, in headless Chromium
against the app on a local server: at 375px and 1280px, "My certificates" and
the public verification page never scroll sideways or cut anything off
(UPG-23's measure), and the PDF download works from the phone.
"""
import pytest

import services_certificates as certs
from tests.test_certificate_types import _signature
from tests.test_integration_flow import _create_event, _login, _unique, _user
from tests.test_phone_journey import PHONE, _check, _login_in_browser, _routes
from utils_storage import get_private


@pytest.fixture
def issued(real_app, tmp_path):
    import services_signatories
    flask_app, db = real_app
    spoc, student = f"{_unique('phspoc')}@test.edu", f"{_unique('phstudent')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, student, 'Student', name='Priya Phone')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Phone Certificate Day'), '2031-02-02', team=False)
    db.collection('events').document(event_id).update({'status': 'completed', 'staff': []})
    services_signatories.add(db, event_id, name='Dr. A. Kumar', title='Principal', image=_signature(), actor=spoc)
    reg_id = _unique('REG')
    db.collection('registrations').document(reg_id).set({
        'event_id': event_id, 'lead_name': 'Priya Venkata Subramanya Lakshminarayana Phone', 'lead_email': student,
        'status': 'Confirmed', 'attendance': 'Present'})
    certs.issue_event(db, event_id, spoc, only=['participation'])
    [cert] = [c for c in certs.for_event(event_id) if c['email'] == student]
    import os
    shots = os.environ.get('CERT_SHOTS') or str(tmp_path / 'shots')
    os.makedirs(shots, exist_ok=True)
    return {'app': flask_app, 'db': db, 'student': student, 'cert': cert, 'reg_id': reg_id, 'shots': shots}


def test_certificates_fit_a_phone_and_download_from_it(issued):
    from tests.headless import chromium, live_server
    d = issued
    problems = []
    p, browser = chromium()
    try:
        with live_server(d['app']) as server:
            base = server.url
            ctx = browser.new_context(viewport=PHONE, accept_downloads=True)
            _routes(ctx, base)
            page = ctx.new_page()
            _login_in_browser(page, base, d['student'], 'Student')

            page.goto(f'{base}/certificates/mine')
            assert d['cert']['number'] in page.content()
            _check(page, d, 'cert-1-mine', problems)
            with page.expect_download() as download:
                page.click('text=Download PDF')
            path = download.value.path()
            with open(path, 'rb') as fh:
                assert fh.read() == get_private(d['cert']['pdf_key'])
            assert download.value.suggested_filename == f"Certificate-{d['cert']['number']}.pdf"

            page.goto(f"{base}/verify/{d['cert']['number']}")
            assert 'Valid certificate' in page.content()
            _check(page, d, 'cert-3-verify', problems)
    finally:
        browser.close()
        p.stop()
    assert problems == []
