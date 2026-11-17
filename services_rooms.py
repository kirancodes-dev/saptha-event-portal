"""
services_rooms.py — rooms for an event: a draft only the SPOC sees, a final
check, then "Allocate final" (UPG-306).

1. Rooms: a room number or name and a capacity in seats. A seat is a person
   (a team of 4 takes 4 seats) or, if the SPOC chooses, a whole team (a team
   of 4 takes 1 seat; UPG-312).
2. Draft: "Auto-fill" places teams in registration order, a team never split,
   into the first room with seats for the whole team; cancelled teams are left
   out. The SPOC moves teams by hand. The draft is saved on the event only.
3. Final check: each room's teams and people, and what to fix.
4. Allocate final: the SPOC ticks "Email the team lead", "Show on the
   website", or both. Only now is `assigned_room` written on registrations,
   which is what the scanner, judges, round panel and participants read.
   `room_on_site` False (email only) keeps the room off participants' pages.
5. Later changes stay in the draft until Allocate final is pressed again; it
   tells only teams whose room changed, or by a channel newly ticked.

Everything lives in the event's `room_plan`:
    rooms       [{name, capacity}]
    per         'person' (default) or 'team': what one seat is (UPG-312)
    draft       {reg_id: room}          draft_at, draft_by
    final       {reg_id: room}          final_at, final_by, email, website
    told        {reg_id: {room, email, website}}   what each team was told
An event whose teams had rooms before UPG-306 has no plan: its rooms are read
as already final and shown on the website (as they were).
"""
import datetime

import services_registration_filters as filters

PLAN = 'room_plan'
MAX_ROOMS = 200
PER_PERSON, PER_TEAM = 'person', 'team'


class RoomError(Exception):
    pass


def _now() -> str:
    # The format registrations use for `registered_at`, so the two compare
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _rid(reg) -> str:
    return str(reg.get('id') or '')


def size(reg: dict) -> int:
    """Seats a team takes: everyone on it, the lead included."""
    return filters.size(reg)


def per(p_or_event) -> str:
    """What one seat is for this plan (or event): a person, or a whole team."""
    d = p_or_event or {}
    if PLAN in d:
        d = d.get(PLAN) or {}
    return PER_TEAM if d.get('per') == PER_TEAM else PER_PERSON


def seats(reg: dict, unit: str = PER_PERSON) -> int:
    """Seats a team takes: 1 when a seat is a team, else everyone on it."""
    return 1 if unit == PER_TEAM else size(reg)


def active(regs) -> list:
    """Teams that can have a room (not cancelled), first registered first."""
    keep = [r for r in regs if str(r.get('status') or '').strip().lower() not in filters.CANCELLED]
    return sorted(keep, key=lambda r: (str(r.get('registered_at') or ''), _rid(r)))


def parse_rooms(names, capacities) -> list:
    """[{name, capacity}] from the form's rows: blank or 0 rows dropped, each name once."""
    rooms, seen = [], set()
    for name, cap in zip(names or [], capacities or []):
        name = str(name or '').strip()[:100]
        try:
            cap = int(str(cap).strip())
        except (TypeError, ValueError):
            cap = 0
        if not name or cap <= 0 or name.lower() in seen:
            continue
        seen.add(name.lower())
        rooms.append({'name': name, 'capacity': min(cap, 100000)})
    return rooms[:MAX_ROOMS]


def plan(event: dict, regs=None) -> dict:
    """The event's room plan. Without one, rooms given before UPG-306 count as
    the final allocation and the draft (they were already shown)."""
    p = dict((event or {}).get(PLAN) or {})
    p['rooms'] = list(p.get('rooms') or (event or {}).get('rooms') or [])
    if 'draft' not in p:
        old = {_rid(r): r['assigned_room'] for r in (regs or []) if r.get('assigned_room')}
        p['draft'] = dict(old)
        if old:
            emailed = bool((event or {}).get('room_emails_sent'))
            p.update(final=dict(old), website=True, email=emailed, legacy=True,
                     told={k: {'room': v, 'email': emailed, 'website': True} for k, v in old.items()})
    p['draft'] = dict(p.get('draft') or {})
    p['final'] = dict(p.get('final') or {})
    p['told'] = dict(p.get('told') or {})
    return p


def _save(db, event_id: str, event: dict, p: dict) -> None:
    keep = {k: v for k, v in p.items() if k != 'legacy'}
    db.collection('events').document(str(event_id)).update({PLAN: keep, 'rooms': keep.get('rooms') or []})
    event[PLAN] = keep
    event['rooms'] = keep.get('rooms') or []


def auto_fill(rooms, regs, unit: str = PER_PERSON) -> dict:
    """{reg_id: room}: registration order, each team whole in the first room with seats for all of it."""
    left = [[r['name'], int(r.get('capacity') or 0)] for r in rooms]
    draft = {}
    for reg in active(regs):
        need = seats(reg, unit)
        for slot in left:
            if slot[1] >= need:
                draft[_rid(reg)] = slot[0]
                slot[1] -= need
                break
    return draft


def save_rooms(db, event_id, event, regs, rooms, by='', unit=None) -> dict:
    p = plan(event, regs)
    p['rooms'] = rooms
    if unit in (PER_PERSON, PER_TEAM):
        p['per'] = unit
    _save(db, event_id, event, p)
    return p


def fill(db, event_id, event, regs, by='') -> dict:
    """Auto-fill: the draft is replaced by a fresh one."""
    p = plan(event, regs)
    if not p['rooms']:
        raise RoomError("Add at least one room with its capacity first.")
    p.update(draft=auto_fill(p['rooms'], regs, per(p)), draft_at=_now(), draft_by=by)
    _save(db, event_id, event, p)
    return p


def move(db, event_id, event, regs, reg_id, room, by='', typed=False) -> dict:
    """Put one team in a room ('' for no room), in the draft only. A room the
    SPOC typed (UPG-313) is the listed room of that name, whatever its capitals,
    or else joins the list with seats for this team."""
    p = plan(event, regs)
    room = str(room or '').strip()[:100]
    p.pop('added', None)
    if room and typed:
        known = {r['name'].lower(): r['name'] for r in p['rooms']}
        if room.lower() in known:
            room = known[room.lower()]
        elif len(p['rooms']) >= MAX_ROOMS:
            raise RoomError(f"You have {MAX_ROOMS} rooms already.")
        else:
            reg = next((r for r in regs or [] if _rid(r) == str(reg_id)), {})
            p['rooms'] = [*p['rooms'], {'name': room, 'capacity': max(1, seats(reg, per(p)) if reg else 1),
                                        'typed': True}]
            p['added'] = room
    if room:
        p['draft'][str(reg_id)] = room
    else:
        p['draft'].pop(str(reg_id), None)
    p.setdefault('draft_at', _now())
    p['draft_by'] = by or p.get('draft_by', '')
    added = p.pop('added', None)
    _save(db, event_id, event, p)
    return dict(p, room=room, added=added)


def summary(event, regs, p=None) -> dict:
    """The final check: each room's teams and people, and what to fix."""
    p = p or plan(event, regs)
    teams = active(regs)
    names = [r['name'] for r in p['rooms']]
    by_room = {n: [] for n in names}
    unallocated, unknown, late, pending = [], [], [], []
    draft_at = str(p.get('draft_at') or '')
    for reg in teams:
        room = p['draft'].get(_rid(reg))
        if not room:
            unallocated.append(reg)
            if draft_at and str(reg.get('registered_at') or '') > draft_at:
                late.append(reg)
        elif room in by_room:
            by_room[room].append(reg)
        else:
            unknown.append((reg, room))
        if room and str(reg.get('status') or '').strip().lower() == 'pending_payment':
            pending.append(reg)
    unit = per(p)
    rooms = []
    for r in p['rooms']:
        people = sum(size(t) for t in by_room[r['name']])
        used = sum(seats(t, unit) for t in by_room[r['name']])
        cap = int(r.get('capacity') or 0)
        rooms.append({'name': r['name'], 'capacity': cap, 'teams': by_room[r['name']], 'people': people,
                      'used': used, 'left': cap - used, 'over': used > cap})
    what = 'teams' if unit == PER_TEAM else 'people'
    problems = [f"{r['name']} has {r['used']} {what} for {r['capacity']} seats." for r in rooms if r['over']]
    for missing in sorted({room for _, room in unknown}):
        problems.append(f"{missing} isn't in your room list: add it, or move its teams.")
    notes = []
    if unallocated:
        notes.append(f"{len(unallocated)} team(s) have no room and won't get one.")
    if late:
        notes.append(f"{len(late)} team(s) registered after the draft was made.")
    if pending:
        notes.append(f"{len(pending)} team(s) with a room are still waiting for payment.")
    final = p['final']
    changes = [reg for reg in teams if final and (p['draft'].get(_rid(reg)) or '') != (final.get(_rid(reg)) or '')]
    return {'rooms': rooms, 'unallocated': unallocated, 'unknown': unknown, 'late': late, 'pending': pending,
            'problems': problems, 'notes': notes, 'changes': changes, 'teams': teams,
            'allocated': sum(1 for t in teams if p['draft'].get(_rid(t))),
            'people': sum(size(t) for t in teams if p['draft'].get(_rid(t))),
            'seats': sum(int(r.get('capacity') or 0) for r in p['rooms']), 'per': unit, 'plan': p}


def counts(event, regs) -> dict:
    """What the page's room cards show after a change (for the page script)."""
    s = summary(event, regs)
    return {'rooms': [{'name': r['name'], 'people': r['people'], 'used': r['used'], 'capacity': r['capacity'],
                       'teams': len(r['teams']), 'over': r['over']} for r in s['rooms']],
            'unallocated': len(s['unallocated']), 'changes': len(s['changes'])}


def rows(event, regs) -> list:
    """The CSV of the draft: one row per team, by room."""
    s = summary(event, regs)
    out = []
    for room in s['rooms']:
        for t in room['teams']:
            out.append(_row(room['name'], t))
    for t, room in s['unknown']:
        out.append(_row(room, t))
    for t in s['unallocated']:
        out.append(_row('', t))
    return out


CSV_COLUMNS = ['Room', 'Team', 'Lead', 'Lead email', 'People', 'Members', 'Registered at']


def _row(room, t):
    members = ', '.join(str(m.get('name') or m.get('email') or '') for m in t.get('members') or []
                        if isinstance(m, dict))
    return [room or 'No room', t.get('team_name') or '', t.get('lead_name') or '', t.get('lead_email') or '',
            size(t), members, t.get('registered_at') or '']


def on_site(reg: dict) -> str:
    """The room a participant may see on the website ('' when it went by email only)."""
    if (reg or {}).get('room_on_site') is False:
        return ''
    return str((reg or {}).get('assigned_room') or '')


def finalize(db, event_id, event, regs, *, email: bool, website: bool, anyway: bool = False, by='') -> dict:
    """Allocate final: write the draft onto registrations and tell teams."""
    if not (email or website):
        raise RoomError("Tick at least one: email the team lead, or show on the website.")
    p = plan(event, regs)
    s = summary(event, regs, p)
    if s['problems'] and not anyway:
        raise RoomError("Fix these first, or tick “allocate anyway”: " + ' '.join(s['problems']))
    if not s['allocated']:
        raise RoomError("No team has a room in the draft yet.")
    import services_hackathon
    import utils_email
    ev = dict(event, id=str(event_id))
    title = event.get('title') or 'Event'
    told, final = p['told'], {}
    result = {'emailed': 0, 'noticed': 0, 'withdrawn': 0, 'teams': 0}
    active_ids = {_rid(t) for t in s['teams']}
    for reg in regs:
        rid = _rid(reg)
        new = p['draft'].get(rid, '') if rid in active_ids else ''
        if (reg.get('assigned_room') or '') != new or (new and reg.get('room_on_site') is not website):
            db.collection('registrations').document(rid).update(
                {'assigned_room': new or None, 'room_on_site': bool(website)})
        was = told.get(rid) or {}
        if new:
            final[rid] = new
            result['teams'] += 1
            moved = was.get('room') != new
            sent = False
            if email and (moved or not was.get('email')) and reg.get('lead_email'):
                sent = bool(utils_email.send_room_assignment_email(
                    to_email=reg['lead_email'], name=reg.get('lead_name') or 'Participant', event_title=title,
                    room_name=new, event_date=str(event.get('date') or ''),
                    event_time=str(event.get('time') or ''), venue=str(event.get('venue') or '')))
                result['emailed'] += int(sent)
            if website and (moved or not was.get('website')):
                result['noticed'] += int(services_hackathon.notify(
                    db, ev, reg, f"Your room: {new}", f"{title}: your team is in {new}.",
                    link='/participant/dashboard', kind='room') > 0)
            told[rid] = {'room': new, 'website': bool(website),
                         'email': sent or (bool(was.get('email')) and not moved)}
        elif was.get('room') and rid in active_ids:
            message = (f"{title}: your team's room ({was['room']}) has been withdrawn. "
                       f"The organisers will tell you where to go.")
            if website or was.get('website'):
                services_hackathon.notify(db, ev, reg, "Your room has changed", message,
                                          link='/participant/dashboard', kind='room')
            if (email or was.get('email')) and reg.get('lead_email'):
                utils_email.send_broadcast_email([reg['lead_email']], f"Room withdrawn — {title}", message, title)
            result['withdrawn'] += 1
            told.pop(rid, None)
        else:
            told.pop(rid, None)
    p.update(final=final, told=told, final_at=_now(), final_by=by, email=bool(email), website=bool(website))
    _save(db, event_id, event, p)
    return result
