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
        from tasks.email_tasks import send_reminder_email_task
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

                if reg.get('reminder_sent'):
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

                if email:
                    send_reminder_email_task.delay(
                        to_email=email,
                        name=name,
                        event_title=event_title,
                        event_date=event_date,
                        venue=venue,
                        reg_id=reg_id,
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

                # Mark reminder queued (not yet sent — task handles confirmation)
                try:
                    db.collection('registrations').document(reg_id).update({
                        'reminder_sent':    True,
                        'reminder_sent_at': datetime.datetime.utcnow().isoformat(),
                    })
                except Exception:
                    pass

        logger.info(
            "send_24h_reminders done — emails_queued=%d wa_queued=%d skipped=%d",
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
