"""
tests/test_razorpay_flow.py — UPG-94 on the real database layer, with the
Razorpay client mocked: the order carries what it pays for; verify asks
Razorpay whether the money arrived (capturing an authorized payment) and
otherwise leaves it to the webhook; failed attempts, refunds and refund
failures arrive by webhook; the checkout page offers a retry; a paid
registration gets its ticket, QR and emails; the webhook needs https in
production; admins see every order's status.
"""
import hashlib
import hmac
import json

from routes_ticket import generate_ticket_token
import routes_payment
from tests import test_paid_events
from tests.test_integration_flow import _unique
from tests.test_paid_events import (WEBHOOK_SECRET, _admin, _checkout, _order_row, _paid_registration,
                                    _receipts, _regs, _verify, _webhook)

# UPG-30's fixtures: Razorpay keys, a fake client, captured mail and a paid event
rzp = test_paid_events.rzp
paid = test_paid_events.paid


def _event(client, kind, payment=None, refund=None, secret=WEBHOOK_SECRET, headers=None):
    """Send a signed Razorpay webhook event."""
    payload = {}
    if payment is not None:
        payload['payment'] = {'entity': payment}
    if refund is not None:
        payload['refund'] = {'entity': refund}
    body = json.dumps({'event': kind, 'payload': payload}).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post('/payment/webhook/razorpay', data=body, content_type='application/json',
                       headers={'X-Razorpay-Signature': sig, **(headers or {})})


def _pending(client):
    with client.session_transaction() as sess:
        return dict(sess.get('pending_reg_data') or {})


def _tickets(d, email):
    return [m for m in d['rzp']['mail'] if m['to'] == email and 'Registered —' in m['subject']]


def _reg(d, reg_id):
    return d['db'].collection('registrations').document(reg_id).get().to_dict()


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_order_carries_event_registration_payer_and_a_unique_receipt(paid):
    d = paid
    client, email, first = _checkout(d)
    reg_id = _pending(client)['reg_id']
    second = client.post('/payment/create_order', json={'event_id': d['event_id']}).get_json()  # a retry

    orders = [d['rzp']['orders'][o['order_id']] for o in (first, second)]
    for order in orders:
        assert order['amount'] == 25000 and order['currency'] == 'INR' and order['payment_capture'] == 1
        assert order['notes'] == {'event_id': d['event_id'], 'registration_id': reg_id, 'email': email}
        assert len(order['receipt']) <= 40 and order['receipt'].startswith(reg_id)
    assert orders[0]['receipt'] != orders[1]['receipt']
    assert _pending(client)['reg_id'] == reg_id   # the same registration across retries


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_an_authorized_payment_is_captured_once_then_confirmed(paid):
    d = paid
    client, email, order = _checkout(d)
    oid, pid = order['order_id'], f"pay_{_unique('auth')}"
    d['rzp']['razorpay'][oid] = {'status': 'attempted', 'amount_paid': 0}
    d['rzp']['payments'][pid] = {'id': pid, 'order_id': oid, 'amount': 25000, 'status': 'authorized'}

    resp = _verify(client, d, oid, pid)
    assert resp.status_code == 200 and 'redirect' in resp.get_json()
    assert d['rzp']['captures'] == [(pid, 25000, {'currency': 'INR'})]
    [(_, reg)] = _regs(d, email)
    assert reg['status'] == 'Confirmed' and reg['payment_status'] == 'Paid' and reg['razorpay_payment_id'] == pid


def test_verify_refuses_what_razorpay_says_failed_or_was_another_amount(paid):
    d = paid
    failed_client, failed_email, failed = _checkout(d)
    pid = f"pay_{_unique('declined')}"
    d['rzp']['razorpay'][failed['order_id']] = {'status': 'attempted', 'amount_paid': 0}
    d['rzp']['payments'][pid] = {'id': pid, 'order_id': failed['order_id'], 'amount': 25000, 'status': 'failed'}
    resp = _verify(failed_client, d, failed['order_id'], pid)
    assert resp.status_code == 400 and 'the payment failed' in resp.get_json()['error']

    cheap_client, cheap_email, cheap = _checkout(d)
    d['rzp']['razorpay'][cheap['order_id']] = {'amount_paid': 100}
    assert _verify(cheap_client, d, cheap['order_id'], f"pay_{_unique('cheap')}").status_code == 400

    for email, order in ((failed_email, failed), (cheap_email, cheap)):
        assert _regs(d, email) == []
        assert _order_row(order['order_id'])['status'] == 'created'   # not claimed: the payer can retry
    assert d['rzp']['captures'] == []


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_when_razorpay_cant_confirm_the_webhook_completes_it_later(paid):
    d = paid
    client, email, order = _checkout(d)
    oid, pid = order['order_id'], f"pay_{_unique('late')}"
    d['rzp']['razorpay'][oid] = 'unreachable'

    resp = _verify(client, d, oid, pid)
    assert resp.status_code == 202
    assert resp.get_json() == {'pending': True, 'message': routes_payment.PENDING_MESSAGE}
    assert _regs(d, email) == [] and _order_row(oid)['status'] == 'created'
    assert _pending(client)['lead_email'] == email

    # The browser is gone; Razorpay's webhook arrives later
    hook = d['app'].test_client()
    assert _webhook(hook, oid, pid, order['amount']).get_json()['status'] == 'completed'
    [(reg_id, reg)] = _regs(d, email)
    assert reg['payment_status'] == 'Paid' and reg['amount_paid'] == 250
    assert len(_receipts(d, email)) == 1

    del d['rzp']['razorpay'][oid]   # the payer's browser tries again: sent to the ticket
    again = _verify(client, d, oid, pid)
    assert again.status_code == 200 and 'redirect' in again.get_json()
    assert len(_regs(d, email)) == 1 and len(_receipts(d, email)) == 1


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_a_webhook_after_the_browser_verified_changes_nothing(paid):
    d = paid
    reg_id, email, order, pay = _paid_registration(d)
    hook = d['app'].test_client()
    assert _webhook(hook, order['order_id'], pay, order['amount']).get_json()['status'] == 'nothing to do'
    assert _webhook(hook, order['order_id'], pay, order['amount']).get_json()['status'] == 'nothing to do'
    assert [r[0] for r in _regs(d, email)] == [reg_id]
    assert len(_receipts(d, email)) == 1 and len(_tickets(d, email)) == 1


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_a_failed_or_cancelled_payment_registers_nothing_and_can_be_retried(paid):
    d = paid
    client, email, first = _checkout(d)
    reg_id = _pending(client)['reg_id']
    hook = d['app'].test_client()

    failed = {'id': f"pay_{_unique('f')}", 'order_id': first['order_id'], 'amount': 25000, 'status': 'failed',
              'error_description': 'Your payment was declined by the bank.'}
    assert _event(hook, 'payment.failed', payment=failed).get_json()['status'] == 'recorded'
    row = _order_row(first['order_id'])
    assert row['status'] == 'created' and 'declined by the bank' in row['failure_reason']
    assert _regs(d, email) == []

    # Cancelled or failed, the form is kept: the checkout page and a new order still work
    assert _pending(client)['reg_id'] == reg_id
    page = client.get(f"/payment/checkout/{d['event_id']}")
    assert page.status_code == 200 and 'id="pay-btn"' in page.get_data(as_text=True)
    retry = client.post('/payment/create_order', json={'event_id': d['event_id']}).get_json()
    assert retry['order_id'] != first['order_id']
    assert d['rzp']['orders'][retry['order_id']]['notes']['registration_id'] == reg_id

    assert _verify(client, d, retry['order_id'], f"pay_{_unique('ok')}").status_code == 200
    assert [r[1]['reg_id'] for r in _regs(d, email)] == [reg_id]
    assert _order_row(retry['order_id'])['failure_reason'] == ''
    # A failure reported for a paid order changes nothing
    late = dict(failed, order_id=retry['order_id'])
    assert _event(hook, 'payment.failed', payment=late).get_json()['status'] == 'nothing to do'
    assert _order_row(retry['order_id'])['status'] == 'paid'


def test_the_checkout_page_handles_failure_and_cancel_on_the_page():
    with open('templates/payment/checkout.html', encoding='utf-8') as fh:
        html = fh.read()
    assert "rzp.on('payment.failed'" in html and 'ondismiss' in html
    assert 'try again' in html and 'res.pending' in html and 'res.message' in html
    assert 'alert(' not in html
    assert 'id="pay-status"' in html and 'role="alert"' in html


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_razorpay_refunds_cancel_the_registration_and_stop_the_ticket(paid):
    d = paid
    reg_id, email, order, pay = _paid_registration(d)
    hook = d['app'].test_client()
    payment = {'id': pay, 'order_id': order['order_id'], 'amount': 25000, 'status': 'refunded'}

    # A partial refund from the dashboard is noted; the registration stands
    part = {'id': f"rfnd_{_unique('part')}", 'payment_id': pay, 'amount': 10000, 'status': 'processed'}
    resp = _event(hook, 'refund.processed', payment=dict(payment, amount_refunded=10000), refund=part)
    assert resp.get_json()['status'] == 'noted'
    assert _order_row(order['order_id'])['status'] == 'paid'
    assert 'Partly refunded ₹100' in _order_row(order['order_id'])['failure_reason']
    assert _reg(d, reg_id)['payment_status'] == 'Paid'

    # The rest is refunded: the order is refunded, the registration cancelled
    rest = {'id': f"rfnd_{_unique('rest')}", 'payment_id': pay, 'amount': 15000, 'status': 'processed'}
    resp = _event(hook, 'refund.processed', payment=dict(payment, amount_refunded=25000), refund=rest)
    assert resp.get_json()['status'] == 'refunded'
    row = _order_row(order['order_id'])
    assert row['status'] == 'refunded' and row['refund_id'] == rest['id'] and row['refunded_by'] == 'razorpay'
    reg = _reg(d, reg_id)
    assert reg['status'] == 'cancelled' and reg['payment_status'] == 'Refunded' and reg['refund_id'] == rest['id']
    with d['app'].app_context():
        token = generate_ticket_token(reg_id, d['event_id'], 'Pay Er')
    checkin = d['owner'].post('/ticket/api/checkin', json={'token': token})
    assert checkin.status_code == 409 and checkin.get_json()['status'] == 'cancelled'

    # Replayed, or forged: nothing changes
    resp = _event(hook, 'refund.processed', payment=dict(payment, amount_refunded=25000), refund=rest)
    assert resp.get_json()['status'] == 'nothing to do'
    forged = {'id': 'rfnd_forged', 'payment_id': pay, 'amount': 25000}
    assert _event(hook, 'refund.failed', payment=payment, refund=forged, secret='wrong').status_code == 400
    assert _order_row(order['order_id'])['status'] == 'refunded'


def test_a_failed_refund_puts_the_order_back_for_the_admin(paid):
    d = paid
    client, email, order = _checkout(d)   # paid, but already registered: the admin refunds it
    d['db'].collection('registrations').document(_unique('REG')).set({
        'event_id': d['event_id'], 'lead_email': email, 'lead_name': 'Pay Er', 'status': 'Confirmed'})
    pay = f"pay_{_unique('rf')}"
    assert _verify(client, d, order['order_id'], pay).status_code == 202
    admin, _ = _admin(d)
    admin.post(f"/admin/payments/{order['order_id']}/refund", data={'confirm': 'yes'})
    refund_id = _order_row(order['order_id'])['refund_id']
    assert _order_row(order['order_id'])['status'] == 'refunded'

    hook = d['app'].test_client()
    # The admin's own refund confirmed by webhook: nothing more to do
    done = {'id': refund_id, 'payment_id': pay, 'amount': 25000, 'status': 'processed'}
    assert _event(hook, 'refund.processed', refund=done, payment={'id': pay}).get_json()['status'] == 'nothing to do'

    failed = {'id': refund_id, 'payment_id': pay, 'amount': 25000, 'status': 'failed'}
    assert _event(hook, 'refund.failed', refund=failed, payment={'id': pay}).get_json()['status'] == 'recorded'
    row = _order_row(order['order_id'])
    assert row['status'] == 'paid' and row['refund_id'] == '' and f"Refund {refund_id} failed" in row['failure_reason']
    assert f"/admin/payments/{order['order_id']}/refund" in admin.get('/admin/payments').get_data(as_text=True)
    assert _event(hook, 'refund.failed', refund=failed, payment={'id': pay}).get_json()['status'] == 'nothing to do'


# ── Criterion 7 ─────────────────────────────────────────────────────────────

def test_a_paid_registration_gets_its_ticket_qr_and_emails(paid):
    from tasks.email_tasks import ticket_qr_png
    d = paid
    _, email, order = _checkout(d)   # the browser closes after paying
    resp = _webhook(d['app'].test_client(), order['order_id'], f"pay_{_unique('t')}", order['amount'])
    reg_id = resp.get_json()['reg_id']

    assert len(_tickets(d, email)) == 1 and len(_receipts(d, email)) == 1
    assert reg_id in _tickets(d, email)[0]['html']
    with d['app'].app_context():
        qr = ticket_qr_png(reg_id)
        token = generate_ticket_token(reg_id, d['event_id'], 'Pay Er')
    assert qr and qr.startswith(b'\x89PNG')
    checkin = d['owner'].post('/ticket/api/checkin', json={'token': token})
    assert checkin.status_code == 200 and checkin.get_json()['status'] == 'success'


# ── Criterion 8 ─────────────────────────────────────────────────────────────

def test_the_webhook_needs_https_in_production(paid, monkeypatch):
    d = paid
    _, email, order = _checkout(d)
    monkeypatch.setenv('FLASK_ENV', 'production')
    hook = d['app'].test_client()
    payment = {'id': f"pay_{_unique('s')}", 'order_id': order['order_id'], 'amount': order['amount'],
               'status': 'captured'}

    assert _event(hook, 'payment.captured', payment=payment).status_code == 403
    assert _regs(d, email) == [] and _order_row(order['order_id'])['status'] == 'created'
    # Behind Cloud Run, TLS ends at the front end, which says so in X-Forwarded-Proto
    resp = _event(hook, 'payment.captured', payment=payment, headers={'X-Forwarded-Proto': 'https'})
    assert resp.status_code == 200 and resp.get_json()['status'] == 'completed'
    assert len(_regs(d, email)) == 1


# ── Criterion 9 ─────────────────────────────────────────────────────────────

def test_admins_see_every_orders_status_and_others_get_403(paid):
    d = paid
    doc_id, _, completed, pay = _paid_registration(d)
    reg_id = _reg(d, doc_id)['reg_id']
    _, _, open_order = _checkout(d)
    hook = d['app'].test_client()
    _event(hook, 'payment.failed', payment={'id': f"pay_{_unique('x')}", 'order_id': open_order['order_id'],
                                            'amount': 25000, 'error_description': 'Card expired'})
    refund = {'id': f"rfnd_{_unique('d')}", 'payment_id': pay, 'amount': 25000}
    _event(hook, 'refund.processed', payment={'id': pay, 'amount_refunded': 25000}, refund=refund)

    admin, _ = _admin(d)
    assert '/admin/payments/orders' in admin.get('/admin/payments').get_data(as_text=True)
    page = admin.get('/admin/payments/orders')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    for text in (completed['order_id'], pay, reg_id, refund['id'], '>refunded<',
                 open_order['order_id'], '>created<', 'Card expired', '₹250'):
        assert text in html, text
    assert d['owner'].get('/admin/payments/orders').status_code == 403
