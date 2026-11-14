"""
services_registration_filters.py — the SPOC's registrations list: filters
that combine, and a sort (UPG-264).

Each filter is one URL argument; an unknown or empty value means "all", so a
link to the list with no arguments shows everything, newest first, as before.
The quick links above the list (entry, pay, members) are the same arguments,
so they keep working on their own and inside the combined form.

    status   active · pending_payment · cancelled
    members  unconfirmed · all_confirmed · no_email · late
    checkin  in · out
    size     below_min · room · full
    entry    selected · not_selected
    pay      paid · unpaid
    sort     newest (default) · oldest · team · lead · most · fewest · waiting
"""
from typing import Callable, Dict, List, Optional, Tuple

CANCELLED = ('cancelled', 'refunded')

# (argument, [(value, label)]) in the order the form shows them
STATUS = [('active', 'Registered (active)'), ('pending_payment', 'Waiting for payment'),
          ('cancelled', 'Cancelled')]
MEMBERS = [('unconfirmed', 'A member not confirmed'), ('all_confirmed', 'Everyone confirmed'),
           ('no_email', 'A member with no email'), ('late', 'Added during window')]
CHECKIN = [('in', 'Checked in'), ('out', 'Not checked in')]
SIZE = [('below_min', 'Below the minimum size'), ('room', 'Has room for more'), ('full', 'Full')]
ENTRY = [('selected', 'On the entry list'), ('not_selected', 'Not on the entry list')]
PAY = [('paid', 'Paid'), ('unpaid', 'Not paid')]
SORTS = [('newest', 'Newest first'), ('oldest', 'Oldest first'), ('team', 'Team name A–Z'),
         ('lead', 'Lead name A–Z'), ('most', 'Most members'), ('fewest', 'Fewest members'),
         ('waiting', 'Most members not confirmed')]

KEYS = ('status', 'members', 'checkin', 'size', 'entry', 'pay')


def _status(reg: dict) -> str:
    return str(reg.get('status') or '').strip().lower()


def _people(reg: dict) -> list:
    return [m for m in reg.get('members') or [] if isinstance(m, dict)]


def size(reg: dict) -> int:
    """People on the team, the lead included (1 for a registration without members)."""
    return len(_people(reg)) or 1


def _others(reg: dict) -> list:
    import services_team_confirm as confirm
    return [m for m in _people(reg) if not confirm.is_lead(reg, m)]


def not_confirmed(reg: dict) -> int:
    """Members, the lead aside, who haven't confirmed: a member with no email counts."""
    return sum(1 for m in _others(reg) if not m.get('confirmed_at'))


def _no_email(reg: dict) -> bool:
    import services_team_confirm as confirm
    return any(not confirm._email(m) for m in _others(reg))


def choices(member_confirm: bool, team_event: bool, any_late: bool) -> Dict[str, list]:
    """The options the page offers for this event: no member or size filters
    without teams, no confirmation filters when it's off."""
    members = [(v, n) for v, n in MEMBERS
               if (v != 'late' or any_late) and (member_confirm or v not in ('unconfirmed', 'all_confirmed'))]
    return {
        'status': STATUS,
        'members': members if team_event else [],
        'checkin': CHECKIN,
        'size': SIZE if team_event else [],
        'entry': ENTRY,
        'pay': PAY,
        'sort': [(v, n) for v, n in SORTS if team_event or v not in ('most', 'fewest', 'waiting')],
    }


def chosen(args) -> Dict[str, str]:
    """The filters and sort in the request, only known values kept."""
    known = {'status': STATUS, 'members': MEMBERS, 'checkin': CHECKIN, 'size': SIZE, 'entry': ENTRY,
             'pay': PAY, 'sort': SORTS}
    out = {}
    for key, options in known.items():
        value = str(args.get(key) or '').strip()
        if value in {v for v, _ in options}:
            out[key] = value
    if out.get('sort') == 'newest':
        out.pop('sort')
    return out


def apply(regs: List[dict], picked: Dict[str, str], event: dict, on_list: Callable[[dict], Optional[bool]],
          checked_in: Callable[[dict], bool]) -> List[dict]:
    """The registrations that pass every chosen filter, in the chosen order.
    `on_list(reg)`: on the entry list (None for a team the list ignores, a
    cancelled one); `checked_in(reg)`: checked in."""
    import services_team_confirm as confirm
    from routes_forms import team_limits
    lo, hi = team_limits(event)
    tests: List[Tuple[str, Callable[[dict], bool]]] = [
        ('status', {
            'active': lambda r: confirm.active(r),
            'pending_payment': lambda r: _status(r) in ('pending_payment', 'pending payment'),
            'cancelled': lambda r: _status(r) in CANCELLED,
        }.get(picked.get('status', ''))),
        ('members', {
            'unconfirmed': lambda r: confirm.active(r) and any(
                st['key'] != 'confirmed' for _, st in confirm.summary(r)),
            'all_confirmed': lambda r: confirm.active(r) and not not_confirmed(r),
            'no_email': _no_email,
            'late': lambda r: any(m.get('late') for m in _people(r)),
        }.get(picked.get('members', ''))),
        ('checkin', {
            'in': checked_in,
            'out': lambda r: not checked_in(r),
        }.get(picked.get('checkin', ''))),
        ('size', {
            'below_min': lambda r: size(r) < lo,
            'room': lambda r: size(r) < hi,
            'full': lambda r: size(r) >= hi,
        }.get(picked.get('size', ''))),
        ('entry', {
            'selected': lambda r: on_list(r) is True,
            'not_selected': lambda r: on_list(r) is False,
        }.get(picked.get('entry', ''))),
        ('pay', {
            'paid': lambda r: str(r.get('payment_status') or '').strip().lower() in ('paid', 'completed'),
            'unpaid': lambda r: str(r.get('payment_status') or '').strip().lower() not in ('paid', 'completed'),
        }.get(picked.get('pay', ''))),
    ]
    shown = [r for r in regs if all(test(r) for _, test in tests if test)]
    return sort(shown, picked.get('sort', 'newest'))


def _name(value) -> str:
    return str(value or '').strip().casefold()


def sort(regs: List[dict], how: str) -> List[dict]:
    """Newest first unless told otherwise; ties keep the newest first."""
    newest = sorted(regs, key=lambda r: str(r.get('registered_at') or ''), reverse=True)
    if how == 'oldest':
        return list(reversed(newest))
    keys = {
        'team': lambda r: (not _name(r.get('team_name')), _name(r.get('team_name'))),
        'lead': lambda r: _name(r.get('lead_name') or r.get('name')),
        'most': lambda r: -size(r),
        'fewest': lambda r: size(r),
        'waiting': lambda r: -not_confirmed(r),
    }
    key = keys.get(how)
    return sorted(newest, key=key) if key else newest
