"""
tests/test_db_connections_traffic.py — UPG-319.

On 2026-11-19 the live site answered "Internal Server Error" to every request,
pictures and fonts too: the database (Cloud SQL db-f1-micro, 25 slots) ran out
of connections ("remaining connection slots are reserved for roles with the
SUPERUSER attribute"). Every request read the session from the database, even
a picture, and each server process could hold 30 connections, with 2 processes
per copy and up to 3 copies, plus the old copies during a deploy.

Now pictures, scripts, fonts, the service worker and the health checks never
read the session; each process keeps at most 2 connections and opens at most
3 more under load, and a request waits for a free one instead of failing; one
process with 8 threads per copy; and the deploy guide's sizes fit the database.
"""
import os
import re
import runpy
import subprocess
import sys

import pytest
from sqlalchemy import event

from tests.test_sessions_server_side import _logged_in_student, sql_app  # noqa: F401  (fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Checkouts:
    """Counts database connections taken from the pool."""

    def __init__(self):
        from db_pg import get_engine
        self.engine, self.n = get_engine(), 0

    def _out(self, *args):
        self.n += 1

    def __enter__(self):
        event.listen(self.engine, 'checkout', self._out)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, 'checkout', self._out)


# ── Criterion 1: files and health checks never read the session ─────────────

@pytest.mark.parametrize('path', ['/static/css/fonts.css', '/static/app-icon.png', '/sw.js', '/robots.txt'])
def test_a_file_never_touches_the_database_and_the_visitor_stays_signed_in(sql_app, path):  # noqa: F811
    flask_app, db = sql_app
    client, email = _logged_in_student(flask_app, db)
    with _Checkouts() as c:
        resp = client.get(path)
    assert resp.status_code in (200, 404), resp.status_code
    assert c.n == 0, f'{path} took {c.n} database connections'
    assert 'Set-Cookie' not in resp.headers                # the session is neither renewed nor dropped
    with client.session_transaction() as s:
        assert s.get('user_id') == email
    assert client.get('/participant/dashboard').status_code == 200   # still signed in


def test_the_health_checks_read_only_their_own_database_check(sql_app):  # noqa: F811
    flask_app, db = sql_app
    client, _ = _logged_in_student(flask_app, db)
    with _Checkouts() as c:
        assert client.get('/health').status_code == 200
    assert c.n == 1                                        # the health check's own query, no session read


def test_a_page_still_reads_the_session(sql_app):  # noqa: F811
    flask_app, db = sql_app
    client, email = _logged_in_student(flask_app, db)
    with _Checkouts() as c:
        assert client.get('/participant/dashboard').status_code == 200
    assert c.n >= 1


def test_only_files_and_health_checks_skip_the_session():
    from flask import Flask

    from session_store import needs_no_session
    app = Flask('x')
    for path in ('/static/js/app.js', '/static/x.png', '/sw.js', '/favicon.ico', '/robots.txt', '/health',
                 '/health/ready'):
        assert needs_no_session(app, path), path
    for path in ('/', '/login', '/staticpage', '/static', '/participant/dashboard', '/health/x', '/healthz'):
        assert not needs_no_session(app, path), path


# ── Criterion 2: a small, capped pool that waits instead of failing ─────────

def test_each_process_keeps_2_connections_opens_at_most_3_more_and_waits_15_seconds():
    import db_pg
    engine = db_pg._postgres_engine('postgresql+psycopg2://user:pass@localhost/none')   # doesn't connect
    try:
        from sqlalchemy.pool import QueuePool
        pool = engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.size() == 2
        assert getattr(pool, '_max_overflow') == 3
        assert getattr(pool, '_timeout') == 15
    finally:
        engine.dispose()


def test_the_pool_sizes_can_be_set_for_a_bigger_database():
    code = ("import db_pg; e = db_pg._postgres_engine('postgresql+psycopg2://u:p@localhost/none'); "
            "print(e.pool.size(), e.pool._max_overflow, e.pool._timeout)")
    env = dict(os.environ, PGBOUNCER_POOL_SIZE='4', PGBOUNCER_MAX_OVERFLOW='6', PGBOUNCER_POOL_TIMEOUT='9',
               DATABASE_URL='sqlite://')
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert out.stdout.split()[-3:] == ['4', '6', '9'], out.stderr[-500:]


# ── Criterion 3: one process, 8 threads per copy ────────────────────────────

def _gunicorn(monkeypatch, **env):
    for name in ('WEB_CONCURRENCY', 'WORKERS', 'GUNICORN_THREADS'):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return runpy.run_path(os.path.join(ROOT, 'gunicorn.conf.py'))


def test_one_process_with_8_threads_by_default_and_both_can_be_set(monkeypatch):
    conf = _gunicorn(monkeypatch)
    assert (conf['workers'], conf['threads']) == (1, 8)
    conf = _gunicorn(monkeypatch, WEB_CONCURRENCY='2', GUNICORN_THREADS='4')
    assert (conf['workers'], conf['threads']) == (2, 4)


# ── Criterion 4: the deploy guide's sizes fit the smallest database ─────────

def _deploy_guide():
    with open(os.path.join(ROOT, 'docs', 'DEPLOY.md'), encoding='utf-8') as f:
        return f.read()


def test_the_deploy_command_and_the_update_command_use_sizes_that_fit_db_f1_micro(monkeypatch):
    import db_pg
    guide = _deploy_guide()
    conf = _gunicorn(monkeypatch)
    commands = [c for c in re.findall(r'gcloud run (?:deploy|services update) saptha[^`]*?(?=\n\n|\n```)', guide, re.S)
                if '--concurrency' in c]
    assert len(commands) >= 2                         # the first set-up and the "change them" command
    for cmd in commands:
        concurrency = int(re.findall(r'--concurrency=(\d+)', cmd)[0])
        instances = int(re.findall(r'--max-instances=(\d+)', cmd)[0])
        assert re.search(r'--min-instances=1\b', cmd)
        assert 'WEB_CONCURRENCY=1' in cmd and 'GUNICORN_THREADS=8' in cmd
        assert 'PGBOUNCER_POOL_SIZE=2' in cmd and 'PGBOUNCER_MAX_OVERFLOW=3' in cmd
        assert concurrency == conf['workers'] * conf['threads']   # Cloud Run sends what a copy can work on
        per_copy = conf['workers'] * (db_pg.PGBOUNCER_POOL_SIZE + db_pg.PGBOUNCER_MAX_OVERFLOW)
        old_copies = conf['workers'] * db_pg.PGBOUNCER_POOL_SIZE * instances
        assert instances * per_copy + old_copies + 1 <= 25 - 3      # db-f1-micro's slots, 3 kept by Google
    flat = ' '.join(guide.split())
    assert 'remaining connection slots are reserved' in flat and '## Traffic and database connections' in guide
