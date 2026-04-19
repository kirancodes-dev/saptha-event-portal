"""
utils_whatsapp.py — SapthaEvent WhatsApp Notifications via Twilio

HOW TO ENABLE:
  Add these 3 variables in Railway → Variables:
    TWILIO_ACCOUNT_SID   = ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_AUTH_TOKEN    = your_auth_token_here
    TWILIO_WHATSAPP_FROM = whatsapp:+14155238886

HOW TO GET THEM (free Twilio trial, no credit card):
  1. Go to twilio.com → Sign up free
  2. Dashboard → Account SID + Auth Token are shown on homepage
  3. Messaging → Try it Out → Send a WhatsApp message
     → Follow sandbox instructions (student texts "join <word>" to +1 415 523 8886)
  4. Sandbox number = whatsapp:+14155238886

IMPORTANT — Sandbox restriction:
  Each recipient must opt in by texting the join code ONCE.
  After that they receive all messages from your portal.
  This restriction is removed when you upgrade to a paid Twilio number.

PHONE NUMBER FORMAT:
  Store phone numbers in Firestore as: 9876543210  (10 digits, no country code)
  This file automatically prepends +91 (India).
  Change _fmt_phone() below if your students are outside India.

GRACEFUL DEGRADATION:
  All functions return False silently if Twilio is not configured.
  The app never crashes — WhatsApp is always optional.
"""

import os
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _client():
    """Return a Twilio REST client, or None if not configured."""
    sid   = os.environ.get('TWILIO_ACCOUNT_SID',   '').strip()
    token = os.environ.get('TWILIO_AUTH_TOKEN',    '').strip()
    if not sid or not token:
        return None
    try:
        from twilio.rest import Client
        return Client(sid, token)
    except ImportError:
        logger.warning("Twilio not installed. Run: pip install twilio")
        return None
    except Exception as exc:
        logger.error("Twilio client init failed: %s", exc)
        return None


def _from_number() -> str:
    return os.environ.get('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')


def _fmt_phone(phone: str) -> str:
    """
    Normalise a phone number to WhatsApp E.164 format.
    Assumes +91 (India) if no country code is present.
    """
    if not phone:
        return ''
    # Strip spaces, dashes, brackets
    p = ''.join(c for c in str(phone) if c.isdigit() or c == '+')
    if p.startswith('+'):
        return f'whatsapp:{p}'
    if len(p) == 10:          # bare Indian mobile number
        return f'whatsapp:+91{p}'
    if len(p) == 12 and p.startswith('91'):
        return f'whatsapp:+{p}'
    return f'whatsapp:+{p}'   # best-effort


def _send(to_phone: str, body: str) -> bool:
    """
    Core send function. Returns True on success, False on any failure.
    Never raises.
    """
    client = _client()
    if not client:
        return False

    to_wa = _fmt_phone(to_phone)
    if not to_wa or len(to_wa) < 15:
        logger.warning("WhatsApp: invalid phone '%s' — skipped", to_phone)
        return False

    try:
        msg = client.messages.create(
            from_=_from_number(),
            to=to_wa,
            body=body,
        )
        logger.info("WhatsApp sent → %s | SID: %s", to_wa, msg.sid)
        return True
    except Exception as exc:
        logger.error("WhatsApp failed → %s | %s", to_wa, exc)
        return False


# ─────────────────────────────────────────────────────────────
# PUBLIC SEND FUNCTIONS — called from routes
# ─────────────────────────────────────────────────────────────

def send_ticket_whatsapp(phone: str, name: str, event_title: str,
                         reg_id: str, base_url: str = '') -> bool:
    """
    Sent when a participant registers for a free event
    or after payment confirmation for a paid event.
    """
    base = base_url or os.environ.get(
        'BASE_URL', 'https://saptha-event-portal-production.up.railway.app')
    body = (
        f"🎟️ *Registration Confirmed!*\n\n"
        f"Hi {name},\n"
        f"You're registered for *{event_title}*.\n\n"
        f"📌 *Ticket ID:* `{reg_id}`\n\n"
        f"Show this ID at the venue for check-in.\n"
        f"👉 Dashboard: {base}/participant/dashboard"
    )
    return _send(phone, body)


def send_payment_receipt_whatsapp(phone: str, name: str, event_title: str,
                                  amount: float, payment_id: str) -> bool:
    """
    Sent after successful Razorpay payment.
    """
    body = (
        f"✅ *Payment Received!*\n\n"
        f"Hi {name},\n"
        f"Your payment of *₹{amount}* for *{event_title}* is confirmed.\n\n"
        f"🧾 *Payment ID:* `{payment_id}`\n\n"
        f"Keep this for your records. Your ticket will arrive by email."
    )
    return _send(phone, body)


def send_staff_credentials_whatsapp(phone: str, name: str, role: str,
                                     event_title: str, email: str,
                                     password: str) -> bool:
    """
    Sent when SPOC appoints a Judge or Coordinator.
    """
    base = os.environ.get(
        'BASE_URL', 'https://saptha-event-portal-production.up.railway.app')
    body = (
        f"🔐 *Your SapthaEvent Login*\n\n"
        f"Hi {name},\n"
        f"You've been appointed as *{role}* for *{event_title}*.\n\n"
        f"📧 Email:    {email}\n"
        f"🔑 Password: `{password}`\n\n"
        f"👉 Login at: {base}/login\n\n"
        f"⚠️ Change your password after first login."
    )
    return _send(phone, body)


def send_room_assignment_whatsapp(phone: str, lead_name: str,
                                   event_title: str, room: str,
                                   judge_name: str, report_time: str = '') -> bool:
    """
    Sent to team lead when room/judge assignment is done by SPOC.
    """
    time_line = f"\n⏰ Report by: {report_time}" if report_time else ''
    body = (
        f"📍 *Room Assignment — {event_title}*\n\n"
        f"Hi {lead_name},\n"
        f"Your team has been assigned:\n\n"
        f"🏠 *Room:* {room}\n"
        f"👨‍⚖️ *Judge:* {judge_name}"
        f"{time_line}\n\n"
        f"Please report on time. Good luck! 🍀"
    )
    return _send(phone, body)


def send_elimination_whatsapp(phone: str, lead_name: str,
                               event_title: str, round_name: str = '') -> bool:
    """
    Sent to a team that has been eliminated from the event.
    """
    round_line = f" after *{round_name}*" if round_name else ''
    body = (
        f"📋 *Event Update — {event_title}*\n\n"
        f"Hi {lead_name},\n"
        f"Your team has been eliminated{round_line}.\n\n"
        f"Thank you for participating! 🙏\n"
        f"Better luck next time. Stay tuned for future events on the portal."
    )
    return _send(phone, body)


def send_result_whatsapp(phone: str, lead_name: str, event_title: str,
                          rank: int, score: float) -> bool:
    """
    Sent to top-3 winners when SPOC publishes final results.
    """
    rank_emojis = {1: '🥇', 2: '🥈', 3: '🥉'}
    emoji = rank_emojis.get(rank, '🏅')
    base  = os.environ.get(
        'BASE_URL', 'https://saptha-event-portal-production.up.railway.app')
    body = (
        f"{emoji} *Congratulations, {lead_name}!*\n\n"
        f"Results are out for *{event_title}*.\n\n"
        f"🏆 *Your Rank:* {rank}\n"
        f"📊 *Score:*     {score}\n\n"
        f"Your certificate has been emailed to you.\n"
        f"👉 View at: {base}/participant/dashboard"
    )
    return _send(phone, body)


def send_broadcast_whatsapp(phone_list: list, event_title: str,
                             subject: str, message: str) -> dict:
    """
    Sends a broadcast message to a list of phone numbers.
    Returns {"sent": N, "failed": M}.
    Used by SPOC from the broadcast panel on the dashboard.
    """
    body = (
        f"📢 *{subject}*\n\n"
        f"Event: *{event_title}*\n\n"
        f"{message}\n\n"
        f"— SapthaEvent Portal"
    )
    sent   = 0
    failed = 0
    for phone in phone_list:
        if phone:
            if _send(phone, body):
                sent += 1
            else:
                failed += 1
    logger.info("Broadcast done — sent: %d, failed: %d", sent, failed)
    return {"sent": sent, "failed": failed}