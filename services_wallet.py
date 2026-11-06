"""
services_wallet.py — Apple Wallet and Google Wallet passes for a ticket (UPG-156).

Each pass carries the same QR as the ticket page: the ticket's verify link
with its signed token, so every scanner accepts it (``routes_ticket``).

Both are off, and their buttons hidden, until their keys are set:

  Apple:  APPLE_PASS_TYPE_ID, APPLE_TEAM_ID, APPLE_PASS_CERT, APPLE_PASS_KEY,
          APPLE_WWDR_CERT (PEM text or a file path), APPLE_PASS_KEY_PASSWORD
          (optional). The certificate comes from the Apple developer account.
  Google: GOOGLE_WALLET_ISSUER_ID and GOOGLE_WALLET_SERVICE_ACCOUNT (the
          service account's JSON key, as text or a file path).

The keys are secrets: Secret Manager in production, never in git.
"""
import datetime
import hashlib
import io
import json
import os
import re
import zipfile
from typing import Optional

APPLE_KEYS = ('APPLE_PASS_TYPE_ID', 'APPLE_TEAM_ID', 'APPLE_PASS_CERT', 'APPLE_PASS_KEY', 'APPLE_WWDR_CERT')
GOOGLE_KEYS = ('GOOGLE_WALLET_ISSUER_ID', 'GOOGLE_WALLET_SERVICE_ACCOUNT')
GOOGLE_SAVE_URL = 'https://pay.google.com/gp/v/save/'
ORGANIZATION = 'SNPSU SapthaEvent'
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'app-icon.png')


def _setting(name: str) -> str:
    return (os.environ.get(name) or '').strip()


def _pem_or_file(name: str) -> bytes:
    """A setting holding PEM/JSON text, or the path of a file holding it."""
    value = _setting(name)
    if value.startswith('-----BEGIN') or value.startswith('{'):
        return value.encode()
    with open(value, 'rb') as f:
        return f.read()


def apple_configured() -> bool:
    return all(_setting(k) for k in APPLE_KEYS)


def google_configured() -> bool:
    return all(_setting(k) for k in GOOGLE_KEYS)


def _when(event: dict) -> str:
    date = str(event.get('date') or '')[:10]
    time = str(event.get('time') or '')[:5]
    return f"{date} {time}".strip()


def _relevant_date(event: dict) -> Optional[str]:
    """The event's start in India time, so the pass shows on the lock screen."""
    try:
        start = datetime.datetime.fromisoformat(f"{str(event.get('date'))[:10]}T{str(event.get('time') or '09:00')[:5]}")
    except ValueError:
        return None
    return start.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30))).isoformat()


# ── Apple Wallet ────────────────────────────────────────────────────────────

def pass_json(reg_id: str, reg: dict, event: dict, qr_message: str) -> dict:
    title = event.get('title') or reg.get('event_title') or 'Event'
    secondary = [{'key': 'date', 'label': 'DATE', 'value': _when(event) or 'To be announced'}]
    if event.get('venue'):
        secondary.append({'key': 'venue', 'label': 'VENUE', 'value': str(event['venue'])})
    auxiliary = [{'key': 'name', 'label': 'NAME', 'value': reg.get('lead_name') or ''},
                 {'key': 'ticket', 'label': 'TICKET', 'value': reg.get('reg_id') or reg_id}]
    if reg.get('team_name') and reg.get('team_name') != 'Individual':
        auxiliary.append({'key': 'team', 'label': 'TEAM', 'value': reg['team_name']})
    barcode = {'format': 'PKBarcodeFormatQR', 'message': qr_message, 'messageEncoding': 'iso-8859-1',
               'altText': reg.get('reg_id') or reg_id}
    data = {
        'formatVersion': 1,
        'passTypeIdentifier': _setting('APPLE_PASS_TYPE_ID'),
        'teamIdentifier': _setting('APPLE_TEAM_ID'),
        'serialNumber': str(reg_id),
        'organizationName': ORGANIZATION,
        'description': f'Ticket for {title}',
        'logoText': 'SapthaEvent',
        'backgroundColor': 'rgb(11, 37, 69)', 'foregroundColor': 'rgb(255, 255, 255)',
        'labelColor': 'rgb(212, 175, 55)',
        'eventTicket': {'primaryFields': [{'key': 'event', 'label': 'EVENT', 'value': title}],
                        'secondaryFields': secondary, 'auxiliaryFields': auxiliary},
        'barcodes': [barcode],
        'barcode': barcode,   # iOS 8 and older
    }
    relevant = _relevant_date(event)
    if relevant:
        data['relevantDate'] = relevant
    return data


def _sign(manifest: bytes) -> bytes:
    """The manifest's detached PKCS#7 signature with the pass certificate."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7
    cert = x509.load_pem_x509_certificate(_pem_or_file('APPLE_PASS_CERT'))
    password = _setting('APPLE_PASS_KEY_PASSWORD').encode() or None
    key = serialization.load_pem_private_key(_pem_or_file('APPLE_PASS_KEY'), password=password)
    wwdr = x509.load_pem_x509_certificate(_pem_or_file('APPLE_WWDR_CERT'))
    return (pkcs7.PKCS7SignatureBuilder().set_data(manifest)
            .add_signer(cert, key, hashes.SHA256()).add_certificate(wwdr)
            .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary]))


def build_pkpass(reg_id: str, reg: dict, event: dict, qr_message: str) -> bytes:
    """A signed .pkpass: pass.json, icons, manifest.json and signature."""
    with open(ICON, 'rb') as f:
        icon = f.read()
    files = {'pass.json': json.dumps(pass_json(reg_id, reg, event, qr_message), ensure_ascii=False).encode(),
             'icon.png': icon, 'icon@2x.png': icon, 'logo.png': icon}
    # Apple's pass format requires SHA-1 manifest hashes; the manifest itself is
    # signed with the pass certificate (PKCS#7, SHA-256) below
    sums = {name: hashlib.sha1(body).hexdigest() for name, body in files.items()}  # nosec
    manifest = json.dumps(sums, sort_keys=True).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, body in files.items():
            z.writestr(name, body)
        z.writestr('manifest.json', manifest)
        z.writestr('signature', _sign(manifest))
    return out.getvalue()


# ── Google Wallet ───────────────────────────────────────────────────────────

def _wallet_id(value: str) -> str:
    """Google Wallet ids allow letters, digits, '.', '_' and '-'."""
    return re.sub(r'[^A-Za-z0-9._-]', '_', str(value))[:100]


def google_claims(reg_id: str, reg: dict, event_id: str, event: dict, qr_message: str, origin: str) -> dict:
    account = json.loads(_pem_or_file('GOOGLE_WALLET_SERVICE_ACCOUNT'))
    issuer = _setting('GOOGLE_WALLET_ISSUER_ID')
    title = event.get('title') or reg.get('event_title') or 'Event'
    class_id = f"{issuer}.{_wallet_id('event-' + str(event_id))}"
    ticket_class = {
        'id': class_id, 'issuerName': ORGANIZATION, 'reviewStatus': 'UNDER_REVIEW',
        'eventName': {'defaultValue': {'language': 'en-IN', 'value': title}},
    }
    if event.get('venue'):
        ticket_class['venue'] = {'name': {'defaultValue': {'language': 'en-IN', 'value': str(event['venue'])}},
                                 'address': {'defaultValue': {'language': 'en-IN', 'value': str(event['venue'])}}}
    start = _relevant_date(event)
    if start:
        ticket_class['dateTime'] = {'start': start}
    ticket = {
        'id': f"{issuer}.{_wallet_id('ticket-' + str(reg_id))}", 'classId': class_id, 'state': 'ACTIVE',
        'ticketHolderName': reg.get('lead_name') or '',
        'ticketNumber': reg.get('reg_id') or str(reg_id),
        'barcode': {'type': 'QR_CODE', 'value': qr_message, 'alternateText': reg.get('reg_id') or str(reg_id)},
    }
    return {
        'iss': account['client_email'], 'aud': 'google', 'typ': 'savetowallet',
        'iat': int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
        'origins': [origin] if origin else [],
        'payload': {'eventTicketClasses': [ticket_class], 'eventTicketObjects': [ticket]},
    }


def google_save_url(reg_id: str, reg: dict, event_id: str, event: dict, qr_message: str, origin: str = '') -> str:
    """The "Save to Google Wallet" link: a JWT signed with the service account's key."""
    import jwt
    account = json.loads(_pem_or_file('GOOGLE_WALLET_SERVICE_ACCOUNT'))
    token = jwt.encode(google_claims(reg_id, reg, event_id, event, qr_message, origin),
                       account['private_key'], algorithm='RS256')
    return GOOGLE_SAVE_URL + token
