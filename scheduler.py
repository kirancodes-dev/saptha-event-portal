"""
scheduler.py — Legacy shim (dev-only fallback)
===============================================
In production, ALL scheduled jobs run in the celery-beat container
via tasks/scheduled_tasks.py. APScheduler is no longer embedded in
the web workers (doing so would run each job N times across N workers).

This module is kept only so local `python app.py` dev runs still get
reminder + lifecycle jobs without requiring a full Celery stack.

Production containers set NO_SCHEDULER=true and this module is never
called.
"""

import os
import logging

logger = logging.getLogger(__name__)

_scheduler = None


def init_scheduler(flask_app):
    """
    Start a local APScheduler only when:
      - NO_SCHEDULER env var is not set, AND
      - CELERY_BROKER_URL is not configured (no Celery available)

    In Docker Compose / Railway, celery-beat owns all scheduling.
    """
    if os.environ.get('NO_SCHEDULER', '').lower() in ('1', 'true', 'yes'):
        logger.info("Scheduler: disabled (NO_SCHEDULER=true) — Celery Beat handles jobs")
        return None

    if os.environ.get('CELERY_BROKER_URL', '').startswith('redis'):
        logger.info("Scheduler: disabled — Celery Beat is configured, skipping APScheduler")
        return None

    # Dev-only: run jobs locally via APScheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from tasks.scheduled_tasks import (send_24h_reminders, send_3day_reminders,
                                           run_event_lifecycle, check_registration_velocity)

        global _scheduler
        _scheduler = BackgroundScheduler(timezone='Asia/Kolkata')

        _scheduler.add_job(
            func=lambda: _run_in_context(flask_app, send_24h_reminders),
            trigger=IntervalTrigger(hours=1),
            id='dev_24h_reminders',
            replace_existing=True,
            misfire_grace_time=600,
        )
        _scheduler.add_job(
            func=lambda: _run_in_context(flask_app, send_3day_reminders),
            trigger=IntervalTrigger(hours=1),
            id='dev_3day_reminders',
            replace_existing=True,
            misfire_grace_time=600,
        )
        _scheduler.add_job(
            func=lambda: _run_in_context(flask_app, run_event_lifecycle),
            trigger=IntervalTrigger(hours=6),
            id='dev_lifecycle',
            replace_existing=True,
            misfire_grace_time=600,
        )
        _scheduler.add_job(
            func=lambda: _run_in_context(flask_app, check_registration_velocity),
            trigger=IntervalTrigger(hours=24),
            id='dev_velocity_alert',
            replace_existing=True,
            misfire_grace_time=600,
        )

        _scheduler.start()
        logger.info("Dev scheduler started (APScheduler) — use Celery Beat in production")
        return _scheduler

    except ImportError:
        logger.warning("APScheduler not available — no scheduled jobs in dev mode")
        return None
    except Exception as exc:
        logger.warning("Dev scheduler failed to start: %s", exc)
        return None


def _run_in_context(flask_app, task_fn):
    """Run a Celery task function synchronously inside Flask app context."""
    with flask_app.app_context():
        try:
            task_fn()
        except Exception as exc:
            logger.exception("Dev scheduler job failed: %s", exc)
