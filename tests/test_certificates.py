"""
tests/test_certificates.py — UPG-06 on the real database layer: certificates
go out through one path, whether the SPOC ends the event or presses "bulk
certificates". Each attendee marked Present gets a PDF, a certificate ID and
verify URL on their registration and an email; nobody gets one twice, and
/verify/<id> confirms it.

Since UPG-138 the one path is services_certificates (a `certificates` row, the
PDF stored privately and emailed as a signed link instead of an attachment,
the public page at /verify/<number>, the person's own download), and places
come from published results rather than the top scores at the end. Every
check below is the old one on that path.
"""
import datetime
import re
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
def ended(real_app, mail, monkeypatch):
    """An event with two attendees marked Present (one scored) and one absent."""
    flask_app, db = real_app
    monkeypatch.setenv('TASK_INLINE_TIMEOUT', '120')      # the background run finishes inside the request
    spoc = f"{_unique('certspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    title = _unique('Certificate Day')
    event_id = _create_event(owner, db, title, datetime.date.today().isoformat(), team=False)
    import services_signatories       # no certificate without a signature (UPG-123)
    from tests.test_certificate_types import _signature
    services_signatories.add(db, event_id, name='Dr. A. Kumar', title='Principal', image=_signature(), actor=spoc)
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
    """The PDFs each certificate email to `email` delivers (through its signed link)."""
    visitor = d['app'].test_client()
    out = []
    for m in d['mail']:
        if m['to'] == email:
            link = re.search(r'href="(?:https?://[^"/]+)?(/certificates/download/[^"]+)"', m['html'])
            if link:
                out.append(visitor.get(link.group(1)).data)
    return out


def _student(d, key):
    client = d['app'].test_client()
    with client.session_transaction() as sess:
        sess.update(user_id=d['people'][key][1], role='Student', name=f'{key.title()} Attendee')
    return client


def _attendee_mail(d):
    attendees = {email for _, email in d['people'].values()}
    return [m for m in d['mail'] if m['to'] in attendees]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_ending_the_event_issues_exactly_one_certificate_per_attendee(ended, caplog):
    import services_certificates as certs
    d = ended
    resp = d['owner'].post(f"/spoc/end_event/{d['event_id']}", data={'template_id': '1'})
    assert resp.status_code == 302
    assert not [r for r in caplog.records if 'failed' in r.getMessage().lower() and r.levelname == 'ERROR']

    issued = {key: _reg(d, key).get('certificate_id') for key in ('ana', 'ben', 'cy')}
    assert issued['ana'] and issued['ben'] and not issued['cy']
    assert issued['ana'] != issued['ben']
    assert _reg(d, 'ben')['certificate_type'] == 'participation'
    for key in ('ana', 'ben'):
        reg = _reg(d, key)
        assert reg['certificate_verify_url'].endswith(f"/verify/{reg['certificate_id']}")
        record = certs.by_number(reg['certificate_id'])                 # was verified_certificates
        assert record['event_id'] == d['event_id'] and record['name'] == f'{key.title()} Attendee'
        pdfs = _pdfs_to(d, d['people'][key][1])
        assert len(pdfs) == 1
        assert pdfs[0][:4] == b'%PDF'
        assert any(f"/verify/{reg['certificate_id']}" in m['html'] for m in d['mail'] if m['to'] == d['people'][key][1])
    assert not _pdfs_to(d, d['people']['cy'][1])

    # The scored attendee's place: from the published results (was: the top scores at the end)
    d['owner'].post(f"/spoc/publish_results/{d['event_id']}")
    assert _reg(d, 'ana')['certificate_type'] == 'winner'
    assert _reg(d, 'ben')['certificate_type'] == 'participation'
    winner = certs.by_number(_reg(d, 'ana')['certificate_id'])
    assert winner['cert_type'] == 'winner' and winner['position'] == 1 and winner['name'] == 'Ana Attendee'


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_verify_shows_an_issued_certificate_and_refuses_a_random_id(ended):
    d = ended
    d['owner'].post(f"/spoc/end_event/{d['event_id']}", data={'template_id': '1'})
    cert_id = _reg(d, 'ben')['certificate_id']
    visitor = d['app'].test_client()

    page = visitor.get(f'/verify/{cert_id}')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Valid certificate' in html and 'Ben Attendee' in html and d['title'] in html

    # The PDF: the attendee's own download (no longer public)
    pdf = _student(d, 'ben').get(f'/certificates/c/{cert_id}/pdf')
    assert pdf.status_code == 200 and pdf.mimetype == 'application/pdf' and pdf.data[:4] == b'%PDF'
    assert visitor.get(f'/certificates/c/{cert_id}/pdf').status_code == 302          # sign in first

    bogus = visitor.get(f'/verify/{uuid.uuid4().hex}{uuid.uuid4().hex}')
    assert bogus.status_code == 404 and 'invalid' in bogus.get_data(as_text=True).lower()

    # The attendee's certificate page links the official PDF
    page = _student(d, 'ben').get(f"/participant/certificate/{d['people']['ben'][0]}")
    assert page.status_code == 200 and f'/certificates/c/{cert_id}/pdf' in page.get_data(as_text=True)


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_bulk_button_issues_through_the_same_path_once(ended):
    d = ended
    # Not before the event is over (UPG-124)
    d['owner'].post(f"/spoc/bulk_certs/{d['event_id']}")
    assert not _reg(d, 'ana').get('certificate_id') and not _attendee_mail(d)
    d['db'].collection('events').document(d['event_id']).update({'status': 'completed'})

    resp = d['owner'].post(f"/spoc/bulk_certs/{d['event_id']}")
    assert resp.status_code == 302
    first = {key: _reg(d, key).get('certificate_id') for key in ('ana', 'ben', 'cy')}
    assert first['ana'] and first['ben'] and not first['cy']
    assert len(_attendee_mail(d)) == 2

    # Pressing it again, or ending the event afterwards, issues nothing twice
    d['owner'].post(f"/spoc/bulk_certs/{d['event_id']}")
    d['owner'].post(f"/spoc/end_event/{d['event_id']}", data={'template_id': '1'})
    assert {key: _reg(d, key).get('certificate_id') for key in ('ana', 'ben', 'cy')} == first
    assert len(_attendee_mail(d)) == 2

    # Another SPOC can't issue this event's certificates
    other = f"{_unique('otherspoc')}@test.edu"
    _user(d['db'], other, 'ClubSPOC')
    assert _login(d['app'], other, 'ClubSPOC').post(f"/spoc/bulk_certs/{d['event_id']}").status_code == 403
