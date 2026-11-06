"""
tests/test_checkout_coupon.py — UPG-56: the checkout page has a coupon field
whose script sends the code with the order, and the price preview shows the
server's discounted total for a valid code, or the server's error and the full
price for an invalid one. The server's price stays the only price.
"""
import re

from tests import test_coupon_limits
from tests.test_coupon_limits import _payer

shop = test_coupon_limits.shop


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_checkout_page_has_a_coupon_field_whose_code_goes_with_the_order(shop):
    d = shop
    page = _payer(d).get(f"/payment/checkout/{d['event_id']}").get_data(as_text=True)
    assert 'id="coupon-input"' in page and 'id="apply-coupon-btn"' in page
    assert re.search(r"payload\.coupon\s*=\s*appliedCoupon", page)          # sent with the order
    assert "fetch('/payment/create_order'" in page and "fetch('/payment/price_preview'" in page


def test_the_order_is_priced_with_the_code_on_the_server(shop):
    d = shop
    code = d['coupon'](5)
    order = _payer(d).post('/payment/create_order', json={'event_id': d['event_id'], 'coupon': code}).get_json()
    assert order['amount'] == 25000                                          # ₹500 less 50%


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_preview_shows_the_servers_discount_or_its_error_and_the_full_price(shop):
    d = shop
    payer = _payer(d)
    code = d['coupon'](5)
    good = payer.post('/payment/price_preview', json={'event_id': d['event_id'], 'coupon': code}).get_json()
    assert good['valid'] is True and good['fee'] == 500 and good['discount'] == 250 and good['total'] == 250
    bad = payer.post('/payment/price_preview', json={'event_id': d['event_id'], 'coupon': 'NOPE123'}).get_json()
    assert bad['valid'] is False and bad['error'] and bad['total'] == 500
    plain = payer.post('/payment/price_preview', json={'event_id': d['event_id']}).get_json()
    assert plain['valid'] is True and plain['total'] == 500 and plain['discount'] == 0
