"""
tests/test_spoc_panel_figures.py — UPG-254 on the real database layer.

The SPOC's event panel showed a "Venue Wayfinder Map" with made-up room
occupancy for every event, and an "Est. Revenue" of the fee times the
registration count. The map is gone; a paid event shows what its paid
registrations actually paid, and a free event shows no money tile.
"""
from tests.test_integration_flow import _create_event, _login, _unique, _user

INVENTED = ('Wayfinder', '310 / 400', '96% FULL', '48 / 50', 'Est. Revenue', 'Tactical Console Layout')


def _panel(page, event_id):
    start = page.index(f'id="detail-panel-{event_id}"')
    end = page.find('id="detail-panel-', start + 1)
    return page[start:end if end > 0 else len(page)]


def test_the_panel_shows_no_invented_figures_and_real_money_for_a_paid_event_only(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('figspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    day = '2030-02-10'
    free_id = _create_event(client, db, _unique('Free Fest'), day, fee=0, team=False)
    paid_id = _create_event(client, db, _unique('Paid Fest'), day, fee=200, team=False)

    def reg(event_id, **fields):
        db.collection('registrations').document(_unique('REG')).set(dict(
            {'event_id': event_id, 'lead_email': f"{_unique('p')}@test.edu", 'status': 'Confirmed'}, **fields))

    reg(free_id)
    reg(free_id)
    reg(paid_id, payment_status='paid', amount_paid=200)
    reg(paid_id, payment_status='paid', amount_paid=150)            # a coupon
    reg(paid_id, payment_status='refunded', amount_paid=200)        # refunded: not money received
    reg(paid_id, payment_status='pending')                          # not paid yet

    page = client.get('/spoc/dashboard').get_data(as_text=True)
    for text in INVENTED:
        assert text not in page, text

    free, paid = _panel(page, free_id), _panel(page, paid_id)
    assert 'data-received' not in free
    assert 'data-received' in paid
    received = paid[paid.index('data-received'):]
    assert '₹350' in received[:received.index('</div>\n              </div>')]
    assert '₹800' not in paid and '₹600' not in paid                  # not fee × count
