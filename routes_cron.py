"""
routes_cron.py — scheduled jobs called by an outside scheduler (UPG-07)

A single web service (Cloud Run) has no Celery beat, so Cloud Scheduler or
the GitHub Actions workflow in .github/workflows/cron.yml calls
POST /internal/cron/<job> with the shared secret in the X-Cron-Secret header
(docs/DEPLOY.md). Every job can safely run again: reminders skip
registrations already reminded (`ticket_sent`, `early_reminder_sent`), the
lifecycle only moves events forward, and the clean-up deletes only expired
rows.
"""
import hmac
import logging
import os

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

cron_bp = Blueprint('cron', __name__, url_prefix='/internal/cron')
HEADER = 'X-Cron-Secret'


def _reminders():
    from tasks.scheduled_tasks import send_24h_reminders, send_3day_reminders
    return {'day_before': send_24h_reminders(), 'three_days': send_3day_reminders()}


def _lifecycle():
    from tasks.scheduled_tasks import run_event_lifecycle
    return run_event_lifecycle()


def _cleanup():
    """Expired sessions (BLK-08) and login attempts older than the throttle window (BLK-13)."""
    from services_login_throttle import purge_expired
    from session_store import purge_expired_sessions
    return {'sessions': purge_expired_sessions(), 'login_attempts': purge_expired()}


JOBS = {'reminders': _reminders, 'lifecycle': _lifecycle, 'cleanup': _cleanup}


@cron_bp.route('/<job>', methods=['POST'])
def run_job(job):
    secret = os.environ.get('CRON_SECRET', '')
    if not secret:
        return jsonify({'error': 'Scheduled jobs are off: CRON_SECRET is not set.'}), 503
    given = request.headers.get(HEADER, '')
    if not hmac.compare_digest(given.encode(), secret.encode()):
        return jsonify({'error': 'forbidden'}), 403
    if job not in JOBS:
        return jsonify({'error': f'Unknown job. Jobs: {", ".join(sorted(JOBS))}.'}), 404
    try:
        result = JOBS[job]()
    except Exception:
        logger.exception("Cron job %s failed", job)
        return jsonify({'job': job, 'status': 'failed'}), 500
    logger.info("Cron job %s: %s", job, result)
    return jsonify({'job': job, 'status': 'ok', 'result': result})
