"""
tasks/notification_tasks.py — Async WhatsApp / SMS notifications
=================================================================
Wraps Twilio sends in Celery tasks so the web workers never block
waiting for the Twilio API.

Queued on: 'email'  (shared with email — both are low-throughput I/O)
"""

import logging
from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    queue='email',
    max_retries=3,
    default_retry_delay=30,
    name='tasks.notification_tasks.send_ticket_whatsapp_task',
)
def send_ticket_whatsapp_task(self, phone: str, name: str, event_title: str,
                               reg_id: str, event_date: str = '', venue: str = ''):
    """Fire-and-forget WhatsApp ticket confirmation."""
    try:
        from utils_whatsapp import send_ticket_whatsapp
        send_ticket_whatsapp(
            phone=phone,
            name=name,
            event_title=event_title,
            reg_id=reg_id,
            event_date=event_date,
            venue=venue,
        )
        logger.info("WhatsApp ticket sent to %s", phone)
    except Exception as exc:
        logger.warning("WhatsApp ticket failed %s: %s", phone, exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='email',
    max_retries=3,
    default_retry_delay=60,
    name='tasks.notification_tasks.send_reminder_whatsapp_task',
)
def send_reminder_whatsapp_task(self, phone: str, name: str, event_title: str,
                                 event_date: str, venue: str, reg_id: str):
    """The day-before reminder on WhatsApp, once per registration and date, to an
    opted-in number under the cap (UPG-147): Meta's API takes only approved
    templates for messages we start, so there it's the template; on Twilio the
    reminder text, through the same gate."""
    try:
        from models import db
        import services_whatsapp as wa
        from utils_email import _base_url
        if wa.provider() == 'meta':
            result = wa.notify(db, 'event_reminder', phone, {
                'name': name, 'event': event_title, 'date': event_date, 'venue': venue,
                'ticket_link': f"{_base_url().rstrip('/')}/ticket/{reg_id}"}, key=f"{reg_id}:{event_date}")
        elif not wa.claim_once(db, 'event_reminder', f"{reg_id}:{event_date}", phone):
            result = 'already'
        else:
            from utils_whatsapp import send_event_reminder_whatsapp
            result = send_event_reminder_whatsapp(phone=phone, name=name, event_title=event_title,
                                                  event_date=event_date, venue=venue, reg_id=reg_id)
            if not result and wa.gate(phone, db) is None:     # the provider failed: give the claim back, retry
                wa.release(db, 'event_reminder', f"{reg_id}:{event_date}", phone)
                raise RuntimeError("WhatsApp reminder not accepted by the provider")
        logger.info("WhatsApp reminder for %s: %s", event_title, result)
    except Exception as exc:
        logger.warning("WhatsApp reminder failed %s: %s", phone, exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='email',
    max_retries=3,
    default_retry_delay=30,
    name='tasks.notification_tasks.send_payment_receipt_whatsapp_task',
)
def send_payment_receipt_whatsapp_task(self, phone: str, name: str,
                                        event_title: str, amount: str,
                                        reg_id: str = '', payment_id: str = ''):
    """WhatsApp payment receipt after Razorpay success (shows the payment ID,
    else the registration ID)."""
    try:
        from utils_whatsapp import send_payment_receipt_whatsapp
        send_payment_receipt_whatsapp(
            phone=phone,
            name=name,
            event_title=event_title,
            amount=amount,
            payment_id=payment_id or reg_id,
        )
        logger.info("WhatsApp payment receipt sent to %s", phone)
    except Exception as exc:
        logger.warning("WhatsApp receipt failed %s: %s", phone, exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='email',
    max_retries=3,
    default_retry_delay=300,
    name='tasks.notification_tasks.send_whatsapp_template',
)
def send_whatsapp_template(self, log_id: str, number: str, template: str, values: dict):
    """One template message, sent once (UPG-147); a failure is retried by the outbox."""
    from services_whatsapp import deliver
    try:
        deliver(log_id, number, template, values)
    except Exception as exc:
        logger.warning("WhatsApp template %s not sent: %s", template, exc)
        raise self.retry(exc=exc)
