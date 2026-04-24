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
    """Fire-and-forget WhatsApp 24-hour reminder."""
    try:
        from utils_whatsapp import send_event_reminder_whatsapp
        send_event_reminder_whatsapp(
            phone=phone,
            name=name,
            event_title=event_title,
            event_date=event_date,
            venue=venue,
            reg_id=reg_id,
        )
        logger.info("WhatsApp reminder sent to %s for %s", phone, event_title)
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
                                        reg_id: str):
    """WhatsApp payment receipt after Razorpay success."""
    try:
        from utils_whatsapp import send_payment_receipt_whatsapp
        send_payment_receipt_whatsapp(
            phone=phone,
            name=name,
            event_title=event_title,
            amount=amount,
            reg_id=reg_id,
        )
        logger.info("WhatsApp payment receipt sent to %s", phone)
    except Exception as exc:
        logger.warning("WhatsApp receipt failed %s: %s", phone, exc)
        raise self.retry(exc=exc)
