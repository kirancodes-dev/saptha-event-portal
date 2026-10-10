"""
tasks/cert_tasks.py — Async certificate generation & distribution
=================================================================
PDF generation is CPU-intensive and blocks gunicorn workers for 200-500 ms
per cert. Offloading to the 'certs' queue keeps the web fleet responsive.
Without a broker the task runs inline (celery_app).

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
    name='tasks.cert_tasks.bulk_generate_certificates',
    time_limit=3600,
)
def bulk_generate_certificates(self, event_id: str, triggered_by: str = 'admin'):
    """
    Issue the certificates of every 'Present' attendee of an event, through
    the one issuing path (utils_certificate.issue_event_certificates, UPG-06).
    A retry issues only what's still missing.
    """
    try:
        from utils_certificate import issue_event_certificates
        results = issue_event_certificates(event_id)
        logger.info("bulk_generate_certificates for event %s by %s: %s", event_id, triggered_by, results)
        return dict(results, event_id=event_id)
    except ValueError as exc:  # no such event: nothing to retry
        logger.warning("bulk_generate_certificates: %s", exc)
        return {'event_id': event_id, 'error': str(exc)}
    except Exception as exc:
        logger.error("bulk_generate_certificates failed event=%s: %s", event_id, exc)
        raise self.retry(exc=exc)
