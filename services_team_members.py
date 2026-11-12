"""
services_team_members.py — the team lead adds a member, up to the team's
limit (UPG-241).

A lead who registered with fewer people than the event allows (3 of 4, say)
adds the missing ones from the team page: name, email, USN and phone. To
replace someone, the lead removes them (UPG-08) and adds the new person. The
new member gets what the members listed at registration get: a link to
confirm and set a password when the event asks members to confirm (UPG-207),
and a portal notice.

Allowed while the team could still register: not cancelled or checked in,
the event not over (UPG-225's rule) and its registration still open. Not when
the fee is per person (a ticket type priced per person), because the team
would owe more: the organiser adds them.
"""
import datetime
import re

_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_PHONE = re.compile(r'^\+?[0-9 \-]{7,16}$')


class AddError(Exception):
    pass


def _email(member) -> str:
    return str((member or {}).get('email') or '').strip().lower()


def room_left(reg: dict, team_max: int) -> int:
    return max(0, int(team_max or 1) - len(reg.get('members') or []))


def why_not(reg: dict, event: dict) -> str:
    """'' when the lead may add a member now, else why not (shown on the page)."""
    from routes_forms import registration_closed, team_limits
    from services_registration_edit import lead_may_edit
    reason = lead_may_edit(reg, event)
    if reason:
        return reason
    _, team_max = team_limits(event)
    if team_max <= 1:
        return "This event is for individuals, so it has no teams to add to."
    if room_left(reg, team_max) <= 0:
        return f"Your team is full: {team_max} people is the most this event allows."
    if registration_closed(event):
        return "Registration for this event has closed, so the team can't grow. Ask the event's organiser."
    import services_ticket_types as tt
    ticket = tt.find(event, reg.get('ticket_type_id', '')) if tt.types_for(event) else None
    if ticket is not None and ticket.get('per') == 'person' and float(ticket.get('price') or 0) > 0:
        return ("The fee for this event is per person, so a new member changes what your team owes. "
                "Ask the event's organiser to add them.")
    return ''


def add(db, reg_id: str, reg: dict, event: dict, form, by: str) -> tuple:
    """Add the member the lead typed in. (member, how_told), or AddError."""
    from routes_forms import team_limits
    from routes_teams import _add_member, _registered_for
    reason = why_not(reg, event)
    if reason:
        raise AddError(reason)
    name = ' '.join(str(form.get('name') or '').split())[:100]
    email = str(form.get('email') or '').strip().lower()
    usn = str(form.get('usn') or '').strip().upper()[:20]
    phone = str(form.get('phone') or '').strip()[:20]
    if not name:
        raise AddError("Enter the new member's name.")
    if not _EMAIL.match(email) or len(email) > 254:
        raise AddError("Enter a valid email address for the new member.")
    if phone and not _PHONE.match(phone):
        raise AddError("Enter a valid phone number, or leave it empty.")
    if email == str(reg.get('lead_email') or '').strip().lower() or any(_email(m) == email for m in reg.get('members') or []):
        raise AddError(f"{email} is already on your team.")
    event_id = str(reg.get('event_id') or '')
    if _registered_for(event_id, email):
        raise AddError(f"{email} is already registered for this event with another team.")
    _, team_max = team_limits(event)
    member = {'role': 'Member', 'name': name, 'email': email, 'usn': usn, 'phone': phone,
              'added_by': by, 'added_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    added = _add_member(reg_id, member, team_max)      # the size is re-checked atomically (UPG-52)
    if added == 'full':
        raise AddError(f"Your team is full: {team_max} people is the most this event allows.")
    if added == 'already':
        raise AddError(f"{email} is already on your team.")
    return member, _tell(db, reg_id, event, member)


def _tell(db, reg_id: str, event: dict, member: dict) -> str:
    """The new member hears as the ones listed at registration did. Returns
    'link' (a confirm-and-set-password link was sent), 'limit', 'failed',
    'email' (a plain "you were added" email) or 'portal' (a notice only)."""
    import services_hackathon as hk
    import services_team_confirm as confirm
    doc = db.collection('registrations').document(reg_id).get()
    reg = (doc.to_dict() or {}) if doc.exists else {}
    title = event.get('title') or 'the event'
    try:
        from routes_notifications_v2 import create_notification
        create_notification(db, user_email=member['email'], notif_type='team_added',
                            title=f"You're on team {reg.get('team_name') or ''} for {title}",
                            message=f"{reg.get('lead_name') or 'Your team lead'} added you to the team.",
                            link=f"/teams/{reg_id}", metadata={'event_id': str(reg.get('event_id') or '')})
    except Exception:
        pass
    if confirm.enabled(event) and hk.email_allowed(event, 'member_confirm'):
        saved = next((m for m in confirm.others(reg) if _email(m) == member['email']), member)
        outcome = confirm.send(db, reg_id, reg, event, saved)
        return 'link' if outcome == 'sent' else outcome
    from services_recipients import notify_team_members
    if notify_team_members() and hk.email_allowed(event, 'team'):
        try:
            from utils_email import send_registration_confirmed_email
            send_registration_confirmed_email(
                member['email'], member['name'], title, event_date=event.get('date', ''),
                venue=event.get('venue', ''), added_by=reg.get('lead_name') or 'Your team lead',
                team_name=reg.get('team_name', ''))
            return 'email'
        except Exception:
            return 'failed'
    return 'portal'
