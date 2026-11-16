"""
tests/test_data_handling.py — UPG-274 on the real database layer: a person's
data download holds their feedback and the certificates issued to them;
deleting the account takes their name, email and comment off their feedback
(the rating stays for the event's report) and leaves no document whose ID
holds the email; the public notice and the security, data and app documents
say what the code does and claim no certification, audit or SLA.
"""
import json
import os
import re

from services_privacy import PRIVACY_NOTICE_VERSION, anonymise_account, own_data
from tests.test_certificate_lists import site  # noqa: F401  (fixture)
from tests.test_integration_flow import _login, _unique, _user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as handle:
        return handle.read()


def _attendee(d, name='Asha Feedback'):
    """A student who attended a finished event, gave feedback and holds a certificate."""
    db = d['db']
    email = f"{_unique('dh')}@test.edu"
    _user(db, email, 'Student', name=name)
    event_id = d['event'](people=1)
    reg_id = _unique('REG')
    db.collection('registrations').document(reg_id).set({
        'event_id': event_id, 'lead_name': name, 'lead_email': email, 'status': 'Confirmed', 'attendance': 'Present'})
    import services_certificates as certs
    certs.issue_event(db, event_id, 'organiser@test.edu')
    response_id = f"{event_id}:{reg_id}:{email}"
    db.collection('feedback_responses').document(response_id).set({
        'event_id': event_id, 'reg_id': reg_id, 'email': email, 'name': name, 'rating': 4,
        'tags': ['Well organised'], 'comments': 'Asha says the hall was too warm'})
    return email, event_id, reg_id, response_id


# ── Criterion 1: the download ───────────────────────────────────────────────

def test_the_download_holds_the_persons_feedback_and_certificates_and_nobody_elses(site):  # noqa: F811
    d = site
    email, event_id, reg_id, _ = _attendee(d)
    other, other_event, _, _ = _attendee(d, name='Bela Other')
    client = _login(d['app'], email, 'Student')
    response = client.post('/compliance/export-data')
    assert response.status_code == 200 and 'attachment' in response.headers['Content-Disposition']
    export = response.get_json()
    assert export['privacy_notice_version'] == PRIVACY_NOTICE_VERSION == '2026-11-15'

    [feedback] = export['sections']['feedback']
    assert feedback['rating'] == 4 and feedback['comments'] == 'Asha says the hall was too warm'
    assert feedback['event_id'] == event_id

    [certificate] = export['sections']['certificates']
    assert certificate['event_id'] == event_id and certificate['name_on_certificate'] == 'Asha Feedback'
    assert re.fullmatch(r'SE-[0-9A-Z-]+', certificate['number']) and certificate['status']
    assert 'pdf_key' not in certificate and 'pdf_sha256' not in certificate     # what it says, not the file

    text = json.dumps(export)
    assert other not in text and 'Bela Other' not in text and other_event not in text
    assert 'password' not in text.lower()


# ── Criterion 2: deletion ───────────────────────────────────────────────────

def test_deleting_the_account_takes_the_person_off_their_feedback_and_keeps_the_rating(site):  # noqa: F811
    d = site
    db = d['db']
    email, event_id, reg_id, response_id = _attendee(d)
    kept_email, kept_event, _, kept_id = _attendee(d, name='Bela Other')

    counts = anonymise_account(db, email)
    assert counts['feedback'] == 1 and counts['registrations'] == 1

    assert not db.collection('feedback_responses').document(response_id).get().exists
    mine = [(doc.id, doc.to_dict()) for doc in db.collection('feedback_responses').where('event_id', '==', event_id).stream()]
    assert len(mine) == 1                                                       # still one response for the report
    new_id, data = mine[0]
    assert data['rating'] == 4 and data['tags'] == ['Well organised']
    assert data['comments'] == '' and data['name'] == 'Deleted user'
    assert email not in new_id and email not in json.dumps(data) and 'Asha' not in json.dumps(data)
    assert data['email'].endswith('@deleted.invalid')
    reg = db.collection('registrations').document(reg_id).get().to_dict()
    assert reg['lead_email'] == data['email']                                   # the response still belongs to its registration

    # nothing is left to download, and the account is gone
    assert not db.collection('users').document(email).get().exists
    assert own_data(db, email)['sections']['feedback'] == []

    # someone else's feedback is untouched
    other = db.collection('feedback_responses').document(kept_id).get().to_dict()
    assert other['email'] == kept_email and other['comments'] == 'Asha says the hall was too warm'

    # the organiser's feedback report still counts the rating
    from tests.test_event_summary import _row
    report = d['owner'].get(f'/reports/events?event={event_id}').get_data(as_text=True)
    assert _row(report, event_id)['feedback'] == '1' and email not in report


def test_a_certificate_already_issued_is_kept_and_the_document_says_so(site):  # noqa: F811
    d = site
    email, event_id, _, _ = _attendee(d)
    import services_certificates as certs
    before = [c['number'] for c in certs.for_person([email])]
    assert len(before) == 1
    anonymise_account(d['db'], email)
    assert [c['number'] for c in certs.for_person([email])] == before            # kept, by design
    doc = _read('docs/DATA_HANDLING.md')
    assert 'Certificates already issued' in doc and 'Certificates after deletion' in doc


# ── Criterion 3: the notice and the documents say what the code does ────────

UNSUPPORTED = (
    r'ISO[ -]?27001', r'SOC ?2', r'\bcertified\b', r'penetration[- ]tested', r'independently audited',
    r'regular security audits', r'zero[- ]trust', r'tamper[- ]evident', r'tamper[- ]proof', r'military[- ]grade',
    r'bank[- ]grade', r'99\.\d+ ?%', r'guaranteed uptime', r'GDPR[- ]compliant', r'DPDP[- ]compliant',
    r'fully compliant', r'issued in compliance',
)


def _claims(text):
    """The unsupported claims a text makes, leaving out sentences that deny them."""
    found = []
    for sentence in re.split(r'(?<=[.!?:])\s+|\n\s*\n|\|', text):
        if re.search(r'\b(no|not|never|none|nor|without|unless|neither)\b', sentence, re.I):
            continue
        found += [p for p in UNSUPPORTED if re.search(p, sentence, re.I)]
    return found


def test_the_public_notice_states_only_what_the_code_does(real_app):
    flask_app, _ = real_app
    page = flask_app.test_client().get('/privacy')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert PRIVACY_NOTICE_VERSION in html or '15 November 2026' in html
    for wrong in ('Firestore', 'Firebase', 'Redis', 'bcrypt', 'regular security audits', 'issued in compliance',
                  'stored in India'):
        assert wrong not in html, wrong
    for right in ('Google Cloud', 'Brevo', 'feedback', 'audit log'):
        assert right in html, right
    assert _claims(re.sub(r'<[^>]+>', ' ', html)) == []


def test_the_documents_make_no_claim_the_repository_cannot_support():
    for path in ('docs/SECURITY.md', 'docs/DATA_HANDLING.md', 'docs/PWA.md'):
        text = _read(path)
        assert _claims(text) == [], path
    security, data, pwa = (_read(p) for p in ('docs/SECURITY.md', 'docs/DATA_HANDLING.md', 'docs/PWA.md'))
    assert 'no claim of certification' in security and 'Known limits' in security
    assert 'not a legal opinion' in data and 'Questions for human review' in data
    assert 'Not reached by the download or the deletion' in data
    # the app document names the files and routes that exist
    assert '/manifest.webmanifest' in pwa and 'static/manifest.json' not in pwa
    assert 'sync-offline' not in pwa and 'public keys' not in pwa
    for path in ('static/sw.js', 'static/js/offline-sync.js', 'static/manifest.webmanifest'):
        assert path in pwa and os.path.exists(os.path.join(ROOT, path)), path


def test_every_file_and_setting_the_security_document_names_exists():
    security = _read('docs/SECURITY.md')
    for name in set(re.findall(r'`([a-z_0-9]+\.py)`', security)):
        assert os.path.exists(os.path.join(ROOT, name)), name
    config = _read('config.py') + _read('app.py') + _read('routes_auth.py')
    for setting in ('MASTER_SECRET_KEY', 'SECRET_KEY', 'REDIS_URL', 'LOGIN_THROTTLE_'):
        assert setting in security and setting in config, setting
    for linked in re.findall(r'\]\(([A-Z_]+\.md)\)', security + _read('docs/DATA_HANDLING.md') + _read('docs/PWA.md')):
        assert os.path.exists(os.path.join(ROOT, 'docs', linked)), linked
