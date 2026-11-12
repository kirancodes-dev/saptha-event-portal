"""
tests/test_waitlist_json_access.py — UPG-232 on the real database layer.

The old JSON routes `/waitlist/list/<event_id>` (each person's name, email,
phone and form answers) and `/waitlist/promote/<event_id>` checked the role
only. Now another event's SPOC and a coordinator not on the event get 403 and
nothing is promoted; the hosting SPOC still lists and promotes.
"""
from tests import test_spoc_waitlist as _wl
from tests.test_integration_flow import _login, _unique, _user
from tests.test_spoc_waitlist import _entry, _full_event, _join

host = _wl.host   # UPG-211's fixture, through UPG-230's tests


def test_only_the_events_organisers_list_and_promote(host):
    h = host
    event_id = _full_event(h)
    wl_id, lead, _ = _join(h, event_id, 'Private Team')
    other = f"{_unique('otherspoc')}@test.edu"
    _user(h['db'], other, 'ClubSPOC')
    coord = f"{_unique('coord')}@test.edu"
    _user(h['db'], coord, 'EventCoordinator')
    for client in (_login(h['app'], other, 'ClubSPOC'), _login(h['app'], coord, 'EventCoordinator')):
        listed = client.get(f'/waitlist/list/{event_id}')
        assert listed.status_code == 403 and lead not in listed.get_data(as_text=True)
        assert client.post(f'/waitlist/promote/{event_id}').status_code == 403
    assert _entry(h, wl_id)['status'] == 'waiting'                      # nothing promoted

    # The hosting SPOC still lists and promotes
    listed = h['owner'].get(f'/waitlist/list/{event_id}')
    assert listed.status_code == 200 and listed.get_json()['waitlist'][0]['id'] == wl_id
    assert h['owner'].post(f'/waitlist/promote/{event_id}').status_code == 200
    assert _entry(h, wl_id)['status'] == 'promoted'


def test_an_unknown_event_is_404(host):
    assert host['owner'].get('/waitlist/list/no-such-event').status_code == 404
