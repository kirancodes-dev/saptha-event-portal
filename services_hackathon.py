"""
services_hackathon.py — a hackathon run through the portal, Hack2skill style.

- UPG-195: a per-event email setting. In "portal" mode (the default for a
  hackathon) a participant gets the registration email (with the WhatsApp
  group and "check the portal" instructions), password emails and, at the
  end, the result email to the team lead. Everything else is a portal notice.
- UPG-190: problem statements the SPOC adds after registration opens, each
  released now or at a set time, shown only to registered teams once released.
- UPG-191: a submission form the SPOC builds (short and long text, links, a
  PDF, the problem statement), open between two times the server enforces,
  with deadline extensions.
- UPG-196: what the student's hackathon page shows (stages, countdowns,
  updates).

Everything lives on the event document under `hackathon` (the events table
keeps unknown fields in extra_json); submissions are `project_submissions`
rows with their answers in extra_json.
"""
import datetime
import logging
import re
import uuid
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

PORTAL, ALL = 'portal', 'all'
EMAIL_MODES = (PORTAL, ALL)
# What still goes by email in portal mode (owner, 2026-11-05); a team
# member's confirmation link too, so they can sign in (UPG-207)
PORTAL_MODE_EMAILS = frozenset({'registration', 'password', 'result', 'member_confirm'})

FIELD_KINDS = {
    'text': 'Short text',
    'textarea': 'Long text',
    'link': 'Link (GitHub, deployed app, video…)',
    'pdf': 'PDF upload',
    'problem': 'Choose a problem statement',
}
MAX_FIELDS = 15
TEXT_LIMIT, TEXTAREA_LIMIT, LINK_LIMIT = 200, 5000, 500
DEFAULT_PDF_MB, MAX_PDF_MB = 10, 25
PROBLEM_PDF_MB = 10
MAX_UPDATES = 200
EXTENSION_CHOICES = (15, 30, 60, 120, 360, 720, 1440)   # minutes the SPOC picks from
MAX_EXTENSION_MINUTES = 7 * 24 * 60
INACTIVE = {'cancelled', 'waitlisted'}
_URL = re.compile(r'^https?://[^\s/$.?#][^\s]*$', re.I)


def _now() -> datetime.datetime:
    """The server's clock, in UTC (tests move it)."""
    return datetime.datetime.now(datetime.timezone.utc)


# ── The event ───────────────────────────────────────────────────────────────

def is_hackathon(event: dict) -> bool:
    from services_event_types import TYPES, get_type
    return get_type(str((event or {}).get('event_type') or '')) is TYPES['hackathon']


def email_mode(event: dict) -> str:
    """'portal' or 'all'. Not set: portal for a hackathon, all for the rest."""
    mode = str((event or {}).get('participant_emails') or '').strip().lower()
    if mode in EMAIL_MODES:
        return mode
    return PORTAL if is_hackathon(event) else ALL


def portal_only(event: dict) -> bool:
    return email_mode(event) == PORTAL


def email_allowed(event: dict, kind: str) -> bool:
    """May a participant email of this kind go out for this event?
    kind: registration, password, result, or anything else (ticket, reminder,
    round, broadcast, room, certificate, team, waitlist, feedback, change)."""
    return not portal_only(event) or kind in PORTAL_MODE_EMAILS


def email_allowed_for(event_id, kind: str, db=None) -> bool:
    """email_allowed for an event known only by its ID (True if it can't be read)."""
    if db is None:
        from models import db
    try:
        doc = db.collection('events').document(str(event_id)).get()
    except Exception:
        return True
    return email_allowed(doc.to_dict() or {}, kind) if doc.exists else True


def data(event: dict) -> dict:
    h = (event or {}).get('hackathon')
    return dict(h) if isinstance(h, dict) else {}


def _save(db, event_id: str, h: dict) -> None:
    db.collection('events').document(str(event_id)).update({'hackathon': h})


def group_link(event: dict) -> str:
    contact = (event or {}).get('contact') or {}
    link = contact.get('group_link') if isinstance(contact, dict) else ''
    return str(link or (event or {}).get('group_link') or '').strip()


def portal_url(event_id: str) -> str:
    from utils_email import _base_url
    return f"{_base_url().rstrip('/')}/hackathon/{event_id}"


def registration_instructions(event: dict, event_id: str) -> dict | None:
    """What the registration email tells a portal-mode team (UPG-195)."""
    if not portal_only(event):
        return None
    return {'group_link': group_link(event), 'portal_url': portal_url(event_id)}


# ── Times (the SPOC types the event's local time; stored in UTC) ────────────

def _tz(event: dict):
    try:
        return ZoneInfo((event or {}).get('timezone') or 'Asia/Kolkata')
    except Exception:
        return ZoneInfo('Asia/Kolkata')


def parse_local(value: str, event: dict) -> datetime.datetime | None:
    """'2026-11-20T18:00' in the event's time zone → an aware UTC datetime."""
    value = str(value or '').strip()
    if not value:
        return None
    try:
        local = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if local.tzinfo is None:
        local = local.replace(tzinfo=_tz(event))
    return local.astimezone(datetime.timezone.utc)


def parse_iso(value) -> datetime.datetime | None:
    if not value:
        return None
    try:
        when = datetime.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=datetime.timezone.utc)


def local_input(value, event: dict) -> str:
    """An ISO UTC time as a datetime-local input value in the event's zone."""
    when = parse_iso(value)
    return when.astimezone(_tz(event)).strftime('%Y-%m-%dT%H:%M') if when else ''


def show(value, event: dict) -> str:
    """'20 Nov 2026, 6:00 PM IST' for people."""
    when = parse_iso(value)
    if not when:
        return ''
    local = when.astimezone(_tz(event))
    return local.strftime('%d %b %Y, %I:%M %p ').lstrip('0') + (local.tzname() or '')


def _iso(when: datetime.datetime) -> str:
    return when.astimezone(datetime.timezone.utc).isoformat()


# ── Portal notices and the updates feed ─────────────────────────────────────

def notify(db, event: dict, reg: dict, title: str, message: str, link: str = '',
           kind: str = 'announcement') -> int:
    """A portal notice to each person on a team (no email). Returns how many."""
    from routes_notifications_v2 import create_notification
    from services_recipients import registration_people
    count = 0
    for email, _name, _phone in registration_people(reg, everyone=True):
        try:
            create_notification(db, user_email=email, notif_type=kind, title=title, message=message,
                                link=link, metadata={'event_id': str((event or {}).get('id') or '')})
            count += 1
        except Exception:
            log.warning("Portal notice to %s failed", email, exc_info=True)
    return count


def post_update(db, event_id: str, event: dict, title: str, message: str = '',
                kind: str = 'update', by: str = '') -> dict:
    """An update on the hackathon's feed, which every registered team sees."""
    h = data(event)
    item = {'id': uuid.uuid4().hex[:10], 'at': _iso(_now()), 'title': str(title)[:200],
            'message': str(message)[:2000], 'kind': kind, 'by': by}
    h['updates'] = (list(h.get('updates') or []) + [item])[-MAX_UPDATES:]
    _save(db, event_id, h)
    event['hackathon'] = h
    return item


def updates(event: dict) -> list:
    return sorted(data(event).get('updates') or [], key=lambda u: u.get('at') or '', reverse=True)


def set_email_mode(db, event_id: str, mode: str) -> bool:
    if mode not in EMAIL_MODES:
        return False
    db.collection('events').document(str(event_id)).update({'participant_emails': mode})
    return True


# ── Problem statements (UPG-190) ────────────────────────────────────────────

def problems(event: dict) -> list:
    return list(data(event).get('problem_statements') or [])


def is_released(problem: dict, now: datetime.datetime | None = None) -> bool:
    at = parse_iso(problem.get('release_at'))
    return bool(at) and at <= (now or _now())


def released_problems(event: dict, now: datetime.datetime | None = None) -> list:
    return [p for p in problems(event) if is_released(p, now)]


def next_release(event: dict, now: datetime.datetime | None = None):
    """The earliest scheduled release still to come, or None."""
    now = now or _now()
    times = [parse_iso(p.get('release_at')) for p in problems(event)]
    future = [t for t in times if t and t > now]
    return min(future) if future else None


def _pdf_ok(raw: bytes, limit_mb: int) -> str:
    if not raw:
        return ''
    if len(raw) > limit_mb * 1024 * 1024:
        return f"The PDF is larger than {limit_mb} MB."
    if not raw.startswith(b'%PDF-'):
        return "That file isn't a PDF."
    return ''


def add_problem(db, event_id: str, event: dict, *, title: str, description: str, track: str = '',
                release: str = 'now', release_at: str = '', pdf: bytes = b'', pdf_name: str = '',
                by: str = '') -> tuple:
    """(ok, message). release: 'now' or 'later' (with release_at, event local time)."""
    title, description = str(title or '').strip()[:200], str(description or '').strip()[:10000]
    if not title or not description:
        return False, "A problem statement needs a title and a description."
    if release == 'later':
        when = parse_local(release_at, event)
        if not when:
            return False, "Choose when the problem statement is released."
        if when <= _now():
            return False, "The release time has passed; choose a later time or release it now."
    else:
        when = _now()
    error = _pdf_ok(pdf, PROBLEM_PDF_MB)
    if error:
        return False, error
    pid = uuid.uuid4().hex[:10]
    item = {'id': pid, 'title': title, 'description': description, 'track': str(track or '').strip()[:100],
            'release_at': _iso(when), 'created_at': _iso(_now()), 'created_by': by,
            'pdf_key': '', 'pdf_name': ''}
    if pdf:
        from utils_storage import put_private
        item['pdf_key'] = put_private(pdf, f"hackathon/{event_id}/problems/{pid}.pdf", 'application/pdf')
        item['pdf_name'] = (re.sub(r'[^\w.\- ]', '', pdf_name or '') or 'problem.pdf')[:120]
    h = data(event)
    h['problem_statements'] = problems(event) + [item]
    _save(db, event_id, h)
    event['hackathon'] = h
    if release != 'later':
        post_update(db, event_id, event, f"Problem statement released: {title}",
                    "Open the Problem statements section to read it.", kind='problems', by=by)
        return True, f"“{title}” is released; registered teams see it now."
    return True, f"“{title}” will be released on {show(item['release_at'], event)}."


def release_now(db, event_id: str, event: dict, pid: str, by: str = '') -> tuple:
    h = data(event)
    items = problems(event)
    for p in items:
        if p.get('id') == pid:
            if is_released(p):
                return False, "It is already released."
            p['release_at'] = _iso(_now())
            h['problem_statements'] = items
            _save(db, event_id, h)
            event['hackathon'] = h
            post_update(db, event_id, event, f"Problem statement released: {p.get('title')}",
                        "Open the Problem statements section to read it.", kind='problems', by=by)
            return True, f"“{p.get('title')}” is released."
    return False, "Problem statement not found."


def remove_problem(db, event_id: str, event: dict, pid: str) -> tuple:
    h = data(event)
    items = problems(event)
    keep = [p for p in items if p.get('id') != pid]
    if len(keep) == len(items):
        return False, "Problem statement not found."
    if released_problems({'hackathon': {'problem_statements': [p for p in items if p.get('id') == pid]}}):
        return False, "A released problem statement can't be removed; teams may have chosen it."
    h['problem_statements'] = keep
    _save(db, event_id, h)
    event['hackathon'] = h
    return True, "Removed."


def find_problem(event: dict, pid: str) -> dict | None:
    return next((p for p in problems(event) if p.get('id') == pid), None)


# ── The submission form (UPG-191) ───────────────────────────────────────────

def form(event: dict) -> dict:
    f = data(event).get('submission_form')
    return dict(f) if isinstance(f, dict) else {}


def has_form(event: dict) -> bool:
    return bool(form(event).get('fields'))


def closes_at(event: dict):
    return parse_iso(form(event).get('closes_at'))


def opens_at(event: dict):
    return parse_iso(form(event).get('opens_at'))


def window(event: dict, now: datetime.datetime | None = None) -> str:
    """not_set, not_open, open or closed — by the server's clock."""
    now = now or _now()
    start, end = opens_at(event), closes_at(event)
    if not has_form(event) or not start or not end:
        return 'not_set'
    if now < start:
        return 'not_open'
    if now >= end:
        return 'closed'
    return 'open'


def parse_fields(form_data) -> tuple:
    """(fields, error) from the builder's field_N_* inputs."""
    numbers = sorted({int(m.group(1)) for key in form_data.keys()
                      for m in [re.fullmatch(r'field_(\d+)_label', key)] if m})
    fields, labels = [], set()
    for i in numbers:
        label = str(form_data.get(f'field_{i}_label') or '').strip()[:120]
        if not label:
            continue
        kind = str(form_data.get(f'field_{i}_kind') or 'text')
        if kind not in FIELD_KINDS:
            return [], f"“{label}” has an unknown type."
        if label.lower() in labels:
            return [], f"Two fields are called “{label}”."
        labels.add(label.lower())
        field: dict = {'id': str(form_data.get(f'field_{i}_id') or '').strip()[:20] or uuid.uuid4().hex[:8],
                 'label': label, 'kind': kind,
                 'required': str(form_data.get(f'field_{i}_required') or '') in ('on', 'yes', '1', 'true'),
                 'help': str(form_data.get(f'field_{i}_help') or '').strip()[:300]}
        if not re.fullmatch(r'[a-f0-9]{1,20}', field['id']):
            field['id'] = uuid.uuid4().hex[:8]
        if kind == 'pdf':
            try:
                mb = int(form_data.get(f'field_{i}_max_mb') or DEFAULT_PDF_MB)
            except ValueError:
                mb = DEFAULT_PDF_MB
            field['max_mb'] = max(1, min(MAX_PDF_MB, mb))
        fields.append(field)
    if not fields:
        return [], "Add at least one field."
    if len(fields) > MAX_FIELDS:
        return [], f"A form can have at most {MAX_FIELDS} fields."
    if sum(1 for f in fields if f['kind'] == 'problem') > 1:
        return [], "Only one field can choose the problem statement."
    return fields, ''


def save_form(db, event_id: str, event: dict, form_data, by: str = '') -> tuple:
    fields, error = parse_fields(form_data)
    if error:
        return False, error
    start = parse_local(form_data.get('opens_at'), event)
    end = parse_local(form_data.get('closes_at'), event)
    if not start or not end:
        return False, "Set when submissions open and close."
    if end <= start:
        return False, "Submissions must close after they open."
    h = data(event)
    old = form(event)
    h['submission_form'] = {'fields': fields, 'opens_at': _iso(start), 'closes_at': _iso(end),
                            'extensions': list(old.get('extensions') or []),
                            'updated_at': _iso(_now()), 'updated_by': by}
    _save(db, event_id, h)
    event['hackathon'] = h
    if not old.get('fields'):
        post_update(db, event_id, event, "Submission form published",
                    f"Submissions open {show(h['submission_form']['opens_at'], event)} and close "
                    f"{show(h['submission_form']['closes_at'], event)}.", kind='submission', by=by)
    elif old.get('closes_at') != h['submission_form']['closes_at']:
        post_update(db, event_id, event, "Submission deadline changed",
                    f"Submissions now close {show(h['submission_form']['closes_at'], event)}.",
                    kind='deadline', by=by)
    return True, "Submission form saved."


def extend_deadline(db, event_id: str, event: dict, minutes, reason: str = '', by: str = '') -> tuple:
    """Move the deadline later by `minutes` from the current deadline (UPG-191).
    Works after the deadline has passed too, as long as the new one is ahead."""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return False, "Choose how long to extend by."
    if minutes <= 0 or minutes > MAX_EXTENSION_MINUTES:
        return False, "An extension is between 1 minute and 7 days."
    f = form(event)
    end = closes_at(event)
    if not f.get('fields') or not end:
        return False, "Set up the submission form first."
    new_end = end + datetime.timedelta(minutes=minutes)
    if new_end <= _now():
        return False, (f"Extending by {_duration(minutes)} still ends in the past "
                       f"({show(_iso(new_end), event)}). Choose a longer extension.")
    f['extensions'] = list(f.get('extensions') or []) + [{
        'minutes': minutes, 'from': _iso(end), 'to': _iso(new_end), 'at': _iso(_now()), 'by': by,
        'reason': str(reason or '').strip()[:300]}]
    f['closes_at'] = _iso(new_end)
    h = data(event)
    h['submission_form'] = f
    _save(db, event_id, h)
    event['hackathon'] = h
    note = f" Reason: {f['extensions'][-1]['reason']}" if f['extensions'][-1]['reason'] else ''
    post_update(db, event_id, event, f"Deadline extended by {_duration(minutes)}",
                f"Submissions now close {show(f['closes_at'], event)}.{note}", kind='deadline', by=by)
    return True, f"Deadline extended by {_duration(minutes)} to {show(f['closes_at'], event)}."


def _duration(minutes: int) -> str:
    days, rest = divmod(int(minutes), 1440)
    hours, mins = divmod(rest, 60)
    parts = [f"{n} {unit}{'s' if n != 1 else ''}" for n, unit in ((days, 'day'), (hours, 'hour'), (mins, 'minute')) if n]
    return ' '.join(parts) or '0 minutes'


# ── Teams and their submissions ─────────────────────────────────────────────

def _status(reg: dict) -> str:
    return str(reg.get('status') or '').strip().lower()


def team_for(db, event_id: str, email):
    """(reg_id, reg) of the active registration this account leads, or (None, None).
    Looks only at this event's registrations, by lead email (indexed)."""
    email = str(email or '').strip().lower()
    if not email:
        return None, None
    from services_event_types import id_variants
    for eid in id_variants(event_id):
        for doc in db.collection('registrations').where('event_id', '==', eid).where('lead_email', '==', email).stream():
            reg = doc.to_dict() or {}
            if _status(reg) not in INACTIVE:
                return doc.id, reg
    return None, None


def submission_for(db, reg_id: str):
    """(sub_id, submission) for a registration, or (None, {})."""
    for doc in db.collection('project_submissions').where('registration_id', '==', str(reg_id)).stream():
        return doc.id, doc.to_dict() or {}
    return None, {}


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value == {}


def submit(db, event_id: str, event: dict, reg_id: str, reg: dict, form_data, files, by: str) -> tuple:
    """(ok, message, errors) — the team lead's submission, created or edited.
    The window is checked here, by the server's clock: nothing is saved after
    the deadline, whatever the browser sends."""
    state = window(event)
    if state == 'not_set':
        return False, "The organisers haven't opened submissions yet.", {}
    if state == 'not_open':
        return False, f"Submissions open on {show(form(event)['opens_at'], event)}.", {}
    if state == 'closed':
        return False, (f"The deadline ({show(form(event)['closes_at'], event)}) has passed. "
                       "Submissions are closed."), {}
    if str(reg.get('lead_email') or '').strip().lower() != str(by or '').strip().lower():
        return False, "Only the team lead can submit.", {}
    if reg.get('is_eliminated'):
        return False, "Your team is no longer in the hackathon.", {}

    sub_id, existing = submission_for(db, reg_id)
    old_answers = dict(existing.get('answers') or {})
    answers, errors, uploads = {}, {}, []
    released = {p['id']: p for p in released_problems(event)}
    for field in form(event)['fields']:
        fid, kind, label = field['id'], field['kind'], field['label']
        if kind == 'pdf':
            upload = files.get(f'f_{fid}') if files else None
            raw = upload.read() if upload and getattr(upload, 'filename', '') else b''
            if raw:
                error = _pdf_ok(raw, field.get('max_mb') or DEFAULT_PDF_MB)
                if error:
                    errors[fid] = error
                    continue
                uploads.append((fid, raw, getattr(upload, 'filename', '')))
                answers[fid] = {'pending': True}
            elif old_answers.get(fid):
                answers[fid] = old_answers[fid]
            elif field.get('required'):
                errors[fid] = f"Upload {label}."
            continue
        value = str(form_data.get(f'f_{fid}') or '').strip()
        if not value:
            if field.get('required'):
                errors[fid] = f"{label} is required."
            continue
        if kind == 'text' and len(value) > TEXT_LIMIT:
            errors[fid] = f"{label}: at most {TEXT_LIMIT} characters."
        elif kind == 'textarea' and len(value) > TEXTAREA_LIMIT:
            errors[fid] = f"{label}: at most {TEXTAREA_LIMIT} characters."
        elif kind == 'link' and (len(value) > LINK_LIMIT or not _URL.match(value)):
            errors[fid] = f"{label}: enter a full link starting with https://"
        elif kind == 'problem' and value not in released:
            errors[fid] = "Choose one of the released problem statements."
        else:
            answers[fid] = value
    if errors:
        return False, "Please fix the highlighted fields.", errors

    from utils_storage import put_private
    for fid, raw, filename in uploads:
        key = put_private(raw, f"hackathon/{event_id}/submissions/{reg_id}/{fid}-{uuid.uuid4().hex[:8]}.pdf",
                          'application/pdf')
        answers[fid] = {'key': key, 'name': (re.sub(r'[^\w.\- ]', '', filename or '') or 'file.pdf')[:120],
                        'size': len(raw)}

    problem_field = next((f for f in form(event)['fields'] if f['kind'] == 'problem'), None)
    problem_id = answers.get(problem_field['id'], '') if problem_field else ''
    title_field = next((f for f in form(event)['fields'] if f['kind'] == 'text' and answers.get(f['id'])), None)
    team_name = reg.get('team_name') or reg.get('lead_name') or 'Team'
    now = _iso(_now())
    record = {
        'event_id': str(event_id), 'registration_id': str(reg_id), 'team_name': team_name,
        'project_title': (answers[title_field['id']] if title_field else '') or team_name,
        'answers': answers, 'problem_id': problem_id,
        'problem_title': (released.get(problem_id) or {}).get('title', ''),
        'updated_at': now, 'last_edited_by': by,
        'versions': int(existing.get('versions') or 0) + 1,
    }
    if sub_id:
        db.collection('project_submissions').document(sub_id).set(record, merge=True)
        message = "Your submission is updated. You can keep editing it until the deadline."
    else:
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        record.update({'submitted_at': now, 'milestone_stage': 'Ideation'})
        db.collection('project_submissions').document(sub_id).set(record)
        message = "Your submission is in. You can edit it until the deadline."
    notify(db, {**event, 'id': event_id}, reg, f"Submission saved: {event.get('title', 'Hackathon')}",
           f"Your team's submission was saved on {show(now, event)}.", link=f"/hackathon/{event_id}",
           kind='announcement')
    return True, message, {}


def submissions(db, event_id: str) -> list:
    """Every submission for an event, newest first, with its registration ID."""
    from services_event_types import id_variants
    seen, out = set(), []
    for eid in id_variants(event_id):
        for doc in db.collection('project_submissions').where('event_id', '==', eid).stream():
            if doc.id not in seen:
                seen.add(doc.id)
                out.append({**(doc.to_dict() or {}), 'id': doc.id})
    return sorted(out, key=lambda s: str(s.get('updated_at') or ''), reverse=True)


# ── The student's page (UPG-196) ────────────────────────────────────────────

def _event_day(event: dict):
    raw = str((event or {}).get('date') or '')[:10]
    try:
        day = datetime.date.fromisoformat(raw)
    except ValueError:
        return None
    return datetime.datetime.combine(day, datetime.time(0, 0), tzinfo=_tz(event))


def _reg_closes(event: dict):
    raw = str((event or {}).get('reg_deadline') or (event or {}).get('deadline') or '')[:10]
    try:
        day = datetime.date.fromisoformat(raw)
    except ValueError:
        return None
    return datetime.datetime.combine(day, datetime.time(23, 59, 59), tzinfo=_tz(event))


def stages(event: dict, reg: dict | None = None, submission: dict | None = None,
           now: datetime.datetime | None = None) -> list:
    """The stage tracker: each {key, label, state (done, current, upcoming),
    note, countdown_to (ISO, or '')}."""
    now = now or _now()
    out = []

    def add(key, label, state, note='', countdown_to=None):
        out.append({'key': key, 'label': label, 'state': state, 'note': note,
                    'countdown_to': _iso(countdown_to) if countdown_to else ''})

    reg_end = _reg_closes(event)
    add('registration', 'Registration', 'done', 'Your team is registered.')
    if reg_end and now < reg_end:
        out[-1]['note'] = f"Registration closes {show(_iso(reg_end), event)}."

    released, upcoming = released_problems(event, now), next_release(event, now)
    if released:
        add('problems', 'Problem statements', 'done', f"{len(released)} released.")
    elif upcoming:
        add('problems', 'Problem statements', 'current', f"Released on {show(_iso(upcoming), event)}.", upcoming)
    else:
        add('problems', 'Problem statements', 'upcoming', "Coming soon. Check back here.")

    state = window(event, now)
    done_note = 'Submitted.' if submission else 'Not submitted.'
    if state == 'not_set':
        add('submission', 'Submission', 'upcoming', "The submission form isn't open yet.")
    elif state == 'not_open':
        add('submission', 'Submission', 'upcoming', f"Opens {show(form(event)['opens_at'], event)}.", opens_at(event))
    elif state == 'open':
        add('submission', 'Submission', 'current',
            f"Closes {show(form(event)['closes_at'], event)}. " + ('Submitted; you can still edit.' if submission
                                                                   else 'Not submitted yet.'), closes_at(event))
    else:
        add('submission', 'Submission', 'done', f"Closed {show(form(event)['closes_at'], event)}. {done_note}")

    reg = reg or {}
    shortlisted = int(event.get('active_round') or 1) > 1 or bool(event.get('shortlist_published'))
    results = bool(event.get('results_published'))
    if reg.get('is_eliminated'):
        add('shortlist', 'Evaluation & shortlist', 'done', "Your team wasn't shortlisted this time.")
    elif shortlisted:
        add('shortlist', 'Evaluation & shortlist', 'done', "Your team is shortlisted for the finale.")
    elif state == 'closed':
        add('shortlist', 'Evaluation & shortlist', 'current', "Submissions are being evaluated.")
    else:
        add('shortlist', 'Evaluation & shortlist', 'upcoming', "After the submission deadline.")

    day = _event_day(event)
    if results:
        add('finale', 'Finale', 'done')
    elif day and now >= day and shortlisted:
        add('finale', 'Finale', 'current', "Shortlisted teams present to the judges.")
    else:
        add('finale', 'Finale', 'upcoming', f"On {show(_iso(day), event).split(',')[0]}." if day else '',
            day if day and now < day and shortlisted else None)

    add('results', 'Results', 'done' if results else 'upcoming',
        "Results are out." if results else "Announced here after the finale.")
    return out


def page_version(event: dict, reg: dict | None, submission: dict | None,
                 now: datetime.datetime | None = None) -> str:
    """Changes whenever what the student's page shows changes (for the
    60-second poll)."""
    import hashlib
    now = now or _now()
    parts = [
        ','.join(u.get('id', '') for u in updates(event)),
        ','.join(p.get('id', '') for p in released_problems(event, now)),
        str(form(event).get('opens_at')), str(form(event).get('closes_at')), window(event, now),
        str(len(form(event).get('fields') or [])), str(form(event).get('updated_at')),
        str((reg or {}).get('is_eliminated')), str((reg or {}).get('current_round')),
        str(event.get('active_round')), str(event.get('results_published')), group_link(event),
        str((submission or {}).get('updated_at')),
    ]
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:16]
