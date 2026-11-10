"""
services_export.py — one export of an event's registrations, in CSV and
Excel, and a one-click event report (UPG-03).

Used by the SPOC, coordinator and admin exports. Callers check
can(user, 'export_data', event) first; nothing here checks permissions.
"""
import csv
import datetime
import io
import re
from collections import Counter, defaultdict

import services_entry

# One row per registration; a team's lead, then its other members
COLUMNS = ['Ticket ID', 'Lead Name', 'Lead USN', 'Department', 'Year', 'Lead Email', 'Lead Phone', 'Team', 'Members',
           'Attendance', 'Check-in Time', 'Payment Status', 'Amount (Rs)', 'Score', 'Rank',
           'Certificate ID', 'Registered At', 'Participant Type', 'Designation', 'Institution',
           'Ticket Type']

def _ptype(record):
    """Student, faculty or external (UPG-12); older records are students."""
    from services_participants import type_of
    return type_of(record)


USN = re.compile(r'^\d?[A-Z]{2}(\d{2})([A-Z]{2,3})\d+$')
# The university's own numbers: batch, college letters, BE, branch (25SUUBEAML231,
# 24BECSE0624 → 2025 AML, 2024 CSE; UPG-222)
USN_BE = re.compile(r'^(\d{2})[A-Z]{0,4}BE([A-Z]{2,4})\d+$')


def _usn_match(usn):
    return USN.match(usn) or USN_BE.match(usn)


def _answers(reg):
    answers = reg.get('form_answers')
    return answers if isinstance(answers, dict) else {}


def department_and_year(reg, profile=None, usn=None):
    """Department: the profile's, else the form's, else the USN's branch code.
    Year: the form's year or semester answer, else the batch in the USN
    (1SN22CS007 → 2022)."""
    answers = _answers(reg)
    usn = str(usn or reg.get('lead_usn') or answers.get('usn') or '').strip().upper()
    m = _usn_match(usn)
    department = ((profile or {}).get('department') or answers.get('department') or answers.get('branch')
                  or (m.group(2) if m else ''))
    year = answers.get('year') or answers.get('year_of_study') or answers.get('semester') or (
        f"20{m.group(1)}" if m else '')
    return str(department or ''), str(year or '')


def _average(reg):
    """The team's score as every board shows it (UPG-84)."""
    from services_leaderboard import score_of
    return score_of(reg)[0]


def _ranks(regs):
    """Published ranks where there are any; otherwise the shared ranking (UPG-84)."""
    if any(r.get('final_rank') for _, r in regs):
        return {rid: r.get('final_rank') for rid, r in regs if r.get('final_rank')}
    from services_leaderboard import rank
    return {row['id']: row['rank'] for row in rank([dict(r, id=rid) for rid, r in regs])}


def _registrations(db, event_id):
    return [(d.id, d.to_dict() or {}) for d in db.collection('registrations').where('event_id', '==', event_id).stream()]


def _profiles(db, regs):
    out = {}
    for _, reg in regs:
        email = (reg.get('lead_email') or '').lower()
        if email and email not in out:
            doc = db.collection('users').document(email).get()
            out[email] = (doc.to_dict() or {}) if doc.exists else {}
    return out


def _event_sessions(db, event_id):
    import services_sessions
    doc = db.collection('events').document(event_id).get()
    return services_sessions.sessions_for((doc.to_dict() or {}) if doc.exists else {})


def _member_confirm(db, event_id):
    """Does the event ask team members to confirm their email (UPG-207)?"""
    import services_team_confirm
    doc = db.collection('events').document(event_id).get()
    return services_team_confirm.enabled((doc.to_dict() or {}) if doc.exists else {})


def _confirm_label(member):
    """A member's confirmation in the Members cell: " [Confirmed]" or " [Waiting]"."""
    return ' [Confirmed]' if member.get('confirmed_at') else ' [Waiting]'


def _entry_event(db, event_id):
    """The event, when its entry list is on (UPG-214); else None."""
    doc = db.collection('events').document(event_id).get()
    event = (doc.to_dict() or {}) if doc.exists else {}
    return event if services_entry.on(event) else None


def registration_columns(db, event_id):
    """COLUMNS, with each team member's and each form question's columns
    before "Attendance" (UPG-222), then one column per agenda session
    (UPG-159), then "Selected to attend" when the event's entry list is on (UPG-214)."""
    return registration_table(db, event_id)[0]


def registration_rows(db, event_id, sessions=True):
    """One row per registration, in registration_columns order (COLUMNS only
    with sessions=False, for the all-events export): a session's cell is
    "Yes" when it was scanned in."""
    return registration_table(db, event_id, sessions)[1]


# ── The event's own columns (UPG-222) ──────────────────────────────────────

# Answers the fixed columns already show, or that aren't the registrant's
IDENTITY_KEYS = {'full_name', 'name', 'participant_name', 'email', 'email_address', 'phone', 'phone_number',
                 'mobile', 'contact', 'usn', 'roll_number', 'roll_no', 'id_number', 'team_name', 'team',
                 'group_name', 'participant_type', 'designation', 'institution', 'ticket_tier', 'ticket_type'}
LAYOUT_TYPES = ('heading', 'paragraph', 'divider')
# A question the SPOC added by hand that asks the USN or the phone
USN_LABEL = re.compile(r'\b(usn|roll\s*(no|number)|reg(istration|ister)?\.?\s*(no|number)|university\s*seat)\b', re.I)
PHONE_LABEL = re.compile(r'\b(phone|mobile|whats\s*app|contact\s*(no|number))\b', re.I)
MEMBER_PARTS = (('name', 'Name'), ('usn', 'USN'), ('email', 'Email'), ('phone', 'Phone'))


def _form_fields(db, event_id):
    """The questions on the event's saved form, in its order."""
    doc = db.collection('event_forms').document(event_id).get()
    data = (doc.to_dict() or {}) if doc.exists else {}
    fields = data if isinstance(data, list) else data.get('fields') or []
    return [f for f in fields if isinstance(f, dict) and (f.get('id') or f.get('field_name'))]


def _fid(field):
    return str(field.get('id') or field.get('field_name'))


def _text(value):
    """An answer as a cell: choices joined, yes/no for a tick box."""
    if isinstance(value, (list, tuple)):
        return ', '.join(str(v) for v in value if str(v).strip())
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    return '' if value is None else str(value).strip()


def _labelled(fields, pattern, kinds=None):
    """Ids of hand-added questions whose label asks for `pattern`."""
    return [_fid(f) for f in fields if _fid(f) not in IDENTITY_KEYS and f.get('type') not in LAYOUT_TYPES
            and f.get('type') != 'email' and (kinds is None or f.get('type') in kinds)
            and pattern.search(str(f.get('label') or ''))]


def _lead(reg, key, ids, profile):
    """The lead's USN or phone: the registration's, else the answer to a
    question asking it, else the account's."""
    answers = _answers(reg)
    for value in [reg.get(f'lead_{key}'), reg.get(key)] + [answers.get(i) for i in ids] + [(profile or {}).get(key)]:
        text = _text(value)
        if text:
            return text.upper() if key == 'usn' else text
    return ''


def _others(reg):
    """The team's members but the lead."""
    lead = str(reg.get('lead_email') or '').strip().lower()
    return [m for m in (reg.get('members') or []) if isinstance(m, dict)
            and not (lead and str(m.get('email') or '').strip().lower() == lead)]


def _unique_header(name, used):
    name = str(name or '').strip() or 'Question'
    candidate, n = name, 1
    while candidate in used:
        n += 1
        candidate = f"{name} (form)" if n == 2 else f"{name} ({n - 1})"
    used.add(candidate)
    return candidate


def _event_columns(fields, regs, confirming, taken, shown=()):
    """(slots, parts, member_headers, questions): the most members besides
    the lead on any team, the parts given for them (name, and USN, email,
    phone when any member gave one), their headers, and (answer id, header)
    for each question on the form, then for answers to questions since
    taken off it."""
    slots = max((len(_others(r)) for _, r in regs), default=0)
    parts = [(key, label) for key, label in MEMBER_PARTS
             if key == 'name' or any(str(m.get(key) or '').strip() for _, r in regs for m in _others(r))]
    used = set(taken)
    member_headers = []
    for i in range(slots):   # the lead is member 1
        member_headers += [_unique_header(f"Member {i + 2} {label}", used) for _, label in parts]
        if confirming:
            member_headers.append(_unique_header(f"Member {i + 2} Confirmed", used))
    questions, seen = [], set(IDENTITY_KEYS) | set(shown)   # shown: the lead's USN and phone questions
    for f in fields:
        fid = _fid(f)
        if fid in seen or f.get('type') in LAYOUT_TYPES or fid.startswith('member_'):
            continue
        seen.add(fid)
        questions.append((fid, _unique_header(f.get('label') or fid, used)))
    for _, r in regs:   # answers to a question the SPOC later removed
        for fid in _answers(r):
            if fid not in seen and not fid.startswith('member_'):
                seen.add(fid)
                questions.append((fid, _unique_header(f"{fid} (no longer on the form)", used)))
    return slots, parts, member_headers, questions


def registration_table(db, event_id, sessions=True):
    """(columns, rows) of the registrations export. With sessions=False the
    columns are COLUMNS only, the same for every event (the all-events export)."""
    import services_sessions
    regs = _registrations(db, event_id)
    agenda = _event_sessions(db, event_id) if sessions else []
    confirming = _member_confirm(db, event_id)
    went = services_sessions.attended(event_id) if agenda else {}
    profiles = _profiles(db, regs)
    ranks = _ranks(regs)
    listed = _entry_event(db, event_id) if sessions else None
    fields = _form_fields(db, event_id)
    usn_ids = _labelled(fields, USN_LABEL, kinds=(None, 'text', 'number'))
    phone_ids = _labelled(fields, PHONE_LABEL, kinds=(None, 'text', 'tel', 'number'))
    split = COLUMNS.index('Attendance')
    slots, parts, member_headers, questions = (
        _event_columns(fields, regs, confirming, COLUMNS, usn_ids + phone_ids)
        if sessions else (0, [], [], []))
    columns = (COLUMNS[:split] + member_headers + [h for _, h in questions] + COLUMNS[split:]
               + [f"Session: {services_sessions.label(s)}" for s in agenda]
               + (['Selected to attend'] if listed else []))
    rows = []
    for rid, r in sorted(regs, key=lambda x: str(x[1].get('registered_at') or '')):
        profile = profiles.get((r.get('lead_email') or '').lower())
        usn = _lead(r, 'usn', usn_ids, profile)
        department, year = department_and_year(r, profile, usn)
        others = _others(r)
        score = r.get('final_score') if r.get('final_score') not in (None, '') else _average(r)
        cells = []
        for i in range(slots):
            m = others[i] if i < len(others) else None
            cells += [_text(m.get(key)) if m else '' for key, _ in parts]
            if confirming:
                cells.append(('Yes' if m.get('confirmed_at') else 'No') if m else '')
        answers = _answers(r)
        cells += [_text(answers.get(fid)) for fid, _ in questions]
        row = [
            r.get('reg_id') or rid, r.get('lead_name', ''), usn, department, year,
            r.get('lead_email', ''), _lead(r, 'phone', phone_ids, profile),
            r.get('team_name', ''), '; '.join(
                str(m.get('name', '')) + (f" ({m['usn']})" if str(m.get('usn') or '').strip() else '')
                + (_confirm_label(m) if confirming else '') for m in others),
        ] + cells + [
            r.get('attendance', 'Pending'), r.get('checkin_time', ''),
            r.get('payment_status', ''), r.get('amount_paid', 0) or 0,
            '' if score is None else score, ranks.get(rid, ''),
            r.get('certificate_id', ''), r.get('registered_at', ''),
            _ptype(r), r.get('designation', ''), r.get('institution', ''),   # UPG-12
            r.get('ticket_type_name', ''),                                    # UPG-155
        ] + ['Yes' if s['id'] in went.get(rid, ()) else '' for s in agenda]  # UPG-159
        row += [('Yes' if services_entry.may_enter(listed, r) else 'No')] if listed else []   # UPG-214
        rows.append(row)
    return columns, rows


def to_csv(rows, columns=COLUMNS):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(v) for v in row])
    return out.getvalue()


def _cell(value):
    # A spreadsheet runs a cell that starts with = + - @ as a formula, and
    # registrants type names: quote those, but leave numbers like +91 98… alone
    if (isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r')
            and not re.fullmatch(r'[+-]?[\d\s().-]+', value)):
        return "'" + value
    return value


def to_xlsx(sheets):
    """sheets: [(title, columns, rows)] → .xlsx bytes."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, columns, rows in sheets:
        ws = wb.create_sheet(title[:31])
        ws.append(columns)
        for cell in ws[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='0D2D62')
        for row in rows:
            ws.append([_cell(v) for v in row])
        for i, name in enumerate(columns, 1):
            ws.column_dimensions[get_column_letter(i)].width = max(12, min(40, len(str(name)) + 4))
        ws.freeze_panes = 'A2'
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def registrations_xlsx(db, event_id):
    return to_xlsx([('Registrations', *registration_table(db, event_id))])


def all_registration_rows(db):
    """Every event's registrations (the admin export), event title first."""
    rows = []
    for e in db.collection('events').stream():
        title = (e.to_dict() or {}).get('title', '')
        rows += [[title] + row for row in registration_rows(db, e.id, sessions=False)]
    return rows


# ── Event report ───────────────────────────────────────────────────────────

def event_report(db, event_id):
    """Registrations against attendance by department and year, feedback
    averages and winners. No AI."""
    ev_doc = db.collection('events').document(event_id).get()
    event = (ev_doc.to_dict() or {}) if ev_doc.exists else {}
    regs = _registrations(db, event_id)
    profiles = _profiles(db, regs)
    ranks = _ranks(regs)

    by_dept, by_year, by_type = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    ratings = []
    for rid, r in regs:
        department, year = department_and_year(r, profiles.get((r.get('lead_email') or '').lower()))
        present = r.get('attendance') == 'Present'
        for table, key in ((by_dept, department or 'Not given'), (by_year, year or 'Not given'),
                           (by_type, _ptype(r))):
            table[key]['registered'] += 1
            table[key]['present'] += 1 if present else 0
        rating = (r.get('feedback') or {}).get('rating') if isinstance(r.get('feedback'), dict) else None
        if isinstance(rating, (int, float)) or str(rating or '').isdigit():
            ratings.append(float(rating))

    winners = sorted(((ranks[rid], r) for rid, r in regs if rid in ranks and ranks[rid] <= 3), key=lambda x: x[0])
    return {
        'event': {'id': event_id, 'title': event.get('title', 'Event'), 'date': str(event.get('date', '')),
                  'venue': event.get('venue', '')},
        'registered': len(regs),
        'present': sum(1 for _, r in regs if r.get('attendance') == 'Present'),
        # Teams the SPOC didn't put on the entry list weren't expected (UPG-214)
        'not_selected': sum(1 for _, r in regs if not services_entry.inactive(r) and services_entry.left_out(event, r)),
        'by_department': {k: dict(v) for k, v in sorted(by_dept.items())},
        'by_year': {k: dict(v) for k, v in sorted(by_year.items())},
        'by_participant_type': {k: dict(v) for k, v in sorted(by_type.items())},   # UPG-12
        'feedback': {'responses': len(ratings),
                     'average_rating': round(sum(ratings) / len(ratings), 2) if ratings else None},
        'winners': [{'rank': rank, 'name': r.get('lead_name', ''), 'team': r.get('team_name', ''),
                     'score': r.get('final_score') or _average(r)} for rank, r in winners],
        'polls': _poll_results(event_id),                                          # UPG-160
        'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


def _poll_results(event_id):
    import services_interact
    out = []
    for p in services_interact.polls_for(event_id):
        res = services_interact.results(p)
        out.append({'question': p['question'], 'answered': res['votes'],
                    'options': [{'option': o, 'answers': n} for o, n in zip(p['options'], res['counts'])]})
    return out


def event_report_xlsx(db, event_id):
    report = event_report(db, event_id)
    ev = report['event']
    expected = report['registered'] - report['not_selected']   # not-selected teams aren't absent (UPG-214)
    present_pct = round(100 * report['present'] / expected, 1) if expected > 0 else 0
    summary = [
        ['Event', ev['title']], ['Date', ev['date']], ['Venue', ev['venue']],
        ['Registered', report['registered']], ['Present', report['present']],
    ] + ([['Not selected to attend', report['not_selected']]] if report['not_selected'] else []) + [
        ['Attendance %', present_pct],
        ['Feedback responses', report['feedback']['responses']],
        ['Average feedback rating', '' if report['feedback']['average_rating'] is None
         else report['feedback']['average_rating']],
        ['Generated', report['generated_at']],
    ]
    breakdown = lambda table: [[k, v.get('registered', 0), v.get('present', 0)] for k, v in table.items()]  # noqa: E731
    return to_xlsx([
        ('Summary', ['Item', 'Value'], summary),
        ('By department', ['Department', 'Registered', 'Present'], breakdown(report['by_department'])),
        ('By year', ['Year', 'Registered', 'Present'], breakdown(report['by_year'])),
        ('By participant type', ['Participant type', 'Registered', 'Present'],
         breakdown(report['by_participant_type'])),
        ('Winners', ['Rank', 'Name', 'Team', 'Score'],
         [[w['rank'], w['name'], w['team'], '' if w['score'] is None else w['score']] for w in report['winners']]),
        ('Polls', ['Poll', 'Option', 'Answers', '% of those who answered', 'People who answered'],
         [[p['question'], o['option'], o['answers'],
           round(100 * o['answers'] / p['answered'], 1) if p['answered'] else 0, p['answered']]
          for p in report['polls'] for o in p['options']]),                        # UPG-160
        ('Registrations', *registration_table(db, event_id)),
    ])


# ── Department Activity & Hours Export (UPG-11) ───────────────────────────

DEPARTMENT_ACTIVITY_COLUMNS = [
    'Student Name', 'USN', 'Email', 'Department', 'Year',
    'Events Attended', 'Total Activity Points', 'Total Activity Hours', 'Participant Type',
]


def department_activity_data(db, department=None, participant_type=None):
    """Return list of dicts with activity totals for every student in the department."""
    students = []
    for u in db.collection('users').stream():
        udata = u.to_dict() or {}
        role = str(udata.get('role', ''))
        if role in ('Student', 'Participant'):
            stud_dept = str(udata.get('department') or '').strip()
            if department and stud_dept.lower() != str(department).strip().lower():
                continue
            # Faculty FDP hours too; ?participant_type= narrows to one type (UPG-12)
            if participant_type and _ptype(udata) != str(participant_type).strip().lower():
                continue
            students.append((u.id, udata))

    # Pre-fetch events
    events_map = {str(e.id): (e.to_dict() or {}) for e in db.collection('events').stream()}

    # Group registrations by email and usn
    regs_by_student = defaultdict(list)
    for r in db.collection('registrations').stream():
        rdata = r.to_dict() or {}
        rdata.setdefault('_doc_id', r.id)   # for session hours (UPG-159)
        email = str(rdata.get('lead_email') or '').strip().lower()
        usn = str(rdata.get('lead_usn') or '').strip().upper()
        if email:
            regs_by_student[email].append(rdata)
        if usn:
            regs_by_student[usn].append(rdata)
        for m in (rdata.get('members') or []):
            m_email = str(m.get('email') or '').strip().lower()
            m_usn = str(m.get('usn') or '').strip().upper()
            if m_email and m_email != email:
                regs_by_student[m_email].append(rdata)
            if m_usn and m_usn != usn:
                regs_by_student[m_usn].append(rdata)

    results = []
    for u_id, sdata in sorted(students, key=lambda x: (x[1].get('department', ''), x[1].get('name', ''))):
        s_email = str(sdata.get('email') or u_id or '').strip()
        s_usn = str(sdata.get('usn') or '').strip().upper()
        # Collect distinct registrations
        seen_reg_ids = set()
        matched_regs = []
        for r in regs_by_student.get(s_email.lower(), []) + (regs_by_student.get(s_usn, []) if s_usn else []):
            rid = str(r.get('id') or r.get('reg_id') or id(r))
            if rid not in seen_reg_ids:
                seen_reg_ids.add(rid)
                matched_regs.append(r)

        attended_count = 0
        total_points = 0.0
        total_hours = 0.0
        from services_ledger import credit_for
        for r in matched_regs:   # each registration once (deduplicated above)
            if str(r.get('attendance') or '').strip().lower() == 'present':
                attended_count += 1
                points, hours = credit_for(r, events_map.get(str(r.get('event_id')), {}), r.get('_doc_id', ''))
                total_points += points
                total_hours += hours

        results.append({
            'name': sdata.get('name', ''),
            'usn': sdata.get('usn', ''),
            'email': s_email,
            'department': sdata.get('department', ''),
            'year': sdata.get('year', ''),
            'events_attended': attended_count,
            'total_points': total_points,
            'total_hours': total_hours,
            'participant_type': _ptype(sdata),
        })
    return results


def department_activity_rows(db, department=None, participant_type=None):
    """List every participant in the department with totals as row tuples."""
    data = department_activity_data(db, department, participant_type)
    return [
        [
            d['name'], d['usn'], d['email'], d['department'], d['year'],
            d['events_attended'], d['total_points'], d['total_hours'], d['participant_type'],
        ]
        for d in data
    ]


def department_activity_csv(db, department=None, participant_type=None):
    return to_csv(department_activity_rows(db, department, participant_type), columns=DEPARTMENT_ACTIVITY_COLUMNS)


def department_activity_xlsx(db, department=None, participant_type=None):
    return to_xlsx([('Department Activity', DEPARTMENT_ACTIVITY_COLUMNS,
                     department_activity_rows(db, department, participant_type))])


# ── Placement drive rounds (UPG-57) ────────────────────────────────────────

PLACEMENT_ROUND_COLUMNS = ['Ticket ID', 'Name', 'USN', 'Email', 'Phone', 'Department', 'Year',
                           'CGPA', 'Active Backlogs', 'Round', 'Result']


def placement_round_rows(db, event_id, round_id, status=None):
    """Everyone with a result in one round of a placement drive (optionally one result)."""
    from services_placement import academic_record, settings
    ev_doc = db.collection('events').document(event_id).get()
    event = (ev_doc.to_dict() or {}) if ev_doc.exists else {}
    round_name = next((r['name'] for r in settings(event).get('rounds') or [] if r['id'] == round_id), round_id)
    regs = _registrations(db, event_id)
    profiles = _profiles(db, regs)
    rows = []
    for rid, r in sorted(regs, key=lambda x: str(x[1].get('lead_name') or '')):
        result = (r.get('placement_rounds') or {}).get(round_id)
        if not result or (status and result != status):
            continue
        rec = academic_record(profiles.get((r.get('lead_email') or '').lower()) or {})
        rows.append([r.get('reg_id') or rid, r.get('lead_name', ''), r.get('lead_usn') or rec['usn'], r.get('lead_email', ''),
                     r.get('lead_phone', ''), rec['department'], rec['year'],
                     '' if rec['cgpa'] is None else rec['cgpa'], '' if rec['backlogs'] is None else rec['backlogs'],
                     round_name, result])
    return rows
