"""
tests/test_screening_removed.py — UPG-246: the waitlist's screening round
(UPG-238) is removed at the owner's request (2026-11-12): no organiser
section, no score column or "Accept the top N", no "Take the screening round"
for people waiting, and its routes are gone. Accept one by one stays.
"""
from tests import test_spoc_waitlist as _wl
from tests.test_integration_flow import _login, _user
from tests.test_spoc_waitlist import _accept, _full_event, _join, _page, _regs_of

host = _wl.host


def test_the_screening_round_is_gone_and_accept_stays(host):
    h = host
    event_id = _full_event(h)
    wl_id, lead, _ = _join(h, event_id, 'Plain Wait')
    page = _page(h['owner'], event_id)
    for gone in ('data-screening', 'data-accept-top', 'Screening round', 'Accept the top'):
        assert gone not in page
    assert 'data-accept-waitlist' in page
    for action in ('question', 'times', 'open', 'close'):
        assert h['owner'].post(f'/coordinator/registrations/{event_id}/screening/{action}').status_code == 404
    assert h['owner'].post(f'/coordinator/registrations/{event_id}/accept_top', data={'n': '1'}).status_code == 404

    _user(h['db'], lead, 'Student')
    client = _login(h['app'], lead, 'Student')
    assert client.get(f'/participant/screening/{event_id}').status_code == 404
    assert 'screening' not in client.get('/participant/dashboard').get_data(as_text=True).lower()

    _accept(h['owner'], event_id, wl_id)
    assert [r['status'] for r in _regs_of(h, event_id, lead)] == ['Confirmed']
