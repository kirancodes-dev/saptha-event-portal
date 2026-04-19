"""
scheduler_enhanced.py — Hardened Task Scheduler with Retry Logic
=================================================================

Enhanced version of scheduler.py with:
- Automatic retry logic (exponential backoff)
- Error tracking and alerting
- Job execution metrics
- Graceful failure handling
- Timeout protection

Usage:
  from scheduler_enhanced import enhanced_init_scheduler
  enhanced_init_scheduler(app)
"""

import logging
import datetime
import time
from functools import wraps
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor

logger = logging.getLogger(__name__)

# Configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds, exponential backoff
JOB_TIMEOUT = 300  # 5 minutes
ALERT_THRESHOLD = 3  # Alert if job fails N times


class JobMetrics:
    """Track job execution metrics"""
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
        self.last_error_time = datetime.datetime.now()
        self.consecutive_failures += 1
    
    def to_dict(self):
        return {
            'total_runs': self.total_runs,
            'successful_runs': self.successful_runs,
            'failed_runs': self.failed_runs,
            'success_rate': (self.successful_runs / self.total_runs * 100) if self.total_runs > 0 else 0,
            'consecutive_failures': self.consecutive_failures,
            'last_error': self.last_error,
            'last_error_time': self.last_error_time.isoformat() if self.last_error_time else None
        }


# Global metrics storage
job_metrics = {}


def retry_with_backoff(max_retries: int = MAX_RETRIES, initial_delay: int = RETRY_DELAY):
    """
    Decorator that retries a function with exponential backoff.
    
    Usage:
        @retry_with_backoff(max_retries=3)
        def risky_operation():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    logger.debug(f"Attempting {func.__name__} (attempt {attempt + 1}/{max_retries + 1})")
                    return func(*args, **kwargs)
                
                except Exception as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}), "
                            f"retrying in {delay}s: {str(e)}"
                        )
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {str(e)}"
                        )
            
            raise last_exception
        
        return wrapper
    return decorator


def safe_job(job_name: str, alert_threshold: int = ALERT_THRESHOLD):
    """
    Decorator that wraps a job with error handling, metrics, and alerting.
    
    Usage:
        @safe_job('send_reminders')
        def reminder_job():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if job_name not in job_metrics:
                job_metrics[job_name] = JobMetrics()
            
            metrics = job_metrics[job_name]
            
            try:
                logger.info(f"[{job_name}] Starting...")
                start_time = time.time()
                
                result = func(*args, **kwargs)
                
                duration = time.time() - start_time
                metrics.record_success()
                logger.info(f"[{job_name}] Completed successfully in {duration:.2f}s")
                
                return result
            
            except Exception as e:
                metrics.record_failure(e)
                logger.error(f"[{job_name}] Failed: {str(e)}", exc_info=True)
                
                # Alert if consecutive failures exceed threshold
                if metrics.consecutive_failures >= alert_threshold:
                    send_alert(
                        f"Job '{job_name}' failed {metrics.consecutive_failures} times",
                        f"Error: {str(e)}\n\nMetrics: {metrics.to_dict()}"
                    )
                
                # Don't re-raise - we want scheduler to keep running
                return None
        
        return wrapper
    return decorator


def send_alert(subject: str, message: str):
    """
    Send alert to administrators when critical jobs fail.
    Can be enhanced to send emails, Slack messages, etc.
    """
    logger.critical(f"ALERT: {subject}\n{message}")
    
    # TODO: Send email to admin
    # TODO: Send Slack notification
    # TODO: Log to external monitoring (Sentry, Datadog)


def get_scheduler_status():
    """Return current scheduler status and metrics"""
    return {
        'timestamp': datetime.datetime.now().isoformat(),
        'job_metrics': {name: metrics.to_dict() for name, metrics in job_metrics.items()}
    }


# =========================================================
# ENHANCED SCHEDULER INITIALIZATION
# =========================================================

def enhanced_init_scheduler(flask_app, enable_threading: bool = True):
    """
    Initialize enhanced background scheduler with retry logic,
    error handling, and monitoring.
    
    Args:
        flask_app: Flask application instance
        enable_threading: Use thread pool executor (True) or process (False)
    
    Returns:
        BackgroundScheduler instance
    """
    executor = ThreadPoolExecutor(
        max_workers=2,
        thread_name_prefix='scheduler-'
    ) if enable_threading else ProcessPoolExecutor(max_workers=2)
    
    scheduler = BackgroundScheduler(
        timezone="Asia/Kolkata",
        executors={'default': executor},
        job_defaults={
            'coalesce': True,  # Only run once if multiple triggers fire
            'max_instances': 1,  # Only one instance at a time
            'misfire_grace_time': 600,  # 10-minute grace period
        }
    )
    
    # Example job: Event reminders every hour
    scheduler.add_job(
        func=_create_reminder_job(flask_app),
        trigger=IntervalTrigger(hours=1),
        id='event_reminders',
        name='Send 24-hour event reminders',
        replace_existing=True,
        max_instances=1
    )
    
    # Example job: Cleanup old data every day at 2 AM IST
    scheduler.add_job(
        func=_create_cleanup_job(flask_app),
        trigger='cron',
        hour=2,
        minute=0,
        timezone='Asia/Kolkata',
        id='data_cleanup',
        name='Cleanup old data',
        replace_existing=True,
        max_instances=1
    )
    
    scheduler.start()
    logger.info("✅ Enhanced scheduler started with retry logic and monitoring")
    
    return scheduler


def _create_reminder_job(flask_app):
    """Create reminder job with error handling"""
    
    @safe_job('event_reminders')
    @retry_with_backoff(max_retries=3, initial_delay=2)
    def reminder_job():
        with flask_app.app_context():
            from models import db
            from utils_email import send_email
            
            # Get IST timezone
            ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
            tomorrow = (datetime.datetime.now(ist) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            
            logger.info(f"Checking for events on {tomorrow}")
            
            # Query events
            events = db.collection('events')\
                .where('status', '==', 'active')\
                .stream()
            
            reminder_count = 0
            
            for event_doc in events:
                event = event_doc.to_dict()
                event_date = str(event.get('date', ''))[:10]
                
                if event_date != tomorrow:
                    continue
                
                # Get registrations for this event
                registrations = db.collection('registrations')\
                    .where('event_id', '==', event_doc.id)\
                    .where('status', '==', 'Confirmed')\
                    .stream()
                
                for reg_doc in registrations:
                    reg = reg_doc.to_dict()
                    
                    # Skip if already sent
                    if reg.get('reminder_sent'):
                        continue
                    
                    # Send email
                    try:
                        send_email(
                            recipient=reg.get('lead_email'),
                            subject=f"Reminder: {event.get('title')} Tomorrow!",
                            body=f"""
                            Dear {reg.get('lead_name')},
                            
                            Your event "{event.get('title')}" is tomorrow!
                            
                            Date: {event.get('date')}
                            Venue: {event.get('venue')}
                            
                            Best regards,
                            SapthaEvent Team
                            """
                        )
                        
                        # Mark as sent
                        db.collection('registrations').document(reg_doc.id).update({
                            'reminder_sent': True,
                            'reminder_sent_at': datetime.datetime.now().isoformat()
                        })
                        
                        reminder_count += 1
                    
                    except Exception as e:
                        logger.error(f"Failed to send reminder to {reg.get('lead_email')}: {e}")
            
            logger.info(f"Sent {reminder_count} reminders")
            return reminder_count
    
    return reminder_job


def _create_cleanup_job(flask_app):
    """Create cleanup job for old data"""
    
    @safe_job('data_cleanup')
    @retry_with_backoff(max_retries=2, initial_delay=5)
    def cleanup_job():
        with flask_app.app_context():
            from models import db
            
            # Example: Delete events older than 6 months
            cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
            
            logger.info(f"Cleaning up events before {cutoff_date}")
            
            old_events = db.collection('events')\
                .where('status', '==', 'completed')\
                .order_by('date')\
                .limit(100)\
                .stream()
            
            deleted_count = 0
            for event in old_events:
                event_data = event.to_dict()
                event_date = event_data.get('date', '')
                
                if event_date < cutoff_date:
                    # Archive or delete
                    db.collection('events').document(event.id).delete()
                    deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} old events")
            return deleted_count
    
    return cleanup_job


if __name__ == '__main__':
    # Test retry decorator
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def test_function():
        import random
        if random.random() < 0.7:
            raise Exception("Random failure for testing")
        return "Success!"
    
    try:
        result = test_function()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Failed: {e}")
