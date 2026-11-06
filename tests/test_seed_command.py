"""
tests/test_seed_command.py — UPG-15: `python seed.py --profile …` is the one
seed command. On a throwaway local database the demo and events profiles add
their accounts and events, and the showcase profile empties the tables and
builds the demonstration portal (summary written); the scale profile needs a
DATABASE_URL.
"""
import json
import os
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _seed(db_file, *args, **env):
    run_env = dict(os.environ, DATABASE_URL=f'sqlite:///{db_file}', CLOUD_SQL_INSTANCE='', FLASK_ENV='development',
                   **env)
    return subprocess.run([sys.executable, 'seed.py', *args], cwd=ROOT, env=run_env,
                          capture_output=True, text=True, timeout=600)


def _count(db_file, table, where='1=1'):
    with sqlite3.connect(db_file) as conn:
        return conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {where}').fetchone()[0]  # nosec B608 (test literals)


def test_the_demo_and_events_profiles_seed_a_local_database(tmp_path):
    db_file = tmp_path / 'seed.db'
    demo = _seed(db_file, '--profile', 'demo')
    assert demo.returncode == 0, demo.stderr[-1500:]
    assert _count(db_file, 'users', "id = 'admin@snpsu.edu.in'") == 1
    assert _count(db_file, 'events') == 1
    events = _seed(db_file, '--profile', 'events')
    assert events.returncode == 0, events.stderr[-1500:]
    assert _count(db_file, 'events') == 8                   # the flagship plus 7 template events


def test_the_showcase_profile_rebuilds_the_portal_and_writes_its_summary(tmp_path):
    db_file, summary = tmp_path / 'showcase.db', tmp_path / 'summary.json'
    assert _seed(db_file, '--profile', 'demo').returncode == 0
    run = _seed(db_file, '--profile', 'showcase', '--summary', str(summary))
    assert run.returncode == 0, run.stderr[-1500:]
    made = json.loads(summary.read_text())
    assert len(made['accounts']) == _count(db_file, 'users')        # the tables were emptied first
    assert _count(db_file, 'users', "id = 'admin@snpsu.edu.in'") == 0
    assert len(made['events']) == _count(db_file, 'events') > 40


def test_the_scale_profile_needs_a_database_url(tmp_path):
    run = subprocess.run([sys.executable, 'seed.py', '--profile', 'scale'], cwd=ROOT,
                         env=dict(os.environ, DATABASE_URL='', CLOUD_SQL_INSTANCE='', FLASK_ENV='development'),
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 1 and 'DATABASE_URL not set' in run.stdout
