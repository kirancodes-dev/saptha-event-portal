"""
tests/test_wallet_passes.py — UPG-156: Apple Wallet and Google Wallet passes
for a ticket, hidden until their keys are set, carrying the ticket's signed
token that every scanner accepts. Keys are made here; nothing is sent out.
"""
import datetime
import hashlib
import io
import json
import zipfile

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

import routes_ticket
from tests.test_checkin_unified import _scan, _ticket_qr_text, gate  # noqa: F401  (fixture)
from tests.test_integration_flow import _login, _unique, _user


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _cert(key, name):
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))


def _pem_key(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


@pytest.fixture
def wallet_keys(monkeypatch, tmp_path):
    pass_key, wwdr_key, google_key = _key(), _key(), _key()
    pass_cert = _cert(pass_key, 'Pass Type ID: pass.edu.test')
    (tmp_path / 'wwdr.pem').write_bytes(_cert(wwdr_key, 'WWDR').public_bytes(serialization.Encoding.PEM))
    monkeypatch.setenv('APPLE_PASS_TYPE_ID', 'pass.edu.test')
    monkeypatch.setenv('APPLE_TEAM_ID', 'TEAM123456')
    monkeypatch.setenv('APPLE_PASS_CERT', pass_cert.public_bytes(serialization.Encoding.PEM).decode())
    monkeypatch.setenv('APPLE_PASS_KEY', _pem_key(pass_key))
    monkeypatch.setenv('APPLE_WWDR_CERT', str(tmp_path / 'wwdr.pem'))    # a file path works too
    monkeypatch.setenv('GOOGLE_WALLET_ISSUER_ID', '3388000000012345678')
    monkeypatch.setenv('GOOGLE_WALLET_SERVICE_ACCOUNT', json.dumps(
        {'client_email': 'wallet@test-project.iam.gserviceaccount.com', 'private_key': _pem_key(google_key)}))
    return {'pass_cert': pass_cert, 'google_public': google_key.public_key()}


def _page(d):
    return d['student'].get(f"/ticket/{d['reg_id']}").get_data(as_text=True)


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_buttons_show_only_with_keys(gate, wallet_keys, monkeypatch):  # noqa: F811
    d = gate
    page = _page(d)
    assert 'Add to Apple Wallet' in page and 'Save to Google Wallet' in page
    for name in ('APPLE_PASS_KEY', 'GOOGLE_WALLET_ISSUER_ID'):
        monkeypatch.setenv(name, '')
    page = _page(d)
    assert 'Add to Apple Wallet' not in page and 'Save to Google Wallet' not in page
    assert d['student'].get(f"/ticket/{d['reg_id']}/wallet/apple.pkpass").status_code == 404
    assert d['student'].get(f"/ticket/{d['reg_id']}/wallet/google").status_code == 404


def test_no_buttons_without_any_keys(gate):  # noqa: F811
    page = _page(gate)
    assert 'data-wallet' not in page


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_pkpass_carries_the_signed_token_and_the_scanner_accepts_it(gate, wallet_keys, monkeypatch):  # noqa: F811
    d = gate
    resp = d['student'].get(f"/ticket/{d['reg_id']}/wallet/apple.pkpass")
    assert resp.status_code == 200 and resp.mimetype == 'application/vnd.apple.pkpass'
    z = zipfile.ZipFile(io.BytesIO(resp.data))
    assert {'pass.json', 'manifest.json', 'signature', 'icon.png'} <= set(z.namelist())
    data = json.loads(z.read('pass.json'))
    assert data['passTypeIdentifier'] == 'pass.edu.test' and data['serialNumber'] == d['reg_id']
    assert data['eventTicket']['auxiliaryFields'][0]['value'] == 'Tara Ticket'

    # The manifest lists every file's SHA-1, and is signed with the pass certificate
    manifest = json.loads(z.read('manifest.json'))
    for name, digest in manifest.items():
        assert hashlib.sha1(z.read(name)).hexdigest() == digest
    signers = pkcs7.load_der_pkcs7_certificates(z.read('signature'))
    assert wallet_keys['pass_cert'] in signers

    # The barcode is the ticket page's QR: its signed token checks in
    message = data['barcodes'][0]['message']
    assert message == _ticket_qr_text(d, monkeypatch)
    token = message.split('/ticket/verify/', 1)[1]
    with d['app'].app_context():
        assert routes_ticket._parse_signed_token(token)[:2] == (True, d['reg_id'])
    first = _scan(d['staff'], message, d['event_id'])
    assert first.status_code == 200 and first.get_json()['status'] == 'success'


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_google_wallet_link_carries_the_same_token_and_event(gate, wallet_keys, monkeypatch):  # noqa: F811
    d = gate
    resp = d['student'].get(f"/ticket/{d['reg_id']}/wallet/google")
    assert resp.status_code == 302
    link = resp.headers['Location']
    assert link.startswith('https://pay.google.com/gp/v/save/')
    claims = jwt.decode(link.rsplit('/', 1)[1], wallet_keys['google_public'], algorithms=['RS256'], audience='google')
    assert claims['iss'] == 'wallet@test-project.iam.gserviceaccount.com' and claims['typ'] == 'savetowallet'
    ticket = claims['payload']['eventTicketObjects'][0]
    ticket_class = claims['payload']['eventTicketClasses'][0]
    assert ticket['barcode']['value'] == _ticket_qr_text(d, monkeypatch)
    assert ticket['classId'] == ticket_class['id'] and ticket['ticketHolderName'] == 'Tara Ticket'
    event = d['db'].collection('events').document(d['event_id']).get().to_dict()
    assert ticket_class['eventName']['defaultValue']['value'] == event['title']
    assert ticket_class['venue']['name']['defaultValue']['value'] == event['venue']
    assert ticket_class['dateTime']['start'].startswith(event['date'])


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_another_persons_ticket_is_403_for_both(gate, wallet_keys):  # noqa: F811
    d = gate
    stranger = f"{_unique('stranger')}@test.edu"
    _user(d['db'], stranger, 'Student')
    other = _login(d['app'], stranger, 'Student')
    assert other.get(f"/ticket/{d['reg_id']}/wallet/apple.pkpass").status_code == 403
    assert other.get(f"/ticket/{d['reg_id']}/wallet/google").status_code == 403
    # Logged out: to the login page, no pass
    anon = d['app'].test_client().get(f"/ticket/{d['reg_id']}/wallet/apple.pkpass")
    assert anon.status_code == 302 and 'pkpass' not in anon.headers.get('Content-Type', '')


def test_a_cancelled_registration_gets_no_pass(gate, wallet_keys):  # noqa: F811
    d = gate
    d['db'].collection('registrations').document(d['reg_id']).update({'status': 'Cancelled'})
    assert d['student'].get(f"/ticket/{d['reg_id']}/wallet/apple.pkpass").status_code == 404
    assert 'Add to Apple Wallet' not in _page(d)


def test_before_the_qr_opens_the_registrant_gets_no_pass(gate, wallet_keys):  # noqa: F811
    d = gate
    d['db'].collection('events').document(d['event_id']).update({'date': '2031-01-01'})
    assert d['student'].get(f"/ticket/{d['reg_id']}/wallet/google").status_code == 403
    assert 'Save to Google Wallet' not in _page(d)
