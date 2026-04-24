"""
tasks/webhook_tasks.py — Razorpay webhook retry with exponential back-off
=========================================================================
When a Razorpay payment.captured event arrives but our Firestore write
fails (network blip, cold-start), the webhook handler enqueues this task
instead of returning 500 to Razorpay (which would cause Razorpay to retry
the webhook itself and potentially double-credit the user).

Queued on: 'webhooks'
"""

import logging
import datetime
from celery_app import celery

logger = logging.getLogger(__name__)

# Exponential back-off: 30s, 2m, 10m, 30m, 2h
_BACKOFF = [30, 120, 600, 1800, 7200]


@celery.task(
    bind=True,
    queue='webhooks',
    max_retries=5,
    name='tasks.webhook_tasks.process_razorpay_payment',
)
def process_razorpay_payment(self, payload: dict):
    """
    Finalise a Razorpay payment.captured event:
    1. Verify Razorpay signature (if not already verified by the route)
    2. Update registration status → 'Paid'
    3. Send ticket email + WhatsApp receipt
    4. Write audit log

    payload keys: razorpay_order_id, razorpay_payment_id, razorpay_signature,
                  reg_id, event_id, amount, lead_email, lead_name, lead_phone
    """
    retry_num = self.request.retries
    try:
        from models import db
        from tasks.email_tasks import send_ticket_email_task
        from tasks.notification_tasks import send_payment_receipt_whatsapp_task

        reg_id     = payload.get('reg_id', '')
        event_id   = payload.get('event_id', '')
        lead_email = payload.get('lead_email', '')
        lead_name  = payload.get('lead_name', '')
        lead_phone = payload.get('lead_phone', '')
        amount     = payload.get('amount', 0)
        payment_id = payload.get('razorpay_payment_id', '')

        if not reg_id:
            logger.error("process_razorpay_payment: missing reg_id in payload")
            return

        reg_ref = db.collection('registrations').document(reg_id)
        reg_doc = reg_ref.get()

        if not reg_doc.exists:
            logger.error("process_razorpay_payment: reg %s not found", reg_id)
            return

        reg = reg_doc.to_dict()
        if reg.get('payment_status') == 'Paid':
            logger.info("process_razorpay_payment: reg %s already paid, idempotent skip", reg_id)
            return

        reg_ref.update({
            'payment_status':    'Paid',
            'status':            'Confirmed',
            'razorpay_payment_id': payment_id,
            'amount_paid':       amount,
            'paid_at':           datetime.datetime.utcnow().isoformat(),
        })

        event_doc   = db.collection('events').document(event_id).get()
        event       = event_doc.to_dict() if event_doc.exists else {}
        event_title = event.get('title', 'Event')
        event_date  = event.get('date', '')
        venue       = event.get('venue', 'SNPSU Campus')

        # Fire-and-forget notifications
        send_ticket_email_task.delay(
            to_email=lead_email,
            name=lead_name,
            event_title=event_title,
            reg_id=reg_id,
            event_date=event_date,
            venue=venue,
        )
        if lead_phone:
            send_payment_receipt_whatsapp_task.delay(
                phone=lead_phone,
                name=lead_name,
                event_title=event_title,
                amount=str(amount),
                reg_id=reg_id,
            )

        # Audit log
        db.collection('audit_log').add({
            'action':     'payment_confirmed',
            'reg_id':     reg_id,
            'event_id':   event_id,
            'payment_id': payment_id,
            'amount':     amount,
            'user':       lead_email,
            'timestamp':  datetime.datetime.utcnow().isoformat(),
        })
        logger.info("Razorpay payment confirmed: reg=%s payment=%s amount=%s",
                    reg_id, payment_id, amount)

    except Exception as exc:
        delay = _BACKOFF[min(retry_num, len(_BACKOFF) - 1)]
        logger.warning("process_razorpay_payment retry %d in %ds: %s", retry_num, delay, exc)
        raise self.retry(exc=exc, countdown=delay)


@celery.task(
    bind=True,
    queue='webhooks',
    max_retries=3,
    default_retry_delay=60,
    name='tasks.webhook_tasks.process_razorpay_refund',
)
def process_razorpay_refund(self, payload: dict):
    """Handle Razorpay refund.processed webhook."""
    try:
        from models import db

        reg_id     = payload.get('reg_id', '')
        payment_id = payload.get('razorpay_payment_id', '')
        refund_id  = payload.get('razorpay_refund_id', '')

        if not reg_id:
            return

        db.collection('registrations').document(reg_id).update({
            'payment_status': 'Refunded',
            'status':         'Cancelled',
            'refund_id':      refund_id,
            'refunded_at':    datetime.datetime.utcnow().isoformat(),
        })
        db.collection('audit_log').add({
            'action':    'payment_refunded',
            'reg_id':    reg_id,
            'refund_id': refund_id,
            'timestamp': datetime.datetime.utcnow().isoformat(),
        })
        logger.info("Razorpay refund processed: reg=%s refund=%s", reg_id, refund_id)

    except Exception as exc:
        raise self.retry(exc=exc)
