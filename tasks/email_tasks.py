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
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f7f6;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#f4f7f6">
<tr><td align="center" style="padding:32px 16px;">
<table width="540" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:12px;border:1px solid #e2e8f0;max-width:540px;">
  <tr>
    <td align="center" style="background:#1a2557;padding:28px 32px 24px;">
      <h2 style="margin:0;font-size:18px;color:#fff;">&#9201; Tomorrow's Your Event!</h2>
    </td>
  </tr>
  <tr>
    <td style="padding:28px 32px;">
      <p style="margin:0 0 12px;font-size:15px;color:#1e293b;">Hello <strong>{name}</strong>,</p>
      <p style="margin:0 0 20px;font-size:14px;color:#475569;line-height:1.6;">
        <strong>{event_title}</strong> is happening <strong>tomorrow</strong>.
      </p>
      <table width="100%" style="background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;margin-bottom:24px;">
        <tr><td style="padding:14px 20px;border-bottom:1px solid #e2e8f0;">
          <span style="font-size:11px;text-transform:uppercase;color:#94a3b8;">Event</span><br>
          <strong style="color:#1a2557;">{event_title}</strong>
        </td></tr>
        <tr><td style="padding:14px 20px;border-bottom:1px solid #e2e8f0;">
          <span style="font-size:11px;text-transform:uppercase;color:#94a3b8;">Date</span><br>
          &#128197; {event_date}
        </td></tr>
        <tr><td style="padding:14px 20px;border-bottom:1px solid #e2e8f0;">
          <span style="font-size:11px;text-transform:uppercase;color:#94a3b8;">Venue</span><br>
          &#128205; {venue}
        </td></tr>
        <tr><td style="padding:14px 20px;">
          <span style="font-size:11px;text-transform:uppercase;color:#94a3b8;">Ticket ID</span><br>
          <code style="color:#1a2557;">{reg_id}</code>
        </td></tr>
      </table>
      <table width="100%"><tr><td align="center">
        <a href="{ticket_url}"
           style="display:inline-block;background:#c9a227;color:#fff;
                  font-size:14px;font-weight:700;padding:12px 32px;
                  border-radius:9px;text-decoration:none;">
          &#127918; View My QR Ticket
        </a>
      </td></tr></table>
    </td>
  </tr>
  <tr>
    <td style="background:#f8fafc;padding:16px 32px;border-top:1px solid #e2e8f0;text-align:center;">
      <p style="margin:0;font-size:12px;color:#94a3b8;">
        SapthaEvent &middot; Sapthagiri NPS University, Bengaluru
      </p>
    </td>
  </tr>
</table>
</td></tr>
</table>
</body>
</html>"""
