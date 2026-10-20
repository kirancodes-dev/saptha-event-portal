"""
services_reach.py — reaching beyond one campus (UPG-146).

* Each event is "campus only" (the default) or "open to other colleges"
  (`audience`); opening it lets external participants register (UPG-12's
  `allowed_participants`), closing it takes that back.
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
import time
from typing import List

AUDIENCES = ('campus', 'open')
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


def set_audience(db, event_id: str, audience: str, actor: str) -> None:
    from services_participants import allowed_types
    from utils import log_action
    if audience not in AUDIENCES:
        raise ValueError("Choose campus only or open to other colleges.")
    ref = db.collection('events').document(event_id)
    event = ref.get().to_dict() or {}
    allowed = [t for t in allowed_types(event) if t != 'external']
    if audience == 'open':
        allowed.append('external')
    ref.update({'audience': audience, 'allowed_participants': allowed or ['student']})
    log_action(db, "EVENT_AUDIENCE", f"{actor}: event {event_id} is {audience}")


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
