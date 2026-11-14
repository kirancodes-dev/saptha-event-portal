"""
tests/test_low_email_auth.py — UPG-152, the low-email registration and login
flow, on the real database layer with a mail provider configured (Brevo's
sender replaced, so nothing leaves the machine):

  * a registration sends one email, to the team lead only; a new account's
    email carries a one-time set-password link that lasts 48 hours;
  * no password is ever emailed; the participant logs in with the registered
    email and the password they chose, stored as a strong hash;
  * an account made by a registration may email itself one reset link in its
    first 48 hours (one-time, 15 minutes); after that, or once it's used, the
    organizer-contact message;
  * a daily email limit counts every email together and, once reached, sends
    nothing and shows the organizer-contact message;
  * emails' status, expiry and reset outcomes are logged and shown to the
    organizer, never a password or a token; the organizer can send a new link.
"""
import datetime
import logging
import re
import time

import pytest
from werkzeug.security import check_password_hash

import routes_forms
import services_email_quota as quota
import utils_email
from services_accounts import ORGANIZER_MESSAGE, REGISTERED_AT
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

REAL_SEND = utils_email._send                      # real_app replaces it with a stub
REAL_CONFIRM = utils_email.send_registration_confirmed_email
NEW_PASSWORD = 'Chosen-pass-2026'


@pytest.fixture
def low(real_app, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setattr(utils_email, '_send', REAL_SEND)
    monkeypatch.setattr(routes_forms, 'send_registration_confirmed_email', REAL_CONFIRM)
    monkeypatch.setenv('BREVO_API_KEY', 'test-brevo-key')
    monkeypatch.setenv('MAIL_FROM', 'SapthaEvent <events@test.edu>')
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 450)
    sent, provider = [], {'ok': True}

    def brevo(to, subject, html, attachments=None):
        if provider['ok']:
            sent.append({'to': to, 'subject': subject, 'html': html})
        return provider['ok']
    monkeypatch.setattr(utils_email, '_send_via_brevo', brevo)

    spoc = f"{_unique('lowspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()

    def event(team=True):
        title = _unique('Low Mail Hack')
        event_id = _create_event(owner, db, title, day, team=team)
        db.collection('events').document(event_id).update({'status': 'registration_open', 'venue': 'Hall A'})
        return event_id, title

    def register(event_id, lead=None, mates=(), client=None):
        lead = lead or f"{_unique('lead')}@test.edu"
        form = {'privacy_consent': 'yes', 'full_name': 'Lena Lead', 'email': lead, 'phone': '9876543210',
                'usn': '1SN22CS200', 'team_name': 'Quiet Inbox'}
        for i, email in enumerate(mates, start=1):
            form.update({f'member_{i}_name': f'Mate {i}', f'member_{i}_email': email,
                         f'member_{i}_usn': f'1SN22CS20{i}'})
        client = client or flask_app.test_client()
        resp = client.post(f'/forms/submit/{event_id}', data=form)
        assert resp.status_code == 302, resp.data[:300]
        return lead, client

    def mates(n=2):
        return [f"{_unique(f'mate{i}')}@test.edu" for i in range(1, n + 1)]

    return {'app': flask_app, 'db': db, 'owner': owner, 'spoc': spoc, 'event': event, 'register': register,
            'mates': mates, 'sent': sent, 'provider': provider}


def _to(sent, email):
    return [m for m in sent if m['to'] == email]


def _links(mail, path):
    return re.findall(r'href="https?://[^/"]+(/' + path + r'/[^"]+)"', mail['html'])


def _user_doc(db, email):
    return db.collection('users').document(email).get().to_dict() or {}


def _flashes(client):
    with client.session_transaction() as sess:
        return [m for _, m in sess.get('_flashes', [])]


def _page(client, path):
    return client.get(path, follow_redirects=True).get_data(as_text=True)


def _token_made_ago(flask_app, monkeypatch, make, seconds):
    import itsdangerous.timed
    then = int(time.time()) - seconds
    with flask_app.app_context(), monkeypatch.context() as m:
        m.setattr(itsdangerous.timed.TimestampSigner, 'get_timestamp', lambda self: then)
        return make()


# ── Criteria 1 and 2: one email, to the lead, with the set-password link ──────

def test_a_new_team_registration_sends_one_email_to_the_lead_only(low):
    event_id, title = low['event']()
    # With member confirmation off (UPG-207 is on by default; its emails are
    # tested in tests/test_team_member_confirm.py) only the lead is emailed
    low['db'].collection('events').document(event_id).update({'member_confirm': False})
    mates = low['mates']()
    lead, client = low['register'](event_id, mates=mates)

    assert [m['to'] for m in low['sent']] == [lead]               # one email, the lead's
    [mail] = low['sent']
    assert mail['subject'] == f'Registration Confirmed — {title}'
    assert len(_links(mail, 'set_password')) == 1
    assert 'works once' in mail['html'] and '48 hours' in mail['html']
    assert title in mail['html'] and 'Quiet Inbox' in mail['html']
    assert 'Password</td>' not in mail['html'] and PASSWORD not in mail['html']   # no credentials
    for mate in mates:
        assert _to(low['sent'], mate) == []
        assert not low['db'].collection('users').document(mate).get().exists   # members get no account
    with low['app'].app_context():
        assert quota.sent_today() == 1

    page = _page(client, '/registration/confirmed')
    assert 'expires in 48 hours' in page and lead in page


def test_an_existing_account_gets_one_confirmation_and_no_login_link(low):
    event_id, title = low['event'](team=False)
    student = f"{_unique('known')}@test.edu"
    _user(low['db'], student, 'Student')
    low['register'](event_id, lead=student)
    [mail] = low['sent']
    assert mail['to'] == student and mail['subject'] == f'Registration Confirmed — {title}'
    assert _links(mail, 'set_password') == [] and '/forms/cancel/' in mail['html']


def test_team_members_get_emails_only_when_the_owner_turns_it_on(low, monkeypatch):
    from services_recipients import registration_people
    reg = {'lead_email': 'lead@test.edu', 'lead_name': 'Lead',
           'members': [{'email': 'lead@test.edu'}, {'email': 'm1@test.edu', 'name': 'One'}]}
    with low['app'].app_context():
        assert [p[0] for p in registration_people(reg)] == ['lead@test.edu']
        assert [p[0] for p in registration_people(reg, everyone=True)] == ['lead@test.edu', 'm1@test.edu']

    monkeypatch.setitem(low['app'].config, 'NOTIFY_TEAM_MEMBERS', True)
    event_id, _ = low['event']()
    low['db'].collection('events').document(event_id).update({'member_confirm': False})   # UPG-207 off
    mates = low['mates']()
    lead, _ = low['register'](event_id, mates=mates)
    assert sorted(m['to'] for m in low['sent']) == sorted([lead] + mates)


# ── Criteria 3 and 4: the set-password link, then logging in ───────────────────

def test_the_set_password_link_lasts_48_hours_works_once_and_then_login_works(low, monkeypatch):
    import services_accounts
    flask_app, db = low['app'], low['db']
    event_id, _ = low['event'](team=False)
    lead, _ = low['register'](event_id)
    stored = _user_doc(db, lead)
    assert stored[REGISTERED_AT] and stored['login_link']['status'] == 'sent'

    def made(hours):
        return _token_made_ago(flask_app, monkeypatch,
                               lambda: services_accounts.make_set_password_token(lead, stored['password']), hours * 3600)
    assert flask_app.test_client().get(f'/set_password/{made(47)}').status_code == 200
    late = flask_app.test_client()
    resp = late.get(f'/set_password/{made(49)}')
    assert resp.headers['Location'] == '/forgot_password'
    assert any('48 hours' in m for m in _flashes(late))

    [link] = _links(low['sent'][0], 'set_password')
    visitor = flask_app.test_client()
    done = visitor.post(link, data={'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert done.status_code == 302
    assert any('Password set' in m and lead in m for m in _flashes(visitor))
    user = _user_doc(db, lead)
    assert user['password'].startswith(('scrypt:', 'pbkdf2:')) and NEW_PASSWORD not in str(user)
    assert check_password_hash(user['password'], NEW_PASSWORD)

    again = flask_app.test_client()
    assert again.get(link).headers['Location'] == '/login'                  # works once
    assert any('already been used' in m for m in _flashes(again))

    fresh = flask_app.test_client()
    wrong = fresh.post('/login', data={'role': 'Student', 'email': lead, 'password': 'not-it-at-all'})
    assert wrong.headers['Location'] == '/login'
    assert 'Email or password is incorrect.' in _flashes(fresh)
    ok = fresh.post('/login', data={'role': 'Student', 'email': lead, 'password': NEW_PASSWORD})
    assert ok.status_code == 302 and ok.headers['Location'] == '/participant/dashboard'


# ── Criteria 5 and 6: one reset in the first 48 hours, 15 minutes, once ───────

def test_one_reset_email_in_the_first_48_hours_then_the_organizer_message(low, monkeypatch):
    # UPG-260: the limit is off by default now (an account always gets its
    # link); this checks it still works when PARTICIPANT_RESET_LIMIT is set
    monkeypatch.setitem(low['app'].config, 'PARTICIPANT_RESET_LIMIT', 1)
    db = low['db']
    event_id, _ = low['event'](team=False)
    lead, _ = low['register'](event_id)
    low['sent'].clear()

    first = low['app'].test_client()
    first.post('/forgot_password', data={'email': lead})
    [mail] = low['sent']
    assert mail['to'] == lead and 'Reset your SapthaEvent password' in mail['subject']
    assert len(_links(mail, 'reset_token')) == 1 and '15 minutes' in mail['html'] and 'works once' in mail['html']
    assert "If an account exists for this email, we've sent a reset link." in _flashes(first)

    second = low['app'].test_client()
    page = second.post('/forgot_password', data={'email': lead}, follow_redirects=True).get_data(as_text=True)
    assert ORGANIZER_MESSAGE in page
    assert len(low['sent']) == 1                                     # nothing more sent
    user = _user_doc(db, lead)
    assert user['reset_requests'] == 1 and user['reset_last']['status'] == 'refused_used'

    # A registration account more than 48 hours old: the organizer message, no email
    other, _ = low['register'](low['event'](team=False)[0])
    long_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=49)).isoformat()
    db.collection('users').document(other).update({REGISTERED_AT: long_ago})
    low['sent'].clear()
    page = low['app'].test_client().post('/forgot_password', data={'email': other},
                                         follow_redirects=True).get_data(as_text=True)
    assert ORGANIZER_MESSAGE in page and low['sent'] == []
    assert _user_doc(db, other)['reset_last']['status'] == 'refused_window'

    # Staff and accounts made before UPG-152 keep the usual reset
    staff = f"{_unique('staffer')}@test.edu"
    _user(db, staff, 'EventCoordinator')
    for _ in range(2):
        low['app'].test_client().post('/forgot_password', data={'email': staff})
    assert len(_to(low['sent'], staff)) == 2


def test_the_reset_link_lasts_15_minutes_and_works_once(low, monkeypatch):
    import services_accounts
    flask_app, db = low['app'], low['db']
    student = f"{_unique('resetter')}@test.edu"
    _user(db, student, 'Student')
    stored = _user_doc(db, student)['password']

    def made(minutes):
        return _token_made_ago(flask_app, monkeypatch,
                               lambda: services_accounts.make_reset_token(student, stored), minutes * 60)
    assert flask_app.test_client().get(f'/reset_token/{made(14)}').status_code == 200
    late = flask_app.test_client()
    assert late.get(f'/reset_token/{made(16)}').headers['Location'] == '/forgot_password'
    assert any('15 minutes' in m for m in _flashes(late))

    flask_app.test_client().post('/forgot_password', data={'email': student})
    [link] = _links(_to(low['sent'], student)[0], 'reset_token')
    client = flask_app.test_client()
    resp = client.post(link, data={'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert resp.headers['Location'] == '/login'
    assert any('Password updated' in m for m in _flashes(client))
    again = flask_app.test_client()
    assert again.get(link).headers['Location'] == '/forgot_password'
    assert any('already been used' in m for m in _flashes(again))


# ── Criteria 7 and 8: the daily email limit ────────────────────────────────────

def test_the_daily_limit_counts_every_email_together_then_sends_nothing(low, monkeypatch):
    flask_app, db = low['app'], low['db']
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 2)
    event_id, _ = low['event'](team=False)
    first, _ = low['register'](event_id)                                 # email 1: registration
    flask_app.test_client().post('/forgot_password', data={'email': first})   # email 2: a reset
    assert [m['to'] for m in low['sent']] == [first, first]
    with flask_app.app_context():
        assert quota.sent_today() == 2 and not quota.available()

    # At the limit: the registration is kept, nothing is sent, the visitor is told
    second, client = low['register'](event_id)
    assert len(low['sent']) == 2
    assert [d.to_dict()['lead_email'] for d in db.collection('registrations').where('event_id', '==', event_id)
            .stream() if d.to_dict()['lead_email'] == second] == [second]
    assert _user_doc(db, second)['login_link']['status'] == 'limit'
    assert "could not send your password-setup email" in ' '.join(_flashes(client))
    page = _page(client, '/registration/confirmed')
    assert 'We could not send your password-setup email. Please contact the hackathon organizer' in page

    # Password reset: the organizer message, the same for a known and an unknown email
    for email in (first, f"{_unique('nobody')}@test.edu"):
        page = flask_app.test_client().post('/forgot_password', data={'email': email},
                                            follow_redirects=True).get_data(as_text=True)
        assert ORGANIZER_MESSAGE in page
    assert len(low['sent']) == 2

    # A new UTC day starts from zero
    monkeypatch.setattr(quota, 'today', lambda: '2999-01-01')
    with flask_app.app_context():
        assert quota.available()


def test_the_counter_is_atomic_and_gives_back_refused_emails(low, monkeypatch):
    flask_app = low['app']
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 3)
    with flask_app.app_context():
        assert quota.reserve(2) and not quota.reserve(2) and quota.reserve(1)
        assert quota.sent_today() == 3
        quota.release(3)
        low['provider']['ok'] = False                                     # the provider refuses
        assert utils_email._send(['a@test.edu', 'b@test.edu'], 'Hi', '<p>x</p>') is False
        assert quota.sent_today() == 0
        low['provider']['ok'] = True
        assert utils_email._send(['a@test.edu', 'b@test.edu'], 'Hi', '<p>x</p>') is True
        assert quota.sent_today() == 2                                    # one per recipient
        monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 0)     # 0: no limit
        assert quota.available(10_000) and quota.reserve(10_000)


# ── Criterion 9: logged for troubleshooting, never a password or token ─────────

def test_status_and_expiry_are_logged_never_a_password_or_token(low, caplog, monkeypatch):
    flask_app, db = low['app'], low['db']
    # UPG-260: the reset limit is off by default now; set it, so the refusal
    # this test checks is still logged without a secret
    monkeypatch.setitem(flask_app.config, 'PARTICIPANT_RESET_LIMIT', 1)
    caplog.set_level(logging.DEBUG)
    event_id, _ = low['event'](team=False)
    lead, _ = low['register'](event_id)
    [set_link] = _links(low['sent'][0], 'set_password')
    flask_app.test_client().post(set_link, data={'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    flask_app.test_client().post('/forgot_password', data={'email': lead})
    [reset_link] = _links(low['sent'][-1], 'reset_token')
    flask_app.test_client().post(reset_link, data={'new_password': NEW_PASSWORD + 'x',
                                                   'confirm_password': NEW_PASSWORD + 'x'})
    flask_app.test_client().post('/forgot_password', data={'email': lead})   # refused: already used

    audit = [f"{e.get('action')} {e.get('details')}" for e in
             (d.to_dict() for d in db.collection('audit_log').stream()) if lead in str(e.get('details'))]
    logs = caplog.text + '\n'.join(audit) + str(_user_doc(db, lead).get('login_link'))
    for secret in (NEW_PASSWORD, set_link.rsplit('/', 1)[1], reset_link.rsplit('/', 1)[1]):
        assert secret not in logs
    assert any(a.startswith('LOGIN_LINK_EMAIL set_password link') and 'sent, expires' in a for a in audit)
    assert any(a.startswith('LOGIN_LINK_EMAIL reset link') and 'sent, expires' in a for a in audit)
    assert any(a.startswith('RESET_REQ_REFUSED') and 'already used' in a for a in audit)


# ── Criterion 10: the organizer sees it and can send a new link ────────────────

def test_the_organizer_sees_the_login_email_and_can_send_a_new_link(low, monkeypatch):
    flask_app, db = low['app'], low['db']
    event_id, _ = low['event'](team=False)
    lead, _ = low['register'](event_id)
    [reg] = [d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream()]
    owner = low['owner']

    page = owner.get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert 'Link sent, expires' in page and 'Send password link' in page
    low['sent'].clear()
    owner.post(f'/coordinator/registrations/{event_id}/login_link', data={'reg_id': reg['reg_id']})
    [mail] = low['sent']
    assert mail['to'] == lead and len(_links(mail, 'set_password')) == 1
    assert _user_doc(db, lead)['login_link']['by'] == low['spoc']

    # Another SPOC can't, and a registration from another event is refused
    stranger = f"{_unique('otherspoc')}@test.edu"
    _user(db, stranger, 'ClubSPOC')
    assert _login(flask_app, stranger, 'ClubSPOC').post(
        f'/coordinator/registrations/{event_id}/login_link', data={'reg_id': reg['reg_id']}).status_code == 403
    other_event, _ = low['event'](team=False)
    owner.post(f'/coordinator/registrations/{other_event}/login_link', data={'reg_id': reg['reg_id']})
    assert len(low['sent']) == 1

    # At the daily limit the organizer is told, and nothing is sent
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 1)
    owner.post(f'/coordinator/registrations/{event_id}/login_link', data={'reg_id': reg['reg_id']})
    assert len(low['sent']) == 1 and any("email limit" in m for m in _flashes(owner))
    page = owner.get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert 'Email not sent: daily limit' in page


def test_link_tokens_are_redacted_in_request_and_access_logs():
    """The app's request log and gunicorn's access log never carry a link token."""
    import importlib.util
    import os
    from types import SimpleNamespace

    from log_redact import redact

    token = 'eyJlIjoiYUBiLmNvbSJ9.Zx1.AbC-d_e'
    for path in (f'/set_password/{token}', f'/reset_token/{token}', f'/forms/cancel/{token}'):
        assert token not in redact(f'GET {path}?next=/x HTTP/1.1')
        assert '[redacted]' in redact(path)
    assert redact('/forgot_password') == '/forgot_password'
    assert redact('') == '' and redact(None) is None

    spec = importlib.util.spec_from_file_location(
        'gunicorn_conf', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gunicorn.conf.py'))
    conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conf)
    from gunicorn.config import Config
    log = conf.logger_class(Config())
    environ = {'REQUEST_METHOD': 'POST', 'RAW_URI': f'/set_password/{token}', 'PATH_INFO': f'/set_password/{token}',
               'QUERY_STRING': '', 'SERVER_PROTOCOL': 'HTTP/1.1', 'REMOTE_ADDR': '1.2.3.4'}
    resp = SimpleNamespace(status='302 FOUND', response_length=0, sent=0, headers=[])
    req = SimpleNamespace(headers=[])
    atoms = log.atoms(resp, req, environ, datetime.timedelta(seconds=0.01))
    assert token not in atoms['r'] and token not in atoms['U']
    assert '/set_password/[redacted]' in atoms['r']
