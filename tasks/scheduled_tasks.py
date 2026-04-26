"""
tasks/scheduled_tasks.py — Celery Beat scheduled jobs
======================================================
These tasks replace APScheduler running inside the web workers.
They run in the dedicated celery-beat container so the web fleet
remains fully stateless.

Beat schedule is defined in celery_app.py.

Jobs:
  send_24h_reminders   — every hour: email + WhatsApp for tomorrow's events
  run_event_lifecycle  — every 6h: close regs, delete stale events
  log_backup_ping      — daily 01:30 IST: remind ops to verify GCS backup
"""

import logging
import datetime
from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    queue='default',
    max_retries=2,
    default_retry_delay=300,
    name='tasks.scheduled_tasks.send_24h_reminders',
    time_limit=3600,
)
def send_24h_reminders(self):
    """
    Scan Firestore for events starting tomorrow (IST).
    For each confirmed registrant who hasn't been reminded, queue
    individual email + WhatsApp reminder tasks.
    """
    try:
        from models import db
        from tasks.email_tasks import send_ticket_email_task
        from tasks.notification_tasks import send_reminder_whatsapp_task

        ist_now      = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
        tomorrow_str = (ist_now + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        logger.info("send_24h_reminders: scanning for events on %s", tomorrow_str)

        events_ref = db.collection('events').where('status', '==', 'active').stream()
        events_tomorrow = [
            {**doc.to_dict(), 'id': doc.id}
            for doc in events_ref
            if str((doc.to_dict() or {}).get('date', ''))[:10] == tomorrow_str
        ]

        if not events_tomorrow:
            logger.info("send_24h_reminders: no events tomorrow")
            return {'queued_emails': 0, 'queued_wa': 0}

        queued_emails = queued_wa = skipped = 0

        for event in events_tomorrow:
            event_id    = event['id']
            event_title = event.get('title', 'Event')
            event_date  = event.get('date', tomorrow_str)
            venue       = event.get('venue', 'SNPSU Campus')

            regs = db.collection('registrations').where('event_id', '==', event_id).stream()

            for reg_doc in regs:
                reg    = reg_doc.to_dict()
                reg_id = reg_doc.id

                if reg.get('ticket_sent'):
                    skipped += 1
                    continue
                if reg.get('status', '') not in ('Confirmed', 'Paid', 'Free', ''):
                    continue
                if reg.get('is_eliminated'):
                    continue

                name  = reg.get('lead_name', 'Participant')
                email = reg.get('lead_email', '')
                phone = (reg.get('lead_phone') or
                         reg.get('phone') or
                         (reg.get('members') or [{}])[0].get('phone', ''))

                # Send the actual entry ticket (with QR link) 1 day before
                if email:
                    send_ticket_email_task.delay(
                        to_email=email,
                        name=name,
                        event_title=event_title,
                        reg_id=reg_id,
                        event_date=event_date,
                        venue=venue,
                    )
                    queued_emails += 1

                if phone:
                    send_reminder_whatsapp_task.delay(
                        phone=phone,
                        name=name,
                        event_title=event_title,
                        event_date=event_date,
                        venue=venue,
                        reg_id=reg_id,
                    )
                    queued_wa += 1

                try:
                    db.collection('registrations').document(reg_id).update({
                        'ticket_sent':    True,
                        'ticket_sent_at': datetime.datetime.utcnow().isoformat(),
                    })
                except Exception:
                    pass

        logger.info(
            "send_24h_reminders done — ticket_emails=%d wa=%d skipped=%d",
            queued_emails, queued_wa, skipped,
        )
        return {'queued_emails': queued_emails, 'queued_wa': queued_wa, 'skipped': skipped}

    except Exception as exc:
        logger.exception("send_24h_reminders failed: %s", exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='default',
    max_retries=2,
    default_retry_delay=300,
    name='tasks.scheduled_tasks.send_3day_reminders',
    time_limit=3600,
)
def send_3day_reminders(self):
    """
    Scan for events 3 days away. Send a "your event is in 3 days, ticket coming soon" reminder.
    """
    try:
        from models import db
        from tasks.email_tasks import send_generic_email_task

        ist_now      = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
        target_str   = (ist_now + datetime.timedelta(days=3)).strftime('%Y-%m-%d')

        logger.info("send_3day_reminders: scanning for events on %s", target_str)

        events_ref   = db.collection('events').where('status', '==', 'active').stream()
        target_events = [
            {**doc.to_dict(), 'id': doc.id}
            for doc in events_ref
            if str((doc.to_dict() or {}).get('date', ''))[:10] == target_str
        ]

        if not target_events:
            logger.info("send_3day_reminders: no events in 3 days")
            return {'queued': 0}

        queued = skipped = 0

        for event in target_events:
            event_id    = event['id']
            event_title = event.get('title', 'Event')
            event_date  = event.get('date', target_str)
            venue       = event.get('venue', 'SNPSU Campus')

            regs = db.collection('registrations').where('event_id', '==', event_id).stream()

            for reg_doc in regs:
                reg    = reg_doc.to_dict()
                reg_id = reg_doc.id

                if reg.get('early_reminder_sent'):
                    skipped += 1
                    continue
                if reg.get('status', '') not in ('Confirmed', 'Paid', 'Free', ''):
                    continue
                if reg.get('is_eliminated'):
                    continue

                name  = reg.get('lead_name', 'Participant')
                email = reg.get('lead_email', '')
                if not email:
                    continue

                subject = f"Reminder: {event_title} is in 3 Days!"
                body_text = (
                    f"Hello {name},\n\n"
                    f"{event_title} is just 3 days away!\n\n"
                    f"Date: {event_date}\nVenue: {venue}\n\n"
                    f"Your entry QR ticket will arrive in your inbox 1 day before the event.\n\n"
                    f"— SapthaEvent, Sapthagiri NPS University"
                )
                body_html = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f4f7f6;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px;">
<table width="540" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:12px;border:1px solid #e2e8f0;max-width:540px;">
  <tr><td align="center" style="background:#1a2557;padding:28px 32px 24px;">
    <h2 style="margin:0;font-size:18px;color:#fff;">📅 Your Event is in 3 Days!</h2>
  </td></tr>
  <tr><td style="padding:28px 32px;">
    <p style="font-size:15px;color:#1e293b;">Hello <strong>{name}</strong>,</p>
    <p style="font-size:14px;color:#475569;">
      <strong>{event_title}</strong> is happening in just 3 days.
    </p>
    <table width="100%" style="background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;margin-bottom:24px;">
      <tr><td style="padding:14px 20px;border-bottom:1px solid #e2e8f0;">
        <span style="font-size:11px;text-transform:uppercase;color:#94a3b8;">Date</span><br>
        <strong style="color:#1a2557;">📅 {event_date}</strong>
      </td></tr>
      <tr><td style="padding:14px 20px;">
        <span style="font-size:11px;text-transform:uppercase;color:#94a3b8;">Venue</span><br>
        <strong style="color:#1a2557;">📍 {venue}</strong>
      </td></tr>
    </table>
    <p style="font-size:13px;color:#64748b;">
      Your entry QR ticket will be emailed to you <strong>1 day before the event</strong>.
    </p>
  </td></tr>
  <tr><td style="background:#f8fafc;padding:16px 32px;border-top:1px solid #e2e8f0;text-align:center;">
    <p style="margin:0;font-size:12px;color:#94a3b8;">
      SapthaEvent &middot; Sapthagiri NPS University, Bengaluru
    </p>
  </td></tr>
</table></td></tr></table>
</body></html>"""

                send_generic_email_task.delay(
                    to_email=email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                )
                queued += 1

                try:
                    db.collection('registrations').document(reg_id).update({
                        'early_reminder_sent':    True,
                        'early_reminder_sent_at': datetime.datetime.utcnow().isoformat(),
                    })
                except Exception:
                    pass

        logger.info("send_3day_reminders done — queued=%d skipped=%d", queued, skipped)
        return {'queued': queued, 'skipped': skipped}

    except Exception as exc:
        logger.exception("send_3day_reminders failed: %s", exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='default',
    max_retries=2,
    default_retry_delay=300,
    name='tasks.scheduled_tasks.check_registration_velocity',
    time_limit=3600,
)
def check_registration_velocity(self):
    """
    Velocity alert — 3 days before the registration deadline.

    For each active event whose reg_deadline is exactly 3 days from now:
      - If registration_count < 70% of max_participants (or < 10 if no cap set),
        email the SPOC with current fill-rate, a shareable registration link,
        and a prompt to broadcast to their network.
      - Marks event with `velocity_alert_sent=True` to avoid repeat sends.
    """
    try:
        from models import db
        from tasks.email_tasks import send_generic_email_task

        ist     = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        ist_now = datetime.datetime.now(ist)
        target  = (ist_now + datetime.timedelta(days=3)).strftime('%Y-%m-%d')

        logger.info("check_registration_velocity: scanning for deadlines on %s", target)

        events = db.collection('events').where('status', '==', 'active').stream()
        alerted = skipped = 0

        for doc in events:
            e      = doc.to_dict() or {}
            e_id   = doc.id

            reg_deadline = str(e.get('reg_deadline', '') or '')[:10]
            if reg_deadline != target:
                continue

            if e.get('velocity_alert_sent'):
                skipped += 1
                continue

            spoc_email = e.get('spoc_id', '')
            if not spoc_email:
                continue

            title     = e.get('title', 'Event')
            event_date = e.get('date', '')
            venue     = e.get('venue', 'SNPSU Campus')
            reg_count = int(e.get('registration_count', 0) or 0)
            max_cap   = int((e.get('limits') or {}).get('max_participants', 0) or 0)

            # Alert threshold: < 70% filled (if capped) or < 10 registrations (uncapped)
            if max_cap:
                fill_pct = reg_count / max_cap
                if fill_pct >= 0.70:
                    skipped += 1
                    continue
                fill_display = f"{reg_count} / {max_cap} ({int(fill_pct * 100)}% filled)"
            else:
                if reg_count >= 10:
                    skipped += 1
                    continue
                fill_display = f"{reg_count} registered (no capacity limit set)"

            reg_link = f"https://sapthaevent.in/forms/register/{e_id}"

            subject = f"⚡ Low registrations alert: {title} — deadline in 3 days"
            body_text = (
                f"Hello,\n\n"
                f"Your event '{title}' has its registration deadline in 3 days ({reg_deadline}), "
                f"but registrations are lower than expected.\n\n"
                f"Current registrations: {fill_display}\n"
                f"Event date: {event_date}  |  Venue: {venue}\n\n"
                f"Share this registration link with your network now:\n{reg_link}\n\n"
                f"— SapthaEvent, Sapthagiri NPS University"
            )
            body_html = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f4f7f6;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px;">
<table width="560" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:14px;border:1px solid #e2e8f0;max-width:560px;">
  <tr><td style="background:#1a2557;padding:28px 32px 22px;border-radius:14px 14px 0 0;">
    <h2 style="margin:0;font-size:18px;color:#fff;">⚡ Registration Velocity Alert</h2>
    <p style="margin:6px 0 0;font-size:13px;color:rgba(255,255,255,.7);">Deadline in 3 days</p>
  </td></tr>
  <tr><td style="padding:28px 32px;">
    <p style="font-size:15px;color:#1e293b;">Hello,</p>
    <p style="font-size:14px;color:#475569;line-height:1.6;">
      Your event <strong style="color:#1a2557;">{title}</strong> has its registration deadline
      on <strong>{reg_deadline}</strong>, but registrations are below the expected threshold.
    </p>
    <table width="100%" style="background:#fff8f0;border-radius:10px;border:1px solid #fde68a;
           margin:20px 0;border-left:4px solid #c9a45e;">
      <tr><td style="padding:16px 20px;">
        <span style="font-size:11px;text-transform:uppercase;color:#94a3b8;font-weight:700;letter-spacing:.5px;">
          Current Fill Rate
        </span><br>
        <strong style="font-size:18px;color:#1a2557;">{fill_display}</strong>
      </td></tr>
    </table>
    <table width="100%" style="background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;margin-bottom:24px;">
      <tr><td style="padding:12px 20px;border-bottom:1px solid #e2e8f0;">
        <span style="font-size:11px;text-transform:uppercase;color:#94a3b8;">Reg Deadline</span><br>
        <strong style="color:#1a2557;">📅 {reg_deadline}</strong>
      </td></tr>
      <tr><td style="padding:12px 20px;border-bottom:1px solid #e2e8f0;">
        <span style="font-size:11px;text-transform:uppercase;color:#94a3b8;">Event Date</span><br>
        <strong style="color:#1a2557;">🗓 {event_date}</strong>
      </td></tr>
      <tr><td style="padding:12px 20px;">
        <span style="font-size:11px;text-transform:uppercase;color:#94a3b8;">Venue</span><br>
        <strong style="color:#1a2557;">📍 {venue}</strong>
      </td></tr>
    </table>
    <p style="font-size:14px;color:#1e293b;font-weight:600;margin-bottom:8px;">
      Share this registration link now:
    </p>
    <table width="100%" style="background:#f1f5f9;border-radius:10px;margin-bottom:20px;">
      <tr><td style="padding:14px 18px;font-family:monospace;font-size:13px;
              color:#1a2557;word-break:break-all;">
        {reg_link}
      </td></tr>
    </table>
    <table><tr><td>
      <a href="{reg_link}"
         style="display:inline-block;padding:12px 28px;background:#c9a45e;color:#fff;
                font-weight:700;font-size:14px;border-radius:10px;text-decoration:none;">
        View Event Page →
      </a>
    </td></tr></table>
    <p style="font-size:12px;color:#94a3b8;margin-top:20px;line-height:1.5;">
      Share on WhatsApp, post on your college notice board, or forward to your department
      to drive last-minute registrations before the deadline closes.
    </p>
  </td></tr>
  <tr><td style="background:#f8fafc;padding:16px 32px;border-top:1px solid #e2e8f0;
          text-align:center;border-radius:0 0 14px 14px;">
    <p style="margin:0;font-size:12px;color:#94a3b8;">
      SapthaEvent &middot; Sapthagiri NPS University, Bengaluru
    </p>
  </td></tr>
</table></td></tr></table>
</body></html>"""

            send_generic_email_task.delay(
                to_email=spoc_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
            )
            alerted += 1

            try:
                db.collection('events').document(e_id).update({
                    'velocity_alert_sent':    True,
                    'velocity_alert_sent_at': ist_now.isoformat(),
                })
            except Exception:
                pass

        logger.info("check_registration_velocity done — alerted=%d skipped=%d", alerted, skipped)
        return {'alerted': alerted, 'skipped': skipped}

    except Exception as exc:
        logger.exception("check_registration_velocity failed: %s", exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='default',
    max_retries=2,
    default_retry_delay=600,
    name='tasks.scheduled_tasks.run_event_lifecycle',
    time_limit=3600,
)
def run_event_lifecycle(self):
    """
    1. Close registrations once reg_deadline has passed (status → registration_closed)
    2. Delete registrations 30 days after event date
    3. Delete event document 5 days after event date
    """
    try:
        from models import db

        ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        today = datetime.datetime.now(ist).date()

        def _parse_date(s):
            s = str(s or '').strip()[:10]
            try:
                return datetime.datetime.strptime(s, '%Y-%m-%d').date()
            except ValueError:
                return None

        events = list(db.collection('events').stream())
        closed = deleted_events = deleted_regs = 0

        for doc in events:
            e      = doc.to_dict() or {}
            e_id   = doc.id
            status = (e.get('status', '') or '').lower()
            event_date = _parse_date(e.get('date'))
            reg_dl     = _parse_date(e.get('reg_deadline'))

            if reg_dl and today > reg_dl and status == 'active':
                try:
                    db.collection('events').document(e_id).update({
                        'status': 'registration_closed',
                        'registration_closed_at': datetime.datetime.now(ist).isoformat(),
                    })
                    closed += 1
                except Exception as exc:
                    logger.warning("Could not close reg for %s: %s", e_id, exc)

            if event_date and (today - event_date).days >= 30:
                try:
                    for r in db.collection('registrations').where('event_id', '==', e_id).stream():
                        r.reference.delete()
                        deleted_regs += 1
                except Exception as exc:
                    logger.warning("Reg cleanup failed %s: %s", e_id, exc)

            if event_date and (today - event_date).days >= 5:
                try:
                    for r in db.collection('registrations').where('event_id', '==', e_id).stream():
                        r.reference.delete()
                        deleted_regs += 1
                    db.collection('events').document(e_id).delete()
                    deleted_events += 1
                except Exception as exc:
                    logger.warning("Event cleanup failed %s: %s", e_id, exc)

        logger.info("run_event_lifecycle: closed=%d events_deleted=%d regs_deleted=%d",
                    closed, deleted_events, deleted_regs)
        return {'closed': closed, 'events_deleted': deleted_events, 'regs_deleted': deleted_regs}

    except Exception as exc:
        logger.exception("run_event_lifecycle failed: %s", exc)
        raise self.retry(exc=exc)


@celery.task(
    queue='default',
    name='tasks.scheduled_tasks.log_backup_ping',
)
def log_backup_ping():
    """
    Daily reminder logged to stdout that operators should verify
    the automated Firestore GCS backup completed successfully.
    """
    import os
    bucket = os.environ.get('GCS_BUCKET_NAME', '<GCS_BUCKET_NAME not set>')
    logger.info(
        "BACKUP CHECK: verify today's Firestore export landed in gs://%s/backups/",
        bucket,
    )
