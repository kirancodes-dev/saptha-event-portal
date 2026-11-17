"""
tests/test_room_seat_per_team.py — UPG-312: a room's seats can count teams
instead of people. With "one seat is a whole team", a team of 4 takes 1 seat:
Auto-fill, the room cards, the final check and its "over capacity" problem all
count teams. An event that never chose still counts people.
"""
from tests.test_room_allocation_final import host, rooms  # noqa: F401  (the UPG-306 fixtures)


def _setup(h, event_id, rows, per=None, action='allocate'):
    data = {'room_name[]': [r[0] for r in rows], 'capacity[]': [str(r[1]) for r in rows], 'action': action}
    if per:
        data['per'] = per
    return h['owner'].post(f'/spoc/setup_rooms/{event_id}', data=data)


# 1. The SPOC chooses what a seat is; it's saved on the event's plan
def test_the_spoc_chooses_a_seat_per_team(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert 'data-room-per' in page and 'value="person" checked' in page    # people by default
    assert _setup(h, event_id, [('101', 3)], per='team', action='save').status_code == 302
    assert h['plan'](event_id)['per'] == 'team'
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert 'value="team" checked' in page and 'Capacity counts teams' in page


# 2. Auto-fill puts one team per seat, whatever its size
def test_auto_fill_counts_one_seat_per_team(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    teams = [h['team'](event_id, f'Team {i}', people=4, at=f'2026-01-01 09:0{i}:00') for i in range(5)]
    _setup(h, event_id, [('Hall A', 3), ('Hall B', 2)], per='team')
    draft = h['plan'](event_id)['draft']
    assert [draft[t['id']] for t in teams] == ['Hall A'] * 3 + ['Hall B'] * 2
    # by people the same rooms would hold nobody: 4 people don't fit in 3 or 2 seats
    _setup(h, event_id, [('Hall A', 3), ('Hall B', 2)], per='person')
    assert h['plan'](event_id)['draft'] == {}


# 3. The cards, the final check and its problems count teams
def test_the_final_check_counts_teams(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    a = h['team'](event_id, 'Quad One', people=4)
    b = h['team'](event_id, 'Quad Two', people=4)
    _setup(h, event_id, [('Lab 1', 2), ('Lab 2', 1)], per='team')
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert '<span data-room-people>2</span> of 2 seats' in page
    review = h['owner'].get(f'/spoc/room_allocation/{event_id}/review').get_data(as_text=True)
    assert '2 of 2 seats · 2 team(s) · 8 people' in review and 'over by' not in review
    # moving the second team into the full room: 3 teams for 2 seats
    _setup(h, event_id, [('Lab 1', 2), ('Lab 2', 1)], per='team', action='save')
    data = h['owner'].post(f"/spoc/reassign_room/{event_id}/{b['id']}", json={'room': 'Lab 1'}).get_json()
    assert {r['name']: r['used'] for r in data['rooms']} == {'Lab 1': 2, 'Lab 2': 0}
    c = h['team'](event_id, 'Quad Three', people=4)
    h['owner'].post(f"/spoc/reassign_room/{event_id}/{c['id']}", json={'room': 'Lab 1'})
    review = h['owner'].get(f'/spoc/room_allocation/{event_id}/review').get_data(as_text=True)
    assert 'Lab 1 has 3 teams for 2 seats.' in review and 'over by 1' in review
    assert a['id'] in h['plan'](event_id)['draft']


# 4. An event that never chose counts people, as before
def test_without_a_choice_seats_are_people(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    h['team'](event_id, 'Trio', people=3)
    _setup(h, event_id, [('Room 9', 2)])
    assert 'per' not in h['plan'](event_id) and h['plan'](event_id)['draft'] == {}
