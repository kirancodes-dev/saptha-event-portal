"""
tests/test_registration_no_auto_login.py — BLK-02 on the real SQL database
layer: registration, waitlist and payment completion never log anyone in.

  * an existing account must log in first (and comes back to the form);
  * a logged-in student always registers as their own account;
  * a new email gets an unverified account and a one-time set-password link;
  * no password is ever shown, stored in the session or emailed.
"""
import hashlib
import hmac
import re
import time

import pytest
from werkzeug.security import check_password_hash

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

NEW_PASSWORD = 'Brand-new-pass-42'


@pytest.fixture
def outbox(real_app, monkeypatch):
    """Capture every email (utils_email._send) and every confirmation call."""
    import routes_forms
    import routes_payment
    import utils_email

    sent = {'mail': [], 'confirmations': [], 'tasks': []}

    def fake_send(to, subject, html, *a, **k):
        sent['mail'].append({'to': to, 'subject': subject, 'html': html})
        return True

    class FakeTask:
        def __init__(self, name):
            self.name = name

        def delay(self, *a, **k):
            sent['tasks'].append((self.name, k))

    monkeypatch.setattr(utils_email, '_send', fake_send)
    monkeypatch.setattr(routes_forms, 'send_registration_confirmed_email',
                        lambda *a, **k: sent['confirmations'].append((a, k)))
    for name in ('send_ticket_email_task', 'send_ticket_whatsapp_task',
                 'send_payment_receipt_whatsapp_task'):
        monkeypatch.setattr(routes_payment, name, FakeTask(name))
    return sent


def _spoc_event(flask_app, db, fee=0):
    spoc = f"{_unique('spoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    return _create_event(client, db, _unique('Reg Event'), '2030-06-01', fee=fee, team=False)


def _form(email, name='New Student'):
    return {'full_name': name, 'email': email, 'phone': '9876543210', 'usn': '1SN20CS099'}


def _session(client):
    with client.session_transaction() as sess:
        return dict(sess)


def _regs(db, event_id):
    return [d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream()]


def _set_password_links(outbox, email):
    links = []
    for m in outbox['mail']:
        if m['to'] == email and 'Set your SapthaEvent password' in m['subject']:
            links += re.findall(r'href="https?://[^/"]+(/set_password/[^"]+)"', m['html'])
    return links


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_anonymous_submit_with_existing_email_must_log_in_first(real_app, outbox):
    flask_app, db = real_app
    event_id = _spoc_event(flask_app, db)
    student = f"{_unique('existing')}@test.edu"
    _user(db, student, 'Student')

    visitor = flask_app.test_client()
    resp = visitor.post(f'/forms/submit/{event_id}', data=_form(student))

    assert resp.status_code == 302
    assert resp.headers['Location'] == f'/login?next=/forms/register/{event_id}'
    assert 'user_id' not in _session(visitor)
    assert _regs(db, event_id) == []
    assert outbox['mail'] == []  # nothing is sent for someone else's account

    # After logging in, the student comes back to the form
    back = visitor.post('/login', data={'role': 'Student', 'email': student, 'password': PASSWORD,
                                        'next': f'/forms/register/{event_id}'})
    assert back.status_code == 302
    assert back.headers['Location'] == f'/forms/register/{event_id}'


def test_login_ignores_an_off_site_next(real_app):
    flask_app, db = real_app
    student = f"{_unique('nextstu')}@test.edu"
    _user(db, student, 'Student')
    for target in ('//evil.example/steal', 'https://evil.example/', '/\\evil.example'):
        client = flask_app.test_client()
        resp = client.post('/login', data={'role': 'Student', 'email': student,
                                           'password': PASSWORD, 'next': target})
        assert resp.status_code == 302
        assert 'evil.example' not in resp.headers['Location']


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_logged_in_student_registers_under_the_session_email(real_app, outbox):
    flask_app, db = real_app
    event_id = _spoc_event(flask_app, db)
    student = f"{_unique('me')}@test.edu"
    other = f"{_unique('someone-else')}@test.edu"
    _user(db, student, 'Student')
    client = _login(flask_app, student, 'Student')

    resp = client.post(f'/forms/submit/{event_id}', data=_form(other, name='Me Myself'))

    assert resp.status_code == 302
    regs = _regs(db, event_id)
    assert len(regs) == 1
    assert regs[0]['lead_email'] == student
    assert regs[0]['form_answers']['email'] == student
    assert not db.collection('users').document(other).get().exists
    assert _session(client)['user_id'] == student
    assert outbox['mail'] == []  # no account was created, so no link


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_waitlist_branch_never_logs_in(real_app, outbox):
    flask_app, db = real_app
    event_id = _spoc_event(flask_app, db)
    db.collection('events').document(event_id).update(
        {'limits': {'max_participants': 1}, 'capacity': 1, 'registration_count': 1})
    email = f"{_unique('waiter')}@test.edu"

    visitor = flask_app.test_client()
    resp = visitor.post(f'/forms/submit/{event_id}', data=_form(email))

    assert resp.status_code == 302
    assert resp.headers['Location'] == f'/event/{event_id}'
    assert 'user_id' not in _session(visitor)
    waiting = list(db.collection('waitlists').where('event_id', '==', event_id).stream())
    assert [w.to_dict()['email'] for w in waiting] == [email]
    assert _regs(db, event_id) == []
    assert len(_set_password_links(outbox, email)) == 1


def test_simulated_payment_completion_never_logs_in(real_app, outbox, monkeypatch):
    monkeypatch.setenv('PAYMENT_SIMULATION', 'true')
    flask_app, db = real_app
    event_id = _spoc_event(flask_app, db, fee=250)
    email = f"{_unique('simpay')}@test.edu"

    visitor = flask_app.test_client()
    assert visitor.post(f'/forms/submit/{event_id}', data=_form(email)).headers['Location'] \
        == f'/payment/checkout/{event_id}'
    resp = visitor.post('/payment/process', data={'event_id': event_id, 'amount': '250'})

    assert resp.status_code == 302
    assert resp.headers['Location'] == '/registration/confirmed'
    assert 'user_id' not in _session(visitor)
    assert [r['lead_email'] for r in _regs(db, event_id)] == [email]


def test_verified_razorpay_payment_never_logs_in(real_app, outbox, monkeypatch):
    import routes_payment
    flask_app, db = real_app
    event_id = _spoc_event(flask_app, db, fee=250)
    email = f"{_unique('rzp')}@test.edu"
    secret = 'test-razorpay-secret-for-pytest'
    orders = {}

    class FakeOrders:
        def create(self, data):
            order = dict(data, id=f"order_{len(orders) + 1}", status='created')
            orders[order['id']] = order
            return order

        def fetch(self, order_id):
            return dict(orders[order_id], status='paid', amount_paid=orders[order_id]['amount'])

    class FakePayments:
        def fetch(self, payment_id):
            order = next(iter(orders.values()))
            return {'id': payment_id, 'order_id': order['id'], 'amount': order['amount'],
                    'status': 'captured'}

    class FakeClient:
        order = FakeOrders()
        payment = FakePayments()

    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_ID', 'rzp_test_pytest')
    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_SECRET', secret)
    monkeypatch.setattr(routes_payment, '_rzp', lambda: FakeClient())

    visitor = flask_app.test_client()
    visitor.post(f'/forms/submit/{event_id}', data=_form(email))
    order = visitor.post('/payment/create_order', json={'event_id': event_id})
    assert order.status_code == 200, order.data
    order_id = order.get_json()['order_id']
    payment_id = 'pay_pytest_001'
    signature = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()

    resp = visitor.post('/payment/verify', json={
        'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id,
        'razorpay_signature': signature, 'event_id': event_id,
    })

    assert resp.status_code == 200, resp.data
    assert resp.get_json()['redirect'] == '/registration/confirmed'
    assert 'user_id' not in _session(visitor)
    assert [r['lead_email'] for r in _regs(db, event_id)] == [email]


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_no_password_is_shown_stored_in_the_session_or_emailed(real_app, outbox):
    flask_app, db = real_app
    event_id = _spoc_event(flask_app, db)
    email = f"{_unique('nopw')}@test.edu"

    visitor = flask_app.test_client()
    resp = visitor.post(f'/forms/submit/{event_id}', data=_form(email))
    assert resp.headers['Location'] == '/registration/confirmed'
    assert not any('password' in k for k in _session(visitor).get('reg_confirmed', {}))

    page = visitor.get('/registration/confirmed')
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'cred-pw' not in body
    assert 'Login Credentials' not in body
    assert email in body  # the page says where the set-password link went

    for _args, kwargs in outbox['confirmations']:
        assert not kwargs.get('raw_password')
    for mail in outbox['mail']:
        assert 'Login Credentials' not in mail['html']


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_new_email_gets_an_account_and_a_one_time_set_password_link(real_app, outbox):
    flask_app, db = real_app
    event_id = _spoc_event(flask_app, db)
    email = f"{_unique('fresh')}@test.edu"

    visitor = flask_app.test_client()
    visitor.post(f'/forms/submit/{event_id}', data=_form(email, name='Fresh Face'))

    user = db.collection('users').document(email).get().to_dict()
    assert user['role'] == 'Student'
    assert user['email_verified'] is False
    assert user['needs_password_reset'] is True
    assert 'user_id' not in _session(visitor)
    links = _set_password_links(outbox, email)
    assert len(links) == 1
    link = links[0]

    # Nobody can log in before the link is used
    assert visitor.post('/login', data={'role': 'Student', 'email': email,
                                        'password': PASSWORD}).headers['Location'] == '/login'

    assert visitor.get(link).status_code == 200
    mismatch = visitor.post(link, data={'new_password': NEW_PASSWORD, 'confirm_password': 'nope1234'})
    assert mismatch.headers['Location'] == link
    assert 'user_id' not in _session(visitor)

    done = visitor.post(link, data={'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert done.status_code == 302
    assert _session(visitor)['user_id'] == email
    user = db.collection('users').document(email).get().to_dict()
    assert user['email_verified'] is True
    assert user['needs_password_reset'] is False
    assert check_password_hash(user['password'], NEW_PASSWORD)

    # The link works once
    other = flask_app.test_client()
    reused = other.get(link)
    assert reused.status_code == 302 and reused.headers['Location'] == '/login'
    other.post(link, data={'new_password': 'Hijack-attempt-9', 'confirm_password': 'Hijack-attempt-9'})
    assert 'user_id' not in _session(other)
    assert check_password_hash(db.collection('users').document(email).get().to_dict()['password'],
                               NEW_PASSWORD)


def test_expired_or_tampered_set_password_link_is_refused(real_app, outbox, monkeypatch):
    import itsdangerous.timed
    import services_accounts
    flask_app, db = real_app
    event_id = _spoc_event(flask_app, db)
    email = f"{_unique('late')}@test.edu"
    visitor = flask_app.test_client()
    visitor.post(f'/forms/submit/{event_id}', data=_form(email))
    stored_hash = db.collection('users').document(email).get().to_dict()['password']

    four_days_ago = int(time.time()) - 4 * 24 * 3600
    with flask_app.app_context():
        with monkeypatch.context() as m:
            m.setattr(itsdangerous.timed.TimestampSigner, 'get_timestamp', lambda self: four_days_ago)
            old_token = services_accounts.make_set_password_token(email, stored_hash)

    expired = visitor.get(f'/set_password/{old_token}')
    assert expired.status_code == 302 and expired.headers['Location'] == '/forgot_password'
    tampered = visitor.get(f'/set_password/{old_token[:-4]}abcd')
    assert tampered.status_code == 302 and tampered.headers['Location'] == '/login'
    assert 'user_id' not in _session(visitor)


# ── The legacy public registration route follows the same rules ────────────

def test_legacy_public_register_route_never_logs_in(real_app, outbox):
    flask_app, db = real_app
    event_id = _spoc_event(flask_app, db)
    existing = f"{_unique('old')}@test.edu"
    _user(db, existing, 'Student')

    visitor = flask_app.test_client()
    resp = visitor.post(f'/participant/public_register/{event_id}', data=_form(existing))
    assert resp.headers['Location'] == f'/login?next=/forms/register/{event_id}'
    assert 'user_id' not in _session(visitor)
    assert _regs(db, event_id) == []

    new = f"{_unique('legacy')}@test.edu"
    resp = visitor.post(f'/participant/public_register/{event_id}', data=_form(new))
    assert resp.headers['Location'] == '/registration/confirmed'
    assert 'user_id' not in _session(visitor)
    assert [r['lead_email'] for r in _regs(db, event_id)] == [new]
    assert len(_set_password_links(outbox, new)) == 1
    assert all('Login Credentials' not in m['html'] for m in outbox['mail'])
