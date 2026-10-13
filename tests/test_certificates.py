"""
tests/test_certificates.py — UPG-06 on the real database layer: certificates
go out through one path (utils_certificate.issue_event_certificates), whether
the SPOC ends the event or presses "bulk certificates". Each attendee marked
Present gets a PDF, a certificate ID and verify URL on their registration and
an email; nobody gets one twice, and /verify/<id> confirms it.
"""
import base64
import datetime
import uuid

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def mail(real_app, monkeypatch):
    import utils_email
    sent = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, attachments=None, *a, **k:
                        sent.append({'to': to, 'subject': subject, 'html': html,
                                     'attachments': attachments or []}) or True)
    return sent


@pytest.fixture
def ended(real_app, mail):
    """An event with two attendees marked Present (one scored) and one absent."""
    flask_app, db = real_app
    spoc = f"{_unique('certspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    title = _unique('Certificate Day')
    event_id = _create_event(owner, db, title, datetime.date.today().isoformat(), team=False)
    people = {}
    for key, attendance, scores in (('ana', 'Present', {'j@test.edu': {'total': 9}}),
                                    ('ben', 'Present', {}),
                                    ('cy', 'Pending', {})):
        reg_id = _unique('REG')
        email = f"{_unique(key)}@test.edu"
        db.collection('registrations').document(reg_id).set({
            'reg_id': reg_id, 'event_id': event_id, 'lead_name': f'{key.title()} Attendee',
            'lead_email': email, 'attendance': attendance, 'payment_status': 'Free',
            'status': 'Confirmed', 'scores': scores, 'members': []})
        people[key] = (reg_id, email)
    return {'app': flask_app, 'db': db, 'owner': owner, 'spoc': spoc, 'event_id': event_id,
            'title': title, 'people': people, 'mail': mail}


def _reg(d, key):
    return d['db'].collection('registrations').document(d['people'][key][0]).get().to_dict()


def _pdfs_to(d, email):
    return [att for m in d['mail'] if m['to'] == email for att in m['attachments']]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_ending_the_event_issues_exactly_one_certificate_per_attendee(ended, caplog):
    d = ended
    resp = d['owner'].post(f"/spoc/end_event/{d['event_id']}", data={'template_id': '1'})
    assert resp.status_code == 302
    assert not [r for r in caplog.records if 'failed' in r.getMessage().lower() and r.levelname == 'ERROR']

    issued = {key: _reg(d, key).get('certificate_id') for key in ('ana', 'ben', 'cy')}
    assert issued['ana'] and issued['ben'] and not issued['cy']
    assert issued['ana'] != issued['ben']
    assert _reg(d, 'ana')['certificate_type'] == 'winner'      # the only scored attendee
    assert _reg(d, 'ben')['certificate_type'] == 'participation'
    for key in ('ana', 'ben'):
        reg = _reg(d, key)
        assert reg['certificate_verify_url'].endswith(f"/verify/{reg['certificate_id']}")
        record = d['db'].collection('verified_certificates').document(reg['certificate_id']).get().to_dict()
        assert record['event_id'] == d['event_id'] and record['student_name'] == f'{key.title()} Attendee'
        pdfs = _pdfs_to(d, d['people'][key][1])
        assert len(pdfs) == 1
        content = pdfs[0].get('content') or pdfs[0].get('data')
        if isinstance(content, str):
            content = base64.b64decode(content)
        assert content[:4] == b'%PDF'
        assert any(f"/verify/{reg['certificate_id']}" in m['html'] for m in d['mail'] if m['to'] == d['people'][key][1])
    assert not _pdfs_to(d, d['people']['cy'][1])


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_verify_shows_an_issued_certificate_and_refuses_a_random_id(ended):
    d = ended
    d['owner'].post(f"/spoc/end_event/{d['event_id']}", data={'template_id': '1'})
    cert_id = _reg(d, 'ben')['certificate_id']
    visitor = d['app'].test_client()

    page = visitor.get(f'/verify/{cert_id}')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Certificate Verified' in html and 'Ben Attendee' in html and d['title'] in html

    pdf = visitor.get(f'/verify/{cert_id}/download')
    assert pdf.status_code == 200 and pdf.mimetype == 'application/pdf' and pdf.data[:4] == b'%PDF'

    bogus = visitor.get(f'/verify/{uuid.uuid4().hex}{uuid.uuid4().hex}')
    assert bogus.status_code == 404 and 'invalid' in bogus.get_data(as_text=True).lower()

    # The attendee's certificate page links the official PDF
    student = d['app'].test_client()
    with student.session_transaction() as sess:
        sess.update(user_id=d['people']['ben'][1], role='Student', name='Ben Attendee')
    page = student.get(f"/participant/certificate/{d['people']['ben'][0]}")
    assert page.status_code == 200 and f'/verify/{cert_id}/download' in page.get_data(as_text=True)


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_bulk_button_issues_through_the_same_path_once(ended):
    d = ended
    resp = d['owner'].post(f"/spoc/bulk_certs/{d['event_id']}")
    assert resp.status_code == 302
    first = {key: _reg(d, key).get('certificate_id') for key in ('ana', 'ben', 'cy')}
    assert first['ana'] and first['ben'] and not first['cy']
    assert len(d['mail']) == 2

    # Pressing it again, or ending the event afterwards, issues nothing twice
    d['owner'].post(f"/spoc/bulk_certs/{d['event_id']}")
    d['owner'].post(f"/spoc/end_event/{d['event_id']}", data={'template_id': '1'})
    assert {key: _reg(d, key).get('certificate_id') for key in ('ana', 'ben', 'cy')} == first
    assert len(d['mail']) == 2

    # Another SPOC can't issue this event's certificates
    other = f"{_unique('otherspoc')}@test.edu"
    _user(d['db'], other, 'ClubSPOC')
    assert _login(d['app'], other, 'ClubSPOC').post(f"/spoc/bulk_certs/{d['event_id']}").status_code == 403
