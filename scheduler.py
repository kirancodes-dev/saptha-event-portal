"""
scheduler.py  —  Automated 24-hour Event Reminder System
=========================================================
Uses APScheduler (BackgroundScheduler) to run a job every hour.
The job scans all active events in Firestore and sends WhatsApp +
email reminders to every registered participant whose event starts
within the next 24 hours (and hasn't already received a reminder).

How it works
------------
1. On app startup, call  init_scheduler(app)
2. The scheduler runs  _reminder_job()  every hour in a background thread
3. The job queries Firestore for events whose date is tomorrow
4. For each such event it fetches all confirmed registrations
5. It sends a WhatsApp message + email to each lead participant
6. It writes  reminder_sent: True  to the registration doc so the same
   person never gets duplicate reminders even if the job runs again

Fields read from each 'events' doc
-----------------------------------
  title, date (string  "YYYY-MM-DD"  or  "YYYY-MM-DD HH:MM"),
  venue, status

Fields written to each 'registrations' doc
-------------------------------------------
  reminder_sent: True          (set once, never overwritten)
  reminder_sent_at: ISO string (for audit)

Environment variables required
-------------------------------
  MAIL_USER, MAIL_PASS         — same as the rest of the app (Flask-Mail)
  TWILIO_ACCOUNT_SID           — WhatsApp (optional — degrades gracefully)
  TWILIO_AUTH_TOKEN            — WhatsApp (optional)
  TWILIO_WHATSAPP_FROM         — WhatsApp (optional)

Install
-------
  pip install apscheduler
"""

import logging
import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval     import IntervalTrigger

logger = logging.getLogger(__name__)

# ─── lazy imports (only available once Flask app is set up) ───
_db  = None
_app = None


# ═══════════════════════════════════════════════════════
# PUBLIC — call once from app.py after app is created
# ═══════════════════════════════════════════════════════

def init_scheduler(flask_app):
    """
    Start the background scheduler.
    Call this ONCE at the bottom of app.py, inside  if __name__ == '__main__'
    OR just before  app.run().

    Usage in app.py:
        from scheduler import init_scheduler
        ...
        init_scheduler(app)
        app.run(...)
    """
    global _app
    _app = flask_app

    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        func    = _reminder_job,
        trigger = IntervalTrigger(hours=1),
        id      = "event_24h_reminder",
        name    = "24-hour event reminder",
        replace_existing = True,
        misfire_grace_time = 600,   # 10-minute grace if job is late
    )
    scheduler.start()

    # Run once immediately on startup so you don't have to wait an hour
    _reminder_job()

    logger.info("Reminder scheduler started — running every hour (IST)")
    return scheduler


# ═══════════════════════════════════════════════════════
# CORE JOB
# ═══════════════════════════════════════════════════════

def _reminder_job():
    """
    Scans Firestore for events starting tomorrow (IST) and sends
    reminder notifications to all confirmed registrants who haven't
    received one yet.
    """
    if _app is None:
        logger.warning("Reminder job: Flask app not set. Skipping.")
        return

    with _app.app_context():
        try:
            _run_reminders()
        except Exception as exc:
            logger.exception("Reminder job failed: %s", exc)


def _run_reminders():
    from models import db

    # ── What is "tomorrow" in IST? ─────────────────────────
    ist_now      = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    tomorrow_str = (ist_now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info("Reminder job: checking for events on %s", tomorrow_str)

    # ── Fetch all active events ────────────────────────────
    events_ref = (
        db.collection("events")
          .where("status", "==", "active")
          .stream()
    )

    events_tomorrow = []
    for doc in events_ref:
        d = doc.to_dict()
        d["id"] = doc.id
        # event.date may be "2026-04-15" or "2026-04-15 10:00 AM"
        event_date_str = str(d.get("date", "")).strip()[:10]   # take first 10 chars
        if event_date_str == tomorrow_str:
            events_tomorrow.append(d)

    if not events_tomorrow:
        logger.info("Reminder job: no events tomorrow, nothing to send.")
        return

    logger.info("Reminder job: found %d event(s) tomorrow", len(events_tomorrow))

    email_total = wa_total = skip_total = 0

    for event in events_tomorrow:
        event_id    = event["id"]
        event_title = event.get("title", "Event")
        event_date  = event.get("date",  "Tomorrow")
        event_venue = event.get("venue", "SNPSU Campus")

        # ── All confirmed registrations for this event ─────
        regs = (
            db.collection("registrations")
              .where("event_id", "==", event_id)
              .stream()
        )

        for reg_doc in regs:
            reg      = reg_doc.to_dict()
            reg_id   = reg_doc.id

            # Skip if already reminded
            if reg.get("reminder_sent"):
                skip_total += 1
                continue

            # Skip unconfirmed / eliminated
            status = reg.get("status", "")
            if status not in ("Confirmed", "Paid", "Free", ""):
                continue
            if reg.get("is_eliminated"):
                continue

            name   = reg.get("lead_name",  "Participant")
            email  = reg.get("lead_email", "")
            phone  = (reg.get("lead_phone") or
                      reg.get("phone") or
                      (reg.get("members") or [{}])[0].get("phone", ""))

            # ── Send email ─────────────────────────────────
            email_ok = False
            if email:
                email_ok = _send_reminder_email(
                    to_email    = email,
                    name        = name,
                    event_title = event_title,
                    event_date  = event_date,
                    venue       = event_venue,
                    reg_id      = reg_id,
                )
                if email_ok:
                    email_total += 1

            # ── Send WhatsApp ──────────────────────────────
            wa_ok = False
            if phone:
                wa_ok = _send_reminder_whatsapp(
                    phone       = phone,
                    name        = name,
                    event_title = event_title,
                    event_date  = event_date,
                    venue       = event_venue,
                    reg_id      = reg_id,
                )
                if wa_ok:
                    wa_total += 1

            # ── Mark reminder sent if at least one channel worked ──
            if email_ok or wa_ok:
                try:
                    db.collection("registrations").document(reg_id).update({
                        "reminder_sent":    True,
                        "reminder_sent_at": datetime.datetime.utcnow().isoformat(),
                    })
                except Exception as exc:
                    logger.warning("Could not mark reminder_sent for %s: %s", reg_id, exc)

    logger.info(
        "Reminder job complete — emails: %d, WhatsApp: %d, skipped (already sent): %d",
        email_total, wa_total, skip_total
    )


# ═══════════════════════════════════════════════════════
# NOTIFICATION HELPERS
# ═══════════════════════════════════════════════════════

def _send_reminder_email(to_email: str, name: str, event_title: str,
                          event_date: str, venue: str, reg_id: str) -> bool:
    """Send a branded HTML reminder email."""
    try:
        from flask_mail import Message
        from flask      import current_app

        mail = current_app.extensions.get("mail")
        if not mail:
            logger.warning("Flask-Mail not initialised, skipping email reminder")
            return False

        ticket_url = f"{current_app.config.get('BASE_URL', 'http://127.0.0.1:5000')}/ticket/{reg_id}"

        msg = Message(
            subject    = f"Reminder: {event_title} is Tomorrow!",
            recipients = [to_email],
        )

        msg.html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f7f6;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f7f6">
<tr><td align="center" style="padding:32px 16px;">
<table width="540" cellpadding="0" cellspacing="0" border="0"
       style="background:#ffffff;border-radius:12px;overflow:hidden;
              border:1px solid #e2e8f0;max-width:540px;">

  <!-- Header -->
  <tr>
    <td align="center"
        style="background:#0d2d62;padding:28px 32px 24px;">
      <div style="width:48px;height:48px;background:#f37021;border-radius:10px;
                  margin:0 auto 12px;line-height:48px;text-align:center;
                  font-size:20px;font-weight:900;color:#fff;">SE</div>
      <h2 style="margin:0;font-size:18px;font-weight:700;color:#ffffff;">
        &#9201; Tomorrow's Your Event!
      </h2>
    </td>
  </tr>

  <!-- Body -->
  <tr>
    <td style="padding:28px 32px;">
      <p style="margin:0 0 12px;font-size:15px;color:#1e293b;">
        Hello <strong>{name}</strong>,
      </p>
      <p style="margin:0 0 20px;font-size:14px;color:#475569;line-height:1.6;">
        This is a reminder that <strong>{event_title}</strong> is happening
        <strong>tomorrow</strong>. Here are your details:
      </p>

      <!-- Info box -->
      <table width="100%" cellpadding="0" cellspacing="0"
             style="background:#f8fafc;border-radius:10px;
                    border:1px solid #e2e8f0;margin-bottom:24px;">
        <tr>
          <td style="padding:16px 20px;border-bottom:1px solid #e2e8f0;">
            <span style="font-size:11px;text-transform:uppercase;letter-spacing:1px;
                         color:#94a3b8;font-weight:700;">Event</span><br>
            <span style="font-size:15px;font-weight:700;color:#0d2d62;">{event_title}</span>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 20px;border-bottom:1px solid #e2e8f0;">
            <span style="font-size:11px;text-transform:uppercase;letter-spacing:1px;
                         color:#94a3b8;font-weight:700;">Date &amp; Time</span><br>
            <span style="font-size:14px;color:#1e293b;">&#128197; {event_date}</span>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 20px;border-bottom:1px solid #e2e8f0;">
            <span style="font-size:11px;text-transform:uppercase;letter-spacing:1px;
                         color:#94a3b8;font-weight:700;">Venue</span><br>
            <span style="font-size:14px;color:#1e293b;">&#128205; {venue}</span>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 20px;">
            <span style="font-size:11px;text-transform:uppercase;letter-spacing:1px;
                         color:#94a3b8;font-weight:700;">Ticket ID</span><br>
            <span style="font-size:14px;font-family:monospace;color:#0d2d62;
                         font-weight:700;">{reg_id}</span>
          </td>
        </tr>
      </table>

      <!-- CTA button -->
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center">
            <a href="{ticket_url}"
               style="display:inline-block;background:#f37021;color:#ffffff;
                      font-size:14px;font-weight:700;padding:12px 32px;
                      border-radius:9px;text-decoration:none;">
              &#127918; View My QR Ticket
            </a>
          </td>
        </tr>
      </table>

      <p style="margin:24px 0 0;font-size:13px;color:#94a3b8;text-align:center;">
        Show the QR code at the venue entrance for entry.
      </p>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background:#f8fafc;padding:16px 32px;
               border-top:1px solid #e2e8f0;text-align:center;">
      <p style="margin:0;font-size:12px;color:#94a3b8;">
        SapthaEvent &nbsp;&middot;&nbsp; Sapthagiri NPS University, Bengaluru
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>
"""
        msg.body = (
            f"Reminder: {event_title} is Tomorrow!\n\n"
            f"Hello {name},\n\n"
            f"Event: {event_title}\n"
            f"Date:  {event_date}\n"
            f"Venue: {venue}\n"
            f"Ticket ID: {reg_id}\n\n"
            f"View your QR ticket: {ticket_url}\n\n"
            f"— SapthaEvent, Sapthagiri NPS University"
        )

        mail.send(msg)
        logger.debug("Reminder email sent to %s for event %s", to_email, event_title)
        return True

    except Exception as exc:
        logger.error("Reminder email failed to %s: %s", to_email, exc)
        return False


def _send_reminder_whatsapp(phone: str, name: str, event_title: str,
                             event_date: str, venue: str, reg_id: str) -> bool:
    """Send a WhatsApp reminder. Silently skips if Twilio not configured."""
    try:
        from utils_whatsapp import send_event_reminder_whatsapp
        return send_event_reminder_whatsapp(
            phone       = phone,
            name        = name,
            event_title = event_title,
            event_date  = event_date,
            venue       = venue,
            reg_id      = reg_id,
        )
    except ImportError:
        logger.debug("utils_whatsapp not available, skipping WhatsApp reminder")
        return False
    except Exception as exc:
        logger.error("WhatsApp reminder failed to %s: %s", phone, exc)
        return False