"""
celery_app.py — Celery factory for SapthaEvent
===============================================
Creates the Celery instance and binds it to the Flask app context so
every task can safely call db, mail, current_app, etc.

Usage
-----
  # In tasks/*.py:
  from celery_app import celery

  @celery.task(bind=True, max_retries=3)
  def my_task(self, ...):
      ...

  # Start worker:
  celery -A celery_app.celery worker --loglevel=info -Q default,email,certs

  # Start Beat scheduler (separate container):
  celery -A celery_app.celery beat --loglevel=info \
         --scheduler celery.beat.PersistentScheduler \
         --schedule /tmp/celerybeat-schedule
"""

import os
from celery import Celery
from celery.schedules import crontab

# ── Broker / backend ──────────────────────────────────────
BROKER_URL  = os.environ.get('CELERY_BROKER_URL',  'redis://localhost:6379/1')
RESULT_URL  = os.environ.get('CELERY_RESULT_BACKEND', BROKER_URL)

celery = Celery(
    'sapthaevent',
    broker=BROKER_URL,
    backend=RESULT_URL,
    include=[
        'tasks.email_tasks',
        'tasks.notification_tasks',
        'tasks.cert_tasks',
        'tasks.export_tasks',
        'tasks.webhook_tasks',
        'tasks.analytics_tasks',
        'tasks.scheduled_tasks',
        'tasks.waitlist_tasks',
    ],
)

# Eager mode when CELERY_BROKER_URL is not explicitly set in the environment.
# This lets localhost run the full workflow (email, WhatsApp, etc.) without Redis.
_no_broker = not os.environ.get('CELERY_BROKER_URL', '').startswith('redis')

celery.conf.update(
    # ── Eager mode — runs tasks inline when no Redis broker is available.
    # This lets the full email/WhatsApp/notification workflow work on
    # localhost without needing a running Redis + Celery worker.
    # Set CELERY_BROKER_URL=redis://... in production to disable eager mode.
    task_always_eager        = _no_broker,
    task_eager_propagates    = False,  # email failures must NOT crash web requests

    # ── Serialisation ─────────────────────────────────────
    task_serializer          = 'json',
    result_serializer        = 'json',
    accept_content           = ['json'],
    result_expires           = 3600,          # results kept 1 h

    # ── Routing — explicit queues per workload ─────────────
    task_routes = {
        'tasks.email_tasks.*':        {'queue': 'email'},
        'tasks.notification_tasks.*': {'queue': 'email'},
        'tasks.cert_tasks.*':         {'queue': 'certs'},
        'tasks.export_tasks.*':       {'queue': 'exports'},
        'tasks.webhook_tasks.*':      {'queue': 'webhooks'},
        'tasks.analytics_tasks.*':    {'queue': 'default'},
        'tasks.scheduled_tasks.*':    {'queue': 'default'},
    },

    # ── Worker behaviour ──────────────────────────────────
    worker_prefetch_multiplier   = 1,     # fair dispatch for long tasks
    task_acks_late               = True,  # ack only after success
    task_reject_on_worker_lost   = True,  # re-queue if worker crashes

    # ── Retry defaults (tasks override per-task) ──────────
    task_default_retry_delay     = 60,    # 60 s between retries
    task_max_retries             = 3,

    # ── Timezone ──────────────────────────────────────────
    timezone                     = 'Asia/Kolkata',
    enable_utc                   = True,

    # ── Beat schedule (runs in the celery-beat container) ─
    beat_schedule = {
        # 24-hour ticket email (entry QR) — run every hour
        'event-24h-reminders': {
            'task':     'tasks.scheduled_tasks.send_24h_reminders',
            'schedule': crontab(minute=0),           # top of every hour
        },
        # 3-day early reminder — run every hour
        'event-3day-reminders': {
            'task':     'tasks.scheduled_tasks.send_3day_reminders',
            'schedule': crontab(minute=30),          # 30 min past every hour
        },
        # Event lifecycle (close regs, delete old events)
        'event-lifecycle': {
            'task':     'tasks.scheduled_tasks.run_event_lifecycle',
            'schedule': crontab(minute=0, hour='*/6'),  # every 6 hours
        },
        # Velocity alert — 3 days before registration deadline
        'registration-velocity-alert': {
            'task':     'tasks.scheduled_tasks.check_registration_velocity',
            'schedule': crontab(minute=45, hour=9),  # 09:45 IST daily
        },
        # Daily analytics rollup — midnight IST
        'daily-analytics': {
            'task':     'tasks.analytics_tasks.daily_rollup',
            'schedule': crontab(minute=0, hour=0),
        },
        # Daily Firestore backup reminder log (actual backup via GCS)
        'daily-backup-ping': {
            'task':     'tasks.scheduled_tasks.log_backup_ping',
            'schedule': crontab(minute=30, hour=1),
        },
    },
)


def init_celery(app):
    """
    Bind a Flask app to the celery instance so tasks run inside the
    app context. Call once from the Flask app factory.

        from celery_app import celery, init_celery
        init_celery(app)
    """
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    celery.conf.update(
        broker=app.config.get('CELERY_BROKER_URL', BROKER_URL),
        backend=app.config.get('CELERY_RESULT_BACKEND', RESULT_URL),
    )
    return celery
