"""
services_placement.py — placement drives (UPG-57).

An event marked as a placement drive (`is_placement`) holds the company's
details and its eligibility rules in `placement`:

    {'company': 'Acme', 'role': 'SDE', 'package': '12 LPA', 'jd_link': 'https://…',
     'branches': ['CSE', 'ISE'], 'years': ['4'], 'min_cgpa': 7.0, 'max_backlogs': 0,
     'rounds': [{'id': 'r1', 'name': 'Aptitude'}, …]}

A student's CGPA and active backlogs come from the roster CSV (UPG-10's import
gained `cgpa` and `backlogs` columns); students see them on their profile and
can't edit them; admins can. Registration checks the rules against that record
and says why someone isn't eligible.

Each registration keeps its result per round in `placement_rounds`
({round_id: 'shortlisted' | 'rejected'}); the student's current round is the
last one they were shortlisted for, unless a later result rejected them. Every
move sends one notice through the notification service.
"""
import datetime
import re

STATUSES = ('shortlisted', 'rejected')


def is_placement(event: dict) -> bool:
    return bool((event or {}).get('is_placement'))


def settings(event: dict) -> dict:
    p = (event or {}).get('placement')
    return p if isinstance(p, dict) else {}


def _list(value):
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = re.split(r'[,;\n]', str(value or ''))
    return [str(x).strip() for x in items if str(x).strip()]


def _number(value, cast=float):
    try:
        return cast(str(value).strip()) if str(value).strip() != '' else None
    except (TypeError, ValueError):
        return None


def from_form(form, previous: dict = None) -> dict:
    """The placement settings from the create or edit form; rounds are kept."""
    previous = previous or {}
    return {
        'company': (form.get('placement_company') or '').strip()[:200],
        'role': (form.get('placement_role') or '').strip()[:200],
        'package': (form.get('placement_package') or '').strip()[:100],
        'jd_link': (form.get('placement_jd_link') or '').strip()[:500],
        'branches': _list(form.get('placement_branches')),
        'years': _list(form.get('placement_years')),
        'min_cgpa': _number(form.get('placement_min_cgpa')),
        'max_backlogs': _number(form.get('placement_max_backlogs'), int),
        'rounds': previous.get('rounds') or [],
    }


def academic_record(user: dict) -> dict:
    """What the roster says: department, year, CGPA and active backlogs."""
    user = user or {}
    return {'usn': str(user.get('usn') or '').strip().upper(),
            'department': str(user.get('department') or '').strip(),
            'year': str(user.get('year') or '').strip(),
            'cgpa': _number(user.get('cgpa')),
            'backlogs': _number(user.get('backlogs'), int)}


def eligibility(event: dict, user: dict):
    """(eligible, reason). The reason says what to fix or whom to ask."""
    rules = settings(event)
    if user is None:
        return False, ("Placement drives are for students on the university roster. "
                       "Log in with your university account, or ask the placement office to add you.")
    rec = academic_record(user)
    branches = [b.lower() for b in rules.get('branches') or []]
    if branches and rec['department'].lower() not in branches:
        return False, (f"This drive is for {', '.join(rules['branches'])} students; "
                       f"your branch on record is {rec['department'] or 'not set'}.")
    years = [str(y).lower() for y in rules.get('years') or []]
    if years and rec['year'].lower() not in years:
        return False, (f"This drive is for year {', '.join(rules['years'])}; "
                       f"your year on record is {rec['year'] or 'not set'}.")
    min_cgpa = rules.get('min_cgpa')
    if min_cgpa is not None:
        if rec['cgpa'] is None:
            return False, "Your CGPA isn't on record yet; ask the placement office to add it."
        if rec['cgpa'] < float(min_cgpa):
            return False, f"This drive needs a CGPA of at least {min_cgpa:g}; yours on record is {rec['cgpa']:g}."
    max_backlogs = rules.get('max_backlogs')
    if max_backlogs is not None:
        if rec['backlogs'] is None:
            return False, "Your active backlogs aren't on record yet; ask the placement office to add them."
        if rec['backlogs'] > int(max_backlogs):
            return False, (f"This drive allows at most {max_backlogs} active backlog(s); "
                           f"you have {rec['backlogs']} on record.")
    return True, ''


def eligible_students(db, event: dict) -> list:
    """Every student on the roster who meets the drive's rules."""
    out = []
    for doc in db.collection('users').stream():
        u = doc.to_dict() or {}
        if str(u.get('role', '')) not in ('Student', 'Participant'):
            continue
        if eligibility(event, u)[0]:
            out.append(dict(u, email=u.get('email') or doc.id))
    return out


def add_round(event: dict, name: str) -> dict:
    """The settings with one more round."""
    s = dict(settings(event))
    rounds = list(s.get('rounds') or [])
    rounds.append({'id': f"r{len(rounds) + 1}", 'name': name.strip()[:100] or f"Round {len(rounds) + 1}"})
    s['rounds'] = rounds
    return s


def current_round(event: dict, reg: dict):
    """(round name, status) a student sees: their latest result, or ('', '')."""
    results = (reg or {}).get('placement_rounds') or {}
    latest = ('', '')
    for r in settings(event).get('rounds') or []:
        if r['id'] in results:
            latest = (r['name'], results[r['id']])
    return latest


def move(db, *, event_id: str, event: dict, reg_id: str, reg: dict, round_id: str, status: str, actor: str) -> bool:
    """Record a result for one round and notify the student once. False if
    nothing changed (same result again, unknown round or status)."""
    rounds = {r['id']: r['name'] for r in settings(event).get('rounds') or []}
    if status not in STATUSES or round_id not in rounds:
        return False
    results = dict((reg or {}).get('placement_rounds') or {})
    if results.get(round_id) == status:
        return False
    results[round_id] = status
    history = list(reg.get('placement_history') or [])
    history.append({'round': round_id, 'status': status, 'by': actor,
                    'at': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    db.collection('registrations').document(reg_id).update(
        {'placement_rounds': results, 'placement_history': history})
    _notify(db, event_id=event_id, event=event, reg=reg, round_name=rounds[round_id],
            round_id=round_id, status=status, reg_id=reg_id)
    return True


def _notify(db, *, event_id, event, reg, round_name, round_id, status, reg_id):
    """One notice per student, round and result (the notification service's key)."""
    try:
        from services_automation import NotificationAutomationEngine
        email = str(reg.get('lead_email') or '').strip().lower()
        if not email:
            return
        company = settings(event).get('company') or event.get('title', 'the placement drive')
        name = reg.get('lead_name') or 'Student'
        if status == 'shortlisted':
            message = f"Hello {name}, you're shortlisted in the {round_name} round for {company}."
        else:
            message = f"Hello {name}, you weren't selected in the {round_name} round for {company}."
        NotificationAutomationEngine.dispatch_trigger(
            db, trigger_name='on_placement_round_result',
            context={'recipient_email': email, 'recipient_name': name, 'event_title': event.get('title', '')},
            custom_rule={'title': f"{company}: {round_name}", 'message': message,
                         'notif_type': 'system_alert', 'channels': ['in_app', 'email']},
            idempotency_key=f"placement_{event_id}_{reg_id}_{round_id}_{status}")
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Placement notice failed for %s", reg_id)
