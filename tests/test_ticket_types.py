"""
tests/test_ticket_types.py — UPG-155 on the real database layer: an event's
ticket types (early bird, a seat limit per type, a team or per-head price),
set in the wizard, chosen on the registration form and charged at checkout.
"""
import datetime
import os
import threading

import pytest

import routes_payment
import services_ticket_types as tt
from tests.test_integration_flow import _login, _unique, _user
from tests.test_paid_events import _verify

SECRET = 'test-razorpay-secret-for-pytest'
EARLY_ENDS = datetime.date(2030, 1, 31)
DURING_EARLY = datetime.date(2030, 1, 15)
AFTER_EARLY = datetime.date(2030, 2, 10)


@pytest.fixture
def shop(real_app, monkeypatch):
    flask_app, db = real_app
    orders = {}

    class FakeOrders:
        def create(self, data):
            order = dict(data, id=f"order_{_unique('rzp')}", status='created')
            orders[order['id']] = order
            return order

        def fetch(self, order_id):
            return dict(orders[order_id], status='paid', amount_paid=orders[order_id]['amount'])

    class FakeClient:
        order = FakeOrders()

    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_ID', 'rzp_test_pytest')
    monkeypatch.setattr(routes_payment, 'RAZORPAY_KEY_SECRET', SECRET)
    monkeypatch.setattr(routes_payment, '_rzp', lambda: FakeClient())
    spoc = f"{_unique('ttspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    day = {'today': DURING_EARLY}
    monkeypatch.setattr(tt, 'today', lambda: day['today'])
    return {'app': flask_app, 'db': db, 'spoc': _login(flask_app, spoc, 'ClubSPOC'), 'day': day}


def _event(d, tickets, team=False, reg_fee=0):
    """An event made in the wizard with these ticket-type rows."""
    title = _unique('Ticket Night')
    form = {
        'title': title, 'category': 'Technical', 'description': 'desc', 'rules': 'rules',
        'date': '2030-06-01', 'time': '10:00', 'reg_deadline': '2030-06-01', 'venue': 'Hall A',
        'participation_type': 'Team' if team else 'Individual',
        'team_min': '1', 'team_max': '4' if team else '1', 'max_participants': '50',
        'reg_fee': str(reg_fee), 'visibility': 'public',
    }
    keys = ('name', 'price', 'start', 'end', 'seats', 'per', 'who')
    data = list(form.items())
    for row in tickets:
        data += [(f'tt_{k}', str(row.get(k, ''))) for k in keys] + [('tt_id', '')]
    from werkzeug.datastructures import MultiDict
    resp = d['spoc'].post('/spoc/create_event', data=MultiDict(data))
    assert resp.status_code == 302, resp.get_data(as_text=True)[:500]
    event_id = next(doc.id for doc in d['db'].collection('events').where('title', '==', title).stream())
    d['db'].collection('events').document(event_id).update({'status': 'registration_open'})
    return event_id


def _ticket_id(d, event_id, name):
    ev = d['db'].collection('events').document(event_id).get().to_dict()
    return next(t['id'] for t in ev['ticket_types'] if t['name'] == name)


def _register(d, event_id, ticket_id, members=0):
    client = d['app'].test_client()
    form = {'privacy_consent': 'yes', 'full_name': 'Tick Et', 'email': f"{_unique('buyer')}@test.edu",
            'phone': '9876543210', 'usn': '1SN20CS042', 'ticket_type': ticket_id}
    if members:
        form['team_name'] = _unique('Team')
        for i in range(1, members + 1):
            form.update({f'member_{i}_name': f'Mate {i}', f'member_{i}_email': f"{_unique('mate')}@test.edu"})
    return client, client.post(f'/forms/submit/{event_id}', data=form)


def _order(client, event_id):
    return client.post('/payment/create_order', json={'event_id': event_id})


def _regs(d, event_id):
    return [doc.to_dict() for doc in d['db'].collection('registrations').where('event_id', '==', event_id).stream()]


# ── Criterion 1: early bird before its end date, refused after ─────────────

def test_early_bird_is_charged_before_its_end_and_refused_after(shop):
    d = shop
    event_id = _event(d, [{'name': 'Early bird', 'price': 200, 'end': EARLY_ENDS.isoformat()},
                          {'name': 'Regular', 'price': 350, 'start': '2030-02-01'}])
    early, regular = _ticket_id(d, event_id, 'Early bird'), _ticket_id(d, event_id, 'Regular')

    # Before the end date: early bird is charged; regular isn't on sale yet
    client, resp = _register(d, event_id, early)
    assert resp.headers['Location'] == f'/payment/checkout/{event_id}'
    assert _order(client, event_id).get_json()['amount'] == 20000
    _, resp = _register(d, event_id, regular)
    assert resp.headers['Location'] == f'/forms/register/{event_id}'

    # After it: the form refuses early bird, and an order for a form sent in
    # time but paid late is refused too
    d['day']['today'] = AFTER_EARLY
    late = _order(client, event_id)
    assert late.status_code == 400 and 'no longer on sale' in late.get_json()['error']
    refused_client, resp = _register(d, event_id, early)
    assert resp.headers['Location'] == f'/forms/register/{event_id}'
    page = refused_client.get(f'/forms/register/{event_id}').get_data(as_text=True)
    assert 'Early bird is no longer on sale.' in page

    # Regular is charged after
    client, resp = _register(d, event_id, regular)
    assert resp.headers['Location'] == f'/payment/checkout/{event_id}'
    assert _order(client, event_id).get_json()['amount'] == 35000


def test_a_ticket_type_must_be_chosen_when_the_event_has_them(shop):
    d = shop
    event_id = _event(d, [{'name': 'Regular', 'price': 0}])
    client, resp = _register(d, event_id, '')
    assert resp.headers['Location'] == f'/forms/register/{event_id}'
    assert 'Please choose a ticket type.' in client.get(f'/forms/register/{event_id}').get_data(as_text=True)
    assert _regs(d, event_id) == []


# ── Criterion 2: a type's seat limit ────────────────────────────────────────

def test_a_type_with_two_seats_refuses_the_third(shop):
    d = shop
    event_id = _event(d, [{'name': 'Limited', 'price': 0, 'seats': 2}, {'name': 'Open', 'price': 0}])
    limited = _ticket_id(d, event_id, 'Limited')
    for _ in range(2):
        assert _register(d, event_id, limited)[1].headers['Location'] == '/registration/confirmed'
    client, resp = _register(d, event_id, limited)
    assert resp.headers['Location'] == f'/forms/register/{event_id}'
    page = client.get(f'/forms/register/{event_id}').get_data(as_text=True)
    assert 'Limited is sold out' in page
    assert len(_regs(d, event_id)) == 2
    # Another type still sells
    assert _register(d, event_id, _ticket_id(d, event_id, 'Open'))[1].headers['Location'] == '/registration/confirmed'


def test_two_payments_completing_for_the_last_seat_register_one(shop):
    d = shop
    event_id = _event(d, [{'name': 'VIP', 'price': 500, 'seats': 1}])
    vip = _ticket_id(d, event_id, 'VIP')
    # Both fill the form while the seat is free, and both start paying
    payers = [_register(d, event_id, vip)[0] for _ in range(2)]
    orders = [_order(c, event_id).get_json()['order_id'] for c in payers]
    first = _verify(payers[0], {'event_id': event_id}, orders[0], f"pay_{_unique('a')}")
    second = _verify(payers[1], {'event_id': event_id}, orders[1], f"pay_{_unique('b')}")
    assert 'redirect' in first.get_json()
    # The second payment is kept for the admin to refund, not lost
    assert second.status_code == 202 and second.get_json()['recorded'] is True
    from services_payments import get_order
    assert get_order(orders[1])['failure_reason'] == 'ticket_sold_out'
    assert len(_regs(d, event_id)) == 1 and tt.sold(event_id, vip) == 1


@pytest.mark.skipif(not os.environ.get('TEST_DATABASE_URL', '').startswith('postgresql'),
                    reason='concurrency is checked on PostgreSQL')
def test_ten_payments_at_once_take_exactly_two_seats(shop):
    d = shop
    event_id = _event(d, [{'name': 'Pair', 'price': 100, 'seats': 2}])
    pair = _ticket_id(d, event_id, 'Pair')
    payers = [_register(d, event_id, pair)[0] for _ in range(10)]
    orders = [_order(c, event_id).get_json()['order_id'] for c in payers]
    start = threading.Barrier(10)
    results = [None] * 10

    def pay(i):
        start.wait()
        results[i] = _verify(payers[i], {'event_id': event_id}, orders[i], f"pay_{_unique('c')}")

    threads = [threading.Thread(target=pay, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sum(1 for r in results if r is not None and 'redirect' in (r.get_json() or {})) == 2
    assert len(_regs(d, event_id)) == 2 and tt.sold(event_id, pair) == 2


def test_take_seat_is_race_free_on_the_database(real_app):
    event_id = _unique('race')
    ticket = {'id': 'gold', 'seats': 3}
    results = []
    start = threading.Barrier(8)

    def grab():
        start.wait()
        results.append(tt.take_seat(event_id, ticket))

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert results.count(True) == 3 and tt.sold(event_id, 'gold') == 3


def test_a_cancelled_registration_frees_its_seat(shop):
    d = shop
    event_id = _event(d, [{'name': 'Solo', 'price': 0, 'seats': 1}])
    solo = _ticket_id(d, event_id, 'Solo')
    assert _register(d, event_id, solo)[1].headers['Location'] == '/registration/confirmed'
    reg = next(doc for doc in d['db'].collection('registrations').where('event_id', '==', event_id).stream())
    from routes_participant import cancel_registration_record
    cancel_registration_record(reg.id, reg.to_dict(), 'test')
    assert tt.sold(event_id, solo) == 0
    assert _register(d, event_id, solo)[1].headers['Location'] == '/registration/confirmed'


# ── Criterion 3: per team or per head ───────────────────────────────────────

def test_a_team_type_charges_once_and_a_per_head_type_per_member(shop):
    d = shop
    event_id = _event(d, [{'name': 'Team pass', 'price': 300, 'per': 'registration'},
                          {'name': 'Per head', 'price': 150, 'per': 'person'}], team=True)
    client, resp = _register(d, event_id, _ticket_id(d, event_id, 'Team pass'), members=2)
    assert resp.headers['Location'] == f'/payment/checkout/{event_id}'
    assert _order(client, event_id).get_json()['amount'] == 30000          # one price, three people
    client, resp = _register(d, event_id, _ticket_id(d, event_id, 'Per head'), members=2)
    assert resp.headers['Location'] == f'/payment/checkout/{event_id}'
    assert _order(client, event_id).get_json()['amount'] == 45000          # ₹150 × 3


# ── Criterion 4: no types, priced as before ─────────────────────────────────

def test_an_event_without_types_is_priced_by_fee_for():
    from services_payments import fee_for, registration_fee
    event = {'fees': {'regular': 100, 'faculty': 300, 'external': 0}, 'ticket_tiers': [{'name': 'VIP', 'price': 9}]}
    for group in ('student', 'faculty', 'external', ''):
        assert registration_fee(event, group, '', 4) == fee_for(event, group)
    assert registration_fee({'entry_fee': 250}) == fee_for({'entry_fee': 250}) == 250


def test_an_event_without_types_charges_its_fee_at_checkout(shop):
    d = shop
    event_id = _event(d, [], reg_fee=400)
    client, resp = _register(d, event_id, '')
    assert resp.headers['Location'] == f'/payment/checkout/{event_id}'
    assert _order(client, event_id).get_json()['amount'] == 40000
    ev = d['db'].collection('events').document(event_id).get().to_dict()
    assert ev['ticket_types'] == []


# ── Criterion 5: the export ─────────────────────────────────────────────────

def test_the_export_shows_each_registrations_ticket_type(shop):
    d = shop
    event_id = _event(d, [{'name': 'Student pass', 'price': 0}, {'name': 'Guest pass', 'price': 0}])
    _register(d, event_id, _ticket_id(d, event_id, 'Student pass'))
    _register(d, event_id, _ticket_id(d, event_id, 'Guest pass'))
    import services_export
    assert services_export.COLUMNS[-1] == 'Ticket Type'
    rows = services_export.registration_rows(d['db'], event_id)
    assert sorted(r[-1] for r in rows) == ['Guest pass', 'Student pass']
    csv_text = services_export.to_csv(rows)
    assert 'Ticket Type' in csv_text.splitlines()[0]


# ── The wizard and the form ─────────────────────────────────────────────────

def test_the_wizard_rejects_a_sale_ending_before_it_starts(shop):
    d = shop
    errors = []
    from werkzeug.datastructures import MultiDict
    form = MultiDict([('tt_name', 'Odd'), ('tt_price', '10'), ('tt_start', '2030-02-01'), ('tt_end', '2030-01-01'),
                      ('tt_seats', ''), ('tt_per', 'registration'), ('tt_who', ''), ('tt_id', '')])
    tt.from_form(form.getlist, errors)
    assert errors == ['Odd: the sale ends before it starts.']


def test_the_form_lists_each_type_with_its_price_and_seats(shop):
    d = shop
    event_id = _event(d, [{'name': 'Early bird', 'price': 200, 'end': EARLY_ENDS.isoformat(), 'seats': 5},
                          {'name': 'Faculty', 'price': 500, 'who': 'faculty'}])
    page = d['app'].test_client().get(f'/forms/register/{event_id}').get_data(as_text=True)
    assert 'Early bird' in page and '₹200' in page and '5 left' in page
    assert 'for Faculty only' in page


def test_a_paid_type_makes_a_waitlist_promotion_paid():
    from routes_waitlist import promotion_terms
    ev = {'title': 'T', 'ticket_types': [{'id': 'p', 'name': 'Paid', 'price': 100},
                                         {'id': 'f', 'name': 'Free', 'price': 0}]}
    assert promotion_terms(ev, 'R1', {'ticket_type_id': 'p'})['is_paid'] is True
    assert promotion_terms(ev, 'R1', {'ticket_type_id': 'f'})['is_paid'] is False
    assert promotion_terms({'title': 'T', 'fee': 50}, 'R1')['is_paid'] is True
