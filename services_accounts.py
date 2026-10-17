"""
services_accounts.py — who a public registration belongs to (BLK-02).

Registration, waitlist and payment completion never log anyone in:
  * a logged-in visitor always registers as their session email;
  * an anonymous visitor may register an email that already has an account,
    without logging in; the account is emailed a link to cancel it (UPG-97);
  * a new email gets an unverified account with no usable password, plus a
    one-time set-password link by email. Following the link sets the password
    and logs in; the link stops working once the password changes.
"""
import datetime
import hashlib
import logging
import secrets
from typing import Optional, Tuple

from flask import current_app, session
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import generate_password_hash

logger = logging.getLogger(__name__)

SET_PASSWORD_SALT = 'sapthaevent-set-password'
SET_PASSWORD_MAX_AGE = 3 * 24 * 3600  # 3 days
RESET_SALT = 'sapthaevent-password-reset'
RESET_MAX_AGE = 3600  # 1 hour
CANCEL_SALT = 'sapthaevent-cancel-registration'
CANCEL_MAX_AGE = 90 * 24 * 3600  # 90 days


def _serializer(salt: str = SET_PASSWORD_SALT) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=salt)


def _fingerprint(password_hash: str) -> str:
    # Binds the token to the current password hash, so it works only once.
    return hashlib.sha256((password_hash or '').encode()).hexdigest()[:16]


def resolve_registrant(db, form_email: str) -> Tuple[str, bool]:
    """Return (email, without_login).

    without_login is True when an anonymous visitor typed the email of an
    existing account: they're registered under it without logging in, no
    account is created or changed, and the account is emailed a link to
    cancel the registration (UPG-97).
    """
    session_email = (session.get('user_id') or '').strip().lower()
    if session_email:
        return session_email, False
    email = (form_email or '').strip().lower()
    return email, bool(email and db.collection('users').document(email).get().exists)


def make_cancel_token(reg_id: str, email: str) -> str:
    """A link token that lets the account owner cancel a registration made
    for their email without logging in (UPG-97)."""
    return _serializer(CANCEL_SALT).dumps({'r': reg_id, 'e': (email or '').lower()})


def load_cancel_token(token: str) -> Tuple[str, str, str]:
    """Return (reg_id, email, error); error is 'expired', 'invalid' or ''."""
    try:
        data = _serializer(CANCEL_SALT).loads(token, max_age=CANCEL_MAX_AGE)
    except SignatureExpired:
        return '', '', 'expired'
    except BadSignature:
        return '', '', 'invalid'
    if not isinstance(data, dict) or not data.get('r') or not data.get('e'):
        return '', '', 'invalid'
    return str(data['r']), str(data['e']), ''


def cancel_url_for(reg: dict) -> str:
    """The emailed cancel link for a registration made without logging in,
    or '' for any other registration (UPG-97)."""
    if not reg.get('registered_without_login') or str(reg.get('status', '')).lower() == 'cancelled':
        return ''
    from utils_email import _base_url
    return f"{_base_url()}/forms/cancel/{make_cancel_token(reg.get('reg_id', ''), reg.get('lead_email', ''))}"


def create_unverified_account(db, email: str, name: str, phone: str = '',
                              role: str = 'Student', **fields) -> None:
    """Create an account nobody can log in to until the emailed set-password
    link is used: for registrations (BLK-02), and for walk-ins and staff that
    someone else creates (UPG-33). Its random password is never shown."""
    db.collection('users').document(email).set({
        'email':                email,
        'name':                 name,
        'role':                 role,
        'category':             'General',
        'phone':                phone,
        'password':             generate_password_hash(secrets.token_urlsafe(32), method='pbkdf2:sha256'),
        'created_at':           datetime.datetime.now().strftime('%Y-%m-%d'),
        'needs_password_reset': True,
        'email_verified':       False,
        **fields,
    })


def make_set_password_token(email: str, password_hash: str) -> str:
    return _serializer().dumps({'e': email, 'p': _fingerprint(password_hash)})


def load_set_password_token(token: str, db) -> Tuple[Optional[str], Optional[dict], str]:
    """Return (email, user, error). error is '' when the token is usable."""
    return _load_bound_token(token, db, SET_PASSWORD_SALT, SET_PASSWORD_MAX_AGE)


def make_reset_token(email: str, password_hash: str) -> str:
    """A password-reset link token, bound to the current password, so it works once (UPG-33)."""
    return _serializer(RESET_SALT).dumps({'e': email, 'p': _fingerprint(password_hash)})


def load_reset_token(token: str, db) -> Tuple[Optional[str], Optional[dict], str]:
    """Return (email, user, error); error is 'expired', 'invalid', 'used' or ''."""
    return _load_bound_token(token, db, RESET_SALT, RESET_MAX_AGE)


def _load_bound_token(token: str, db, salt: str, max_age: int) -> Tuple[Optional[str], Optional[dict], str]:
    try:
        data = _serializer(salt).loads(token, max_age=max_age)
    except SignatureExpired:
        return None, None, 'expired'
    except BadSignature:
        return None, None, 'invalid'
    if not isinstance(data, dict):  # a token from before UPG-33
        return None, None, 'invalid'
    email = data.get('e', '')
    doc = db.collection('users').document(email).get() if email else None
    if not doc or not doc.exists:
        return None, None, 'invalid'
    user = doc.to_dict() or {}
    if not secrets.compare_digest(_fingerprint(user.get('password', '')), str(data.get('p', ''))):
        return None, None, 'used'
    return email, user, ''


def send_set_password_link(db, email: str, name: str, reason: str = '') -> bool:
    """Email a one-time set-password link for a newly created account.
    `reason` completes "A SapthaEvent account was created for this email ..."."""
    from utils_email import _base_url, send_set_password_email
    doc = db.collection('users').document(email).get()
    if not doc.exists:
        return False
    token = make_set_password_token(email, (doc.to_dict() or {}).get('password', ''))
    url = f"{_base_url()}/set_password/{token}"  # BASE_URL, never the request's host (BLK-16)
    try:
        return bool(send_set_password_email(email, name, url, reason=reason))
    except Exception as exc:  # never fail a registration because mail is down
        logger.warning("Set-password email to %s failed: %s", email, exc)
        return False


def is_safe_next(target: str) -> bool:
    """Only same-site relative paths may be used as a post-login redirect."""
    return bool(target) and target.startswith('/') and not target.startswith('//') and '\\' not in target


# ── Personal calendar feed (BLK-04) ──────────────────────────────────────────
# Calendar apps can't send the session cookie, so the subscribe URL carries a
# signed per-user token. Bumping the user's calendar_feed_version (rotate)
# invalidates every older link.
CALENDAR_FEED_SALT = 'sapthaevent-calendar-feed'


def make_calendar_feed_token(email: str, version: int = 0) -> str:
    from itsdangerous import URLSafeSerializer
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt=CALENDAR_FEED_SALT).dumps(
        {'e': email.lower(), 'v': int(version or 0)})


def load_calendar_feed_token(token: str, db) -> Optional[str]:
    """Return the email a feed token belongs to, or None if invalid or rotated."""
    from itsdangerous import URLSafeSerializer
    try:
        data = URLSafeSerializer(current_app.config['SECRET_KEY'], salt=CALENDAR_FEED_SALT).loads(token)
    except BadSignature:
        return None
    email = (data or {}).get('e', '')
    doc = db.collection('users').document(email).get() if email else None
    if not doc or not doc.exists:
        return None
    if int((doc.to_dict() or {}).get('calendar_feed_version', 0) or 0) != int(data.get('v', -1)):
        return None
    return email
