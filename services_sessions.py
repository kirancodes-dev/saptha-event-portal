"""
services_sessions.py — agenda sessions: attendance, starred sessions and
session hours (UPG-159).

The sessions are the event's agenda items (`event['agenda']`). Each has an
`id`, a start time, and optionally an end time, a room, a capacity and hours.
An agenda saved before UPG-159 has items without an ID: they get one the next
time the organiser saves the schedule, and until then can't be scanned into.

Attendance is per registration (a team's registration is one row), recorded
when the event's check-in staff scan a ticket in "session" mode. The session
scan checks the person in to the event first if they aren't yet, through the
shared check-in, so a session scan never lets in someone the gate would refuse.

Hours: when any session has hours, a registration earns the hours of the
sessions it attended rather than the event's hours (services_ledger).
"""
import datetime as _dt
import secrets
from typing import Dict, List, Optional, Set

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
MAX_SESSIONS = 60


def new_id() -> str:
    return 's' + secrets.token_hex(4)


def _num(value, kind=float):
    try:
        number = kind(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def parse_agenda(form) -> List[Dict]:
    """The agenda from the schedule builder's rows (time[], end[], title[],
    desc[], room[], capacity[], hours[], sid[]). Rows keep their ID; new rows
    get one."""
    columns = {name: form.getlist(f'{name}[]') for name in
               ('time', 'end', 'title', 'desc', 'room', 'capacity', 'hours', 'sid')}
    rows = len(columns['title'])
    agenda, seen = [], set()
    for i in range(min(rows, MAX_SESSIONS)):
        def cell(name):
            values = columns[name]
            return (values[i] if i < len(values) else '').strip()
        time, title = cell('time'), cell('title')
        if not (time and title):
            continue
        sid = cell('sid')
        if not sid or sid in seen or len(sid) > 32:
            sid = new_id()
        seen.add(sid)
        item = {'id': sid, 'time': time, 'title': title[:200], 'desc': cell('desc')[:500]}
        if cell('end'):
            item['end'] = cell('end')
        if cell('room'):
            item['room'] = cell('room')[:100]
        capacity, hours = _num(cell('capacity'), int), _num(cell('hours'))
        if capacity:
            item['capacity'] = capacity
        if hours:
            item['hours'] = round(hours, 2)
        agenda.append(item)
    return agenda


def sessions_for(event: dict) -> List[Dict]:
    """The event's sessions that can be scanned into (agenda items with an ID)."""
    return [item for item in ((event or {}).get('agenda') or []) if isinstance(item, dict) and item.get('id')]


def find(event: dict, session_id: str) -> Optional[Dict]:
    return next((s for s in sessions_for(event) if s['id'] == str(session_id or '')), None)


def has_session_hours(event: dict) -> bool:
    return any(_num(s.get('hours')) for s in sessions_for(event))


def label(session: dict) -> str:
    return f"{session.get('time', '')} {session.get('title', '')}".strip()


# ── Attendance ─────────────────────────────────────────────────────────────

def _session():
    from db_pg import get_session
    return get_session()


def count(event_id: str, session_id: str) -> int:
    from models_pg import SessionAttendance
    with _session() as s:
        return s.query(func.count(SessionAttendance.key)).filter(
            SessionAttendance.event_id == str(event_id), SessionAttendance.session_id == str(session_id)).scalar() or 0


def is_full(event_id: str, session: dict) -> bool:
    capacity = _num(session.get('capacity'), int)
    return bool(capacity) and count(event_id, session['id']) >= capacity


def attend(event_id: str, session_id: str, reg_id: str, by: str, over_capacity: bool = False) -> Optional[str]:
    """Record the registration at the session. Returns None when it's new, or
    the time of the first scan when it was already in."""
    from models_pg import SessionAttendance
    key = f"{reg_id}:{session_id}"
    now = _dt.datetime.now(IST).strftime('%H:%M:%S')
    try:
        with _session() as s:
            s.add(SessionAttendance(key=key, event_id=str(event_id), session_id=str(session_id),
                                    reg_id=str(reg_id), scanned_at=now, scanned_by=by or '',
                                    over_capacity=bool(over_capacity)))
            s.commit()
        return None
    except IntegrityError:
        return scanned_at(reg_id, session_id) or 'earlier'


def scanned_at(reg_id: str, session_id: str) -> Optional[str]:
    """When the registration was first scanned into the session, or None."""
    from models_pg import SessionAttendance
    with _session() as s:
        row = s.get(SessionAttendance, f"{reg_id}:{session_id}")
        return None if row is None else (row.scanned_at or 'earlier')


def attended(event_id: str) -> Dict[str, Set[str]]:
    """{reg_id: {session ids}} for the event."""
    from models_pg import SessionAttendance
    out: Dict[str, Set[str]] = {}
    with _session() as s:
        for reg_id, session_id in s.query(SessionAttendance.reg_id, SessionAttendance.session_id).filter(
                SessionAttendance.event_id == str(event_id)):
            out.setdefault(reg_id, set()).add(session_id)
    return out


def attended_by(reg_id: str) -> Set[str]:
    from models_pg import SessionAttendance
    with _session() as s:
        return {sid for (sid,) in s.query(SessionAttendance.session_id).filter(
            SessionAttendance.reg_id == str(reg_id))}


def session_hours(reg_id: str, event: dict) -> float:
    """The hours of the event's sessions this registration attended."""
    if not reg_id:
        return 0.0
    went = attended_by(reg_id)
    return float(sum(_num(s.get('hours')) or 0 for s in sessions_for(event) if s['id'] in went))


# ── Starred sessions ("My agenda") ─────────────────────────────────────────

def _star_key(email, event_id, session_id):
    return f"{(email or '').lower()}:{event_id}:{session_id}"


def star(email: str, event_id: str, session_id: str, on: bool = True) -> None:
    from models_pg import SessionStar
    key = _star_key(email, event_id, session_id)
    with _session() as s:
        row = s.get(SessionStar, key)
        if on and row is None:
            s.add(SessionStar(key=key, email=(email or '').lower(), event_id=str(event_id), session_id=str(session_id)))
        elif not on and row is not None:
            s.delete(row)
        else:
            return
        try:
            s.commit()
        except IntegrityError:   # starred twice at once: it's starred
            s.rollback()


def starred(email: str, event_id: str) -> Set[str]:
    from models_pg import SessionStar
    with _session() as s:
        return {sid for (sid,) in s.query(SessionStar.session_id).filter(
            SessionStar.email == (email or '').lower(), SessionStar.event_id == str(event_id))}


# ── Calendar file ──────────────────────────────────────────────────────────

def _ics_text(value: Optional[str]) -> str:
    return (str(value or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            .replace('\r', '').replace('\n', '\\n'))


def _at(day: str, hhmm: str) -> Optional[_dt.datetime]:
    try:
        return _dt.datetime.strptime(f"{day[:10]} {hhmm[:5]}", '%Y-%m-%d %H:%M').replace(tzinfo=IST)
    except (TypeError, ValueError):
        return None


def ics(event_id: str, event: dict, sessions: List[Dict]) -> str:
    """An iCalendar file with one VEVENT per session, on the event's date
    (sessions without an end last an hour)."""
    day = str(event.get('date') or '')[:10]
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//SapthaEvent//My agenda//EN', 'CALSCALE:GREGORIAN']
    for s in sessions:
        start = _at(day, s.get('time', ''))
        if start is None:
            continue
        end = _at(day, s.get('end', '')) or start + _dt.timedelta(hours=1)
        if end <= start:
            end = start + _dt.timedelta(hours=1)
        utc = _dt.timezone.utc
        lines += ['BEGIN:VEVENT', f"UID:{event_id}-{s['id']}@sapthaevent", f"DTSTAMP:{stamp}",
                  f"DTSTART:{start.astimezone(utc).strftime('%Y%m%dT%H%M%SZ')}",
                  f"DTEND:{end.astimezone(utc).strftime('%Y%m%dT%H%M%SZ')}",
                  f"SUMMARY:{_ics_text(s.get('title'))} — {_ics_text(event.get('title'))}"]
        where = s.get('room') or event.get('venue')
        if where:
            lines.append(f"LOCATION:{_ics_text(where)}")
        if s.get('desc'):
            lines.append(f"DESCRIPTION:{_ics_text(s['desc'])}")
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines) + '\r\n'
