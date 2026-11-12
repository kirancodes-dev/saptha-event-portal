"""
tests/test_waitlist_manual.py — UPG-243 on the real database layer.

Owner, 2026-11-12: "until the SPOC accepts, the waiting team should stay on
the waitlist; stop pushing teams from the waitlist automatically, or keep a
toggle in the event". The hosting SPOC switches moving up on its own off (it
stays on for events that don't): a freed seat then stays free and nobody is
registered or emailed until the SPOC accepts; a new sign-up joins the waitlist
while anyone waits, so nobody takes the seat ahead of them; the SPOC's Accept
still registers anyone. Switched back on, the old rule applies.
"""
from tests import test_spoc_waitlist as _wl
from tests.test_integration_flow import _login, _unique, _user
from tests.test_seat_email import _taker
from tests.test_spoc_waitlist import _accept, _entry, _full_event, _join, _page, _regs_of

host = _wl.host   # UPG-211's fixture, through UPG-230's tests


def _switch(h, event_id, on):
    return h['owner'].post(f'/coordinator/registrations/{event_id}/waitlist_auto', data={'auto': 'on' if on else 'off'})


def test_switched_off_a_freed_seat_waits_for_the_spocs_accept(host):
    h = host
    event_id = _full_event(h)
    wl_id, lead, _ = _join(h, event_id, 'Patient Team')
    assert 'data-waitlist-auto="on"' in _page(h['owner'], event_id)       # on unless switched off
    assert _switch(h, event_id, False).status_code == 302
    assert h['db'].collection('events').document(event_id).get().to_dict()['waitlist_auto'] is False
    assert 'data-waitlist-auto="off"' in _page(h['owner'], event_id)

    h['emails'].clear()
    h['cancel'](h['owner'], event_id, _taker(h, event_id), 'Duplicate team')
    assert h['count'](event_id) == 0                                        # the seat is free...
    assert _entry(h, wl_id)['status'] == 'waiting' and _regs_of(h, event_id, lead) == []
    assert [m for m in h['emails'] if m['to'] == lead] == []                # ...and nobody was moved up

    # A newcomer can't take the free seat ahead of the team waiting
    _, newcomer, _ = _join(h, event_id, 'Newcomer')
    assert _regs_of(h, event_id, newcomer) == []

    # The waiting team's card says the organiser chooses
    _user(h['db'], lead, 'Student')
    dash = _login(h['app'], lead, 'Student').get('/participant/dashboard').get_data(as_text=True)
    assert 'The organiser chooses who gets a seat' in dash

    # The SPOC accepts: now they're registered and emailed
    _accept(h['owner'], event_id, wl_id)
    [reg] = _regs_of(h, event_id, lead)
    assert reg['status'] == 'Confirmed' and h['count'](event_id) == 1
    assert len([m for m in h['emails'] if m['to'] == lead]) == 1


def test_switched_back_on_the_first_in_line_moves_up_again(host):
    h = host
    event_id = _full_event(h)
    _switch(h, event_id, False)
    _switch(h, event_id, True)
    _, lead, _ = _join(h, event_id, 'Quick Team')
    h['cancel'](h['owner'], event_id, _taker(h, event_id), 'Duplicate team')
    [reg] = _regs_of(h, event_id, lead)
    assert reg['status'] == 'Confirmed'


def test_only_the_hosting_spoc_switches_it(host):
    h = host
    event_id = _full_event(h)
    other = f"{_unique('otherspoc')}@test.edu"
    _user(h['db'], other, 'ClubSPOC')
    resp = _login(h['app'], other, 'ClubSPOC').post(f'/coordinator/registrations/{event_id}/waitlist_auto',
                                                     data={'auto': 'off'})
    assert resp.status_code == 403
    assert 'waitlist_auto' not in h['db'].collection('events').document(event_id).get().to_dict()
