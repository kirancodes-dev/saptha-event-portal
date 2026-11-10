"""
services_registration_edit.py — correcting a registration's details (UPG-225)

The team lead (their own registration, until the team is checked in or the
event is over) and the event's organisers (`manage_registrations`, any time)
correct what was entered wrong: the lead's name, USN and phone, the team
name, each member's name, USN and phone, and the answers to the event's own
questions. A detail lives in several places, and a change is written to each:

- the registration's `lead_name`, `lead_usn`, `lead_phone`, `team_name`;
- the lead's and members' rows in `members` (under the registration's lock,
  so a member joining at the same moment isn't lost, UPG-52);
- `form_answers`: the standard ids (full_name, usn, phone, …), a USN or phone
  question the SPOC added by hand (UPG-222's labels) and the member_N_* answers;
- the copy in `form_submissions` that the form responses page reads.

Nothing else on the registration changes: attendance, payment, team code,
entry list, member confirmation, scores and the ticket stay as they are. The
lead's email is their login and isn't changed here; a waiting member's email
goes through UPG-207's correction, which sends a new link.
"""
import datetime
import logging

import services_export as export

logger = logging.getLogger(__name__)

NAME_KEYS = ('full_name', 'name', 'participant_name')
USN_KEYS = ('usn', 'roll_number', 'roll_no', 'id_number')
PHONE_KEYS = ('phone', 'phone_number', 'mobile', 'contact')
TEAM_KEYS = ('team_name', 'team', 'group_name')
# Answers that aren't one of the event's own questions here: the lead's
# details (shown once, above), the email (the login) and the registration's type
NOT_QUESTIONS = export.IDENTITY_KEYS | {'lead_name'}
CANCELLED = ('cancelled', 'refunded')
MEMBER_PARTS = (('name', 'Name', 'text'), ('usn', 'USN', 'text'), ('phone', 'Phone', 'tel'))
LIMITS = {'name': 150, 'usn': 30, 'phone': 20, 'team_name': 100}


def _email(value) -> str:
    return str(value or '').strip().lower()


def cancelled(reg: dict) -> bool:
    return str(reg.get('status') or '').strip().lower() in CANCELLED


def lead_may_edit(reg: dict, event: dict) -> str:
    """'' when the lead may correct the registration now, else why not."""
    from routes_coordinator import checked_in
    from services_certificates import event_ended
    if cancelled(reg):
        return "This registration is cancelled, so its details can't be changed."
    if checked_in(reg):
        return ("Your team has been checked in, so its details can't be changed here. "
                "Ask the event's organiser to correct them.")
    if event_ended(event or {}) or str((event or {}).get('status') or '').lower() == 'cancelled':
        return "The event is over, so the details can't be changed here. Ask the event's organiser."
    return ''


def _fid(field) -> str:
    return str(field.get('id') or field.get('field_name') or '')


def _norm(value, upper=False):
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, bool):
        return 'yes' if value else ''
    text = '' if value is None else str(value).strip()
    return text.upper() if upper else text


def _member_key(member: dict) -> str:
    """Who a member is between opening the page and saving: the email, else the name."""
    return _email(member.get('email')) or 'name:' + str(member.get('name') or '').strip()


def build(db, event_id: str, event: dict, reg: dict) -> dict:
    """What the edit page shows: {'lead', 'team', 'members', 'questions',
    'values', 'lead_email'}. Each input has a `name` (the form field) and a
    current value in `values`."""
    from routes_forms import registration_schema, team_limits
    import services_team_confirm as confirm
    fields = [f for f in registration_schema(event_id, event).get('fields') or [] if isinstance(f, dict) and _fid(f)]
    by_id = {_fid(f): f for f in fields}
    usn_ids = export._labelled(fields, export.USN_LABEL, kinds=(None, 'text', 'number'))
    phone_ids = export._labelled(fields, export.PHONE_LABEL, kinds=(None, 'text', 'tel', 'number'))
    answers = export._answers(reg)
    lead_email = _email(reg.get('lead_email') or reg.get('student_email'))
    doc = db.collection('users').document(lead_email).get() if lead_email else None
    profile = (doc.to_dict() or {}) if doc is not None and doc.exists else {}

    def source(keys, ids):
        return [by_id[i] for i in list(keys) + list(ids) if i in by_id]

    usn_from, phone_from = source(USN_KEYS, usn_ids), source(PHONE_KEYS, phone_ids)
    lead = [
        {'name': 'lead_name', 'key': 'name', 'label': 'Name', 'type': 'text', 'required': True,
         'targets': NAME_KEYS},
        {'name': 'lead_usn', 'key': 'usn', 'label': 'USN', 'type': 'text',
         'required': any(f.get('required') for f in usn_from),
         'pattern': next((f.get('pattern') for f in usn_from if f.get('pattern')), ''),
         'targets': USN_KEYS + tuple(usn_ids)},
        {'name': 'lead_phone', 'key': 'phone', 'label': 'Phone', 'type': 'tel',
         'required': any(f.get('required') for f in phone_from), 'targets': PHONE_KEYS + tuple(phone_ids)},
    ]
    values: dict = {
        'lead_name': str(reg.get('lead_name') or export._text(next((answers.get(k) for k in NAME_KEYS
                                                                     if answers.get(k)), ''))),
        'lead_usn': export._lead(reg, 'usn', usn_ids, profile),
        'lead_phone': export._lead(reg, 'phone', phone_ids, profile),
    }

    team = None
    if team_limits(event)[1] > 1 or reg.get('team_code'):
        team = {'name': 'team_name', 'label': 'Team name', 'type': 'text', 'required': True}
        values['team_name'] = str(reg.get('team_name') or '')

    confirming = confirm.enabled(event)
    members = []
    for i, m in enumerate(export._others(reg), start=1):
        parts = []
        for key, label, ftype in MEMBER_PARTS:
            asked = by_id.get(f'member_{i}_{key}') or by_id.get(f'member_1_{key}')
            if key != 'name' and not asked and not str(m.get(key) or '').strip():
                continue   # a part the event doesn't ask, and the member never gave
            name = f'm{i}_{key}'
            parts.append({'name': name, 'key': key, 'label': label, 'type': ftype,
                          'required': key == 'name' or bool((by_id.get(f'member_{i}_{key}') or {}).get('required'))})
            values[name] = str(m.get(key) or '')
        st = confirm.status(m) if confirming else None
        members.append({'n': i + 1, 'index': i, 'key': _member_key(m), 'email': _email(m.get('email')),
                        'name': str(m.get('name') or ''), 'parts': parts, 'status': st,
                        'can_correct_email': bool(st and st['key'] != 'confirmed' and _email(m.get('email')))})

    questions = []
    for f in fields:
        fid = _fid(f)
        if (f.get('type') in export.LAYOUT_TYPES or fid in NOT_QUESTIONS or fid.startswith('member_')
                or fid in usn_ids or fid in phone_ids):
            continue
        questions.append(dict(f, name='q_' + fid))
        value = answers.get(fid)
        if isinstance(value, bool):
            value = 'yes' if value else ''
        values['q_' + fid] = value if isinstance(value, list) else export._text(value)
    return {'lead': lead, 'team': team, 'members': members, 'questions': questions, 'values': values,
            'lead_email': lead_email}


def _submitted(form, field) -> object:
    if field.get('type') == 'checkbox_group':
        return form.getlist(field['name'])
    if field.get('type') == 'checkbox':
        return 'yes' if form.get(field['name']) else ''
    return str(form.get(field['name']) or '').strip()


def apply(db, reg_id: str, event_id: str, event: dict, form, by: str, organiser: bool) -> dict:
    """Save the corrections a form sent. {'changed': [labels], 'errors':
    {input name: message}, 'values', 'page', 'gone': [members no longer on the
    team], 'certificates': whether any were already issued to this team}."""
    from routes_forms import _field_errors
    doc = db.collection('registrations').document(reg_id).get()
    reg = (doc.to_dict() or {}) if doc.exists else {}
    page = build(db, event_id, event, reg)
    current = dict(page['values'])
    values = dict(current)
    out = {'changed': [], 'errors': {}, 'values': values, 'page': page, 'gone': [], 'certificates': False}

    # What was sent, in the inputs of the page as it is now
    changed, pseudo = [], []
    for f in page['lead'] + ([page['team']] if page['team'] else []):
        values[f['name']] = _submitted(form, f)
        if f['name'] == 'lead_usn':
            values[f['name']] = _norm(values[f['name']], upper=True)
        if _norm(values[f['name']], f['name'] == 'lead_usn') != _norm(current.get(f['name']), f['name'] == 'lead_usn'):
            changed.append(f)
            pseudo.append(f)
    by_key = {m['key']: m for m in page['members']}
    member_changes = {}   # key: {part: value}
    for n in range(1, 1 + len([k for k in form.keys() if k.endswith('_key') and k.startswith('m')])):
        key = str(form.get(f'm{n}_key') or '')
        m = by_key.get(key)
        if m is None:
            if key:
                out['gone'].append(key.split(':', 1)[-1])
            continue
        for part in m['parts']:
            sent = form.get(f"m{n}_{part['key']}")
            if sent is None:
                continue
            value = _norm(sent, part['key'] == 'usn')
            values[part['name']] = value
            if value != _norm(current.get(part['name']), part['key'] == 'usn'):
                member_changes.setdefault(key, {})[part['key']] = value
                said = part['label'] if part['key'] == 'usn' else part['label'].lower()
                labelled = dict(part, label=f"Member {m['n']} {said}")
                changed.append(labelled)
                pseudo.append(labelled)
    answers = dict(export._answers(reg))
    new_answers = dict(answers)
    changed_q = []
    for q in page['questions']:
        value = _submitted(form, q)
        values[q['name']] = value
        if _norm(value) != _norm(current.get(q['name'])):
            new_answers[_fid(q)] = value
            changed_q.append(q)
            changed.append(q)

    # Only what changed is checked: an old value today's rules would refuse
    # doesn't stop the correction of another
    errors = {}
    for fid, msg in _field_errors({'fields': [dict(q, id=_fid(q)) for q in changed_q]}, new_answers):
        errors.setdefault('q_' + fid, msg)
    for fid, msg in _field_errors({'fields': [dict(p, id=p['name']) for p in pseudo]}, values):
        errors.setdefault(fid, msg)
    out['errors'] = errors
    if errors or not changed:
        return out

    # Write each change everywhere it lives
    updates = {}
    lead_member = {}
    for f in page['lead']:
        if f in changed:
            value = values[f['name']][:LIMITS[f['key']]]
            updates[f['name']] = value
            lead_member[f['key']] = value
            for target in f['targets']:   # each answer that holds it, standard or hand-added
                if target in answers:
                    new_answers[target] = value
    if page['team'] and page['team'] in changed:
        updates['team_name'] = values['team_name'][:LIMITS['team_name']]
        for target in TEAM_KEYS:
            if target in answers:
                new_answers[target] = updates['team_name']
    for key, parts in member_changes.items():
        for part in parts:
            parts[part] = parts[part][:LIMITS[part]]
        for slot in {k.split('_')[1] for k in answers if k.startswith('member_') and k.count('_') >= 2}:
            name, email = answers.get(f'member_{slot}_name'), _email(answers.get(f'member_{slot}_email'))
            if (email and email == key) or (not email and key == 'name:' + str(name or '').strip()):
                for part, value in parts.items():
                    if f'member_{slot}_{part}' in answers or part == 'name':
                        new_answers[f'member_{slot}_{part}'] = value
    if new_answers != answers:
        updates['form_answers'] = new_answers
    updates['details_edited_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    updates['details_edited_by'] = by
    db.collection('registrations').document(reg_id).update(updates)

    lead_email = page['lead_email']
    if lead_member or member_changes:
        import services_team_confirm as confirm

        def change(m):
            if lead_email and _email(m.get('email')) == lead_email:
                return dict(lead_member) if lead_member else None
            return dict(member_changes[_member_key(m)]) if _member_key(m) in member_changes else None
        confirm.update_members(db, reg_id, change)

    if 'form_answers' in updates or 'lead_name' in updates:
        copy = {'answers': new_answers}
        if 'lead_name' in updates:
            copy['name'] = updates['lead_name']
        for sub in db.collection('form_submissions').where('reg_id', '==', reg_id).stream():
            try:
                db.collection('form_submissions').document(sub.id).update(copy)
            except Exception:
                logger.exception("Could not update the form response %s of %s", sub.id, reg_id)

    labels = [str(f.get('label') or f['name']) for f in changed]
    out['changed'] = labels
    from utils import log_action
    log_action(db, "REGISTRATION_EDITED", f"{by} changed {', '.join(labels)} of {reg_id} "
                                          f"for event {event_id}" + (" (organiser)" if organiser else ''))
    if organiser and lead_email and lead_email != _email(by):
        try:
            from routes_notifications_v2 import create_notification
            title = event.get('title') or 'an event'
            create_notification(db, user_email=lead_email, notif_type='update',
                                title=f"Your registration was updated: {title}",
                                message=f"The event's organiser corrected: {', '.join(labels)}.",
                                link='/participant/dashboard', metadata={'event_id': str(event_id)})
        except Exception:
            logger.warning("Portal notice to %s failed", lead_email, exc_info=True)
    try:
        import services_certificates
        out['certificates'] = any(str(c.get('reg_id') or '') == reg_id
                                  for c in services_certificates.for_event(event_id))
    except Exception:
        out['certificates'] = False
    return out


def message(result: dict, organiser: bool) -> str:
    """The note after saving."""
    text = "Saved: " + ', '.join(result['changed']) + '.'
    if result['gone']:
        text += f" Not changed: {', '.join(result['gone'])}, no longer on the team."
    if result['certificates']:
        text += (" Certificates already issued keep the old details: correct them from the event's "
                 "Certificates page." if organiser else
                 " Certificates already issued keep the old details: ask the event's organiser to correct them.")
    return text
