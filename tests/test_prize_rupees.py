"""
tests/test_prize_rupees.py — UPG-367: a prize typed as a plain amount shows
in rupees ("3000" is "₹3,000"); anything else ("Trophy and goodies") shows as
typed, on the public event page.
"""
import pytest

import services_registration_state as rs
from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.mark.parametrize('typed, shown', [
    ('3000', '₹3,000'), ('3,000', '₹3,000'), ('Rs. 3000', '₹3,000'), ('₹5000', '₹5,000'), ('3000/-', '₹3,000'),
    ('100000', '₹1,00,000'), ('1234567', '₹12,34,567'), ('2500.50', '₹2,500.50'), ('12', '₹12'),
    ('Trophy and goodies', 'Trophy and goodies'), ('₹2000 + trophy', '₹2000 + trophy'), ('—', '—'), ('', ''),
])
def test_a_plain_amount_is_in_rupees_and_other_text_as_typed(typed, shown):
    assert rs.prize_text(typed) == shown


def test_the_event_page_shows_prizes_in_rupees(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('pspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Prize Event'), '2031-03-20', team=False)
    db.collection('events').document(event_id).update(
        {'status': 'active', 'prizes': {'1st': '3000', '2nd': 'Trophy and goodies', '3rd': '1000'}})
    page = flask_app.test_client().get(f'/event/{event_id}').get_data(as_text=True)
    assert '<div class="prize-val">₹3,000</div>' in page
    assert '<div class="prize-val">Trophy and goodies</div>' in page
    assert '<div class="prize-val">₹1,000</div>' in page
    assert '<div class="prize-val">3000</div>' not in page
