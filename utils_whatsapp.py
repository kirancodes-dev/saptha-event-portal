"""
utils_whatsapp.py  —  WhatsApp Notifications via Twilio

Setup (one time):
  1. Create a free Twilio account at https://twilio.com
  2. Enable the WhatsApp Sandbox:
       Console → Messaging → Try it out → Send a WhatsApp message
  3. Your sandbox number will look like: +14155238886
  4. Students must send "join <your-sandbox-word>" to that number once
     to opt in (sandbox only — production removes this requirement)
  5. Set these 3 environment variables on Render and in your .env:
       TWILIO_ACCOUNT_SID   = ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
       TWILIO_AUTH_TOKEN    = your_auth_token
       TWILIO_WHATSAPP_FROM = whatsapp:+14155238886

Production upgrade path:
  - Apply for a Twilio WhatsApp Business number (takes ~1 week approval)
  - Once approved, remove the sandbox opt-in requirement
  - Update TWILIO_WHATSAPP_FROM to your approved number
  - All message functions below work identically — no code changes needed

Phone number format:
  All numbers must include the country code without spaces or dashes.
  India: 9876543210  →  +919876543210  (we handle the + prefix below)

Message templates:
  Twilio sandbox accepts freeform messages.
  Twilio production requires pre-approved templates for outbound messages.
  This file uses freeform format — works immediately on sandbox.
"""

import os
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# =========================================================
# TWILIO CLIENT (lazy-loaded so app starts even if not configured)
# =========================================================

_client = None


def _get_client():
    """Return a Twilio REST client, initialised once."""
    global _client
    if _client is not None:
        return _client

    try:
        from twilio.rest import Client
        sid   = os.environ.get('TWILIO_ACCOUNT_SID',   '').strip()
        token = os.environ.get('TWILIO_AUTH_TOKEN',    '').strip()
        if not sid or not token:
            raise RuntimeError(
                "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set "
                "as environment variables."
            )
        _client = Client(sid, token)
        return _client
    except ImportError:
        raise RuntimeError(
            "twilio package is not installed. "
            "Run: pip install twilio"
        )


def _from_number() -> str:
    """WhatsApp-prefixed sender number from env."""
    raw = os.environ.get('TWILIO_WHATSAPP_FROM', '').strip()
    if not raw:
        raise RuntimeError("TWILIO_WHATSAPP_FROM environment variable is not set.")
    return raw if raw.startswith('whatsapp:') else f'whatsapp:{raw}'


def _format_phone(phone: str) -> Optional[str]:
    """
    Normalise an Indian mobile number to E.164 format.
    Accepts:  9876543210 / 09876543210 / +919876543210 / 91-9876543210
    Returns:  whatsapp:+919876543210  or None if invalid
    """
    if not phone:
        return None

    # Strip all non-digit characters
    digits = re.sub(r'\D', '', str(phone))

    # Indian numbers: 10 digits → prepend 91
    if len(digits) == 10:
        digits = '91' + digits
    # Already has country code prefix
    elif len(digits) == 12 and digits.startswith('91'):
        pass
    elif len(digits) == 11 and digits.startswith('0'):
        digits = '91' + digits[1:]
    else:
        logger.warning("Could not normalise phone number: %s", phone)
        return None

    return f'whatsapp:+{digits}'


def _send(to_phone: str, body: str) -> bool:
    """
    Core send function. Returns True on success, False on any error.
    Never raises — always safe to call from a route without try/except.
    """
    try:
        to = _format_phone(to_phone)
        if not to:
            logger.error("WhatsApp send skipped — invalid phone: %s", to_phone)
            return False

        client = _get_client()
        msg = client.messages.create(
            from_=_from_number(),
            to=to,
            body=body
        )
        logger.info("WhatsApp sent to %s — SID: %s", to_phone, msg.sid)
        return True

    except Exception as exc:
        logger.error("WhatsApp send failed to %s — %s", to_phone, exc)
        return False


def _send_bulk(phone_list: list, body: str) -> dict:
    """
    Send the same message to multiple numbers.
    Returns {'sent': N, 'failed': N}
    """
    sent = failed = 0
    for phone in phone_list:
        if _send(phone, body):
            sent += 1
        else:
            failed += 1
    return {'sent': sent, 'failed': failed}


# =========================================================
# 1. REGISTRATION TICKET CONFIRMATION
#    Sent immediately after a student registers (free or paid).
# =========================================================

def send_ticket_whatsapp(phone: str, name: str, event_title: str,
                          reg_id: str, event_date: str = '',
                          venue: str = '',
                          base_url: str = '') -> bool:
    """
    Sends a compact ticket confirmation to the participant's WhatsApp.
    Called from routes_participant.py and routes_payment.py after
    a successful registration.
    """
    base_url = base_url or os.environ.get('BASE_URL', 'http://127.0.0.1:5000')

    lines = [
        f"🎟️ *Registration Confirmed!*",
        f"",
        f"Hello {name}! You're in for *{event_title}*.",
        f"",
        f"📋 *Ticket ID:* `{reg_id}`",
    ]
    if event_date:
        lines.append(f"📅 *Date:* {event_date}")
    if venue:
        lines.append(f"📍 *Venue:* {venue}")

    lines += [
        f"",
        f"🔗 View your ticket & QR code:",
        f"{base_url}/ticket/{reg_id}",
        f"",
        f"Show this QR at the venue entrance.",
        f"_— SapthaEvent, Sapthagiri NPS University_",
    ]

    return _send(phone, '\n'.join(lines))


# =========================================================
# 2. ROOM & JUDGE ASSIGNMENT ALERT
#    Sent after the coordinator runs room allocation.
# =========================================================

def send_room_assignment_whatsapp(phone: str, name: str, event_title: str,
                                   round_num: int, room: str,
                                   judge_name: str) -> bool:
    """
    Notifies a team lead about their room and judge assignment.
    Called from routes_coordinator.py → trigger_reminders().
    """
    body = (
        f"⚡ *Round {round_num} Assignment — {event_title}*\n\n"
        f"Hello {name}!\n\n"
        f"🏠 *Your Room:* {room}\n"
        f"👨‍⚖️ *Your Judge:* {judge_name}\n\n"
        f"Please report to your room immediately.\n"
        f"*All the best! 🚀*\n\n"
        f"_— SapthaEvent_"
    )
    return _send(phone, body)


# =========================================================
# 3. RESULT / WINNER ANNOUNCEMENT
#    Sent when the coordinator publishes final results.
# =========================================================

def send_result_whatsapp(phone: str, name: str, event_title: str,
                          rank: int, score: float) -> bool:
    """
    Notifies a winner their rank and score.
    Called from routes_coordinator.py → publish_results().
    """
    medals = {1: "🥇 1st Place", 2: "🥈 2nd Place", 3: "🥉 3rd Place"}
    rank_text = medals.get(rank, f"🏅 Top {rank}")

    body = (
        f"🏆 *Results Published — {event_title}*\n\n"
        f"Congratulations {name}!\n\n"
        f"{rank_text}\n"
        f"📊 *Final Score:* {score}\n\n"
        f"Log in to the portal to view the full leaderboard "
        f"and download your certificate.\n\n"
        f"_— SapthaEvent, Sapthagiri NPS University_"
    )
    return _send(phone, body)


# =========================================================
# 4. ELIMINATION NOTIFICATION
#    Sent to teams that did not advance to the next round.
# =========================================================

def send_elimination_whatsapp(phone: str, name: str,
                               event_title: str, round_num: int) -> bool:
    """
    Gently notifies a team they were eliminated.
    Called from routes_coordinator.py → promote_round().
    """
    body = (
        f"📋 *{event_title} — Round {round_num} Results*\n\n"
        f"Hello {name},\n\n"
        f"Thank you for participating in Round {round_num}. "
        f"Unfortunately your team did not advance to the next round.\n\n"
        f"Your participation certificate will be available in the portal shortly.\n\n"
        f"Keep building! 💪\n"
        f"_— SapthaEvent_"
    )
    return _send(phone, body)


# =========================================================
# 5. BROADCAST MESSAGE
#    Send a custom message from coordinator to all participants.
#    Called from routes_coordinator.py → broadcast_message().
# =========================================================

def send_broadcast_whatsapp(phone_list: list, event_title: str,
                              subject: str, message: str) -> dict:
    """
    Sends a custom broadcast to a list of phone numbers.
    Returns {'sent': N, 'failed': N}
    """
    body = (
        f"📢 *[{event_title}] {subject}*\n\n"
        f"{message}\n\n"
        f"_— Event Organizers_"
    )
    return _send_bulk(phone_list, body)


# =========================================================
# 6. PAYMENT RECEIPT
#    Sent after a successful payment via Razorpay / simulation.
# =========================================================

def send_payment_receipt_whatsapp(phone: str, name: str, event_title: str,
                                   reg_id: str, amount: int) -> bool:
    """
    Sends a payment confirmation receipt.
    Called from routes_payment.py after payment is confirmed.
    """
    body = (
        f"✅ *Payment Confirmed — {event_title}*\n\n"
        f"Hello {name},\n\n"
        f"💰 *Amount Paid:* ₹{amount}\n"
        f"🎟️ *Ticket ID:* `{reg_id}`\n\n"
        f"Your registration is confirmed. "
        f"Keep your Ticket ID handy for entry.\n\n"
        f"_— SapthaEvent_"
    )
    return _send(phone, body)


# =========================================================
# 7. STAFF CREDENTIALS
#    Sent when a Judge or EventCoordinator account is created.
# =========================================================

def send_staff_credentials_whatsapp(phone: str, name: str, role: str,
                                      event_title: str, email: str,
                                      password: str) -> bool:
    """
    Sends login credentials to a newly appointed staff member.
    Called from routes_coordinator.py → assign_staff().
    """
    body = (
        f"👋 *Welcome to SapthaEvent, {name}!*\n\n"
        f"You have been appointed as *{role}* for:\n"
        f"📌 *{event_title}*\n\n"
        f"🔑 *Your Login Credentials:*\n"
        f"Email: {email}\n"
        f"Password: `{password}`\n\n"
        f"⚠️ You will be asked to change this on first login.\n\n"
        f"_— SapthaEvent Admin_"
    )
    return _send(phone, body)


# =========================================================
# 8. EVENT REMINDER  (can be triggered manually or via cron)
# =========================================================

def send_event_reminder_whatsapp(phone: str, name: str, event_title: str,
                                   event_date: str, venue: str,
                                   reg_id: str) -> bool:
    """
    24-hour reminder before an event starts.
    Can be triggered manually from coordinator dashboard or via a cron job.
    """
    body = (
        f"⏰ *Event Reminder — Tomorrow!*\n\n"
        f"Hello {name},\n\n"
        f"*{event_title}* is happening tomorrow!\n\n"
        f"📅 *Date:* {event_date}\n"
        f"📍 *Venue:* {venue}\n"
        f"🎟️ *Ticket ID:* `{reg_id}`\n\n"
        f"Don't forget to bring your Ticket ID for entry.\n"
        f"See you there! 🎉\n\n"
        f"_— SapthaEvent_"
    )
    return _send(phone, body)


# =========================================================
# 9. WHATSAPP STATUS CHECK (for admin testing)
# =========================================================

def check_whatsapp_config() -> dict:
    """
    Returns a dict with config status. Call from admin panel to verify setup.
    Example: GET /admin/whatsapp_status
    """
    status = {
        'account_sid_set':   bool(os.environ.get('TWILIO_ACCOUNT_SID')),
        'auth_token_set':    bool(os.environ.get('TWILIO_AUTH_TOKEN')),
        'from_number_set':   bool(os.environ.get('TWILIO_WHATSAPP_FROM')),
        'twilio_installed':  False,
        'ready':             False,
    }
    try:
        import twilio  # noqa
        status['twilio_installed'] = True
    except ImportError:
        pass

    status['ready'] = all([
        status['account_sid_set'],
        status['auth_token_set'],
        status['from_number_set'],
        status['twilio_installed'],
    ])
    return status