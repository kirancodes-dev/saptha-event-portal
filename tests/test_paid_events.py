"""
tests/test_paid_events.py — UPG-30 on the real database layer, with the
Razorpay client mocked: a paid registration gets one receipt; admins mark
registrations refunded or cancelled (and those tickets stop checking in);
money taken without a registration is never lost or overbooked, can be
completed by Razorpay's webhook, is listed for the admin and can be refunded.
"""
import csv
import hashlib
import hmac
import io
import json

import pytest

import routes_payment
from routes_ticket import generate_ticket_token
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

SECRET = 'test-razorpay-secret-for-pytest'
WEBHOOK_SECRET = 'test-webhook-secret-for-pytest'


@pytest.fixture
def rzp(real_app, monkeypatch):
    """Razorpay keys and a fake client recording orders and refunds; outgoing mail captured."""
    import utils_email
    calls = {'orders': {}, 'refunds': [], 'mail': []}

    class FakeOrders:
        def create(self, data):
            order = dict(data, id=f"order_{_unique('rzp')}", status='created')
            calls['orders'][order['id']] = order
            return order

    class FakePayments:
        def refund(self, payment_id, data):
            calls['refunds'].append((payment_id, data))
            return {'id': f"rfnd_{_unique('r')}", 'payment_id': payment_id, 'amount': data['amount']}

    class FakeClient:
        order = FakeOrders()
        payment = FakePayments()

    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_ID', 'rzp_test_pytest')
    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_SECRET', SECRET)
    monkeypatch.setattr(routes_payment, '_rzp', lambda: FakeClient())
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', WEBHOOK_SECRET)
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k:
                        calls['mail'].append({'to': to, 'subject': subject, 'html': html}) or True)
    return calls


@pytest.fixture
def paid(real_app, rzp):
    flask_app, db = real_app
    spoc = f"{_unique('paidspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Paid Night'), '2030-06-01', fee=250, team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open'})
    return {'app': flask_app, 'db': db, 'owner': owner, 'event_id': event_id, 'rzp': rzp}


def _admin(d):
    admin = f"{_unique('payadmin')}@test.edu"
    _user(d['db'], admin, 'SuperAdmin')
    client = d['app'].test_client()
    client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                'secret_key': d['app'].config.get('MASTER_SECRET_KEY', '')})
    return client, admin


def _checkout(d, email=None):
    """A payer who submitted the form and created an order: (client, email, order)."""
    client = d['app'].test_client()
    email = email or f"{_unique('payer')}@test.edu"
    resp = client.post(f"/forms/submit/{d['event_id']}", data={
        'full_name': 'Pay Er', 'email': email, 'phone': '9876543210', 'usn': '1SN20CS042'})
    assert resp.headers['Location'] == f"/payment/checkout/{d['event_id']}"
    order = client.post('/payment/create_order', json={'event_id': d['event_id']}).get_json()
    return client, email, order


def _verify(client, d, order_id, payment_id):
    sig = hmac.new(SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    return client.post('/payment/verify', json={'razorpay_order_id': order_id, 'razorpay_payment_id': payment_id,
                                                'razorpay_signature': sig, 'event_id': d['event_id']})


def _webhook(client, order_id, payment_id, amount, secret=WEBHOOK_SECRET):
    body = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {
        'id': payment_id, 'order_id': order_id, 'amount': amount, 'currency': 'INR', 'status': 'captured'}}}}).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post('/payment/webhook/razorpay', data=body, content_type='application/json',
                       headers={'X-Razorpay-Signature': sig})


def _regs(d, email=None):
    regs = [(doc.id, doc.to_dict()) for doc in d['db'].collection('registrations').where('event_id', '==', d['event_id']).stream()]
    return [r for r in regs if email is None or r[1].get('lead_email') == email]


def _receipts(d, email):
    return [m for m in d['rzp']['mail'] if m['to'] == email and 'Payment receipt' in m['subject']]


def _order_row(order_id):
    from services_payments import get_order
    return get_order(order_id)


def _audit(d, actor):
    return [e.to_dict() for e in d['db'].collection('audit_log').where('actor_email', '==', actor).stream()]


def _paid_registration(d):
    client, email, order = _checkout(d)
    pay = f"pay_{_unique('p')}"
    assert _verify(client, d, order['order_id'], pay).status_code == 200
    [(reg_id, _)] = _regs(d, email)
    return reg_id, email, order, pay


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_a_verified_payment_confirms_and_sends_one_receipt(paid):
    d = paid
    client, email, order = _checkout(d)
    assert order['amount'] == 25000
    resp = _verify(client, d, order['order_id'], 'pay_receipt_1')
    assert resp.status_code == 200 and 'redirect' in resp.get_json()
    [(_, reg)] = _regs(d, email)
    assert reg['status'] == 'Confirmed' and reg['payment_status'] == 'Paid' and reg['amount_paid'] == 250
    receipts = _receipts(d, email)
    assert len(receipts) == 1
    assert '₹250' in receipts[0]['html'] and 'pay_receipt_1' in receipts[0]['html']


# ── Criteria 2 and 3 ────────────────────────────────────────────────────────

def test_admin_marks_registrations_refunded_and_cancelled_and_their_tickets_stop(paid):
    d = paid
    refunded, _, _, _ = _paid_registration(d)
    cancelled, _, _, _ = _paid_registration(d)
    client, admin = _admin(d)

    page = client.get('/admin/payments')
    assert page.status_code == 200 and refunded in page.get_data(as_text=True)
    assert client.post(f'/admin/registrations/{refunded}/mark',
                       data={'action': 'refunded', 'reason': 'Refunded at the desk'}).status_code == 302
    assert client.post(f'/admin/registrations/{cancelled}/mark',
                       data={'action': 'cancelled', 'reason': 'Event clash'}).status_code == 302

    r1 = d['db'].collection('registrations').document(refunded).get().to_dict()
    r2 = d['db'].collection('registrations').document(cancelled).get().to_dict()
    assert r1['status'].lower() == 'cancelled' and r1['payment_status'] == 'Refunded'
    assert r2['status'].lower() == 'cancelled' and r2['cancel_reason'] == 'Event clash'
    actions = {e['action']: e['details'] for e in _audit(d, admin)}
    assert refunded in actions['REGISTRATION_REFUNDED'] and cancelled in actions['REGISTRATION_CANCELLED']

    with d['app'].app_context():
        tokens = [generate_ticket_token(r, d['event_id'], 'Pay Er') for r in (refunded, cancelled)]
    for token in tokens:
        resp = d['owner'].post('/ticket/api/checkin', json={'token': token})
        assert resp.status_code == 409 and resp.get_json()['status'] == 'cancelled'


def test_non_admins_cant_use_any_payment_action(paid):
    d = paid
    reg_id, _, _, _ = _paid_registration(d)
    student = f"{_unique('nosy')}@test.edu"
    _user(d['db'], student, 'Student')
    for client in (d['owner'], _login(d['app'], student, 'Student')):
        assert client.get('/admin/payments').status_code == 403
        assert client.post(f'/admin/registrations/{reg_id}/mark',
                           data={'action': 'refunded', 'reason': 'x'}).status_code == 403
        assert client.post('/admin/payments/order_anything/refund', data={'confirm': 'yes'}).status_code == 403
        assert client.get('/admin/analytics/export/payments').status_code == 403
    reg = d['db'].collection('registrations').document(reg_id).get().to_dict()
    assert reg['status'] == 'Confirmed' and reg['payment_status'] == 'Paid'


# ── Criterion 5 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('failure', ['event full', 'already registered', 'error'])
def test_a_failed_completion_keeps_the_payment_and_overbooks_nobody(paid, monkeypatch, failure):
    d = paid
    client, email, order = _checkout(d)
    if failure == 'event full':  # the last seat went while they paid
        count = d['db'].collection('events').document(d['event_id']).get().to_dict().get('registration_count', 0)
        d['db'].collection('events').document(d['event_id']).update({
            'limits': {'max_participants': count + 1, 'team_min': 1, 'team_max': 1}, 'registration_count': count + 1})
    elif failure == 'already registered':
        d['db'].collection('registrations').document(_unique('REG')).set({
            'event_id': d['event_id'], 'lead_email': email, 'lead_name': 'Pay Er', 'status': 'Confirmed'})
    else:
        monkeypatch.setattr(routes_payment, 'record_form_submission',
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('database went away')))
    before = d['db'].collection('events').document(d['event_id']).get().to_dict().get('registration_count', 0)
    expected_regs = len(_regs(d, email)) if failure == 'already registered' else 0

    resp = _verify(client, d, order['order_id'], f"pay_{_unique('fail')}")
    assert resp.status_code == 202
    body = resp.get_json()
    assert body['recorded'] is True and body['message'] == routes_payment.RECORDED_MESSAGE
    if failure != 'error':  # the error happens after the registration row is written; it stays unmatched
        assert len(_regs(d, email)) == expected_regs
        after = d['db'].collection('events').document(d['event_id']).get().to_dict().get('registration_count', 0)
        assert after == before
    row = _order_row(order['order_id'])
    assert row['status'] == 'paid' and row['reg_id'] == '' and row['failure_reason']

    client_admin, _ = _admin(d)
    assert order['order_id'] in client_admin.get('/admin/payments').get_data(as_text=True)
    with open('templates/payment/checkout.html', encoding='utf-8') as fh:
        assert 'res.message' in fh.read()  # the checkout page shows the payer this message


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_the_webhook_completes_a_payment_whose_browser_never_returned_once(paid):
    d = paid
    browser, email, order = _checkout(d)
    hook = d['app'].test_client()

    resp = _webhook(hook, order['order_id'], 'pay_hook_1', order['amount'])
    assert resp.status_code == 200 and resp.get_json()['status'] == 'completed'
    [(_, reg)] = _regs(d, email)
    assert reg['payment_status'] == 'Paid' and reg['amount_paid'] == 250 and reg['razorpay_payment_id'] == 'pay_hook_1'
    assert _order_row(order['order_id'])['reg_id'] == reg['reg_id']
    assert len(_receipts(d, email)) == 1

    # Replayed, then the browser's verify arriving late: nothing changes
    assert _webhook(hook, order['order_id'], 'pay_hook_1', order['amount']).get_json()['status'] == 'nothing to do'
    late = _verify(browser, d, order['order_id'], 'pay_hook_1')
    assert late.status_code == 200 and 'redirect' in late.get_json()
    assert len(_regs(d, email)) == 1 and len(_receipts(d, email)) == 1


def test_the_webhook_refuses_bad_signatures_and_ignores_unknown_orders(paid):
    d = paid
    _, email, order = _checkout(d)
    hook = d['app'].test_client()
    assert _webhook(hook, order['order_id'], 'pay_forged', order['amount'], secret='wrong-secret').status_code == 400
    assert _regs(d, email) == [] and _order_row(order['order_id'])['status'] == 'created'

    resp = _webhook(hook, 'order_nobody_made', 'pay_ghost', 25000)
    assert resp.status_code == 200 and _regs(d) == []
    resp = _webhook(hook, order['order_id'], 'pay_cheap', 100)   # an amount that isn't the order's
    assert resp.status_code == 200 and _regs(d, email) == []


def test_the_webhook_fails_closed_without_its_secret(paid, monkeypatch):
    d = paid
    _, email, order = _checkout(d)
    monkeypatch.delenv('RAZORPAY_WEBHOOK_SECRET')
    assert _webhook(d['app'].test_client(), order['order_id'], 'pay_x', order['amount']).status_code == 503
    assert _regs(d, email) == []


# ── Criterion 7 ─────────────────────────────────────────────────────────────

def test_the_admin_list_shows_exactly_the_paid_orders_without_a_registration(paid):
    d = paid
    _, _, completed, _ = _paid_registration(d)                       # paid, registered
    unpaid_client, _, unpaid = _checkout(d)                          # never paid
    orphan_client, orphan_email, orphan = _checkout(d)               # paid, then already registered
    d['db'].collection('registrations').document(_unique('REG')).set({
        'event_id': d['event_id'], 'lead_email': orphan_email, 'lead_name': 'Pay Er', 'status': 'Confirmed'})
    assert _verify(orphan_client, d, orphan['order_id'], f"pay_{_unique('o')}").status_code == 202

    client, _ = _admin(d)
    html = client.get('/admin/payments').get_data(as_text=True)
    listed = set(__import__('re').findall(r'/admin/payments/(order_[^/"]+)/refund', html))
    assert orphan['order_id'] in listed
    assert completed['order_id'] not in listed and unpaid['order_id'] not in listed
    from services_payments import unmatched_orders
    assert orphan['order_id'] in {o['id'] for o in unmatched_orders()}
    assert completed['order_id'] not in {o['id'] for o in unmatched_orders()}


# ── Criterion 8 ─────────────────────────────────────────────────────────────

def test_the_refund_calls_razorpay_once_and_is_recorded(paid):
    d = paid
    client_payer, email, order = _checkout(d)
    d['db'].collection('registrations').document(_unique('REG')).set({
        'event_id': d['event_id'], 'lead_email': email, 'lead_name': 'Pay Er', 'status': 'Confirmed'})
    _verify(client_payer, d, order['order_id'], 'pay_to_refund')
    client, admin = _admin(d)

    assert client.post(f"/admin/payments/{order['order_id']}/refund").status_code == 302   # not confirmed
    assert d['rzp']['refunds'] == []
    assert client.post(f"/admin/payments/{order['order_id']}/refund", data={'confirm': 'yes'}).status_code == 302
    assert d['rzp']['refunds'] == [('pay_to_refund', {'amount': 25000})]
    row = _order_row(order['order_id'])
    assert row['status'] == 'refunded' and row['refund_id'].startswith('rfnd_') and row['refunded_by'] == admin
    assert any(e['action'] == 'PAYMENT_REFUNDED' and order['order_id'] in e['details'] for e in _audit(d, admin))

    client.post(f"/admin/payments/{order['order_id']}/refund", data={'confirm': 'yes'})
    assert len(d['rzp']['refunds']) == 1                   # a second request does nothing
    assert order['order_id'] not in client.get('/admin/payments').get_data(as_text=True)


# ── Finance export ──────────────────────────────────────────────────────────

def test_the_finance_export_has_one_row_per_payment(paid):
    d = paid
    _, _, completed, pay = _paid_registration(d)
    client, _ = _admin(d)
    resp = client.get('/admin/analytics/export/payments')
    assert resp.status_code == 200
    rows = {r['order_id']: r for r in csv.DictReader(io.StringIO(resp.get_data(as_text=True)))}
    assert rows[completed['order_id']]['payment_id'] == pay and rows[completed['order_id']]['status'] == 'paid'
    assert float(rows[completed['order_id']]['amount_inr']) == 250.0
