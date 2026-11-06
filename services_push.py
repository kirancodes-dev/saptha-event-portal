"""
services_push.py — browser push notifications (UPG-157).

One subscription per browser (its endpoint), each belonging to the user
logged in when it was made. A push copies a notice that also goes by email
or in-app; it never replaces a required email. Off, with no prompt shown,
until VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY are set.

A subscription the push service reports gone (404 or 410) is deleted.
"""
import datetime
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

ICON = '/static/app-icon.png'


def public_key() -> str:
    return (os.environ.get('VAPID_PUBLIC_KEY') or '').strip()


def configured() -> bool:
    return bool(public_key() and (os.environ.get('VAPID_PRIVATE_KEY') or '').strip())


def _session():
    from db_pg import get_session
    return get_session()


def subscribe(email: str, subscription: dict) -> bool:
    """Save this browser's subscription for the user; a browser that was
    another user's moves to this one. False for a malformed subscription."""
    from models_pg import PushSubscription
    endpoint = str((subscription or {}).get('endpoint') or '').strip()
    keys = (subscription or {}).get('keys') or {}
    p256dh, auth = str(keys.get('p256dh') or '').strip(), str(keys.get('auth') or '').strip()
    if not endpoint.startswith('https://') or not p256dh or not auth or len(endpoint) > 2000:
        return False
    email = email.strip().lower()
    with _session() as s:
        rows = s.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).all()
        if rows:
            for extra in rows[1:]:
                s.delete(extra)
            row = rows[0]
            row.user_email, row.p256dh, row.auth_key = email, p256dh[:255], auth
        else:
            s.add(PushSubscription(user_email=email, endpoint=endpoint, p256dh=p256dh[:255], auth_key=auth,
                                   created_at=datetime.datetime.now(datetime.timezone.utc)))
    return True


def unsubscribe(email: str, endpoint: str = '') -> None:
    """This browser's subscription, or (without an endpoint) all of the user's."""
    from models_pg import PushSubscription
    with _session() as s:
        q = s.query(PushSubscription).filter(PushSubscription.user_email == email.strip().lower())
        if endpoint:
            q = q.filter(PushSubscription.endpoint == endpoint)
        q.delete(synchronize_session=False)


def subscriptions(email: str) -> list:
    from models_pg import PushSubscription
    with _session() as s:
        return [{'id': str(r.id), 'endpoint': r.endpoint, 'keys': {'p256dh': r.p256dh, 'auth': r.auth_key}}
                for r in s.query(PushSubscription).filter(PushSubscription.user_email == email.strip().lower())]


def _webpush(info: dict, payload: str):
    from pywebpush import webpush  # type: ignore[import-untyped]
    return webpush(subscription_info=info, data=payload,
                   vapid_private_key=os.environ.get('VAPID_PRIVATE_KEY', '').strip(),
                   vapid_claims={'sub': os.environ.get('VAPID_EMAIL') or 'mailto:admin@snpsu.edu.in'},
                   timeout=10)


def send(email: str, title: str, body: str, url: str = '/', tag: str = '') -> int:
    """Push to each of the user's browsers; returns how many took it."""
    if not configured() or not email:
        return 0
    from models_pg import PushSubscription
    payload = json.dumps({'title': title[:120], 'body': body[:300], 'url': url or '/', 'icon': ICON,
                          'tag': tag or 'saptha-notif'})
    sent = 0
    for sub in subscriptions(email):
        try:
            _webpush({'endpoint': sub['endpoint'], 'keys': sub['keys']}, payload)
            sent += 1
        except Exception as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status in (404, 410):   # the browser unsubscribed or the subscription expired
                with _session() as s:
                    s.query(PushSubscription).filter(PushSubscription.endpoint == sub['endpoint']).delete(
                        synchronize_session=False)
            else:
                logger.warning("Push to %s failed: %s", email, exc)
    return sent


def send_once(db, email: str, key: str, title: str, body: str, url: str = '/') -> int:
    """send(), once per key and person, however often the caller runs."""
    if not configured() or not email:
        return 0
    doc_id = f"push_{key}_{email.strip().lower()}"[:250]
    ref = db.collection('notification_dedup').document(doc_id)
    if ref.get().exists:
        return 0
    sent = send(email, title, body, url, tag=key[:60])
    ref.set({'idempotency_key': doc_id, 'trigger_name': 'push', 'recipient_email': email.strip().lower(),
             'dispatched_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'channels': ['push']})
    return sent


def push_to_registrants(db, event_id: str, key: str, title: str, body: str, url: Optional[str] = None) -> int:
    """Each active registration's lead and members, once each per key."""
    if not configured():
        return 0
    from services_recipients import registration_people
    seen, sent = set(), 0
    for doc in db.collection('registrations').where('event_id', '==', str(event_id)).stream():
        reg = doc.to_dict() or {}
        if str(reg.get('status') or '').strip().lower() == 'cancelled':
            continue
        for email, _name, _phone in registration_people(reg):
            if email and email not in seen:
                seen.add(email)
                sent += send_once(db, email, f"{key}_{event_id}", title, body, url or f'/event/{event_id}')
    return sent
