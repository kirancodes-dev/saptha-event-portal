"""
tests/test_email_links_and_logo.py — UPG-91: links in emails open the address
the portal is being used on when that address is trusted (this machine, the
local network or ngrok in development; BASE_URL and TRUSTED_HOSTS anywhere),
never a forged one; the logo travels inside each email; and a refused Gmail
login reports Gmail's reason.
"""
import email
import json

import pytest

from utils_links import is_trusted_host

BASE = 'https://events.example.edu'


# ── Which addresses are trusted ────────────────────────────────────────────

@pytest.mark.parametrize('host', ['localhost:5001', '127.0.0.1:5001', '192.168.1.6:5001', '10.0.0.5',
                                  '[::1]:5001', 'ab12-34cd.ngrok-free.app', 'events.example.edu'])
def test_development_trusts_this_machine_the_lan_and_ngrok(host):
    assert is_trusted_host(host, BASE, production=False)


@pytest.mark.parametrize('host', ['evil.example', 'events.example.edu.evil.example', 'attacker.com:5001',
                                  '8.8.8.8', 'ngrok-free.app.evil.example', '', 'user@evil.example'])
def test_untrusted_hosts_are_never_used(host):
    assert not is_trusted_host(host, BASE, production=False)


def test_production_trusts_only_base_url_and_listed_hosts(monkeypatch):
    for host in ('localhost:5001', '192.168.1.6', 'ab12.ngrok-free.app'):
        assert not is_trusted_host(host, BASE, production=True)
    assert is_trusted_host('events.example.edu', BASE, production=True)
    monkeypatch.setenv('TRUSTED_HOSTS', 'portal.snpsu.edu.in, *.preview.example')
    assert is_trusted_host('portal.snpsu.edu.in', BASE, production=True)
    assert is_trusted_host('pr-12.preview.example', BASE, production=True)
    assert not is_trusted_host('preview.example.evil.example', BASE, production=True)


# ── Links follow the trusted address in use ────────────────────────────────

@pytest.fixture
def mailer(real_app, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setitem(flask_app.config, 'BASE_URL', BASE)
    monkeypatch.setitem(flask_app.config, 'FLASK_ENV', 'development')
    sent = []
    import utils_email
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: sent.append((to, html)) or True)
    return flask_app, db, sent


@pytest.mark.parametrize('origin', ['http://192.168.1.6:5001', 'http://127.0.0.1:5001',
                                    'https://ab12-34cd.ngrok-free.app'])
def test_a_link_sent_from_a_trusted_address_opens_there(mailer, origin):
    flask_app, db, sent = mailer
    from utils_email import _base_url
    with flask_app.test_request_context('/', base_url=origin):
        assert _base_url() == origin


def test_a_forged_address_still_gets_base_url(mailer):
    flask_app, db, sent = mailer
    from utils_email import _base_url
    for forged in ('http://evil.example', 'https://attacker.example'):
        with flask_app.test_request_context('/', base_url=forged, headers={'X-Forwarded-Host': 'attacker.example'}):
            assert _base_url() == BASE
    with flask_app.app_context():                        # scheduled jobs: no request
        assert _base_url() == BASE


def test_set_password_email_links_to_the_address_in_use(mailer):
    flask_app, db, sent = mailer
    from tests.test_integration_flow import _unique, _user
    from services_accounts import send_set_password_link
    email_addr = f"{_unique('linkuser')}@test.edu"
    _user(db, email_addr, 'ClubSPOC', name='Link User')
    with flask_app.test_request_context('/', base_url='http://192.168.1.6:5001'):
        assert send_set_password_link(db, email_addr, 'Link User')
    with flask_app.test_request_context('/', base_url='http://evil.example'):
        assert send_set_password_link(db, email_addr, 'Link User')
    assert 'http://192.168.1.6:5001/set_password/' in sent[0][1]
    assert f'{BASE}/set_password/' in sent[1][1] and 'evil.example' not in sent[1][1]
    db.collection('users').document(email_addr).delete()


# ── The logo travels with the email ────────────────────────────────────────

class _FakeSMTP:
    sent = []
    auth_seen = []

    def __init__(self, *a, **k):
        self.esmtp_features = {'auth': 'LOGIN PLAIN XOAUTH2'}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self, *a):
        return 250, b'ok'

    def login(self, user, password):
        _FakeSMTP.auth_seen.append(self.esmtp_features['auth'])

    def send_message(self, msg):
        _FakeSMTP.sent.append(msg)


def test_smtp_email_carries_the_logo_inline_and_logs_in_with_plain_only(monkeypatch, real_app):
    import smtplib
    import utils_email
    monkeypatch.setenv('MAIL_USER', 'portal@example.com')
    monkeypatch.setenv('MAIL_PASS', 'abcd efgh ijkl mnop')
    monkeypatch.delenv('COLLEGE_LOGO_URL', raising=False)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', _FakeSMTP)
    _FakeSMTP.sent.clear()
    _FakeSMTP.auth_seen.clear()
    html = utils_email._html_wrapper('<p>Hello</p>', 'Test')
    assert utils_email.LOGO_CID in html and '/static/snpsu-logo.png' not in html
    assert utils_email._send_via_gmail('someone@example.com', 'Hi', html)
    msg = email.message_from_bytes(_FakeSMTP.sent[0].as_bytes())
    parts = list(msg.walk())
    logo = [p for p in parts if p.get('Content-ID') == '<snpsu-logo>']
    assert logo and logo[0].get_content_type() == 'image/png' and logo[0].get_payload(decode=True)[:4] == b'\x89PNG'
    assert any(p.get_content_type() == 'multipart/related' for p in parts)
    assert _FakeSMTP.auth_seen == ['PLAIN']      # no AUTH LOGIN retry that hides Gmail's reason


def test_brevo_gets_a_public_logo_address(monkeypatch, real_app):
    import urllib.request
    import utils_email
    monkeypatch.setenv('BREVO_API_KEY', 'xkeysib-test')
    monkeypatch.setenv('MAIL_FROM', 'SapthaEvent <portal@example.com>')
    monkeypatch.setenv('COLLEGE_LOGO_URL', 'https://cdn.example.edu/logo.png')
    captured = {}

    class _Resp:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        captured['payload'] = json.loads(req.data)
        return _Resp()
    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    html = utils_email._html_wrapper('<p>Hello</p>', 'Test')
    assert utils_email._send_via_brevo('someone@example.com', 'Hi', html)
    body = captured['payload']['htmlContent']
    assert 'https://cdn.example.edu/logo.png' in body and 'cid:' not in body
