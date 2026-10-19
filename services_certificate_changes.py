"""
services_certificate_changes.py — correcting and revoking certificates (UPG-127).

Corrections: the certificate's own person asks for their name to be
corrected (one request open per certificate, `certificate_corrections/<id>`);
whoever may issue the event's certificates approves or rejects it. Approving
makes a new version with the same number and the new name: the old version
stops being current (status "superseded"), the new one is drawn, stored with
its SHA-256 and emailed. A rejected request changes nothing.

Revocation: a reason is required; the certificate stays current with status
"revoked", and the verification page shows it revoked with the date.

`check_file` tells a verifier whether a PDF they hold is the current version
of its number, a replaced one, or not one of ours. Every issue (UPG-124),
correction and revocation is audit-logged.
"""
import datetime
import hashlib
import json
import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

COLLECTION = 'certificate_corrections'


class ChangeError(ValueError):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _audit(db, action: str, details: str) -> None:
    from utils import log_action
    log_action(db, action, details)


# ── Corrections ─────────────────────────────────────────────────────────────

def pending_for(db, number: str) -> Optional[dict]:
    for doc in db.collection(COLLECTION).where('number', '==', number).stream():
        row = doc.to_dict() or {}
        if row.get('status') == 'pending':
            return dict(row, id=doc.id)
    return None


def for_event(db, event_id: str, status: Optional[str] = 'pending') -> list:
    rows = [dict(d.to_dict() or {}, id=d.id) for d in db.collection(COLLECTION).where('event_id', '==', event_id).stream()]
    return sorted((r for r in rows if status is None or r.get('status') == status),
                  key=lambda r: r.get('created_at') or '')


def request_correction(db, number: str, requester: str, new_name: str, reason: str = '') -> dict:
    """The certificate's own person asks for a corrected name."""
    import services_certificates as certs
    cert = certs.by_number(number)
    requester = (requester or '').strip().lower()
    if not cert or (cert.get('email') or '').lower() != requester or not requester:
        raise ChangeError("Only the person a certificate was issued to can ask for a correction.")
    if cert['status'] != 'valid':
        raise ChangeError("This certificate was revoked and can't be corrected.")
    new_name = ' '.join(str(new_name or '').split())[:300]
    if not new_name or new_name == cert['name']:
        raise ChangeError("Give the name as it should appear on the certificate.")
    if pending_for(db, cert['number']):
        raise ChangeError("A correction for this certificate is already waiting for the organiser.")
    request_id = uuid.uuid4().hex
    row = {'number': cert['number'], 'cert_id': cert['id'], 'event_id': cert['event_id'], 'requested_by': requester,
           'old_name': cert['name'], 'new_name': new_name, 'reason': str(reason or '').strip()[:500],
           'status': 'pending', 'created_at': _now().isoformat()}
    db.collection(COLLECTION).document(request_id).set(row)
    _audit(db, "CERT_CORRECTION_REQUESTED", f"{requester}: {cert['number']} from '{cert['name']}' to '{new_name}'")
    return dict(row, id=request_id)


def _get_request(db, event_id: str, request_id: str) -> dict:
    doc = db.collection(COLLECTION).document(request_id).get()
    row = (doc.to_dict() or {}) if doc.exists else {}
    if not row or row.get('event_id') != event_id:
        raise ChangeError("No such correction request.")
    if row.get('status') != 'pending':
        raise ChangeError("That request was already decided.")
    return dict(row, id=request_id)


def reject(db, event_id: str, request_id: str, actor: str, note: str = '') -> None:
    row = _get_request(db, event_id, request_id)
    db.collection(COLLECTION).document(request_id).update({
        'status': 'rejected', 'decided_by': actor, 'decided_at': _now().isoformat(), 'note': str(note or '')[:500]})
    _audit(db, "CERT_CORRECTION_REJECTED", f"{actor}: {row['number']} stays '{row['old_name']}'")


def approve(db, event_id: str, request_id: str, actor: str) -> dict:
    """A new version of the certificate with the corrected name."""
    row = _get_request(db, event_id, request_id)
    cert = new_version(row['number'], actor, name=row['new_name'])
    db.collection(COLLECTION).document(request_id).update({
        'status': 'approved', 'decided_by': actor, 'decided_at': _now().isoformat(), 'version': cert['version']})
    _audit(db, "CERT_CORRECTED", f"{actor}: {cert['number']} version {cert['version']}, "
                                 f"'{row['old_name']}' to '{row['new_name']}' (event {event_id})")
    return cert


def new_version(number: str, actor: str, name: str) -> dict:
    """Replace the current version of `number` by a new one with this name:
    the same number, the next version, drawn, stored and emailed."""
    import services_certificates as certs
    from sqlalchemy import update as sql_update
    from models_pg import Certificate
    old = certs.by_number(number)
    if not old or old['status'] != 'valid':
        raise ChangeError("Only a valid, current certificate can be corrected.")
    with certs._session() as s, s.begin():
        done = s.execute(sql_update(Certificate)
                         .where(Certificate.id == uuid.UUID(old['id']), Certificate.is_current.is_(True))
                         .values(is_current=False, status='superseded')).rowcount
        if done != 1:
            raise ChangeError("The certificate changed meanwhile; try again.")
        row = Certificate(number=old['number'], version=old['version'] + 1, is_current=True, status='valid',
                          event_id=old['event_id'], person_key=old['person_key'], recipient_email=old['email'],
                          recipient_name=name[:300], reg_id=old['reg_id'], cert_type=old['cert_type'],
                          position=old['position'], data_json=json.dumps(old['data'], default=str), issued_by=actor or None)
        s.add(row)
        s.flush()
        cert = certs._row_dict(row)
    event_doc = _event(cert['event_id'])
    cert = certs.store_pdf(cert, certs.render(event_doc, cert))
    certs.deliver(cert)
    return cert


def _event(event_id: str) -> dict:
    from models import db
    doc = db.collection('events').document(event_id).get()
    return (doc.to_dict() or {}) if doc.exists else {}


# ── Revocation ──────────────────────────────────────────────────────────────

def revoke(db, number: str, actor: str, reason: str) -> dict:
    import services_certificates as certs
    reason = ' '.join(str(reason or '').split())[:500]
    if not reason:
        raise ChangeError("Give a reason for revoking the certificate.")
    cert = certs.by_number(number)
    if not cert:
        raise ChangeError("No such certificate.")
    if cert['status'] == 'revoked':
        raise ChangeError("That certificate is already revoked.")
    certs.update(cert['id'], status='revoked', revoked_at=_now(), revoked_by=actor, revoked_reason=reason)
    _audit(db, "CERT_REVOKED", f"{actor}: {cert['number']} ({cert['name']}, {cert['cert_type']}, "
                               f"event {cert['event_id']}): {reason}")
    return certs.by_number(number)


# ── Checking a file ─────────────────────────────────────────────────────────

def check_file(number: str, data: bytes) -> dict:
    """Which version of `number` this PDF is: {'state': 'current' | 'replaced' |
    'revoked' | 'unknown', 'version': n}."""
    import services_certificates as certs
    digest = hashlib.sha256(data or b'').hexdigest()
    match = next((c for c in certs.versions(str(number).strip().upper()) if c.get('pdf_sha256') == digest), None)
    if not match:
        return {'state': 'unknown', 'version': None}
    if match['status'] == 'revoked':
        return {'state': 'revoked', 'version': match['version']}
    return {'state': 'current' if match['is_current'] else 'replaced', 'version': match['version']}
