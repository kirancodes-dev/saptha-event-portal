"""
tests/test_login_throttle.py — BLK-13 on the real database layer: failed
logins (web and API) and password-reset requests are limited per IP and per
account, with counters every instance shares, and the answer is the same
whether or not the account exists.

Each test runs on both counter stores: the database table and Redis
(fakeredis). Unless a test says otherwise, the clock is frozen, so every
attempt happens at the same instant and the wait is the whole 60 s window.
"""
import json
import os
import subprocess
import sys
import time

import pytest

from tests.test_integration_flow import PASSWORD, _unique, _user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def clock(monkeypatch):
    import services_login_throttle as throttle
    now = [time.time()]
    monkeypatch.setattr(throttle, '_now', lambda: now[0])
    return now


@pytest.fixture(params=['database', 'redis'])
def throttled_app(request, real_app, monkeypatch, clock):
    flask_app, db = real_app
    for name, value in (('LOGIN_THROTTLE_IP_LIMIT', 5), ('LOGIN_THROTTLE_ACCOUNT_LIMIT', 5),
                        ('LOGIN_THROTTLE_WINDOW', 60), ('LOGIN_THROTTLE_STORAGE', request.param)):
        monkeypatch.setitem(flask_app.config, name, value)
    if request.param == 'redis':
        import fakeredis

        import services_login_throttle as throttle
        server = fakeredis.FakeServer()
        monkeypatch.setattr(throttle, '_redis_client', lambda: fakeredis.FakeRedis(server=server))
    return flask_app, db


def _web_login(flask_app, email, password, ip, role='Student'):
    return flask_app.test_client().post(
        '/login', data={'role': role, 'email': email, 'password': password},
        environ_base={'REMOTE_ADDR': ip})


def _api_login(flask_app, email, password, ip):
    return flask_app.test_client().post(
        '/api/v1/auth/login', json={'email': email, 'password': password, 'role': 'Student'},
        environ_base={'REMOTE_ADDR': ip})


def _logged_in(resp):
    return resp.status_code == 302 and resp.headers['Location'] not in ('/login', '/reset_password')


def _student(db, prefix='thr'):
    email = f"{_unique(prefix)}@test.edu"
    _user(db, email, 'Student')
    return email


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_sixth_failed_login_from_one_ip_is_refused_across_accounts(throttled_app):
    flask_app, db = throttled_app
    ip = '203.0.113.10'
    existing = [_student(db) for _ in range(3)]
    unknown = [f"{_unique('nobody')}@test.edu" for _ in range(2)]

    # 5 failures on 5 different accounts (known and unknown) are answered normally
    for email in existing + unknown:
        resp = _web_login(flask_app, email, 'wrong-password', ip)
        assert resp.status_code == 302 and resp.headers['Location'] == '/login'

    # The 6th from that IP is refused with the wait, on yet another account
    sixth = _web_login(flask_app, f"{_unique('other')}@test.edu", 'wrong-password', ip)
    assert sixth.status_code == 429
    assert sixth.headers['Retry-After'] == '60'
    assert b'Please try again in 60 seconds.' in sixth.data

    # While blocked, even the right password from that IP is refused and logs nobody in
    blocked = flask_app.test_client()
    resp = blocked.post('/login', data={'role': 'Student', 'email': existing[0], 'password': PASSWORD},
                        environ_base={'REMOTE_ADDR': ip})
    assert resp.status_code == 429
    with blocked.session_transaction() as sess:
        assert 'user_id' not in sess

    # Other IPs aren't affected
    assert _logged_in(_web_login(flask_app, existing[0], PASSWORD, '203.0.113.11'))


def test_password_reset_requests_are_limited_per_ip_and_per_account(throttled_app):
    flask_app, db = throttled_app
    import utils_email
    sent = []
    original = utils_email._send
    utils_email._send = lambda *a, **k: sent.append(a) or True
    try:
        # Per IP: 5 requests for different emails, then 429
        for i in range(5):
            email = _student(db) if i % 2 else f"{_unique('nobody')}@test.edu"
            resp = flask_app.test_client().post('/forgot_password', data={'email': email},
                                                environ_base={'REMOTE_ADDR': '198.51.100.1'})
            assert resp.status_code == 302
        resp = flask_app.test_client().post('/forgot_password', data={'email': _student(db)},
                                            environ_base={'REMOTE_ADDR': '198.51.100.1'})
        assert resp.status_code == 429 and b'Please try again in 60 seconds.' in resp.data

        # Per account: 5 requests for one email from different IPs, then 429,
        # and no 6th email goes out
        target = _student(db)
        for i in range(5):
            resp = flask_app.test_client().post('/forgot_password', data={'email': target},
                                                environ_base={'REMOTE_ADDR': f'198.51.100.{10 + i}'})
            assert resp.status_code == 302
        before = len(sent)
        resp = flask_app.test_client().post('/forgot_password', data={'email': target},
                                            environ_base={'REMOTE_ADDR': '198.51.100.99'})
        assert resp.status_code == 429
        assert len(sent) == before
    finally:
        utils_email._send = original


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_sixth_failure_on_one_account_from_different_ips_is_refused_until_the_window_passes(throttled_app, clock):
    flask_app, db = throttled_app
    email = _student(db)

    for i in range(5):
        resp = _web_login(flask_app, email, 'wrong-password', f'192.0.2.{i + 1}')
        assert resp.status_code == 302 and resp.headers['Location'] == '/login'

    sixth = _web_login(flask_app, email, 'wrong-password', '192.0.2.50')
    assert sixth.status_code == 429 and b'Please try again in 60 seconds.' in sixth.data
    # The right password is refused too while the account is locked
    assert _web_login(flask_app, email, PASSWORD, '192.0.2.51').status_code == 429

    # The wait counts down, and the refused attempts didn't extend it
    clock[0] += 45
    assert b'Please try again in 15 seconds.' in _web_login(flask_app, email, PASSWORD, '192.0.2.52').data

    # After the window the correct password works
    clock[0] += 16
    assert _logged_in(_web_login(flask_app, email, PASSWORD, '192.0.2.53'))


def test_success_resets_the_account_counter_but_not_the_ip_counter(throttled_app):
    flask_app, db = throttled_app
    email = _student(db)

    # 4 failures, then a success: the account starts again from zero
    for i in range(4):
        _web_login(flask_app, email, 'wrong-password', f'192.0.2.{100 + i}')
    assert _logged_in(_web_login(flask_app, email, PASSWORD, '192.0.2.110'))
    for i in range(5):
        resp = _web_login(flask_app, email, 'wrong-password', f'192.0.2.{120 + i}')
        assert resp.status_code == 302, f"failure {i + 1} after the reset was refused"
    assert _web_login(flask_app, email, 'wrong-password', '192.0.2.130').status_code == 429

    # One IP: 4 failures on other accounts, then a success there; the IP's
    # count isn't reset, so the 5th failure is the last one allowed
    ip, other = '192.0.2.200', _student(db)
    for _ in range(4):
        _web_login(flask_app, f"{_unique('nobody')}@test.edu", 'wrong-password', ip)
    assert _logged_in(_web_login(flask_app, other, PASSWORD, ip))
    assert _web_login(flask_app, f"{_unique('nobody')}@test.edu", 'wrong-password', ip).status_code == 302
    assert _web_login(flask_app, f"{_unique('nobody')}@test.edu", 'wrong-password', ip).status_code == 429


# ── Criterion 3 ─────────────────────────────────────────────────────────────

SECOND_INSTANCE = """
import json, sys
sys.path.insert(0, {root!r})
import app as app_module
from extensions import limiter
flask_app = app_module.app
flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SERVER_NAME=None,
                        LOGIN_THROTTLE_STORAGE='database', LOGIN_THROTTLE_IP_LIMIT=5,
                        LOGIN_THROTTLE_ACCOUNT_LIMIT=5, LOGIN_THROTTLE_WINDOW=60)
limiter.enabled = False
codes = []
for ip, email in {attempts!r}:
    resp = flask_app.test_client().post('/login', data={{'role': 'Student', 'email': email,
                                        'password': 'wrong-password'}}, environ_base={{'REMOTE_ADDR': ip}})
    codes.append(resp.status_code)
print('CODES=' + json.dumps(codes))
"""


def test_failures_recorded_by_another_process_count_here(real_app, monkeypatch):
    """A second app instance in its own process (as on another Cloud Run
    instance or gunicorn worker), sharing only the database."""
    flask_app, db = real_app
    for name, value in (('LOGIN_THROTTLE_IP_LIMIT', 5), ('LOGIN_THROTTLE_ACCOUNT_LIMIT', 5),
                        ('LOGIN_THROTTLE_WINDOW', 60), ('LOGIN_THROTTLE_STORAGE', 'database')):
        monkeypatch.setitem(flask_app.config, name, value)
    email, ip = _student(db), '203.0.113.77'

    # The other instance records 3 failures on the account and 2 more from the IP
    attempts = [(f'203.0.113.{i}', email) for i in (1, 2, 3)] + \
               [(ip, f"{_unique('nobody')}@test.edu") for _ in range(2)]
    out = subprocess.run([sys.executable, '-c', SECOND_INSTANCE.format(root=ROOT, attempts=attempts)],
                         cwd=ROOT, env=dict(os.environ), capture_output=True, text=True, timeout=180)
    codes = json.loads(out.stdout.split('CODES=')[-1].strip().splitlines()[0])
    assert codes == [302] * 5, out.stderr[-2000:]

    # Here: 2 more failures on the account are allowed, the 6th is refused
    for i in (4, 5):
        assert _web_login(flask_app, email, 'wrong-password', f'203.0.113.{i}').status_code == 302
    assert _web_login(flask_app, email, PASSWORD, '203.0.113.6').status_code == 429

    # And 3 more from the IP, then refused
    for _ in range(3):
        assert _web_login(flask_app, f"{_unique('nobody')}@test.edu", 'x', ip).status_code == 302
    assert _web_login(flask_app, f"{_unique('nobody')}@test.edu", 'x', ip).status_code == 429


def test_redis_counters_are_shared_by_separate_clients(real_app, monkeypatch, clock):
    """With REDIS_URL, two instances are two clients of one Redis server."""
    import fakeredis

    import services_login_throttle as throttle
    flask_app, db = real_app
    monkeypatch.setitem(flask_app.config, 'LOGIN_THROTTLE_STORAGE', 'redis')
    server = fakeredis.FakeServer()
    # a new connection on every call (an endless supply: each check reads several counters)
    monkeypatch.setattr(throttle, '_redis_client', lambda: fakeredis.FakeRedis(server=server))

    email = _student(db)
    for i in range(5):
        assert _web_login(flask_app, email, 'wrong-password', f'203.0.113.{30 + i}').status_code == 302
    assert _web_login(flask_app, email, PASSWORD, '203.0.113.40').status_code == 429


def test_a_redis_outage_falls_back_to_the_database(real_app, monkeypatch, clock):
    import services_login_throttle as throttle
    flask_app, db = real_app
    monkeypatch.setitem(flask_app.config, 'LOGIN_THROTTLE_STORAGE', 'redis')

    def down():
        raise ConnectionError('redis is down')
    monkeypatch.setattr(throttle, '_redis_client', down)

    email = _student(db)
    for i in range(5):
        assert _web_login(flask_app, email, 'wrong-password', f'203.0.113.{60 + i}').status_code == 302
    assert _web_login(flask_app, email, PASSWORD, '203.0.113.70').status_code == 429


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_api_login_is_limited_the_same_way_and_answers_alike_for_unknown_accounts(throttled_app):
    flask_app, db = throttled_app
    existing, unknown = _student(db), f"{_unique('nobody')}@test.edu"

    refusals = []
    for n, email in enumerate((existing, unknown)):
        for i in range(5):
            resp = _api_login(flask_app, email, 'wrong-password', f'192.0.2.{10 * n + i + 1}')
            assert resp.status_code == 401
            assert resp.get_json()['message'] == 'Email or password is incorrect.'  # UPG-35 wording
        sixth = _api_login(flask_app, email, 'wrong-password', f'192.0.2.{10 * n + 9}')
        assert sixth.status_code == 429 and sixth.headers['Retry-After'] == '60'
        refusals.append(sixth.get_json())
    assert refusals[0] == refusals[1] == {
        'status': 'error', 'error': 'too_many_attempts',
        'message': 'Too many attempts. Please try again in 60 seconds.',
        'details': {'retry_after': 60}}

    # Per IP across accounts, as on the web
    for _ in range(5):
        assert _api_login(flask_app, f"{_unique('nobody')}@test.edu", 'x', '192.0.2.80').status_code == 401
    assert _api_login(flask_app, existing, PASSWORD, '192.0.2.80').status_code == 429

    # Web and API share one counter: 3 web + 2 API failures, then the API refuses
    shared = _student(db)
    for i in range(3):
        _web_login(flask_app, shared, 'wrong-password', f'192.0.2.{90 + i}')
    for i in range(2):
        assert _api_login(flask_app, shared, 'wrong-password', f'192.0.2.{95 + i}').status_code == 401
    assert _api_login(flask_app, shared, PASSWORD, '192.0.2.99').status_code == 429


def test_api_success_resets_the_account_counter(throttled_app):
    flask_app, db = throttled_app
    email = _student(db)
    for i in range(4):
        assert _api_login(flask_app, email, 'wrong-password', f'192.0.2.{150 + i}').status_code == 401
    ok = _api_login(flask_app, email, PASSWORD, '192.0.2.160')
    assert ok.status_code == 200 and ok.get_json()['data']['tokens']
    for i in range(5):
        assert _api_login(flask_app, email, 'wrong-password', f'192.0.2.{170 + i}').status_code == 401


# ── UPG-37: hourly per-account cap ──────────────────────────────────────────

@pytest.fixture
def hourly_app(throttled_app, monkeypatch):
    flask_app, db = throttled_app
    monkeypatch.setitem(flask_app.config, 'LOGIN_THROTTLE_ACCOUNT_HOURLY_LIMIT', 20)
    return flask_app, db


def test_hourly_cap_stops_a_slow_guesser(hourly_app, clock):
    flask_app, db = hourly_app
    email, start = _student(db, 'slow'), clock[0]

    # 20 failures, one every 2.5 minutes (never more than 1 a minute): all answered normally
    for i in range(20):
        clock[0] = start + i * 150
        resp = _web_login(flask_app, email, 'wrong-password', f'192.0.2.{i + 1}')
        assert resp.status_code == 302 and resp.headers['Location'] == '/login', i

    # The 21st within the hour is refused until the oldest failure leaves the hour
    clock[0] = start + 49 * 60
    refused = _web_login(flask_app, email, PASSWORD, '192.0.2.99')
    assert refused.status_code == 429
    assert refused.headers['Retry-After'] == str(3600 - 49 * 60)
    clock[0] = start + 3601
    assert _logged_in(_web_login(flask_app, email, PASSWORD, '192.0.2.98'))


def test_hourly_cap_applies_to_the_api_on_the_shared_counter(hourly_app, clock):
    flask_app, db = hourly_app
    email, start = _student(db, 'slowapi'), clock[0]
    for i in range(20):
        clock[0] = start + i * 150
        login = _web_login if i % 2 else _api_login
        resp = login(flask_app, email, 'wrong-password', f'192.0.2.{i + 101}')
        assert resp.status_code in (302, 401), i
    clock[0] = start + 49 * 60
    refused = _api_login(flask_app, email, PASSWORD, '192.0.2.200')
    assert refused.status_code == 429 and refused.get_json()['error'] == 'too_many_attempts'


def test_success_clears_the_hourly_count_and_ips_have_no_hourly_cap(hourly_app, clock):
    flask_app, db = hourly_app
    email, start = _student(db, 'oops'), clock[0]
    for i in range(19):
        clock[0] = start + i * 150
        _web_login(flask_app, email, 'wrong-password', f'192.0.2.{i + 1}')
    clock[0] = start + 19 * 150
    assert _logged_in(_web_login(flask_app, email, PASSWORD, '192.0.2.50'))
    for i in range(5):  # without the reset, the 2nd of these would be the 21st
        clock[0] = start + (20 + i) * 150
        assert _web_login(flask_app, email, 'wrong-password', f'192.0.2.{i + 60}').status_code == 302

    # One IP, 25 failures on different accounts spread over the hour: never refused
    ip = '198.51.100.7'
    for i in range(25):
        clock[0] = start + 4000 + i * 140
        resp = _web_login(flask_app, f"{_unique('nobody')}@test.edu", 'x', ip)
        assert resp.status_code == 302, i
