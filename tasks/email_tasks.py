"""
tasks/email_tasks.py — Async email delivery
============================================
All email sends go through these tasks so the web workers return
immediately (fire-and-forget) and the Celery email worker handles
retries, back-off, and delivery tracking.

Queued on: 'email'
"""

import logging
from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    queue='email',
    max_retries=3,
    default_retry_delay=30,
    name='tasks.email_tasks.send_ticket_email_task',
)
def send_ticket_email_task(self, to_email: str, name: str, event_title: str,
                            reg_id: str, event_date: str = '', venue: str = '',
                            is_new_user: bool = False, raw_password: str = ''):
    """Send a registration confirmation / QR ticket email."""
    try:
        from utils_email import send_ticket_email
        send_ticket_email(
            to_email=to_email,
            name=name,
            event_title=event_title,
            reg_id=reg_id,
            event_date=event_date,
            venue=venue,
            is_new_user=is_new_user,
            raw_password=raw_password,
        )
        logger.info("ticket email sent to %s reg=%s", to_email, reg_id)
    except Exception as exc:
        logger.warning("ticket email failed to %s: %s — retry %d", to_email, exc, self.request.retries)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='email',
    max_retries=3,
    default_retry_delay=60,
    name='tasks.email_tasks.send_reminder_email_task',
)
def send_reminder_email_task(self, to_email: str, name: str, event_title: str,
                              event_date: str, venue: str, reg_id: str):
    """Send a 24-hour event reminder email."""
    try:
        import os
        from utils_email import _send
        base_url = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
        ticket_url = f"{base_url}/ticket/{reg_id}"
        html = _reminder_html(name, event_title, event_date, venue, reg_id, ticket_url)
        _send(to_email, f"⏰ Reminder: {event_title} is Tomorrow!", html)
        logger.info("reminder email sent to %s for %s", to_email, event_title)
    except Exception as exc:
        logger.warning("reminder email failed %s: %s", to_email, exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='email',
    max_retries=3,
    default_retry_delay=30,
    name='tasks.email_tasks.send_generic_email_task',
)
def send_generic_email_task(self, to_email: str, subject: str,
                             body_text: str, body_html: str = ''):
    """Generic fire-and-forget email for announcements, password resets, etc."""
    try:
        from utils_email import _send
        html = body_html or f"<pre style='font-family:sans-serif'>{body_text}</pre>"
        _send(to_email, subject, html)
        logger.info("generic email sent to %s subject=%r", to_email, subject)
    except Exception as exc:
        logger.warning("generic email failed to %s: %s — retry %d",
                       to_email, exc, self.request.retries)
        raise self.retry(exc=exc)


# ── HTML template helper ──────────────────────────────────

def _reminder_html(name, event_title, event_date, venue, reg_id, ticket_url):
    from utils_email import _html_wrapper
    content = f"""
    <h3 style="color:#0f172a; font-size:20px; font-weight:700; margin-top:0; margin-bottom:16px;">⏰ Your Event is Tomorrow!</h3>
    <p style="margin-bottom: 20px;">
      Hello <strong>{name}</strong>, get ready! <strong>{event_title}</strong> is happening tomorrow.
    </p>
    
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin: 24px 0; font-size: 14px;">
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
        <tr>
          <td style="padding: 8px 0; color: #94a3b8; text-transform: uppercase; font-size: 11px; font-weight: 700;">Event</td>
          <td style="padding: 8px 0; color: #1a2557; font-weight: 700; text-align: right;">{event_title}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; color: #94a3b8; text-transform: uppercase; font-size: 11px; font-weight: 700;">Date</td>
          <td style="padding: 8px 0; color: #0f172a; font-weight: 600; text-align: right;">📅 {event_date}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; color: #94a3b8; text-transform: uppercase; font-size: 11px; font-weight: 700;">Venue</td>
          <td style="padding: 8px 0; color: #0f172a; font-weight: 600; text-align: right;">📍 {venue}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; color: #94a3b8; text-transform: uppercase; font-size: 11px; font-weight: 700;">Ticket ID</td>
          <td style="padding: 8px 0; font-family: monospace; color: #1a2557; font-weight: 700; text-align: right;">{reg_id}</td>
        </tr>
      </table>
    </div>
    
    <div style="text-align: center; margin: 30px 0;">
      <a href="{ticket_url}" style="background-color: #c9a45e; color: #ffffff; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: 700; display: inline-block; box-shadow: 0 4px 12px rgba(201, 164, 94, 0.25);">
        🎫 View My QR Ticket
      </a>
    </div>
    
    <p>Please report to the venue on time with your ticket ID or QR code ready for scanning.</p>
    """
    return _html_wrapper(content, f"Event Reminder — {event_title}")

