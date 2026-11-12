"""
services_event_contact.py — the event's own ticket guidelines and support
email (UPG-242).

The ticket's back used to show four fixed "venue guidelines" and a fixed
contact for every event. The SPOC now types the event's own guidelines (one
per line, shown as a list on the ticket) and a support email, which the
ticket and the participant emails show ("Questions? Write to ...").
"""
import re

MAX_LINES = 12
LINE_MAX = 300
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

DEFAULT_GUIDELINES = [
    "Report to the venue 15 minutes before the start time.",
    "Carry your college ID card for physical verification.",
    "Set mobile screen brightness to maximum for QR scanning.",
    "No food or beverages allowed inside the laboratories.",
]


def clean_guidelines(text: str) -> str:
    """One guideline per line: numbering ("01.", "1)", "-") taken off, blank
    lines dropped, at most 12."""
    lines = []
    for raw in str(text or '').replace('\r\n', '\n').split('\n'):
        line = re.sub(r'^\s*(?:[-*•]|\d{1,2}\s*[.)])\s*', '', raw).strip()
        if line:
            lines.append(' '.join(line.split())[:LINE_MAX])
    return '\n'.join(lines[:MAX_LINES])


def guidelines(event: dict) -> list:
    """The event's ticket guidelines, or the general ones when it has none."""
    own = [line for line in str((event or {}).get('ticket_guidelines') or '').split('\n') if line.strip()]
    return own or list(DEFAULT_GUIDELINES)


def valid_email(value: str) -> bool:
    value = str(value or '').strip()
    return not value or (bool(_EMAIL.match(value)) and len(value) <= 254)


def support_email(event: dict) -> str:
    value = str((event or {}).get('support_email') or '').strip().lower()
    return value if value and valid_email(value) else ''


def support_text(event: dict) -> str:
    """The line plain-text participant emails end with, or ''."""
    email = support_email(event)
    return f"\nQuestions? Write to {email}\n" if email else ''


def for_registration(reg_id: str) -> str:
    """The support email of a registration's event ('' if none or unreadable)."""
    try:
        from models import db
        reg = db.collection('registrations').document(str(reg_id)).get()
        event_id = (reg.to_dict() or {}).get('event_id') if reg.exists else ''
        event = db.collection('events').document(str(event_id)).get() if event_id else None
        return support_email(event.to_dict() or {}) if event is not None and event.exists else ''
    except Exception:
        return ''
