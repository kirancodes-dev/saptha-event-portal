"""
services_share.py — where registrations come from: tracked share links (UPG-162).

The organiser names links for an event (WhatsApp group, Instagram, the poster,
a department); each is the event page with `?src=<code>`, and each has a poster
QR. A visitor's code is kept in their session for that event, and the form
carries it in a hidden field, so it survives the form's Back and a resubmission;
it's stored on the registration as `source`. The standard `utm_source` is read
when there's no `src`.

Only the code is kept, nothing about the visitor (DPDP): a code the event
doesn't know is stored as "other", and a visit with no code as "" (direct).
Visits per link are a count, one per browser session per event.
"""
import re
from typing import Dict, List

from sqlalchemy.exc import IntegrityError

CODE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,31}$')
OTHER = 'other'
RESERVED = (OTHER, 'direct')
MAX_LINKS = 30
SESSION_KEY = 'share_src'
NOT_COUNTED = ('cancelled', 'refunded', 'rejected')


class ShareError(ValueError):
    """A reason to refuse, shown to the organiser as it is."""


def links_for(event: dict) -> List[Dict]:
    return [link for link in event.get('share_links') or [] if isinstance(link, dict) and link.get('code')]


def _slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')[:32].strip('-')


def add_link(db, event_id: str, event: dict, label: str, code: str = '') -> str:
    label = (label or '').strip()[:60]
    if not label:
        raise ShareError('Name the link, for example "Poster" or "CSE WhatsApp group".')
    code = (code or '').strip().lower() or _slug(label)
    if not CODE.match(code):
        raise ShareError('The code takes lowercase letters, digits, "-" and "_" (up to 32).')
    if code in RESERVED:
        raise ShareError(f'"{code}" is kept for visits without a known link; choose another code.')
    links = links_for(event)
    if any(link['code'] == code for link in links):
        raise ShareError(f'This event already has a link with the code "{code}".')
    if len(links) >= MAX_LINKS:
        raise ShareError(f'An event has at most {MAX_LINKS} share links.')
    links.append({'code': code, 'label': label})
    db.collection('events').document(event_id).update({'share_links': links})
    return code


def remove_link(db, event_id: str, event: dict, code: str) -> None:
    """Registrations keep their code; the report lists it as a removed link."""
    links = [link for link in links_for(event) if link['code'] != code]
    db.collection('events').document(event_id).update({'share_links': links})


def resolve(event: dict, raw: str) -> str:
    """The code to store for what the visitor arrived with: one of the
    event's codes, "other" for anything else, '' for nothing."""
    raw = (raw or '').strip().lower()[:64]
    if not raw:
        return ''
    return raw if any(link['code'] == raw for link in links_for(event)) else OTHER


def capture(sess, event_id: str, event: dict, args) -> str:
    """Note the code a visitor arrived with (`src`, else `utm_source`) and
    count the visit once per session. Returns the code kept for the event."""
    raw = args.get('src') or args.get('utm_source') or ''
    kept = dict(sess.get(SESSION_KEY) or {})
    if raw:
        code = resolve(event, raw)
        if kept.get(event_id) != code:
            kept.pop(event_id, None)
            kept[event_id] = code
            sess[SESSION_KEY] = dict(list(kept.items())[-20:])   # the most recent events only
            try:
                record_visit(event_id, code)
            except Exception:   # a count is never worth a failed page
                import logging
                logging.getLogger(__name__).warning("Visit count for %s failed", event_id, exc_info=True)
    return kept.get(event_id, '')


def for_submission(sess, event_id: str, event: dict, form) -> str:
    """The source to store on a registration: the form's hidden field, else
    the session's, checked again against the event's links."""
    raw = form.get('src') or (sess.get(SESSION_KEY) or {}).get(event_id) or ''
    return resolve(event, raw)


# ── Visits ──────────────────────────────────────────────────────────────────

def record_visit(event_id: str, code: str) -> None:
    from db_pg import get_session
    from models_pg import SourceVisit
    key = f"{event_id}:{code}"
    for _ in range(2):
        try:
            with get_session(primary=True) as s:
                updated = (s.query(SourceVisit).filter(SourceVisit.key == key)
                           .update({SourceVisit.visits: SourceVisit.visits + 1}, synchronize_session=False))
                if not updated:
                    s.add(SourceVisit(key=key, event_id=str(event_id), code=code, visits=1))
            return
        except IntegrityError:   # someone else's first visit landed together: count again as an update
            continue


def visits(event_id: str) -> Dict[str, int]:
    from db_pg import get_session
    from models_pg import SourceVisit
    with get_session() as s:
        return {code: n for code, n in
                s.query(SourceVisit.code, SourceVisit.visits).filter(SourceVisit.event_id == str(event_id))}


# ── The report ──────────────────────────────────────────────────────────────

def report(db, event_id: str, event: dict) -> List[Dict]:
    """One row per source: the event's links, then removed links still on
    registrations, "other" and direct. Conversion is registrations per visit,
    for sources that count visits."""
    counts: Dict[str, int] = {}
    for doc in db.collection('registrations').where('event_id', '==', event_id).stream():
        reg = doc.to_dict() or {}
        if str(reg.get('status') or '').strip().lower() in NOT_COUNTED:
            continue
        code = str(reg.get('source') or '')
        counts[code] = counts.get(code, 0) + 1
    seen = visits(event_id)

    rows = [{'code': link['code'], 'label': link['label']} for link in links_for(event)]
    known = {row['code'] for row in rows}
    rows += [{'code': code, 'label': f'{code} (link removed)'}
             for code in sorted(set(counts) | set(seen)) if code and code not in known and code != OTHER]
    rows += [{'code': OTHER, 'label': 'Other (unknown code)'}, {'code': '', 'label': 'Direct (no link)'}]
    for row in rows:
        row['registrations'] = counts.get(row['code'], 0)
        row['visits'] = seen.get(row['code']) if row['code'] else None
        row['conversion'] = (round(row['registrations'] * 100 / row['visits'], 1)
                             if row['visits'] else None)
    return rows
