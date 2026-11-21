"""
services_activity.py — the audit log as people read it (UPG-297 (a)).

The log stores codes (`LOGIN_SUCCESS`) and UTC times; the Super Admin's
dashboard shows plain words ("Signed in") and the time in India
("15 Nov 2026, 05:05"). The full audit log page keeps every entry.
"""
import datetime

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Signing in and out are most of the log; the dashboard's short list leaves
# them out (the audit log page still has them).
ROUTINE = frozenset({'LOGIN_SUCCESS', 'LOGOUT', 'LOGIN_LINK_EMAIL'})

_WORDS = {
    'LOGIN_SUCCESS': 'Signed in',
    'LOGOUT': 'Signed out',
    'LOGIN_FAILED': 'Sign-in failed',
    'LOGIN_THROTTLED': 'Sign-in paused after too many tries',
    'LOGIN_BLOCKED_INACTIVE': 'Sign-in refused: account turned off',
    'LOGIN_BLOCKED_LEGACY_HASH': 'Sign-in refused: password must be reset',
    'USER_REGISTERED': 'New account',
    'EVENT_CREATED': 'Event created',
    'EVENT_EDITED': 'Event edited',
    'EVENT_UPDATED': 'Event edited',
    'EVENT_PUBLISHED': 'Event published',
    'EVENT_DELETED': 'Event deleted',
    'EVENT_CLONED': 'Event copied',
    'CHECKIN': 'Checked in',
    'CERT_ISSUED': 'Certificate issued',
    'CERT_ISSUED_BY_HAND': 'Certificate issued by hand',
    'BULK_CERTS': 'Certificates issued',
    'RESULTS_PUBLISHED': 'Results published',
    'RESULTS_REPUBLISHED': 'Results published again',
    'PAYMENT_REFUNDED': 'Payment refunded',
    'PASSWORD_RESET': 'Password reset',
    'PASSWORD_CHANGED': 'Password changed',
    'RESET_LINK_SENT': 'Password reset link sent',
    'SPOC_APPOINTED': 'SPOC appointed',
    'ROLE_ASSIGNED': 'Role given',
    'ROLE_REVOKED': 'Role taken away',
    'ADMIN_USER_ADDED': 'User added',
    'ADMIN_USER_UPDATED': 'User edited',
    'ADMIN_USER_ACTIVE': 'User turned on or off',
    'USER_DELETED': 'User deleted',
    'WALKIN_REGISTERED': 'Walk-in registered',
}

# Short forms spelled out in the fallback; names that stay in capitals.
_EXPAND = {'CERT': 'certificate', 'CERTS': 'certificates', 'REQ': 'request', 'REG': 'registration',
           'ADMIN': 'admin', 'WALKIN': 'walk-in', 'CHECKIN': 'check-in'}
_KEEP = {'AI', 'NAAC', 'SPOC', 'USN', 'QR', 'PDF', 'CSV'}


def action_text(code) -> str:
    """'LOGIN_SUCCESS' is 'Signed in'; a code without its own words reads as a
    sentence ('ROOMS_ALLOCATED' is 'Rooms allocated')."""
    code = str(code or '').strip()
    if not code:
        return 'Action'
    if code in _WORDS:
        return _WORDS[code]
    if not code.replace('_', '').isupper():
        return code                     # already words
    words = []
    for part in filter(None, code.split('_')):
        words.append(part if part in _KEEP else _EXPAND.get(part, part.lower()))
    text = ' '.join(words)
    return text[:1].upper() + text[1:]


def when_text(value) -> str:
    """A stored time (UTC, a datetime or ISO text) as the time in India:
    '15 Nov 2026, 05:05'. Anything else comes back as text."""
    ts = value
    if isinstance(ts, str):
        try:
            ts = datetime.datetime.fromisoformat(ts.strip().replace('Z', '+00:00'))
        except ValueError:
            return value
    if not isinstance(ts, datetime.datetime):
        return str(value or '')
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    ts = ts.astimezone(_IST)
    return f"{ts.day} {ts.strftime('%b %Y, %H:%M')}"


def dashboard_feed(entries, limit=15):
    """The dashboard's short list: newest first, without signing in and out."""
    return [e for e in entries if (e.get('action') or '') not in ROUTINE][:limit]
