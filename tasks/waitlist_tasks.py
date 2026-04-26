"""
tasks/waitlist_tasks.py — Waitlist promotion when a seat opens up
"""
import logging
import datetime
import time

from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    queue='email',
    max_retries=3,
    default_retry_delay=30,
    name='tasks.waitlist_tasks.promote_from_waitlist',
)
def promote_from_waitlist(self, event_id: str):
    """
    Promote the next person on the waitlist for an event.
    Called after a cancellation frees a seat.
    """
    try:
        from models import db
        from google.cloud.firestore_v1.base_query import FieldFilter
        from tasks.email_tasks import send_generic_email_task

        # Find the oldest waiting entry for this event
        entries = list(
            db.collection('waitlist')
              .where(filter=FieldFilter('event_id', '==', event_id))
              .where(filter=FieldFilter('status', '==', 'waiting'))
              .order_by('joined_at')
              .limit(1)
              .stream()
        )
        if not entries:
            logger.info("promote_from_waitlist: no waitlist entries for %s", event_id)
            return {'promoted': False}

        entry_doc  = entries[0]
        entry      = entry_doc.to_dict()
        entry_id   = entry_doc.id
        email      = entry.get('email', '')
        name       = entry.get('name', 'Participant')
        event_title = entry.get('event_title', 'Event')
        reg_data   = entry.get('reg_data', {})

        # Check if they already registered somehow
        existing = list(
            db.collection('registrations')
              .where(filter=FieldFilter('event_id', '==', event_id))
              .where(filter=FieldFilter('lead_email', '==', email))
              .limit(1).stream()
        )
        if existing:
            db.collection('waitlist').document(entry_id).update({'status': 'already_registered'})
            promote_from_waitlist.apply_async(args=[event_id])
            return {'promoted': False, 'reason': 'already_registered'}

        # Create registration
        reg_id = reg_data.get('reg_id') or f"REG-{int(time.time() * 1000)}"
        reg_data.update({
            'reg_id': reg_id,
            'status': 'Confirmed',
            'payment_status': entry.get('payment_status', 'Free'),
            'amount_paid': entry.get('amount_paid', 0),
            'is_eliminated': False,
            'current_round': 1,
            'from_waitlist': True,
        })
        db.collection('registrations').document(reg_id).set(reg_data)

        event_ref = db.collection('events').document(event_id)
        event_doc = event_ref.get().to_dict() or {}
        event_ref.update({'registration_count': event_doc.get('registration_count', 0) + 1})

        # Mark waitlist entry as promoted
        db.collection('waitlist').document(entry_id).update({
            'status': 'promoted',
            'promoted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'reg_id': reg_id,
        })

        # Send email notification
        event_date = event_doc.get('date', '')
        venue      = event_doc.get('venue', 'SNPSU Campus')
        send_generic_email_task.delay(
            to_email=email,
            subject=f"Great news! Your waitlist spot for {event_title} is confirmed",
            body=(
                f"Hi {name},\n\n"
                f"A seat has opened up and you've been promoted from the waitlist for "
                f"{event_title}!\n\n"
                f"Your registration is now confirmed.\n"
                f"Registration ID: {reg_id}\n"
                f"Event Date: {event_date}\n"
                f"Venue: {venue}\n\n"
                f"See you there!\n— SapthaEvent Team"
            ),
        )

        logger.info("promote_from_waitlist: promoted %s to %s for event %s", email, reg_id, event_id)
        return {'promoted': True, 'reg_id': reg_id, 'email': email}

    except Exception as exc:
        logger.exception("promote_from_waitlist failed event=%s: %s", event_id, exc)
        raise self.retry(exc=exc)
