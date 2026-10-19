"""
tests/test_production_boot.py — UPG-20: production start-up refuses with one
error naming every missing setting and starts with strong dummy values (on a
migrated database: SQLite with ALLOW_SQLITE_IN_PRODUCTION, and PostgreSQL when
TEST_DATABASE_URL points at one); every environment variable the app reads is
in .env.example; /health is 503 with the database unreachable and 200
otherwise, with no error text; production logs are one JSON object per line;
Sentry starts only with SENTRY_DSN and without personal data; production
responses carry HSTS, nosniff, a referrer policy and a frame policy.
"""
import ast
import json
import os
import re
import secrets
import subprocess
import sys
import types

import pytest

from tests.test_migrations_baseline import pg_url  # noqa: F401  (fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Strong dummy settings, made fresh for each run so no secret-looking literal sits
# in the repo (the CI secret scan, UPG-118)
STRONG = {
    'FLASK_ENV': 'production',
    'SECRET_KEY': secrets.token_urlsafe(32),
    'MASTER_SECRET_KEY': secrets.token_urlsafe(16),
    'JWT_SECRET_KEY': secrets.token_urlsafe(32),
    'BASE_URL': 'https://events.example.edu',
    'BREVO_API_KEY': 'dummy-' + secrets.token_hex(8),
    'MAIL_FROM': 'events@example.edu',
    'CRON_SECRET': secrets.token_urlsafe(24),
    'CELERY_BROKER_URL': '', 'RAZORPAY_KEY_ID': '', 'RAZORPAY_KEY_SECRET': '', 'RAZORPAY_WEBHOOK_SECRET': '',
    'PAYMENT_SIMULATION': '', 'SUPER_ADMIN_PASS': '', 'SENTRY_DSN': '', 'CLOUD_SQL_INSTANCE': '',
    'DATABASE_TYPE': 'postgres',
}

BOOT = r'''
import json, logging, sys
try:
    import app as app_module
except Exception as exc:
    print("BOOT=" + json.dumps({"started": False, "error": str(exc)}))
    sys.exit(0)
client = app_module.app.test_client()
home = client.get("/", base_url="https://events.example.edu")
health = client.get("/health", base_url="https://events.example.edu")
logging.getLogger("boot-test").warning("boot check line")
sys.stderr.flush()
print("BOOT=" + json.dumps({"started": True, "home": home.status_code, "health": health.status_code,
                            "health_body": health.get_json(), "headers": dict(home.headers)}))
'''


def _alembic(url):
    env = dict(os.environ, DATABASE_URL=url, FLASK_ENV='development')
    env.pop('TEST_DATABASE_URL', None)
    r = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-1500:]


def _boot(url, **overrides):
    env = dict(os.environ, **STRONG, DATABASE_URL=url)
    env.update(overrides)
    env.pop('TEST_DATABASE_URL', None)
    r = subprocess.run([sys.executable, '-c', BOOT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith('BOOT=')), None)
    assert line, (r.returncode, r.stdout[-800:], r.stderr[-2000:])
    return json.loads(line[5:]), r.stderr


@pytest.fixture
def migrated_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'prod.db'}"
    _alembic(url)
    return url


# ── Criteria 1, 3 (healthy), 4 and 6 through a real production start-up ──────

def test_production_refuses_with_one_error_naming_every_missing_setting(migrated_sqlite):
    result, _ = _boot(migrated_sqlite, ALLOW_SQLITE_IN_PRODUCTION='true', BREVO_API_KEY='', CRON_SECRET='')
    assert result['started'] is False
    error = result['error']
    assert 'Refusing to start in production' in error
    assert 'no mail provider' in error and 'CRON_SECRET' in error       # both, in one error
    assert error.count('\n  - ') == 2


def test_production_starts_with_strong_settings_and_is_hardened(migrated_sqlite):
    result, stderr = _boot(migrated_sqlite, ALLOW_SQLITE_IN_PRODUCTION='true')
    assert result['started'] is True, result
    assert result['home'] == 200 and result['health'] == 200
    assert set(result['health_body']) == {'status', 'timestamp', 'version'}
    headers = {k.lower(): v for k, v in result['headers'].items()}
    assert headers['strict-transport-security'].startswith('max-age=31536000')
    assert headers['x-content-type-options'] == 'nosniff'
    assert headers['referrer-policy'] == 'strict-origin-when-cross-origin'
    assert headers['x-frame-options'] == 'SAMEORIGIN'
    # Logs: one JSON object per line, with severity and message
    [line] = [ln for ln in stderr.splitlines() if 'boot check line' in ln]
    entry = json.loads(line)
    assert entry['severity'] == 'WARNING' and entry['message'] == 'boot check line'


def test_production_starts_on_postgresql(pg_url):  # noqa: F811
    _alembic(pg_url)
    result, _ = _boot(pg_url)
    assert result['started'] is True and result['health'] == 200, result
    refused, _ = _boot(pg_url, JWT_SECRET_KEY=STRONG['SECRET_KEY'], MAIL_FROM='')
    assert refused['started'] is False
    assert 'JWT_SECRET_KEY must differ' in refused['error'] and 'MAIL_FROM' in refused['error']


def test_without_a_database_production_names_that_too():
    result, _ = _boot('', BREVO_API_KEY='')
    assert result['started'] is False
    assert 'DATABASE_URL must be set' in result['error'] and 'no mail provider' in result['error']


# ── Criterion 2 ─────────────────────────────────────────────────────────────

# Read only by developer tools, never by the app: seed_safety.py's Firestore check
TOOL_ONLY = {'FIRESTORE_EMULATOR_HOST', 'GOOGLE_APPLICATION_CREDENTIALS'}


def _env_names(source):
    names = set()
    for node in ast.walk(ast.parse(source)):
        key = None
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            if ast.unparse(node.func) in ('os.environ.get', 'os.getenv', 'environ.get', 'os.environ.setdefault',
                                          'os.environ.pop'):
                key = node.args[0].value
        elif isinstance(node, ast.Subscript) and ast.unparse(node.value) in ('os.environ', 'environ') \
                and isinstance(node.slice, ast.Constant):
            key = node.slice.value
        if isinstance(key, str) and re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            names.add(key)
    return names


def test_every_environment_variable_the_app_reads_is_in_env_example():
    tracked = subprocess.run(['git', 'ls-files', '*.py'], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.split()
    read = set()
    for path in (p for p in tracked if not p.startswith('tests/')):
        with open(os.path.join(ROOT, path), encoding='utf-8') as f:
            read |= _env_names(f.read())
    with open(os.path.join(ROOT, '.env.example'), encoding='utf-8') as f:
        listed = set(re.findall(r'^#?\s*([A-Z][A-Z0-9_]*)=', f.read(), re.M))
    assert len(read) > 90
    assert sorted(read - listed - TOOL_ONLY) == []


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_health_is_503_without_the_database_and_shows_no_error(real_app, monkeypatch):
    flask_app, _ = real_app
    client = flask_app.test_client()
    ok = client.get('/health')
    assert ok.status_code == 200 and ok.get_json()['status'] == 'healthy'
    assert client.get('/health/ready').get_json() == {'ready': True}

    from sqlalchemy import create_engine
    import db_pg
    unreachable = create_engine('postgresql+psycopg2://nobody:secret-pw@127.0.0.1:1/none',
                                connect_args={'connect_timeout': 2})
    monkeypatch.setattr(db_pg, 'get_engine', lambda: unreachable)
    for path, body_keys in (('/health', {'status', 'timestamp', 'version'}), ('/health/ready', {'ready'})):
        down = client.get(path)
        assert down.status_code == 503 and set(down.get_json()) == body_keys
        text = down.get_data(as_text=True)
        for leak in ('Error', 'refused', '127.0.0.1', 'secret-pw', 'Traceback', 'psycopg'):
            assert leak not in text, (path, leak)


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_sentry_starts_only_with_a_dsn_and_without_personal_data(monkeypatch):
    import app as app_module
    calls = []
    fake = types.ModuleType('sentry_sdk')
    fake.init = lambda **kw: calls.append(kw)
    flask_integration = types.ModuleType('sentry_sdk.integrations.flask')
    flask_integration.FlaskIntegration = lambda: 'flask-integration'
    monkeypatch.setitem(sys.modules, 'sentry_sdk', fake)
    monkeypatch.setitem(sys.modules, 'sentry_sdk.integrations', types.ModuleType('sentry_sdk.integrations'))
    monkeypatch.setitem(sys.modules, 'sentry_sdk.integrations.flask', flask_integration)

    assert app_module.init_sentry(env={}) is False and calls == []
    assert app_module.init_sentry(env={'SENTRY_DSN': '  '}) is False and calls == []
    assert app_module.init_sentry(env={'SENTRY_DSN': 'https://key@o1.ingest.sentry.io/1', 'FLASK_ENV': 'production',
                                       'K_REVISION': 'saptha-00042'}) is True
    [kw] = calls
    assert kw['send_default_pii'] is False and kw['dsn'].startswith('https://key@')
    assert kw['release'] == 'saptha-00042' and kw['environment'] == 'production'
