"""
services_team_confirm.py — team members confirm their email (UPG-207).

The lead types each member's name and email on the registration form. After
the team registers (after paying, for a paid event) each member the lead
listed gets one email with a 48-hour link: a member without an account
confirms by choosing a password (an unverified account is made for them, as
for a lead, BLK-02), a member who already has one confirms by signing in.
Confirming marks the member `confirmed_at`; they then see their own
certificate in "My certificates" (matched by email, UPG-122).

What is kept on the member, in the registration's `members` list:
  confirm_nonce    the current link's nonce; a new send or an email correction
                   replaces it, so older links stop working
  confirm_email    the last send: 'sent', 'limit' (held back by the daily
                   email limit, UPG-152) or 'failed'
  confirm_sent_at  the time of the last send
  confirm_resends  the times of the lead's resends (3 in 24 hours)
  confirmed_at     when the member confirmed; 'confirmed_by' says how
                   ('link', 'sign-in' or 'invite' for the invite code, UPG-08)

Per event, `member_confirm` (on unless set False) switches it; off, members
get nothing, as before. The email kind `member_confirm` goes out in a
portal-mode hackathon too (services_hackathon.PORTAL_MODE_EMAILS).
"""
import datetime
import logging
import re
import secrets
from typing import Optional, Tuple

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

SALT = 'sapthaevent-team-confirm'
MAX_AGE = 48 * 3600                 # as the set-password link (UPG-152)
RESEND_LIMIT = 3
RESEND_WINDOW = datetime.timedelta(hours=24)
LEAD_ROLES = ('lead', 'team leader')
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class ConfirmError(ValueError):
    pass


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _when(value) -> Optional[datetime.datetime]:
    try:
        moment = datetime.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=datetime.timezone.utc)


def _email(member) -> str:
    return str((member or {}).get('email') or '').strip().lower()


# ── Who is asked ────────────────────────────────────────────────────────────

def enabled(event: dict) -> bool:
    """On for a team event unless the organiser switched it off."""
    from routes_forms import team_limits
    return (event or {}).get('member_confirm') is not False and team_limits(event or {})[1] > 1


def is_lead(reg: dict, member: dict) -> bool:
    return (str(member.get('role') or '').strip().lower() in LEAD_ROLES
            or _email(member) == str(reg.get('lead_email') or '').strip().lower())


def others(reg: dict) -> list:
    """The members the lead listed or who joined: everyone but the lead, with an email."""
    return [m for m in reg.get('members') or []
            if isinstance(m, dict) and _email(m) and not is_lead(reg, m)]


def active(reg: dict) -> bool:
    """A registration whose members are asked: not cancelled, waitlisted or unpaid."""
    return str(reg.get('status') or '').strip().lower() not in (
        'cancelled', 'refunded', 'waitlisted', 'pending_payment', 'pending payment')


def status(member: dict) -> dict:
    """What the lead and the organiser see: {'key', 'label', 'tone'}."""
    if member.get('confirmed_at'):
        return {'key': 'confirmed', 'label': 'Confirmed', 'tone': 'success'}
    sent = member.get('confirm_email')
    if sent == 'limit':
        return {'key': 'held', 'label': 'Waiting: email held back (daily limit)', 'tone': 'danger'}
    if sent == 'failed':
        return {'key': 'failed', 'label': 'Waiting: email failed', 'tone': 'danger'}
    if sent == 'sent':
        return {'key': 'waiting', 'label': 'Waiting', 'tone': 'warning'}
    return {'key': 'not_sent', 'label': 'Waiting: no link sent', 'tone': 'neutral'}


def resends_left(member: dict) -> int:
    since = _now() - RESEND_WINDOW
    recent = [t for t in member.get('confirm_resends') or [] if (_when(t) or since) > since]
    return max(0, RESEND_LIMIT - len(recent))


# ── The link ────────────────────────────────────────────────────────────────

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=SALT)


def make_token(reg_id: str, email: str, nonce: str) -> str:
    return _serializer().dumps({'r': str(reg_id), 'e': email.strip().lower(), 'n': nonce})


def load_token(db, token: str) -> Tuple[Optional[str], Optional[dict], Optional[dict], str]:
    """(reg_id, registration, member, error); error is 'expired', 'invalid',
    'replaced' (a newer link was sent, or the email was corrected) or ''."""
    try:
        data = _serializer().loads(token, max_age=MAX_AGE)
    except SignatureExpired:
        return None, None, None, 'expired'
    except BadSignature:
        return None, None, None, 'invalid'
    if not isinstance(data, dict) or not data.get('r') or not data.get('e') or not data.get('n'):
        return None, None, None, 'invalid'
    doc = db.collection('registrations').document(str(data['r'])).get()
    if not doc.exists:
        return None, None, None, 'invalid'
    reg = doc.to_dict() or {}
    member = next((m for m in others(reg) if _email(m) == data['e']), None)
    if member is not None and member.get('confirmed_at'):
        return str(data['r']), reg, member, ''           # the page says they already confirmed
    if member is None or not secrets.compare_digest(str(member.get('confirm_nonce') or ''), str(data['n'])):
        return None, None, None, 'replaced'
    return str(data['r']), reg, member, ''


# ── Changing one member ─────────────────────────────────────────────────────

def update_member(db, reg_id: str, email: str, change) -> Optional[dict]:
    """Apply change(member) -> dict of new values to one member, atomically on
    the SQL layer (the registration row is locked, as routes_teams._add_member),
    so a member joining at the same moment isn't lost. The member as saved, or
    None if there's no such member."""
    import json

    from db_adapter import SQLFirestoreAdapter
    email = email.strip().lower()
    if not isinstance(db, SQLFirestoreAdapter):
        doc = db.collection('registrations').document(reg_id).get()
        members = list((doc.to_dict() or {}).get('members') or [])
        for i, m in enumerate(members):
            if isinstance(m, dict) and _email(m) == email:
                members[i] = dict(m, **change(dict(m)))
                db.collection('registrations').document(reg_id).update({'members': members})
                return members[i]
        return None

    from sqlalchemy.orm import Session

    from db_adapter import CustomJSONEncoder, to_uuid
    from db_pg import get_engine
    from models_pg import Registration, TeamMember
    with Session(get_engine()) as s, s.begin():
        reg = (s.query(Registration).filter(Registration.id == to_uuid(reg_id))
               .with_for_update().one_or_none())
        if reg is None:
            return None
        for row in s.query(TeamMember).filter(TeamMember.registration_id == reg.id).all():
            try:
                member = json.loads(row.extra_json or '{}')
            except ValueError:
                member = {}
            member = dict({'name': row.name, 'email': row.email, 'usn': row.usn, 'phone': row.phone},
                          **(member if isinstance(member, dict) else {}))
            if (row.email or '').strip().lower() != email:
                continue
            member.update(change(dict(member)))
            row.email = member.get('email', row.email)
            row.extra_json = json.dumps(member, cls=CustomJSONEncoder)
            return member
    return None


# ── Sending ─────────────────────────────────────────────────────────────────

def _audit(db, action: str, details: str) -> None:
    from utils import log_action
    log_action(db, action, details)


def _ensure_account(db, email: str, name: str) -> bool:
    """True when the member must set a password (no usable one yet). An
    account is made only for an email that has none: never a second one."""
    doc = db.collection('users').document(email).get()
    if doc.exists:
        return bool((doc.to_dict() or {}).get('needs_password_reset'))
    from services_accounts import create_unverified_account
    create_unverified_account(db, email, name or 'Participant', from_registration=True)
    return True


def send(db, reg_id: str, reg: dict, event: dict, member: dict, by: str = '', resend: bool = False) -> str:
    """Email one member a new link (older links stop working). Returns 'sent',
    'limit' (today's email limit is reached: nothing sent) or 'failed'."""
    import services_email_quota as quota
    from utils_email import _base_url, _is_production, mail_provider, send_member_confirm_email
    email = _email(member)
    nonce = secrets.token_urlsafe(12)
    needs_password = _ensure_account(db, email, member.get('name') or '')
    if not quota.available():
        outcome = 'limit'
    else:
        url = f"{_base_url()}/teams/confirm/{make_token(reg_id, email, nonce)}"
        try:
            ok = send_member_confirm_email(
                email, member.get('name') or 'Participant', lead=reg.get('lead_name') or 'Your team lead',
                team=reg.get('team_name') or '', event_title=event.get('title') or '', url=url,
                needs_password=needs_password)
        except Exception as exc:   # never fail a registration because mail is down
            logger.warning("Member confirmation email to %s failed: %s", email, exc)
            ok = False
        outcome = 'sent' if ok else ('limit' if not quota.available() else 'failed')
    # The link is live once it reached the member; in development without a
    # mail provider it's in the log instead (utils_email._log_link_without_mail)
    live = outcome == 'sent' or (outcome == 'failed' and not mail_provider() and not _is_production())
    now = _now().isoformat()

    def change(m):
        values = {'confirm_email': outcome, 'confirm_sent_at': now}
        if live:
            values['confirm_nonce'] = nonce
        if resend:
            values['confirm_resends'] = list(m.get('confirm_resends') or []) + [now]
        return values
    update_member(db, reg_id, email, change)
    _audit(db, "TEAM_CONFIRM_EMAIL", f"confirmation link for {email} in {reg_id}: {outcome}"
           + (f" (resent by {by})" if resend and by else (f", sent by {by}" if by else '')))
    return outcome


def after_registration(db, reg_id: str, reg: dict, event: dict) -> dict:
    """One link to each member the lead listed, when the event asks for it.
    {email: outcome}."""
    if not enabled(event):
        return {}
    import services_hackathon
    if not services_hackathon.email_allowed(event, 'member_confirm'):
        return {}
    out = {}
    for member in others(reg):
        if member.get('confirmed_at') or member.get('confirm_email') == 'sent':
            continue
        try:
            out[_email(member)] = send(db, reg_id, reg, event, member)
        except Exception as exc:   # never fail the registration: the lead or organiser can resend
            logger.exception("Member confirmation for %s in %s failed: %s", _email(member), reg_id, exc)
            out[_email(member)] = 'failed'
    return out


def resend(db, reg_id: str, reg: dict, event: dict, email: str, by: str) -> str:
    member = next((m for m in others(reg) if _email(m) == email.strip().lower()), None)
    if member is None:
        raise ConfirmError("That person isn't a member of this team.")
    if member.get('confirmed_at'):
        raise ConfirmError(f"{email} has already confirmed.")
    if not resends_left(member):
        raise ConfirmError(f"The link to {email} was already resent {RESEND_LIMIT} times in the last 24 hours. "
                           "Try again tomorrow, or check the email is right.")
    return send(db, reg_id, reg, event, member, by=by, resend=True)


def _has_certificate(event_id: str, email: str) -> bool:
    try:
        import services_certificates as certs
        return any((c.get('email') or '').lower() == email for c in certs.for_event(event_id))
    except Exception:
        logger.exception("Could not check certificates for %s", email)
        return True     # can't tell: don't let the email move away from a certificate


def correct_email(db, reg_id: str, reg: dict, event: dict, old: str, new: str, by: str) -> str:
    """Replace a waiting member's email and send the new address a link; the
    old link stops working. Returns the send's outcome."""
    from routes_teams import _registered_for
    old, new = old.strip().lower(), new.strip().lower()
    member = next((m for m in others(reg) if _email(m) == old), None)
    if member is None:
        raise ConfirmError("That person isn't a member of this team.")
    if member.get('confirmed_at'):
        raise ConfirmError(f"{old} has already confirmed, so the email can't be changed here.")
    if _has_certificate(str(reg.get('event_id') or ''), old):
        raise ConfirmError(f"A certificate has already been issued to {old}, so the email can't be changed "
                           "from the team page. Ask the event's organiser to correct the certificate.")
    if not _EMAIL.match(new) or len(new) > 254:
        raise ConfirmError("Enter a valid email address.")
    if new == old:
        raise ConfirmError("That's the email the member already has.")
    if _registered_for(str(reg.get('event_id') or ''), new):
        raise ConfirmError(f"{new} is already registered for this event.")
    saved = update_member(db, reg_id, old, lambda m: {
        'email': new, 'confirm_nonce': '', 'confirm_email': '', 'confirm_resends': [],
        'email_corrected_from': old})
    if saved is None:
        raise ConfirmError("That person isn't a member of this team.")
    _audit(db, "TEAM_MEMBER_EMAIL_CORRECTED", f"{by} changed a member's email in {reg_id} from {old} to {new}")
    return send(db, reg_id, reg, event, saved, by=by)


def confirm(db, reg_id: str, email: str, how: str) -> None:
    now = _now().isoformat()
    update_member(db, reg_id, email, lambda m: {'confirmed_at': m.get('confirmed_at') or now,
                                                'confirmed_by': m.get('confirmed_by') or how,
                                                'confirm_nonce': ''})
    _audit(db, "TEAM_MEMBER_CONFIRMED", f"{email} confirmed their place in {reg_id} ({how})")


def send_waiting(db, event_id: str, event: dict, by: str) -> dict:
    """The organiser's "Send confirmation links to waiting members": each
    waiting member never sent a link (or held back by the daily limit, or
    failed) gets one. A second press sends nothing to anyone already sent.
    {'sent': n, 'limit': n, 'failed': n}."""
    counts = {'sent': 0, 'limit': 0, 'failed': 0}
    if not enabled(event):
        return counts
    regs = db.collection('registrations').where('event_id', '==', event_id).stream()
    for doc in regs:
        reg = doc.to_dict() or {}
        if not active(reg):
            continue
        for member in others(reg):
            if member.get('confirmed_at') or member.get('confirm_email') == 'sent':
                continue
            counts[send(db, doc.id, reg, event, member, by=by)] += 1
    _audit(db, "TEAM_CONFIRM_BULK", f"{by} sent waiting members' links for event {event_id}: {counts}")
    return counts


def summary(reg: dict) -> list:
    """[(member, status)] for the organiser's list and export."""
    return [(m, status(m)) for m in others(reg)]
