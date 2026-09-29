"""
tests/test_repo_hygiene.py — Nothing that holds user data or credentials may be
tracked in git (BLK-01): local databases, .env files, service-account keys,
compiled Python, the Data Connect emulator's data folder and Flask's instance/.

Also pins the .gitignore rules that keep those files out. CI runs this file in
its own job (see .github/workflows/ci.yml, "Repo hygiene & secret scan").
"""
import json
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (pattern on the repo-relative path, reason)
FORBIDDEN = [
    (re.compile(r'(^|/)\.env(\.[^/]+)?$'), '.env file (only .env.example may be tracked)'),
    (re.compile(r'\.db$'), 'database file'),
    (re.compile(r'\.sqlite[^/]*$'), 'SQLite database file'),
    (re.compile(r'(^|/)(serviceAccountKey|service-account[^/]*)\.json$'), 'service-account key file'),
    (re.compile(r'\.pyc$'), 'compiled Python'),
    (re.compile(r'(^|/)__pycache__/'), 'compiled Python cache'),
    (re.compile(r'^dataconnect/\.dataconnect/'), 'Data Connect emulator data (local Postgres)'),
    (re.compile(r'^instance/'), 'Flask instance folder (local config / databases)'),
]
ALLOWED = [re.compile(r'(^|/)\.env\.example$')]


def forbidden_reason(path):
    if any(a.search(path) for a in ALLOWED):
        return None
    for pattern, reason in FORBIDDEN:
        if pattern.search(path):
            return reason
    return None


def _git(*args):
    return subprocess.run(['git', '-C', ROOT, *args], capture_output=True, text=True)


@pytest.fixture(scope='module')
def tracked_files():
    top = _git('rev-parse', '--show-toplevel')
    if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(ROOT):
        pytest.skip('not running from a git checkout of this repository')
    out = _git('ls-files', '-z')
    assert out.returncode == 0, out.stderr
    return [p for p in out.stdout.split('\0') if p]


def test_no_forbidden_files_are_tracked(tracked_files):
    offenders = [f'{p}  ({forbidden_reason(p)})' for p in tracked_files if forbidden_reason(p)]
    assert not offenders, (
        'These files must not be committed (remove with `git rm --cached`, '
        'they are covered by .gitignore):\n  ' + '\n  '.join(offenders))


def test_no_service_account_credentials_in_tracked_json(tracked_files):
    offenders = []
    for path in tracked_files:
        if not path.endswith('.json'):
            continue
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full) or os.path.getsize(full) > 2_000_000:
            continue
        try:
            with open(full, encoding='utf-8') as fh:
                data = json.load(fh)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and data.get('type') == 'service_account' and data.get('private_key'):
            offenders.append(path)
    assert not offenders, f'service-account credentials committed: {offenders}'


@pytest.mark.parametrize('path', [
    '.env', '.env.production', 'config/.env.local', 'saptha_fallback.db', 'instance/event_portal.db',
    'data/app.sqlite3', 'x.sqlite-journal', 'serviceAccountKey.json', 'keys/service-account-prod.json',
    '__pycache__/app.cpython-311.pyc', 'pkg/mod.pyc', 'dataconnect/.dataconnect/pgliteData/pg17/PG_VERSION',
])
def test_patterns_flag_forbidden_paths(path):
    assert forbidden_reason(path)


@pytest.mark.parametrize('path', [
    '.env.example', 'saptha-event-portal/.env.example', 'db_adapter.py', 'docs/DATABASE.md',
    'dataconnect/schema/schema.gql', 'dataconnect/dataconnect.yaml', 'tests/test_db_documents.py',
])
def test_patterns_allow_normal_paths(path):
    assert forbidden_reason(path) is None


@pytest.mark.parametrize('path,ignored', [
    ('.env', True), ('.env.production', True), ('sub/.env.local', True),
    ('.env.example', False), ('sub/dir/.env.example', False),
    ('local.db', True), ('data.sqlite', True), ('data.sqlite3', True),
    ('instance/config.py', True), ('dataconnect/.dataconnect/pgliteData/x', True),
    ('__pycache__/m.cpython-311.pyc', True), ('pkg/m.pyc', True),
    ('service-account.json', True), ('service-account-prod.json', True), ('serviceAccountKey.json', True),
    ('dataconnect/schema/schema.gql', False),
])
def test_gitignore_rules(tracked_files, path, ignored):
    # Only this repo's .gitignore counts, not a developer's global excludes file;
    # --no-index so the rule is checked even if such a file were (wrongly) tracked
    r = _git('-c', 'core.excludesFile=/dev/null', 'check-ignore', '--no-index', '-q', path)
    assert (r.returncode == 0) is ignored, f'{path}: expected ignored={ignored}'
