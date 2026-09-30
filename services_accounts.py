"""
services_accounts.py — who a public registration belongs to (BLK-02).

Registration, waitlist and payment completion never log anyone in:
  * a logged-in visitor always registers as their session email;
  * an email that already has an account must log in first;
  * a new email gets an unverified account with no usable password, plus a
    one-time set-password link by email. Following the link sets the password
    and logs in; the link stops working once the password changes.
"""
import datetime
import hashlib
import logging
import secrets
from typing import Optional, Tuple
from urllib.parse import quote

from flask import current_app, request, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import generate_password_hash

logger = logging.getLogger(__name__)

SET_PASSWORD_SALT = 'sapthaevent-set-password'
SET_PASSWORD_MAX_AGE = 3 * 24 * 3600  # 3 days


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=SET_PASSWORD_SALT)


def _fingerprint(password_hash: str) -> str:
    # Binds the token to the current password hash, so it works only once.
    return hashlib.sha256((password_hash or '').encode()).hexdigest()[:16]


def resolve_registrant(db, form_email: str, event_id: str) -> Tuple[str, Optional[str]]:
    """Return (email, login_redirect).

    login_redirect is set when an anonymous visitor typed the email of an
    existing account: they must log in first, and nothing may be created.
    """
    session_email = (session.get('user_id') or '').strip().lower()
    if session_email:
        return session_email, None
    email = (form_email or '').strip().lower()
    if email and db.collection('users').document(email).get().exists:
        return email, login_url(f'/forms/register/{event_id}')
    return email, None


def login_url(next_path: str) -> str:
    return f"/login?next={quote(next_path, safe='/')}"


def create_unverified_account(db, email: str, name: str, phone: str = '') -> None:
    """Create a Student account nobody can log in to until the email link is used."""
    db.collection('users').document(email).set({
        'email':                email,
        'name':                 name,
        'role':                 'Student',
        'category':             'General',
        'phone':                phone,
        'password':             generate_password_hash(secrets.token_urlsafe(32), method='pbkdf2:sha256'),
        'created_at':           datetime.datetime.now().strftime('%Y-%m-%d'),
        'needs_password_reset': True,
        'email_verified':       False,
    })


def make_set_password_token(email: str, password_hash: str) -> str:
    return _serializer().dumps({'e': email, 'p': _fingerprint(password_hash)})


def load_set_password_token(token: str, db) -> Tuple[Optional[str], Optional[dict], str]:
    """Return (email, user, error). error is '' when the token is usable."""
    try:
        data = _serializer().loads(token, max_age=SET_PASSWORD_MAX_AGE)
    except SignatureExpired:
        return None, None, 'expired'
    except BadSignature:
        return None, None, 'invalid'
    email = (data or {}).get('e', '')
    doc = db.collection('users').document(email).get() if email else None
    if not doc or not doc.exists:
        return None, None, 'invalid'
    user = doc.to_dict() or {}
    if not secrets.compare_digest(_fingerprint(user.get('password', '')), str(data.get('p', ''))):
        return None, None, 'used'
    return email, user, ''


def send_set_password_link(db, email: str, name: str) -> bool:
    """Email a one-time set-password link for a newly created account."""
    from utils_email import send_set_password_email
    doc = db.collection('users').document(email).get()
    if not doc.exists:
        return False
    token = make_set_password_token(email, (doc.to_dict() or {}).get('password', ''))
    url = f"{request.host_url.rstrip('/')}/set_password/{token}"
    try:
        return bool(send_set_password_email(email, name, url))
    except Exception as exc:  # never fail a registration because mail is down
        logger.warning("Set-password email to %s failed: %s", email, exc)
        return False


def is_safe_next(target: str) -> bool:
    """Only same-site relative paths may be used as a post-login redirect."""
    return bool(target) and target.startswith('/') and not target.startswith('//') and '\\' not in target
