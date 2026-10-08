"""
tests/test_coupon_limits.py — UPG-36 on the real database layer: a coupon's
uses can't be overspent. An order holds a use from the moment it's created
(one conditional UPDATE), an unpaid order gives it back after the hold
expires, and a retry by the same payer doesn't hold two.
"""
import datetime
import os
import threading

import pytest

import routes_payment
from tests.test_integration_flow import _create_event, _login, _unique, _user
from tests.test_paid_events import _verify  # noqa: F401  (same signing)

SECRET = 'test-razorpay-secret-for-pytest'


@pytest.fixture
def shop(real_app, monkeypatch):
    flask_app, db = real_app

    class FakeOrders:
        def create(self, data):
            return dict(data, id=f"order_{_unique('rzp')}", status='created')

    class FakeClient:
        order = FakeOrders()

    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_ID', 'rzp_test_pytest')
    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_SECRET', SECRET)
    monkeypatch.setattr(routes_payment, '_rzp', lambda: FakeClient())
    spoc = f"{_unique('couponspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Coupon Night'), '2030-06-01',
                             fee=500, team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open'})

    def coupon(max_uses):
        code = _unique('HALF').upper().replace('-', '')
        db.collection('coupons').document(_unique('cpn')).set({
            'code': code, 'event_id': event_id, 'discount_type': 'percentage', 'discount_value': 50,
            'max_uses': max_uses, 'current_uses': 0, 'is_active': True})
        return code
    return {'app': flask_app, 'db': db, 'event_id': event_id, 'coupon': coupon}


def _payer(d):
    client = d['app'].test_client()
    resp = client.post(f"/forms/submit/{d['event_id']}", data={
        'full_name': 'Cou Pon', 'email': f"{_unique('saver')}@test.edu", 'phone': '9876543210', 'usn': '1SN20CS042'})
    assert resp.headers['Location'] == f"/payment/checkout/{d['event_id']}"
    return client


def _order(client, d, code):
    return client.post('/payment/create_order', json={'event_id': d['event_id'], 'coupon': code})


def _uses(d, code):
    return next(doc.to_dict()['current_uses'] for doc in d['db'].collection('coupons').stream()
                if (doc.to_dict() or {}).get('code') == code)


def _status(order_id):
    from services_payments import get_order
    return get_order(order_id)['status']


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_two_checkouts_before_anyone_pays_get_one_discount(shop):
    d = shop
    code = d['coupon'](1)
    first, second = _payer(d), _payer(d)
    a = _order(first, d, code)
    b = _order(second, d, code)
    assert a.status_code == 200 and a.get_json()['amount'] == 25000            # half of ₹500
    assert b.status_code == 400 and 'limit' in b.get_json()['error']

    # The second payer can still pay full price; the first pays and uses the coupon
    full = second.post('/payment/create_order', json={'event_id': d['event_id']})
    assert full.status_code == 200 and full.get_json()['amount'] == 50000
    assert _verify(first, d, a.get_json()['order_id'], f"pay_{_unique('c')}").status_code == 200
    assert _uses(d, code) == 1
    assert _order(_payer(d), d, code).status_code == 400
    assert _uses(d, code) == 1


def test_a_payer_starting_checkout_again_holds_one_use(shop):
    d = shop
    code = d['coupon'](1)
    client = _payer(d)
    first = _order(client, d, code)
    again = _order(client, d, code)                     # e.g. they closed the payment window
    assert first.status_code == 200 and again.status_code == 200
    assert _status(first.get_json()['order_id']) == 'replaced'
    assert _order(_payer(d), d, code).status_code == 400


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_an_unpaid_order_gives_its_use_back_when_the_hold_expires(shop):
    d = shop
    code = d['coupon'](1)
    abandoned = _payer(d)
    held = _order(abandoned, d, code).get_json()['order_id']
    assert _order(_payer(d), d, code).status_code == 400

    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        s.get(PaymentOrder, held).created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=31)

    later = _payer(d)
    resp = _order(later, d, code)
    assert resp.status_code == 200 and resp.get_json()['amount'] == 25000
    assert _status(held) == 'expired'

    # Paying the expired order now finds no use left: the money is kept for the admin, not lost
    late = _verify(abandoned, d, held, f"pay_{_unique('late')}")
    assert late.status_code == 202 and late.get_json()['recorded'] is True
    from services_payments import get_order
    assert get_order(held)['status'] == 'paid' and get_order(held)['failure_reason'] == routes_payment.COUPON_GONE
    assert _uses(d, code) == 0  # nobody paid with it yet


# ── Criterion 3 ─────────────────────────────────────────────────────────────

@pytest.mark.skipif(not os.environ.get('TEST_DATABASE_URL', '').startswith('postgresql'),
                    reason='concurrency is checked on PostgreSQL')
def test_ten_concurrent_checkouts_get_exactly_the_coupons_three_uses(shop):
    d = shop
    code = d['coupon'](3)
    clients = [_payer(d) for _ in range(10)]
    start = threading.Barrier(10)
    results = [None] * 10

    def checkout(i):
        start.wait()
        results[i] = _order(clients[i], d, code)

    threads = [threading.Thread(target=checkout, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    discounted = [r for r in results if r is not None and r.status_code == 200 and r.get_json()['amount'] == 25000]
    refused = [r for r in results if r is not None and r.status_code == 400]
    assert len(discounted) == 3 and len(refused) == 7
