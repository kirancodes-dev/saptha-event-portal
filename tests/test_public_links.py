"""
tests/test_public_links.py — BLK-16: every link that leaves the app (emails,
QR codes, referrals) is built from BASE_URL, never from the request's host,
which a client can forge with Host or X-Forwarded-Host.

Each request below is sent to a forged host (evil.example) with a forged
X-Forwarded-Host (attacker.example); neither may appear in any link.
"""
import ast
import datetime
import os
import re
import subprocess

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user
from tests.test_registration_no_auto_login import _form, _spoc_event

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'https://events.example.edu'
FORGED = {'base_url': 'http://evil.example', 'headers': {'X-Forwarded-Host': 'attacker.example'}}


@pytest.fixture
def public_app(real_app, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setitem(flask_app.config, 'BASE_URL', BASE)
    return flask_app, db


@pytest.fixture
def mails(real_app, monkeypatch):
    """Every email the app sends (utils_email._send), as {'to', 'html'}."""
    import utils_email
    sent = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: sent.append({'to': to, 'html': html}) or True)
    return sent


def _clean(text):
    assert 'evil.example' not in text and 'attacker.example' not in text, text[:500]


def _on_forged_host(client):
    """The test client sends cookies by host, so copy the session to the forged
    host; the request then carries the forged Host and the user's session."""
    sid = client.get_cookie('session').value
    client.set_cookie('session', sid, domain='evil.example')
    return client


def _links(html, path):
    return re.findall(r'https?://[^"\'\s<>]+' + re.escape(path) + r'[^"\'\s<>]*', html)


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_password_reset_email_links_to_base_url_whatever_the_host(public_app, mails):
    flask_app, db = public_app
    student = f"{_unique('reset')}@test.edu"
    _user(db, student, 'Student')

    resp = flask_app.test_client().post('/forgot_password', data={'email': student}, **FORGED)
    assert resp.status_code == 302

    mails = [m for m in mails if m['to'] == student]
    assert len(mails) == 1
    links = _links(mails[0]['html'], '/reset_token/')
    assert links and all(link.startswith(f'{BASE}/reset_token/') for link in links)
    _clean(mails[0]['html'])


def test_set_password_email_on_registration_links_to_base_url(public_app, mails):
    flask_app, db = public_app
    event_id = _spoc_event(flask_app, db)
    newcomer = f"{_unique('newcomer')}@test.edu"

    resp = flask_app.test_client().post(f'/forms/submit/{event_id}', data=_form(newcomer), **FORGED)
    assert resp.status_code == 302

    mails = [m for m in mails if m['to'] == newcomer]
    assert mails
    links = [link for m in mails for link in _links(m['html'], '/set_password/')]
    assert links and all(link.startswith(f'{BASE}/set_password/') for link in links)
    for m in mails:
        _clean(m['html'])


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def _today_event_with_student(flask_app, db):
    spoc = f"{_unique('qrspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    spoc_client = _login(flask_app, spoc, 'ClubSPOC')
    today = datetime.date.today().isoformat()
    event_id = _create_event(spoc_client, db, _unique('QR Event'), today, team=False)
    student = f"{_unique('qrstu')}@test.edu"
    _user(db, student, 'Student')
    student_client = _login(flask_app, student, 'Student')
    assert student_client.post(f'/forms/submit/{event_id}', data=_form(student)).status_code == 302
    reg_id = next(d.id for d in db.collection('registrations').where('event_id', '==', event_id).stream())
    return spoc_client, student_client, event_id, reg_id


def test_qr_codes_and_referral_links_use_base_url(public_app, mails, monkeypatch):
    flask_app, db = public_app
    import qrcode

    import routes_ticket
    encoded = []

    class _Image:
        def save(self, buf, format=None):
            buf.write(b'png')

    monkeypatch.setattr(routes_ticket, 'generate_qr_base64', lambda data, *a, **k: encoded.append(data) or 'x')
    monkeypatch.setattr(routes_ticket, 'generate_qr_response', lambda data, *a, **k: encoded.append(data) or ('', 200))
    monkeypatch.setattr(qrcode, 'make', lambda data, *a, **k: encoded.append(data) or _Image())

    spoc_client, student_client, event_id, reg_id = _today_event_with_student(flask_app, db)
    _on_forged_host(spoc_client)
    _on_forged_host(student_client)

    assert student_client.get(f'/ticket/{reg_id}', **FORGED).status_code == 200      # ticket page QR
    assert student_client.get(f'/ticket/qr/{reg_id}', **FORGED).status_code == 200   # QR image
    assert spoc_client.get(f'/checkin/venue_qr/{event_id}', **FORGED).status_code == 200
    assert len(encoded) == 3
    assert encoded[0].startswith(f'{BASE}/ticket/verify/') and encoded[1].startswith(f'{BASE}/ticket/verify/')
    assert encoded[2].startswith(f'{BASE}/checkin/{event_id}?code=')

    referral = student_client.get('/participant/referrals/api/stats', **FORGED).get_json()
    assert referral['referral_link'].startswith(f'{BASE}/register?ref=')

    from utils_email import _base_url
    with flask_app.test_request_context('/', **FORGED):
        assert _base_url() == BASE
    _clean(' '.join(encoded) + referral['referral_link'])


# ── Criterion 3 ─────────────────────────────────────────────────────────────

STRONG = {'FLASK_ENV': 'production', 'SECRET_KEY': 'x' * 64, 'MASTER_SECRET_KEY': 'a-long-master-key'}


@pytest.mark.parametrize('base_url', ['', 'http://events.example.edu', 'https://localhost',
                                      'https://127.0.0.1:5000', 'events.example.edu'])
def test_production_refuses_a_missing_or_unsafe_base_url(base_url):
    from config import validate_production_config
    with pytest.raises(RuntimeError) as refused:
        validate_production_config(dict(STRONG, BASE_URL=base_url))
    assert 'BASE_URL' in str(refused.value)

    # Reported in the same single error as the other problems
    with pytest.raises(RuntimeError) as both:
        validate_production_config(dict(STRONG, SECRET_KEY='', BASE_URL=base_url))
    assert 'BASE_URL' in str(both.value) and 'SECRET_KEY' in str(both.value)


def test_production_starts_with_an_https_base_url():
    from config import validate_production_config
    validate_production_config(dict(STRONG, BASE_URL='https://events.example.edu'))
    validate_production_config({'FLASK_ENV': 'development'})  # development needs none


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_proxy_fix_trusts_one_hop_of_for_and_proto_only(public_app, monkeypatch):
    from werkzeug.middleware.proxy_fix import ProxyFix
    flask_app, _ = public_app
    proxy = flask_app.wsgi_app
    assert isinstance(proxy, ProxyFix)
    assert (proxy.x_for, proxy.x_proto, proxy.x_host, proxy.x_port, proxy.x_prefix) == (1, 1, 0, 0, 0)

    seen = {}

    def inner(environ, start_response):
        seen.update(environ)
        start_response('200 OK', [])
        return [b'']
    monkeypatch.setattr(proxy, 'app', inner)
    proxy({'REQUEST_METHOD': 'GET', 'PATH_INFO': '/', 'SERVER_NAME': 'site.example', 'SERVER_PORT': '443',
           'wsgi.url_scheme': 'http', 'REMOTE_ADDR': '10.0.0.1', 'HTTP_HOST': 'site.example',
           'HTTP_X_FORWARDED_HOST': 'attacker.example', 'HTTP_X_FORWARDED_PREFIX': '/evil',
           'HTTP_X_FORWARDED_FOR': '203.0.113.9', 'HTTP_X_FORWARDED_PROTO': 'https'},
          lambda *a: None)
    assert seen['HTTP_HOST'] == 'site.example'          # X-Forwarded-Host ignored
    assert seen.get('SCRIPT_NAME', '') == ''            # X-Forwarded-Prefix ignored
    assert seen['REMOTE_ADDR'] == '203.0.113.9'         # client IP for the login throttle
    assert seen['wsgi.url_scheme'] == 'https'


# ── Criterion 5 ─────────────────────────────────────────────────────────────

ALLOWED_HOST_USES = {
    'app.py',                    # same-site check on the referrer before redirecting back
    'routes_payment_stripe.py',  # the caller's own Stripe redirect URLs (removed by UPG-14)
    'middleware_tenant.py',      # tenant lookup by domain (multi-tenancy is off), not a link
}


def _app_modules():
    out = subprocess.run(['git', 'ls-files', '*.py'], cwd=ROOT, capture_output=True, text=True, check=True)
    skip = ('functions/', 'scratch/', 'tests/', 'migrations/')
    return [f for f in out.stdout.split() if not f.startswith(skip) and f != 'generate_project_report.py']


def test_no_app_module_builds_links_from_the_request_host():
    offenders = []
    for path in _app_modules():
        try:
            tree = ast.parse(open(os.path.join(ROOT, path), encoding='utf-8').read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr in ('host_url', 'url_root', 'host')
                    and isinstance(node.value, ast.Name) and node.value.id == 'request'
                    and path not in ALLOWED_HOST_USES):
                offenders.append(f'{path}:{node.lineno} request.{node.attr}')
    assert offenders == []


def test_outbound_message_modules_hold_no_hard_coded_deploy_url():
    for path in ('utils_email.py', 'utils_whatsapp.py', 'routes_ticket.py'):
        source = open(os.path.join(ROOT, path), encoding='utf-8').read()
        assert not re.search(r'https?://[\w.-]+\.(run\.app|railway\.app|onrender\.com)', source), path
