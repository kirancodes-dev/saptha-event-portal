"""
tests/test_payments_secure.py — BLK-03 on the real SQL database layer:
paid events can't be completed without a real, matching payment.

  * the simulated checkout exists only with PAYMENT_SIMULATION=true, never
    in production;
  * without Razorpay keys, order creation and verification fail closed;
  * /payment/verify accepts only an order this server created for the same
    event and payer, records the server's amount, and a payment ID works once;
  * waitlist promotion on a paid event holds the seat until it's paid.
"""
import hashlib
import hmac

import pytest

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

SECRET = 'test-razorpay-secret-for-pytest'


@pytest.fixture
def mail(real_app, monkeypatch):
    """Capture Celery email/WhatsApp tasks queued by payment and promotion."""
    import routes_payment
    import tasks.email_tasks

    queued = []

    class FakeTask:
        def __init__(self, name):
            self.name = name

        def delay(self, *a, **k):
            queued.append((self.name, k))

        def apply(self, *a, **k):
            queued.append((self.name, k))

    for name in ('send_ticket_email_task', 'send_ticket_whatsapp_task',
                 'send_payment_receipt_whatsapp_task'):
        monkeypatch.setattr(routes_payment, name, FakeTask(name))
    monkeypatch.setattr(tasks.email_tasks, 'send_generic_email_task', FakeTask('generic_email'))
    return queued


@pytest.fixture
def razorpay(monkeypatch):
    """Configure Razorpay keys and a fake client that records created orders."""
    import routes_payment

    orders = {}

    class FakeOrders:
        def create(self, data):
            order = dict(data, id=f"order_{_unique('rzp')}", status='created')
            orders[order['id']] = order
            return order

    class FakeClient:
        order = FakeOrders()

    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_ID', 'rzp_test_pytest')
    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_SECRET', SECRET)
    monkeypatch.setattr(routes_payment, '_rzp', lambda: FakeClient())
    return orders


def _sign(order_id, payment_id, secret=SECRET):
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def _event(flask_app, db, fee, **extra):
    spoc = f"{_unique('spoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(client, db, _unique('Paid Event'), '2030-06-01', fee=fee, team=False)
    if extra:
        db.collection('events').document(event_id).update(extra)
    return event_id


def _start(flask_app, event_id, email=None, client=None):
    """Submit the registration form; returns the client with a pending registration."""
    client = client or flask_app.test_client()
    email = email or f"{_unique('payer')}@test.edu"
    resp = client.post(f'/forms/submit/{event_id}', data={
        'full_name': 'Pay Er', 'email': email, 'phone': '9876543210', 'usn': '1SN20CS042'})
    assert resp.headers['Location'] == f'/payment/checkout/{event_id}', resp.headers['Location']
    return client


def _order(client, event_id):
    resp = client.post('/payment/create_order', json={'event_id': event_id})
    assert resp.status_code == 200, resp.data
    return resp.get_json()


def _verify(client, event_id, order_id, payment_id, **extra):
    body = {'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id,
            'razorpay_signature': _sign(order_id, payment_id), 'event_id': event_id}
    body.update(extra)
    return client.post('/payment/verify', json=body)


def _regs(db, event_id):
    return [d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream()]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_simulated_checkout_needs_the_flag_and_never_runs_in_production(real_app, mail, monkeypatch):
    flask_app, db = real_app
    event_id = _event(flask_app, db, fee=250)
    monkeypatch.delenv('PAYMENT_SIMULATION', raising=False)

    client = _start(flask_app, event_id)
    assert client.post('/payment/process', data={'event_id': event_id, 'amount': '0'}).status_code == 403
    assert _regs(db, event_id) == []

    monkeypatch.setenv('PAYMENT_SIMULATION', 'true')
    monkeypatch.setenv('FLASK_ENV', 'production')
    assert client.post('/payment/process', data={'event_id': event_id, 'amount': '0'}).status_code == 403
    assert _regs(db, event_id) == []

    monkeypatch.setenv('FLASK_ENV', 'development')
    resp = client.post('/payment/process', data={'event_id': event_id, 'amount': '1'})
    assert resp.status_code == 302
    regs = _regs(db, event_id)
    assert len(regs) == 1
    assert regs[0]['amount_paid'] == 250  # the server's price, not the form's ₹1


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_payment_fails_closed_without_razorpay_keys(real_app, mail, monkeypatch):
    import routes_payment
    flask_app, db = real_app
    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_ID', '')
    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_SECRET', '')
    monkeypatch.delenv('PAYMENT_SIMULATION', raising=False)
    event_id = _event(flask_app, db, fee=500)
    client = _start(flask_app, event_id)

    created = client.post('/payment/create_order', json={'event_id': event_id})
    assert created.status_code == 503
    assert 'simulate' not in (created.get_json() or {})

    forged = client.post('/payment/verify', json={
        'razorpay_order_id': 'order_FAKE123', 'razorpay_payment_id': 'pay_FAKE456',
        'razorpay_signature': _sign('order_FAKE123', 'pay_FAKE456', secret=''),
        'event_id': event_id, 'amount_inr': 1})
    assert forged.status_code == 503
    assert _regs(db, event_id) == []

    # Simulation, when switched on, is the only keyless path
    monkeypatch.setenv('PAYMENT_SIMULATION', 'true')
    assert client.post('/payment/create_order', json={'event_id': event_id}).get_json()['simulate'] is True


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_verify_accepts_only_this_servers_order_for_the_same_event_and_payer(real_app, mail, razorpay):
    flask_app, db = real_app
    cheap = _event(flask_app, db, fee=100)
    dear = _event(flask_app, db, fee=500)

    # A correctly signed payment for an order this server never created
    alice = _start(flask_app, dear)
    assert _verify(alice, dear, 'order_NOT_OURS', 'pay_1').status_code == 400
    assert _regs(db, dear) == []

    # Someone else's order (another payer, another event)
    bob = _start(flask_app, cheap)
    bobs_order = _order(bob, cheap)['order_id']
    assert _verify(alice, dear, bobs_order, 'pay_2').status_code == 400
    assert _regs(db, dear) == []

    # Your own order, created for a cheaper event, used for a dearer one
    carol_email = f"{_unique('carol')}@test.edu"
    carol = _login_student(flask_app, db, carol_email)
    _start(flask_app, cheap, email=carol_email, client=carol)
    carols_cheap_order = _order(carol, cheap)['order_id']
    _start(flask_app, dear, email=carol_email, client=carol)
    assert _verify(carol, dear, carols_cheap_order, 'pay_3').status_code == 400
    assert _regs(db, dear) == []

    # The genuine order still works
    alices_order = _order(alice, dear)['order_id']
    assert _verify(alice, dear, alices_order, 'pay_4').status_code == 200
    assert len(_regs(db, dear)) == 1


def _login_student(flask_app, db, email):
    _user(db, email, 'Student')
    client = flask_app.test_client()
    client.post('/login', data={'role': 'Student', 'email': email, 'password': PASSWORD})
    return client


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_amount_comes_from_the_server_never_the_request(real_app, mail, razorpay):
    flask_app, db = real_app
    # 8 of 10 seats taken → dynamic pricing 1.5 × ₹200 = ₹300
    event_id = _event(flask_app, db, fee=200, limits={'max_participants': 10}, registration_count=8)
    client = _start(flask_app, event_id)

    order = _order(client, event_id)
    assert order['amount'] == 30000
    assert razorpay[order['order_id']]['amount'] == 30000

    resp = _verify(client, event_id, order['order_id'], 'pay_amount', amount_inr=1)
    assert resp.status_code == 200, resp.data
    reg = _regs(db, event_id)[0]
    assert reg['amount_paid'] == 300
    assert reg['payment_status'] == 'Paid'
    assert reg['razorpay_order_id'] == order['order_id']


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_a_payment_id_can_be_used_once(real_app, mail, razorpay):
    flask_app, db = real_app
    event_id = _event(flask_app, db, fee=150)

    first = _start(flask_app, event_id)
    first_order = _order(first, event_id)['order_id']
    assert _verify(first, event_id, first_order, 'pay_ONCE').status_code == 200

    second = _start(flask_app, event_id)
    second_order = _order(second, event_id)['order_id']
    reused = _verify(second, event_id, second_order, 'pay_ONCE')
    assert reused.status_code == 409
    assert len(_regs(db, event_id)) == 1

    # The same order can't be completed twice, even with a new payment ID
    again = _start(flask_app, event_id)
    again_order = _order(again, event_id)['order_id']
    with again.session_transaction() as sess:
        pending = dict(sess['pending_reg_data'])
    assert _verify(again, event_id, again_order, 'pay_AGAIN').status_code == 200
    with again.session_transaction() as sess:
        sess['pending_reg_data'] = pending  # replay the same checkout
    assert _verify(again, event_id, again_order, 'pay_AGAIN_2').status_code == 409
    assert len(_regs(db, event_id)) == 2

def test_waitlist_promotion_on_a_paid_event_holds_the_seat_until_paid(real_app, mail, razorpay, monkeypatch):
    monkeypatch.setenv('PAYMENT_SIMULATION', 'true')
    flask_app, db = real_app
    event_id = _event(flask_app, db, fee=250, limits={'max_participants': 1}, capacity=1)

    first_email = f"{_unique('first')}@test.edu"
    first = _login_student(flask_app, db, first_email)
    _start(flask_app, event_id, email=first_email, client=first)
    first.post('/payment/process', data={'event_id': event_id})
    assert [r['lead_email'] for r in _regs(db, event_id)] == [first_email]

    second_email = f"{_unique('second')}@test.edu"
    second = _login_student(flask_app, db, second_email)
    wl = second.post(f'/forms/submit/{event_id}', data={
        'full_name': 'Second', 'email': second_email, 'phone': '9876543210', 'usn': '1SN20CS043'})
    assert wl.headers['Location'] == '/participant/dashboard'

    reg_doc = next(d for d in db.collection('registrations').where('event_id', '==', event_id).stream()
                   if d.to_dict()['lead_email'] == first_email)
    first.post(f'/participant/cancel/{reg_doc.id}')
    count_after_promotion = db.collection('events').document(event_id).get().to_dict()['registration_count']

    held = [r for r in _regs(db, event_id) if r['lead_email'] == second_email]
    assert len(held) == 1
    assert held[0]['status'] == 'pending_payment'
    assert held[0]['payment_status'] == 'Pending'
    pay_path = f"/payment/pay/{held[0]['reg_id']}"
    assert any(pay_path in k.get('body', '') for name, k in mail if name == 'generic_email')

    # Only the owner can use the pay link; paying confirms the same registration
    assert first.get(pay_path).headers['Location'] == '/participant/dashboard'
    go = second.get(pay_path)
    assert go.headers['Location'] == f'/payment/checkout/{event_id}'
    order = _order(second, event_id)
    assert _verify(second, event_id, order['order_id'], 'pay_HELD').status_code == 200

    mine = [r for r in _regs(db, event_id) if r['lead_email'] == second_email]
    assert len(mine) == 1
    assert mine[0]['reg_id'] == held[0]['reg_id']
    assert mine[0]['status'] == 'Confirmed' and mine[0]['payment_status'] == 'Paid'
    assert mine[0]['amount_paid'] * 100 == order['amount']  # the server's price for the event
    assert db.collection('events').document(event_id).get().to_dict()['registration_count'] == count_after_promotion
