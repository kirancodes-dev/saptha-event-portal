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
SET_PASSWORD_MAX_AGE = 48 * 3600  # 48 hours (UPG-152)
RESET_SALT = 'sapthaevent-password-reset'
RESET_MAX_AGE = 15 * 60  # 15 minutes (UPG-152)

# An account made by an event registration records when (UPG-152): its owner
# may ask for PARTICIPANT_RESET_LIMIT reset emails in the first
# PARTICIPANT_RESET_WINDOW_HOURS, and is sent to the organizer after that.
REGISTERED_AT = 'registration_account_at'
ORGANIZER_MESSAGE = ("We could not complete your password reset. "
                     "Please contact the hackathon organizer for assistance.")
REGISTRATION_EMAIL_NOT_SENT = ("You're registered, but we could not send your password-setup email. "
                               "Please contact the hackathon organizer for assistance.")
CANCEL_SALT = 'sapthaevent-cancel-registration'
CANCEL_MAX_AGE = 90 * 24 * 3600  # 90 days


def _serializer(salt: str = SET_PASSWORD_SALT) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=salt)


def _fingerprint(password_hash: str) -> str:
    # Binds the token to the current password hash, so it works only once.
    return hashlib.sha256((password_hash or '').encode()).hexdigest()[:16]


def resolve_registrant(db, form_email: str, by_organiser: bool = False) -> Tuple[str, bool]:
    """Return (email, without_login).

    without_login is True when an anonymous visitor typed the email of an
    existing account: they're registered under it without logging in, no
    account is created or changed, and the account is emailed a link to
    cancel the registration (UPG-97). `by_organiser`: the SPOC adds a team
    by hand, so the email typed is the lead's, never the SPOC's (UPG-244).
    """
    session_email = '' if by_organiser else (session.get('user_id') or '').strip().lower()
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
                              role: str = 'Student', from_registration: bool = False, **fields) -> bool:
    """Create an account nobody can log in to until the emailed set-password
    link is used: for registrations (BLK-02), and for walk-ins and staff that
    someone else creates (UPG-33). Its random password is never shown.
    `from_registration`: an event registration made it, so its owner's own
    password resets are limited (UPG-152).
    False when another request created the same account a moment earlier (two
    tabs, UPG-115): the database's unique email refused this one."""
    if from_registration:
        fields[REGISTERED_AT] = _utcnow().isoformat()
    try:
        _write_unverified(db, email, name, phone, role, fields)
    except Exception as exc:
        if 'users' in str(getattr(exc, 'orig', exc)) and ('UNIQUE' in str(exc) or 'unique' in str(exc).lower()):
            return False
        raise
    return True


def _write_unverified(db, email, name, phone, role, fields):
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


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _when(value) -> Optional[datetime.datetime]:
    try:
        moment = datetime.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=datetime.timezone.utc)


def email_login_link(db, email: str, name: str = '', kind: str = 'set_password', reason: str = '',
                     registration: Optional[dict] = None, by: str = '', send=None) -> str:
    """Email a one-time link: 'set_password' (48 hours) or 'reset' (15 minutes).

    Returns 'sent', 'limit' (today's email limit is reached, so nothing was
    sent), 'failed' or 'missing' (no such account). The outcome, the time and
    the link's expiry are kept on the account as `login_link` and written to
    the audit log for organizers; the token never is (UPG-152). `send` replaces
    the reset email's sender (routes_auth passes its own)."""
    import services_email_quota as quota
    from utils import log_action
    from utils_email import _base_url, send_password_reset_email, send_set_password_email
    ref = db.collection('users').document(email)
    doc = ref.get()
    if not doc.exists:
        return 'missing'
    user = doc.to_dict() or {}
    now = _utcnow()
    max_age = RESET_MAX_AGE if kind == 'reset' else SET_PASSWORD_MAX_AGE
    if not quota.available():
        status = 'limit'
    else:
        if kind == 'reset':
            token = make_reset_token(email, user.get('password', ''))
            url = f"{_base_url()}/reset_token/{token}"  # BASE_URL, never the request's host (BLK-16)
        else:
            token = make_set_password_token(email, user.get('password', ''))
            url = f"{_base_url()}/set_password/{token}"
        try:
            if kind == 'reset':
                ok = (send or send_password_reset_email)(email, name or user.get('name', ''), url)
            else:
                ok = send_set_password_email(email, name or user.get('name', ''), url, reason=reason,
                                             registration=registration)
        except Exception as exc:  # never fail a registration because mail is down
            logger.warning("%s email to %s failed: %s", kind, email, exc)
            ok = False
        status = 'sent' if ok else ('limit' if not quota.available() else 'failed')
    record = {'kind': kind, 'status': status, 'at': now.isoformat()}
    if status == 'sent':
        record['expires_at'] = (now + datetime.timedelta(seconds=max_age)).isoformat()
    if by:
        record['by'] = by
    try:
        ref.update({'login_link': record})
    except Exception as exc:
        logger.warning("Could not record the %s link status for %s: %s", kind, email, exc)
    log_action(db, "LOGIN_LINK_EMAIL",
               f"{kind} link for {email}: {status}"
               + (f", expires {record['expires_at']}" if 'expires_at' in record else '')
               + (f", sent by {by}" if by else ''))
    return status


def send_set_password_link(db, email: str, name: str, reason: str = '',
                           registration: Optional[dict] = None) -> bool:
    """Email a one-time set-password link for a newly created account.
    `reason` completes "A SapthaEvent account was created for this email ...";
    `registration` makes it the registration's only email (UPG-152)."""
    return email_login_link(db, email, name, 'set_password', reason, registration) == 'sent'


PARTICIPANT_ROLES = ('Student', 'Participant')


def login_status(user: Optional[dict]) -> dict:
    """What an organizer sees about a registrant's login email (UPG-152):
    {'label', 'tone', 'can_send'}. Never the link itself."""
    if not user:
        return {'label': 'No account', 'tone': 'secondary', 'can_send': False}
    role = str(getattr(user.get('role'), 'value', user.get('role')) or '')
    can_send = role in PARTICIPANT_ROLES and user.get('is_active') is not False
    link = user.get('login_link') or {}
    last = user.get('reset_last') or {}
    refused = str(last.get('status') or '')
    later = str(link.get('at') or '') > str(last.get('at') or '')   # a link sent after the refusal wins
    label, tone = 'Password set', 'success'
    if refused.startswith('refused_') and not later:
        label, tone = ('Reset refused: already used' if refused == 'refused_used'
                       else 'Reset refused: 48 hours over'), 'warning'
    elif link.get('status') == 'limit':
        label, tone = 'Email not sent: daily limit', 'danger'
    elif link.get('status') == 'failed':
        label, tone = 'Email failed', 'danger'
    elif user.get('needs_password_reset'):
        expires = _when(link.get('expires_at'))
        if link.get('status') == 'sent' and expires and expires > _utcnow():
            label, tone = f"Link sent, expires {expires.strftime('%d %b %H:%M')} UTC", 'info'
        elif link.get('status') == 'sent':
            label, tone = 'Link expired, password not set', 'warning'
        else:
            label, tone = 'Password not set', 'warning'
    return {'label': label, 'tone': tone, 'can_send': can_send}


# ── Self-service password resets for registration accounts (UPG-152) ────────

def _reset_settings() -> Tuple[int, int]:
    cfg = current_app.config
    return (int(cfg.get('PARTICIPANT_RESET_WINDOW_HOURS', 48)), int(cfg.get('PARTICIPANT_RESET_LIMIT', 0)))


def reset_refusal(user: dict) -> str:
    """Why this account's owner may not email themselves a reset link: 'used'
    (they already had their PARTICIPANT_RESET_LIMIT), 'window' (more than
    PARTICIPANT_RESET_WINDOW_HOURS since the registration made it), or ''.
    Only accounts made by a registration are limited; staff and older
    accounts keep the usual reset. With PARTICIPANT_RESET_LIMIT 0, the
    default since UPG-260, nobody is limited: an account that exists always
    gets its link (the request throttle and the daily email limit still apply)."""
    started = _when((user or {}).get(REGISTERED_AT))
    if started is None:
        return ''
    hours, allowed = _reset_settings()
    if allowed <= 0:
        return ''
    if int(user.get('reset_requests') or 0) >= allowed:
        return 'used'
    if _utcnow() > started + datetime.timedelta(hours=hours):
        return 'window'
    return ''


def note_reset_request(db, email: str, user: dict, status: str) -> None:
    """Keep the outcome of a reset request on the account: a sent link uses
    one of a registration account's requests (UPG-152)."""
    updates: dict = {'reset_last': {'status': status, 'at': _utcnow().isoformat()}}
    if status == 'sent' and (user or {}).get(REGISTERED_AT):
        updates['reset_requests'] = int(user.get('reset_requests') or 0) + 1
    try:
        db.collection('users').document(email).update(updates)
    except Exception as exc:
        logger.warning("Could not record a reset request for %s: %s", email, exc)


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
