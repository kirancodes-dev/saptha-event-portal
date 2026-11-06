"""
services_certificates.py — who gets which certificate, and the one record of
every certificate issued (UPG-122).

Types: participation; winner, runner-up and other positions (from published
results); merit and special mention (issued by hand); volunteer, coordinator,
organiser and judge (the event's staff); speaker or resource person; workshop or
FDP completion; NSS / NCC extension hours.

Who is eligible:
  * participation, completion and extension: people marked Present, and on a
    multi-day event on at least the organiser's share of its days (default 80%);
  * every member of a team, in their own name, by their own attendance;
  * positions: the podium of the event's published results (each member too);
  * staff and speakers: from the event, no attendance needed.

The `certificates` table holds every certificate. At most one current
certificate per person, event and type: the database's partial unique index
refuses a second, so issuing twice, or two runs at once, never duplicates one.
The number is random (`new_number`), never derived from the person.
"""
import datetime
import json
import logging
import os
import re
import secrets
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

TYPES = {
    'participation':   {'title': 'Certificate of Participation', 'phrase': 'for participating in'},
    'completion':      {'title': 'Certificate of Completion', 'phrase': 'for successfully completing'},
    'extension':       {'title': 'Certificate of Service', 'phrase': 'for extension activity in'},
    'winner':          {'title': 'Certificate of Merit', 'phrase': 'for securing the first place in'},
    'runner_up':       {'title': 'Certificate of Merit', 'phrase': 'for securing the second place in'},
    'position':        {'title': 'Certificate of Merit', 'phrase': 'for securing a place in'},
    'merit':           {'title': 'Certificate of Merit', 'phrase': 'for meritorious performance in'},
    'special_mention': {'title': 'Special Mention', 'phrase': 'for an outstanding contribution to'},
    'volunteer':       {'title': 'Certificate of Appreciation', 'phrase': 'for volunteering at'},
    'coordinator':     {'title': 'Certificate of Appreciation', 'phrase': 'for coordinating'},
    'organiser':       {'title': 'Certificate of Appreciation', 'phrase': 'for organising'},
    'judge':           {'title': 'Certificate of Appreciation', 'phrase': 'for serving as a judge at'},
    'speaker':         {'title': 'Certificate of Appreciation', 'phrase': 'for serving as a resource person at'},
}
ATTENDED_TYPES = ('participation', 'completion', 'extension')
POSITION_TYPES = ('winner', 'runner_up', 'position')
STAFF_TYPES = {'volunteer': 'volunteer', 'eventcoordinator': 'coordinator', 'coordinator': 'coordinator',
               'judge': 'judge', 'eventorganizer': 'organiser', 'organiser': 'organiser'}
COMPLETION_EVENT_TYPES = ('workshop', 'fdp', 'orientation')
EXTENSION_EVENT_TYPES = ('nss_ncc', 'social_drive')
DEFAULT_MIN_ATTENDANCE = 80
# Crockford-style alphabet: no 0/O, 1/I/L, U; 13 characters ≈ 64 random bits
_ALPHABET = '23456789ABCDEFGHJKMNPQRSTVWXYZ'


class CertificateError(ValueError):
    pass


def new_number() -> str:
    """A random, unguessable certificate number, e.g. SE-7KQ4-M2XD-9HTR-P."""
    raw = ''.join(secrets.choice(_ALPHABET) for _ in range(13))
    return f"SE-{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12]}"


def person_key(email: str = '', usn: str = '', name: str = '', reg_id: str = '') -> str:
    """One person, whatever the email's case: their email, else their USN, else
    their name on this registration."""
    email = (email or '').strip().lower()
    if email:
        return email
    usn = (usn or '').strip().upper()
    if usn:
        return f'usn:{usn}'
    plain = re.sub(r'\s+', ' ', (name or '').strip().lower())
    return f"name:{plain}:{reg_id}"


# ── The event's days and someone's attendance ───────────────────────────────

def _date(value) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(value or '')[:10])
    except ValueError:
        return None


def event_days(event: dict) -> int:
    start = _date(event.get('date') or event.get('start_datetime'))
    end = _date(event.get('end_date') or event.get('end_datetime')) or start
    if not start or not end or end < start:
        return 1
    return (end - start).days + 1


def min_attendance(event: dict) -> int:
    try:
        return max(0, min(100, int(event.get('cert_min_attendance_pct', DEFAULT_MIN_ATTENDANCE))))
    except (TypeError, ValueError):
        return DEFAULT_MIN_ATTENDANCE


def attended_enough(reg: dict, event: dict, member: Optional[dict] = None) -> bool:
    """Present, and on a multi-day event on enough of its days."""
    if member is not None and str(member.get('attendance') or '').strip():
        present = str(member.get('attendance')).strip().lower() == 'present'
    else:
        present = str(reg.get('attendance') or '').strip().lower() == 'present'
    if not present:
        return False
    days = event_days(event)
    if days <= 1:
        return True
    attended = len(set(reg.get('attendance_days') or [])) or 1
    return attended * 100 >= min_attendance(event) * days


# ── Who gets which certificate ──────────────────────────────────────────────

def attendance_type(event: dict) -> str:
    kind = str(event.get('event_type') or '').lower()
    category = str(event.get('category') or '').strip().upper()
    if kind in EXTENSION_EVENT_TYPES or category in ('NSS', 'NCC'):
        return 'extension'
    if kind in COMPLETION_EVENT_TYPES:
        return 'completion'
    return 'participation'


def _people(reg: dict, reg_id: str):
    """The lead and each team member, once each: (name, email, usn, member or None)."""
    lead_email = str(reg.get('lead_email') or reg.get('email') or '').strip().lower()
    yield (reg.get('lead_name') or reg.get('name') or 'Participant', lead_email,
           reg.get('lead_usn') or reg.get('usn') or '', None)
    seen = {lead_email} if lead_email else set()
    for m in reg.get('members') or []:
        if not isinstance(m, dict):
            continue
        email = str(m.get('email') or '').strip().lower()
        if email and email in seen:
            continue
        seen.add(email)
        yield (m.get('name') or 'Participant', email, m.get('usn') or '', m)


def _active(reg: dict) -> bool:
    return str(reg.get('status') or '').strip().lower() not in ('cancelled', 'refunded', 'waitlisted',
                                                                'pending_payment', 'pending payment')


def _speakers(event: dict) -> List[dict]:
    details = event.get('details') or {}
    people = []
    if details.get('speaker'):
        people.append({'name': details['speaker'], 'designation': details.get('speaker_designation', '')})
    for key in ('resource_persons', 'trainer'):
        for line in str(details.get(key) or '').splitlines():
            name, _, title = line.partition(',')
            if name.strip():
                people.append({'name': name.strip(), 'designation': title.strip()})
    for s in event.get('speakers') or []:
        if isinstance(s, dict) and s.get('name'):
            people.append({'name': s['name'], 'designation': s.get('designation') or s.get('title') or '',
                           'email': s.get('email', '')})
    return people


def _ranks(db, event_id: str, event: dict) -> Dict[str, int]:
    """Registration id → place, for the podium of the event's published results."""
    if not event.get('results_published'):
        return {}
    from services_leaderboard import for_event, podium
    return {str(r['id']): int(r['rank']) for r in podium(for_event(db, event_id))}


AWARD_TYPES = ('merit', 'special_mention')


def registered_people(db, event_id: str) -> List[dict]:
    """Everyone on an active registration (each team member too): who the
    organiser can award a merit or special-mention certificate to (UPG-142)."""
    out = []
    for d in db.collection('registrations').where('event_id', '==', event_id).stream():
        reg = d.to_dict() or {}
        if not _active(reg):
            continue
        for name, email, usn, member in _people(reg, d.id):
            out.append({'name': name, 'email': email, 'reg_id': d.id, 'lead': member is None,
                        'person_key': person_key(email, usn, name, d.id),
                        'designation': (reg.get('designation') if member is None else member.get('designation')) or '',
                        'institution': (reg.get('institution') if member is None else member.get('institution')) or '',
                        'team': reg.get('team_name') if reg.get('team_name') not in (None, '', 'Individual') else ''})
    return sorted(out, key=lambda p: p['name'].lower())


def award(db, event_id: str, person: str, kind: str, note: str = '', actor: str = '') -> Optional[dict]:
    """Award a merit or special-mention certificate to a registered person:
    issued once, emailed and audit-logged like any other. None if they have it."""
    from services_certificate_runs import ready_to_issue
    if kind not in AWARD_TYPES:
        raise CertificateError("Choose merit or special mention.")
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        raise CertificateError('Event not found.')
    event = doc.to_dict() or {}
    problem = ready_to_issue(event)
    if problem:
        raise CertificateError(problem)
    who = next((p for p in registered_people(db, event_id) if p['person_key'] == person), None)
    if who is None:
        raise CertificateError("Choose someone registered for this event.")
    cert = issue_one(event_id, event, dict(who, cert_type=kind, note=' '.join(str(note or '').split())), actor)
    if cert:
        from utils import log_action
        log_action(db, "CERT_AWARDED", f"{actor}: {TYPES[kind]['title']} {cert['number']} to {who['name']} "
                                       f"for event {event_id}")
    return cert


def recipients(db, event_id: str, event: Optional[dict] = None) -> List[dict]:
    """Every certificate the event's people are owed: one dict per person and type."""
    if event is None:
        doc = db.collection('events').document(event_id).get()
        if not doc.exists:
            raise CertificateError('Event not found.')
        event = doc.to_dict() or {}
    out: List[dict] = []
    base_type = attendance_type(event)
    ranks = _ranks(db, event_id, event)
    extras = {'hours': float(event.get('activity_hours') or 0) or None,
              'points': float(event.get('activity_points') or 0) or None}

    regs = [(d.id, d.to_dict() or {}) for d in db.collection('registrations').where('event_id', '==', event_id).stream()]
    for reg_id, reg in regs:
        if not _active(reg):
            continue
        place = ranks.get(str(reg_id))
        for name, email, usn, member in _people(reg, reg_id):
            common = {'name': name, 'email': email, 'reg_id': reg_id, 'lead': member is None,
                      'person_key': person_key(email, usn, name, reg_id),
                      'designation': (reg.get('designation') if member is None else member.get('designation')) or '',
                      'institution': (reg.get('institution') if member is None else member.get('institution')) or '',
                      'team': reg.get('team_name') if reg.get('team_name') not in (None, '', 'Individual') else ''}
            if attended_enough(reg, event, member):
                out.append(dict(common, cert_type=base_type, **extras))
            if place:
                kind = 'winner' if place == 1 else 'runner_up' if place == 2 else 'position'
                out.append(dict(common, cert_type=kind, position=place))

    for s in event.get('staff') or []:
        kind = STAFF_TYPES.get(str(s.get('role') or '').replace(' ', '').lower())
        if kind and s.get('email'):
            out.append({'name': s.get('name') or s['email'].split('@')[0].title(), 'email': s['email'].lower(),
                        'person_key': person_key(s['email']), 'cert_type': kind, 'role': s.get('role')})
    organiser = event.get('organizer') or {}
    if organiser.get('email') or event.get('spoc_id'):
        email = str(organiser.get('email') or event.get('spoc_id')).lower()
        out.append({'name': organiser.get('name') or email.split('@')[0].title(), 'email': email,
                    'person_key': person_key(email), 'cert_type': 'organiser'})
    for sp in _speakers(event):
        out.append({'name': sp['name'], 'email': (sp.get('email') or '').lower(), 'designation': sp.get('designation', ''),
                    'person_key': person_key(sp.get('email', ''), name=sp['name'], reg_id='speaker'),
                    'cert_type': 'speaker'})

    # One per person and type (a speaker listed twice, a lead also on the staff list as a judge, ...)
    unique, seen = [], set()
    for r in out:
        key = (r['person_key'], r['cert_type'])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ── The records ─────────────────────────────────────────────────────────────

def _session():
    from sqlalchemy.orm import Session
    from db_pg import get_engine
    return Session(get_engine())


def _row_dict(row) -> dict:
    data = json.loads(row.data_json or '{}')
    return {'id': str(row.id), 'number': row.number, 'version': row.version, 'is_current': row.is_current,
            'status': row.status, 'event_id': row.event_id, 'person_key': row.person_key,
            'email': row.recipient_email, 'name': row.recipient_name, 'reg_id': row.reg_id,
            'cert_type': row.cert_type, 'position': row.position, 'data': data, 'pdf_key': row.pdf_key,
            'pdf_sha256': row.pdf_sha256, 'issued_at': row.issued_at, 'issued_by': row.issued_by,
            'emailed_at': row.emailed_at, 'revoked_at': row.revoked_at, 'revoked_reason': row.revoked_reason}


def claim(event_id: str, recipient: dict, data: dict, actor: str = '') -> Optional[dict]:
    """Create the current certificate for this person, event and type; None if
    there is one already (the database refuses a second)."""
    from sqlalchemy.exc import IntegrityError
    from models_pg import Certificate
    for _ in range(3):   # a clash on the random number (rare) gets a new number
        try:
            with _session() as s, s.begin():
                row = Certificate(number=new_number(), version=1, is_current=True, status='valid',
                                  event_id=str(event_id), person_key=recipient['person_key'],
                                  recipient_email=recipient.get('email') or None,
                                  recipient_name=str(recipient.get('name') or 'Participant')[:300],
                                  reg_id=recipient.get('reg_id'), cert_type=recipient['cert_type'],
                                  position=recipient.get('position'), data_json=json.dumps(data, default=str),
                                  issued_by=actor or None)
                s.add(row)
                s.flush()
                return _row_dict(row)
        except IntegrityError as exc:
            if 'number' in str(getattr(exc, 'orig', exc)).lower() and 'personkey' not in str(exc).lower():
                continue
            return None
    raise CertificateError("Couldn't make a unique certificate number.")


def current(event_id: str, person: str, cert_type: str) -> Optional[dict]:
    from sqlalchemy import select
    from models_pg import Certificate
    with _session() as s:
        row = s.execute(select(Certificate).where(Certificate.event_id == str(event_id),
                                                  Certificate.person_key == person,
                                                  Certificate.cert_type == cert_type,
                                                  Certificate.is_current.is_(True))).scalar_one_or_none()
        return _row_dict(row) if row else None


def by_number(number: str, version: Optional[int] = None) -> Optional[dict]:
    """The current version of a certificate number (or a given version)."""
    from sqlalchemy import select
    from models_pg import Certificate
    with _session() as s:
        q = select(Certificate).where(Certificate.number == number)
        q = q.where(Certificate.version == version) if version else q.where(Certificate.is_current.is_(True))
        row = s.execute(q).scalars().first()
        return _row_dict(row) if row else None


NUMBER_PATTERN = re.compile(r'^SE(-[0-9A-Z]{4}){3}-[0-9A-Z]$')


def looks_like_number(value: str) -> bool:
    return bool(NUMBER_PATTERN.match(str(value or '').strip().upper()))


def versions(number: str) -> List[dict]:
    """Every version of a certificate number, oldest first."""
    from sqlalchemy import select
    from models_pg import Certificate
    with _session() as s:
        q = select(Certificate).where(Certificate.number == number).order_by(Certificate.version)
        return [_row_dict(r) for r in s.execute(q).scalars()]


def _day(value) -> str:
    return value.strftime('%d %B %Y') if hasattr(value, 'strftime') else str(value or '')[:10]


def public_view(number: str, version: Optional[int] = None) -> Optional[dict]:
    """What the public verification page shows (UPG-126): the status, name,
    event, date, type and college; never an email, phone or other personal data.
    Without a version, the current one; a version that was replaced says so."""
    import certificate_pdf
    number = str(number or '').strip().upper()
    every = versions(number)
    if not every:
        return None
    current_row = next((c for c in every if c['is_current']), every[-1])
    cert = current_row if version is None else next((c for c in every if c['version'] == version), None)
    if cert is None:
        return None
    data = cert['data'] or {}
    if cert['status'] == 'revoked':
        state = 'revoked'
    elif not cert['is_current']:
        state = 'replaced'
    else:
        state = 'valid'
    spec = TYPES.get(cert['cert_type'], {})
    return {'number': number, 'version': cert['version'], 'state': state, 'name': cert['name'],
            'event_title': data.get('event_title') or 'Event', 'date': _date_text(data),
            'type_title': spec.get('title', 'Certificate'), 'position': cert.get('position'),
            'college': certificate_pdf.branding()['name'], 'issued_on': _day(cert['issued_at']),
            'revoked_on': _day(cert['revoked_at']) if cert['status'] == 'revoked' else '',
            'current_version': current_row['version'], 'current_issued_on': _day(current_row['issued_at']),
            'versions': len(every)}


def _date_text(data: dict) -> str:
    start, end = _date(data.get('date')), _date(data.get('end_date'))
    if start and end and end != start:
        return f"{start.strftime('%d %B %Y')} to {end.strftime('%d %B %Y')}"
    return start.strftime('%d %B %Y') if start else ''


def for_event(event_id: str, current_only: bool = True) -> List[dict]:
    from sqlalchemy import select
    from models_pg import Certificate
    with _session() as s:
        q = select(Certificate).where(Certificate.event_id == str(event_id))
        if current_only:
            q = q.where(Certificate.is_current.is_(True))
        return [_row_dict(r) for r in s.execute(q.order_by(Certificate.recipient_name)).scalars()]


def for_person(emails: Iterable[str]) -> List[dict]:
    from sqlalchemy import select
    from models_pg import Certificate
    emails = [e.strip().lower() for e in emails if e]
    if not emails:
        return []
    with _session() as s:
        q = (select(Certificate).where(Certificate.recipient_email.in_(emails), Certificate.is_current.is_(True))
             .order_by(Certificate.issued_at.desc()))
        return [_row_dict(r) for r in s.execute(q).scalars()]


def update(cert_id: str, **values) -> None:
    import uuid
    from sqlalchemy import update as sql_update
    from models_pg import Certificate
    with _session() as s, s.begin():
        s.execute(sql_update(Certificate).where(Certificate.id == uuid.UUID(str(cert_id))).values(**values))


def wording(event: dict, recipient: dict) -> dict:
    """What the certificate says, as issued: kept on the record, with the
    signatories and template of that moment (a later change to the event's
    signatories doesn't touch it, UPG-123)."""
    kind = recipient['cert_type']
    spec = TYPES[kind]
    phrase = spec['phrase']
    if kind in AWARD_TYPES and recipient.get('note'):
        phrase = str(recipient['note'])[:160]          # the organiser's own line (UPG-142)
    if kind == 'position' and recipient.get('position'):
        phrase = f"for securing the {_ordinal(recipient['position'])} place in"
    return {'title': spec['title'], 'phrase': phrase, 'event_title': event.get('title') or 'Event',
            'event_type': event.get('event_type') or '', 'department': event.get('department') or '',
            'date': event.get('date') or '', 'end_date': event.get('end_date') or '',
            'designation': recipient.get('designation') or '', 'institution': recipient.get('institution') or '',
            'team': recipient.get('team') or '', 'role': recipient.get('role') or '',
            'hours': recipient.get('hours'), 'points': recipient.get('points'),
            'position': recipient.get('position'),
            'signatories': [{k: sig.get(k) for k in ('id', 'name', 'title', 'order', 'image_key')}
                            for sig in sorted(event.get('cert_signatories') or [], key=lambda x: x.get('order', 0))],
            'style': event.get('cert_style') or 'classic'}


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# ── Issuing ─────────────────────────────────────────────────────────────────

def pdf_key(event_id: str, number: str, version: int) -> str:
    return f"certificates/{event_id}/{number}-v{version}.pdf"


def verify_url(number: str) -> str:
    from utils_email import _base_url
    return f"{_base_url().rstrip('/')}/verify/{number}"


def render(event: dict, cert: dict) -> bytes:
    """The certificate's PDF: its type's template in the event's style, the
    college's branding, and the signatories it was issued with (UPG-123)."""
    import certificate_pdf
    from services_signatories import image_bytes
    data = cert['data']
    signatories = data.get('signatories') or []
    issued = cert.get('issued_at') or datetime.datetime.now(datetime.timezone.utc)
    return certificate_pdf.render(number=cert['number'], name=cert['name'], data=data, cert_type=cert['cert_type'],
                                  signatories=signatories, verify_url=verify_url(cert['number']),
                                  issued_on=issued.strftime('%d %B %Y') if hasattr(issued, 'strftime') else str(issued)[:10],
                                  style=data.get('style') or 'classic', signature_bytes=image_bytes(signatories))


def store_pdf(cert: dict, pdf: bytes) -> dict:
    """Keep the PDF privately with its SHA-256 on the record (a changed file is detectable)."""
    import hashlib
    from utils_storage import put_private
    key = put_private(pdf, pdf_key(cert['event_id'], cert['number'], cert['version']), 'application/pdf')
    digest = hashlib.sha256(pdf).hexdigest()
    update(cert['id'], pdf_key=key, pdf_sha256=digest)
    return dict(cert, pdf_key=key, pdf_sha256=digest)


STALE_AFTER = datetime.timedelta(minutes=10)


def _take_over(cert_id: str) -> bool:
    """A record a failed run left without a PDF, at least STALE_AFTER old: take it
    with a conditional update, so only one run renders it."""
    import uuid
    from sqlalchemy import update as sql_update
    from models_pg import Certificate
    now = datetime.datetime.now(datetime.timezone.utc)
    with _session() as s, s.begin():
        result = s.execute(sql_update(Certificate)
                           .where(Certificate.id == uuid.UUID(str(cert_id)), Certificate.pdf_key.is_(None),
                                  Certificate.issued_at <= now - STALE_AFTER)
                           .values(issued_at=now))
        return result.rowcount == 1


ENDED_STATUSES = ('completed', 'archived')
NOT_HELD_STATUSES = ('draft', 'pending', 'pending_approval', 'changes_requested', 'rejected', 'cancelled')


def _ist_today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()


def event_ended(event: dict) -> bool:
    """Certificates are issued once the event is over: completed, or past its last day (IST)."""
    status = str(event.get('status') or '').lower()
    if status in ENDED_STATUSES:
        return True
    if status in NOT_HELD_STATUSES:
        return False
    days = [d for d in (_date(event.get('date')), _date(event.get('end_date')), _date(event.get('end_datetime'))) if d]
    return bool(days) and max(days) < _ist_today()


def file_check(cert: dict) -> str:
    """'ok' when the stored PDF matches the SHA-256 on the record, 'changed' when
    it doesn't, 'missing' when there's no file (UPG-124)."""
    import hashlib
    from utils_storage import StorageError, get_private
    if not cert.get('pdf_key') or not cert.get('pdf_sha256'):
        return 'missing'
    try:
        data = get_private(cert['pdf_key'])
    except (StorageError, OSError):
        return 'missing'
    return 'ok' if hashlib.sha256(data).hexdigest() == cert['pdf_sha256'] else 'changed'


def require_signatories(event: dict) -> None:
    """No certificate without a signatory who has signed (UPG-123)."""
    from services_signatories import missing_message, ready
    signatories = event.get('cert_signatories') or []
    if not ready(signatories):
        raise CertificateError(missing_message(signatories))


def issue_one(event_id: str, event: dict, recipient: dict, actor: str = '') -> Optional[dict]:
    """Issue this person's certificate of this type, once: None when they have it
    already. Only the run that created the record renders its PDF; a record a
    failed run left without one is taken over after STALE_AFTER."""
    cert = claim(event_id, recipient, wording(event, recipient), actor)
    if cert is None:
        existing = current(event_id, recipient['person_key'], recipient['cert_type'])
        if not existing or existing.get('pdf_key') or not _take_over(existing['id']):
            return None
        cert = existing
    try:
        cert = store_pdf(cert, render(event, cert))
    except Exception:
        _release(cert['id'])          # so a retry can issue it at once (UPG-124)
        raise
    _audit_issue(cert, actor)
    _link_registration(recipient, cert)
    deliver(cert)
    return cert


def _link_registration(recipient: dict, cert: dict) -> None:
    """The lead's registration keeps its certificate's number and link, as before
    UPG-138, for the dashboards, exports and the participant's page. A place
    (winner, runner-up) takes precedence over attendance."""
    if not recipient.get('lead') or not recipient.get('reg_id'):
        return
    if cert['cert_type'] not in ATTENDED_TYPES + POSITION_TYPES:
        return
    try:
        from models import db
        ref = db.collection('registrations').document(recipient['reg_id'])
        reg = ref.get().to_dict() or {}
        if reg.get('certificate_type') in POSITION_TYPES and cert['cert_type'] in ATTENDED_TYPES:
            return
        ref.update({'certificate_id': cert['number'], 'certificate_verify_url': verify_url(cert['number']),
                    'certificate_type': cert['cert_type'],
                    'certificate_issued_at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    except Exception:
        logger.exception("Registration %s not linked to certificate %s", recipient.get('reg_id'), cert.get('number'))


def _audit_issue(cert: dict, actor: str) -> None:
    """Every certificate issued is in the audit log (UPG-127)."""
    try:
        from models import db
        from utils import log_action
        log_action(db, "CERT_ISSUED", f"{actor or 'system'}: {cert['number']} ({cert['cert_type']}) to "
                                      f"{cert['name']} for event {cert['event_id']}")
    except Exception:
        logger.exception("Audit row for certificate %s not written", cert.get('number'))


# ── Delivery (UPG-125) ──────────────────────────────────────────────────────

TOKEN_SALT = 'certificate-download'


def link_days() -> int:
    return max(1, int(os.environ.get('CERT_LINK_DAYS', '30')))


def _secret() -> str:
    """The app's SECRET_KEY, also from a background thread with no app context."""
    from flask import current_app
    try:
        return current_app.config['SECRET_KEY']
    except RuntimeError:
        import app as app_module
        return app_module.app.config['SECRET_KEY']


def _serializer():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(_secret(), salt=TOKEN_SALT)


def download_token(cert: dict) -> str:
    return _serializer().dumps({'n': cert['number'], 'v': cert['version']})


def read_token(token: str) -> dict:
    """{'n': number, 'v': version}; itsdangerous' SignatureExpired or BadSignature if not."""
    return _serializer().loads(token, max_age=link_days() * 86400)


def download_url(cert: dict) -> str:
    from utils_email import _base_url
    return f"{_base_url().rstrip('/')}/certificates/download/{download_token(cert)}"


def deliver(cert: dict) -> None:
    """Queue the certificate's email (sent once; the outbox retries a failure)."""
    if not cert.get('email'):
        return
    import services_hackathon   # a portal-only event: the certificate is in the portal (UPG-195)
    if not services_hackathon.email_allowed_for(cert.get('event_id'), 'certificate'):
        return
    try:
        from tasks.email_tasks import send_certificate_email
        send_certificate_email.delay(cert['id'])
    except Exception:
        logger.exception("Certificate email for %s not queued", cert.get('number'))


def email_once(cert_id: str) -> str:
    """Send the certificate's email unless it was sent: 'sent', 'already' or 'no address'.
    The send is claimed with a conditional update, so it goes out once; a failed
    send gives the claim back for the retry."""
    import uuid
    from sqlalchemy import select
    from sqlalchemy import update as sql_update
    from models_pg import Certificate
    from utils_email import send_certificate_issued_email
    with _session() as s, s.begin():
        claimed = s.execute(sql_update(Certificate)
                            .where(Certificate.id == uuid.UUID(str(cert_id)), Certificate.emailed_at.is_(None))
                            .values(emailed_at=datetime.datetime.now(datetime.timezone.utc))).rowcount == 1
    if not claimed:
        return 'already'
    with _session() as s:
        row = s.execute(select(Certificate).where(Certificate.id == uuid.UUID(str(cert_id)))).scalars().first()
        cert = _row_dict(row)
    if not cert.get('email'):
        return 'no address'
    try:
        ok = send_certificate_issued_email(cert['email'], cert['name'], cert['data'].get('event_title') or 'Event',
                                           TYPES.get(cert['cert_type'], {}).get('title', 'Certificate'), cert['number'],
                                           download_url(cert), verify_url(cert['number']), link_days())
    except Exception:
        ok = False
    if not ok:
        update(cert_id, emailed_at=None)
        raise CertificateError(f"The email for certificate {cert['number']} wasn't sent.")
    return 'sent'


def _release(cert_id: str) -> None:
    """Drop a record whose PDF couldn't be made (only while it has none)."""
    import uuid
    from sqlalchemy import delete
    from models_pg import Certificate
    try:
        with _session() as s, s.begin():
            s.execute(delete(Certificate).where(Certificate.id == uuid.UUID(str(cert_id)), Certificate.pdf_key.is_(None)))
    except Exception:
        logger.exception("Certificate record %s not released; a later run takes it over", cert_id)


def issue_event(db, event_id: str, actor: str = '', only: Optional[Iterable[str]] = None) -> dict:
    """Issue every certificate the event's people are owed (or only these types).
    Counts: issued, already (had one), failed."""
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        raise CertificateError('Event not found.')
    event = doc.to_dict() or {}
    require_signatories(event)
    counts = {'issued': 0, 'already': 0, 'failed': 0}
    wanted = set(only) if only else None
    for r in recipients(db, event_id, event):
        if wanted and r['cert_type'] not in wanted:
            continue
        try:
            if issue_one(event_id, event, r, actor):
                counts['issued'] += 1
            else:
                counts['already'] += 1
        except Exception:
            logger.exception("Certificate for %s (%s) at %s failed", r.get('person_key'), r['cert_type'], event_id)
            counts['failed'] += 1
    return counts


# ── Lists, exports and counts (UPG-128) ─────────────────────────────────────

EXPORT_COLUMNS = ['Number', 'Version', 'Name', 'Email', 'Certificate', 'Place', 'Status', 'Issued on', 'Emailed on']


def list_rows(event_id: str) -> List[dict]:
    """The event's current certificates, for its organisers' list and exports."""
    return [dict(c, type_title=TYPES.get(c['cert_type'], {}).get('title', c['cert_type']),
                 issued_on=_day(c['issued_at']) if c['issued_at'] else '',
                 emailed_on=_day(c['emailed_at']) if c['emailed_at'] else '')
            for c in for_event(event_id)]


def export_rows(rows: List[dict]) -> List[list]:
    return [[r['number'], r['version'], r['name'], r['email'] or '', r['type_title'], r['position'] or '',
             r['status'], r['issued_on'], r['emailed_on']] for r in rows]


def college_counts(db) -> List[dict]:
    """Valid current certificates per department, event type and month of issue:
    a data source for the NAAC/AQAR report (not built yet)."""
    from collections import Counter
    from sqlalchemy import select
    from models_pg import Certificate
    events = {str(d.id): d.to_dict() or {} for d in db.collection('events').stream()}
    counts = Counter()
    with _session() as s:
        q = select(Certificate.event_id, Certificate.issued_at).where(Certificate.is_current.is_(True),
                                                                      Certificate.status == 'valid')
        for event_id, issued_at in s.execute(q):
            event = events.get(str(event_id), {})
            month = issued_at.strftime('%Y-%m') if hasattr(issued_at, 'strftime') else str(issued_at or '')[:7]
            counts[(event.get('department') or 'Not set', event.get('event_type') or event.get('category') or 'Not set',
                    month)] += 1
    return [{'department': d, 'event_type': t, 'month': m, 'certificates': n}
            for (d, t, m), n in sorted(counts.items())]
