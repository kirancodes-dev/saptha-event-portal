"""
services_runsheet.py — the event's run sheet (UPG-272): the schedule the
organisers work from on the day.

The schedule is the event's agenda (`event['agenda']`, services_sessions).
The run sheet adds, for each item:

* a status (`planned`, `ready`, `running`, `done`, `delayed`, `cancelled`),
  kept on the agenda item: the public schedule marks a delayed or cancelled
  item;
* an owner (who is responsible) and a note for the staff, kept apart from the
  event in `run_sheets/<event_id>` so no public page or API carries them.

Saving the schedule is refused while two items need the same room at the same
time, or an item ends before it starts. An owner with two items at once, and a
room another event uses at that time, are warnings: the organiser may know
better. The schedule has times, not days, so for an event longer than a day
every clash is a warning (the two items may be on different days).

A change participants should know about (a new time or room, an item
cancelled, delayed, added or removed) can be announced when it is saved: it
goes to the event's announcements and to each registered person's
notification bell. No email is sent.
"""
import datetime
from typing import Dict, List, Optional, Tuple

from services_sessions import STATUSES

COLLECTION = 'run_sheets'
STATUS_LABELS = {'planned': 'Planned', 'ready': 'Ready', 'running': 'Running now', 'done': 'Done',
                 'delayed': 'Delayed', 'cancelled': 'Cancelled'}
STATUS_TONES = {'planned': 'neutral', 'ready': 'info', 'running': 'success', 'done': 'neutral',
                'delayed': 'warning', 'cancelled': 'danger'}
PUBLIC_STATUSES = ('delayed', 'cancelled')        # the ones a participant is told about
STAFF_STATUSES = ('planned', 'ready', 'running', 'done')   # the ones the event's staff set
OWNER_MAX, NOTE_MAX = 120, 300


def minutes(hhmm) -> Optional[int]:
    """`"09:30"` → 570; None for anything that isn't a time of day."""
    try:
        hours, mins = str(hhmm or '').strip()[:5].split(':')
        value = int(hours) * 60 + int(mins)
    except ValueError:
        return None
    return value if 0 <= int(hours) <= 23 and 0 <= int(mins) <= 59 else None


def status_of(item: dict) -> str:
    status = str((item or {}).get('status') or 'planned')
    return status if status in STATUSES else 'planned'


def _room(item: dict) -> str:
    return ' '.join(str((item or {}).get('room') or '').split()).casefold()


def _span(item: dict) -> Optional[Tuple[int, int]]:
    """An item's minutes from start to end; an item without an end is the
    moment it starts."""
    start = minutes(item.get('time'))
    if start is None:
        return None
    end = minutes(item.get('end'))
    return (start, end if end is not None and end > start else start)


def _overlap(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    if a[0] == a[1] or b[0] == b[1]:                       # one is a moment: inside the other, or the same moment
        point, other = (a, b) if a[0] == a[1] else (b, a)
        return other[0] <= point[0] < other[1] or point[0] == other[0]
    return a[0] < b[1] and b[0] < a[1]


def _when(item: dict) -> str:
    return f"{item.get('time', '')}" + (f"–{item['end']}" if item.get('end') else '')


def _name(item: dict) -> str:
    return f"“{item.get('title', '')}”"


def multi_day(event: dict) -> bool:
    end = str((event or {}).get('end_date') or '')[:10]
    return bool(end) and end != str((event or {}).get('date') or '')[:10]


def check(agenda: List[dict], owners: Optional[Dict[str, dict]] = None, one_day: bool = True) -> Tuple[List[dict], List[dict]]:
    """`(problems, warnings)`, each `{'ids': [...], 'message': ...}`.
    Problems stop the save. Cancelled items take no room and nobody's time."""
    owners = owners or {}
    problems, warnings = [], []
    live = [i for i in agenda if status_of(i) != 'cancelled']
    for item in agenda:
        start, end = minutes(item.get('time')), minutes(item.get('end'))
        if start is None:
            problems.append({'ids': [item['id']], 'message': f"{_name(item)} needs a start time like 09:30."})
        elif item.get('end') and end is None:
            problems.append({'ids': [item['id']], 'message': f"{_name(item)}: the end time isn't a time of day."})
        elif end is not None and end <= start:
            problems.append({'ids': [item['id']], 'message': f"{_name(item)} ends at {item['end']}, before it starts at {item['time']}."})
    for n, a in enumerate(live):
        for b in live[n + 1:]:
            sa, sb = _span(a), _span(b)
            if not sa or not sb or not _overlap(sa, sb):
                continue
            if _room(a) and _room(a) == _room(b):
                clash = {'ids': [a['id'], b['id']], 'message':
                         f"{a['room']} is needed twice at the same time: {_name(a)} ({_when(a)}) and {_name(b)} ({_when(b)})."}
                if one_day:
                    problems.append(clash)
                else:
                    warnings.append(dict(clash, message=clash['message'] + " If they are on different days, ignore this."))
            who_a = str((owners.get(a['id']) or {}).get('owner') or '').strip()
            who_b = str((owners.get(b['id']) or {}).get('owner') or '').strip()
            if who_a and who_a.casefold() == who_b.casefold():
                warnings.append({'ids': [a['id'], b['id']], 'message':
                                 f"{who_a} is responsible for two items at the same time: {_name(a)} ({_when(a)}) and {_name(b)} ({_when(b)})."})
    return problems, warnings


def elsewhere(db, event_id: str, event: dict, agenda: List[dict]) -> List[dict]:
    """Warnings for rooms another event uses at the same time on the same day
    (single-day events only: the schedule has no days)."""
    day = str((event or {}).get('date') or '')[:10]
    mine = [i for i in agenda if _room(i) and _span(i) and status_of(i) != 'cancelled']
    if not day or not mine or multi_day(event):
        return []
    from services_event_types import is_listed
    out = []
    for doc in db.collection('events').where('date', '==', day).stream():
        if str(doc.id) == str(event_id):
            continue
        other = doc.to_dict() or {}
        if str(other.get('status') or '').lower() in ('cancelled', 'rejected', 'archived') or multi_day(other):
            continue
        theirs = [i for i in other.get('agenda') or [] if isinstance(i, dict) and status_of(i) != 'cancelled']
        if other.get('time'):                             # the event itself, in its own room
            theirs.append({'title': other.get('title', ''), 'time': other.get('time'), 'end': other.get('end_time'),
                           'room': other.get('room_name') or other.get('venue')})
        name = f"“{other.get('title', '')}”" if is_listed(other) else "another event that isn't published yet"
        for a in mine:
            for b in theirs:
                sb = _span(b)
                if sb and _room(a) == _room(b) and _overlap(_span(a), sb):
                    out.append({'ids': [a['id']], 'message':
                                f"{a['room']} is also used by {name} at {_when(b)}, while {_name(a)} ({_when(a)}) is there."})
                    break
    return out


# ── Owners and staff notes ──────────────────────────────────────────────────

def staff_fields(db, event_id: str) -> Dict[str, dict]:
    """`{item id: {'owner', 'note'}}`: for the event's staff only."""
    doc = db.collection(COLLECTION).document(str(event_id)).get()
    items = (doc.to_dict() or {}).get('items') if doc.exists else None
    return {str(k): {'owner': str((v or {}).get('owner') or ''), 'note': str((v or {}).get('note') or '')}
            for k, v in (items or {}).items()}


def read_staff_fields(form, agenda: List[dict], rows: List[int]) -> Dict[str, dict]:
    """The owner and note typed beside each kept row."""
    owners, notes = form.getlist('owner[]'), form.getlist('note[]')
    out = {}
    for item, row in zip(agenda, rows):
        owner = ' '.join((owners[row] if row < len(owners) else '').split())[:OWNER_MAX]
        note = ' '.join((notes[row] if row < len(notes) else '').split())[:NOTE_MAX]
        if owner or note:
            out[item['id']] = {'owner': owner, 'note': note}
    return out


def save_staff_fields(db, event_id: str, fields: Dict[str, dict], actor: str) -> None:
    db.collection(COLLECTION).document(str(event_id)).set({
        'items': fields, 'updated_by': actor,
        'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})


def rows(event: dict, fields: Dict[str, dict]) -> List[dict]:
    """The run sheet in time order, each item with its owner, note and status."""
    out = []
    for item in (event or {}).get('agenda') or []:
        if not isinstance(item, dict):
            continue
        status = status_of(item)
        extra = fields.get(str(item.get('id') or ''), {})
        out.append(dict(item, status=status, status_label=STATUS_LABELS[status], status_tone=STATUS_TONES[status],
                        owner=extra.get('owner', ''), note=extra.get('note', '')))
    return sorted(out, key=lambda i: (minutes(i.get('time')) if minutes(i.get('time')) is not None else 24 * 60))


def by_owner(sheet: List[dict]) -> List[Tuple[str, List[dict]]]:
    """Who is responsible for what: `[(owner, their items)]`, nobody's last."""
    groups: Dict[str, List[dict]] = {}
    names: Dict[str, str] = {}
    for item in sheet:
        key = item['owner'].casefold()
        names.setdefault(key, item['owner'])
        groups.setdefault(key, []).append(item)
    return [(names[k], groups[k]) for k in sorted(groups, key=lambda k: (k == '', k))]


def set_status(db, event_id: str, event: dict, item_id: str, status: str, actor: str) -> Optional[dict]:
    """Change one item's status. Returns the item as it was, or None when the
    item or the status isn't known."""
    from utils import log_action
    if status not in STATUSES:
        return None
    agenda = [dict(i) for i in (event or {}).get('agenda') or [] if isinstance(i, dict)]
    before = next((dict(i) for i in agenda if str(i.get('id') or '') == str(item_id)), None)
    if before is None:
        return None
    for item in agenda:
        if str(item.get('id') or '') == str(item_id):
            item.pop('status', None)
            if status != 'planned':
                item['status'] = status
    db.collection('events').document(str(event_id)).update({'agenda': agenda})
    log_action(db, "RUN_SHEET_STATUS", f"{actor}: event {event_id}, \"{before.get('title', '')}\" is {status}")
    return before


# ── Telling participants ────────────────────────────────────────────────────

def changes(before: List[dict], after: List[dict]) -> List[str]:
    """What changed that a participant should know, one sentence each. Items
    are matched by ID; an agenda from before items had IDs gives nothing."""
    old = {str(i['id']): i for i in before or [] if isinstance(i, dict) and i.get('id')}
    new = {str(i['id']): i for i in after or [] if isinstance(i, dict) and i.get('id')}
    if not old:
        return []
    out = []
    for sid, item in new.items():
        was = old.get(sid)
        where = f" in {item['room']}" if item.get('room') else ''
        if was is None:
            if status_of(item) != 'cancelled':
                out.append(f"New: {_name(item)} at {item.get('time', '')}{where}.")
            continue
        now_status, was_status = status_of(item), status_of(was)
        if now_status == 'cancelled':
            if was_status != 'cancelled':
                out.append(f"{_name(item)} ({was.get('time', '')}) is cancelled.")
            continue
        if was_status == 'cancelled':
            out.append(f"{_name(item)} is back on, at {item.get('time', '')}{where}.")
            continue
        if item.get('time') != was.get('time'):
            out.append(f"{_name(item)} now starts at {item.get('time', '')} (was {was.get('time', '')}).")
        elif (item.get('end') or '') != (was.get('end') or '') and item.get('end'):
            out.append(f"{_name(item)} now ends at {item['end']}" + (f" (was {was['end']})." if was.get('end') else '.'))
        if _room(item) != _room(was):
            out.append(f"{_name(item)} has moved to {item['room']}" + (f" (was {was['room']})." if was.get('room') else '.')
                       if item.get('room') else f"{_name(item)} is no longer in {was.get('room')}; the place will be announced.")
        if now_status == 'delayed' and was_status != 'delayed':
            out.append(f"{_name(item)} ({item.get('time', '')}) is delayed.")
    for sid, was in old.items():
        if sid not in new and status_of(was) != 'cancelled':
            out.append(f"{_name(was)} ({was.get('time', '')}) has been taken off the schedule.")
    return out


def announce(db, event_id: str, event: dict, sentences: List[str], actor: str) -> int:
    """Post the changes to the event's announcements and to each registered
    person's notification bell. Returns how many people were told."""
    from routes_notifications_v2 import create_bulk_notifications
    from services_recipients import registration_people
    from utils import log_action
    import services_entry
    if not sentences:
        return 0
    title = str((event or {}).get('title') or 'Event')
    message = "Schedule change: " + ' '.join(sentences)
    db.collection('announcements').add({
        'event_id': str(event_id), 'event_title': title, 'message': message[:1000], 'priority': 'warning',
        'spoc_email': actor, 'kind': 'schedule_change',
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    people = []
    for doc in db.collection('registrations').where('event_id', '==', str(event_id)).stream():
        reg = doc.to_dict() or {}
        if str(reg.get('status') or '').strip().lower() in ('cancelled', 'refunded'):
            continue
        if services_entry.left_out(event, reg):          # not on the entry list: told nothing more (UPG-214)
            continue
        for email, _name_, _phone in registration_people(reg):
            if email not in people:
                people.append(email)
    if people:
        create_bulk_notifications(db, emails=people, notif_type='announcement', title=f"{title}: schedule change",
                                  message=message[:500], link=f"/event/{event_id}")
    log_action(db, "SCHEDULE_CHANGE_ANNOUNCED", f"{actor}: event {event_id}, {len(sentences)} change(s) to {len(people)} people")
    return len(people)
