"""
scheduler_enhanced.py — Lightweight Job Helpers for SapthaEvent
=================================================================
In production and standard deployments, scheduled tasks run via
/internal/cron/<job> (UPG-07) or Celery beat. This module retains
lightweight job wrappers and metrics needed by maintenance tests.
"""

import datetime
from functools import wraps
import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2
ALERT_THRESHOLD = 3


class JobMetrics:
    """Track job execution metrics."""

    def __init__(self):
        self.total_runs = 0
        self.successful_runs = 0
        self.failed_runs = 0
        self.last_error = None
        self.last_error_time = None
        self.consecutive_failures = 0

    def record_success(self):
        self.total_runs += 1
        self.successful_runs += 1
        self.consecutive_failures = 0

    def record_failure(self, error: Exception):
        self.total_runs += 1
        self.failed_runs += 1
        self.last_error = str(error)
        self.last_error_time = datetime.datetime.now(datetime.timezone.utc)
        self.consecutive_failures += 1

    def to_dict(self):
        return {
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "success_rate": (self.successful_runs / self.total_runs * 100) if self.total_runs > 0 else 0,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
        }


job_metrics = {}


def retry_with_backoff(max_retries: int = MAX_RETRIES, initial_delay: int = RETRY_DELAY):
    """Decorator that retries a function with exponential backoff."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.error("%s failed after %d attempts: %s", func.__name__, max_retries + 1, e)

            raise last_exception

        return wrapper
    return decorator


def safe_job(job_name: str, alert_threshold: int = ALERT_THRESHOLD):
    """Decorator that wraps a job with error handling, metrics, and alerting."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if job_name not in job_metrics:
                job_metrics[job_name] = JobMetrics()

            metrics = job_metrics[job_name]

            try:
                start_time = time.time()
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                metrics.record_success()
                logger.info("[%s] Completed in %.2fs", job_name, duration)
                return result
            except Exception as e:
                metrics.record_failure(e)
                logger.error("[%s] Failed: %s", job_name, e, exc_info=True)
                if metrics.consecutive_failures >= alert_threshold:
                    logger.critical("[%s] Exceeded consecutive failure threshold %d", job_name, alert_threshold)
                raise e

        return wrapper
    return decorator


def _create_cleanup_job(flask_app):
    """Create cleanup job for old data (soft-archives old completed events)."""

    @safe_job("data_cleanup")
    @retry_with_backoff(max_retries=2, initial_delay=1)
    def cleanup_job():
        with flask_app.app_context():
            from models import db

            cutoff_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
            old_events = (
                db.collection("events")
                .where("status", "==", "completed")
                .where("date", "<", cutoff_date)
                .limit(100)
                .stream()
            )

            archived_count = 0
            for event in old_events:
                db.collection("events").document(event.id).update({"status": "archived"})
                archived_count += 1

            return archived_count

    return cleanup_job


def _create_event_status_transition_job(flask_app):
    """Transition events that have passed their date from 'active' to 'completed'."""

    @safe_job("event_status_transition")
    @retry_with_backoff(max_retries=2, initial_delay=1)
    def status_transition_job():
        with flask_app.app_context():
            from models import db
            today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

            past_active_events = (
                db.collection("events")
                .where("status", "==", "active")
                .where("date", "<", today_str)
                .stream()
            )

            transitioned_count = 0
            for event in past_active_events:
                db.collection("events").document(event.id).update({"status": "completed"})
                transitioned_count += 1

            return transitioned_count

    return status_transition_job
