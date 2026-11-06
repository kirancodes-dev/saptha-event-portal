"""
tests/test_untimed_events.py — UPG-47 on the real database layer: an event
created through the SPOC form without a time reads back with its date's whole
day (the wizard fills 00:00–23:59), and one saved with no times at all through
the database layer reads back with none (never its save time), and its page says the time is to be announced; room
clashes for events saved without times go by their date: the same room on the
same day clashes, on another day it doesn't.
"""
import pytest

from tests.test_venue_booking_on_create import _bookings, _events, venue  # noqa: F401  (fixture)

DAY, OTHER_DAY = '2031-05-05', '2031-05-06'


def _create(d, title, day, room=True):
    data = {'title': title, 'category': 'Technical', 'description': 'desc', 'rules': 'rules',
            'date': day, 'reg_deadline': day, 'participation_type': 'Individual', 'team_min': '1',
            'team_max': '1', 'max_participants': '50', 'reg_fee': '0', 'visibility': 'public'}
    if room:
        data['room_id'] = d['room_id']
    else:
        data['venue'] = 'Main Hall'                 # the form needs a venue or a room
    return d['spoc'].post('/spoc/create_event', data=data)


def test_an_event_saved_without_a_time_has_no_start_or_end(venue):  # noqa: F811
    d = venue
    from tests.test_integration_flow import _unique
    title = _unique('Untimed Talk')
    assert _create(d, title, DAY, room=False).status_code == 302
    [event] = _events(d, title)
    for key in ('start_datetime', 'end_datetime'):
        value = str(event.get(key) or '')
        assert value == '' or value.startswith(DAY), (key, value)   # never the save time (DAY is years away)
    d['db'].collection('events').document(event['id']).update({'status': 'registration_open'})
    page = d['app'].test_client().get(f"/event/{event['id']}").get_data(as_text=True)
    assert 'Time to be announced' in page


def test_the_database_layer_keeps_missing_times_empty(venue):  # noqa: F811
    """Other ways in (API v1 drafts, seeds) save events with no times at all; the
    SQL layer used to fill in the save time."""
    from tests.test_integration_flow import _unique
    event_id = _unique('EVT')
    d = venue
    d['db'].collection('events').document(event_id).set({'title': 'No Times', 'date': DAY, 'status': 'draft',
                                                         'category': 'Technical'})
    event = d['db'].collection('events').document(event_id).get().to_dict()
    assert not event.get('start_datetime') and not event.get('end_datetime')


@pytest.mark.parametrize('second_day, clashes', [(DAY, True), (OTHER_DAY, False)])
def test_untimed_events_clash_by_their_date(venue, second_day, clashes):  # noqa: F811
    d = venue
    from tests.test_integration_flow import _unique
    first = _unique('Untimed A')
    assert _create(d, first, DAY).status_code == 302
    [event] = _events(d, first)
    d['admin'].post(f"/admin/events/approve/{event['id']}")
    assert [b['status'] for b in _bookings(d, event['id'])] == ['confirmed']

    second = _unique('Untimed B')
    resp = _create(d, second, second_day)
    if clashes:
        assert resp.status_code == 400 and 'already booked' in resp.get_data(as_text=True)
        assert _events(d, second) == []
    else:
        assert resp.status_code == 302 and len(_events(d, second)) == 1
