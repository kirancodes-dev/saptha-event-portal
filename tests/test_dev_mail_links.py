"""
tests/test_dev_mail_links.py — UPG-39: with no mail provider configured, the
set-password and reset links are written to the log in development so the
flows can be followed locally, and never in production.
"""
import logging

import pytest

from tests.test_integration_flow import _unique, _user
from tests.test_registration_no_auto_login import _form, _spoc_event

PROVIDERS = ('BREVO_API_KEY', 'RESEND_API_KEY', 'MAIL_USER', 'MAIL_PASS')


@pytest.fixture
def no_provider(real_app, monkeypatch):
    for name in PROVIDERS:
        monkeypatch.setenv(name, '')
    return real_app


def _run_both_flows(flask_app, db):
    """A registration with a new email, and a reset request for an existing account."""
    event_id = _spoc_event(flask_app, db)
    newcomer = f"{_unique('devnew')}@test.edu"
    assert flask_app.test_client().post(f'/forms/submit/{event_id}', data=_form(newcomer)).status_code == 302
    student = f"{_unique('devreset')}@test.edu"
    _user(db, student, 'Student')
    assert flask_app.test_client().post('/forgot_password', data={'email': student}).status_code == 302
    return newcomer, student


def _logged(caplog):
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == 'utils_email']


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_development_logs_both_links(no_provider, caplog):
    flask_app, db = no_provider
    caplog.set_level(logging.WARNING, logger='utils_email')
    newcomer, student = _run_both_flows(flask_app, db)

    messages = [m for level, m in _logged(caplog) if level == logging.WARNING]
    assert any(newcomer in m and '/set_password/' in m and 'DEVELOPMENT ONLY' in m for m in messages)
    assert any(student in m and '/reset_token/' in m and 'DEVELOPMENT ONLY' in m for m in messages)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_production_never_logs_a_link(no_provider, caplog, monkeypatch):
    flask_app, db = no_provider
    monkeypatch.setitem(flask_app.config, 'FLASK_ENV', 'production')
    caplog.set_level(logging.DEBUG)
    newcomer, student = _run_both_flows(flask_app, db)

    every_record = [r.getMessage() for r in caplog.records]
    assert not any('/set_password/' in m or '/reset_token/' in m for m in every_record)
    errors = [m for level, m in _logged(caplog) if level == logging.ERROR]
    assert any('No mail provider' in m and newcomer in m for m in errors)
    assert any('No mail provider' in m and student in m for m in errors)


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_with_a_provider_the_links_are_not_logged(real_app, caplog, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setenv('BREVO_API_KEY', 'xkeysib-test-not-real')  # _send itself is stubbed by real_app
    caplog.set_level(logging.DEBUG)
    _run_both_flows(flask_app, db)
    assert not any('/set_password/' in r.getMessage() or '/reset_token/' in r.getMessage() for r in caplog.records)
