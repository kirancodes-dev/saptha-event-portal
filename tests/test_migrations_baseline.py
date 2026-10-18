"""
tests/test_migrations_baseline.py — UPG-16: the schema is built only by Alembic.

  * `alembic upgrade head` builds an empty SQLite file and an empty PostgreSQL
    database, and `compare_metadata` against models_pg finds no differences
    (on SQLite, type reflection is ignored: UUID columns read back as NUMERIC);
  * `alembic downgrade base` then `upgrade head` works on PostgreSQL;
  * production start-up issues no CREATE or ALTER, and refuses a database
    that isn't at head with a clear message.

Each step runs in a subprocess so its DATABASE_URL can't leak into the
suite. The PostgreSQL steps use a fresh database on TEST_DATABASE_URL's server
and are skipped without one.
"""
import json
import os
import subprocess
import sys
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COMPARE = r'''
import json, os
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from db_pg import _normalize_url
from models_pg import Base
url = _normalize_url(os.environ["DATABASE_URL"])
engine = create_engine(url)
with engine.connect() as conn:
    ctx = MigrationContext.configure(conn, opts={"compare_type": not url.startswith("sqlite")})
    diffs = compare_metadata(ctx, Base.metadata)
print("DIFFS=" + json.dumps([str(d) for d in diffs]))
'''

STARTUP = r'''
import json
from sqlalchemy import event
import db_pg
statements = []
event.listen(db_pg.get_engine(), "before_cursor_execute",
             lambda conn, cursor, stmt, *a: statements.append(stmt.strip().split()[0:2]))
try:
    from db_adapter import SQLFirestoreAdapter
    SQLFirestoreAdapter()
    print("STARTUP=" + json.dumps({"ok": True, "ddl": [s for s in statements if s and s[0].upper() in ("CREATE", "ALTER")]}))
except db_pg.DatabaseConfigError as exc:
    print("STARTUP=" + json.dumps({"ok": False, "error": str(exc)}))
'''


def _run(args, url, extra_env=None):
    env = dict(os.environ, DATABASE_URL=url, DATABASE_TYPE='postgres', FLASK_ENV='development')
    env.update(extra_env or {})
    env.pop('TEST_DATABASE_URL', None)
    return subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)


def _alembic(url, *args):
    r = _run([sys.executable, '-m', 'alembic', *args], url)
    assert r.returncode == 0, r.stderr[-1500:]


def _python(code, url, marker, **env):
    r = _run([sys.executable, '-c', code], url, env)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith(marker + '=')), None)
    assert line, (r.stdout[-800:], r.stderr[-1500:])
    return json.loads(line[len(marker) + 1:])


@pytest.fixture
def sqlite_url(tmp_path):
    return f"sqlite:///{tmp_path / 'empty.db'}"


@pytest.fixture
def pg_url():
    base = os.environ.get('TEST_DATABASE_URL', '')
    if not base.startswith('postgres'):
        pytest.skip('needs TEST_DATABASE_URL pointing at PostgreSQL')
    from sqlalchemy import create_engine, text
    from db_pg import _normalize_url
    name = f"upg16_{uuid.uuid4().hex[:10]}"
    admin = create_engine(_normalize_url(base), isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(base)
    yield urlunsplit(parts._replace(path=f'/{name}'))
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_upgrade_head_builds_an_empty_sqlite_database_that_matches_the_models(sqlite_url):
    _alembic(sqlite_url, 'upgrade', 'head')
    assert _python(COMPARE, sqlite_url, 'DIFFS') == []


def test_upgrade_head_builds_an_empty_postgresql_database_that_matches_the_models(pg_url):
    _alembic(pg_url, 'upgrade', 'head')
    assert _python(COMPARE, pg_url, 'DIFFS') == []


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_downgrade_base_then_upgrade_head_on_postgresql(pg_url):
    _alembic(pg_url, 'upgrade', 'head')
    _alembic(pg_url, 'downgrade', 'base')
    _alembic(pg_url, 'upgrade', 'head')
    assert _python(COMPARE, pg_url, 'DIFFS') == []


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_production_start_up_refuses_an_unmigrated_database_and_never_alters_one(sqlite_url):
    refused = _python(STARTUP, sqlite_url, 'STARTUP', FLASK_ENV='production', ALLOW_SQLITE_IN_PRODUCTION='true')
    assert refused['ok'] is False and 'alembic upgrade head' in refused['error']

    _alembic(sqlite_url, 'upgrade', 'head')
    started = _python(STARTUP, sqlite_url, 'STARTUP', FLASK_ENV='production', ALLOW_SQLITE_IN_PRODUCTION='true')
    assert started == {'ok': True, 'ddl': []}


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_deploy_guide_shows_the_migration_step_and_the_stamp():
    with open(os.path.join(ROOT, 'docs', 'DEPLOY.md'), encoding='utf-8') as fh:
        guide = fh.read()
    assert 'alembic upgrade head' in guide and 'alembic stamp 0001_baseline' in guide
