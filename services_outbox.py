"""
services_outbox.py — background tasks without a broker (UPG-18)

With no Celery broker (`CELERY_BROKER_URL` not `redis://…`), every queued task
runs inline in the request. Each one runs once, in a worker thread, for at most
`TASK_INLINE_TIMEOUT` seconds (default 10), so a slow mail or WhatsApp provider
can't hold the request. A task that fails or runs past the limit is stored in
the `outbox` table, and the cron endpoint's `outbox` job
(`POST /internal/cron/outbox`, UPG-07) retries due rows with backoff until it
succeeds or reaches `OUTBOX_MAX_ATTEMPTS` (default 5), when it's marked failed.

Each row's key is its idempotency key (a hash of the task and its arguments):
storing the same failed send twice keeps one row, and a row is claimed with a
conditional UPDATE, so two cron runs can't send it twice.

With a broker, Celery queues tasks as before and none of this runs.
"""
import concurrent.futures
import datetime
import hashlib
import importlib
import json
import logging
import os

logger = logging.getLogger(__name__)

_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=int(os.environ.get('TASK_INLINE_THREADS', '8')), thread_name_prefix='inline-task')

BASE_BACKOFF = datetime.timedelta(minutes=5)
MAX_BACKOFF = datetime.timedelta(hours=6)
STUCK_AFTER = datetime.timedelta(minutes=30)   # a 'running' row older than this is retried
KEEP_DONE = datetime.timedelta(days=7)
KEEP_FAILED = datetime.timedelta(days=30)


def inline_timeout() -> float:
    return float(os.environ.get('TASK_INLINE_TIMEOUT', '10'))


def max_attempts() -> int:
    return int(os.environ.get('OUTBOX_MAX_ATTEMPTS', '5'))


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def backoff(attempts: int) -> datetime.timedelta:
    """5 minutes after the first failure, doubling, at most 6 hours."""
    return min(BASE_BACKOFF * (2 ** max(attempts - 1, 0)), MAX_BACKOFF)


def task_key(task_name: str, args, kwargs) -> str:
    raw = json.dumps([task_name, list(args or ()), kwargs or {}], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _session():
    from sqlalchemy.orm import Session

    from db_pg import get_engine
    return Session(get_engine())


def _run_once(task, args, kwargs):
    """Run the task in this thread with no inline retries: (ok, error text)."""
    retries = task.max_retries if task.max_retries is not None else 0
    result = task.apply(args=args, kwargs=kwargs, retries=retries)
    if result.failed():
        return False, repr(result.result)[:2000]
    return True, ''


def _submit(task, args, kwargs):
    """(ok, error, future); ok is None when the task is still running at the limit."""
    future = _executor.submit(_run_once, task, args, kwargs)
    try:
        ok, error = future.result(timeout=inline_timeout())
        return ok, error, future
    except concurrent.futures.TimeoutError:
        return None, f'timed out after {inline_timeout():g}s', future
    except Exception as exc:  # the thread itself failed
        return False, repr(exc)[:2000], future


def _finish_late(key):
    """When a timed-out run ends, record a success so it isn't sent again."""
    def callback(future):
        try:
            ok, _ = future.result()
        except Exception:
            return
        if ok:
            mark_done(key, only_if=('pending', 'running'))
    return callback


def run_inline(task, args=(), kwargs=None):
    """Run a queued task inline (no broker). Never raises: a failure or a
    timeout is stored in the outbox. Returns an EagerResult."""
    from celery.result import EagerResult
    import uuid

    args, kwargs = tuple(args or ()), dict(kwargs or {})
    ok, error, future = _submit(task, args, kwargs)
    task_id = str(uuid.uuid4())
    if ok:
        return EagerResult(task_id, None, 'SUCCESS')
    key = store(task.name, args, kwargs, error)
    if ok is None and key:
        future.add_done_callback(_finish_late(key))
    logger.warning("Task %s %s; kept in the outbox for retry", task.name, 'timed out' if ok is None else 'failed')
    return EagerResult(task_id, None, 'FAILURE')


def store(task_name, args, kwargs, error) -> str:
    """Keep a failed send for retry (attempts 1). One row per key: a send
    already waiting keeps its row; one done or failed earlier is re-armed."""
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError

    from models_pg import OutboxTask
    try:
        args_json, kwargs_json = json.dumps(list(args)), json.dumps(kwargs)
    except (TypeError, ValueError):
        logger.error("Task %s has arguments that can't be stored; not retried", task_name)
        return ''
    key = task_key(task_name, args, kwargs)
    now = _now()
    try:
        try:
            with _session() as s, s.begin():
                s.add(OutboxTask(key=key, task_name=task_name, args_json=args_json, kwargs_json=kwargs_json,
                                 status='pending', attempts=1, next_attempt_at=now + backoff(1),
                                 last_error=error, created_at=now, updated_at=now))
        except IntegrityError:
            with _session() as s, s.begin():
                s.execute(update(OutboxTask)
                          .where(OutboxTask.key == key, OutboxTask.status.in_(('done', 'failed')))
                          .values(status='pending', attempts=1, next_attempt_at=now + backoff(1),
                                  last_error=error, updated_at=now))
    except Exception:
        logger.exception("Could not store task %s in the outbox", task_name)
        return ''
    return key


def mark_done(key, only_if=('running',)):
    from sqlalchemy import update

    from models_pg import OutboxTask
    with _session() as s, s.begin():
        s.execute(update(OutboxTask).where(OutboxTask.key == key, OutboxTask.status.in_(only_if))
                  .values(status='done', last_error=None, updated_at=_now()))


def _due(now):
    """Rows to retry: pending and due, or left 'running' by a process that died."""
    from sqlalchemy import and_, or_

    from models_pg import OutboxTask
    return or_(and_(OutboxTask.status == 'pending', OutboxTask.next_attempt_at <= now),
               and_(OutboxTask.status == 'running', OutboxTask.updated_at <= now - STUCK_AFTER))


def _claim(key, now) -> bool:
    """Take one row with a conditional UPDATE, so two runs can't both send it."""
    from sqlalchemy import update

    from models_pg import OutboxTask
    with _session() as s, s.begin():
        result = s.execute(update(OutboxTask).where(OutboxTask.key == key, _due(now))
                           .values(status='running', updated_at=_now()))
        return result.rowcount == 1


def _task_by_name(name):
    from celery_app import celery
    module = name.rsplit('.', 1)[0]
    importlib.import_module(module)
    return celery.tasks[name]


def _after_attempt(key, attempts, ok, error):
    from sqlalchemy import update

    from models_pg import OutboxTask
    now = _now()
    if ok:
        values = dict(status='done', attempts=attempts, last_error=None)
    elif attempts >= max_attempts():
        values = dict(status='failed', attempts=attempts, last_error=error)
    else:
        values = dict(status='pending', attempts=attempts, last_error=error,
                      next_attempt_at=now + backoff(attempts))
    with _session() as s, s.begin():
        s.execute(update(OutboxTask).where(OutboxTask.key == key, OutboxTask.status == 'running')
                  .values(updated_at=now, **values))


def retry_due(limit: int = 50) -> dict:
    """The cron `outbox` job: retry rows that are due, once each."""
    from sqlalchemy import select

    from models_pg import OutboxTask
    now = _now()
    with _session() as s:
        rows = s.execute(
            select(OutboxTask.key, OutboxTask.task_name, OutboxTask.args_json, OutboxTask.kwargs_json,
                   OutboxTask.attempts)
            .where(_due(now)).order_by(OutboxTask.next_attempt_at).limit(limit)).all()

    counts = {'sent': 0, 'retry_later': 0, 'failed': 0, 'skipped': 0}
    for key, name, args_json, kwargs_json, attempts in rows:
        if not _claim(key, now):
            counts['skipped'] += 1          # another run took it
            continue
        attempts = int(attempts or 0) + 1
        try:
            task = _task_by_name(name)
            ok, error, future = _submit(task, tuple(json.loads(args_json)), json.loads(kwargs_json))
        except Exception as exc:
            ok, error, future = False, repr(exc)[:2000], None
        if ok is None and future is not None:
            future.add_done_callback(_finish_late(key))
        _after_attempt(key, attempts, bool(ok), error)
        if ok:
            counts['sent'] += 1
        elif attempts >= max_attempts():
            counts['failed'] += 1
            logger.error("Outbox task %s failed %d times; giving up: %s", name, attempts, error)
        else:
            counts['retry_later'] += 1
    return counts


def purge_old() -> int:
    """The cron `cleanup` job: sent rows after 7 days, failed rows after 30."""
    from sqlalchemy import and_, delete, or_

    from models_pg import OutboxTask
    now = _now()
    with _session() as s, s.begin():
        result = s.execute(delete(OutboxTask).where(or_(
            and_(OutboxTask.status == 'done', OutboxTask.updated_at <= now - KEEP_DONE),
            and_(OutboxTask.status == 'failed', OutboxTask.updated_at <= now - KEEP_FAILED))))
        return result.rowcount or 0
