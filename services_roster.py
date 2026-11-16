"""
services_roster.py — the student roster comes in from a CSV file in two
steps: check, then confirm (UPG-271).

`check(db, text)` reads the file and changes nothing. It says, row by row,
what would happen (a new student, an existing student updated, nothing to
change) and what is wrong with each row that can't be used: a missing or
malformed email, the same email or USN twice in the file, a USN that already
belongs to someone else, a CGPA or backlog count that isn't a number, an
email that belongs to a staff account. `apply` then writes only the rows with
nothing wrong, and only when the administrator confirms.

The checked file waits in `roster_imports` for at most an hour, readable only
by the administrator who uploaded it, and is deleted when it is confirmed,
cancelled or out of date. Confirming checks it again, so a change made in the
meantime is never overwritten blindly.

Columns (the first row names them; order and capitals don't matter): email
(required), name, usn, department, year, section, cgpa, backlogs. Other
columns are ignored and named on the preview.
"""
import csv
import datetime
import io
import re
import secrets
from typing import Dict, List, Optional, Tuple

COLLECTION = 'roster_imports'
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
KEEP_MINUTES = 60
SAMPLE = ("email,name,usn,department,year,section,cgpa,backlogs\n"
          "asha.rao@example.edu,Asha Rao,1SN23CS001,CSE,2,A,8.4,0\n")

# column → the headings it is known by
ALIASES = {
    'email': ('email', 'email_id', 'student_email', 'mail', 'email_address'),
    'name': ('name', 'student_name', 'full_name'),
    'usn': ('usn', 'roll_no', 'roll_number', 'rollno', 'reg_no', 'registration_no'),
    'department': ('department', 'dept', 'branch'),
    'year': ('year', 'class_year', 'batch'),
    'section': ('section', 'sec'),
    'cgpa': ('cgpa', 'gpa'),
    'backlogs': ('backlogs', 'active_backlogs'),
}
LABELS = {'email': 'Email', 'name': 'Name', 'usn': 'USN', 'department': 'Department', 'year': 'Year',
          'section': 'Section', 'cgpa': 'CGPA', 'backlogs': 'Backlogs'}
TEXT_FIELDS = ('name', 'usn', 'department', 'year', 'section')
LIMITS = {'name': 150, 'usn': 30, 'department': 100, 'year': 20, 'section': 20}
_EMAIL = re.compile(r'^[^@\s,;<>"]+@[^@\s,;<>"]+\.[A-Za-z]{2,}$')
CREATE, UPDATE, SAME, SKIP = 'create', 'update', 'same', 'skip'


class RosterError(ValueError):
    """The file as a whole can't be read (nothing to preview)."""


def decode(raw: bytes) -> str:
    if len(raw) > MAX_BYTES:
        raise RosterError(f"This file is larger than {MAX_BYTES // (1024 * 1024)} MB. Split it and upload the parts.")
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def _key(heading) -> str:
    return re.sub(r'[\s\-]+', '_', str(heading or '').strip().lower())


def _columns(fieldnames) -> Tuple[Dict[str, str], List[str]]:
    """Which heading feeds each field, and the headings nothing reads."""
    known, unknown = {}, []
    for heading in fieldnames or []:
        if heading is None or not str(heading).strip():
            continue
        field = next((f for f, names in ALIASES.items() if _key(heading) in names), None)
        if field and field not in known:
            known[field] = heading
        else:
            unknown.append(str(heading).strip())
    return known, unknown


def _number(text: str, whole: bool):
    value = float(text)
    if value != value or value in (float('inf'), float('-inf')):
        raise ValueError
    if whole:
        if value != int(value):
            raise ValueError
        return int(value)
    return round(value, 2)


def check(db, text: str) -> dict:
    """Read the file and say what would happen, changing nothing."""
    if not str(text or '').strip():
        raise RosterError("The file is empty. Choose a CSV file with a heading row and one student a row.")
    try:
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames
        raw_rows = [(reader.line_num, raw) for raw in reader]   # the file's own line numbers
    except csv.Error as exc:
        raise RosterError(f"This file can't be read as CSV ({exc}). Save it as CSV (comma separated) and try again.")
    known, unknown = _columns(fieldnames)
    if 'email' not in known:
        raise RosterError("The file has no email column. Its first row must name the columns, and one of them "
                          "must be \"email\". Columns found: " + (', '.join(str(f) for f in fieldnames or [] if f) or 'none') + '.')
    if len(raw_rows) > MAX_ROWS:
        raise RosterError(f"This file has {len(raw_rows)} rows; one upload takes up to {MAX_ROWS}. Split it and upload the parts.")

    accounts = {}
    by_usn: Dict[str, str] = {}
    for doc in db.collection('users').stream():
        data = doc.to_dict() or {}
        accounts[str(doc.id).lower()] = data
        if data.get('usn'):
            by_usn.setdefault(str(data['usn']).strip().upper(), str(doc.id).lower())

    rows, seen_email, seen_usn = [], {}, {}
    for line, raw in raw_rows:
        values = {f: ' '.join(str(raw.get(h) or '').split()) for f, h in known.items()}
        if not any(values.values()) and not any(str(v or '').strip() for v in raw.values() if not isinstance(v, list)):
            continue                                        # a blank line
        email = values.get('email', '').lower()
        row = {'line': line, 'email': email, 'problems': [], 'notes': [], 'changes': [], 'values': {}}
        for field in TEXT_FIELDS:
            value = values.get(field, '')
            if len(value) > LIMITS[field]:
                row['problems'].append(f"{LABELS[field]} is longer than {LIMITS[field]} characters.")
            row['values'][field] = value
        row['values']['usn'] = row['values']['usn'].upper()
        if raw.get(None):
            row['problems'].append("This row has more values than the heading row has columns. "
                                   "A value with a comma in it needs quotes around it.")

        if not email:
            row['problems'].append("No email address.")
        elif not _EMAIL.match(email) or len(email) > 254:
            row['problems'].append(f"\"{email}\" isn't an email address.")
        elif email in seen_email:
            row['problems'].append(f"Same email as line {seen_email[email]}; only the first is used.")
        else:
            seen_email[email] = line

        usn = row['values']['usn']
        if usn:
            if usn in seen_usn and seen_usn[usn][1] != email:
                row['problems'].append(f"USN {usn} is also on line {seen_usn[usn][0]} for another student.")
            else:
                seen_usn.setdefault(usn, (line, email))
            owner = by_usn.get(usn)
            if owner and owner != email:
                row['problems'].append(f"USN {usn} already belongs to another account ({_mask(owner)}).")

        for field, whole, low, high in (('cgpa', False, 0, 10), ('backlogs', True, 0, 99)):
            text_value = values.get(field, '')
            if not text_value:
                continue
            try:
                number = _number(text_value, whole)
                if not low <= number <= high:
                    raise ValueError
                row['values'][field] = number
            except ValueError:
                row['problems'].append(f"{LABELS[field]} \"{text_value}\" isn't a "
                                       + ("whole number" if whole else "number") + f" from {low} to {high}.")

        existing = accounts.get(email) if email else None
        if existing is not None:
            role = str(existing.get('role') or 'Student')
            if role not in ('Student', 'Participant'):
                row['problems'].append(f"This email belongs to a staff account ({role}); the roster doesn't change staff accounts.")
            for field, value in row['values'].items():
                old = existing.get(field)
                if value not in ('', None) and str(old if old is not None else '') != str(value):
                    row['changes'].append({'field': LABELS[field], 'old': '' if old is None else str(old), 'new': str(value)})
        elif email and not row['values'].get('name'):
            row['notes'].append("No name: the part of the email before the @ is used until the student changes it.")

        row['action'] = (SKIP if row['problems'] else CREATE if existing is None
                         else UPDATE if row['changes'] else SAME)
        rows.append(row)

    if not rows:
        raise RosterError("The file has a heading row but no students under it.")
    counts = {a: sum(1 for r in rows if r['action'] == a) for a in (CREATE, UPDATE, SAME, SKIP)}
    counts['rows'] = len(rows)
    return {'rows': rows, 'counts': counts, 'columns': [LABELS[f] for f in ALIASES if f in known],
            'ignored_columns': unknown, 'usable': counts[CREATE] + counts[UPDATE]}


def _mask(email: str) -> str:
    """An address said without giving it away: `as***@example.edu`."""
    name, _, domain = str(email).partition('@')
    return f"{name[:2]}***@{domain}"


def apply(db, checked: dict, actor: str, update_existing: bool = True) -> dict:
    """Write the rows that have nothing wrong. Existing students are updated
    with the file's values, or left alone when `update_existing` is false."""
    from services_accounts import create_unverified_account
    from utils import log_action
    done = {'created': 0, 'updated': 0, 'left': 0, 'skipped': checked['counts'][SKIP], 'same': checked['counts'][SAME]}
    for row in checked['rows']:
        values = {k: v for k, v in row['values'].items() if v not in ('', None)}
        if row['action'] == CREATE:
            name = values.pop('name', '') or row['email'].split('@')[0]
            if create_unverified_account(db, email=row['email'], name=name, role='Student', **values):
                done['created'] += 1
            else:
                done['left'] += 1                     # created by someone else a moment ago
        elif row['action'] == UPDATE:
            if update_existing:
                db.collection('users').document(row['email']).set(values, merge=True)
                done['updated'] += 1
            else:
                done['left'] += 1
    log_action(db, "STUDENT_ROSTER_IMPORTED",
               f"Roster imported by {actor}: {done['created']} created, {done['updated']} updated, "
               f"{done['left']} existing left as they were, {done['skipped']} rows not used")
    return done


def problems_csv(checked: dict) -> str:
    """The rows that can't be used, with why, to fix and upload again."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['Line', 'Email', 'Name', 'USN', 'What is wrong'])
    for row in checked['rows']:
        if row['problems']:
            writer.writerow([row['line'], _safe(row['email']), _safe(row['values'].get('name', '')),
                             _safe(row['values'].get('usn', '')), ' '.join(row['problems'])])
    return out.getvalue()


def _safe(value) -> str:
    """A cell a spreadsheet won't run as a formula."""
    text = str(value or '')
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


# ── The file waiting to be confirmed ────────────────────────────────────────

def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _expired(doc: dict) -> bool:
    try:
        made = datetime.datetime.fromisoformat(str(doc.get('created_at')))
    except ValueError:
        return True
    return _now() - made > datetime.timedelta(minutes=KEEP_MINUTES)


def hold(db, text: str, filename: str, actor: str) -> str:
    """Keep a checked file for its uploader to confirm; older ones are deleted."""
    sweep(db, actor)
    import_id = secrets.token_urlsafe(16)
    db.collection(COLLECTION).document(import_id).set({
        'text': text, 'filename': str(filename or 'roster.csv')[:120], 'by': actor,
        'created_at': _now().isoformat()})
    return import_id


def held(db, import_id: str, actor: str) -> Optional[dict]:
    """The waiting file, for the administrator who uploaded it and nobody else."""
    if not re.fullmatch(r'[A-Za-z0-9_\-]{10,40}', str(import_id or '')):
        return None
    doc = db.collection(COLLECTION).document(import_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    if _expired(data):
        discard(db, import_id)
        return None
    return data if str(data.get('by') or '').lower() == str(actor or '').lower() else None


def discard(db, import_id: str) -> None:
    db.collection(COLLECTION).document(import_id).delete()


def sweep(db, actor: str = '') -> int:
    """Delete waiting files that are out of date, and this uploader's earlier ones."""
    gone = 0
    for doc in db.collection(COLLECTION).stream():
        data = doc.to_dict() or {}
        if _expired(data) or (actor and str(data.get('by') or '').lower() == actor.lower()):
            discard(db, doc.id)
            gone += 1
    return gone
