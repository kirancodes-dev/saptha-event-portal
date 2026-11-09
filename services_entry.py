"""
services_entry.py — UPG-214: the SPOC quietly chooses which registered teams
may attend.

Registering doesn't mean entry. With the event's switch on (`entry_selection`),
only the teams the SPOC ticked (`entry_selected` on the registration) get in;
every check-in path asks may_enter(). Nobody is told: no notice, email or push
on selecting or unselecting, and the team's own pages don't change. Teams that
can't come in are left out of later reminders and blasts (left_out()).

A team already checked in stays in (it can't be unselected); a team out of the
competition (eliminated in a round) can't come in while the switch is on.
"""
import datetime

SWITCH = 'entry_selection'      # event: only selected teams may enter
LIMIT = 'entry_hall_limit'      # event: seats in the hall (0 = no limit), a warning only
FIELD = 'entry_selected'        # registration: the SPOC ticked it
REFUSED_FIELD = 'entry_refused'  # registration: refused attempts at the door

# Staff screens; neutral, in case the student sees the phone
REFUSED = "Not on the entry list – no entry."
# What a student sees at self check-in
SEE_DESK = "Please see the registration desk."


def on(event) -> bool:
    return bool((event or {}).get(SWITCH))


def hall_limit(event) -> int:
    try:
        return max(int((event or {}).get(LIMIT) or 0), 0)
    except (TypeError, ValueError):
        return 0


def inactive(reg) -> bool:
    return str((reg or {}).get('status') or '').strip().lower() in ('cancelled', 'refunded')


def checked_in(reg) -> bool:
    """In already: the team, any member, or any attendance day."""
    reg = reg or {}
    if str(reg.get('attendance') or '').strip().lower() == 'present' or reg.get('attendance_days'):
        return True
    return any(str(m.get('attendance') or '').strip().lower() == 'present'
               for m in reg.get('members') or [] if isinstance(m, dict))


def selected(reg) -> bool:
    return bool((reg or {}).get(FIELD))


def may_enter(event, reg) -> bool:
    """Whether the entry list lets this registration in. Always true with the
    switch off; cancellation and payment are checked elsewhere."""
    if not on(event) or checked_in(reg):
        return True
    return selected(reg) and not (reg or {}).get('is_eliminated')


def left_out(event, reg) -> bool:
    """Not to be sent the event's reminders and blasts: it can't come in."""
    return not may_enter(event, reg)


def _regs(db, event_id):
    return [(d.id, d.to_dict() or {}) for d in
            db.collection('registrations').where('event_id', '==', event_id).stream()]


def counts(db, event_id, event, regs=None) -> dict:
    """Active registrations: selected (may enter), not selected, checked in,
    refused attempts at the door; the hall limit and whether it's passed."""
    regs = _regs(db, event_id) if regs is None else regs
    active = [r for _, r in regs if not inactive(r)]
    allowed = sum(1 for r in active if may_enter(dict(event or {}, **{SWITCH: True}), r))
    limit = hall_limit(event)
    return {'on': on(event), 'selected': allowed, 'not_selected': len(active) - allowed,
            'checked_in': sum(1 for r in active if checked_in(r)),
            'refused': sum(int(r.get(REFUSED_FIELD) or 0) for r in active),
            'limit': limit, 'over': bool(limit) and allowed > limit}


def blocked_ids(db, event_id, event, regs=None) -> list:
    """Registrations the door turns away (both IDs a ticket may carry), for
    the scanner's offline list."""
    if not on(event):
        return []
    regs = _regs(db, event_id) if regs is None else regs
    out = []
    for rid, r in regs:
        if not inactive(r) and not may_enter(event, r):
            out.extend({str(rid), str(r.get('reg_id') or rid)})
    return sorted(set(out))


def note_refused(db, reg_id, reg) -> None:
    try:
        db.collection('registrations').document(reg_id).update(
            {REFUSED_FIELD: int((reg or {}).get(REFUSED_FIELD) or 0) + 1})
    except Exception:
        pass


def set_selected(db, regs, value: bool, actor: str) -> dict:
    """Tick or untick these registrations (pairs of id and data, already of
    this event). Cancelled ones are skipped; a checked-in team can't be
    unticked; an eliminated one can't be ticked. Sends nothing to anyone."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out = {'changed': 0, 'kept_in': 0, 'eliminated': 0, 'paid_out': 0}
    for rid, r in regs:
        if inactive(r):
            continue
        if not value and checked_in(r):
            out['kept_in'] += 1
            continue
        if value and r.get('is_eliminated'):
            out['eliminated'] += 1
            continue
        if selected(r) == value:
            continue
        db.collection('registrations').document(rid).update(
            {FIELD: value, 'entry_selected_by': actor, 'entry_selected_at': now})
        out['changed'] += 1
        if not value and str(r.get('payment_status') or r.get('paymentStatus') or '').strip().lower() \
                in ('paid', 'completed'):
            out['paid_out'] += 1
    return out


def match_csv(text: str, regs) -> tuple:
    """The registrations a CSV names, by team name, lead or member email, or
    registration ID in any cell of a row; and the rows that matched nothing
    (their first cell). A header row is skipped."""
    import csv
    import io
    keys = {}
    for rid, r in regs:
        for k in [rid, r.get('reg_id'), r.get('team_name'), r.get('lead_email')] + \
                 [m.get('email') for m in r.get('members') or [] if isinstance(m, dict)]:
            if k and str(k).strip():
                keys.setdefault(str(k).strip().lower(), (rid, r))
    found, missed = {}, []
    header = {'team', 'team name', 'email', 'lead email', 'reg id', 'registration id', 'ticket id', 'name'}
    for row in csv.reader(io.StringIO(text or '')):
        cells = [c.strip() for c in row if c.strip()]
        if not cells:
            continue
        hits = [keys[c.lower()] for c in cells if c.lower() in keys]
        for rid, r in hits:
            found[rid] = (rid, r)
        if not hits and not any(c.lower() in header for c in cells):
            missed.append(cells[0])
    return list(found.values()), missed
