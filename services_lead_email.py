"""
services_lead_email.py — the event's SPOC corrects a team lead's email (UPG-256).

The lead's email is their login. A lead who mistyped it at registration never
gets the login email, so they can't get in to fix anything, their teammates'
emails included. The SPOC (after the lead asks, through the event's support
email) types the right address:

- the registration's `lead_email` (and `student_email`, where an old record
  has it) and the lead's row in `members` move to the new address;
- the ticket's generation goes up by one, so a QR sent to the wrong address
  stops working (as a transfer does, UPG-161);
- the new address gets the login: a set-password link for a new or never-used
  account, or an email saying to sign in for an account that has a password;
  and a portal notice;
- the account made for the wrong address is removed when nobody ever used it
  (no password set, not verified, a participant) and it is on no other
  registration.

Refused for a cancelled team, after check-in, once a certificate was issued
to the old address, or when the new address is already on a team at the event.
"""
import datetime
import logging
import re

logger = logging.getLogger(__name__)

_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class LeadEmailError(ValueError):
    """Why the correction can't be made, shown to the SPOC as it is."""


def _lower(value) -> str:
    return str(value or '').strip().lower()


def why_not(reg: dict, event: dict) -> str:
    from services_entry import checked_in, inactive
    if inactive(reg):
        return "This registration is cancelled, so its lead can't change."
    if checked_in(reg):
        return "The team has been checked in, so the lead's email can't change."
    return ''


def _on_another_registration(db, email: str, except_reg: str) -> bool:
    for doc in db.collection('registrations').where('lead_email', '==', email).limit(2).stream():
        if doc.id != except_reg and str((doc.to_dict() or {}).get('reg_id') or '') != except_reg:
            return True
    from routes_participant import member_registrations
    return any(doc_id != except_reg and str(data.get('reg_id') or '') != except_reg
               for doc_id, data in member_registrations(email))


def _unused_account(user: dict) -> bool:
    role = str(getattr(user.get('role'), 'value', user.get('role')) or '')
    return (bool(user) and user.get('needs_password_reset') is True and not user.get('email_verified')
            and role in ('Student', 'Participant'))


def correct(db, reg_id: str, reg: dict, event: dict, new: str, by: str) -> dict:
    """Move the registration's lead to `new`. Returns {'old', 'new', 'login'
    ('sent', 'limit', 'failed' or 'sign-in'), 'removed_account'}, or
    LeadEmailError."""
    from routes_teams import _registered_for
    from services_accounts import create_unverified_account, email_login_link
    from services_team_confirm import _has_certificate, update_members
    from utils import log_action
    old = _lower(reg.get('lead_email') or reg.get('student_email'))
    new = _lower(new)
    event_id = str(reg.get('event_id') or '')
    reason = why_not(reg, event)
    if reason:
        raise LeadEmailError(reason)
    if not _EMAIL.match(new) or len(new) > 254:
        raise LeadEmailError("Enter a valid email address.")
    if new == old:
        raise LeadEmailError("That's the email the lead already has.")
    if _registered_for(event_id, new):
        raise LeadEmailError(f"{new} is already registered for this event.")
    if old and _has_certificate(event_id, old):
        raise LeadEmailError(f"A certificate has already been issued to {old}, so the lead's email can't change. "
                             "Correct the certificate first.")

    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    history = list(reg.get('email_corrections') or []) + [{'from': old, 'to': new, 'at': now, 'by': by}]
    updates = {'lead_email': new, 'ticket_gen': int(reg.get('ticket_gen') or 0) + 1, 'email_corrections': history}
    if reg.get('student_email'):
        updates['student_email'] = new
    db.collection('registrations').document(reg_id).update(updates)
    update_members(db, reg_id, lambda m: {'email': new} if (_lower(m.get('email')) == old and old)
                   or str(m.get('role') or '').lower() == 'lead' else None, first=True)

    # The login goes to the right address
    name = reg.get('lead_name') or ''
    title = event.get('title') or 'the event'
    team = reg.get('team_name') or ''
    doc = db.collection('users').document(new).get()
    user = (doc.to_dict() or {}) if doc.exists else {}
    if not user:
        create_unverified_account(db, new, name, str(reg.get('lead_phone') or reg.get('phone') or ''),
                                  from_registration=True)
    if not user or user.get('needs_password_reset'):
        login = email_login_link(db, new, name, 'set_password',
                                 f"because the organiser of {title} corrected the email you registered with"
                                 + (f" as the lead of team {team}" if team else ''), by=by)
    else:
        from utils_email import send_email_notification
        login = 'sign-in' if send_email_notification(
            new, f"You lead {team or 'your registration'} for {title}",
            f"Hi {name or 'there'},\n\nThe organiser of {title} corrected the email you registered with to "
            f"this one. Sign in with it to see {'your team' if team else 'your registration'} and ticket.",
            title) else 'failed'
    try:
        from routes_notifications_v2 import create_notification
        create_notification(db, user_email=new, notif_type='update',
                            title=f"You lead {team or 'your registration'} for {title}",
                            message="The organiser corrected the email you registered with to this one.",
                            link=f"/teams/{reg_id}" if reg.get('team_code') else '/participant/dashboard',
                            metadata={'event_id': event_id})
    except Exception:
        logger.warning("Portal notice to %s failed", new, exc_info=True)

    # The account made for the wrong address goes, if nobody ever used it
    removed = False
    if old:
        old_doc = db.collection('users').document(old).get()
        if old_doc.exists and _unused_account(old_doc.to_dict() or {}) and \
                not _on_another_registration(db, old, reg_id):
            try:
                db.collection('users').document(old).delete()
                removed = True
            except Exception:
                logger.warning("Could not remove the unused account %s", old, exc_info=True)
    log_action(db, "LEAD_EMAIL_CORRECTED", f"{by} changed the lead of {reg_id} (event {event_id}) from {old} "
                                           f"to {new}; login: {login}" + ("; unused account removed" if removed else ''))
    return {'old': old, 'new': new, 'login': login, 'removed_account': removed}
