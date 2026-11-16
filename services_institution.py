"""
services_institution.py — the institution this deployment serves (UPG-268).

One deployment serves one institution: there is one database, and no page
filters by organisation. Setting a deployment up for an institution is
therefore a repeatable checklist for its Super Admin, not a "tenant" record:

* the institution's details (name, short name, public address, support email,
  certificate colours), saved here in `settings/institution` and used by the
  page footer, the help address and the certificate;
* the first administrators, invited through the existing "add a user" flow
  (a set-password link, no password typed by anyone else);
* what is and isn't ready, read from the deployment itself.

Anything a field doesn't cover (the home page's facts about the university in
university_info.py, the logo file) is listed in docs/INSTITUTION_SETUP.md as a
code or environment change; nothing here pretends otherwise.
"""
import os
import re
import time
from typing import Dict, List, Tuple
from urllib.parse import urlparse

COLLECTION, DOCUMENT = 'settings', 'institution'
FIELDS = ('name', 'short_name', 'public_url', 'support_email', 'primary_color', 'accent_color')
ADMIN_ROLES = ('SuperAdmin', 'Super Admin', 'UniversityAdmin', 'Admin')

_cache: Dict[str, object] = {'at': 0.0, 'value': None, 'db': None}
_TTL = 30.0


def defaults() -> dict:
    """What the deployment uses when nothing has been saved: its environment
    and the built-in facts file."""
    try:
        from university_info import UNIVERSITY
        name, short = UNIVERSITY['name'], UNIVERSITY.get('short', '')
    except Exception:
        name, short = 'University', ''
    return {
        'name': (os.environ.get('COLLEGE_NAME') or name).strip(),
        'short_name': short,
        'public_url': (os.environ.get('BASE_URL') or '').strip().rstrip('/'),
        'support_email': (os.environ.get('SUPPORT_EMAIL') or '').strip(),
        'primary_color': (os.environ.get('CERT_PRIMARY_COLOR') or '#0c1240').strip(),
        'accent_color': (os.environ.get('CERT_ACCENT_COLOR') or '#c9a020').strip(),
    }


def saved(db) -> dict:
    """The fields the Super Admin saved (empty before the first save)."""
    try:
        doc = db.collection(COLLECTION).document(DOCUMENT).get()
        data = (doc.to_dict() or {}) if doc.exists else {}
    except Exception:
        data = {}
    return {k: str(data.get(k) or '').strip() for k in FIELDS if str(data.get(k) or '').strip()} | \
        {k: data[k] for k in ('updated_at', 'updated_by') if data.get(k)}


def profile(db) -> dict:
    """The details in force: saved values over the deployment's defaults.
    Only the saved part is remembered for a moment (it is a database read);
    the defaults are read from the environment each time."""
    now = time.monotonic()
    if _cache['value'] is not None and _cache['db'] is db and now - float(_cache['at']) < _TTL:
        kept: dict = _cache['value']    # type: ignore[assignment]
    else:
        kept = saved(db)
        _cache.update(at=now, value=kept, db=db)
    value = dict(defaults(), **{k: kept[k] for k in FIELDS if k in kept})
    value['saved'] = bool([k for k in FIELDS if k in kept])
    value['updated_at'], value['updated_by'] = kept.get('updated_at', ''), kept.get('updated_by', '')
    return value


def forget() -> None:
    _cache.update(at=0.0, value=None, db=None)


def validate(form) -> Tuple[dict, Dict[str, str]]:
    """Clean values and, per field, what's wrong with it."""
    clean = {k: str(form.get(k) or '').strip() for k in FIELDS}
    problems: Dict[str, str] = {}
    if not 2 <= len(clean['name']) <= 120:
        problems['name'] = "Enter the institution's name (2 to 120 characters)."
    if len(clean['short_name']) > 20:
        problems['short_name'] = "Keep the short name to 20 characters."
    if clean['public_url']:
        clean['public_url'] = clean['public_url'].rstrip('/')
        url = urlparse(clean['public_url'])
        local = url.hostname in ('localhost', '127.0.0.1')
        if url.scheme not in ('https', 'http') or not url.hostname or url.path not in ('', '/') or url.query:
            problems['public_url'] = "Enter the address people open, like https://events.example.edu, with nothing after it."
        elif url.scheme != 'https' and not local:
            problems['public_url'] = "The public address must start with https://."
    if clean['support_email'] and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', clean['support_email']):
        problems['support_email'] = "Enter a valid email address, or leave it empty."
    for key, label in (('primary_color', 'main'), ('accent_color', 'accent')):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', clean[key]):
            problems[key] = f"Enter the {label} colour as # and six letters or digits, like #0c1240."
    return clean, problems


def save(db, clean: dict, actor: str) -> List[str]:
    """Save the details; returns the names of the fields that changed."""
    import datetime
    before = profile(db)
    changed = [k for k in FIELDS if str(before.get(k) or '') != clean[k]]
    if not changed and before.get('saved'):
        return []
    db.collection(COLLECTION).document(DOCUMENT).set(dict(
        clean, updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), updated_by=actor))
    forget()
    return changed or list(FIELDS)


def administrators(db) -> List[dict]:
    out = []
    for doc in db.collection('users').stream():
        user = doc.to_dict() or {}
        if str(user.get('role') or '') in ADMIN_ROLES:
            out.append({'email': doc.id, 'name': user.get('name') or doc.id, 'role': user.get('role'),
                        # an invited account can't sign in until its set-password link is used
                        'active': not user.get('needs_password_reset')})
    return sorted(out, key=lambda a: a['email'])


def _configured(*names) -> bool:
    return all((os.environ.get(n) or '').strip() for n in names)


def checklist(db, host_url: str = '') -> List[dict]:
    """What a deployment needs before an institution uses it, each item read
    from the deployment itself: done or not, and where to fix it."""
    p = profile(db)
    admins = administrators(db)
    active = [a for a in admins if a['active']]
    try:
        units = sum(1 for _ in db.collection('org_units').limit(1).stream())
    except Exception:
        units = 0
    mail = _configured('BREVO_API_KEY') or _configured('MAIL_USER', 'MAIL_PASS') or _configured('MAIL_USER', 'MAIL_PASSWORD')
    storage = (os.environ.get('STORAGE_TYPE') or '').strip().lower()
    url = p['public_url']
    here = (host_url or '').rstrip('/')
    items = [
        {'key': 'details', 'label': "The institution's details are saved", 'done': bool(p['saved']),
         'detail': f"In force: {p['name']}." if p['saved'] else "Still the built-in defaults. Check them and save.",
         'link': '#details'},
        {'key': 'address', 'label': 'The public address is set and is the one in use',
         'done': bool(url) and url.startswith('https://') and (not here or here == url),
         'detail': ("Not set." if not url else
                    f"{url} is saved, but you opened this page at {here}." if here and here != url else url),
         'link': '#details'},
        {'key': 'admins', 'label': 'Two administrators can sign in',
         'done': len(active) >= 2,
         'detail': f"{len(active)} of {len(admins)} administrator account{'s' if len(admins) != 1 else ''} "
                   "can sign in. A second one means nobody is locked out when one person leaves.",
         'link': '#admins'},
        {'key': 'support', 'label': 'People can reach someone for help', 'done': bool(p['support_email']),
         'detail': p['support_email'] or "No support email: help and privacy pages show no address.",
         'link': '#details'},
        {'key': 'units', 'label': 'Schools, departments or clubs are set up', 'done': bool(units),
         'detail': "At least one unit exists." if units else "None yet. Events can still be created without them.",
         'link': '/admin/org_units'},
        {'key': 'mail', 'label': 'Email can be sent', 'done': bool(mail),
         'detail': "A mail provider is configured." if mail else
                   "No mail provider is configured, so invitations, tickets and certificates can't be emailed.",
         'link': '/admin/system'},
        {'key': 'storage', 'label': 'Uploads are kept outside the server', 'done': storage in ('s3', 'gcs'),
         'detail': f"File storage: {storage}." if storage in ('s3', 'gcs') else
                   "Files are stored on the server's own disk, which a redeploy can erase.",
         'link': '/admin/system'},
        {'key': 'jobs', 'label': 'Scheduled jobs can run', 'done': _configured('CRON_SECRET'),
         'detail': "Reminders, closing registration on time and retries." if _configured('CRON_SECRET') else
                   "No scheduler secret: reminders and automatic closing won't run.",
         'link': '/admin/system'},
    ]
    return items


# ── Demo or the institution's own deployment (UPG-275) ───────────────────────

DEMO, PRODUCTION, DEVELOPMENT = 'demo', 'production', 'development'


def environment(config) -> dict:
    """What this copy of the portal is, read from its settings: a demo
    (`DEMO_ENVIRONMENT`), an institution's own deployment (`FLASK_ENV` is
    production) or a development copy. A demo says so on every page."""
    if config.get('DEMO_ENVIRONMENT'):
        return {'key': DEMO, 'label': 'Demo',
                'explanation': "This is a demo copy of the portal. Its people, events, registrations and figures "
                               "are sample data, and it may be emptied and rebuilt at any time."}
    if str(config.get('FLASK_ENV') or '') == 'production':
        return {'key': PRODUCTION, 'label': "The institution's own deployment",
                'explanation': "This is an institution's own deployment. Its events, registrations and "
                               "certificates are real records."}
    return {'key': DEVELOPMENT, 'label': 'Development copy',
            'explanation': "This is a development copy on someone's own machine, with test data."}

