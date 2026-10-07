"""
tests/test_mail_sender.py — UPG-41: no built-in sender account. Mail comes
from MAIL_FROM, else from the MAIL_USER login; with neither, the HTTP
providers refuse to send rather than use somebody's address.
"""
import os
import subprocess
import sys
import types
import urllib.request

import pytest

import utils_email

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENDER_SETTINGS = ('MAIL_FROM', 'MAIL_USER', 'MAIL_PASS', 'BREVO_API_KEY', 'RESEND_API_KEY')


@pytest.fixture
def no_sender(monkeypatch):
    for name in SENDER_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    calls = []

    def sent(*args, **kwargs):
        calls.append(args)
        pytest.fail('mail was sent')
    monkeypatch.setattr(urllib.request, 'urlopen', sent)
    monkeypatch.setitem(sys.modules, 'resend', types.SimpleNamespace(Emails=types.SimpleNamespace(send=sent)))
    return monkeypatch, calls


def test_with_neither_setting_there_is_no_sender_and_nothing_is_sent(no_sender):
    monkeypatch, calls = no_sender
    assert utils_email._from_address() == ''

    for provider in ('BREVO_API_KEY', 'RESEND_API_KEY'):
        monkeypatch.setenv(provider, 'test-key')
        assert utils_email._send('someone@test.edu', 'Hello', '<p>hi</p>') is False
        assert 'MAIL_FROM' in utils_email.LAST_EMAIL_ERROR
        monkeypatch.delenv(provider)
    assert calls == []


def test_the_sender_is_mail_from_else_the_mail_user_login(no_sender):
    monkeypatch, _ = no_sender
    monkeypatch.setenv('MAIL_USER', 'events@example.edu')
    assert utils_email._from_address() == 'SapthaEvent <events@example.edu>'
    monkeypatch.setenv('MAIL_FROM', 'Saptha Events <noreply@example.edu>')
    assert utils_email._from_address() == 'Saptha Events <noreply@example.edu>'


def test_config_has_no_built_in_mail_account():
    # A fresh interpreter: Config reads the environment when it's imported
    env = {k: v for k, v in os.environ.items() if k not in SENDER_SETTINGS + ('MAIL_SENDER',)}
    env.update(MAIL_USER='', MAIL_PASS='')
    out = subprocess.run(
        [sys.executable, '-c', 'import config; c = config.Config; '
                               'print(repr((c.MAIL_USERNAME, c.MAIL_PASSWORD, c.MAIL_DEFAULT_SENDER[1])))'],
        cwd=ROOT, env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "('', '', '')"
