"""
services_naac.py — NAAC / AQAR evidence from event data (UPG-144).

* NAAC categories: a list the Super Admin edits (`settings/naac_categories`),
  with a default; each event's organiser picks one (`naac_category`).
* Post-event reports (`naac_reports/<event id>`): objectives, summary,
  outcomes, the resource person, a collaborator, and evidence files (photos,
  with their geotag when the phone wrote one, a brochure or notice, other
  files) kept in private storage. Attendance and hours come from check-ins.
  Due `NAAC_REPORT_DAYS` (default 7) after the event; the organiser is
  reminded once a day until it's submitted.
* The report builder: an academic year (starting `NAAC_YEAR_START_MONTH`,
  default June) filtered by department or club, category and event type.
  Its columns and sheets come from `config/naac_layout.json`, not code.

Who may do what: organisers edit their own events' reports (`edit_event`);
the IQAC coordinator and Super Admin see everything; a department admin sees
events of their own department.
"""
import datetime
import io
import json
import logging
import os
import uuid
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

REPORTS = 'naac_reports'
SETTINGS_DOC = ('settings', 'naac_categories')
DEFAULT_CATEGORIES = [
    'Seminar / conference', 'Workshop', 'FDP / professional development', 'Guest lecture',
    'Extension / outreach (NSS, NCC, community)', 'Cultural', 'Sports', 'Technical competition',
    'Industry interaction', 'Placement',
]
ALL_ROLES = ('SuperAdmin', 'Super Admin', 'UniversityAdmin', 'IQACCoordinator')
FILE_KINDS = {'photo': ('JPEG', 'PNG'), 'brochure': ('PDF', 'JPEG', 'PNG'), 'evidence': ('PDF', 'JPEG', 'PNG')}
MAX_BYTES = {'photo': 5 * 1024 * 1024, 'brochure': 10 * 1024 * 1024, 'evidence': 10 * 1024 * 1024}
LAYOUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'naac_layout.json')
FDP_TYPES = ('fdp', 'workshop', 'orientation', 'conference')


class NaacError(ValueError):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _today():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()


def report_days() -> int:
    return max(1, int(os.environ.get('NAAC_REPORT_DAYS', '7')))


def year_start_month() -> int:
    return min(12, max(1, int(os.environ.get('NAAC_YEAR_START_MONTH', '6'))))


def layout() -> dict:
    with open(LAYOUT_FILE, encoding='utf-8') as fh:
        return json.load(fh)


# ── Categories ──────────────────────────────────────────────────────────────

def categories(db) -> List[str]:
    doc = db.collection(SETTINGS_DOC[0]).document(SETTINGS_DOC[1]).get()
    saved = (doc.to_dict() or {}).get('names') if doc.exists else None
    return list(saved) if saved else list(DEFAULT_CATEGORIES)


def save_categories(db, names: List[str], actor: str) -> List[str]:
    from utils import log_action
    clean, seen = [], set()
    for n in names:
        n = ' '.join(str(n or '').split())[:80]
        if n and n.lower() not in seen:
            seen.add(n.lower())
            clean.append(n)
    if not clean:
        raise NaacError("Keep at least one NAAC category.")
    db.collection(SETTINGS_DOC[0]).document(SETTINGS_DOC[1]).set({'names': clean, 'updated_by': actor,
                                                                  'updated_at': _now().isoformat()})
    log_action(db, "NAAC_CATEGORIES_SAVED", f"{actor}: {', '.join(clean)}")
    return clean


def set_category(db, event_id: str, name: str, actor: str) -> None:
    from utils import log_action
    if name not in categories(db):
        raise NaacError("Choose one of the NAAC categories.")
    db.collection('events').document(event_id).update({'naac_category': name})
    log_action(db, "NAAC_CATEGORY_SET", f"{actor}: event {event_id} is '{name}'")


# ── Who sees what ───────────────────────────────────────────────────────────

def sees_all(session) -> bool:
    return session.get('role') in ALL_ROLES


def user_department(db, session) -> str:
    doc = db.collection('users').document(str(session.get('user_id') or '').lower()).get()
    return str((doc.to_dict() or {}).get('department') or '').strip() if doc.exists else ''


def may_view(db, session, event: dict) -> bool:
    from services_permission import can
    if sees_all(session):
        return True
    if session.get('role') == 'DepartmentAdmin':
        dept = user_department(db, session)
        return bool(dept) and dept.lower() == str(event.get('department') or '').strip().lower()
    return can(session, 'edit_event', event, db=db)


def may_edit(db, session, event: dict) -> bool:
    from services_permission import can
    return session.get('role') not in ('IQACCoordinator', 'DepartmentAdmin') and can(session, 'edit_event', event, db=db)


def may_run_builder(session) -> bool:
    return sees_all(session) or session.get('role') == 'DepartmentAdmin'


# ── Dates ───────────────────────────────────────────────────────────────────

def _date(value) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(value or '')[:10])
    except ValueError:
        return None


def last_day(event: dict) -> Optional[datetime.date]:
    days = [d for d in (_date(event.get('date')), _date(event.get('end_date')), _date(event.get('end_datetime'))) if d]
    return max(days) if days else None


def due_date(event: dict) -> Optional[datetime.date]:
    end = last_day(event)
    return end + datetime.timedelta(days=report_days()) if end else None


def academic_year(day: datetime.date) -> str:
    start = day.year if day.month >= year_start_month() else day.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def year_range(label: str):
    start = int(str(label)[:4])
    first = datetime.date(start, year_start_month(), 1)
    nxt = datetime.date(start + 1, year_start_month(), 1)
    return first, nxt - datetime.timedelta(days=1)


# ── Reports ─────────────────────────────────────────────────────────────────

def get_report(db, event_id: str) -> dict:
    doc = db.collection(REPORTS).document(event_id).get()
    return (doc.to_dict() or {}) if doc.exists else {}


TEXT_FIELDS = {'objectives': 2000, 'summary': 4000, 'outcomes': 2000, 'resource_name': 200,
               'resource_designation': 200, 'resource_organisation': 200, 'collaborator': 200}


def save_report(db, event_id: str, form: dict, actor: str, submit: bool = False) -> dict:
    from utils import log_action
    report = get_report(db, event_id)
    for field, limit in TEXT_FIELDS.items():
        if field in form:
            report[field] = str(form.get(field) or '').strip()[:limit]
    if submit:
        missing = [label for field, label in (('objectives', 'objectives'), ('summary', 'a summary'),
                                              ('outcomes', 'outcomes')) if not report.get(field)]
        if missing:
            raise NaacError(f"Add {', '.join(missing)} before submitting.")
        report.update(status='submitted', submitted_at=_now().isoformat(), submitted_by=actor)
    else:
        report.setdefault('status', 'draft')
    report.update(event_id=event_id, updated_at=_now().isoformat(), updated_by=actor)
    db.collection(REPORTS).document(event_id).set(report)
    log_action(db, "NAAC_REPORT_SUBMITTED" if submit else "NAAC_REPORT_SAVED", f"{actor}: event {event_id}")
    return report


def _geotag(image) -> Optional[dict]:
    """Latitude and longitude from a photo's EXIF GPS data, if the phone wrote it."""
    try:
        gps = image.getexif().get_ifd(0x8825)
    except Exception:
        return None
    if not gps or 2 not in gps or 4 not in gps:
        return None

    def degrees(value, ref):
        d, m, s = (float(x) for x in value)
        out = d + m / 60 + s / 3600
        return -out if ref in ('S', 'W') else out
    try:
        return {'lat': round(degrees(gps[2], gps.get(1, 'N')), 6), 'lon': round(degrees(gps[4], gps.get(3, 'E')), 6)}
    except Exception:
        return None


def add_file(db, event_id: str, kind: str, filename: str, data: bytes, actor: str, shareable: bool = False) -> dict:
    """Keep an evidence file privately; refuse anything but PDF, JPG or PNG, or too big."""
    from PIL import Image, UnidentifiedImageError
    from utils import log_action
    from utils_storage import put_private
    if kind not in FILE_KINDS:
        raise NaacError("Choose photo, brochure or evidence.")
    if not data:
        raise NaacError("Choose a file to upload.")
    if len(data) > MAX_BYTES[kind]:
        raise NaacError(f"A {kind} file must be {MAX_BYTES[kind] // (1024 * 1024)} MB or smaller.")
    geotag = None
    if data[:5] == b'%PDF-':
        kind_found, ext = 'PDF', 'pdf'
    else:
        try:
            image = Image.open(io.BytesIO(data))
            kind_found = image.format
            geotag = _geotag(image) if kind == 'photo' else None
        except (UnidentifiedImageError, OSError):
            kind_found = ''
        ext = {'JPEG': 'jpg', 'PNG': 'png'}.get(kind_found, '')
    if kind_found not in FILE_KINDS[kind]:
        allowed = ', '.join('JPG' if k == 'JPEG' else k for k in FILE_KINDS[kind])
        raise NaacError(f"Upload the {kind} as {allowed}.")
    file_id = uuid.uuid4().hex
    key = put_private(data, f"naac/{event_id}/{file_id}.{ext}",
                      'application/pdf' if ext == 'pdf' else f"image/{'jpeg' if ext == 'jpg' else 'png'}")
    entry = {'id': file_id, 'kind': kind, 'name': os.path.basename(str(filename or f'{kind}.{ext}'))[:120],
             'key': key, 'ext': ext, 'size': len(data), 'geotag': geotag, 'shareable': bool(shareable and kind == 'photo'),
             'uploaded_by': actor, 'uploaded_at': _now().isoformat()}
    report = get_report(db, event_id)
    report.setdefault('status', 'draft')
    report['files'] = list(report.get('files') or []) + [entry]
    report['event_id'] = event_id
    db.collection(REPORTS).document(event_id).set(report)
    log_action(db, "NAAC_FILE_ADDED", f"{actor}: {kind} '{entry['name']}' on event {event_id}")
    return entry


def attendance(db, event_id: str, event: dict) -> Dict[str, float]:
    """People marked Present (each team member counted), by participant type, and their hours."""
    counts = {'students': 0, 'faculty': 0, 'external': 0}
    hours_each = float(event.get('activity_hours') or 0)
    for d in db.collection('registrations').where('event_id', '==', event_id).stream():
        reg = d.to_dict() or {}
        if str(reg.get('status') or '').lower() in ('cancelled', 'refunded', 'waitlisted'):
            continue
        people = [(reg.get('attendance'), reg.get('participant_type'))]
        people += [(m.get('attendance', reg.get('attendance')), m.get('participant_type') or reg.get('participant_type'))
                   for m in reg.get('members') or [] if isinstance(m, dict)
                   and str(m.get('email') or '').lower() != str(reg.get('lead_email') or '').lower()]
        for present, ptype in people:
            if str(present or '') == 'Present':
                key = {'faculty': 'faculty', 'external': 'external'}.get(str(ptype or '').lower(), 'students')
                counts[key] += 1
    total = sum(counts.values())
    return dict(counts, total=total, hours=round(total * hours_each, 1))


def organiser_email(event: dict) -> str:
    return str((event.get('organizer') or {}).get('email') or event.get('spoc_id') or '').lower()


# ── Missing reports and reminders ───────────────────────────────────────────

def _events(db) -> List[dict]:
    return [dict(d.to_dict() or {}, id=d.id) for d in db.collection('events').stream()]


def needs_report(event: dict) -> bool:
    end = last_day(event)
    status = str(event.get('status') or '').lower()
    return bool(end) and end < _today() and status not in ('draft', 'pending_approval', 'rejected', 'cancelled')


def missing(db, session=None) -> List[dict]:
    """Held events with no submitted report, oldest first, with whether they're overdue."""
    out = []
    for ev in _events(db):
        if not needs_report(ev) or (session is not None and not may_view(db, session, ev)):
            continue
        report = get_report(db, ev['id'])
        if report.get('status') == 'submitted':
            continue
        due = due_date(ev)
        out.append({'id': ev['id'], 'title': ev.get('title', 'Event'), 'date': str(ev.get('date') or ''),
                    'department': ev.get('department') or '', 'organiser': organiser_email(ev),
                    'due': due.isoformat() if due else '', 'overdue': bool(due and due < _today()),
                    'reminders': len(report.get('reminders') or [])})
    return sorted(out, key=lambda r: r['date'])


def remind(db, event_id: str, actor: str = 'system') -> bool:
    """Email the organiser that the event's NAAC report is due."""
    from utils import log_action
    from utils_email import _base_url, send_email_notification
    doc = db.collection('events').document(event_id).get()
    event = doc.to_dict() or {} if doc.exists else {}
    to = organiser_email(event)
    if not to:
        return False
    due = due_date(event)
    sent = send_email_notification(
        to, f"NAAC report due: {event.get('title', 'your event')}",
        f"The post-event NAAC report for {event.get('title', 'your event')} is "
        f"{'overdue' if due and due < _today() else 'due'}{f' (due {due.isoformat()})' if due else ''}. "
        f"Fill it in at {_base_url().rstrip('/')}/naac/events/{event_id}/report", event.get('title', 'SapthaEvent'))
    report = get_report(db, event_id)
    report['reminders'] = list(report.get('reminders') or []) + [{'at': _now().isoformat(), 'by': actor, 'sent': bool(sent)}]
    report['event_id'] = event_id
    report.setdefault('status', 'draft')
    db.collection(REPORTS).document(event_id).set(report)
    log_action(db, "NAAC_REMINDER", f"{actor}: event {event_id} to {to} ({'sent' if sent else 'failed'})")
    return bool(sent)


def daily_reminders(db) -> dict:
    """The cron job: one reminder a day for each overdue report (`/internal/cron/naac`)."""
    sent = skipped = 0
    today = _today().isoformat()
    for row in missing(db):
        if not row['overdue']:
            continue
        last = [r for r in get_report(db, row['id']).get('reminders') or [] if r.get('by') == 'system']
        if last and str(last[-1].get('at', ''))[:10] == today:
            skipped += 1
            continue
        sent += 1 if remind(db, row['id'], 'system') else 0
    return {'sent': sent, 'already_today': skipped}


# ── The report builder ──────────────────────────────────────────────────────

def _unit(event: dict) -> List[str]:
    return [str(v).strip() for v in (event.get('department'), event.get('club'), event.get('category')) if v]


def filter_options(db, session) -> dict:
    events = [e for e in _events(db) if may_view(db, session, e)]
    years = sorted({academic_year(last_day(e)) for e in events if last_day(e)}, reverse=True)
    return {'years': years or [academic_year(_today())],
            'units': sorted({u for e in events for u in _unit(e)}),
            'categories': categories(db),
            'event_types': sorted({str(e.get('event_type')) for e in events if e.get('event_type')})}


def build(db, session, year: str, unit: str = '', category: str = '', event_type: str = '') -> dict:
    """The year's NAAC data: summary per category, detail rows, awards, faculty participation."""
    import services_certificates as certs
    first, last = year_range(year)
    chosen = []
    for ev in _events(db):
        end = last_day(ev)
        if not end or not (first <= end <= last) or not needs_report(ev) or not may_view(db, session, ev):
            continue
        if unit and unit not in _unit(ev):
            continue
        if category and (ev.get('naac_category') or '') != category:
            continue
        if event_type and str(ev.get('event_type') or '') != event_type:
            continue
        chosen.append(ev)
    chosen.sort(key=lambda e: str(e.get('date') or ''))
    detail: Dict[str, List[dict]] = {}
    summary: Dict[str, dict] = {}
    awards, faculty = [], []
    for ev in chosen:
        cat = ev.get('naac_category') or 'Not classified'
        report = get_report(db, ev['id'])
        att = attendance(db, ev['id'], ev)
        detail.setdefault(cat, []).append({
            'id': ev['id'], 'title': ev.get('title', 'Event'), 'date': str(ev.get('date') or ''),
            'end_date': str(ev.get('end_date') or ''), 'department': ev.get('department') or '',
            'event_type': ev.get('event_type') or '', 'category': cat,
            'resource_person': ', '.join(p for p in (report.get('resource_name'), report.get('resource_designation'),
                                                      report.get('resource_organisation')) if p),
            'collaborator': report.get('collaborator') or '', 'students': att['students'], 'faculty': att['faculty'],
            'external': att['external'], 'participants': att['total'], 'hours': att['hours'],
            'report': report.get('status') or 'missing', 'evidence_files': len(report.get('files') or []),
            'evidence_link': f"/naac/events/{ev['id']}/report"})
        s = summary.setdefault(cat, {'category': cat, 'events': 0, 'students': 0, 'faculty': 0, 'external': 0,
                                     'participants': 0, 'hours': 0.0})
        s['events'] += 1
        for k in ('students', 'faculty', 'external'):
            s[k] += att[k]
        s['participants'] += att['total']
        s['hours'] = round(s['hours'] + att['hours'], 1)
        for c in certs.for_event(ev['id']):
            if c['cert_type'] in certs.POSITION_TYPES + certs.AWARD_TYPES and c['status'] == 'valid':
                awards.append({'name': c['name'], 'award': certs.TYPES[c['cert_type']]['title'],
                               'position': c.get('position') or '', 'event': ev.get('title', 'Event'),
                               'date': str(ev.get('date') or ''), 'department': ev.get('department') or ''})
        if str(ev.get('event_type') or '').lower() in FDP_TYPES:
            for d in db.collection('registrations').where('event_id', '==', ev['id']).stream():
                reg = d.to_dict() or {}
                if str(reg.get('participant_type') or '').lower() == 'faculty' and reg.get('attendance') == 'Present':
                    faculty.append({'name': reg.get('lead_name') or '', 'designation': reg.get('designation') or '',
                                    'institution': reg.get('institution') or '', 'event': ev.get('title', 'Event'),
                                    'event_type': ev.get('event_type') or '', 'date': str(ev.get('date') or ''),
                                    'hours': float(ev.get('activity_hours') or 0)})
    return {'year': year, 'from': first.isoformat(), 'to': last.isoformat(),
            'filters': {'unit': unit, 'category': category, 'event_type': event_type},
            'summary': [summary[c] for c in sorted(summary)], 'detail': {c: detail[c] for c in sorted(detail)},
            'awards': awards, 'faculty': faculty, 'events': chosen}


# ── Exports ─────────────────────────────────────────────────────────────────

def _rows(rows: List[dict], columns: List[dict]) -> List[list]:
    return [[r.get(col['field'], '') for col in columns] for r in rows]


def to_xlsx(data: dict) -> bytes:
    import services_export
    lay = layout()
    sheets = [('Summary', [c['title'] for c in lay['summary']], _rows(data['summary'], lay['summary']))]
    for cat, rows in data['detail'].items():
        name = ''.join(ch for ch in cat if ch not in '[]:*?/\\')[:31] or 'Category'
        sheets.append((name, [c['title'] for c in lay['detail']], _rows(rows, lay['detail'])))
    sheets.append(('Awards', [c['title'] for c in lay['awards']], _rows(data['awards'], lay['awards'])))
    sheets.append(('Faculty', [c['title'] for c in lay['faculty']], _rows(data['faculty'], lay['faculty'])))
    return services_export.to_xlsx(sheets)


def to_pdf(data: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    import certificate_pdf
    brand = certificate_pdf.branding()
    lay = layout()
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=f"NAAC report {data['year']}")
    story = []
    head = [Paragraph(f"<b>{escape(brand['name'])}</b>", styles['Title'])]
    if brand['logo']:
        try:
            logo = RLImage(brand['logo'], width=46 * mm, height=12 * mm)
            story.append(Table([[logo, head[0]]], colWidths=[50 * mm, None],
                               style=[('BACKGROUND', (0, 0), (0, 0), colors.HexColor(brand['primary'])),
                                      ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
        except Exception:
            story += head
    else:
        story += head
    f = data['filters']
    story.append(Paragraph(escape(f"NAAC / AQAR activity report, academic year {data['year']} "
                                  f"({data['from']} to {data['to']})"), styles['Heading2']))
    chosen = ', '.join(f"{k.replace('_', ' ')}: {v}" for k, v in f.items() if v) or 'all events'
    story.append(Paragraph(escape(f"Filters: {chosen}"), styles['Normal']))
    story.append(Spacer(1, 4 * mm))
    cell = styles['BodyText']
    cell.fontSize = 8
    cell.leading = 10

    def table(columns, rows):
        body = [[Paragraph(f"<b>{escape(c['title'])}</b>", cell) for c in columns]]
        body += [[Paragraph(escape(str(v)), cell) for v in row] for row in _rows(rows, columns)]
        t = Table(body, repeatRows=1)
        t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
                               ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8ecf6')),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        return t
    story += [Paragraph('Summary by NAAC category', styles['Heading3']), table(lay['summary'], data['summary'])]
    totals = {k: sum(r[k] for r in data['summary']) for k in ('events', 'participants')}
    story.append(Paragraph(escape(f"Total: {totals['events']} events, {totals['participants']} participants, "
                                  f"{round(sum(r['hours'] for r in data['summary']), 1)} hours."), styles['Normal']))
    for cat, rows in data['detail'].items():
        story += [Spacer(1, 3 * mm), Paragraph(escape(cat), styles['Heading3']), table(lay['detail'], rows)]
    if data['awards']:
        story += [Spacer(1, 3 * mm), Paragraph('Awards and positions won', styles['Heading3']),
                  table(lay['awards'], data['awards'])]
    if data['faculty']:
        story += [Spacer(1, 3 * mm), Paragraph('Faculty participation in FDPs and workshops', styles['Heading3']),
                  table(lay['faculty'], data['faculty'])]
    doc.build(story)
    return buf.getvalue()


def evidence_zip(db, data: dict) -> bytes:
    import re
    import zipfile
    from utils_storage import StorageError, get_private

    def safe(text):
        return re.sub(r'[^A-Za-z0-9._ -]+', '_', str(text)).strip()[:80] or 'item'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for ev in data['events']:
            folder = f"{safe(ev.get('naac_category') or 'Not classified')}/{safe(str(ev.get('date') or '') + ' ' + ev.get('title', ''))}"
            for f in get_report(db, ev['id']).get('files') or []:
                try:
                    zf.writestr(f"{folder}/{f['kind']}-{safe(f['name'])}", get_private(f['key']))
                except (StorageError, OSError):
                    logger.warning("Evidence %s for %s not read", f.get('id'), ev['id'])
    return buf.getvalue()
