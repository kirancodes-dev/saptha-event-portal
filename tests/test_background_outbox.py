"""
tests/test_background_outbox.py — UPG-18 on the real database layer, no broker:
a task that raises leaves one outbox row (attempts 1) and the request that
queued it still succeeds; a task past TASK_INLINE_TIMEOUT hands control back
within the limit and is stored (and marked sent if it finishes later); the
cron `outbox` job sends a stored task once, a second run sends nothing, and a
task that keeps failing is marked failed at the maximum. Also: the job needs
the cron secret, `cleanup` deletes only old sent/failed rows, and with a broker
apply_async isn't intercepted. Criterion 4 is the DEPLOY.md section.
"""
import datetime
import os
import time

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import services_outbox
from celery_app import celery
from db_pg import get_engine
from models_pg import OutboxTask
from tests.test_integration_flow import _create_event, _login, _unique, _user

CRON = 'cron-secret-for-pytest'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = {}            # tag -> number of times the task body ran
FAILING = set()      # tags whose task raises


@celery.task(name='tests.test_background_outbox.sometimes_fails')
def sometimes_fails(tag):
    RUNS[tag] = RUNS.get(tag, 0) + 1
    if tag in FAILING:
        raise RuntimeError(f'provider down for {tag}')
    return 'sent'


@celery.task(name='tests.test_background_outbox.slow')
def slow(tag, seconds):
    time.sleep(seconds)
    RUNS[tag] = RUNS.get(tag, 0) + 1
    return 'sent'


def _row(task, *args):
    key = services_outbox.task_key(task.name, args, {})
    with Session(get_engine()) as s:
        row = s.execute(select(OutboxTask).where(OutboxTask.key == key)).scalar_one_or_none()
        return None if row is None else {'status': row.status, 'attempts': row.attempts, 'error': row.last_error,
                                         'key': key}


def _set(key, **values):
    with Session(get_engine()) as s, s.begin():
        s.execute(update(OutboxTask).where(OutboxTask.key == key).values(**values))


def _due_now(key):
    _set(key, next_attempt_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1))


@pytest.fixture
def cron(real_app, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setenv('CRON_SECRET', CRON)
    client = flask_app.test_client()

    def run(job):
        resp = client.post(f'/internal/cron/{job}', headers={'X-Cron-Secret': CRON})
        assert resp.status_code == 200, resp.data
        return resp.get_json()
    return {'app': flask_app, 'db': db, 'client': client, 'run': run}


def test_no_broker_means_tasks_run_inline():
    assert celery.conf.task_always_eager is True        # the test setup has no redis:// broker


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_a_failing_task_leaves_one_row_with_attempts_1_and_the_call_returns(cron):
    tag = _unique('fail')
    FAILING.add(tag)
    result = sometimes_fails.delay(tag)                   # never raises
    assert result.status == 'FAILURE' and RUNS[tag] == 1  # ran once: no inline retries
    row = _row(sometimes_fails, tag)
    assert (row['status'], row['attempts']) == ('pending', 1) and 'provider down' in row['error']
    sometimes_fails.delay(tag)                            # the same send failing again keeps one row
    assert _row(sometimes_fails, tag)['attempts'] == 1


def test_a_request_whose_task_fails_still_succeeds(cron, monkeypatch):
    d = cron
    import routes_waitlist

    def broken(db, event_id):
        raise RuntimeError('waitlist store unavailable')
    monkeypatch.setattr(routes_waitlist, 'auto_promote', broken)
    spoc, student = f"{_unique('obspoc')}@test.edu", f"{_unique('obstu')}@test.edu"
    _user(d['db'], spoc, 'ClubSPOC')
    _user(d['db'], student, 'Student')
    event_id = _create_event(_login(d['app'], spoc, 'ClubSPOC'), d['db'], _unique('Outbox Talk'), '2031-01-20',
                             team=False)
    reg_id = _unique('REG')
    d['db'].collection('registrations').document(reg_id).set({
        'event_id': event_id, 'lead_email': student, 'lead_name': 'Ola', 'status': 'Confirmed'})

    resp = _login(d['app'], student, 'Student').post(f'/participant/cancel/{reg_id}')
    assert resp.status_code == 302 and resp.headers['Location'] == '/participant/dashboard'
    assert d['db'].collection('registrations').document(reg_id).get().to_dict()['status'] == 'Cancelled'
    from tasks.waitlist_tasks import promote_from_waitlist
    row = _row(promote_from_waitlist, event_id)
    assert (row['status'], row['attempts']) == ('pending', 1)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_a_task_past_the_timeout_returns_within_the_limit_and_is_stored(cron, monkeypatch):
    monkeypatch.setenv('TASK_INLINE_TIMEOUT', '0.5')
    tag = _unique('slow')
    started = time.monotonic()
    slow.delay(tag, 2)
    assert time.monotonic() - started < 1.5               # the caller waited about the limit, not 2 s
    row = _row(slow, tag, 2)
    assert row['status'] == 'pending' and 'timed out' in row['error']
    # When it finishes after all, the row is marked sent, so it isn't retried
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _row(slow, tag, 2)['status'] != 'done':
        time.sleep(0.1)
    assert _row(slow, tag, 2)['status'] == 'done' and RUNS[tag] == 1


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_retry_job_sends_a_stored_task_once(cron):
    tag = _unique('retry')
    FAILING.add(tag)
    sometimes_fails.delay(tag)
    key = _row(sometimes_fails, tag)['key']
    cron['run']('outbox')
    assert RUNS[tag] == 1                                 # not due yet (5 minutes): not retried

    FAILING.discard(tag)                                  # the provider is back
    _due_now(key)
    cron['run']('outbox')
    assert RUNS[tag] == 2 and _row(sometimes_fails, tag)['status'] == 'done'
    _due_now(key)
    cron['run']('outbox')                                 # a second run sends nothing
    assert RUNS[tag] == 2


def test_a_task_that_keeps_failing_is_marked_failed_at_the_maximum(cron, monkeypatch):
    monkeypatch.setenv('OUTBOX_MAX_ATTEMPTS', '3')
    tag = _unique('dead')
    FAILING.add(tag)
    sometimes_fails.delay(tag)                            # attempt 1, inline
    key = _row(sometimes_fails, tag)['key']
    for attempt in (2, 3):
        _due_now(key)
        cron['run']('outbox')
        assert _row(sometimes_fails, tag)['attempts'] == attempt
    row = _row(sometimes_fails, tag)
    assert row['status'] == 'failed' and RUNS[tag] == 3
    _due_now(key)
    cron['run']('outbox')                                 # failed rows aren't retried
    assert RUNS[tag] == 3


def test_a_claimed_row_isnt_sent_by_a_second_run(cron):
    tag = _unique('claim')
    FAILING.add(tag)
    sometimes_fails.delay(tag)
    key = _row(sometimes_fails, tag)['key']
    FAILING.discard(tag)
    _due_now(key)
    now = datetime.datetime.now(datetime.timezone.utc)
    assert services_outbox._claim(key, now) is True       # one run takes it
    assert services_outbox._claim(key, now) is False      # the other can't
    assert services_outbox.retry_due()['sent'] == 0 and RUNS[tag] == 1


# ── The extras in "To test later" ───────────────────────────────────────────

def test_the_outbox_job_needs_the_cron_secret(cron):
    assert cron['client'].post('/internal/cron/outbox').status_code == 403
    assert cron['client'].post('/internal/cron/outbox', headers={'X-Cron-Secret': 'wrong'}).status_code == 403


def test_cleanup_deletes_only_old_sent_and_failed_rows(cron):
    now = datetime.datetime.now(datetime.timezone.utc)
    ages = {'old-done': ('done', 8), 'new-done': ('done', 1), 'old-failed': ('failed', 31),
            'new-failed': ('failed', 10), 'old-pending': ('pending', 40)}
    keys = {}
    for label, (status, days) in ages.items():
        tag = _unique(label)
        keys[label] = services_outbox.store(sometimes_fails.name, (tag,), {}, 'stored by the test')
        _set(keys[label], status=status, updated_at=now - datetime.timedelta(days=days))
    cron['run']('cleanup')
    with Session(get_engine()) as s:
        left = set(s.execute(select(OutboxTask.key).where(OutboxTask.key.in_(keys.values()))).scalars())
    assert left == {keys['new-done'], keys['new-failed'], keys['old-pending']}


def test_with_a_broker_apply_async_is_not_intercepted(monkeypatch):
    from celery import Task
    queued = []
    monkeypatch.setattr(celery.conf, 'task_always_eager', False)
    monkeypatch.setattr(Task, 'apply_async', lambda self, *a, **k: queued.append(self.name) or 'queued')
    monkeypatch.setattr(services_outbox, 'run_inline', lambda *a, **k: pytest.fail('ran inline with a broker'))
    assert sometimes_fails.delay(_unique('broker')) == 'queued'
    assert queued == [sometimes_fails.name]


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_deploy_guide_explains_both_modes():
    with open(os.path.join(ROOT, 'docs', 'DEPLOY.md'), encoding='utf-8') as f:
        guide = f.read()
    section = guide[guide.index('## Background tasks'):]
    assert '**Inline + outbox' in section and '**Broker mode' in section
    for setting in ('TASK_INLINE_TIMEOUT', 'OUTBOX_MAX_ATTEMPTS', 'TASK_INLINE_THREADS', 'CELERY_BROKER_URL'):
        assert setting in section, setting
    assert '`outbox` | every 15 minutes' in guide
