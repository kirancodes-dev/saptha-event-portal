"""
tests/test_notices.py — UPG-31 on the real database layer: the
registration confirmation, the day-before ticket (through the cron
endpoint), and the change and cancellation notices go out through Brevo's
HTTP API once each, and with no mail keys nothing leaves the machine.
"""
import base64
import datetime
import json
import socket
import urllib.request

import pytest

import routes_forms
import utils_email
import utils_whatsapp
from tests.test_integration_flow import _create_event, _login, _unique, _user

REAL_SEND = utils_email._send                      # real_app replaces it with a stub
REAL_CONFIRM = utils_email.send_registration_confirmed_email
REAL_WA_SEND = utils_whatsapp._send
CRON = 'cron-secret-for-pytest'
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
LOCAL = ('127.0.0.1', '::1', 'localhost')


@pytest.fixture
def offline(monkeypatch):
    """Any connection or name lookup beyond this machine is recorded and refused."""
    attempts = []
    real_connect, real_lookup = socket.socket.connect, socket.getaddrinfo

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in LOCAL:
            attempts.append(address)
            raise OSError('network blocked in tests')
        return real_connect(sock, address)

    def lookup(host, *args, **kwargs):
        if host not in LOCAL and host is not None:
            attempts.append(host)
            raise OSError('network blocked in tests')
        return real_lookup(host, *args, **kwargs)
    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket, 'getaddrinfo', lookup)
    return attempts


@pytest.fixture
def site(real_app, offline, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setattr(utils_email, '_send', REAL_SEND)
    monkeypatch.setattr(routes_forms, 'send_registration_confirmed_email', REAL_CONFIRM)
    monkeypatch.setenv('CRON_SECRET', CRON)
    spoc = f"{_unique('notespoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')

    def event(date, status='registration_open'):
        title = _unique('Notice Night')
        event_id = _create_event(owner, db, title, date, team=False)
        db.collection('events').document(event_id).update({'status': status, 'venue': 'Hall A'})
        return event_id, title

    def register(event_id, who, phone='9876543210'):
        email = f"{_unique(who)}@test.edu"
        resp = flask_app.test_client().post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes',
            'full_name': who.title(), 'email': email, 'phone': phone, 'usn': '1SN20CS042'})
        assert resp.status_code == 302
        [reg] = [d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream()
                 if (d.to_dict() or {}).get('lead_email') == email]
        return email, reg['reg_id']
    return {'app': flask_app, 'db': db, 'owner': owner, 'event': event, 'register': register}


@pytest.fixture
def brevo(site, monkeypatch):
    """Brevo configured; its HTTP API answers 201 and records each message."""
    monkeypatch.setenv('BREVO_API_KEY', 'test-brevo-key')
    monkeypatch.setenv('MAIL_FROM', 'SapthaEvent <events@test.edu>')
    sent = []

    class Created:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(req, timeout=None):
        assert req.full_url == 'https://api.brevo.com/v3/smtp/email'
        assert req.headers['Api-key'] == 'test-brevo-key'
        sent.append(json.loads(req.data))
        return Created()
    monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
    return sent


def _to(sent, email, subject_start=''):
    return [m for m in sent if [t['email'] for t in m['to']] == [email] and m['subject'].startswith(subject_start)]


def _day(offset):
    return (datetime.datetime.now(IST).date() + datetime.timedelta(days=offset)).isoformat()


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_a_registration_sends_one_confirmation_through_brevo(site, brevo):
    d = site
    event_id, title = d['event'](_day(10))
    email, _ = d['register'](event_id, 'rhea')
    [mail] = _to(brevo, email, 'Registration Confirmed')
    assert mail['subject'] == f'Registration Confirmed — {title}'
    assert mail['sender'] == {'name': 'SapthaEvent', 'email': 'events@test.edu'}
    assert title in mail['htmlContent'] and _day(10) in mail['htmlContent'] and 'Hall A' in mail['htmlContent']
    assert [a['name'] for a in mail['attachment']] == ['invite.ics']

    # Registering again is refused, and sends nothing more
    d['app'].test_client().post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes',
        'full_name': 'Rhea', 'email': email, 'phone': '9876543210', 'usn': '1SN20CS042'})
    assert len(_to(brevo, email, 'Registration Confirmed')) == 1


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_day_before_ticket_goes_out_once_with_the_entry_qr(site, brevo, monkeypatch):
    d = site
    whatsapps = []
    monkeypatch.setattr(utils_whatsapp, '_send', lambda phone, body: whatsapps.append((phone, body)) or True)
    event_id, title = d['event'](_day(1), status='active')        # the reminder reads `active` only (UPG-43)
    people = [d['register'](event_id, who) for who in ('ana', 'ben')]
    brevo.clear()

    cron = d['app'].test_client()
    for _ in range(2):
        resp = cron.post('/internal/cron/reminders', headers={'X-Cron-Secret': CRON})
        assert resp.status_code == 200

    from tasks.email_tasks import ticket_qr_png
    for email, reg_id in people:
        [ticket] = _to(brevo, email)
        assert ticket['subject'] == f'✅ Registered — {title}' and reg_id in ticket['htmlContent']
        qr = next(a for a in ticket['attachment'] if a['name'] == 'QR_Ticket.png')
        with d['app'].app_context():
            assert base64.b64decode(qr['content']) == ticket_qr_png(reg_id)   # the signed token the scanners accept
    assert len(whatsapps) == 2 and all('Tomorrow' in body for _, body in whatsapps)


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_a_venue_change_and_a_cancellation_each_notify_every_registrant_once(site, brevo):
    d = site
    event_id, title = d['event'](_day(10))
    people = [d['register'](event_id, who)[0] for who in ('cara', 'dev')]
    gone, gone_id = d['register'](event_id, 'gone')
    d['db'].collection('registrations').document(gone_id).update({'status': 'cancelled'})
    brevo.clear()

    edit = {'venue': 'Hall B', 'title': title}
    for _ in range(2):                                               # saving the same change twice
        assert d['owner'].post(f'/spoc/edit_event/{event_id}', data=edit).status_code == 302
    for email in people:
        [notice] = _to(brevo, email)
        assert notice['subject'] == f'Update: {title}' and 'Hall B' in notice['htmlContent']
    assert _to(brevo, gone) == []

    # A coordinator-side edit of the date notifies too
    brevo.clear()
    d['owner'].post(f'/coordinator/edit_event/{event_id}', data={
        'title': title, 'date': _day(12), 'venue': 'Hall B', 'overview': 'desc'})
    assert sorted(m['to'][0]['email'] for m in brevo) == sorted(people)
    assert all(_day(12) in m['htmlContent'] for m in brevo)

    brevo.clear()
    for target in ('cancelled', 'cancelled', 'draft', 'cancelled'):  # cancelled again after a restore
        d['owner'].post(f'/spoc/event/{event_id}/transition', data={'target_state': target})
    for email in people:
        [notice] = _to(brevo, email)
        assert notice['subject'] == f'Cancelled: {title}'
    assert _to(brevo, gone) == []


def test_notices_escape_what_people_type(site, brevo):
    utils_email.send_email_notification('x@test.edu', 'Update', '<b>Hi</b> & <script>alert(1)</script>')
    [mail] = brevo
    assert '<script>' not in mail['htmlContent'] and '&lt;b&gt;Hi&lt;/b&gt; &amp;' in mail['htmlContent']


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_with_no_mail_keys_nothing_leaves_the_machine(site, offline, monkeypatch):
    d = site
    monkeypatch.setattr(utils_whatsapp, '_send', REAL_WA_SEND)
    opened = []
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: opened.append(a) or pytest.fail('urlopen called'))
    assert utils_email.mail_provider() == ''

    event_id, _ = d['event'](_day(1), status='active')
    email, reg_id = d['register'](event_id, 'quiet')
    d['app'].test_client().post('/internal/cron/reminders', headers={'X-Cron-Secret': CRON})
    d['owner'].post(f'/spoc/edit_event/{event_id}', data={'venue': 'Hall Z'})
    d['owner'].post(f'/spoc/event/{event_id}/transition', data={'target_state': 'cancelled'})
    assert REAL_SEND(email, 'Hello', '<p>hi</p>') is False
    assert utils_whatsapp.send_event_reminder_whatsapp('9876543210', 'Q', 'T', reg_id=reg_id) is False
    assert offline == [] and opened == []
