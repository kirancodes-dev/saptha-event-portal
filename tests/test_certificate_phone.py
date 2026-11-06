"""
tests/test_certificate_phone.py — UPG-125 criterion 4 and UPG-132 (UPG-28's
certificate part), in headless Chromium against the app on a local server:
at 375px and 1280px, "My certificates", the participant's certificate page and
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

            page.goto(f"{base}/participant/certificate/{d['reg_id']}")
            _check(page, d, 'cert-2-participant-page', problems)
            page.goto(f"{base}/verify/{d['cert']['number']}")
            assert 'Valid certificate' in page.content()
            _check(page, d, 'cert-3-verify', problems)
    finally:
        browser.close()
        p.stop()
    assert problems == []


@pytest.fixture
def organiser(real_app, tmp_path, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setenv('TASK_INLINE_TIMEOUT', '120')
    spoc = f"{_unique('phorg')}@test.edu"
    _user(db, spoc, 'ClubSPOC', name='Olga Organiser')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Organised Certificate Day'),
                             '2031-02-02', team=False)
    db.collection('events').document(event_id).update({'status': 'completed', 'staff': []})
    for i in range(30):
        db.collection('registrations').document(_unique('REG')).set({
            'event_id': event_id, 'lead_name': f'Attendee {i:02d} Venkatanarasimharajuvaripeta',
            'lead_email': f"{_unique('pho')}@test.edu", 'status': 'Confirmed', 'attendance': 'Present'})
    sig = tmp_path / 'signature.png'
    sig.write_bytes(_signature())
    import os
    shots = os.environ.get('CERT_SHOTS') or str(tmp_path / 'shots')
    os.makedirs(shots, exist_ok=True)
    return {'app': flask_app, 'db': db, 'spoc': spoc, 'event_id': event_id, 'signature': str(sig), 'shots': shots}


def test_the_organiser_signs_issues_and_lists_on_a_phone(organiser):
    from tests.headless import chromium, live_server
    d = organiser
    problems = []
    p, browser = chromium()
    try:
        with live_server(d['app']) as server:
            base = server.url
            ctx = browser.new_context(viewport=PHONE)
            _routes(ctx, base)
            page = ctx.new_page()
            _login_in_browser(page, base, d['spoc'], 'ClubSPOC')
            page.goto(f"{base}/certificates/events/{d['event_id']}")
            assert page.locator('button:has-text("Issue certificates")').is_disabled()       # no signature yet
            _check(page, d, 'org-1-unsigned', problems)

            page.fill('#sig-name', 'Dr. Ananthapadmanabha Krishnamurthy')
            page.fill('#sig-title', 'Principal and Dean of Student Affairs')
            page.set_input_files('#sig-file', d['signature'])
            page.click('form[action$="/signatories"] button[type=submit]')
            page.wait_for_load_state('load')
            assert 'added as a signatory' in page.content()
            _check(page, d, 'org-2-signed', problems)

            page.click('button:has-text("Issue certificates")')
            page.wait_for_load_state('load')
            assert 'Issuing 31 certificates' in page.content()
            page.goto(f"{base}/certificates/events/{d['event_id']}")
            assert '31 of 31 done, 0 failed' in page.content()
            _check(page, d, 'org-3-issued', problems)

            page.goto(f"{base}/certificates/events/{d['event_id']}/list")
            assert 'Showing 1–25 of 31' in page.content()
            _check(page, d, 'org-4-list', problems)
    finally:
        browser.close()
        p.stop()
    assert len(certs.for_event(d['event_id'])) == 31
    assert problems == []
