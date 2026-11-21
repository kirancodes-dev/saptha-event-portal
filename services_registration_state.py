"""
services_registration_state.py — the one answer to "can someone register for
this event right now, and if not, why?" (UPG-266).

Every page that offers or refuses registration reads `state(event)`: the home
page, the catalogue, the event page and its popup, the open-events page, the
student dashboard, the "registration closed" page, the organisers' panels and
the live refresh. The registration form's own gate (`routes_forms.
registration_closed`) is this module's `registerable`, so a page can never
offer an action the form then refuses.

The day is the university's (IST), as in the lifecycle job. Dates are whole
days: registration opens at the start of `reg_opens` and stays open through
the end of the deadline day.

Seats are the count the form itself uses (`registration_count`), so "full"
here is exactly when the form puts a new sign-up on the waitlist. A full event
always takes a waitlist in this app, so the state for a full event is
`waitlist`; `full` is used only where a caller says the waitlist can't be
joined (`waitlist_open=False`).
"""
import datetime
import re
from typing import Optional

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

NOT_OPEN, OPEN, WAITLIST, FULL = 'not_open', 'open', 'waitlist', 'full'
CLOSED, ENDED, CANCELLED, UNPUBLISHED, PROGRAMME = 'closed', 'ended', 'cancelled', 'unpublished', 'programme'

KEYS = (NOT_OPEN, OPEN, WAITLIST, FULL, CLOSED, ENDED, CANCELLED, UNPUBLISHED, PROGRAMME)
REGISTERABLE = (OPEN, WAITLIST)

_CANCELLED = ('cancelled', 'rejected')
_UNPUBLISHED = ('draft', 'pending', 'pending_approval', 'changes_requested', 'archived', 'inactive')
_OVER = ('completed', 'certified', 'evaluation')

LABELS = {
    NOT_OPEN: 'Opens soon', OPEN: 'Registration open', WAITLIST: 'Full: waitlist open', FULL: 'Full',
    CLOSED: 'Registration closed', ENDED: 'Event over', CANCELLED: 'Cancelled', UNPUBLISHED: 'Not published',
    PROGRAMME: 'See the programme',
}
TONES = {
    NOT_OPEN: 'info', OPEN: 'success', WAITLIST: 'warning', FULL: 'warning', CLOSED: 'neutral',
    ENDED: 'neutral', CANCELLED: 'danger', UNPUBLISHED: 'neutral', PROGRAMME: 'info',
}


def today() -> datetime.date:
    return datetime.datetime.now(IST).date()


def _day(value) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(value or '').strip()[:10])
    except ValueError:
        return None


def _int(value) -> int:
    try:
        return max(int(float(value or 0)), 0)
    except (TypeError, ValueError):
        return 0


def _long(day: datetime.date) -> str:
    return f"{day.day} {day.strftime('%B %Y')}"


def seats(event: dict, taken: Optional[int] = None) -> dict:
    """The limit (0 without one), seats taken and seats free, as the form counts them."""
    event = event or {}
    limit = _int((event.get('limits') or {}).get('max_participants')) or _int(event.get('capacity'))
    used = _int(event.get('registration_count')) if taken is None else _int(taken)
    return {'limit': limit, 'taken': used, 'free': max(limit - used, 0) if limit else None}


def state(event: dict, *, taken: Optional[int] = None, waiting_for_organiser: bool = False,
          waitlist_open: bool = True, on: Optional[datetime.date] = None) -> dict:
    """The event's registration state.

    `taken` overrides the event's own count. `waiting_for_organiser` is true
    when the waitlist no longer moves up on its own and someone is on it, so
    new sign-ups join the line even with a seat free (UPG-243)."""
    event = event or {}
    on = on or today()
    status = str(event.get('status') or '').strip().lower()
    opens = _day(event.get('reg_opens'))
    # `deadline` first, as the form's gate has always read it (UPG-34)
    deadline = _day(event.get('deadline') or event.get('reg_deadline'))
    first = _day(event.get('date'))
    last = max([d for d in (first, _day(event.get('end_date'))) if d], default=None)
    room = seats(event, taken)

    def answer(key, explanation, action='', action_label=''):
        return {
            'key': key, 'label': LABELS[key], 'tone': TONES[key], 'explanation': explanation,
            'action': action, 'action_label': action_label,
            'action_url': f"/forms/register/{event.get('id', '')}" if action else '',
            'registerable': key in REGISTERABLE,
            'opens': opens.isoformat() if opens else '', 'deadline': deadline.isoformat() if deadline else '',
            'seats': room,
        }

    if status in _CANCELLED:
        return answer(CANCELLED, "This event was cancelled. Nobody can register.")
    if status in _UNPUBLISHED:
        return answer(UNPUBLISHED, "This event isn't published, so nobody can register yet.")
    if status in _OVER or (last and on > last):
        return answer(ENDED, "This event is over." if not last else f"This event ended on {_long(last)}.")
    if event.get('is_fest') and status == 'published':
        return answer(PROGRAMME, "This is a fest: register for each event in its programme.")
    if status == 'published':
        if opens and on < opens:
            return answer(NOT_OPEN, f"Registration opens on {_long(opens)}.")
        return answer(NOT_OPEN, "Registration hasn't opened yet. The organisers will open it soon.")
    if status == 'registration_closed':
        return answer(CLOSED, f"Registration closed on {_long(deadline)}." if deadline and on > deadline
                      else "The organisers have closed registration.")
    if opens and on < opens:
        return answer(NOT_OPEN, f"Registration opens on {_long(opens)}.")
    if deadline and on > deadline:
        return answer(CLOSED, f"Registration closed on {_long(deadline)}.")

    until = f" until {_long(deadline)}" if deadline else ""
    if (room['limit'] and room['taken'] >= room['limit']) or (room['limit'] and waiting_for_organiser):
        taken = "The one seat is taken." if room['limit'] == 1 else f"All {room['limit']} seats are taken."
        if not waitlist_open:
            return answer(FULL, taken)
        why = taken if room['taken'] >= room['limit'] else "Others are already waiting for a seat."
        return answer(WAITLIST, f"{why} You can join the waitlist{until}; you'll be told if a seat opens.",
                      'waitlist', 'Join the waitlist')
    left = ''
    if room['limit'] and room['free'] is not None and room['free'] <= max(5, room['limit'] // 10):
        left = f" {room['free']} seat{'' if room['free'] == 1 else 's'} left."
    return answer(OPEN, f"Registration is open{until}.{left}", 'register', 'Register')


def registerable(event: dict) -> bool:
    """Would the registration form take a new sign-up (a seat or the waitlist)?"""
    return state(event)['registerable']


def for_event(db, event_id: str, event: dict) -> dict:
    """`state` with the waitlist rule the form applies (UPG-243), read from the database."""
    waiting = False
    try:
        from services_waitlist import auto_moves_up, someone_waiting
        if seats(event)['limit'] and not auto_moves_up(event):
            waiting = someone_waiting(db, event_id)
    except Exception:
        waiting = False
    return state(dict(event or {}, id=event_id), waiting_for_organiser=waiting)


def of(db, event) -> dict:
    """`for_event` for whatever a template holds: a dict or a document wrapper."""
    event_id = getattr(event, 'id', None)
    if not isinstance(event, dict):
        event = event.to_dict() if hasattr(event, 'to_dict') else {}
    event = event or {}
    return for_event(db, event_id or event.get('id', ''), event)


def public(view: dict) -> dict:
    """What a public page or the live refresh may show: no counts beyond seats."""
    return {k: view[k] for k in ('key', 'label', 'tone', 'explanation', 'action', 'action_label', 'action_url')}


# ── How pages word and order events (UPG-294) ───────────────────────────────

def day_text(value) -> str:
    """A stored date as people read it: '2026-11-25' is '25 Nov 2026', and
    '2026-11-25T10:00' is '25 Nov 2026, 10:00'. Text that isn't a date ('TBA')
    comes back as it is."""
    text = str(value or '').strip()
    day = _day(text) if re.match(r'\d{4}-\d{2}-\d{2}', text) else None
    if not day:
        return text
    clock = re.match(r'[T ](\d{2}:\d{2})', text[10:])
    return f"{day.day} {day.strftime('%b %Y')}" + (f", {clock.group(1)}" if clock else '')


_PRIZE_NUMBER = re.compile(r'^(?:₹|rs\.?|inr)?\s*(\d[\d,]*)(\.\d{1,2})?\s*(?:/-|rs\.?|inr|rupees)?$', re.I)


def prize_text(value) -> str:
    """A prize as people read it (UPG-367): a plain amount ('3000', 'Rs. 3,000',
    '3000/-') is '₹3,000', grouped the Indian way ('₹1,00,000'); any other
    text ('Trophy and goodies') comes back as it was typed."""
    text = str(value if value is not None else '').strip()
    found = _PRIZE_NUMBER.match(text)
    if not found:
        return text
    digits = found.group(1).replace(',', '').lstrip('0') or '0'
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return '₹' + ','.join(groups + [tail]) + (found.group(2) or '')


_LISTING_GROUP = {OPEN: 0, WAITLIST: 0, PROGRAMME: 0, NOT_OPEN: 1, FULL: 1, CLOSED: 2}


def listing_key(view: dict, date) -> tuple:
    """Sort key for a public list of events: what a visitor can register for
    first, then what opens soon, then what has closed, each soonest first;
    events that are over or cancelled come last, the most recent first."""
    group = _LISTING_GROUP.get((view or {}).get('key'), 3)
    day = _day(date)
    number = day.toordinal() if day else 10 ** 7
    return (group, -number if group == 3 else number)


_ORGANISER_WORDS = {
    'draft': ('Draft', 'neutral'), 'pending': ('Waiting for approval', 'warning'),
    'pending_approval': ('Waiting for approval', 'warning'), 'changes_requested': ('Changes requested', 'warning'),
    'archived': ('Archived', 'neutral'), 'inactive': ('Inactive', 'neutral'), 'rejected': ('Rejected', 'danger'),
}


def organiser_status(event: dict, view: Optional[dict] = None) -> dict:
    """The event's status in plain words for the people who run it: the
    registration state everyone else sees, except that an event the public
    can't see yet says why (draft, waiting for approval, changes requested)."""
    event = event or {}
    view = view or state(event)
    status = str(event.get('status') or '').strip().lower()
    if status in _ORGANISER_WORDS:
        label, tone = _ORGANISER_WORDS[status]
    elif view['key'] == PROGRAMME:
        label, tone = 'Published', 'success'
    else:
        label, tone = view['label'], view['tone']
    return {'label': label, 'tone': tone, 'explanation': view['explanation'], 'key': view['key']}


def team_label(name) -> str:
    """'Phoenix' is 'Team Phoenix'; a name that already says it ('Team Phoenix',
    'TEAM X', 'team-alpha') stays as it is (UPG-377)."""
    text = str(name or '').strip()
    if not text:
        return ''
    return text if re.match(r'team\b', text, re.I) else f'Team {text}'


def checkin_window(event: dict) -> dict:
    """When the event's people can be checked in (UPG-378): from its first day
    to its last, in India. 'before', 'open' or 'over', and the two days in words.
    An event without a date is always open."""
    event = event or {}
    first = _day(event.get('date') or event.get('start_datetime'))
    last = _day(event.get('end_date') or event.get('end_datetime')) or first
    if first and last and last < first:
        last = first
    now = today()
    key = 'open' if not first else ('before' if now < first else ('over' if now > last else 'open'))
    return {'key': key, 'first': day_text(first.isoformat()) if first else '',
            'last': day_text(last.isoformat()) if last else ''}
