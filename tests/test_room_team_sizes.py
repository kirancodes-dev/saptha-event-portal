"""
tests/test_room_team_sizes.py — UPG-316: teams of 3 and teams of 4 in separate
rooms, or mixed, as the SPOC chooses before Auto-fill. A room can be kept for
one team size ("Only teams of 4") or be "Mixed" whatever the choice; with
"Separate" no other room mixes sizes, the biggest teams first. With "Mixed"
(the default), Auto-fill is as before. Moving by hand still puts any team
anywhere; the final check notes it without blocking Allocate final.
"""
from tests.test_room_allocation_final import host, rooms  # noqa: F401  (the UPG-306 fixtures)


def _setup(h, event_id, rows, by_size=False, per=None, action='allocate'):
    data = {'room_name[]': [r[0] for r in rows], 'capacity[]': [str(r[1]) for r in rows],
            'team_size[]': [str(r[2]) if len(r) > 2 else '' for r in rows], 'action': action}
    data['by_size'] = '1' if by_size else '0'
    if per:
        data['per'] = per
    return h['owner'].post(f'/spoc/setup_rooms/{event_id}', data=data)


def _teams(h, event_id, sizes):
    """Teams of the given sizes, registered a minute apart in this order."""
    return [h['team'](event_id, f'T{i} of {n}', people=n, at=f'2026-01-01 09:{i:02d}:00')
            for i, n in enumerate(sizes)]


# 1. A "Teams of" room takes only teams of that size
def test_a_room_for_teams_of_n_takes_only_that_size(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    teams = _teams(h, event_id, [3, 4, 3, 4, 4, 5])
    assert _setup(h, event_id, [('Fours', 12, 4), ('Threes', 6, 3)]).status_code == 302
    draft = h['plan'](event_id)['draft']
    assert [draft.get(t['id']) for t in teams] == ['Threes', 'Fours', 'Threes', 'Fours', 'Fours', None]
    # with an open room too, the sized rooms are used first and the rest go to the open one
    _setup(h, event_id, [('Open', 20), ('Fours', 8, 4), ('Threes', 3, 3)])
    draft = h['plan'](event_id)['draft']
    assert [draft.get(t['id']) for t in teams] == ['Threes', 'Fours', 'Open', 'Fours', 'Open', 'Open']


# 2. Same sizes together: no room mixes sizes; the 4s fill first, then the 3s
def test_keeping_sizes_together_never_mixes_a_room(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    teams = _teams(h, event_id, [3, 4, 3, 4, 4, 3, 3])
    _setup(h, event_id, [('101', 8), ('102', 8), ('103', 8), ('104', 8)], by_size=True)
    draft = h['plan'](event_id)['draft']
    by_name = {t['name']: draft.get(t['id']) for t in teams}
    assert by_name == {'T1 of 4': '101', 'T3 of 4': '101', 'T4 of 4': '102',      # registration order within 4s
                       'T0 of 3': '103', 'T2 of 3': '103', 'T5 of 3': '104', 'T6 of 3': '104'}
    for room in ('101', '102', '103', '104'):
        sizes = {int(t['name'][-1]) for t in teams if draft.get(t['id']) == room}
        assert len(sizes) == 1
    review = h['owner'].get(f'/spoc/room_allocation/{event_id}/review').get_data(as_text=True)
    assert 'mixes teams' not in review

    # one seat per team: 2 teams a room, still never mixed
    _setup(h, event_id, [('A', 2), ('B', 2), ('C', 2), ('D', 2)], by_size=True, per='team')
    draft = h['plan'](event_id)['draft']
    rooms_of = {}
    for t in teams:
        rooms_of.setdefault(draft.get(t['id']), set()).add(int(t['name'][-1]))
    assert None not in rooms_of and all(len(s) == 1 for s in rooms_of.values())
    assert rooms_of == {'A': {4}, 'B': {4}, 'C': {3}, 'D': {3}}


# 3. Without either, Auto-fill is as before: registration order, sizes mixed
def test_without_sizes_auto_fill_is_unchanged(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    teams = _teams(h, event_id, [3, 4, 3])
    _setup(h, event_id, [('Hall', 10), ('Annex', 10)])
    draft = h['plan'](event_id)['draft']
    assert [draft[t['id']] for t in teams] == ['Hall', 'Hall', 'Hall']           # 10 people, mixed
    assert h['plan'](event_id).get('by_size') is False


# 4. Saved and shown; a hand move across sizes is allowed, shown and noted, not blocked
def test_sizes_are_shown_and_a_hand_move_is_noted_not_blocked(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    three, four = _teams(h, event_id, [3, 4])
    _setup(h, event_id, [('Fours', 8, 4), ('Threes', 6, 3)], by_size=True)
    p = h['plan'](event_id)
    assert p['by_size'] is True and [r.get('team_size') for r in p['rooms']] == [4, 3]
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert 'name="by_size" value="1" checked' in page and 'name="by_size" value="0" checked' not in page
    assert page.count('<option value="4" selected>Only teams of 4</option>') == 1
    assert page.count('<option value="3" selected>Only teams of 3</option>') == 1
    assert '>Teams of 4</span>' in page and 'Fours (teams of 4)</option>' in page

    data = h['owner'].post(f"/spoc/reassign_room/{event_id}/{three['id']}", json={'room': 'Fours'}).get_json()
    assert data['status'] == 'ok'
    card = next(r for r in data['rooms'] if r['name'] == 'Fours')
    assert card['sizes'] == [3, 4] and card['team_size'] == 4
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert 'sizes mixed" data-room-sizes data-room-mixed="0">Teams of 3 and 4' in page
    review = h['owner'].get(f'/spoc/room_allocation/{event_id}/review').get_data(as_text=True)
    assert 'Fours is for teams of 4 but has a team of 3.' in review
    assert h['final'](h['owner'], event_id, website='1').status_code == 302    # not blocked
    assert h['plan'](event_id)['final'] == {three['id']: 'Fours', four['id']: 'Fours'}

    # back to Mixed and a size cleared: saved as such, and the page says so
    _setup(h, event_id, [('Fours', 8), ('Threes', 6, 3)], action='save')
    p = h['plan'](event_id)
    assert p['by_size'] is False and 'team_size' not in p['rooms'][0] and p['rooms'][1]['team_size'] == 3
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert 'name="by_size" value="0" checked' in page


# 5. Flexible: with sizes separate, a "Mixed" room still takes any team
def test_a_mixed_room_takes_any_size_when_sizes_are_separate(rooms):  # noqa: F811
    h = rooms
    event_id = h['event']()
    teams = _teams(h, event_id, [4, 3, 4, 3, 4, 3])
    _setup(h, event_id, [('Overflow', 7, 'mix'), ('101', 8), ('102', 6)], by_size=True)
    p = h['plan'](event_id)
    assert p['rooms'][0].get('mixed') is True and 'team_size' not in p['rooms'][0]
    draft = p['draft']
    by_name = {t['name']: draft.get(t['id']) for t in teams}
    # every team placed: the Mixed room takes a 4 and a 3 together; 101 is kept for 4s, 102 for 3s
    assert by_name == {'T0 of 4': 'Overflow', 'T2 of 4': '101', 'T4 of 4': '101',
                       'T1 of 3': 'Overflow', 'T3 of 3': '102', 'T5 of 3': '102'}
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert '<option value="mix" selected>Mixed (any size)</option>' in page and '>Mixed</span>' in page
    assert 'Overflow (mixed)</option>' in page
    review = h['owner'].get(f'/spoc/room_allocation/{event_id}/review').get_data(as_text=True)
    assert 'mixes teams' not in review and 'mixed sizes' in review          # mixed on purpose: no note

    # the same rooms with sizes Mixed: registration order, any room
    _setup(h, event_id, [('Overflow', 7, 'mix'), ('101', 8), ('102', 6)], by_size=False)
    draft = h['plan'](event_id)['draft']
    assert [draft.get(t['id']) for t in teams] == ['Overflow', 'Overflow', '101', '101', '102', None]
