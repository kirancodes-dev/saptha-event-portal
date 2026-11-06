"""
tests/test_certificate_delivery.py — UPG-125 on the real database layer: one
email per certificate with a signed download link that expires (and fails
when altered), "My certificates" for students and faculty (team members
too), the ledger's links, the PNG for LinkedIn and the share link; UPG-133:
the certificate email escapes what it prints.
"""
import io
import re
import time

import pytest
from PIL import Image

import services_certificates as certs
from tests.test_certificate_types import _signature
from tests.test_integration_flow import _create_event, _login, _unique, _user
from utils_storage import get_private


@pytest.fixture
def mail(monkeypatch):
    import utils_email
    sent = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, attachments=None, *a, **k:
                        sent.append({'to': to, 'subject': subject, 'html': html}) or True)
    return sent


@pytest.fixture
def site(real_app, mail):
    flask_app, db = real_app
    spoc = f"{_unique('delspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')

    def event(**fields):
        import services_signatories
        event_id = _create_event(owner, db, _unique('Delivered Event'), '2031-03-03', team=True)
        db.collection('events').document(event_id).update(dict({'status': 'completed', 'staff': []}, **fields))
        services_signatories.add(db, event_id, name='Dr. A. Kumar', title='Principal', image=_signature(), actor=spoc)
        return event_id

    def person(event_id, name, **fields):
        email = f"{_unique(name.split()[0].lower())}@test.edu"
        _user(db, email, 'Student', name=name)
        db.collection('registrations').document(_unique('REG')).set(dict({
            'event_id': event_id, 'lead_name': name, 'lead_email': email, 'status': 'Confirmed',
            'attendance': 'Present'}, **fields))
        return email
    return {'app': flask_app, 'db': db, 'spoc': spoc, 'owner': owner, 'event': event, 'person': person,
            'mail': mail, 'visitor': flask_app.test_client()}


def _link(message):
    return re.search(r'href="(?:https?://[^"/]+)?(/certificates/download/[^"]+)"', message['html']).group(1)


def _issue(d, event_id):
    return certs.issue_event(d['db'], event_id, d['spoc'], only=['participation'])


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_one_email_per_certificate_with_a_link_that_expires_and_resists_tampering(site, monkeypatch):
    d = site
    event_id = d['event']()
    asha, ravi = d['person'](event_id, 'Asha Rao'), d['person'](event_id, 'Ravi Kumar')
    _issue(d, event_id)
    to_people = [m for m in d['mail'] if m['to'] in (asha, ravi)]
    assert sorted(m['to'] for m in to_people) == sorted([asha, ravi])
    [message] = [m for m in to_people if m['to'] == asha]
    [cert] = [c for c in certs.for_event(event_id) if c['email'] == asha]
    assert cert['emailed_at'] is not None and cert['number'] in message['html']

    link = _link(message)
    resp = d['visitor'].get(link)
    assert resp.status_code == 200 and resp.mimetype == 'application/pdf'
    assert resp.data == get_private(cert['pdf_key'])
    assert f"Certificate-{cert['number']}.pdf" in resp.headers['Content-Disposition']

    tampered = link[:-3] + ('aaa' if not link.endswith('aaa') else 'bbb')
    assert d['visitor'].get(tampered).status_code == 404
    real_time = time.time
    monkeypatch.setattr(time, 'time', lambda: real_time() + 31 * 86400)    # past CERT_LINK_DAYS (30)
    expired = d['visitor'].get(link)
    assert expired.status_code == 410 and 'This link has expired' in expired.get_data(as_text=True)
    monkeypatch.setattr(time, 'time', real_time)

    before = len(d['mail'])
    _issue(d, event_id)                                                         # a re-run sends nothing
    assert certs.email_once(cert['id']) == 'already' and len(d['mail']) == before


def test_a_failed_send_is_retried_and_still_sent_once(site, monkeypatch):
    import utils_email
    d = site
    event_id = d['event']()
    email = d['person'](event_id, 'Flaky Farah')
    monkeypatch.setattr(utils_email, '_send', lambda *a, **k: False)
    _issue(d, event_id)
    [cert] = [c for c in certs.for_event(event_id) if c['email'] == email]
    assert cert['emailed_at'] is None                                          # given back for the retry
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k:
                        d['mail'].append({'to': to, 'subject': subject, 'html': html}) or True)
    assert certs.email_once(cert['id']) == 'sent' and certs.email_once(cert['id']) == 'already'
    assert [m['to'] for m in d['mail']].count(email) == 1


def test_a_replaced_certificates_link_says_so(site):
    d = site
    event_id = d['event']()
    email = d['person'](event_id, 'Old Olga')
    _issue(d, event_id)
    [cert] = [c for c in certs.for_event(event_id) if c['email'] == email]
    link = _link(next(m for m in d['mail'] if m['to'] == email))
    certs.update(cert['id'], is_current=False, status='superseded')
    resp = d['visitor'].get(link)
    assert resp.status_code == 410 and 'This certificate was replaced' in resp.get_data(as_text=True)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_my_certificates_lists_the_persons_own_including_team_members(site):
    d = site
    event_id = d['event']()
    mate = f"{_unique('mate')}@test.edu"
    _user(d['db'], mate, 'Student', name='Mira Mate')
    lead = d['person'](event_id, 'Leela Lead', team_name='Byte Club',
                       members=[{'name': 'Mira Mate', 'email': mate, 'attendance': 'Present'}])
    other = d['person'](d['event'](), 'Someone Else')
    _issue(d, event_id)
    numbers = {c['email']: c['number'] for c in certs.for_event(event_id)}
    for email, name in ((lead, 'Leela Lead'), (mate, 'Mira Mate')):
        page = _login(d['app'], email, 'Student').get('/certificates/mine').get_data(as_text=True)
        assert numbers[email] in page and 'Certificate of Participation' in page, name
        assert all(n not in page for e, n in numbers.items() if e != email)
    assert 'No certificates yet' in _login(d['app'], other, 'Student').get('/certificates/mine').get_data(as_text=True)

    student = _login(d['app'], lead, 'Student')
    assert 'href="/certificates/mine"' in student.get('/participant/dashboard').get_data(as_text=True)
    ledger = student.get('/participant/ledger').get_data(as_text=True)
    assert f"/certificates/c/{numbers[lead]}/pdf" in ledger
    assert student.get(f"/certificates/c/{numbers[lead]}/pdf").data == \
        get_private(next(c for c in certs.for_event(event_id) if c['email'] == lead)['pdf_key'])


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_png_is_an_image_of_the_certificate_and_the_share_link_verifies(site):
    d = site
    event_id = d['event']()
    email = d['person'](event_id, 'Pia Picture')
    _issue(d, event_id)
    [cert] = [c for c in certs.for_event(event_id) if c['email'] == email]
    student = _login(d['app'], email, 'Student')
    resp = student.get(f"/certificates/c/{cert['number']}/png")
    image = Image.open(io.BytesIO(resp.data))
    assert resp.mimetype == 'image/png' and image.format == 'PNG'
    assert image.size[0] > 1500 and abs(image.size[0] / image.size[1] - 2 ** 0.5) < 0.02   # A4 landscape
    assert len(image.convert('RGB').getcolors(maxcolors=1_000_000) or []) > 50             # a drawn page, not blank

    page = student.get('/certificates/mine').get_data(as_text=True)
    share = re.search(r'href="(?:https?://[^"/]+)?(/verify/[^"]+)"', page).group(1)
    assert share == f"/verify/{cert['number']}"
    shared = d['visitor'].get(share).get_data(as_text=True)
    assert 'Valid certificate' in shared and 'Pia Picture' in shared
    assert 'linkedin.com/sharing/share-offsite' in page

    stranger = d['person'](d['event'](), 'Sam Stranger')
    for kind in ('pdf', 'png'):
        assert _login(d['app'], stranger, 'Student').get(f"/certificates/c/{cert['number']}/{kind}").status_code == 403
    assert d['owner'].get(f"/certificates/c/{cert['number']}/pdf").status_code == 200        # the event's organiser


# ── UPG-133 ─────────────────────────────────────────────────────────────────

def test_upg133_the_certificate_email_shows_markup_as_text(site):
    d = site
    event_id = d['event'](title='<i>Ital</i> & Co')
    email = d['person'](event_id, '<b>Ann</b>')
    _issue(d, event_id)
    [message] = [m for m in d['mail'] if m['to'] == email]
    assert '&lt;b&gt;Ann&lt;/b&gt;' in message['html'] and '<b>Ann</b>' not in message['html']
    assert '&lt;i&gt;Ital&lt;/i&gt; &amp; Co' in message['html'] and '<i>Ital</i>' not in message['html']
    # The old path's email too, while it still sends (until UPG-138)
    import utils_email
    utils_email._send_cert_email('ann@test.edu', '<b>Ann</b>', '<i>Ital</i> & Co', 'participation', 0, 0, b'%PDF',
                                 reg_id='REG-<x>', certificate_id='abc')
    old = d['mail'][-1]['html']
    assert '&lt;b&gt;Ann&lt;/b&gt;' in old and '<b>Ann</b>' not in old and '<i>Ital</i>' not in old
    assert 'REG-&lt;x&gt;' in old
