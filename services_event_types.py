"""
services_event_types.py — every kind of event a SPOC can create (UPG-73, UPG-74).

One registry drives the create wizard, its validation, the review page and the
public listings:

* TYPES: each event type, with its defaults (category, participation, team
  size, mode, audience), whether it's judged, the catalogue preset it uses
  (services_templates) and the details only that type needs (a sport and a
  format for a tournament, a discipline for a cultural competition, ...).
* parse_form(): turns the wizard's form into event fields and a list of
  messages, without touching the database, so it can be tested on its own.
* is_listed(): whether an event appears in public listings.
"""
from __future__ import annotations

import datetime
import json
import re
from typing import Any, Dict, List, Optional, Tuple

# ── Groups and types ────────────────────────────────────────────────────────

GROUPS: List[Tuple[str, str, str]] = [
    ('learning',    'Talks & learning',              'fa-chalkboard-user'),
    ('competition', 'Competitions',                  'fa-trophy'),
    ('cultural',    'Cultural',                      'fa-masks-theater'),
    ('sports',      'Sports',                        'fa-futbol'),
    ('community',   'Community, clubs & exhibitions', 'fa-hands-holding-circle'),
    ('career',      'Career',                        'fa-briefcase'),
    ('fest',        'Fests & big events',            'fa-flag'),
    ('other',       'Anything else',                 'fa-sliders'),
]

CATEGORIES = ('Technical', 'Cultural', 'Sports', 'Management', 'Academic', 'NSS', 'NCC', 'Social')
MODES = ('offline', 'online', 'hybrid')
PARTICIPATION = ('Individual', 'Team', 'Both')
SUBMISSION_TYPES = ('none', 'github', 'drive', 'file')

SPORTS = ('Cricket', 'Football', 'Basketball', 'Volleyball', 'Kabaddi', 'Kho-Kho', 'Throwball',
          'Hockey', 'Handball', 'Badminton', 'Table tennis', 'Tennis', 'Chess', 'Carrom', 'Other')
SPORT_FORMATS = ('Knockout', 'League', 'League then knockout')
GENDERS = ('Open', 'Men', 'Women', 'Mixed')
CULTURAL_DISCIPLINES = ('Dance', 'Music', 'Drama / theatre', 'Fashion show', 'Art & painting',
                        'Photography', 'Literary', 'Comedy / stand-up', 'Film', 'Other')
PERFORMANCE_SIZES = ('Solo', 'Duo', 'Group')


def _f(name, label, kind='text', options=(), required=False, help='', placeholder=''):
    """One type-specific detail field."""
    return {'name': name, 'label': label, 'kind': kind, 'options': list(options),
            'required': required, 'help': help, 'placeholder': placeholder}


SPEAKER = [_f('speaker', 'Speaker / resource person', placeholder='e.g. Dr. A. Rao'),
           _f('speaker_designation', 'Designation and organisation', placeholder='e.g. Principal Scientist, ISRO')]

# key → spec. `preset` names a services_templates catalogue entry.
TYPES: Dict[str, Dict[str, Any]] = {
    # Talks & learning
    'seminar':        dict(name='Seminar', group='learning', icon='fa-chalkboard-user', category='Academic',
                           blurb='A talk with Q&A and attendance certificates.', preset='seminar',
                           details=SPEAKER),
    'guest_lecture':  dict(name='Guest lecture', group='learning', icon='fa-user-tie', category='Academic',
                           blurb='An invited expert speaks to students.', preset='seminar',
                           details=SPEAKER),
    'workshop':       dict(name='Workshop', group='learning', icon='fa-laptop-code', category='Technical',
                           blurb='Hands-on training with limited seats.', preset='workshop',
                           details=[_f('trainer', 'Trainer'),
                                    _f('prerequisites', 'Prerequisites', placeholder='e.g. Basic Python'),
                                    _f('bring', 'What to bring', placeholder='e.g. Laptop with VS Code')]),
    'conference':     dict(name='Conference', group='learning', icon='fa-people-roof', category='Academic',
                           blurb='Multi-session event with tracks and paper sessions.', preset='conference',
                           audience=['student', 'faculty', 'external'],
                           details=[_f('tracks', 'Tracks or themes', 'textarea', placeholder='One per line'),
                                    _f('proceedings', 'Proceedings / publisher', placeholder='Optional')]),
    'webinar':        dict(name='Webinar', group='learning', icon='fa-video', category='Academic', mode='online',
                           blurb='An online talk with a meeting link.', preset='webinar',
                           audience=['student', 'faculty', 'external'], details=SPEAKER),
    'fdp':            dict(name='Faculty development programme', group='learning', icon='fa-user-graduate',
                           category='Academic', blurb='Faculty-only training over one or more days.',
                           preset='workshop', audience=['faculty', 'external'],
                           details=[_f('resource_persons', 'Resource persons', 'textarea',
                                       placeholder='One per line'),
                                    _f('sponsored_by', 'Sponsored by', placeholder='e.g. AICTE ATAL (optional)')]),
    'orientation':    dict(name='Orientation / induction', group='learning', icon='fa-door-open', category='Academic',
                           blurb='Welcome and orientation for a batch.', preset='seminar',
                           details=[_f('batch', 'For which batch', placeholder='e.g. 2026 first years')]),

    # Competitions
    'hackathon':      dict(name='Hackathon', group='competition', icon='fa-code', category='Technical',
                           blurb='Team build sprint with submissions and judging.', preset='hackathon',
                           competitive=True, participation='Team', team=(2, 4), submission='github',
                           details=[_f('duration_hours', 'Duration (hours)', 'number', placeholder='e.g. 24'),
                                    _f('themes', 'Problem themes or tracks', 'textarea', placeholder='One per line')]),
    'coding_contest': dict(name='Coding contest', group='competition', icon='fa-terminal', category='Technical',
                           blurb='Timed programming contest, solo or in pairs.', preset='hackathon',
                           competitive=True, participation='Individual',
                           details=[_f('platform', 'Contest platform', 'select',
                                       ('In-house', 'HackerRank', 'Codeforces', 'CodeChef', 'LeetCode', 'Other')),
                                    _f('duration_hours', 'Duration (hours)', 'number'),
                                    _f('languages', 'Languages allowed', placeholder='e.g. C, C++, Java, Python')]),
    'quiz':           dict(name='Quiz', group='competition', icon='fa-circle-question', category='Technical',
                           blurb='Prelims and finals, usually in small teams.', competitive=True,
                           participation='Team', team=(2, 3),
                           details=[_f('quiz_format', 'Format', 'select',
                                       ('Written prelims + stage finals', 'Online prelims + stage finals',
                                        'Buzzer rounds only', 'Other')),
                                    _f('topic', 'Topic', placeholder='e.g. General, Tech, Business')]),
    'paper_presentation': dict(name='Paper presentation', group='competition', icon='fa-file-lines',
                           category='Technical', blurb='Abstract submission, then presentations to judges.',
                           competitive=True, participation='Team', team=(1, 3), submission='drive',
                           details=[_f('abstract_deadline', 'Abstract deadline', 'date'),
                                    _f('domains', 'Domains', placeholder='e.g. AI, IoT, Renewable energy')]),
    'project_expo':   dict(name='Project expo', group='competition', icon='fa-diagram-project', category='Technical',
                           blurb='Teams show working projects at stalls.', competitive=True,
                           participation='Team', team=(1, 4),
                           details=[_f('domains', 'Domains', placeholder='e.g. Robotics, Healthcare')]),
    'debate':         dict(name='Debate / elocution', group='competition', icon='fa-microphone-lines',
                           category='Cultural', blurb='Debate, elocution, JAM, group discussion or MUN.',
                           competitive=True, participation='Individual',
                           details=[_f('style', 'Style', 'select',
                                       ('Debate', 'Elocution', 'JAM', 'Group discussion', 'MUN', 'Other'),
                                       required=True),
                                    _f('language', 'Language', placeholder='e.g. English, Kannada')]),
    'case_competition': dict(name='Case / business plan', group='competition', icon='fa-chart-line',
                           category='Management', blurb='Case study, business plan or marketing challenge.',
                           competitive=True, participation='Team', team=(2, 4), submission='drive',
                           details=[_f('kind', 'Kind', 'select',
                                       ('Case study', 'Business plan', 'Marketing', 'Finance', 'HR', 'Other'),
                                       required=True)]),

    # Cultural
    'cultural_competition': dict(name='Cultural competition', group='cultural', icon='fa-masks-theater',
                           category='Cultural', blurb='Dance, music, drama, fashion, art, literary and more.',
                           preset='cultural', competitive=True, participation='Both', team=(1, 12),
                           details=[_f('discipline', 'Discipline', 'select', CULTURAL_DISCIPLINES, required=True),
                                    _f('performance_size', 'Solo or group', 'select', PERFORMANCE_SIZES,
                                       required=True),
                                    _f('time_limit_minutes', 'Time on stage (minutes)', 'number'),
                                    _f('language', 'Language / theme', placeholder='Optional')]),
    'cultural_show':  dict(name='Cultural show / concert', group='cultural', icon='fa-music', category='Cultural',
                           blurb='A performance for an audience (pro-show, concert, play).', preset='cultural',
                           details=[_f('performers', 'Performers / line-up', 'textarea')]),

    # Sports
    'sports_tournament': dict(name='Sports tournament', group='sports', icon='fa-futbol', category='Sports',
                           blurb='Team or individual sport with fixtures and standings.', preset='sports',
                           competitive=True, participation='Team', team=(5, 15),
                           details=[_f('sport', 'Sport', 'select', SPORTS, required=True),
                                    _f('sport_other', 'Which sport (if Other)'),
                                    _f('format', 'Format', 'select', SPORT_FORMATS, required=True),
                                    _f('gender', 'Gender category', 'select', GENDERS, required=True),
                                    _f('match_rules', 'Match length / rules', placeholder='e.g. T10, 2 halves of 20 min')]),
    'athletics':      dict(name='Athletics / track & field', group='sports', icon='fa-person-running',
                           category='Sports', blurb='Individual events with heats and finals.', preset='sports',
                           competitive=True, participation='Individual',
                           details=[_f('disciplines', 'Events', 'textarea', required=True,
                                       placeholder='e.g. 100 m, 400 m, long jump, shot put'),
                                    _f('gender', 'Gender category', 'select', GENDERS, required=True)]),
    'esports':        dict(name='E-sports', group='sports', icon='fa-gamepad', category='Sports',
                           blurb='Online or LAN gaming tournament.', competitive=True, participation='Team',
                           team=(1, 5),
                           details=[_f('game', 'Game', required=True, placeholder='e.g. Valorant, BGMI, FIFA'),
                                    _f('platform', 'Platform', 'select', ('PC', 'Mobile', 'Console')),
                                    _f('format', 'Format', 'select', SPORT_FORMATS)]),

    # Community, clubs & exhibitions
    'nss_ncc':        dict(name='NSS / NCC activity', group='community', icon='fa-hand-holding-heart', category='NSS',
                           blurb='Camps, drives and parades with volunteer hours.',
                           details=[_f('unit', 'Unit', 'select', ('NSS', 'NCC'), required=True),
                                    _f('activity', 'Activity', placeholder='e.g. Village camp, Swachh Bharat drive')]),
    'social_drive':   dict(name='Social drive', group='community', icon='fa-hands-helping', category='Social',
                           blurb='Blood donation, cleanliness, plantation, awareness.',
                           details=[_f('cause', 'Cause', 'select',
                                       ('Blood donation', 'Cleanliness', 'Tree plantation', 'Awareness', 'Fundraiser',
                                        'Other'), required=True),
                                    _f('partner', 'Partner organisation', placeholder='Optional')]),
    'club_activity':  dict(name='Club activity', group='community', icon='fa-people-group', category='Technical',
                           blurb='A club meeting, session or outing.',
                           details=[_f('club', 'Club', required=True, placeholder='e.g. Coding Club')]),
    'exhibition':     dict(name='Exhibition / open day', group='community', icon='fa-building-columns',
                           category='Academic', blurb='Stalls, displays or an open house for visitors.',
                           audience=['student', 'faculty', 'external'],
                           details=[_f('stalls', 'Number of stalls', 'number')]),

    # Career
    'placement_drive': dict(name='Placement drive', group='career', icon='fa-briefcase', category='Management',
                           blurb='Company hiring with eligibility rules and rounds.', placement=True),
    'career_fair':    dict(name='Career fair / alumni talk', group='career', icon='fa-handshake',
                           category='Management', blurb='Companies or alumni meet students.',
                           details=[_f('companies', 'Companies or speakers', 'textarea', placeholder='One per line')]),

    # Fests (UPG-74)
    'fest':           dict(name='Fest / big event', group='fest', icon='fa-flag', category='Cultural',
                           blurb='A fest or meet that holds many events (add them after creating it).',
                           fest=True,
                           details=[_f('fest_kind', 'Kind of fest', 'select',
                                       ('Cultural', 'Technical', 'Sports meet', 'Management', 'Multi-category'),
                                       required=True),
                                    _f('theme', 'Theme / tagline', placeholder='Optional')]),

    # Anything else
    'custom':         dict(name='Custom event', group='other', icon='fa-sliders', category='Technical',
                           blurb='Set everything yourself.'),
}

for _key, _spec in TYPES.items():
    _spec.setdefault('key', _key)
    _spec.setdefault('competitive', False)
    _spec.setdefault('participation', 'Individual')
    _spec.setdefault('team', (1, 1) if _spec['participation'] == 'Individual' else (1, 4))
    _spec.setdefault('mode', 'offline')
    _spec.setdefault('audience', ['student'])
    _spec.setdefault('preset', None)
    _spec.setdefault('details', [])
    _spec.setdefault('submission', 'none')
    _spec.setdefault('placement', False)
    _spec.setdefault('fest', False)

# Events made before UPG-73 used these keys
LEGACY_TYPES = {'competition': 'custom', 'sports': 'sports_tournament', 'cultural': 'cultural_competition'}


def get_type(key: str) -> Dict[str, Any]:
    key = (key or '').strip().lower()
    return TYPES.get(LEGACY_TYPES.get(key, key)) or TYPES['custom']


def grouped() -> List[Dict[str, Any]]:
    """The type picker: groups in order, each with its types."""
    return [{'key': g, 'label': label, 'icon': icon,
             'types': [t for t in TYPES.values() if t['group'] == g]}
            for g, label, icon in GROUPS]


def type_label(event: dict) -> str:
    return get_type((event or {}).get('event_type')).get('name', 'Event')


# ── Form → event fields ─────────────────────────────────────────────────────

_URL = re.compile(r'^https://[^\s/$.?#].[^\s]*$', re.I)
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_TIME = re.compile(r'^\d{2}:\d{2}$')


def _date(value: str) -> Optional[datetime.date]:
    value = (value or '').strip()
    if not _DATE.match(value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def _int(value, default=0) -> Optional[int]:
    value = str(value if value is not None else '').strip()
    if value == '':
        return default
    try:
        return int(float(value))
    except ValueError:
        return None


def _money(value) -> Optional[float]:
    value = str(value if value is not None else '').strip()
    if value == '':
        return None
    try:
        amount = round(float(value), 2)
    except ValueError:
        return None
    return amount


def _clean(value, limit=2000) -> str:
    return str(value or '').strip()[:limit]


def _url_ok(value: str) -> bool:
    return bool(_URL.match(value))


def parse_form(form, *, today: Optional[datetime.date] = None, parent: Optional[dict] = None
               ) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """The event fields a wizard form describes, every problem that stops it
    being saved (errors) and everything the SPOC should know (warnings).

    `form` is request.form (or any mapping with get/getlist). `parent` is the
    fest a sub-event belongs to (UPG-74). Nothing is saved here.
    """
    today = today or datetime.date.today()
    getlist = form.getlist if hasattr(form, 'getlist') else (lambda k: form.get(k) or [])
    errors: List[str] = []
    warnings: List[str] = []
    spec = get_type(form.get('event_type') or form.get('template_id'))
    key = spec['key']

    # Basics
    title = _clean(form.get('title'), 300)
    if not title:
        errors.append('Give the event a title.')
    category = _clean(form.get('category'), 50) or spec['category']
    if category == 'Tech':
        category = 'Technical'
    if category not in CATEGORIES:
        errors.append('Choose one of the listed categories.')
    visibility = _clean(form.get('visibility'), 20) or 'Public'
    if visibility not in ('Public', 'Private', 'Department'):
        visibility = 'Public'

    # When
    start = _date(form.get('date'))
    end = _date(form.get('end_date')) or start
    start_time = _clean(form.get('time'), 5)
    end_time = _clean(form.get('end_time'), 5)
    if not start:
        errors.append('Choose the date the event starts.')
    elif start < today:
        # Recording a past event (for attendance, hours or certificates) is allowed
        warnings.append('This event starts in the past, so nobody can register for it.')
    if start and end and end < start:
        errors.append('The event ends before it starts.')
    for label, value in (('start time', start_time), ('end time', end_time)):
        if value and not _TIME.match(value):
            errors.append(f'The {label} should look like 14:30.')
    if start and end and start == end and start_time and end_time and end_time <= start_time:
        errors.append('The end time is before the start time.')
    if start and end and (end - start).days > 60:
        errors.append('An event can last at most 60 days.')

    deadline = _date(form.get('reg_deadline'))
    reg_opens = _date(form.get('reg_opens'))
    if not spec['fest']:
        if not deadline:
            errors.append('Choose the last date to register.')
        elif start and deadline > end:
            errors.append('Registration must close on or before the last day of the event.')
        if reg_opens and deadline and reg_opens > deadline:
            errors.append('Registration opens after it closes.')

    # Where
    mode = _clean(form.get('event_mode'), 10) or spec['mode']
    if mode not in MODES:
        mode = 'offline'
    venue = _clean(form.get('venue'), 300)
    room_id = _clean(form.get('room_id'), 128)
    online_link = _clean(form.get('online_link'), 500)
    map_link = _clean(form.get('map_link'), 500)
    if mode in ('offline', 'hybrid') and not (venue or room_id):
        errors.append('Add a venue or pick a room.')
    if mode in ('online', 'hybrid') and online_link and not _url_ok(online_link):
        errors.append('The online meeting link must start with https://.')
    if map_link and not _url_ok(map_link):
        errors.append('The map link must start with https://.')

    # Who can take part
    from services_participants import from_form as audience_from_form
    audience = audience_from_form(getlist('allowed_participants')) if getlist('allowed_participants') \
        else list(spec['audience'])
    years = sorted({y for y in (_int(v, None) for v in getlist('allowed_years')) if y in (1, 2, 3, 4, 5)})
    if not getlist('allowed_years'):
        years = [y for y in (1, 2, 3, 4) if form.get(f'year_{y}') == 'on']
    capacity = _int(form.get('max_participants'), 0)
    if capacity is None or capacity < 0:
        errors.append('Capacity must be a whole number (0 means no limit).')
        capacity = 0

    participation = _clean(form.get('participation_type'), 20) or spec['participation']
    if participation not in PARTICIPATION:
        participation = spec['participation']
    team_min, team_max = 1, 1
    max_teams = _int(form.get('max_teams'), 0) or 0
    if participation in ('Team', 'Both'):
        team_min = _int(form.get('team_min'), spec['team'][0])
        team_max = _int(form.get('team_max'), spec['team'][1])
        if team_min is None or team_max is None or team_min < 1 or team_max < 1:
            errors.append('Team sizes must be whole numbers of at least 1.')
            team_min, team_max = spec['team']
        elif team_min > team_max:
            errors.append('The smallest team is larger than the largest team.')
        elif team_max > 50:
            errors.append('A team can have at most 50 members.')

    # Fees per group (UPG-73); blank means "same as the regular fee"
    fees: Dict[str, float] = {}
    regular = _money(form.get('reg_fee'))
    if form.get('reg_fee') not in (None, '') and (regular is None or regular < 0):
        errors.append('The fee must be 0 or more.')
    fees['regular'] = max(regular or 0.0, 0.0)
    for group in ('student', 'faculty', 'external'):
        raw = form.get(f'fee_{group}')
        if raw in (None, ''):
            continue
        amount = _money(raw)
        if amount is None or amount < 0:
            errors.append(f'The {group} fee must be 0 or more.')
        else:
            fees[group] = amount

    # Type details
    details: Dict[str, Any] = {}
    for field in spec['details']:
        # The wizard names each type's fields apart (detail_<type>__<name>)
        value = _clean(form.get(f"detail_{key}__{field['name']}") or form.get(f"detail_{field['name']}"), 2000)
        if field['kind'] == 'select' and value and value not in field['options']:
            errors.append(f"{field['label']}: choose one of the options.")
            value = ''
        if field['kind'] == 'number' and value:
            if _int(value, None) is None or _int(value, 0) < 0:
                errors.append(f"{field['label']} must be a number.")
                value = ''
        if field['kind'] == 'date' and value and not _date(value):
            errors.append(f"{field['label']} should be a date.")
            value = ''
        if field['required'] and not value:
            errors.append(f"{field['label']} is required for a {spec['name'].lower()}.")
        if value:
            details[field['name']] = value
    if key == 'sports_tournament' and details.get('sport') == 'Other' and not details.get('sport_other'):
        errors.append('Name the sport.')
    if spec['placement'] and not _clean(form.get('placement_company')):
        errors.append('Name the company for the placement drive.')

    # Competition setup
    judging = []
    prizes = {}
    rounds = 1
    # Judged types, and older forms that send judging or prizes without a type
    competitive = (spec['competitive'] or form.get('competitive') == 'yes'
                   or bool((form.get('judging_criteria_json') or '').strip('[] '))
                   or any(form.get(f'prize_{n}') for n in (1, 2, 3)))
    if competitive:
        try:
            judging = json.loads(form.get('judging_criteria_json') or '[]')
        except (TypeError, ValueError):
            judging = []
        judging = [{'name': _clean(c.get('name'), 80), 'description': _clean(c.get('description'), 300),
                    'max_score': max(1, min(_int(c.get('max_score'), 10) or 10, 1000))}
                   for c in judging if isinstance(c, dict) and _clean(c.get('name'))][:20]
        rounds = _int(form.get('total_rounds'), 1)
        if rounds is None or not 1 <= rounds <= 10:
            errors.append('Rounds must be between 1 and 10.')
            rounds = 1
        for place in ('1st', '2nd', '3rd'):
            value = _clean(form.get(f"prize_{place[0]}"), 120)
            if value:
                prizes[place] = value
    submission = _clean(form.get('submission_type'), 10) or spec['submission']
    if submission not in SUBMISSION_TYPES:
        submission = 'none'

    # Extras
    sponsors = []
    try:
        raw_sponsors = json.loads(form.get('sponsors_json') or '[]')
    except (TypeError, ValueError):
        raw_sponsors = []
    for sp in raw_sponsors if isinstance(raw_sponsors, list) else []:
        if not isinstance(sp, dict) or not _clean(sp.get('name')):
            continue
        logo = _clean(sp.get('logo_url'), 500)
        site = _clean(sp.get('website'), 500)
        sponsors.append({'name': _clean(sp.get('name'), 120), 'tier': _clean(sp.get('tier'), 40),
                         'logo_url': logo if _url_ok(logo) else '', 'website': site if _url_ok(site) else ''})
    banner = _clean(form.get('banner_url'), 500)
    if banner and not (_url_ok(banner) or banner.startswith('/static/')):
        errors.append('The banner must be an https:// image address.')
        banner = ''
    group_link = _clean(form.get('group_link'), 500)
    if group_link and not _url_ok(group_link):
        errors.append('The WhatsApp/group link must start with https://.')
        group_link = ''
    contact_phone = re.sub(r'[^\d+ ]', '', _clean(form.get('contact_phone'), 20))
    coordinators = sorted({e.strip().lower() for e in (form.get('coordinators') or '').split(',')
                           if re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', e.strip())})
    try:
        points = max(0.0, float(form.get('activity_points') or 0))
        hours = max(0.0, float(form.get('activity_hours') or 0))
    except ValueError:
        errors.append('Activity points and hours must be numbers.')
        points = hours = 0.0

    # A sub-event stays inside its fest (UPG-74)
    if parent is not None:
        p_start, p_end = _date(parent.get('date')), _date(parent.get('end_date') or parent.get('date'))
        if spec['fest']:
            errors.append("A fest can't be added inside another fest.")
        if start and p_start and p_end and not (p_start <= start and (end or start) <= p_end):
            errors.append(f"The event must take place during the fest ({p_start.isoformat()} to "
                          f"{p_end.isoformat()}).")

    def iso(day, clock):
        return f"{day.isoformat()}T{clock or '00:00'}:00" if day else None

    data = {
        'title': title,
        'event_type': key,
        'template_id': spec['preset'] or key,
        'category': category,
        'visibility': visibility,
        'description': _clean(form.get('description'), 20000),
        'rules': _clean(form.get('rules'), 20000),
        'banner_url': banner,
        'event_mode': mode,
        'date': start.isoformat() if start else '',
        'time': start_time,
        'end_date': end.isoformat() if end else '',
        'end_time': end_time,
        'start_datetime': iso(start, start_time),
        'end_datetime': iso(end, end_time or '23:59'),
        'reg_opens': reg_opens.isoformat() if reg_opens else '',
        'reg_deadline': deadline.isoformat() if deadline else '',
        'venue': venue or ('Online' if mode == 'online' else ''),
        'map_link': map_link,
        'online_link': online_link,
        'participation_type': participation,
        'is_team_event': participation in ('Team', 'Both'),
        'capacity': capacity,
        'limits': {'team_min': team_min, 'team_max': team_max, 'max_participants': capacity,
                   'allowed_years': years, 'max_teams': max_teams},
        'allowed_participants': audience,
        'fees': fees,
        'pricing_type': 'paid' if any(v > 0 for v in fees.values()) else 'free',
        'details': details,
        'judging_criteria': judging,
        'total_rounds': rounds,
        'prizes': prizes,
        'prize_pool': _clean(form.get('prize_pool'), 120),
        'form_schema': {
            'require_lead_whatsapp': form.get('req_lead_whatsapp') == 'on',
            'require_member_usn': form.get('req_member_usn') == 'on',
            'require_member_email': form.get('req_member_email') == 'on',
            'require_member_whatsapp': form.get('req_member_whatsapp') == 'on',
            'submission_type': submission,
        },
        'sponsors': sponsors,
        'coordinators': coordinators,
        'contact': {'phone': contact_phone, 'group_link': group_link},
        'activity_points': points,
        'activity_hours': hours,
        'is_placement': bool(spec['placement']),
        'is_fest': bool(spec['fest']),
    }
    if spec['fest']:
        data.update(capacity=0, participation_type='Individual', is_team_event=False)
    if parent is not None:
        data['parent_event_id'] = parent.get('id')
        data['visibility'] = parent.get('visibility') or data['visibility']
    data['competitive'] = competitive
    if deadline and deadline < today and not spec['fest']:
        warnings.append('Registration has already closed (the last date to register has passed).')
    return data, errors, warnings


# ── Ids ─────────────────────────────────────────────────────────────────────

def id_variants(event_id) -> List[str]:
    """An event id in every form it reaches us (with and without dashes), so a
    fest finds its sub-events whichever link was used (UPG-74)."""
    raw = str(event_id or '').strip()
    out = [raw] if raw else []
    try:
        import uuid
        u = uuid.UUID(raw)
        for form in (str(u), u.hex):
            if form not in out:
                out.append(form)
    except (ValueError, AttributeError):
        pass
    return out


# ── Listings ────────────────────────────────────────────────────────────────

LISTED_STATUSES = ('active', 'published', 'registration_open', 'registration_closed', 'in_progress')


def is_listed(event: dict, *, viewer_dept: str = '', is_admin: bool = False) -> bool:
    """Whether an event appears in public listings: published, not private,
    and department-only events only for that department (or admins)."""
    status = str(event.get('status') or 'active').strip().lower()
    if status not in LISTED_STATUSES:
        return False
    visibility = str(event.get('visibility') or 'Public').strip().lower()
    if visibility == 'private':
        return False
    if visibility in ('department', 'department_only') or event.get('department_only') is True:
        if is_admin:
            return True
        mine = (viewer_dept or '').strip().lower()
        return bool(mine) and mine in {str(event.get(k) or '').strip().lower()
                                       for k in ('department', 'org_unit_id')}
    return True


# ── Event → wizard values (editing, UPG-73) ─────────────────────────────────

def form_values(event: dict) -> Dict[str, Any]:
    """The wizard's field values for a saved event, so the same wizard edits it."""
    ev = event or {}
    spec = get_type(ev.get('event_type'))
    limits = ev.get('limits') or {}
    fees = ev.get('fees') or {}
    prizes = ev.get('prizes') or {}
    organizer = ev.get('organizer') or {}
    contact = ev.get('contact') or {}
    placement = ev.get('placement') or {}
    values: Dict[str, Any] = {
        'event_type': spec['key'],
        'title': ev.get('title', ''), 'category': ev.get('category', spec['category']),
        'visibility': ev.get('visibility', 'Public'), 'description': ev.get('description', ''),
        'rules': ev.get('rules', ''), 'banner_url': ev.get('banner_url', ''),
        'date': ev.get('date', ''), 'time': ev.get('time', ''),
        'end_date': ev.get('end_date', '') if ev.get('end_date') != ev.get('date') else '',
        'end_time': ev.get('end_time', ''),
        'reg_opens': ev.get('reg_opens', ''), 'reg_deadline': ev.get('reg_deadline', ''),
        'event_mode': ev.get('event_mode', spec['mode']),
        'room_id': ev.get('room_id', ''), 'venue': ev.get('venue', '') if ev.get('venue') != 'Online' else '',
        'map_link': ev.get('map_link', ''), 'online_link': ev.get('online_link', ''),
        'allowed_participants': list(ev.get('allowed_participants') or spec['audience']),
        'allowed_years': [str(y) for y in (limits.get('allowed_years') or [])],
        'max_participants': str(ev.get('capacity') or limits.get('max_participants') or ''),
        'participation_type': ev.get('participation_type', spec['participation']),
        'team_min': str(limits.get('team_min', '')), 'team_max': str(limits.get('team_max', '')),
        'max_teams': str(limits.get('max_teams') or ''),
        'reg_fee': str(int(fees['regular']) if float(fees.get('regular') or 0).is_integer() else fees.get('regular', 0)),
        'total_rounds': str(ev.get('total_rounds') or 1),
        'submission_type': (ev.get('form_schema') or {}).get('submission_type', spec['submission']),
        'judging_criteria_json': json.dumps(ev.get('judging_criteria') or []),
        'prize_1': prizes.get('1st', ''), 'prize_2': prizes.get('2nd', ''), 'prize_3': prizes.get('3rd', ''),
        'prize_pool': ev.get('prize_pool', ''),
        'sponsors_json': json.dumps(ev.get('sponsors') or []),
        'coordinators': ', '.join(ev.get('coordinators') or []),
        'contact_phone': contact.get('phone') or organizer.get('phone', ''),
        'group_link': contact.get('group_link') or (organizer.get('group_link') if organizer.get('group_link') != '#' else ''),
        'activity_points': str(ev.get('activity_points') or 0), 'activity_hours': str(ev.get('activity_hours') or 0),
    }
    for group in ('student', 'faculty', 'external'):
        if group in fees:
            values[f'fee_{group}'] = str(fees[group])
    for name, value in (ev.get('details') or {}).items():
        values[f"detail_{spec['key']}__{name}"] = value
    for key in ('company', 'role', 'package', 'jd_link', 'min_cgpa', 'max_backlogs'):
        if placement.get(key) not in (None, ''):
            values[f'placement_{key}'] = str(placement[key])
    for key in ('branches', 'years'):
        if placement.get(key):
            values[f'placement_{key}'] = ', '.join(str(x) for x in placement[key])
    for flag in ('require_lead_whatsapp', 'require_member_usn', 'require_member_email', 'require_member_whatsapp'):
        if (ev.get('form_schema') or {}).get(flag):
            values[flag.replace('require_', 'req_')] = 'on'
    return values
