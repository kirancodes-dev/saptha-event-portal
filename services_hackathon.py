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
- UPG-321: a time when each team's lead chooses one problem statement (a cap
  per problem statement, lock, reopen, extend, the SPOC assigns); the
  submission is for the chosen one.

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


def update_key(item: dict) -> str:
    """How one update is named for deleting: its id (older ones: its time)."""
    return str(item.get('id') or item.get('at') or '')


def remove_update(db, event_id: str, event: dict, key: str):
    """Take one update off the feed (UPG-323). Returns the removed update,
    or None when there is no such update."""
    h = data(event)
    items = list(h.get('updates') or [])
    gone = next((u for u in items if key and update_key(u) == key), None)
    if gone is None:
        return None
    h['updates'] = [u for u in items if u is not gone]
    _save(db, event_id, h)
    event['hackathon'] = h
    return gone


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


# ── Choosing a problem statement (UPG-321) ──────────────────────────────────
#
# The SPOC sets a time when teams choose (opens_at, closes_at), optionally a
# cap of teams per problem statement, and can lock it early, reopen it and
# extend it. Each team's lead chooses one released problem statement on the
# hackathon page while it is open and may change it until it closes; then it
# is locked and the submission uses it, whatever the form sends. The SPOC
# assigns one to a team that didn't choose (or changes one). A hackathon with
# no selection time works as before: the team picks on the submission form.
#
# The cap is counted in ticket_type_sales under "<event_id>:problem:<pid>"
# (the seat counter of UPG-155), taken with one conditional UPDATE, so two
# teams can't both get the last place.

def selection(event: dict) -> dict:
    s = data(event).get('selection')
    return dict(s) if isinstance(s, dict) else {}


def _selection_times(event: dict) -> tuple:
    """(opens, closes) as datetimes, or (None, None) when either isn't set."""
    s = selection(event)
    start, end = parse_iso(s.get('opens_at')), parse_iso(s.get('closes_at'))
    return (start, end) if start and end else (None, None)


def selection_on(event: dict) -> bool:
    """The SPOC has set a time for teams to choose."""
    return _selection_times(event)[0] is not None


def selection_window(event: dict, now: datetime.datetime | None = None) -> str:
    """not_set, not_open, open, locked (by the SPOC) or closed (time over)."""
    start, end = _selection_times(event)
    if start is None or end is None:
        return 'not_set'
    now = now or _now()
    if selection(event).get('locked'):
        return 'locked'
    if now < start:
        return 'not_open'
    if now >= end:
        return 'closed'
    return 'open'


def selection_cap(event: dict) -> int:
    try:
        return max(0, int(selection(event).get('cap') or 0))
    except (TypeError, ValueError):
        return 0


def choice_of(reg: dict | None) -> dict:
    c = (reg or {}).get('problem_choice')
    return dict(c) if isinstance(c, dict) and c.get('pid') else {}


def _save_selection(db, event_id: str, event: dict, s: dict) -> None:
    h = data(event)
    h['selection'] = s
    _save(db, event_id, h)
    event['hackathon'] = h


def save_selection(db, event_id: str, event: dict, form_data, by: str = '') -> tuple:
    """(ok, message): when teams choose, and the most teams per problem statement."""
    start = parse_local(form_data.get('sel_opens_at'), event)
    end = parse_local(form_data.get('sel_closes_at'), event)
    if not start or not end:
        return False, "Set when teams start and stop choosing."
    if end <= start:
        return False, "Choosing must close after it opens."
    try:
        cap = int(str(form_data.get('cap') or '0').strip() or 0)
    except ValueError:
        return False, "The most teams per problem statement is a whole number (0 for no limit)."
    if cap < 0 or cap > 10000:
        return False, "The most teams per problem statement is between 0 (no limit) and 10000."
    old = selection(event)
    s = {'opens_at': _iso(start), 'closes_at': _iso(end), 'cap': cap, 'locked': bool(old.get('locked')),
         'extensions': list(old.get('extensions') or []), 'updated_at': _iso(_now()), 'updated_by': by}
    _save_selection(db, event_id, event, s)
    cap_note = f" Each problem statement takes at most {cap} team{'s' if cap != 1 else ''}." if cap else ''
    if not old.get('opens_at'):
        post_update(db, event_id, event, "Choose your problem statement",
                    f"Team leads choose one problem statement on this page between {show(s['opens_at'], event)} "
                    f"and {show(s['closes_at'], event)}. Your submission will be for the one you choose."
                    + cap_note, kind='problems', by=by)
    elif (old.get('opens_at'), old.get('closes_at'), old.get('cap')) != (s['opens_at'], s['closes_at'], cap):
        post_update(db, event_id, event, "Problem statement choice: times changed",
                    f"Choosing is open {show(s['opens_at'], event)} to {show(s['closes_at'], event)}." + cap_note,
                    kind='problems', by=by)
    return True, "The time to choose a problem statement is saved."


def extend_selection(db, event_id: str, event: dict, minutes, reason: str = '', by: str = '') -> tuple:
    """Move the close later by `minutes` from the current close, even after it
    passed; an extension also lifts the SPOC's lock (it gives teams more time)."""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return False, "Choose how long to extend by."
    if minutes <= 0 or minutes > MAX_EXTENSION_MINUTES:
        return False, "An extension is between 1 minute and 7 days."
    end = _selection_times(event)[1]
    if end is None:
        return False, "Set the time to choose a problem statement first."
    s = selection(event)
    new_end = end + datetime.timedelta(minutes=minutes)
    if new_end <= _now():
        return False, (f"Extending by {_duration(minutes)} still ends in the past "
                       f"({show(_iso(new_end), event)}). Choose a longer extension.")
    s['extensions'] = list(s.get('extensions') or []) + [{
        'minutes': minutes, 'from': _iso(end), 'to': _iso(new_end), 'at': _iso(_now()), 'by': by,
        'reason': str(reason or '').strip()[:300]}]
    s['closes_at'], s['locked'] = _iso(new_end), False
    _save_selection(db, event_id, event, s)
    note = f" Reason: {s['extensions'][-1]['reason']}" if s['extensions'][-1]['reason'] else ''
    post_update(db, event_id, event, f"Problem statement choice extended by {_duration(minutes)}",
                f"Team leads can choose or change until {show(s['closes_at'], event)}.{note}",
                kind='problems', by=by)
    return True, f"Choosing extended by {_duration(minutes)} to {show(s['closes_at'], event)}."


def lock_selection(db, event_id: str, event: dict, by: str = '') -> tuple:
    if not selection_on(event):
        return False, "Set the time to choose a problem statement first."
    s = selection(event)
    if s.get('locked'):
        return False, "Choosing is already locked."
    s.update(locked=True, locked_at=_iso(_now()), locked_by=by)
    _save_selection(db, event_id, event, s)
    post_update(db, event_id, event, "Problem statements are locked",
                "Choosing is closed. Your team's problem statement is the one shown on this page; "
                "your submission will be for it.", kind='problems', by=by)
    return True, "Locked. Teams can no longer choose or change."


def reopen_selection(db, event_id: str, event: dict, by: str = '') -> tuple:
    if not selection_on(event):
        return False, "Set the time to choose a problem statement first."
    s, end = selection(event), _selection_times(event)[1]
    if not s.get('locked'):
        return False, "Choosing isn't locked."
    if end is None or end <= _now():
        return False, "The time to choose has passed. Extend it to reopen."
    s.update(locked=False, locked_at='', locked_by='')
    _save_selection(db, event_id, event, s)
    post_update(db, event_id, event, "Problem statement choice reopened",
                f"Team leads can choose or change until {show(s['closes_at'], event)}.", kind='problems', by=by)
    return True, "Reopened."


def _cap_key(pid: str) -> str:
    return f"problem:{pid}"


def taken(event_id: str, event: dict) -> dict:
    """{problem id: teams that have it}, from the counter (one query)."""
    from db_pg import get_session
    from models_pg import TicketTypeSale
    import services_ticket_types as tt
    keys = {tt._key(str(event_id), _cap_key(p['id'])): p['id'] for p in problems(event)}
    if not keys:
        return {}
    out = {pid: 0 for pid in keys.values()}
    with get_session() as s:
        for key, sold in s.query(TicketTypeSale.key, TicketTypeSale.sold).filter(TicketTypeSale.key.in_(list(keys))):
            out[keys[key]] = int(sold or 0)
    return out


def _take(event_id: str, pid: str, cap: int) -> bool:
    import services_ticket_types as tt
    return tt.take_seat(str(event_id), {'id': _cap_key(pid), 'seats': cap})


def _give_back(event_id: str, pid: str) -> None:
    import services_ticket_types as tt
    if pid:
        tt.give_back_seat(str(event_id), _cap_key(pid))


def _free_cancelled(db, event_id: str, pid: str) -> int:
    """Give back the places of teams that chose `pid` and were cancelled (or
    moved to the waitlist) since. Each team's place is given back once: a row
    "<event_id>:problem-freed:<pid>:<reg_id>" is created first, and only the
    request that creates it gives the place back, so two requests at once
    can't free it twice. The team's choice is cleared. Returns how many."""
    from sqlalchemy.exc import IntegrityError

    from db_pg import get_session
    from models_pg import TicketTypeSale
    from services_event_types import id_variants
    import services_ticket_types as tt
    freed = 0
    for eid in id_variants(event_id):
        for doc in db.collection('registrations').where('event_id', '==', eid).stream():
            reg = doc.to_dict() or {}
            if choice_of(reg).get('pid') != pid or _status(reg) not in INACTIVE | {'refunded'}:
                continue
            try:
                with get_session() as s:
                    s.add(TicketTypeSale(key=tt._key(str(event_id), f"problem-freed:{pid}:{doc.id}"), sold=1))
            except IntegrityError:
                continue                       # freed already, by this or another request
            _give_back(event_id, pid)
            db.collection('registrations').document(doc.id).update({'problem_choice': None})
            freed += 1
    return freed


def _set_choice(db, event: dict, reg_id: str, problem: dict, by: str, by_spoc: bool) -> None:
    choice = {'pid': problem['id'], 'title': problem.get('title', ''), 'at': _iso(_now()), 'by': by,
              'set_by_spoc': by_spoc}
    db.collection('registrations').document(str(reg_id)).update({'problem_choice': choice})
    # A submission made before the change follows it, so everything after
    # (scoring, marks, results) reads the team's one problem statement
    sub_id, sub = submission_for(db, reg_id)
    if sub_id:
        answers = dict(sub.get('answers') or {})
        field = next((f for f in form(event).get('fields') or [] if f.get('kind') == 'problem'), None)
        if field:
            answers[field['id']] = problem['id']
        db.collection('project_submissions').document(sub_id).set(
            {'problem_id': problem['id'], 'problem_title': problem.get('title', ''), 'answers': answers}, merge=True)


def choose(db, event_id: str, event: dict, reg_id: str, reg: dict, pid: str, by: str) -> tuple:
    """(ok, message): the team lead chooses, or changes, the team's problem
    statement while choosing is open. Checked here, by the server's clock."""
    state = selection_window(event)
    s = selection(event)
    if state == 'not_set':
        return False, "Choosing a problem statement isn't open."
    if state == 'not_open':
        return False, f"Choosing opens on {show(s['opens_at'], event)}."
    if state in ('closed', 'locked'):
        return False, "Choosing is closed; your team's problem statement is locked."
    if str(reg.get('lead_email') or '').strip().lower() != str(by or '').strip().lower():
        return False, "Only the team lead can choose."
    if reg.get('is_eliminated'):
        return False, "Your team is no longer in the hackathon."
    problem = next((p for p in released_problems(event) if p['id'] == str(pid or '')), None)
    if problem is None:
        return False, "Choose one of the released problem statements."
    old = choice_of(reg).get('pid', '')
    if old == problem['id']:
        return True, f"Your team already has “{problem['title']}”."
    cap = selection_cap(event)
    if not _take(event_id, problem['id'], cap):
        if not _free_cancelled(db, event_id, problem['id']) or not _take(event_id, problem['id'], cap):
            return False, f"“{problem['title']}” is full ({cap} teams). Choose another."
    _set_choice(db, event, reg_id, problem, by, by_spoc=False)
    _give_back(event_id, old)
    reg['problem_choice'] = {'pid': problem['id'], 'title': problem.get('title', '')}
    return True, (f"Your team's problem statement is “{problem['title']}”. You can change it until "
                  f"{show(s['closes_at'], event)}.")


def assign(db, event_id: str, event: dict, reg_id: str, pid: str, by: str) -> tuple:
    """(ok, message): the SPOC sets a team's problem statement, at any time and
    past the cap (the SPOC decides). The team is told on its page."""
    if not selection_on(event):
        return False, "Set the time to choose a problem statement first."
    problem = next((p for p in released_problems(event) if p['id'] == str(pid or '')), None)
    if problem is None:
        return False, "Choose one of the released problem statements."
    from services_event_types import id_variants
    doc = db.collection('registrations').document(str(reg_id)).get()
    reg = (doc.to_dict() or {}) if doc.exists else {}
    if not doc.exists or str(reg.get('event_id') or '') not in set(id_variants(event_id)) | {str(event_id)} \
            or _status(reg) in INACTIVE:
        return False, "Team not found."
    old = choice_of(reg).get('pid', '')
    team = reg.get('team_name') or reg.get('lead_name') or 'The team'
    if old == problem['id']:
        return True, f"{team} already has “{problem['title']}”."
    _take(event_id, problem['id'], 0)
    _set_choice(db, event, reg_id, problem, by, by_spoc=True)
    _give_back(event_id, old)
    notify(db, {**event, 'id': event_id}, reg, "Your problem statement",
           f"The organisers set your team's problem statement to “{problem['title']}”. "
           "Your submission will be for it.", link=f"/hackathon/{event_id}", kind='announcement')
    return True, f"{team} now has “{problem['title']}”."


def selection_board(db, event_id: str, event: dict) -> dict:
    """For the SPOC: each released problem statement with its teams, and the
    teams that haven't chosen."""
    import services_hackathon_eval as ev
    released = released_problems(event)
    by_pid = {p['id']: [] for p in released}
    not_chosen = []
    for reg_id, reg in ev._event_regs(db, event_id):
        if reg.get('is_eliminated'):
            continue
        row = {'id': reg_id, 'team': reg.get('team_name') or reg.get('lead_name') or 'Team',
               'lead': reg.get('lead_email') or '', 'choice': choice_of(reg)}
        pid = row['choice'].get('pid')
        (by_pid[pid] if pid in by_pid else not_chosen).append(row)
    key = lambda r: str(r['team']).lower()
    return {'problems': [{**p, 'teams': sorted(by_pid[p['id']], key=key)} for p in released],
            'not_chosen': sorted(not_chosen, key=key), 'cap': selection_cap(event)}


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
    # UPG-321: with a time to choose, the team's chosen problem statement is
    # the one submitted, whatever the form sends
    chosen = choice_of(reg) if selection_on(event) else {}
    if selection_on(event) and not chosen:
        return False, ("Your team hasn't chosen a problem statement, so it can't submit yet. "
                       "Ask the organisers to assign one."), {}

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
        if kind == 'problem' and chosen:
            answers[fid] = chosen['pid']
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
    if chosen:
        problem_id = chosen['pid']
    title_field = next((f for f in form(event)['fields'] if f['kind'] == 'text' and answers.get(f['id'])), None)
    team_name = reg.get('team_name') or reg.get('lead_name') or 'Team'
    now = _iso(_now())
    record = {
        'event_id': str(event_id), 'registration_id': str(reg_id), 'team_name': team_name,
        'project_title': (answers[title_field['id']] if title_field else '') or team_name,
        'answers': answers, 'problem_id': problem_id,
        'problem_title': (released.get(problem_id) or find_problem(event, problem_id) or {}).get('title', ''),
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

    sel = selection_window(event, now)
    if sel != 'not_set':                                  # UPG-321
        mine = choice_of(reg).get('title', '')
        s_open, s_close = _selection_times(event)
        if sel == 'not_open':
            add('selection', 'Choose a problem statement', 'upcoming',
                f"Team leads choose from {show(_iso(s_open), event)}.", s_open)
        elif sel == 'open':
            add('selection', 'Choose a problem statement', 'current',
                (f"Yours: {mine}. You can change it until {show(_iso(s_close), event)}." if mine else
                 f"Not chosen yet. Choose before {show(_iso(s_close), event)}."), s_close)
        else:
            add('selection', 'Choose a problem statement', 'done',
                f"Locked: {mine}." if mine else "Locked. Your team didn't choose; the organisers will assign one.")

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
        str(selection(event).get('opens_at')), str(selection(event).get('closes_at')),
        str(selection(event).get('cap')), selection_window(event, now), choice_of(reg).get('pid', ''),
    ]
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:16]
