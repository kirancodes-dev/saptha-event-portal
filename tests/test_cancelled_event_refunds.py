"""
tests/test_cancelled_event_refunds.py — UPG-51 on the real database layer,
Razorpay mocked: a cancelled paid event's registrations are refunded through
Razorpay once each, only with the confirmation, failures kept and retryable,
every refund recorded, audit-logged and emailed; two requests at once still
refund each payment once; a registration without an order is listed for a
manual refund; only the Super Admin and the event's owner may act.
"""
import re

from tests import test_paid_events
from tests.test_integration_flow import _login, _unique, _user
from tests.test_paid_events import _admin, _paid_registration

rzp = test_paid_events.rzp
paid = test_paid_events.paid


def _cancelled_with_three(d):
    regs = [_paid_registration(d) for _ in range(3)]
    d['db'].collection('events').document(d['event_id']).update({'status': 'cancelled'})
    return regs


def _refund_mail(d, email):
    return [m for m in d['rzp']['mail'] if m['to'] == email and m['subject'].startswith('Refund')]


def _audits(d):
    return [e.to_dict() for e in d['db'].collection('audit_log').where('action', '==', 'PAYMENT_REFUNDED').stream()
            if d['event_id'] in (e.to_dict().get('details') or '')]


# ── Criteria 1 and 2 ────────────────────────────────────────────────────────

def test_refund_all_needs_the_confirmation_then_refunds_each_payment_once(paid):
    d = paid
    regs = _cancelled_with_three(d)
    admin, _ = _admin(d)
    page = admin.get(f"/admin/events/{d['event_id']}/refunds").get_data(as_text=True)
    assert all(pay in page for _, _, _, pay in regs)

    admin.post(f"/admin/events/{d['event_id']}/refund_all")                    # no confirmation
    assert d['rzp']['refunds'] == []
    admin.post(f"/admin/events/{d['event_id']}/refund_all", data={'confirm': 'yes'})
    assert sorted(d['rzp']['refunds']) == sorted((pay, {'amount': 25000}) for _, _, _, pay in regs)
    for reg_id, email, order, pay in regs:
        row = test_paid_events._order_row(order['order_id'])
        assert row['status'] == 'refunded' and row['refund_id'].startswith('rfnd_')
        reg = d['db'].collection('registrations').document(reg_id).get().to_dict()
        assert reg['payment_status'] == 'Refunded' and reg['status'].lower() == 'cancelled'
        assert len(_refund_mail(d, email)) == 1
    assert len(_audits(d)) == 3

    admin.post(f"/admin/events/{d['event_id']}/refund_all", data={'confirm': 'yes'})   # pressing again
    assert len(d['rzp']['refunds']) == 3 and len(_audits(d)) == 3


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_a_failed_refund_is_listed_and_only_it_is_retried(paid):
    d = paid
    regs = _cancelled_with_three(d)
    failing = regs[1]
    d['rzp']['refund_fail'] = {failing[3]: 'gateway timeout'}
    admin, _ = _admin(d)
    admin.post(f"/admin/events/{d['event_id']}/refund_all", data={'confirm': 'yes'})
    assert len(d['rzp']['refunds']) == 3
    row = test_paid_events._order_row(failing[2]['order_id'])
    assert row['status'] == 'paid' and 'gateway timeout' in row['failure_reason']
    assert 'gateway timeout' in admin.get(f"/admin/events/{d['event_id']}/refunds").get_data(as_text=True)
    assert _refund_mail(d, failing[1]) == []

    d['rzp']['refund_fail'] = {}
    admin.post(f"/admin/events/{d['event_id']}/refund_all", data={'confirm': 'yes'})
    assert [p for p, _ in d['rzp']['refunds']].count(failing[3]) == 2              # retried
    assert len(d['rzp']['refunds']) == 4                                          # only that one
    assert test_paid_events._order_row(failing[2]['order_id'])['status'] == 'refunded'
    assert len(_refund_mail(d, failing[1])) == 1


# ── "To test later": concurrency and a registration without an order ───────

def test_two_requests_at_once_refund_each_payment_once(paid):
    d = paid
    regs = _cancelled_with_three(d)
    first, _ = _admin(d)
    second, _ = _admin(d)
    # While the first request is inside its first Razorpay call, a second one runs to the end
    d['rzp']['during_refund'] = lambda: second.post(f"/admin/events/{d['event_id']}/refund_all", data={'confirm': 'yes'})
    first.post(f"/admin/events/{d['event_id']}/refund_all", data={'confirm': 'yes'})
    paid_ids = [p for p, _ in d['rzp']['refunds']]
    assert sorted(paid_ids) == sorted(pay for _, _, _, pay in regs)                # once each
    assert len(_audits(d)) == 3


def test_a_registration_without_an_order_is_listed_for_a_manual_refund(paid):
    d = paid
    d['db'].collection('registrations').document(_unique('REG')).set({
        'event_id': d['event_id'], 'lead_email': f"{_unique('cash')}@test.edu", 'lead_name': 'Paid In Cash',
        'status': 'Confirmed', 'payment_status': 'Paid', 'amount_paid': 250})
    d['db'].collection('events').document(d['event_id']).update({'status': 'cancelled'})
    admin, _ = _admin(d)
    page = admin.get(f"/admin/events/{d['event_id']}/refunds").get_data(as_text=True)
    assert 'Paid In Cash' in page and 'No Razorpay order on record: refund by hand' in page
    admin.post(f"/admin/events/{d['event_id']}/refund_all", data={'confirm': 'yes'})
    assert d['rzp']['refunds'] == []


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_only_the_admin_and_the_owner_may_refund_and_only_a_cancelled_event(paid):
    d = paid
    regs = [_paid_registration(d)]
    other = f"{_unique('otherspoc')}@test.edu"
    _user(d['db'], other, 'ClubSPOC')
    stranger = _login(d['app'], other, 'ClubSPOC')
    assert stranger.get(f"/admin/events/{d['event_id']}/refunds").status_code == 403
    assert stranger.post(f"/admin/events/{d['event_id']}/refund_all", data={'confirm': 'yes'}).status_code == 403

    # Not cancelled yet: refused even for the owner
    resp = d['owner'].post(f"/admin/events/{d['event_id']}/refund_all", data={'confirm': 'yes'}, follow_redirects=True)
    assert re.search(r'only for cancelled events', resp.get_data(as_text=True)) and d['rzp']['refunds'] == []

    d['db'].collection('events').document(d['event_id']).update({'status': 'cancelled'})
    assert d['owner'].get(f"/admin/events/{d['event_id']}/refunds").status_code == 200
    d['owner'].post(f"/admin/events/{d['event_id']}/refund_all", data={'confirm': 'yes'})
    assert [p for p, _ in d['rzp']['refunds']] == [regs[0][3]]
