"""
services_transfer.py — hand a ticket to someone else (UPG-161).

Off unless the event allows it (`transfers_allowed`), and only until
`transfer_cutoff_hours` (default 24) before the start. Only the registration's
lead transfers it; for a team, the new person takes the lead's place and the
team stays.

The new holder must have an account, so the checks use their own profile and
not what the sender typed: their participant type must be one the event takes
(a students-only event stays on campus), a placement drive's rules must let
them in, the ticket type must be open to them, and they mustn't pay more than
the ticket cost (a transfer is refused rather than undercharging).

The registration keeps its ID; its ticket generation goes up by one, so the
old QR, wallet pass and emailed ticket stop working at every scanner
(routes_ticket.token_is_current) and the new holder's ticket page shows the new one.
"""
import datetime as _dt
import re
from typing import Dict, Optional, Tuple

IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
NOT_TRANSFERABLE = ('cancelled', 'refunded', 'waitlisted', 'pending_payment', 'pending payment', 'rejected')
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class TransferRefused(ValueError):
    """Why the transfer can't happen, shown to the person as it is."""


def _now() -> _dt.datetime:
    return _dt.datetime.now(IST)


def event_start(event: dict) -> Optional[_dt.datetime]:
    """When the event starts, in IST."""
    raw = str(event.get('start_datetime') or '')
    if not raw:
        day = str(event.get('date') or '')[:10]
        raw = f"{day}T{(str(event.get('time') or '') or '00:00')[:5]}" if day else ''
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M'):
        try:
            return _dt.datetime.strptime(raw[:19] if fmt.endswith('%S') else raw[:16], fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def cutoff(event: dict) -> Optional[_dt.datetime]:
    start = event_start(event)
    hours = int(event.get('transfer_cutoff_hours', 24) or 0)
    return start - _dt.timedelta(hours=hours) if start else None


def open_for(event: dict, reg: dict, actor_email: str) -> Tuple[bool, str]:
    """(True, '') when this person may transfer this registration now."""
    if not event.get('transfers_allowed'):
        return False, "This event doesn't allow ticket transfers."
    if (actor_email or '').strip().lower() != (reg.get('lead_email') or '').strip().lower():
        return False, "Only the person who registered can transfer this ticket."
    status = str(reg.get('status') or '').strip().lower()
    if status in NOT_TRANSFERABLE:
        return False, "Only a confirmed registration can be transferred."
    if str(reg.get('attendance') or '').strip().lower() == 'present':
        return False, "This ticket has already been used at the entrance."
    limit = cutoff(event)
    if limit is None or _now() >= limit:
        return False, "Transfers for this event have closed."
    return True, ''


def _registered(db, event_id: str, email: str) -> bool:
    for doc in db.collection('registrations').where('event_id', '==', event_id).stream():
        reg = doc.to_dict() or {}
        if str(reg.get('status') or '').strip().lower() == 'cancelled':
            continue
        people = {(reg.get('lead_email') or '').lower()} | {(m.get('email') or '').lower()
                                                           for m in reg.get('members') or []}
        if email in people:
            return True
    return False


def check_recipient(db, event_id: str, event: dict, reg: dict, email: str) -> Dict:
    """The recipient's profile if they may take this ticket, else TransferRefused."""
    from services_participants import PLURALS, allowed_types, type_of
    from services_payments import PaymentError, registration_fee
    from services_placement import eligibility, is_placement
    import services_ticket_types as tt

    email = (email or '').strip().lower()
    if not EMAIL.match(email):
        raise TransferRefused("Enter the new holder's email address.")
    if email == (reg.get('lead_email') or '').lower():
        raise TransferRefused("That's your own email.")
    doc = db.collection('users').document(email).get()
    if not doc.exists:
        raise TransferRefused("They need a SapthaEvent account first: ask them to sign up with that email, then try again.")
    profile = doc.to_dict() or {}
    if _registered(db, event_id, email):
        raise TransferRefused("They're already registered for this event.")

    ptype = type_of(profile)
    allowed = allowed_types(event)
    if ptype not in allowed:
        raise TransferRefused('This event is for ' + ' and '.join(PLURALS[t] for t in allowed) + ' only.')
    if is_placement(event):
        ok, reason = eligibility(event, profile)
        if not ok:
            raise TransferRefused(f"They can't take this ticket: {reason}")
    ticket_id = reg.get('ticket_type_id') or ''
    ticket = tt.find(event, ticket_id) if ticket_id else None
    if ticket is not None and not tt.allowed_for(ticket, ptype):
        raise TransferRefused(f"The {ticket['name']} ticket isn't open to {PLURALS[ptype]}.")
    size = max(1, len(reg.get('members') or []))
    try:
        theirs = registration_fee(event, ptype, ticket_id, size)
        paid = registration_fee(event, type_of(reg), ticket_id, size)
    except PaymentError as exc:
        raise TransferRefused(str(exc))
    if theirs > paid:
        raise TransferRefused(f"They would pay Rs {theirs:g} for this event and this ticket cost Rs {paid:g}, "
                              "so it can't be transferred to them. They can register themselves.")
    return dict(profile, email=email, participant_type=ptype)


def transfer(db, reg_id: str, reg: dict, event: dict, recipient: Dict, actor: str) -> dict:
    """Move the registration to the recipient and replace its ticket."""
    from utils import log_action
    old_email = (reg.get('lead_email') or '').lower()
    name = recipient.get('name') or recipient['email'].split('@')[0]
    lead = {'role': 'Lead', 'name': name, 'email': recipient['email'],
            'usn': recipient.get('usn') or '', 'phone': recipient.get('phone') or ''}
    members = [lead if (m.get('email') or '').lower() == old_email or str(m.get('role') or '').lower() == 'lead'
               else m for m in reg.get('members') or []]
    if not any(m is lead for m in members):
        members.insert(0, lead)
    history = list(reg.get('transfers') or []) + [{
        'from': old_email, 'from_name': reg.get('lead_name', ''), 'to': recipient['email'],
        'at': _now().isoformat(timespec='seconds'), 'by': actor}]
    updates = {
        'lead_email': recipient['email'], 'lead_name': name,
        'lead_phone': recipient.get('phone') or '', 'phone': recipient.get('phone') or '',
        'lead_usn': recipient.get('usn') or '',
        'participant_type': recipient['participant_type'],
        'designation': recipient.get('designation') or '', 'institution': recipient.get('institution') or '',
        'members': members,
        'ticket_gen': int(reg.get('ticket_gen') or 0) + 1,
        'transfers': history,
    }
    db.collection('registrations').document(reg_id).update(updates)
    log_action(db, "TICKET_TRANSFERRED",
               f"Reg {reg_id} of event {reg.get('event_id')}: {old_email} → {recipient['email']} (by {actor})")
    return dict(reg, **updates)


def notify(reg_id: str, event: dict, old_email: str, old_name: str, new_email: str, new_name: str) -> None:
    """Tell both people; the new holder gets the ticket page link."""
    from utils_email import _base_url, send_email_notification
    title = event.get('title', 'the event')
    import services_hackathon
    if not services_hackathon.email_allowed(event, 'transfer'):   # portal notices instead (UPG-195)
        from models import db
        from routes_notifications_v2 import create_notification
        create_notification(db, user_email=old_email, notif_type='announcement',
                            title=f"Your ticket for {title} was transferred",
                            message=f"Your ticket now belongs to {new_name}. Your old QR code no longer works.")
        create_notification(db, user_email=new_email, notif_type='announcement',
                            title=f"You have a ticket for {title}",
                            message=f"{old_name} has transferred their ticket to you.", link=f"/ticket/{reg_id}")
        return
    try:
        send_email_notification(
            old_email, f"Your ticket for {title} was transferred",
            f"Hi {old_name},\n\nYour ticket for {title} now belongs to {new_name}. "
            "Your old ticket and QR code no longer work.", title)
        send_email_notification(
            new_email, f"You have a ticket for {title}",
            f"Hi {new_name},\n\n{old_name} has transferred their ticket for {title} to you.\n"
            f"Your ticket and entry QR: {_base_url()}/ticket/{reg_id}", title)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Transfer emails for %s failed", reg_id, exc_info=True)
