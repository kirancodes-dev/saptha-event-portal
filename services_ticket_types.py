"""
services_ticket_types.py — ticket types: early-bird windows, a seat limit per
type and team or per-head prices (UPG-155).

An event's ``ticket_types`` (set in the wizard) is a list of:

    {'id', 'name', 'price', 'sale_start', 'sale_end', 'seats', 'who', 'per'}

  * ``sale_start`` / ``sale_end`` are dates (YYYY-MM-DD, India time), both
    inclusive; blank means "from now" / "until registration closes".
  * ``seats`` is the most registrations of that type; 0 means no limit.
  * ``who`` lists the participant types that may buy it (student, faculty,
    external); empty means everyone the event allows.
  * ``per`` is 'registration' (one price for the registration, a whole team
    included) or 'person' (price × the team's members).

An event without ticket types is priced by ``services_payments.fee_for`` as
before. The older ``ticket_tiers`` field (filled with defaults by templates
and the AI copilot) is never used for prices.

Seats are counted in ``ticket_type_sales`` and taken with one conditional
UPDATE, so two registrations can't both take the last seat.
"""
import datetime
from typing import List, Optional, Tuple

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

try:
    from zoneinfo import ZoneInfo
    _IST = ZoneInfo('Asia/Kolkata')
except Exception:  # pragma: no cover
    _IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

GROUPS = ('student', 'faculty', 'external')
MAX_TYPES = 10


def today() -> datetime.date:
    """Today in India, where sale dates are set."""
    return datetime.datetime.now(_IST).date()


def _date(value) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(value or '')[:10])
    except ValueError:
        return None


def _num(value, cast=float, default=0):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def types_for(event: dict) -> List[dict]:
    """The event's ticket types, cleaned; [] when it has none."""
    out = []
    for raw in (event or {}).get('ticket_types') or []:
        if not isinstance(raw, dict) or not str(raw.get('id') or '').strip():
            continue
        who = [g for g in (raw.get('who') or []) if g in GROUPS]
        out.append({
            'id': str(raw['id']).strip(),
            'name': str(raw.get('name') or 'Ticket').strip(),
            'price': max(0.0, round(_num(raw.get('price'), float, 0.0), 2)),
            'sale_start': str(raw.get('sale_start') or '')[:10],
            'sale_end': str(raw.get('sale_end') or '')[:10],
            'seats': max(0, _num(raw.get('seats'), int, 0)),
            'who': who,
            'per': 'person' if raw.get('per') == 'person' else 'registration',
        })
    return out


def find(event: dict, type_id: str) -> Optional[dict]:
    type_id = str(type_id or '').strip()
    return next((t for t in types_for(event) if t['id'] == type_id), None)


def on_sale(ticket: dict, day: Optional[datetime.date] = None) -> bool:
    day = day or today()
    start, end = _date(ticket.get('sale_start')), _date(ticket.get('sale_end'))
    return not (start and day < start) and not (end and day > end)


def allowed_for(ticket: dict, participant_type: str) -> bool:
    return not ticket['who'] or (participant_type or 'student') in ticket['who']


def price(ticket: dict, member_count: int = 1) -> float:
    """What a registration with this type costs."""
    count = max(1, int(member_count or 1)) if ticket['per'] == 'person' else 1
    return round(ticket['price'] * count, 2)


# ── Seats ──────────────────────────────────────────────────────────────────

def _key(event_id: str, type_id: str) -> str:
    return f"{event_id}:{type_id}"


def sold(event_id: str, type_id: str) -> int:
    from db_pg import get_session
    from models_pg import TicketTypeSale
    with get_session() as s:
        row = s.get(TicketTypeSale, _key(event_id, type_id))
        return int(row.sold) if row else 0


def seats_left(event_id: str, ticket: dict) -> Optional[int]:
    """Seats still free, or None when the type has no limit."""
    if not ticket['seats']:
        return None
    return max(0, ticket['seats'] - sold(event_id, ticket['id']))


def take_seat(event_id: str, ticket: dict) -> bool:
    """Take one seat of this type if one is free (always, without a limit).
    One conditional UPDATE, so it's race-free."""
    from db_pg import get_session
    from models_pg import TicketTypeSale
    key = _key(event_id, ticket['id'])
    try:
        with get_session() as s:
            if s.get(TicketTypeSale, key) is None:
                s.add(TicketTypeSale(key=key, sold=0))
    except IntegrityError:
        pass  # another registration created it first
    with get_session() as s:
        stmt = update(TicketTypeSale).where(TicketTypeSale.key == key)
        if ticket['seats']:
            stmt = stmt.where(TicketTypeSale.sold < int(ticket['seats']))
        return s.execute(stmt.values(sold=TicketTypeSale.sold + 1)).rowcount == 1


def give_back_seat(event_id: str, type_id: str) -> None:
    """A cancelled registration, or one that couldn't be saved, frees its seat."""
    if not type_id:
        return
    from db_pg import get_session
    from models_pg import TicketTypeSale
    with get_session() as s:
        s.execute(update(TicketTypeSale)
                  .where(TicketTypeSale.key == _key(event_id, type_id), TicketTypeSale.sold > 0)
                  .values(sold=TicketTypeSale.sold - 1))


# ── Choosing a type ────────────────────────────────────────────────────────

def offered(event: dict, event_id: str, participant_type: str = '',
            day: Optional[datetime.date] = None) -> List[dict]:
    """Every type with what the form shows: on sale, for whom and seats left."""
    out = []
    for t in types_for(event):
        left = seats_left(event_id, t)
        out.append(dict(t, on_sale=on_sale(t, day), seats_left=left,
                        sold_out=left == 0, for_you=allowed_for(t, participant_type)))
    return out


def check_choice(event: dict, event_id: str, type_id: str, participant_type: str,
                 day: Optional[datetime.date] = None) -> Tuple[Optional[dict], str]:
    """(ticket, '') when this registrant may buy this type now, else (None, why)."""
    if not types_for(event):
        return None, ''
    ticket = find(event, type_id)
    if ticket is None:
        return None, 'Please choose a ticket type.'
    if not on_sale(ticket, day):
        start = _date(ticket['sale_start'])
        if start and (day or today()) < start:
            return None, f"{ticket['name']} goes on sale on {start.strftime('%d %b %Y')}."
        return None, f"{ticket['name']} is no longer on sale."
    if not allowed_for(ticket, participant_type):
        return None, f"{ticket['name']} isn't available to you; please choose another ticket."
    if seats_left(event_id, ticket) == 0:
        return None, f"{ticket['name']} is sold out; please choose another ticket."
    return ticket, ''


# ── The wizard ─────────────────────────────────────────────────────────────

def from_form(getlist, errors: list) -> List[dict]:
    """Ticket types from the wizard's repeated fields (tt_*); appends messages to errors."""
    import re
    names = getlist('tt_name')
    columns = {k: getlist(f'tt_{k}') for k in ('id', 'price', 'start', 'end', 'seats', 'per', 'who')}
    out, seen = [], set()
    for i, name in enumerate(names):
        def col(k):
            values = columns[k]
            return str(values[i]).strip() if i < len(values) else ''
        name = str(name or '').strip()[:80]
        if not name and not col('price') and not col('seats'):
            continue   # an empty row
        label = name or f'Ticket {i + 1}'
        if not name:
            errors.append(f'Ticket type {i + 1}: give it a name.')
        amount = _num(col('price') or 0, float, None)
        if amount is None or amount < 0:
            errors.append(f'{label}: the price must be 0 or more.')
            amount = 0.0
        seats = _num(col('seats') or 0, int, None)
        if seats is None or seats < 0:
            errors.append(f'{label}: seats must be a whole number, 0 for no limit.')
            seats = 0
        start, end = _date(col('start')), _date(col('end'))
        if col('start') and not start or col('end') and not end:
            errors.append(f'{label}: sale dates must be dates.')
        if start and end and end < start:
            errors.append(f'{label}: the sale ends before it starts.')
        who = [g for g in col('who').split(',') if g in GROUPS]
        type_id = re.sub(r'[^a-z0-9-]', '', col('id').lower())[:40] \
            or re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')[:40] or f't{i + 1}'
        while type_id in seen:
            type_id = f'{type_id}-{i + 1}'
        seen.add(type_id)
        out.append({'id': type_id, 'name': label, 'price': round(amount, 2),
                    'sale_start': start.isoformat() if start else '',
                    'sale_end': end.isoformat() if end else '',
                    'seats': seats, 'who': who,
                    'per': 'person' if col('per') == 'person' else 'registration'})
    if len(out) > MAX_TYPES:
        errors.append(f'An event can have at most {MAX_TYPES} ticket types.')
        out = out[:MAX_TYPES]
    return out
