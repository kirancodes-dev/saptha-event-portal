"""
services_summary.py — the event summary report (UPG-273): one row per event
with its registrations, attendance and no-shows, results, feedback and
certificates, for a range of event dates.

Every figure is counted from the records themselves when the report is opened:
the registration documents, the feedback responses and the certificate
register. Nothing is read from a cached count, so a figure here is the number
of records the organiser's own lists show for that event. `DEFINITIONS` says
what each column counts; the page and the Excel file carry it with the
figures.

Payments are not in this report (they have their own pages).

A registration is one sign-up: a team is one registration, whatever its size.
"""
import collections
import datetime
from typing import Dict, List, Optional, Tuple

import services_entry
from services_insights import attended, reg_state
from services_registration_state import today as ist_today

# (key, heading, what it counts)
DEFINITIONS: List[Tuple[str, str, str]] = [
    ('registrations', 'Registrations',
     "Every registration record for the event, whatever its status. A team is one registration. "
     "Registrations = Confirmed + Waitlisted + Pending + Cancelled."),
    ('confirmed', 'Confirmed',
     "Registrations that hold a seat: not on the waitlist, not waiting for approval or payment, and not "
     "cancelled. Those checked in at the gate are confirmed."),
    ('waitlisted', 'Waitlisted', "Registrations waiting for a seat."),
    ('pending', 'Pending', "Registrations waiting for the organiser's approval or for payment."),
    ('cancelled', 'Cancelled', "Registrations cancelled, rejected or refunded."),
    ('attended', 'Attended',
     "Confirmed registrations marked present: scanned in at the gate, or marked present by the organiser."),
    ('not_selected', 'Not on the entry list',
     "Confirmed registrations the organiser left off the entry list (for example after shortlisting) and "
     "that were not marked present. They were not expected, so they are not no-shows."),
    ('no_shows', 'No-shows',
     "Confirmed registrations on the entry list that were not marked present. Counted only after the "
     "event's last day; blank until then. For a finished event, Confirmed = Attended + No-shows + Not on "
     "the entry list."),
    ('attendance_rate', 'Attendance rate',
     "Attended ÷ (Attended + No-shows), as a percentage. Finished events only; in the total row, over the "
     "finished events."),
    ('results', 'Results published', "Whether the organiser has published the event's results. In the total row, "
     "the number of events with published results."),
    ('placed', 'Placed 1st to 3rd',
     "Registrations placed first to third on the published results (more than three when a place is "
     "shared). 0 until the results are published."),
    ('feedback', 'Feedback responses', "Feedback forms submitted for the event, one for each person who answered."),
    ('rating', 'Average rating',
     "The mean of the 1 to 5 ratings on those responses. Blank when there are none. In the total row, the "
     "mean over every response counted."),
    ('certificates', 'Certificates issued',
     "Certificates issued for the event that are valid now. Revoked certificates, and versions replaced by "
     "a correction, are not counted."),
]
COUNTED = ('registrations', 'confirmed', 'waitlisted', 'pending', 'cancelled', 'attended', 'not_selected',
           'no_shows', 'placed', 'feedback', 'certificates')
HEADINGS = {key: heading for key, heading, _ in DEFINITIONS}


def _day(value) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(value or '').strip()[:10])
    except ValueError:
        return None


def read_filters(args) -> dict:
    """The filters from a query string, with what is wrong with them."""
    problems = []
    raw_from, raw_to = str(args.get('from') or '').strip(), str(args.get('to') or '').strip()
    date_from, date_to = _day(raw_from), _day(raw_to)
    if raw_from and not date_from:
        problems.append(f"“{raw_from}” isn't a date; the From date was ignored.")
    if raw_to and not date_to:
        problems.append(f"“{raw_to}” isn't a date; the To date was ignored.")
    if date_from and date_to and date_from > date_to:
        problems.append("The From date is after the To date, so they were swapped.")
        date_from, date_to = date_to, date_from
    return {'from': date_from, 'to': date_to, 'category': str(args.get('category') or '').strip(),
            'event': str(args.get('event') or '').strip(), 'problems': problems}


def describe(filters: dict) -> str:
    """The filters in words, for the page and the files."""
    def long(day):
        return f"{day.day} {day.strftime('%B %Y')}"
    if filters['from'] and filters['to']:
        when = f"Events from {long(filters['from'])} to {long(filters['to'])}"
    elif filters['from']:
        when = f"Events on or after {long(filters['from'])}"
    elif filters['to']:
        when = f"Events on or before {long(filters['to'])}"
    else:
        when = "Events on any date"
    return when + (f", category {filters['category']}" if filters['category'] else '') + \
        (", one event" if filters['event'] else '') + ". Dates are the day each event starts."


def _feedback(responses: List[dict], regs: List[Tuple[str, dict]]) -> Dict[str, List[dict]]:
    """Responses by event: one per person, plus a response kept only on a
    registration from before each person had their own (the rule of
    routes_feedback.event_responses)."""
    by_event = collections.defaultdict(list)
    answered = set()
    for r in responses:
        event_id = str(r.get('event_id') or '')
        by_event[event_id].append(r)
        answered.add((event_id, r.get('reg_id'), str(r.get('email') or '').lower()))
    for reg_id, reg in regs:
        fb = reg.get('feedback')
        event_id = str(reg.get('event_id') or '')
        lead = str(reg.get('lead_email') or '').lower()
        if fb and (event_id, reg.get('reg_id') or reg_id, lead) not in answered and (event_id, reg_id, lead) not in answered:
            by_event[event_id].append(fb if isinstance(fb, dict) else {})
    return by_event


def _certificates() -> Dict[str, int]:
    """Valid current certificates per event, from the certificate register."""
    from sqlalchemy import func, select
    from models_pg import Certificate
    from services_certificates import _session
    with _session() as s:
        q = (select(Certificate.event_id, func.count()).where(Certificate.is_current.is_(True), Certificate.status == 'valid')
             .group_by(Certificate.event_id))
        return {str(event_id): int(n) for event_id, n in s.execute(q)}


def _rating(responses: List[dict]) -> Tuple[float, int]:
    """(sum, count) of the ratings from 1 to 5."""
    total, count = 0.0, 0
    for r in responses:
        try:
            rating = float(r.get('rating'))
        except (TypeError, ValueError):
            continue
        if 1 <= rating <= 5:
            total, count = total + rating, count + 1
    return total, count


def build(db, events: List[dict], filters: dict, on: Optional[datetime.date] = None) -> dict:
    """The report over `events` (dicts with their `id`, already limited to
    what the viewer may see)."""
    from services_leaderboard import podium, rank
    on = on or ist_today()
    categories = sorted({str(e.get('category') or 'Other') for e in events})
    choices = sorted(((str(e['id']), str(e.get('title') or 'Untitled event'), str(e.get('date') or '')[:10])
                      for e in events), key=lambda c: (c[2], c[1].lower()), reverse=True)

    chosen = []
    for event in events:
        first = _day(event.get('date'))
        if filters['event'] and str(event['id']) != filters['event']:
            continue
        if filters['category'] and str(event.get('category') or 'Other') != filters['category']:
            continue
        if (filters['from'] or filters['to']) and not first:
            continue
        if filters['from'] and first < filters['from']:
            continue
        if filters['to'] and first > filters['to']:
            continue
        chosen.append(event)
    ids = {str(e['id']) for e in chosen}

    regs = collections.defaultdict(list)
    every = []
    for doc in db.collection('registrations').stream():
        reg = doc.to_dict() or {}
        event_id = str(reg.get('event_id') or reg.get('eventId') or '')
        if event_id in ids:
            regs[event_id].append(dict(reg, id=doc.id))
            every.append((doc.id, reg))
    feedback = _feedback([d.to_dict() or {} for d in db.collection('feedback_responses').stream()
                          if str((d.to_dict() or {}).get('event_id') or '') in ids], every) if ids else {}
    certificates = _certificates() if ids else {}

    rows = []
    rating_sum, rating_count = 0.0, 0
    for event in chosen:
        event_id = str(event['id'])
        mine = regs.get(event_id, [])
        states = collections.Counter(reg_state(r) for r in mine)
        confirmed = [r for r in mine if reg_state(r) == 'confirmed']
        present = sum(1 for r in confirmed if attended(r))
        not_selected = sum(1 for r in confirmed if not attended(r) and services_entry.left_out(event, r))
        first, last = _day(event.get('date')), _day(event.get('end_date'))
        last = max([d for d in (first, last) if d], default=None)
        finished = bool(last and last < on)
        no_shows = len(confirmed) - present - not_selected if finished else None
        published = bool(event.get('results_published'))
        total, count = _rating(feedback.get(event_id, []))
        rating_sum, rating_count = rating_sum + total, rating_count + count
        rows.append({
            'id': event_id, 'title': str(event.get('title') or 'Untitled event'),
            'date': first.isoformat() if first else '', 'category': str(event.get('category') or 'Other'),
            'status': str(event.get('status') or ''), 'finished': finished,
            'registrations': len(mine), 'confirmed': len(confirmed), 'waitlisted': states['waitlisted'],
            'pending': states['pending'], 'cancelled': states['cancelled'],
            'attended': present, 'not_selected': not_selected, 'no_shows': no_shows,
            'attendance_rate': _pct(present, present + no_shows) if finished else None,
            'results': published, 'placed': len(podium(rank(mine))) if published else 0,
            'feedback': len(feedback.get(event_id, [])), 'rating': round(total / count, 2) if count else None,
            'certificates': certificates.get(event_id, 0),
        })
    rows.sort(key=lambda r: (r['date'] or '9999', r['title'].lower()))

    totals = {key: sum(r[key] or 0 for r in rows) for key in COUNTED}
    done = [r for r in rows if r['finished']]
    totals.update({
        'events': len(rows), 'finished': len(done),
        'attendance_rate': _pct(sum(r['attended'] for r in done), sum(r['attended'] + r['no_shows'] for r in done)),
        'results': sum(1 for r in rows if r['results']),
        'rating': round(rating_sum / rating_count, 2) if rating_count else None,
    })
    return {'rows': rows, 'totals': totals, 'filters': filters, 'described': describe(filters),
            'categories': categories, 'choices': choices, 'on': on.isoformat(), 'definitions': DEFINITIONS}


def _pct(part, whole) -> Optional[float]:
    return round(part * 100 / whole, 1) if whole else None


# ── Files ───────────────────────────────────────────────────────────────────

COLUMNS = ['Event', 'Date', 'Category', 'Status'] + [heading for _, heading, _ in DEFINITIONS]


def _cells(row: dict) -> list:
    def blank(value):
        return '' if value is None else value
    return [blank(row['registrations']), blank(row['confirmed']), blank(row['waitlisted']), blank(row['pending']),
            blank(row['cancelled']), blank(row['attended']), blank(row['not_selected']), blank(row['no_shows']),
            blank(row['attendance_rate'])]


def table(report: dict) -> List[list]:
    """The report as rows for a file: one per event, then the total."""
    out = []
    for r in report['rows']:
        out.append([r['title'], r['date'], r['category'], r['status']] + _cells(r)
                   + ['Yes' if r['results'] else 'No', r['placed'], r['feedback'],
                      '' if r['rating'] is None else r['rating'], r['certificates']])
    t = report['totals']
    out.append([f"Total ({t['events']} event{'' if t['events'] == 1 else 's'})", '', '', ''] + _cells(t)
               + [t['results'], t['placed'], t['feedback'], '' if t['rating'] is None else t['rating'], t['certificates']])
    return out


def definitions_table(report: dict) -> List[list]:
    return [['This report', report['described'] + f" Counted on {report['on']}."]] + \
           [[heading, text] for _, heading, text in DEFINITIONS]
