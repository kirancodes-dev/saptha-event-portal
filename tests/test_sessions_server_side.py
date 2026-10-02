"""
tests/test_sessions_server_side.py — BLK-08 on the real SQL database layer:
sessions live in the database, survive restarts, work across instances and
aren't created for anonymous page views.
"""
import datetime
import json
import os
import subprocess
import sys

import pytest
from flask import Flask, session as flask_session

from tests.test_integration_flow import PASSWORD, _unique, _user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def sql_app(real_app, monkeypatch):
    """The real app on the database session store (the production default),
    whatever SESSION_TYPE the test environment sets."""
    from session_store import SQLSessionInterface
    flask_app, db = real_app
    monkeypatch.setattr(flask_app, 'session_interface', SQLSessionInterface())
    return flask_app, db


def _rows():
    from sqlalchemy.orm import Session

    from db_pg import get_engine
    from models_pg import FlaskSession
    with Session(get_engine()) as s:
        return s.query(FlaskSession).count()


def _logged_in_student(flask_app, db):
    email = f"{_unique('sess')}@test.edu"
    _user(db, email, 'Student')
    client = flask_app.test_client()
    resp = client.post('/login', data={'role': 'Student', 'email': email, 'password': PASSWORD})
    assert resp.headers['Location'] != '/login'
    return client, email


def _second_instance(secret_key):
    """A separately created Flask app sharing only the database: another
    Cloud Run instance, or this one after a restart."""
    from session_store import SQLSessionInterface
    other = Flask('second-instance')
    other.config.update(SECRET_KEY=secret_key, TESTING=True)
    other.session_interface = SQLSessionInterface()

    @other.route('/whoami')
    def whoami():
        return {'user': flask_session.get('user_id')}
    return other


def _cookie(client, name='session'):
    found = client.get_cookie(name)
    return found.value if found else None


# ── Criteria 1 and 3 ───────────────────────────────────────────────────────

def test_anonymous_traffic_creates_no_sessions_and_logs_nobody_out(sql_app):
    flask_app, db = sql_app
    client, email = _logged_in_student(flask_app, db)
    before = _rows()

    anonymous = flask_app.test_client()
    events = anonymous.get('/events')
    assert events.status_code == 200
    assert not any(h.startswith('session=') for h in events.headers.getlist('Set-Cookie'))
    assert _rows() == before  # a plain page view stores no session

    # 600 different visitors on a page with a form token (the old file store
    # pruned past 500 and logged real users out)
    for _ in range(600):
        flask_app.test_client().get('/')
    assert _rows() >= before + 600
    with client.session_transaction() as sess:
        assert sess.get('user_id') == email
    assert client.get('/participant/dashboard').status_code == 200


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_file_sessions_if_chosen_keep_a_high_threshold(real_app):
    flask_app, _ = real_app
    assert flask_app.config['SESSION_FILE_THRESHOLD'] >= 50000


# ── Criteria 4 and 5 ───────────────────────────────────────────────────────

def test_a_session_works_on_another_instance_and_after_a_restart(sql_app):
    flask_app, db = sql_app
    client, email = _logged_in_student(flask_app, db)
    sid = _cookie(client)
    assert sid

    # Another instance (separate app object and session store) sees the login
    other = _second_instance(flask_app.config['SECRET_KEY']).test_client()
    other.set_cookie('session', sid)
    assert other.get('/whoami').get_json() == {'user': email}

    # "Restart" the real app: a brand-new session store, same database
    from session_store import SQLSessionInterface
    flask_app.session_interface = SQLSessionInterface()
    assert client.get('/participant/dashboard').status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('user_id') == email

    # Logging out removes it everywhere
    client.get('/logout')
    assert other.get('/whoami').get_json() == {'user': None}


def test_expired_sessions_are_ignored_and_purged(sql_app):
    flask_app, db = sql_app
    from sqlalchemy.orm import Session

    from db_pg import get_engine
    from models_pg import FlaskSession
    from session_store import purge_expired_sessions

    client, _ = _logged_in_student(flask_app, db)
    sid = _cookie(client)
    with Session(get_engine()) as s, s.begin():
        s.get(FlaskSession, sid).expiry = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
    with client.session_transaction() as sess:
        assert 'user_id' not in sess
    assert purge_expired_sessions() >= 1
    with Session(get_engine()) as s:
        assert s.get(FlaskSession, sid) is None


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_production_cookies_are_secure_httponly_and_lax(sql_app, monkeypatch):
    env = dict(os.environ, FLASK_ENV='production', SECRET_KEY='x' * 48, MASTER_SECRET_KEY='y' * 24)
    for name in ('SESSION_TYPE', 'REDIS_URL'):  # check the default, not CI's choice
        env.pop(name, None)
    code = ("import json, config; c = config.Config; print(json.dumps([c.SESSION_COOKIE_SECURE, "
            "c.SESSION_COOKIE_HTTPONLY, c.SESSION_COOKIE_SAMESITE, c.SESSION_TYPE]))")
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                         capture_output=True, text=True, check=True)
    secure, httponly, samesite, session_type = json.loads(out.stdout.strip().splitlines()[-1])
    assert (secure, httponly, samesite) == (True, True, 'Lax')
    assert session_type == 'sqlalchemy'  # no REDIS_URL: the database, never files

    # And the cookie the app actually sends carries those flags
    flask_app, db = sql_app
    monkeypatch.setitem(flask_app.config, 'SESSION_COOKIE_SECURE', True)
    email = f"{_unique('cookie')}@test.edu"
    _user(db, email, 'Student')
    resp = flask_app.test_client().post('/login', data={'role': 'Student', 'email': email, 'password': PASSWORD})
    cookie = next(h for h in resp.headers.getlist('Set-Cookie') if h.startswith('session='))
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
