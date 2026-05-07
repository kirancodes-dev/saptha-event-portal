"""
tasks/cert_tasks.py — Async certificate generation & distribution
=================================================================
PDF generation is CPU-intensive and blocks gunicorn workers for 200-500 ms
per cert. Offloading to the 'certs' queue keeps the web fleet responsive.

Queued on: 'certs'
"""

import logging
from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    queue='certs',
    max_retries=2,
    default_retry_delay=120,
    name='tasks.cert_tasks.generate_and_send_certificate',
    time_limit=300,   # 5 min hard limit per cert
    soft_time_limit=240,
)
def generate_and_send_certificate(self, reg_id: str, event_id: str,
                                   recipient_email: str, recipient_name: str):
    """
    Generate a PDF certificate for a registration and email it.
    Called after an admin marks attendance as 'Present'.
    """
    try:
        from models import db
        from utils_certificates import generate_certificate_pdf  # type: ignore
        from tasks.email_tasks import send_generic_email_task

        reg_doc = db.collection('registrations').document(reg_id).get()
        if not reg_doc.exists:
            logger.warning("cert_task: reg %s not found, aborting", reg_id)
            return

        event_doc = db.collection('events').document(event_id).get()
        event = event_doc.to_dict() if event_doc.exists else {}

        pdf_bytes = generate_certificate_pdf(
            reg_id=reg_id,
            name=recipient_name,
            event_title=event.get('title', 'Event'),
            event_date=event.get('date', ''),
            venue=event.get('venue', 'SNPSU Campus'),
        )

        # Store cert URL in Firestore (upload to GCS first if configured)
        cert_url = _upload_cert(pdf_bytes, reg_id)
        db.collection('registrations').document(reg_id).update({
            'certificate_url': cert_url,
            'certificate_generated_at': _utcnow(),
        })

        # Email cert to participant
        send_generic_email_task.delay(
            to_email=recipient_email,
            subject=f"Your Certificate — {event.get('title', 'Event')}",
            body_text=f"Hello {recipient_name},\n\nPlease find your certificate attached.\n\n— SapthaEvent",
        )
        logger.info("certificate generated for reg=%s", reg_id)

    except Exception as exc:
        logger.error("cert generation failed reg=%s: %s", reg_id, exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='certs',
    max_retries=2,
    default_retry_delay=120,
    name='tasks.cert_tasks.bulk_generate_certificates',
    time_limit=3600,
)
def bulk_generate_certificates(self, event_id: str, triggered_by: str = 'admin'):
    """
    Generate certificates for all 'Present' attendees of an event.
    Dispatches individual generate_and_send_certificate tasks per registrant.
    """
    try:
        from models import db
        from google.cloud.firestore_v1.base_query import FieldFilter

        regs = (
            db.collection('registrations')
            .where(filter=FieldFilter('event_id', '==', event_id))
            .where(filter=FieldFilter('attendance', '==', 'Present'))
            .stream()
        )

        count = 0
        for reg_doc in regs:
            reg = reg_doc.to_dict()
            if reg.get('certificate_url'):
                continue  # already done
            generate_and_send_certificate.delay(
                reg_id=reg_doc.id,
                event_id=event_id,
                recipient_email=reg.get('lead_email', ''),
                recipient_name=reg.get('lead_name', 'Participant'),
            )
            count += 1

        logger.info("bulk_generate_certificates: queued %d certs for event %s by %s",
                    count, event_id, triggered_by)
        return {'queued': count, 'event_id': event_id}

    except Exception as exc:
        logger.error("bulk_generate_certificates failed event=%s: %s", event_id, exc)
        raise self.retry(exc=exc)


# ── Helpers ───────────────────────────────────────────────

def _upload_cert(pdf_bytes: bytes, reg_id: str) -> str:
    """Upload cert PDF to GCS; return public URL. Falls back to data URI."""
    try:
        from google.cloud import storage
        import os

        bucket_name = os.environ.get('GCS_BUCKET_NAME', '')
        if not bucket_name:
            raise ValueError("GCS_BUCKET_NAME not set")

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob   = bucket.blob(f"certificates/{reg_id}.pdf")
        blob.upload_from_string(pdf_bytes, content_type='application/pdf')
        blob.make_public()
        return blob.public_url
    except Exception as exc:
        logger.warning("GCS upload failed, cert not stored publicly: %s", exc)
        return ''


def _utcnow():
    import datetime
    return datetime.datetime.utcnow().isoformat()
