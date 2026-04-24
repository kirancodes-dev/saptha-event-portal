"""
tasks/analytics_tasks.py — Daily analytics rollup
===================================================
Aggregates event/registration metrics into a 'analytics_daily' Firestore
collection so dashboards can read pre-computed numbers instead of doing
expensive full-collection scans at render time.

Queued on: 'default'
Schedule:  daily at midnight IST (via Celery Beat in celery_app.py)
"""

import logging
import datetime
from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    queue='default',
    max_retries=2,
    default_retry_delay=300,
    name='tasks.analytics_tasks.daily_rollup',
    time_limit=600,
)
def daily_rollup(self):
    """
    Snapshot key metrics into analytics_daily/{YYYY-MM-DD}:
      - total_events, active_events
      - total_registrations, confirmed_registrations, paid_registrations
      - total_users, new_users_today
      - total_revenue
    """
    try:
        from models import db

        ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        today_str = datetime.datetime.now(ist).strftime('%Y-%m-%d')

        events = list(db.collection('events').stream())
        regs   = list(db.collection('registrations').stream())
        users  = list(db.collection('users').stream())

        total_events        = len(events)
        active_events       = sum(1 for e in events if (e.to_dict() or {}).get('status') == 'active')
        total_regs          = len(regs)
        confirmed_regs      = 0
        paid_regs           = 0
        total_revenue       = 0.0
        new_users_today     = 0

        for r in regs:
            d = r.to_dict() or {}
            if d.get('status') == 'Confirmed':
                confirmed_regs += 1
            if d.get('payment_status') == 'Paid':
                paid_regs    += 1
                total_revenue += float(d.get('amount_paid', 0) or 0)

        for u in users:
            d = u.to_dict() or {}
            created = str(d.get('created_at', ''))[:10]
            if created == today_str:
                new_users_today += 1

        snapshot = {
            'date':                   today_str,
            'total_events':           total_events,
            'active_events':          active_events,
            'total_registrations':    total_regs,
            'confirmed_registrations': confirmed_regs,
            'paid_registrations':     paid_regs,
            'total_users':            len(users),
            'new_users_today':        new_users_today,
            'total_revenue':          round(total_revenue, 2),
            'generated_at':           datetime.datetime.utcnow().isoformat(),
        }

        db.collection('analytics_daily').document(today_str).set(snapshot)
        logger.info("daily_rollup complete: %s", snapshot)
        return snapshot

    except Exception as exc:
        logger.error("daily_rollup failed: %s", exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='default',
    max_retries=1,
    name='tasks.analytics_tasks.event_registration_snapshot',
)
def event_registration_snapshot(self, event_id: str):
    """
    On-demand snapshot of a single event's registration stats.
    Called by admin routes after bulk imports or major status changes.
    """
    try:
        from models import db
        from google.cloud.firestore_v1.base_query import FieldFilter

        regs = list(db.collection('registrations')
                    .where(filter=FieldFilter('event_id', '==', event_id))
                    .stream())

        total     = len(regs)
        confirmed = sum(1 for r in regs if (r.to_dict() or {}).get('status') == 'Confirmed')
        paid      = sum(1 for r in regs if (r.to_dict() or {}).get('payment_status') == 'Paid')
        present   = sum(1 for r in regs if (r.to_dict() or {}).get('attendance') == 'Present')

        db.collection('events').document(event_id).update({
            'registration_count': total,
            'confirmed_count':    confirmed,
            'paid_count':         paid,
            'present_count':      present,
            'stats_updated_at':   datetime.datetime.utcnow().isoformat(),
        })
        logger.info("event snapshot: event=%s total=%d confirmed=%d paid=%d present=%d",
                    event_id, total, confirmed, paid, present)
        return {'event_id': event_id, 'total': total}

    except Exception as exc:
        raise self.retry(exc=exc)
