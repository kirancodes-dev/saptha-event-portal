"""
services_seat_email.py — the one "you're in" email after a waitlist promotion
(UPG-240).

Whether a seat was freed (a cancelled or deleted team; the first in line moves
up on their own) or the SPOC accepted them (UPG-235), the person who joined
gets ONE email: registered (or a seat held until they pay, with the pay link),
the event's details, and — when their account has no password yet, because
the set-password link from when they joined has run out or was never used — a
fresh set-password link in the same email. It is a registration email, so a
portal-mode hackathon sends it too (UPG-237).

If something is still left to do (a password to set, a fee to pay), one
reminder goes 24 hours later from the hourly `reminders` job, and never more.
The reminders due are kept in `seat_reminders`, one per registration.
"""
import datetime
import logging

logger = logging.getLogger(__name__)

REMINDER_AFTER = datetime.timedelta(hours=24)
REMINDERS = 'seat_reminders'


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _user(db, email):
    doc = db.collection('users').document(email).get() if email else None
    return (doc.to_dict() or {}) if doc is not None and doc.exists else None


def needs_password(user) -> bool:
    """An account made by a registration or the waitlist, whose owner never
    chose a password."""
    return bool(user and user.get('needs_password_reset'))


def _paying(reg: dict) -> bool:
    return (str(reg.get('status') or '').strip().lower() == 'pending_payment'
            and str(reg.get('payment_status') or '').strip().lower() not in ('paid', 'completed'))


def _password_part(db, email: str, user: dict, by: str = '') -> tuple:
    """(text, record) — the set-password lines for the email, and what's kept
    on the account once it's sent (as services_accounts.email_login_link
    keeps it; never the link itself)."""
    from services_accounts import SET_PASSWORD_MAX_AGE, make_set_password_token
    from utils_email import _base_url
    url = f"{_base_url()}/set_password/{make_set_password_token(email, user.get('password', ''))}"
    hours = SET_PASSWORD_MAX_AGE // 3600
    text = ("\nYour login: you haven't set a password yet. Choose one here (the link works once, "
            f"for {hours} hours), then log in with this email and that password:\n{url}\n")
    now = _now()
    record = {'kind': 'set_password', 'status': 'sent', 'at': now.isoformat(),
              'expires_at': (now + datetime.timedelta(seconds=SET_PASSWORD_MAX_AGE)).isoformat()}
    if by:
        record['by'] = by
    return text, record


def _send(db, email: str, subject: str, text: str, event: dict, by: str = '') -> dict:
    """Send one email; with a set-password link in it when the account needs one."""
    import services_email_quota as quota
    from utils import log_action
    from utils_email import _base_url, send_email_notification
    user = _user(db, email)
    with_link = needs_password(user)
    record = None
    if with_link:
        part, record = _password_part(db, email, user, by)
        text = text + part
    else:
        text = text + f"\nLog in with this email and your password: {_base_url()}/login\n"
    from services_event_contact import support_text
    text = text + support_text(event)                 # "Questions? Write to ..." (UPG-242)
    try:
        ok = bool(send_email_notification(email, subject, text, event.get('title') or ''))
    except Exception:
        logger.warning("The seat email to %s failed", email, exc_info=True)
        ok = False
    status = 'sent' if ok else ('limit' if not quota.available() else 'failed')
    if with_link:
        if status != 'sent':
            record = {'kind': 'set_password', 'status': status, 'at': _now().isoformat()}
        try:
            db.collection('users').document(email).update({'login_link': record})
        except Exception:
            logger.warning("Could not record the set-password link for %s", email, exc_info=True)
        log_action(db, "LOGIN_LINK_EMAIL", f"set_password link for {email}: {status}"
                   + (f", expires {record['expires_at']}" if 'expires_at' in record else '')
                   + ", in the waitlist seat email")
    return {'status': status, 'password_link': with_link}


def tell(db, event: dict, promoted: dict, how: str = 'freed', by: str = '') -> dict:
    """Email the person promoted from the waitlist, once. how: 'freed' (a seat
    opened and they were first in line) or 'accepted' (the SPOC chose them).
    Returns {'status': 'sent'|'limit'|'failed'|'off', 'password_link': bool}."""
    import services_hackathon as hk
    from routes_coordinator import accepted_message
    email = str(promoted.get('user_email') or '').strip().lower()
    reg_id = promoted.get('reg_id') or ''
    if not email or not hk.email_allowed(event, 'registration'):
        return {'status': 'off', 'password_link': False}
    subject, text = accepted_message(event, promoted, how=how)
    result = _send(db, email, subject, text, event, by)
    try:
        db.collection('registrations').document(reg_id).update({'seat_email': dict(
            result, at=_now().isoformat(), how=how)})
    except Exception:
        logger.warning("Could not record the seat email on %s", reg_id, exc_info=True)
    reg = promoted.get('registration') or {}
    if result['status'] == 'sent' and (result['password_link'] or _paying(dict(reg, status=promoted.get('status')))):
        db.collection(REMINDERS).document(str(reg_id)).set({
            'reg_id': str(reg_id), 'event_id': str(event.get('id') or reg.get('event_id') or ''),
            'email': email, 'how': how, 'status': 'due',
            'due_at': (_now() + REMINDER_AFTER).isoformat()})
    return result


def send_reminders(db, now=None) -> dict:
    """The hourly job: for each seat email sent 24 hours ago whose person still
    has a password to set or a fee to pay, one reminder; then never again."""
    import services_hackathon as hk
    from routes_coordinator import seat_step
    now = now or _now()
    sent = done = 0
    for snap in db.collection(REMINDERS).where('status', '==', 'due').stream():
        item = snap.to_dict() or {}
        if str(item.get('due_at') or '') > now.isoformat():
            continue
        ref = db.collection(REMINDERS).document(snap.id)
        reg_doc = db.collection('registrations').document(str(item.get('reg_id') or '')).get()
        reg = (reg_doc.to_dict() or {}) if reg_doc.exists else {}
        ev_doc = db.collection('events').document(str(item.get('event_id') or '')).get()
        event = dict((ev_doc.to_dict() or {}) if ev_doc.exists else {}, id=str(item.get('event_id') or ''))
        email = str(item.get('email') or '')
        cancelled = str(reg.get('status') or '').strip().lower() in ('cancelled', 'refunded')
        over = str(event.get('date') or '9999')[:10] < now.date().isoformat()
        paying = _paying(reg)
        if (not reg or cancelled or over or not hk.email_allowed(event, 'registration')
                or not (paying or needs_password(_user(db, email)))):
            ref.update({'status': 'done', 'closed_at': now.isoformat()})
            done += 1
            continue
        title = event.get('title') or 'your event'
        promoted = {'reg_id': snap.id, 'status': reg.get('status'), 'registration': reg}
        step = seat_step(promoted)
        subject = f"Reminder: pay to confirm your seat for {title}" if paying else \
            f"Reminder: set your password for {title}"
        text = (f"Hi {reg.get('lead_name') or 'there'},\n\n"
                f"Yesterday we told you that you're in for {title}. "
                + ("Your seat is held until you pay.\n\n" if paying else "Your seat is confirmed.\n\n")
                + step + f"\nRegistration ID: {snap.id}\n")
        result = _send(db, email, subject, text, event)
        ref.update({'status': 'sent' if result['status'] == 'sent' else 'failed', 'sent_at': now.isoformat()})
        sent += result['status'] == 'sent'
    return {'sent': sent, 'closed': done}
