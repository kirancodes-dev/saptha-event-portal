"""
services_impact.py — SapthaEvent's track record from real data only (UPG-145).

Every figure is a count of records; nothing is estimated, rounded up or
padded, and a figure that can't be counted is left out. Months are those of
the record's own date: an event's last day, a registration's time, a
certificate's issue, a report's submission. The one estimate shown, hours
saved, is the organisers' own answer and is labelled as such.

Testimonials: after an event, the organiser and a sample of the people who
attended get one signed link (`/impact/testimonial/<token>`) asking for a
rating and a comment, with permission to quote. Only comments with that
permission can be approved by the Super Admin, and only approved ones are
shown publicly (the impact report and the optional public page).
"""
import datetime
import io
import logging
import os
import random
from collections import defaultdict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

TESTIMONIALS = 'testimonials'
SETTINGS = ('settings', 'impact')
TOKEN_SALT = 'testimonial'
HELD_EXCLUDED = ('draft', 'pending_approval', 'rejected', 'cancelled')
METRICS = ('events', 'registrations', 'checkins', 'expected', 'certificates', 'units', 'external',
           'naac_reports', 'forms_saved')


def sample_size() -> int:
    return max(0, int(os.environ.get('TESTIMONIAL_SAMPLE', '10')))


def _today():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()


def _month(value) -> str:
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m')
    text = str(value or '')
    return text[:7] if len(text) >= 7 and text[4] == '-' else ''


def _held(event: dict) -> bool:
    from services_naac import last_day
    end = last_day(event)
    return bool(end) and end < _today() and str(event.get('status') or '').lower() not in HELD_EXCLUDED


def walk_in(reg: dict) -> bool:
    """A desk sign-up rather than an online form: marked since UPG-145; before
    that, the walk-in route set the registration and check-in times together."""
    if reg.get('source') == 'walk_in':
        return True
    registered, checked = str(reg.get('registered_at') or ''), str(reg.get('checkin_time') or '')
    return bool(reg.get('payment_mode') and checked and len(registered) >= 16 and registered[11:16] == checked[:5])


def _people(reg: dict):
    yield reg.get('attendance'), reg.get('participant_type')
    lead = str(reg.get('lead_email') or '').lower()
    for m in reg.get('members') or []:
        if isinstance(m, dict) and str(m.get('email') or '').lower() != lead:
            yield m.get('attendance', reg.get('attendance')), m.get('participant_type') or reg.get('participant_type')


def figures(db) -> Dict[str, dict]:
    """{'YYYY-MM': counts} for every month that has any record."""
    import services_certificates as certs
    from sqlalchemy import select
    from models_pg import Certificate
    from services_naac import last_day
    months: Dict[str, dict] = defaultdict(lambda: {m: 0 for m in METRICS} | {'unit_names': set()})
    events = {str(d.id): d.to_dict() or {} for d in db.collection('events').stream()}
    held_month = {}
    for event_id, ev in events.items():
        if _held(ev):
            month = last_day(ev).strftime('%Y-%m')
            held_month[event_id] = month
            months[month]['events'] += 1
            for unit in (ev.get('department'), ev.get('club')):
                if unit:
                    months[month]['unit_names'].add(str(unit).strip())
    for d in db.collection('registrations').stream():
        reg = d.to_dict() or {}
        made = _month(reg.get('registered_at'))
        if made:
            months[made]['registrations'] += 1
            if not walk_in(reg):
                months[made]['forms_saved'] += 1
        month = held_month.get(str(reg.get('event_id')))
        if not month or str(reg.get('status') or '').lower() in ('cancelled', 'refunded', 'waitlisted'):
            continue
        for present, ptype in _people(reg):
            months[month]['expected'] += 1
            if present == 'Present':
                months[month]['checkins'] += 1
            if str(ptype or '').lower() == 'external':
                months[month]['external'] += 1
    with certs._session() as s:
        for (issued_at,) in s.execute(select(Certificate.issued_at).where(Certificate.is_current.is_(True),
                                                                          Certificate.status == 'valid')):
            month = _month(issued_at)
            if month:
                months[month]['certificates'] += 1
    for d in db.collection('naac_reports').stream():
        report = d.to_dict() or {}
        if report.get('status') == 'submitted' and _month(report.get('submitted_at')):
            months[_month(report['submitted_at'])]['naac_reports'] += 1
    return {m: months[m] for m in sorted(months)}


def _finish(row: dict) -> dict:
    out = {k: v for k, v in row.items() if k != 'unit_names'}
    out['units'] = len(row['unit_names'])
    out['attendance_rate'] = round(100 * row['checkins'] / row['expected'], 1) if row['expected'] else None
    return out


def dashboard(db, year: Optional[str] = None) -> dict:
    """Rows per month (of the year, if given) and per year, from figures()."""
    by_month = figures(db)
    years: Dict[str, dict] = {}
    for month, row in by_month.items():
        y = years.setdefault(month[:4], {m: 0 for m in METRICS} | {'unit_names': set()})
        for m in METRICS:
            if m != 'units':
                y[m] += row[m]
        y['unit_names'] |= row['unit_names']
    months = [dict(_finish(row), month=m) for m, row in by_month.items() if not year or m.startswith(year)]
    return {'months': months, 'years': [dict(_finish(row), year=y) for y, row in sorted(years.items())],
            'time_saved': time_saved(db)}


def period_totals(db, start: str, end: str) -> dict:
    """The key numbers for months start..end (YYYY-MM, inclusive)."""
    total = {m: 0 for m in METRICS} | {'unit_names': set()}
    for month, row in figures(db).items():
        if start <= month <= end:
            for m in METRICS:
                if m != 'units':
                    total[m] += row[m]
            total['unit_names'] |= row['unit_names']
    return _finish(total)


# ── Time saved (organisers' estimates) ──────────────────────────────────────

def save_hours_saved(db, event_id: str, value, actor: str) -> None:
    from utils import log_action
    try:
        hours = float(value)
    except (TypeError, ValueError):
        raise ValueError("Give a number of hours, or leave it blank.")
    if not 0 <= hours <= 500:
        raise ValueError("Give a number of hours between 0 and 500.")
    db.collection('events').document(event_id).update({'hours_saved': hours})
    log_action(db, "IMPACT_HOURS_SAVED", f"{actor}: event {event_id}, {hours:g} hours")


def time_saved(db) -> dict:
    answers = [float(e.get('hours_saved')) for e in (d.to_dict() or {} for d in db.collection('events').stream())
               if e.get('hours_saved') not in (None, '')]
    return {'events': len(answers), 'total': sum(answers),
            'average': round(sum(answers) / len(answers), 1) if answers else None}


# ── Testimonials ────────────────────────────────────────────────────────────

def _serializer():
    from itsdangerous import URLSafeTimedSerializer
    from services_certificates import _secret
    return URLSafeTimedSerializer(_secret(), salt=TOKEN_SALT)


def token_for(event_id: str, email: str, name: str, role: str) -> str:
    return _serializer().dumps({'e': event_id, 'm': email, 'n': name, 'r': role})


def read_token(token: str) -> dict:
    return _serializer().loads(token, max_age=30 * 86400)


def request_testimonials(db) -> dict:
    """The daily job: once per held event, ask the organiser and a sample of attendees."""
    from services_naac import organiser_email
    from utils import log_action
    from utils_email import _base_url, send_email_notification
    asked_events = sent = 0
    for d in db.collection('events').stream():
        ev = d.to_dict() or {}
        if not _held(ev) or ev.get('testimonials_requested_at'):
            continue
        people = []
        organiser = organiser_email(ev)
        if organiser:
            people.append((organiser, (ev.get('organizer') or {}).get('name') or organiser.split('@')[0], 'Organiser'))
        attendees = []
        for r in db.collection('registrations').where('event_id', '==', d.id).stream():
            reg = r.to_dict() or {}
            if reg.get('attendance') == 'Present' and reg.get('lead_email'):
                role = {'faculty': 'Faculty', 'external': 'External participant'}.get(
                    str(reg.get('participant_type') or '').lower(), 'Student')
                attendees.append((str(reg['lead_email']).lower(), reg.get('lead_name') or 'Participant', role))
        random.shuffle(attendees)
        people += [p for p in attendees if p[0] != organiser][:sample_size()]
        base = _base_url().rstrip('/')
        for email, name, role in people:
            link = f"{base}/impact/testimonial/{token_for(d.id, email, name, role)}"
            if send_email_notification(email, f"How was {ev.get('title', 'the event')}?",
                                       f"A minute of your time: how did SapthaEvent work for {ev.get('title', 'the event')}? "
                                       f"Rate it and leave a short comment here: {link}", ev.get('title', 'SapthaEvent')):
                sent += 1
        db.collection('events').document(d.id).update({'testimonials_requested_at': datetime.datetime.now(
            datetime.timezone.utc).isoformat(), 'testimonials_asked': len(people)})
        log_action(db, "IMPACT_TESTIMONIALS_REQUESTED", f"system: event {d.id}, {len(people)} asked")
        asked_events += 1
    return {'events': asked_events, 'emails': sent}


def save_testimonial(db, claim: dict, rating, comment: str, may_quote: bool) -> dict:
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        raise ValueError("Choose a rating from 1 to 5.")
    doc_id = f"{claim['e']}:{claim['m']}"
    ref = db.collection(TESTIMONIALS).document(doc_id)
    old = ref.get().to_dict() or {} if ref.get().exists else {}
    row = {'event_id': claim['e'], 'email': claim['m'], 'name': claim['n'], 'role': claim['r'], 'rating': rating,
           'comment': ' '.join(str(comment or '').split())[:600], 'may_quote': bool(may_quote),
           'approved': bool(old.get('approved')) and bool(may_quote),
           'created_at': old.get('created_at') or datetime.datetime.now(datetime.timezone.utc).isoformat()}
    ref.set(row)
    return row


def testimonials(db, approved_only: bool = False) -> List[dict]:
    rows = [dict(d.to_dict() or {}, id=d.id) for d in db.collection(TESTIMONIALS).stream()]
    if approved_only:
        rows = [r for r in rows if r.get('approved') and r.get('may_quote')]
    return sorted(rows, key=lambda r: r.get('created_at') or '', reverse=True)


def set_approved(db, testimonial_id: str, approved: bool, actor: str) -> None:
    from utils import log_action
    ref = db.collection(TESTIMONIALS).document(testimonial_id)
    doc = ref.get()
    if not doc.exists:
        raise ValueError("No such testimonial.")
    if approved and not (doc.to_dict() or {}).get('may_quote'):
        raise ValueError("Only comments the person allowed us to quote can be shown.")
    ref.update({'approved': bool(approved)})
    log_action(db, "IMPACT_TESTIMONIAL_" + ("APPROVED" if approved else "WITHDRAWN"), f"{actor}: {testimonial_id}")


# ── The public page switch ──────────────────────────────────────────────────

def public_on(db) -> bool:
    doc = db.collection(SETTINGS[0]).document(SETTINGS[1]).get()
    return bool((doc.to_dict() or {}).get('public')) if doc.exists else False


def set_public(db, on: bool, actor: str) -> None:
    from utils import log_action
    db.collection(SETTINGS[0]).document(SETTINGS[1]).set({'public': bool(on), 'by': actor})
    log_action(db, "IMPACT_PUBLIC_PAGE", f"{actor}: {'on' if on else 'off'}")


# ── The impact report (2 pages) ─────────────────────────────────────────────

def shareable_photos(db, start: str, end: str, limit: int = 4) -> List[bytes]:
    from services_naac import last_day
    from utils_storage import StorageError, get_private
    out = []
    events = {str(d.id): d.to_dict() or {} for d in db.collection('events').stream()}
    for d in db.collection('naac_reports').stream():
        ev = events.get(str(d.id)) or {}
        end_day = last_day(ev)
        if not end_day or not (start <= end_day.strftime('%Y-%m') <= end):
            continue
        for f in (d.to_dict() or {}).get('files') or []:
            if f.get('kind') == 'photo' and f.get('shareable') and len(out) < limit:
                try:
                    out.append(get_private(f['key']))
                except (StorageError, OSError):
                    pass
    return out


def report_pdf(db, start: str, end: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    import certificate_pdf
    from services_naac import last_day
    brand = certificate_pdf.branding()
    totals = period_totals(db, start, end)
    saved = time_saved(db)
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=f"{brand['name']} on SapthaEvent")
    story = [Paragraph(f"<b>{escape(brand['name'])}</b>", styles['Title']),
             Paragraph(escape(f"Events on SapthaEvent, {start} to {end}"), styles['Heading2'])]
    kinds: Dict[str, int] = defaultdict(int)
    for d in db.collection('events').stream():
        ev = d.to_dict() or {}
        if _held(ev) and start <= last_day(ev).strftime('%Y-%m') <= end:
            kinds[ev.get('naac_category') or (ev.get('event_type') or 'Other').replace('_', ' ').title()] += 1
    if kinds:
        story.append(Paragraph('What was run: ' + escape(', '.join(f"{n} {k}" for k, n in sorted(kinds.items()))) + '.',
                               styles['Normal']))
    rows = [('Events held', totals['events']), ('Registrations', totals['registrations']),
            ('Check-ins', totals['checkins']),
            ('Attendance', f"{totals['attendance_rate']}% ({totals['checkins']} of {totals['expected']})"
             if totals['attendance_rate'] is not None else None),
            ('Certificates issued', totals['certificates']), ('Departments and clubs', totals['units']),
            ('External participants', totals['external']), ('NAAC reports submitted', totals['naac_reports']),
            ('Registrations without a paper or Google form', totals['forms_saved']),
            ('Hours saved (organisers\' estimates)', f"{saved['total']:g} over {saved['events']} events"
             if saved['events'] else None)]
    table = Table([[k, str(v)] for k, v in rows if v is not None], colWidths=[95 * mm, 70 * mm])
    table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
                               ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#eef1f8'))]))
    story += [Spacer(1, 5 * mm), table, PageBreak()]
    quotes = testimonials(db, approved_only=True)[:5]
    if quotes:
        story.append(Paragraph('What people said', styles['Heading2']))
        for q in quotes:
            story.append(Paragraph(f"“{escape(q['comment'])}” — <b>{escape(q['name'])}</b>, {escape(q['role'])} "
                                   f"({'★' * int(q['rating'])})", styles['Normal']))
            story.append(Spacer(1, 2 * mm))
    photos = shareable_photos(db, start, end)
    if photos:
        story.append(Paragraph('From the events', styles['Heading2']))
        cells = []
        for data in photos:
            try:
                cells.append(RLImage(io.BytesIO(data), width=80 * mm, height=55 * mm, kind='proportional'))
            except Exception:
                logger.warning("A shareable photo couldn't be drawn")
        if cells:
            story.append(Table([cells[i:i + 2] for i in range(0, len(cells), 2)]))
    doc.build(story)
    return buf.getvalue()
