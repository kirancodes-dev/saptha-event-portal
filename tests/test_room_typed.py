"""
tests/test_room_typed.py — UPG-313: in the draft, the SPOC can type a room
number for a team instead of picking one. A typed room that's in the list
(whatever its capitals) is that room; a new one joins the list with seats for
the team, so the final check and Allocate final accept it.
"""
from tests.test_room_allocation_final import host, rooms  # noqa: F401  (the UPG-306 fixtures)


def _move(h, event_id, reg_id, room, typed=True, client=None):
    return (client or h['owner']).post(f'/spoc/reassign_room/{event_id}/{reg_id}', json={'room': room, 'typed': typed})


def test_the_list_offers_to_type_a_room(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    h['team'](event_id, 'Typers')
    h['setup'](h['owner'], event_id, [('101', 10)])
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert 'data-room-type' in page and 'Type a room no.' in page


def test_a_typed_new_room_joins_the_list_and_can_be_allocated(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    t = h['team'](event_id, 'Quad', people=4)
    h['setup'](h['owner'], event_id, [('101', 10)])
    data = _move(h, event_id, t['id'], '  Seminar Hall 3 ').get_json()
    assert data['status'] == 'ok' and data['room'] == 'Seminar Hall 3' and data['added'] == 'Seminar Hall 3'
    p = h['plan'](event_id)
    assert p['draft'][t['id']] == 'Seminar Hall 3'
    assert {'name': 'Seminar Hall 3', 'capacity': 4} in [{k: r[k] for k in ('name', 'capacity')} for r in p['rooms']]
    review = h['owner'].get(f'/spoc/room_allocation/{event_id}/review').get_data(as_text=True)
    assert "isn&#39;t in your room list" not in review and '4 of 4 seats' in review
    assert h['final'](h['owner'], event_id, website=True).status_code == 302
    assert h['reg'](t['id'])['assigned_room'] == 'Seminar Hall 3'


def test_a_typed_room_in_the_list_is_that_room(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    t = h['team'](event_id, 'Pair')
    h['setup'](h['owner'], event_id, [('Lab A', 10)])
    data = _move(h, event_id, t['id'], 'lab a').get_json()
    assert data['room'] == 'Lab A' and data['added'] == ''
    assert [r['name'] for r in h['plan'](event_id)['rooms']] == ['Lab A']


def test_a_typed_room_seats_a_team_as_one_when_seats_are_teams(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    t = h['team'](event_id, 'Big', people=4)
    h['owner'].post(f'/spoc/setup_rooms/{event_id}', data={'room_name[]': ['101'], 'capacity[]': ['5'],
                                                           'per': 'team', 'action': 'save'})
    _move(h, event_id, t['id'], 'Annex')
    assert [r['capacity'] for r in h['plan'](event_id)['rooms'] if r['name'] == 'Annex'] == [1]


def test_picking_from_the_list_is_unchanged_and_another_spoc_cant_type(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    t = h['team'](event_id, 'Plain')
    h['setup'](h['owner'], event_id, [('101', 10)])
    # not typed: an unknown room stays a problem to fix, as before
    _move(h, event_id, t['id'], 'Ghost', typed=False)
    assert [r['name'] for r in h['plan'](event_id)['rooms']] == ['101']
    from tests.test_integration_flow import _login, _unique, _user
    other = f"{_unique('typespoc')}@test.edu"
    _user(h['db'], other, 'ClubSPOC')
    assert _move(h, event_id, t['id'], 'Mine', client=_login(h['app'], other, 'ClubSPOC')).status_code == 403
    assert [r['name'] for r in h['plan'](event_id)['rooms']] == ['101']
