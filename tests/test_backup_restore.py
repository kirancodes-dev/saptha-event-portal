"""
tests/test_backup_restore.py — UPG-21 against a real PostgreSQL (skipped
without TEST_DATABASE_URL and pg_dump/pg_restore/psql): scripts/backup_db.sh
dumps a migrated database with rows in it, uploads the dump and prunes dumps
past the retention; scripts/restore_db.sh puts it into an empty database with
the same row count in every table and the same Alembic revision, and refuses a
database that already has tables. The bucket is a local folder behind a
stand-in `aws` command; nothing leaves the machine.
"""
import os
import shutil
import subprocess
import sys
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAKE_AWS = r'''#!/usr/bin/env bash
# A stand-in for `aws s3 cp|ls|rm` that keeps s3://bucket/... in $FAKE_S3_DIR
set -e
[ "$1" = "--endpoint-url" ] && shift 2
[ "$1" = "s3" ] || exit 9
shift
local_path() { echo "$FAKE_S3_DIR/${1#s3://}"; }
case "$1" in
  cp)
    src="$2"; dst="$3"
    case "$src" in s3://*) src="$(local_path "$src")" ;; esac
    case "$dst" in s3://*) dst="$(local_path "$dst")"; mkdir -p "$(dirname "$dst")" ;; esac
    cp "$src" "$dst" ;;
  ls)
    dir="$(local_path "$2")"
    [ -d "$dir" ] && for f in "$dir"/*; do [ -f "$f" ] && echo "2026-10-18 02:00:00 $(wc -c < "$f") $(basename "$f")"; done; true ;;
  rm) rm -f "$(local_path "$2")" ;;
esac
'''


def _pg_bin():
    try:
        import pgserver
        path = os.path.join(os.path.dirname(pgserver.__file__), 'pginstall', 'bin')
        if os.path.exists(os.path.join(path, 'pg_dump')):
            return path
    except ImportError:
        pass
    found = shutil.which('pg_dump')
    return os.path.dirname(found) if found else None


@pytest.fixture
def pg():
    base = os.environ.get('TEST_DATABASE_URL', '')
    pg_bin = _pg_bin()
    if not base.startswith('postgres') or not pg_bin:
        pytest.skip('needs TEST_DATABASE_URL (PostgreSQL) and pg_dump/pg_restore/psql')
    from sqlalchemy import create_engine, text
    from db_pg import _normalize_url
    admin = create_engine(_normalize_url(base), isolation_level='AUTOCOMMIT')
    names = [f"upg21_{k}_{uuid.uuid4().hex[:8]}" for k in ('src', 'dst')]
    with admin.connect() as conn:
        for name in names:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    urls = [urlunsplit(urlsplit(base)._replace(path=f'/{n}')) for n in names]
    yield {'src': urls[0], 'dst': urls[1], 'bin': pg_bin}
    with admin.connect() as conn:
        for name in names:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def _psql(pg, url, sql):
    r = subprocess.run([os.path.join(pg['bin'], 'psql'), url, '-Atc', sql], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _counts(pg, url):
    tables = _psql(pg, url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1").split()
    return {t: int(_psql(pg, url, f'SELECT count(*) FROM "{t}"')) for t in tables}


def test_a_backup_restores_into_an_empty_database_with_the_same_rows(pg, tmp_path):
    env = dict(os.environ, DATABASE_URL=pg['src'], FLASK_ENV='development')
    env.pop('TEST_DATABASE_URL', None)
    r = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-1000:]
    for i in range(7):
        _psql(pg, pg['src'], f"INSERT INTO users (id, email, name, role, \"passwordHash\", \"isActive\", \"createdAt\", \"updatedAt\") "
                             f"VALUES ('u{i}@test.edu', 'u{i}@test.edu', 'User {i}', 'Participant', 'x', true, now(), now())")
    before = _counts(pg, pg['src'])
    assert before['users'] == 7

    bucket = tmp_path / 'bucket'
    (bucket / 'backups').mkdir(parents=True)
    (bucket / 'backups' / 'saptha-20200101T000000Z.dump').write_bytes(b'old')   # past the retention
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    (fake_bin / 'aws').write_text(FAKE_AWS)
    (fake_bin / 'aws').chmod(0o755)
    run_env = dict(os.environ, PATH=f"{fake_bin}:{pg['bin']}:{os.environ['PATH']}", FAKE_S3_DIR=str(bucket),
                   DATABASE_URL=pg['src'], BACKUP_BUCKET='s3://backups', BACKUP_RETENTION_DAYS='30')

    backup = subprocess.run(['bash', 'scripts/backup_db.sh'], cwd=ROOT, env=run_env, capture_output=True, text=True, timeout=300)
    assert backup.returncode == 0, backup.stderr
    dumps = sorted(p.name for p in (bucket / 'backups').iterdir())
    assert len(dumps) == 1 and dumps[0].startswith('saptha-2026') and 'Removed 1 dump' in backup.stdout

    restore = subprocess.run(['bash', 'scripts/restore_db.sh', f's3://backups/{dumps[0]}', pg['dst']], cwd=ROOT,
                             env=run_env, capture_output=True, text=True, timeout=300)
    assert restore.returncode == 0, restore.stderr
    assert _counts(pg, pg['dst']) == before
    assert _psql(pg, pg['dst'], 'SELECT version_num FROM alembic_version') == \
        _psql(pg, pg['src'], 'SELECT version_num FROM alembic_version')

    again = subprocess.run(['bash', 'scripts/restore_db.sh', f's3://backups/{dumps[0]}', pg['dst']], cwd=ROOT,
                           env=run_env, capture_output=True, text=True, timeout=300)
    assert again.returncode == 3 and 'already has' in again.stderr


def test_the_guide_documents_backups_and_the_restore_drill():
    with open(os.path.join(ROOT, 'docs', 'DEPLOY.md'), encoding='utf-8') as fh:
        guide = fh.read()
    for needed in ('## Backups', '## Restore drill', 'BACKUP_RETENTION_DAYS', 'BACKUP_BUCKET', 'restore_db.sh'):
        assert needed in guide, needed
