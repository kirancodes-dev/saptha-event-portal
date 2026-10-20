"""
services_whatsapp.py — WhatsApp notifications through an official API (UPG-147).

Off unless a provider is configured (and `WHATSAPP_ENABLED` isn't `false`): Meta's
WhatsApp Cloud API (`WHATSAPP_PROVIDER=meta`, `META_WA_TOKEN`,
`META_WA_PHONE_ID`) or Twilio (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
`TWILIO_WHATSAPP_FROM`, UPG-49). Every message, old or new, passes `gate()`:
the person opted in (a checkbox at registration or their profile) and hasn't
replied STOP, and this month's cap (set by the Super Admin) isn't reached.
At the cap, WhatsApp stops for the month, the Super Admin is told once, and
email carries on as always (email never depends on WhatsApp).

The three messages here (registration confirmed, the day-before reminder,
change and cancellation notices) come from `config/whatsapp_templates.json`
and go out once each (`whatsapp_log`), through the outbox (UPG-18), which
retries a failed send.
"""
import datetime
import hashlib
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

TEMPLATES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'whatsapp_templates.json')
CONSENT = 'whatsapp_consent'
LOG = 'whatsapp_log'
USAGE = 'whatsapp_usage'
STOP_WORDS = ('STOP', 'STOPALL', 'UNSUBSCRIBE', 'CANCEL', 'END', 'QUIT')
START_WORDS = ('START', 'UNSTOP', 'SUBSCRIBE')


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _db():
    from models import db
    return db


def provider() -> str:
    return (os.environ.get('WHATSAPP_PROVIDER') or 'twilio').strip().lower()


def configured() -> bool:
    if provider() == 'meta':
        return bool(os.environ.get('META_WA_TOKEN', '').strip() and os.environ.get('META_WA_PHONE_ID', '').strip())
    return bool(os.environ.get('TWILIO_ACCOUNT_SID', '').strip() and os.environ.get('TWILIO_AUTH_TOKEN', '').strip())


def enabled() -> bool:
    """On when a provider is configured, unless WHATSAPP_ENABLED=false: with no
    provider settings (the default) nothing is ever sent."""
    return os.environ.get('WHATSAPP_ENABLED', '').strip().lower() != 'false' and configured()


def normalise(phone: str) -> str:
    """+91XXXXXXXXXX for a bare Indian mobile number; '' when it isn't a number."""
    digits = ''.join(c for c in str(phone or '') if c.isdigit())
    if str(phone or '').strip().startswith('+') and len(digits) >= 10:
        return '+' + digits
    if len(digits) == 10:
        return '+91' + digits
    if len(digits) == 12 and digits.startswith('91'):
        return '+' + digits
    return ''


def templates() -> dict:
    with open(TEMPLATES_FILE, encoding='utf-8') as fh:
        return {k: v for k, v in json.load(fh).items() if not k.startswith('_')}


def render(template: str, values: dict) -> str:
    spec = templates()[template]
    body = spec['body']
    for i, name in enumerate(spec['variables'], start=1):
        body = body.replace('{{%d}}' % i, str(values.get(name, '')))
    return body


# ── Consent ─────────────────────────────────────────────────────────────────

def set_consent(db, phone: str, opt_in: bool, source: str) -> bool:
    number = normalise(phone)
    if not number:
        return False
    from utils import log_action
    db.collection(CONSENT).document(number).set({'opt_in': bool(opt_in), 'at': _now().isoformat(), 'source': source})
    log_action(db, "WHATSAPP_OPT_IN" if opt_in else "WHATSAPP_OPT_OUT", f"{number[:-4]}**** via {source}")
    return True


def has_consent(db, phone: str) -> bool:
    number = normalise(phone)
    if not number:
        return False
    doc = db.collection(CONSENT).document(number).get()
    return bool(doc.exists and (doc.to_dict() or {}).get('opt_in'))


# ── The monthly cap ─────────────────────────────────────────────────────────

def monthly_cap(db) -> int:
    doc = db.collection('settings').document('whatsapp').get()
    saved = (doc.to_dict() or {}).get('monthly_cap') if doc.exists else None
    return int(saved if saved is not None else os.environ.get('WHATSAPP_MONTHLY_CAP', '1000'))


def set_monthly_cap(db, cap: int, actor: str) -> None:
    from utils import log_action
    if cap < 0:
        raise ValueError("The cap can't be negative.")
    db.collection('settings').document('whatsapp').set({'monthly_cap': int(cap), 'by': actor})
    log_action(db, "WHATSAPP_CAP", f"{actor}: {int(cap)} a month")


def _month() -> str:
    return _now().strftime('%Y-%m')


def used_this_month(db) -> int:
    doc = db.collection(USAGE).document(_month()).get()
    return int((doc.to_dict() or {}).get('count', 0)) if doc.exists else 0


def _count_send(db) -> None:
    ref = db.collection(USAGE).document(_month())
    doc = ref.get()
    row = (doc.to_dict() or {}) if doc.exists else {}
    row['count'] = int(row.get('count', 0)) + 1
    ref.set(row)


def _cap_reached(db) -> bool:
    if used_this_month(db) < monthly_cap(db):
        return False
    ref = db.collection(USAGE).document(_month())
    row = ref.get().to_dict() or {}
    if not row.get('alerted'):
        row['alerted'] = _now().isoformat()
        ref.set(row)
        _alert_admins(db)
    return True


def _alert_admins(db) -> None:
    from utils import log_action
    from utils_email import send_email_notification
    message = (f"SapthaEvent reached this month's WhatsApp cap ({monthly_cap(db)} messages). WhatsApp is paused "
               f"until next month; email carries on. Raise the cap on the WhatsApp settings page if needed.")
    admins = [d.id for d in db.collection('users').stream()
              if str((d.to_dict() or {}).get('role') or '') in ('SuperAdmin', 'Super Admin', 'UniversityAdmin')]
    for email in admins or [os.environ.get('SUPER_ADMIN_EMAIL', '')]:
        if email:
            send_email_notification(email, "WhatsApp cap reached", message)
    log_action(db, "WHATSAPP_CAP_REACHED", message)


def gate(phone: str, db=None, consented: bool = False) -> Optional[str]:
    """None when a WhatsApp message to this phone may go; else why not.
    `consented`: the caller checked the person's own opt-in (UPG-49's
    notification preference); a STOP reply still wins."""
    db = db or _db()
    if not enabled():
        return 'off'
    if consented:
        doc = db.collection(CONSENT).document(normalise(phone)).get() if normalise(phone) else None
        if doc is not None and doc.exists and (doc.to_dict() or {}).get('opt_in') is False:
            return 'no consent'
    elif not has_consent(db, phone):
        return 'no consent'
    if _cap_reached(db):
        return 'cap reached'
    return None


def counted(db=None) -> None:
    _count_send(db or _db())


# ── Sending the three template messages ─────────────────────────────────────

def _log_id(template: str, key: str, number: str) -> str:
    return hashlib.sha256(f"{template}|{key}|{number}".encode()).hexdigest()[:40]


def claim_once(db, template: str, key: str, phone: str) -> bool:
    """True the first time this message is claimed for this phone, False after."""
    number = normalise(phone) or str(phone)
    ref = db.collection(LOG).document(_log_id(template, key, number))
    if ref.get().exists:
        return False
    ref.set({'template': template, 'key': key, 'to': number, 'status': 'claimed', 'at': _now().isoformat()})
    return True


def release(db, template: str, key: str, phone: str) -> None:
    """Undo claim_once after a failed send, so the retry can send it."""
    number = normalise(phone) or str(phone)
    db.collection(LOG).document(_log_id(template, key, number)).delete()


def notify(db, template: str, phone: str, values: dict, key: str) -> str:
    """Queue one template message, once per (template, key, phone): 'queued',
    'already', or why not (off, no consent, cap reached, bad number)."""
    number = normalise(phone)
    if not number:
        return 'bad number'
    why = gate(number, db)
    if why:
        return why
    log_id = _log_id(template, key, number)
    ref = db.collection(LOG).document(log_id)
    if ref.get().exists:
        return 'already'
    ref.set({'template': template, 'key': key, 'to': number, 'status': 'queued', 'at': _now().isoformat()})
    try:
        from tasks.notification_tasks import send_whatsapp_template
        send_whatsapp_template.delay(log_id, number, template, values)
    except Exception:
        logger.exception("WhatsApp %s to %s not queued", template, number)
    return 'queued'


def deliver(log_id: str, number: str, template: str, values: dict) -> None:
    """The task's work: send once; raise on failure so the outbox retries it."""
    db = _db()
    ref = db.collection(LOG).document(log_id)
    row = ref.get().to_dict() or {}
    if row.get('status') == 'sent':
        return
    if _send_now(number, template, values):
        ref.update({'status': 'sent', 'sent_at': _now().isoformat()})
        _count_send(db)
        return
    ref.update({'status': 'failed', 'failed_at': _now().isoformat()})
    raise RuntimeError(f"WhatsApp {template} to {number[:-4]}**** failed")


def _send_now(number: str, template: str, values: dict) -> bool:
    if provider() == 'meta':
        import requests
        spec = templates()[template]
        payload = {'messaging_product': 'whatsapp', 'to': number.lstrip('+'), 'type': 'template',
                   'template': {'name': template, 'language': {'code': spec.get('language', 'en')},
                                'components': [{'type': 'body', 'parameters': [
                                    {'type': 'text', 'text': str(values.get(n, ''))} for n in spec['variables']]}]}}
        try:
            resp = requests.post(f"https://graph.facebook.com/v20.0/{os.environ['META_WA_PHONE_ID']}/messages",
                                 json=payload, timeout=15,
                                 headers={'Authorization': f"Bearer {os.environ['META_WA_TOKEN']}"})
            return resp.status_code < 300
        except Exception as exc:
            logger.warning("Meta WhatsApp send failed: %s", exc)
            return False
    from utils_whatsapp import _provider_send
    return _provider_send(number, render(template, values))


# ── Replies (STOP) ──────────────────────────────────────────────────────────

def handle_reply(db, phone: str, text: str) -> Optional[str]:
    word = str(text or '').strip().upper()
    if word in STOP_WORDS:
        set_consent(db, phone, False, 'reply STOP')
        return 'stopped'
    if word in START_WORDS:
        set_consent(db, phone, True, 'reply START')
        return 'started'
    return None
