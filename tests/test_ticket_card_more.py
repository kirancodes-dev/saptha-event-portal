"""
tests/test_ticket_card_more.py — UPG-366: each ticket on the student's
dashboard shows one main button (View ticket); Edit details, the team page,
Badge and Event info sit under "More", with Cancel last and set apart, still
asking to confirm, and it still cancels.
"""
import re

from tests import test_registration_edit as _edit

team = _edit.team   # the lead Lena, members Hima and Alif (UPG-225's fixture)
_reg = _edit._reg


def _actions(html, rid):
    """The card's actions: (shown on the card, folded under More)."""
    for block in re.findall(r'data-ticket-actions>(.*?)</details>', html, re.S):
        if f'href="/ticket/{rid}"' in block:
            shown, more = block.split('<details', 1)
            return shown, more
    raise AssertionError('no ticket card for the registration')


def test_one_main_button_and_the_rest_under_more_with_cancel_last(team):
    t = team
    rid = t['reg_id']
    html = t['lead_client'].get('/participant/dashboard').get_data(as_text=True)
    shown, more = _actions(html, rid)

    assert len(re.findall(r'class="btn btn-primary', shown)) == 1 and f'href="/ticket/{rid}"' in shown
    for hidden in ('data-edit-details', f'/teams/{rid}', f'/participant/badge/{rid}', f"/event/{t['event_id']}",
                   f'/participant/cancel/{rid}'):
        assert hidden not in shown, hidden
        assert hidden in more, hidden
    assert re.search(r'<summary[^>]*>.*More</summary>', more, re.S)

    # Cancel comes after everything else, apart, and asks first
    cancel = more.index(f'/participant/cancel/{rid}')
    assert all(more.index(x) < cancel for x in ('data-edit-details', f'/participant/badge/{rid}', f"/event/{t['event_id']}"))
    assert 'data-ticket-cancel' in more and 'data-confirm="Cancel registration for' in more


def test_cancel_from_more_still_cancels(team):
    t = team
    rid = t['reg_id']
    resp = t['lead_client'].post(f'/participant/cancel/{rid}')
    assert resp.status_code == 302
    assert _reg(t)['status'] == 'Cancelled'
    html = t['lead_client'].get('/participant/dashboard').get_data(as_text=True)
    assert f'/participant/cancel/{rid}' not in html     # nothing left to cancel
