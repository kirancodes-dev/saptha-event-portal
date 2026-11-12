"""
services_waitlist.py — a waitlist's order and each person's place in it (UPG-114).

The order is the order people joined (`joined_at`, then the entry's id when two
joined in the same instant). A person's place is worked out when it's shown:
one more than the number of people still waiting who joined earlier. So places
never repeat, and they close up when someone ahead is promoted or leaves. The
`position` stored on an entry is only its place on the day it joined.
"""


# ── Moving up on their own, or only when the SPOC accepts (UPG-243) ─────────
AUTO = 'waitlist_auto'


def auto_moves_up(event: dict) -> bool:
    """Does a freed seat go to the first in line on its own? On unless the
    event's SPOC switched it off; then only the SPOC's Accept registers
    someone from the waitlist."""
    return (event or {}).get(AUTO) is not False


def someone_waiting(db, event_id: str) -> bool:
    query = db.collection('waitlists').where('event_id', '==', str(event_id)).where('status', '==', 'waiting')
    return any(True for _ in query.limit(1).stream())


def joins_waitlist(db, event_id: str, event: dict, count: int, limit: int) -> bool:
    """Does a new sign-up go on the waitlist? When the event is full, and also
    while teams wait for the SPOC to accept them (moving up on their own is
    off), so a newcomer can't take a freed seat ahead of them."""
    if limit and count >= limit:
        return True
    return bool(limit) and not auto_moves_up(event) and someone_waiting(db, event_id)


def waiting(db, event_id: str) -> list:
    """[(entry id, entry)] still waiting for the event, first in line first."""
    query = db.collection('waitlists').where('event_id', '==', event_id).where('status', '==', 'waiting')
    entries = [(d.id, d.to_dict() or {}) for d in query.stream()]
    return sorted(entries, key=lambda e: (str(e[1].get('joined_at') or ''), str(e[0])))


def place_in_line(db, event_id: str, email: str):
    """This person's place (1 = next to be promoted), or None if they aren't waiting."""
    email = (email or '').strip().lower()
    for place, (_, entry) in enumerate(waiting(db, event_id), start=1):
        if str(entry.get('user_email') or entry.get('email') or '').strip().lower() == email:
            return place
    return None


# ── Where a person stands (UPG-236) ─────────────────────────────────────────
# What each state means to the person, for their dashboard and My events.
STANDING = {
    'waiting': 'Waiting for a seat',
    'pay': 'Accepted: pay to confirm',
    'accepted': 'Accepted: registered',
    'already': 'Already registered',
    'left': 'Left the waitlist',
    'closed': 'No longer waiting',
}


def _norm(value) -> str:
    return str(value or '').strip().lower()


def _members_of(entry: dict) -> list:
    reg = entry.get('reg_data') if isinstance(entry.get('reg_data'), dict) else {}
    return [m for m in reg.get('members') or [] if isinstance(m, dict)]


def _registration(db, event_id: str, lead: str):
    """The registration a promotion made for this lead (not a cancelled one), or None."""
    found = [d.to_dict() or {} for d in db.collection('registrations')
             .where('event_id', '==', event_id).where('lead_email', '==', lead).stream()]
    live = [r for r in found if _norm(r.get('status')) not in ('cancelled', 'refunded')]
    return (live or found or [None])[0]


def standing(db, email: str) -> list:
    """Every waitlist entry this person is on, as the one who joined or as a
    member of the team that joined, with where it stands now: still waiting
    (their place, how many are ahead), accepted (registered, or a link to pay
    first), already registered, left, or no longer waiting. Waiting first,
    then the newest."""
    email = _norm(email)
    if not email:
        return []
    entries = {}
    for field in ('user_email', 'email'):
        for d in db.collection('waitlists').where(field, '==', email).stream():
            entries[d.id] = d.to_dict() or {}
    # A team member is named only in the team's form answers
    for d in db.collection('waitlists').where('status', 'in', ['waiting', 'promoted']).stream():
        entry = d.to_dict() or {}
        if d.id not in entries and any(_norm(m.get('email')) == email for m in _members_of(entry)):
            entries[d.id] = entry

    lines, events, rows = {}, {}, []
    for wl_id, entry in entries.items():
        event_id = str(entry.get('event_id') or '')
        if not event_id:
            continue
        if event_id not in events:
            doc = db.collection('events').document(event_id).get()
            events[event_id] = (doc.to_dict() or {}) if doc.exists else None
        event = events[event_id]
        if event is None:
            continue
        lead = _norm(entry.get('user_email') or entry.get('email'))
        reg_data = entry.get('reg_data') if isinstance(entry.get('reg_data'), dict) else {}
        from utils import venue_label
        row = {
            'id': wl_id, 'event_id': event_id,
            'event_title': event.get('title') or entry.get('event_title') or 'Event',
            'event_date': event.get('date') or '', 'venue': venue_label(event),
            'team_name': reg_data.get('team_name') or '',
            'lead_name': reg_data.get('lead_name') or entry.get('name') or '',
            'is_lead': lead == email, 'joined_at': str(entry.get('joined_at') or ''),
            'place': None, 'ahead': None, 'waiting_total': None, 'link': '', 'link_label': '',
            'auto': auto_moves_up(event),
        }
        status = _norm(entry.get('status'))
        if status == 'waiting':
            if event_id not in lines:
                lines[event_id] = [e for e, _ in waiting(db, event_id)]
            line = lines[event_id]
            place = line.index(wl_id) + 1 if wl_id in line else None
            row.update(state='waiting', place=place, ahead=(place - 1) if place else None,
                       waiting_total=len(line), link=f'/event/{event_id}', link_label='See the event')
        elif status == 'promoted':
            reg = _registration(db, event_id, lead)
            if reg is None:   # the organiser deleted the team: gone from this event (UPG-245)
                continue
            if _norm(reg.get('status')) == 'pending_payment':
                row['state'] = 'pay'
                if row['is_lead']:
                    row.update(link=f"/payment/pay/{reg.get('reg_id')}", link_label='Pay to confirm your seat')
            else:
                row.update(state='accepted', link='/participant/my_events?tab=registered',
                           link_label='See your registration')
            row['accepted_at'] = str(entry.get('promoted_at') or '')
        elif status == 'already_registered':
            row.update(state='already', link='/participant/my_events?tab=registered',
                       link_label='See your registration')
        elif status == 'cancelled':
            row['state'] = 'left'
        elif status == 'removed':   # deleted by the organiser (UPG-245)
            continue
        else:
            row['state'] = 'closed'
        row['label'] = STANDING[row['state']]
        rows.append(row)
    rows.sort(key=lambda r: r['joined_at'], reverse=True)
    rows.sort(key=lambda r: r['state'] != 'waiting')
    return rows
