"""
services_reach.py — reaching beyond one campus (UPG-146).

* Each event is "campus only" (the default), for "invited institutions" or
  "open to other colleges" (`audience`); the last two let external
  participants register (UPG-12's `allowed_participants`), campus-only takes
  that back. An invited institution is a name and its email domains: an
  outside participant registers with an address on one of them (UPG-270).
* `eligibility(event)` is the one sentence saying who may register, shown on
  the event page, its popup, the open-events page and the form (UPG-270).
* `/open-events` lists upcoming open events, searchable, with no login.
* Every public event page carries share cards (Open Graph and Twitter tags)
  and schema.org Event data, built here and encoded as JSON, never by hand.
* The listing kit: copy-ready text, the poster and the registration link for
  Unstop, KnowAFest and Festooo. None of them publishes an API for posting
  listings (checked 2026-10-20), so nothing is posted automatically or scraped.
* A small "Powered by SapthaEvent" line on public pages, tickets and emails,
  which the Super Admin can switch off (`settings/branding`).
"""
import datetime
import re
import time
from typing import List, Optional, Tuple

AUDIENCES = ('campus', 'invited', 'open')
MODE_LABELS = {'campus': 'This institution only', 'invited': 'Invited institutions', 'open': 'Open to everyone'}
MAX_INVITED = 50
# Anyone can have an address on these, so they can't stand for an institution
PUBLIC_MAIL = ('gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.in', 'yahoo.co.in', 'outlook.com', 'hotmail.com',
               'live.com', 'icloud.com', 'rediffmail.com', 'proton.me', 'protonmail.com', 'aol.com', 'zoho.com')
_DOMAIN = re.compile(r'^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$')
OPEN_STATUSES = ('published', 'registration_open', 'active')
SITES = (
    {'id': 'unstop', 'name': 'Unstop', 'submit': 'https://unstop.com/', 'summary_limit': 300,
     'how': 'Sign in as an organiser, choose "Host" and the event type, then paste these fields.'},
    {'id': 'knowafest', 'name': 'KnowAFest', 'submit': 'https://www.knowafest.com/', 'summary_limit': 250,
     'how': 'Use "Add your fest" on the site and paste these fields.'},
    {'id': 'festooo', 'name': 'Festooo', 'submit': 'https://www.festooo.com/', 'summary_limit': 250,
     'how': 'Use the site\'s form for listing an event and paste these fields.'},
)
_cache = {'at': 0.0, 'value': True}


def _today():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()


# ── Audience ────────────────────────────────────────────────────────────────

def is_open(event: dict) -> bool:
    return str(event.get('audience') or 'campus') == 'open'


def parse_invited(text) -> Tuple[List[dict], List[str]]:
    """The invited institutions an organiser typed, one a line as
    `Name, email-domain[, another-domain]`, and what's wrong with each line
    that can't be used. Nothing is saved while there is a problem."""
    out, problems, seen = [], [], {}
    lines = [ln.strip() for ln in str(text or '').replace('\r', '').split('\n')]
    for n, line in enumerate(lines, start=1):
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        name, domains = ' '.join(parts[0].split())[:150], []
        if not name:
            problems.append(f"Line {n}: give the institution's name first.")
            continue
        if len(parts) < 2 or not any(parts[1:]):
            problems.append(f"Line {n}: add {name}'s email domain after a comma, for example \"{name}, college.edu.in\".")
            continue
        bad = False
        for raw in parts[1:]:
            domain = raw.lower().lstrip('@')
            if not domain:
                continue
            if not _DOMAIN.match(domain):
                problems.append(f"Line {n}: \"{raw}\" isn't an email domain. Use the part after the @, like college.edu.in.")
                bad = True
            elif domain in PUBLIC_MAIL:
                problems.append(f"Line {n}: anyone can have an @{domain} address, so it can't stand for {name}. "
                                "Use the institution's own domain.")
                bad = True
            elif domain in seen:
                problems.append(f"Line {n}: {domain} is already on line {seen[domain]}.")
                bad = True
            else:
                seen[domain] = n
                domains.append(domain)
        if not bad and domains:
            out.append({'name': name, 'domains': domains})
    if len(out) > MAX_INVITED:
        problems.append(f"An event takes up to {MAX_INVITED} invited institutions; this list has {len(out)}.")
    return out, problems


def invited_institutions(event: dict) -> List[dict]:
    """The event's invited institutions, each `{'name', 'domains'}`."""
    out = []
    for row in (event or {}).get('invited_institutions') or []:
        if isinstance(row, dict) and row.get('name') and row.get('domains'):
            out.append({'name': str(row['name']), 'domains': [str(d).lower() for d in row['domains'] if d]})
    return out


def invited_text(event: dict) -> str:
    """The list as the organiser types it."""
    return '\n'.join(f"{i['name']}, {', '.join(i['domains'])}" for i in invited_institutions(event))


def access_mode(event: dict) -> str:
    """Who may register: `campus`, `invited` or `open`. The event's
    participant types decide (UPG-12), so an event that takes external
    participants is open whichever page switched that on; `invited` narrows
    the outside participants to the listed institutions."""
    from services_participants import allowed_types
    if 'external' not in allowed_types(event):
        return 'campus'
    return 'invited' if str((event or {}).get('audience') or '') == 'invited' else 'open'


def invited_match(event: dict, email: str) -> Optional[dict]:
    """The invited institution an email address belongs to, if any."""
    domain = str(email or '').strip().lower().rpartition('@')[2]
    if not domain:
        return None
    for inst in invited_institutions(event):
        if any(domain == d or domain.endswith('.' + d) for d in inst['domains']):
            return inst
    return None


def _home_name(db=None) -> str:
    try:
        import services_institution
        if db is None:
            from models import db
        return services_institution.profile(db)['name']
    except Exception:
        return 'this institution'


def eligibility(event: dict, db=None) -> dict:
    """Who may register, in one sentence a visitor reads before the form."""
    from services_participants import PLURALS, allowed_types
    mode, home = access_mode(event), _home_name(db)
    inside = [PLURALS[t] for t in allowed_types(event) if t != 'external']
    ours = f"{' and '.join(inside)} of {home}" if inside else ''
    invited = invited_institutions(event) if mode == 'invited' else []
    names = ', '.join(i['name'] for i in invited)
    domains = ', '.join('@' + d for i in invited for d in i['domains'])
    if mode == 'campus':
        line = f"For {ours} only."
    elif mode == 'invited':
        if invited:
            line = (f"For {ours}, and for participants" if ours else "For participants") + \
                   f" from the invited institutions: {names}. Invited participants register with their institution's email address ({domains})."
        else:
            line = f"For {ours} only. No other institution has been invited yet." if ours else \
                   "By invitation only. No institution has been invited yet."
    else:
        line = (f"Open to {ours}, and to participants from other colleges and organisations." if ours
                else "Open to participants from any college or organisation.")
    return {'mode': mode, 'label': MODE_LABELS[mode], 'line': line, 'institutions': [i['name'] for i in invited],
            'outside': mode != 'campus'}


def refusal(event: dict, participant_type: str, email: str) -> Tuple[Optional[str], Optional[str]]:
    """Why this person can't register as an outside participant, and the
    invited institution their address belongs to. `(None, None)` when the
    rule doesn't apply: only outside participants of an invitation-only
    event are checked here; the participant types are checked by the form."""
    if participant_type != 'external' or access_mode(event) != 'invited':
        return None, None
    match = invited_match(event, email)
    if match:
        return None, match['name']
    invited = invited_institutions(event)
    if not invited:
        return "This event is by invitation, and no other institution has been invited yet.", None
    return ("This event takes outside participants from the invited institutions only: "
            + ', '.join(i['name'] for i in invited) + ". Register with your institution's email address ("
            + ', '.join('@' + d for i in invited for d in i['domains']) + ")."), None


def is_outside(reg: dict) -> bool:
    """A registration from outside the institution (an external participant)."""
    from services_participants import type_of
    return type_of(reg) == 'external'


def set_audience(db, event_id: str, audience: str, actor: str, invited_text: str = '') -> None:
    from services_participants import allowed_types
    from utils import log_action
    if audience not in AUDIENCES:
        raise ValueError("Choose this institution only, invited institutions, or open to everyone.")
    ref = db.collection('events').document(event_id)
    event = ref.get().to_dict() or {}
    allowed = [t for t in allowed_types(event) if t != 'external']
    updates = {'audience': audience}
    if audience == 'invited':
        invited, problems = parse_invited(invited_text)
        if problems:
            raise ValueError(' '.join(problems))
        if not invited:
            raise ValueError("List at least one invited institution with its email domain.")
        updates['invited_institutions'] = invited
    if audience in ('invited', 'open'):
        allowed.append('external')
    updates['allowed_participants'] = allowed or ['student']
    ref.update(updates)
    names = ', '.join(i['name'] for i in updates.get('invited_institutions', []))
    log_action(db, "EVENT_AUDIENCE", f"{actor}: event {event_id} is {audience}" + (f" ({names})" if names else ''))


def open_events(db, q: str = '', category: str = '', event_type: str = '', date_from: str = '',
                date_to: str = '') -> List[dict]:
    """Upcoming events open to other colleges, soonest first."""
    today = _today().isoformat()
    needle = q.strip().lower()
    out = []
    for d in db.collection('events').stream():
        ev = dict(d.to_dict() or {}, id=d.id)
        day = str(ev.get('date') or '')[:10]
        if not is_open(ev) or str(ev.get('status') or '').lower() not in OPEN_STATUSES or not day or day < today:
            continue
        if needle and needle not in f"{ev.get('title', '')} {ev.get('description', '')} {ev.get('department', '')}".lower():
            continue
        if category and str(ev.get('category') or '') != category:
            continue
        if event_type and str(ev.get('event_type') or '') != event_type:
            continue
        if (date_from and day < date_from) or (date_to and day > date_to):
            continue
        out.append(ev)
    return sorted(out, key=lambda e: str(e.get('date') or ''))


# ── Share cards and schema.org ──────────────────────────────────────────────

def _image(event: dict, base: str) -> str:
    for key in ('poster_url', 'banner_url', 'image_url', 'banner', 'poster', 'image'):
        value = str(event.get(key) or '')
        if value.startswith('https://'):
            return value
        if value.startswith('/static/'):
            return base + value
    return f"{base}/static/img/email-logo.png"


def share_meta(event: dict) -> dict:
    """Open Graph / Twitter values and the schema.org Event for an event page."""
    from utils import venue_label
    from utils_email import _base_url
    base = _base_url().rstrip('/')
    url = f"{base}/event/{event.get('id', '')}"
    when = str(event.get('date') or '')[:10]
    place = venue_label(event)
    summary = ' '.join(str(event.get('description') or '').split())
    description = ' · '.join(p for p in (when, place) if p) + (f". {summary}" if summary else '')
    online = str(event.get('event_mode') or '').lower() == 'online'
    fee = (event.get('fees') or {}).get('regular') if isinstance(event.get('fees'), dict) else None
    json_ld = {
        '@context': 'https://schema.org', '@type': 'Event', 'name': event.get('title') or 'Event',
        'startDate': when + (f"T{event['time']}" if event.get('time') else ''),
        'eventStatus': 'https://schema.org/EventCancelled' if str(event.get('status')) == 'cancelled'
        else 'https://schema.org/EventScheduled',
        'eventAttendanceMode': 'https://schema.org/OnlineEventAttendanceMode' if online
        else 'https://schema.org/OfflineEventAttendanceMode',
        'location': {'@type': 'VirtualLocation', 'url': url} if online else {'@type': 'Place', 'name': place},
        'image': [_image(event, base)], 'description': summary[:500] or event.get('title') or 'Event', 'url': url,
        'offers': {'@type': 'Offer', 'price': str(fee or 0), 'priceCurrency': 'INR', 'url': url,
                   'availability': 'https://schema.org/InStock'},
        'organizer': {'@type': 'Organization', 'name': (event.get('organizer') or {}).get('name')
                      or event.get('department') or 'SapthaEvent', 'url': base},
    }
    if event.get('end_date'):
        json_ld['endDate'] = str(event['end_date'])[:10]
    return {'title': event.get('title') or 'Event', 'description': description[:300], 'url': url,
            'image': _image(event, base), 'json_ld': json_ld,
            'whatsapp': 'https://wa.me/?text=' + _quote(f"{event.get('title', 'Event')} · {when} · {place} {url}")}


def _quote(text: str) -> str:
    from urllib.parse import quote
    return quote(text, safe='')


# ── The listing kit ─────────────────────────────────────────────────────────

def listing_kit(event: dict) -> List[dict]:
    meta = share_meta(event)
    summary = ' '.join(str(event.get('description') or '').split())
    out = []
    for site in SITES:
        short = summary if len(summary) <= site['summary_limit'] else summary[:site['summary_limit'] - 1].rsplit(' ', 1)[0] + '…'
        out.append(dict(site, fields=[
            ('Event name', meta['title']), ('Short description', short), ('Full description', summary),
            ('Dates', ' to '.join(p for p in (str(event.get('date') or '')[:10], str(event.get('end_date') or '')[:10]) if p)),
            ('Venue', meta['json_ld']['location'].get('name') or 'Online'),
            ('Category', str(event.get('category') or event.get('event_type') or '')),
            ('Registration link', meta['url']), ('Poster image', meta['image'])]))
    return out


# ── "Powered by SapthaEvent" ────────────────────────────────────────────────

def powered_by(db=None) -> bool:
    """On unless the Super Admin switched it off (cached for 30 seconds)."""
    if time.time() - _cache['at'] < 30:
        return _cache['value']
    try:
        if db is None:
            from models import db
        doc = db.collection('settings').document('branding').get()
        value = (doc.to_dict() or {}).get('powered_by', True) if doc.exists else True
    except Exception:
        value = True
    _cache.update(at=time.time(), value=bool(value))
    return bool(value)


def set_powered_by(db, on: bool, actor: str) -> None:
    from utils import log_action
    db.collection('settings').document('branding').set({'powered_by': bool(on), 'by': actor})
    _cache.update(at=time.time(), value=bool(on))
    log_action(db, "POWERED_BY_LINE", f"{actor}: {'on' if on else 'off'}")
