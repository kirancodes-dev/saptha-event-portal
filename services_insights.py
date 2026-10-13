"""
services_insights.py — the figures behind the analytics pages (UPG-83).

`build()` takes plain event and registration dicts (already scoped to what the
viewer may see) and returns everything the Super Admin and SPOC analytics pages
draw: headline figures with the previous period beside them, one row per event
for the comparison chart and table, the registrations trend, a weekday × hour
heatmap, the funnel, categories, participant types and no-shows.

Every figure is counted from the registrations themselves, never from the
cached `registration_count` on an event (UPG-81).
"""
import collections
import datetime
from typing import Optional

PERIODS = {'7': 7, '30': 30, '90': 90, '365': 365, 'all': None}
PERIOD_LABELS = {'7': 'Last 7 days', '30': 'Last 30 days', '90': 'Last 90 days',
                 '365': 'Last 12 months', 'all': 'All time'}
# Statuses in which an event is visible and running (UPG-43 workflow, plus legacy 'active')
LIVE_STATUSES = {'published', 'registration_open', 'registration_closed', 'in_progress', 'evaluation', 'active'}
DONE_STATUSES = {'completed', 'certified'}
WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
PARTICIPANT_LABELS = {'student': 'Students', 'faculty': 'Faculty', 'external': 'External'}


# ── Reading a registration ──────────────────────────────────────────────────

def reg_state(reg: dict) -> str:
    """One of confirmed, pending, waitlisted, cancelled. Case and the newer
    workflow statuses (checked_in, shortlisted, …) are folded in."""
    status = str(reg.get('status') or 'confirmed').strip().lower().replace(' ', '_')
    if status in ('cancelled', 'canceled', 'refunded', 'rejected'):
        return 'cancelled'
    if status == 'waitlisted':
        return 'waitlisted'
    if status in ('pending', 'pending_payment', 'applied'):
        return 'pending'
    return 'confirmed'


def attended(reg: dict) -> bool:
    """Marked present, or checked in at the gate unless later marked absent."""
    if reg.get('attendance') == 'Present':
        return True
    return str(reg.get('status') or '').lower() == 'checked_in' and reg.get('attendance') != 'Absent'


def reg_time(reg: dict) -> Optional[datetime.datetime]:
    """When the registration was made, from `registered_at` (string or
    datetime) or the row's creation time."""
    for key in ('registered_at', 'registeredAt', 'created_at', 'createdAt'):
        raw = reg.get(key)
        if not raw:
            continue
        if isinstance(raw, datetime.datetime):
            return raw.replace(tzinfo=None)
        if isinstance(raw, datetime.date):
            return datetime.datetime.combine(raw, datetime.time())
        text = str(raw).strip().replace('T', ' ')
        for fmt, width in (('%Y-%m-%d %H:%M:%S', 19), ('%Y-%m-%d %H:%M', 16), ('%Y-%m-%d', 10)):
            try:
                return datetime.datetime.strptime(text[:width], fmt)
            except ValueError:
                continue
    return None


def paid_amount(reg: dict) -> float:
    if str(reg.get('payment_status') or reg.get('paymentStatus') or '').lower() == 'refunded':
        return 0.0
    try:
        return max(float(reg.get('amount_paid') or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _event_id(reg: dict) -> str:
    return str(reg.get('event_id') or reg.get('eventId') or '')


def _pct(part, whole) -> Optional[float]:
    return round(part * 100 / whole, 1) if whole else None


def _delta(cur, prev) -> Optional[float]:
    """Percentage change against the previous period; None when there's nothing to compare."""
    if prev in (None, 0):
        return None
    return round((cur - prev) * 100 / prev, 1)


# ── Building the page ──────────────────────────────────────────────────────

def build(events: list, regs: list, *, period: str = '30', category: str = '',
          today: Optional[datetime.date] = None) -> dict:
    """Everything the analytics page shows. `events` carry an `id`;
    `regs` are registration dicts with `event_id`."""
    today = today or datetime.date.today()
    period = period if period in PERIODS else '30'
    days = PERIODS[period]

    all_categories = sorted({str(e.get('category') or 'Other') for e in events})
    # Colour follows the category: the four with the most registrations overall
    # (not just this period or filter) keep a colour; the rest are "Other"
    ev_cat = {str(e['id']): str(e.get('category') or 'Other') for e in events}
    cat_totals = collections.Counter(ev_cat.get(_event_id(r), '') for r in regs if _event_id(r) in ev_cat)
    colour_categories = sorted(c for c, _ in cat_totals.most_common(4))
    if category:
        events = [e for e in events if str(e.get('category') or 'Other') == category]
    by_id = {str(e['id']): e for e in events}
    regs = [r for r in regs if _event_id(r) in by_id]

    def in_window(r, lo, hi):
        t = reg_time(r)
        return t is not None and lo <= t.date() <= hi

    start: Optional[datetime.date] = None
    prev: Optional[list] = None
    if days:
        start = today - datetime.timedelta(days=days - 1)
        prev_start = start - datetime.timedelta(days=days)
        cur = [r for r in regs if in_window(r, start, today)]
        prev = [r for r in regs if in_window(r, prev_start, start - datetime.timedelta(days=1))]
    else:
        cur = list(regs)

    # ── One row per event ──
    rows = []
    per_event = collections.defaultdict(list)
    for r in cur:
        per_event[_event_id(r)].append(r)
    for eid, ev in by_id.items():
        er = per_event.get(eid, [])
        date = str(ev.get('date') or '')[:10]
        in_period = bool(er) or start is None or (bool(date) and start.isoformat() <= date <= today.isoformat())
        if not in_period:
            continue
        states = collections.Counter(reg_state(r) for r in er)
        att = sum(1 for r in er if attended(r))
        confirmed = states['confirmed']
        held = date and date <= today.isoformat()
        capacity = 0
        for key in ('capacity', 'max_participants'):
            try:
                capacity = capacity or int(ev.get(key) or (ev.get('limits') or {}).get(key) or 0)
            except (TypeError, ValueError):
                pass
        rows.append({
            'id': eid,
            'title': ev.get('title') or 'Untitled event',
            'category': str(ev.get('category') or 'Other'),
            'status': str(ev.get('status') or ''),
            'date': date,
            'registered': len(er),
            'confirmed': confirmed,
            'waitlisted': states['waitlisted'],
            'pending': states['pending'],
            'cancelled': states['cancelled'],
            'attended': att,
            'no_show': max(confirmed - att, 0) if held else 0,
            # Confirmed for an event that hasn't happened yet: with attended, no-show
            # and other (waitlisted, pending, cancelled) these add up to `registered`
            'upcoming': 0 if held else max(confirmed - att, 0),
            'other': states['waitlisted'] + states['pending'] + states['cancelled'],
            'attendance_rate': _pct(att, confirmed) if held else None,
            'revenue': round(sum(paid_amount(r) for r in er), 2),
            'capacity': capacity,
            'fill_rate': _pct(len(er) - states['cancelled'], capacity) if capacity else None,
        })
    rows.sort(key=lambda x: (-x['registered'], x['title'].lower()))

    # ── Headline figures ──
    def totals(rs: list) -> dict:
        confirmed = sum(1 for r in rs if reg_state(r) == 'confirmed')
        return {'registrations': len(rs), 'confirmed': confirmed,
                'attended': sum(1 for r in rs if attended(r)),
                'revenue': round(sum(paid_amount(r) for r in rs), 2),
                'paid': sum(1 for r in rs if paid_amount(r) > 0)}
    now = totals(cur)
    before = totals(prev) if prev is not None else None
    held_rows = [x for x in rows if x['attendance_rate'] is not None]
    held_confirmed = sum(x['confirmed'] for x in held_rows)
    kpis = {
        'registrations': now['registrations'],
        'registrations_delta': _delta(now['registrations'], before and before['registrations']),
        'revenue': now['revenue'],
        'revenue_delta': _delta(now['revenue'], before and before['revenue']),
        'paid': now['paid'],
        'attended': now['attended'],
        'attendance_rate': _pct(sum(x['attended'] for x in held_rows), held_confirmed),
        'live_events': sum(1 for e in events if str(e.get('status') or '') in LIVE_STATUSES),
        'events': len(events),
        'events_in_period': len(rows),
        'compared': before is not None,
    }

    # ── Trend: daily, or weekly when the span is long ──
    times = sorted(t for t in (reg_time(r) for r in cur) if t)
    first = start or (times[0].date() if times else today)
    span = (today - first).days + 1
    weekly = span > 120
    buckets = collections.OrderedDict()
    day = first
    while day <= today:
        key = (day - datetime.timedelta(days=day.weekday())) if weekly else day
        buckets.setdefault(key.isoformat(), 0)
        day += datetime.timedelta(days=1)
    cats_in_period = sorted({x['category'] for x in rows})
    by_cat = {c: dict.fromkeys(buckets, 0) for c in cats_in_period}
    for r in cur:
        t = reg_time(r)
        if not t:
            continue
        d = t.date()
        key = ((d - datetime.timedelta(days=d.weekday())) if weekly else d).isoformat()
        if key in buckets:
            buckets[key] += 1
            cat = str(by_id[_event_id(r)].get('category') or 'Other')
            if cat in by_cat:
                by_cat[cat][key] += 1
    trend = {'labels': list(buckets), 'total': list(buckets.values()), 'weekly': weekly,
             'by_category': [{'name': c, 'data': list(v.values())} for c, v in by_cat.items()]}

    # ── Weekday × hour ──
    heat = collections.Counter()
    for r in cur:
        t = reg_time(r)
        if t and (t.hour or t.minute or t.second):     # date-only values carry no hour
            heat[(t.weekday(), t.hour)] += 1
    heatmap = [[h, d, heat[(d, h)]] for d in range(7) for h in range(24)]

    # ── Funnel ──
    certified = sum(1 for r in cur if r.get('certificate_id') or (
        attended(r) and str(by_id[_event_id(r)].get('status') or '') in DONE_STATUSES))
    funnel = [
        {'stage': 'Registered', 'value': now['registrations']},
        {'stage': 'Confirmed', 'value': now['confirmed']},
        {'stage': 'Attended', 'value': now['attended']},
        {'stage': 'Certified', 'value': certified},
    ]

    # ── Categories and participant types ──
    categories = []
    for c in cats_in_period:
        cr = [x for x in rows if x['category'] == c]
        categories.append({'name': c, 'events': len(cr), 'registrations': sum(x['registered'] for x in cr),
                           'attended': sum(x['attended'] for x in cr), 'revenue': sum(x['revenue'] for x in cr)})
    categories.sort(key=lambda x: -x['registrations'])
    ptypes = collections.Counter(str(r.get('participant_type') or 'student').lower() for r in cur)
    ptype_present = collections.Counter(str(r.get('participant_type') or 'student').lower() for r in cur if attended(r))
    participants = [{'type': PARTICIPANT_LABELS.get(t, t.title()), 'registered': n, 'attended': ptype_present[t]}
                    for t, n in ptypes.most_common()]

    no_shows = sorted((x for x in held_rows if x['confirmed']),
                      key=lambda x: (-(100 - (x['attendance_rate'] or 0)), x['title'].lower()))

    return {
        'period': period, 'period_label': PERIOD_LABELS[period], 'category': category,
        'categories_available': all_categories, 'colour_categories': colour_categories,
        'range': {'start': start.isoformat() if start else (times[0].date().isoformat() if times else ''),
                  'end': today.isoformat()},
        'kpis': kpis, 'events': rows, 'trend': trend, 'heatmap': heatmap, 'weekdays': WEEKDAYS,
        'funnel': funnel, 'categories': categories, 'participants': participants,
        'no_shows': [{'title': x['title'], 'id': x['id'], 'confirmed': x['confirmed'], 'attended': x['attended'],
                      'no_show': x['no_show'], 'rate': round(100 - x['attendance_rate'], 1)} for x in no_shows],
    }
