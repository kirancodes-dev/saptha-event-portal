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

After registration closes (UPG-250) the event's SPOC can open a window, for a
set time, in which registered teams change again: the lead adds and removes
members and teammates join with the invite code. New teams still can't
register. The window's end is saved on the event as `add_members_until` (an
ISO time in UTC); it closes by itself then, or when the SPOC closes it.

A member added or joining while the window is open is marked `late`, with
when and by whom (UPG-252): the SPOC's list labels them "Added during
window" and filters on them. When the window ends (the SPOC's "Close now",
or its time passing, noticed by the hourly `reminders` job or the next visit
to the SPOC's list) the SPOC who opened it gets one portal notice naming the
members added and whether each has confirmed.
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


# ── The SPOC's window after registration closes (UPG-250) ────────────────────

WINDOW = 'add_members_until'
SINCE = 'add_members_since'       # when the current window first opened (UPG-252)
DURATIONS = {'30': 30, '60': 60, '120': 120, '1440': 1440}     # minutes, as the SPOC's form offers
LONGEST = datetime.timedelta(days=7)
CLOSED_MESSAGE = "Registration for this event has closed, so the team can't grow. Ask the event's organiser."
CLOSED_REMOVE = "Registration for this event has closed, so the team can't change. Ask the event's organiser."


class WindowError(Exception):
    pass


def _now() -> datetime.datetime:
    """The clock, in UTC (tests move it)."""
    return datetime.datetime.now(datetime.timezone.utc)


def window_until(event: dict):
    """When the window closes (aware UTC), or None if none was opened."""
    from services_hackathon import parse_iso
    return parse_iso((event or {}).get(WINDOW))


def window_open(event: dict) -> bool:
    until = window_until(event)
    return bool(until) and _now() < until


def window_closes(event: dict) -> str:
    """'20 Nov 2026, 6:00 PM IST' while open, else ''."""
    from services_hackathon import show
    return show((event or {}).get(WINDOW), event) if window_open(event) else ''


def closed_for_changes(event: dict) -> bool:
    """Registration is closed and no window is open: teams stay as they are."""
    from routes_forms import registration_closed
    return registration_closed(event or {}) and not window_open(event)


def why_no_window(event: dict) -> str:
    """'' when the SPOC may open a window now, else why not."""
    from routes_forms import registration_closed, team_limits
    from services_certificates import event_ended
    status = str((event or {}).get('status') or '').strip().lower()
    if team_limits(event or {})[1] <= 1:
        return "This event is for individuals, so it has no teams to add to."
    if status in ('draft', 'pending_approval', 'published'):
        return "Registration hasn't opened yet."
    if status in ('cancelled', 'archived') or event_ended(event or {}):
        return "The event is over, so teams can't change."
    if not registration_closed(event or {}):
        return "Registration is still open, so leads can already add members."
    return ''


def teams_with_room(db, event_id: str, event: dict) -> list:
    """(reg_id, registration) of each live team with a free place."""
    from routes_forms import team_limits
    from services_entry import checked_in, inactive
    _, team_max = team_limits(event or {})
    found = []
    for doc in db.collection('registrations').where('event_id', '==', str(event_id)).stream():
        reg = doc.to_dict() or {}
        if reg.get('team_code') and not inactive(reg) and not checked_in(reg) and room_left(reg, team_max) > 0:
            found.append((str(reg.get('reg_id') or doc.id), reg))
    return found


def open_window(db, event_id: str, event: dict, length: str, until_local: str = '',
                email: bool = True, by: str = '') -> dict:
    """Open (or move the end of) the window. Every lead whose team has room
    gets a portal notice and, with `email`, an email with the closing time.
    Returns {'until': text, 'teams': n, 'emailed': n}, or WindowError."""
    import services_hackathon as hk
    reason = why_no_window(event)
    if reason:
        raise WindowError(reason)
    now = _now()
    if length in DURATIONS:
        until = now + datetime.timedelta(minutes=DURATIONS[length])
    elif length == 'until':
        until = hk.parse_local(until_local, event)
        if until is None:
            raise WindowError("Choose the date and time the window closes.")
        if until <= now:
            raise WindowError("That time has passed: choose a later one.")
    else:
        raise WindowError("Choose how long teams have.")
    if until - now > LONGEST:
        raise WindowError("A window can be open for 7 days at most.")
    until = until.replace(microsecond=0)
    changes = {WINDOW: until.isoformat(), 'add_members_opened_by': by, 'add_members_opened_at': now.isoformat()}
    if not window_open(event) or not event.get(SINCE):
        changes[SINCE] = now.isoformat()               # a new window; moving the end keeps its start
    db.collection('events').document(str(event_id)).update(changes)
    event = dict(event, **{WINDOW: until.isoformat()})
    closes = hk.show(until.isoformat(), event)
    teams = teams_with_room(db, event_id, event)
    emailed = 0
    title = event.get('title') or 'the event'
    for reg_id, reg in teams:
        lead = str(reg.get('lead_email') or '').strip().lower()
        if not lead:
            continue
        message = (f"The organiser has opened {title} for team changes until {closes}. "
                   f"Your team has room: add members from your team page, or share your invite code.")
        try:
            from routes_notifications_v2 import create_notification
            create_notification(db, user_email=lead, notif_type='team_window',
                                title=f"Add members to {reg.get('team_name') or 'your team'} until {closes}",
                                message=message, link=f"/teams/{reg_id}#add-member",
                                metadata={'event_id': str(event_id)})
        except Exception:
            pass
        if email:
            try:
                from utils_email import send_add_members_window_email
                emailed += bool(send_add_members_window_email(
                    lead, reg.get('lead_name') or '', reg.get('team_name') or '', title, closes, reg_id))
            except Exception:
                pass
    return {'until': closes, 'teams': len(teams), 'emailed': emailed}


def late_fields(event: dict) -> dict:
    """What marks a member added while the window is open (UPG-252)."""
    from routes_forms import registration_closed
    return {'late': True} if registration_closed(event or {}) and window_open(event) else {}


def late_members(db, event_id: str, since=None) -> list:
    """Members added in a window (since `since`, if given), on live teams:
    [{'name', 'email', 'team', 'reg_id', 'added_at', 'added_by', 'confirmed'}]."""
    from services_entry import inactive
    from services_hackathon import parse_iso
    found = []
    for doc in db.collection('registrations').where('event_id', '==', str(event_id)).stream():
        reg = doc.to_dict() or {}
        if inactive(reg):
            continue
        for m in reg.get('members') or []:
            if not isinstance(m, dict) or not m.get('late'):
                continue
            added = parse_iso(m.get('added_at'))
            if since and added and added < since:
                continue
            found.append({'name': m.get('name') or '', 'email': _email(m), 'team': reg.get('team_name') or '',
                          'reg_id': str(reg.get('reg_id') or doc.id), 'added_at': m.get('added_at') or '',
                          'added_by': m.get('added_by') or '', 'confirmed': bool(m.get('confirmed_at'))})
    return sorted(found, key=lambda f: f['added_at'])


def finish_window(db, event_id: str, event: dict, by: str = ''):
    """End the window, if one was opened, and send the SPOC who opened it one
    portal notice naming the members added in it. Returns those members, or
    None when there was no window to end (nothing is sent)."""
    from services_hackathon import parse_iso
    event_id = str(event_id)
    ref = db.collection('events').document(event_id)
    fresh = ref.get()
    event = dict(event or {}, **((fresh.to_dict() or {}) if fresh.exists else {}))
    if not event.get(WINDOW):
        return None
    ref.update({WINDOW: '', SINCE: ''})
    added = late_members(db, event_id, parse_iso(event.get(SINCE)))
    to = str(event.get('add_members_opened_by') or event.get('created_by') or '').strip().lower()
    title = event.get('title') or 'the event'
    confirmed = sum(a['confirmed'] for a in added)
    if added:
        names = '; '.join(f"{a['name'] or a['email']} ({a['team'] or 'a team'}): "
                          f"{'confirmed' if a['confirmed'] else 'not confirmed yet'}" for a in added[:25])
        more = f"; and {len(added) - 25} more" if len(added) > 25 else ''
        message = f"{len(added)} added, {confirmed} confirmed. {names}{more}."
    else:
        message = "No members were added while it was open."
    if to:
        try:
            from routes_notifications_v2 import create_notification
            create_notification(db, user_email=to, notif_type='team_window_closed',
                                title=f"Team changes for {title} have closed: {len(added)} member"
                                      f"{'' if len(added) == 1 else 's'} added",
                                message=message,
                                link=f"/coordinator/registrations/{event_id}?members=late",
                                metadata={'event_id': event_id})
        except Exception:
            pass
    from utils import log_action
    log_action(db, "ADD_MEMBERS_WINDOW_CLOSED",
               f"Event {event_id}: window ended{f' by {by}' if by else ''}; {len(added)} added, {confirmed} confirmed")
    return added


def close_window(db, event_id: str, event: dict = None, by: str = ''):
    """The SPOC's "Close now"."""
    return finish_window(db, event_id, event or {}, by=by)


def finish_ended_windows(db) -> int:
    """For the hourly job: end each window whose time has passed. Returns how many."""
    ended = 0
    for doc in db.collection('events').stream():
        event = doc.to_dict() or {}
        if event.get(WINDOW) and not window_open(event):
            ended += finish_window(db, doc.id, event) is not None
    return ended


def why_not_remove(reg: dict, event: dict) -> str:
    """'' when the lead may remove a member now: not when adding is refused
    for the team itself (cancelled, checked in, the event over; UPG-259), and
    after registration closes only while the SPOC's window is open."""
    from services_registration_edit import lead_may_edit
    return lead_may_edit(reg, event or {}) or (CLOSED_REMOVE if closed_for_changes(event) else '')


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
    if registration_closed(event) and not window_open(event):
        return CLOSED_MESSAGE
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
              'added_by': by, 'added_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              **late_fields(event)}
    added = _add_member(reg_id, member, team_max)      # the size is re-checked atomically (UPG-52)
    if added == 'full':
        raise AddError(f"Your team is full: {team_max} people is the most this event allows.")
    if added == 'already':
        raise AddError(f"{email} is already on your team.")
    return member, _tell(db, reg_id, event, member)


def own_details(member: dict, form) -> dict:
    """The name, USN and phone a member typed on their confirm page (UPG-251):
    the values that differ from what's saved, or AddError. Blank keeps what
    the lead typed; without the page's details block, nothing changes."""
    if form.get('details') != '1':
        return {}
    name = ' '.join(str(form.get('name') or '').split())[:100]
    usn = str(form.get('usn') or '').strip().upper()[:20]
    phone = str(form.get('phone') or '').strip()[:20]
    if phone and not _PHONE.match(phone):
        raise AddError("Enter a valid phone number, or leave it empty.")
    typed = {'name': name, 'usn': usn, 'phone': phone}
    return {k: v for k, v in typed.items() if v and v != str(member.get(k) or '')}


def save_own_details(db, reg_id: str, email: str, user: dict, typed: dict) -> None:
    """Save what the member typed on the team, and fill a USN or phone still
    missing from their profile; the profile gets what it lacked."""
    import services_team_confirm as confirm
    profile = {k: str((user or {}).get(k) or '') for k in ('usn', 'phone')}

    def change(m):
        values = dict(typed)
        for key in ('usn', 'phone'):
            if not values.get(key) and not m.get(key) and profile[key]:
                values[key] = profile[key]
        return values or None
    saved = confirm.update_member(db, reg_id, email, change)
    fill = {k: v for k, v in typed.items() if k in ('usn', 'phone') and v and not profile[k]}
    if fill:
        db.collection('users').document(email).update(fill)
    if saved is not None and typed:
        try:
            from utils import log_action
            log_action(db, "TEAM_MEMBER_DETAILS", f"{email} updated their details in {reg_id}: {', '.join(sorted(typed))}")
        except Exception:
            pass


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
