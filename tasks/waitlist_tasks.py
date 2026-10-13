"""
tasks/waitlist_tasks.py — Waitlist promotion when a seat opens up
"""
import logging

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
        try:
            import app as app_module
            db = getattr(app_module, 'db', None)
            if db is None:
                from models import db
        except Exception:
            from models import db

        from routes_waitlist import auto_promote
        res = auto_promote(db, event_id)
        if res:
            return {'promoted': True, 'email': res.get('user_email', ''), 'reg_id': res.get('reg_id', '')}
        return {'promoted': False}
    except Exception as exc:
        logger.exception("promote_from_waitlist failed event=%s: %s", event_id, exc)
        raise self.retry(exc=exc)

