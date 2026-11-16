"""
tests/test_runsheet.py — UPG-272 on the real database layer: each schedule
item has a time, a room, someone responsible and a status; a room can't be
used twice at once; the event's staff see who does what and move items along;
a change participants should know about is announced to them; and what is for
the staff never reaches a public page or the API.
"""
import datetime
import re
import uuid

import pytest

import services_runsheet as runsheet
from tests import test_checkin_unified as _gate
from tests.test_integration_flow import _create_event, _unique

gate = _gate.gate


def _form(rows, **extra):
    """The schedule builder's form: one dict a row."""
    data = {f'{k}[]': [str(r.get(k, '')) for r in rows]
            for k in ('sid', 'time', 'end', 'title', 'desc', 'room', 'capacity', 'hours', 'owner', 'note', 'status')}
    return dict(data, **extra)


def _agenda(d, event_id=None):
    return d['db'].collection('events').document(event_id or d['event_id']).get().to_dict().get('agenda') or []


def _save(d, rows, **extra):
    return d['owner'].post(f"/spoc/agenda/{d['event_id']}", data=_form(rows, **extra), follow_redirects=True)


def _ids(d):
    return {i['title']: i['id'] for i in _agenda(d)}


def _bell(d, email):
    return [n.to_dict() for n in d['db'].collection('notifications_v2').where('user_email', '==', email).stream()]


def _announcements(d):
    return [a.to_dict() for a in d['db'].collection('announcements').where('event_id', '==', d['event_id']).stream()]


@pytest.fixture
def day(gate, monkeypatch):
    """The gate's event with a three-item schedule, and every email caught."""
    import utils_email
    d = gate
    d['mail'] = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: d['mail'].append(to) or True)
    page = _save(d, [
        {'time': '09:00', 'end': '09:30', 'title': 'Welcome', 'room': 'Hall A', 'owner': 'In', 'note': 'Mics from the store'},
        {'time': '09:30', 'end': '11:00', 'title': 'Round one', 'room': 'Lab 2', 'owner': 'Priya'},
        {'time': '11:00', 'title': 'Results', 'room': 'Hall A'}])
    assert page.status_code == 200 and 'Schedule saved!' in page.get_data(as_text=True)
    return d


# ── The rules, on their own ─────────────────────────────────────────────────

def _item(sid, time, end='', room='', status=''):
    return {k: v for k, v in {'id': sid, 'title': sid.upper(), 'time': time, 'end': end, 'room': room, 'status': status}.items() if v}


def test_a_room_cannot_be_used_twice_at_once_and_an_item_cannot_end_before_it_starts():
    a, b = _item('a', '10:00', '11:00', 'Hall A'), _item('b', '10:30', '11:30', ' hall  a ')
    problems, warnings = runsheet.check([a, b])
    assert [p['ids'] for p in problems] == [['a', 'b']] and warnings == []
    assert 'Hall A is needed twice at the same time' in problems[0]['message']
    # one after the other, another room, no room at all, or one of them cancelled: fine
    assert runsheet.check([a, _item('b', '11:00', '12:00', 'Hall A')]) == ([], [])
    assert runsheet.check([a, _item('b', '10:30', '11:30', 'Hall B')]) == ([], [])
    assert runsheet.check([_item('a', '10:00', '11:00'), _item('b', '10:30', '11:30')]) == ([], [])
    assert runsheet.check([a, dict(b, status='cancelled')]) == ([], [])
    # an item with no end is the moment it starts
    assert runsheet.check([a, _item('b', '10:15', room='Hall A')])[0]
    assert runsheet.check([a, _item('b', '11:00', room='Hall A')]) == ([], [])
    assert runsheet.check([_item('a', '10:00', room='Hall A'), _item('b', '10:00', room='Hall A')])[0]

    problems, _ = runsheet.check([_item('a', '10:00', '09:00'), _item('b', '25:00'), _item('c', '10:00', 'soon')])
    assert [p['ids'] for p in problems] == [['a'], ['b'], ['c']]
    assert 'ends at 09:00, before it starts at 10:00' in problems[0]['message']
    assert 'needs a start time' in problems[1]['message']

    # an event longer than a day has times, not days: the clash is a warning
    problems, warnings = runsheet.check([a, b], one_day=False)
    assert problems == [] and 'different days' in warnings[0]['message']
    # one person, two items at once: a warning, whatever the rooms
    problems, warnings = runsheet.check([a, _item('b', '10:30', '11:30', 'Hall B')],
                                        {'a': {'owner': 'Priya'}, 'b': {'owner': ' priya '}})
    assert problems == [] and 'Priya is responsible for two items at the same time' in warnings[0]['message']


def test_only_changes_a_participant_should_know_become_sentences():
    before = [_item('a', '10:00', '11:00', 'Hall A'), _item('b', '11:00', room='Hall B'), _item('c', '12:00')]
    assert runsheet.changes(before, [dict(i) for i in before]) == []
    after = [dict(before[0], time='10:30'), dict(before[1], room='Lab 1', status='delayed'), _item('d', '13:00', room='Lawn')]
    said = runsheet.changes(before, after)
    assert said == ['“A” now starts at 10:30 (was 10:00).', '“B” has moved to Lab 1 (was Hall B).',
                    '“B” (11:00) is delayed.', 'New: “D” at 13:00 in Lawn.',
                    '“C” (12:00) has been taken off the schedule.']
    assert runsheet.changes(before, [dict(before[0], status='cancelled')] + before[1:]) == ['“A” (10:00) is cancelled.']
    assert runsheet.changes([dict(before[0], status='cancelled')], [before[0]]) == ['“A” is back on, at 10:00 in Hall A.']
    # the staff's own statuses, seats and hours say nothing to participants
    assert runsheet.changes(before, [dict(before[0], status='running', capacity=40, hours=2)] + before[1:]) == []
    assert runsheet.changes([], after) == []                     # the first schedule isn't a change


# ── Criterion 1: each item has a time, a room, an owner and a status ────────

def test_the_schedule_keeps_who_is_responsible_and_a_status_for_each_item(day):
    d = day
    agenda = _agenda(d)
    assert [(i['time'], i.get('end'), i['title'], i['room']) for i in agenda] == [
        ('09:00', '09:30', 'Welcome', 'Hall A'), ('09:30', '11:00', 'Round one', 'Lab 2'), ('11:00', None, 'Results', 'Hall A')]
    ids = _ids(d)
    assert runsheet.staff_fields(d['db'], d['event_id']) == {
        ids['Welcome']: {'owner': 'In', 'note': 'Mics from the store'}, ids['Round one']: {'owner': 'Priya', 'note': ''}}

    builder = d['owner'].get(f"/spoc/agenda/{d['event_id']}").get_data(as_text=True)
    assert 'value="Mics from the store"' in builder and 'value="Priya"' in builder
    assert '<option value="In"></option>' in builder              # the event's staff are offered as owners
    assert 'id="agenda-row-template"' in builder and builder.count('name="owner[]"') == 4   # 3 rows + the blank one
    for status in ('planned', 'ready', 'running', 'done', 'delayed', 'cancelled'):
        assert f'<option value="{status}"' in builder

    # saved again with a status and a new owner: the IDs stay, the rest follows
    rows = [dict(sid=i['id'], time=i['time'], end=i.get('end', ''), title=i['title'], room=i['room']) for i in agenda]
    rows[2].update(owner='Priya', status='ready')
    assert _save(d, rows).status_code == 200
    assert _ids(d) == ids and [i.get('status') for i in _agenda(d)] == [None, None, 'ready']
    assert runsheet.staff_fields(d['db'], d['event_id']) == {ids['Results']: {'owner': 'Priya', 'note': ''}}
    # someone else's event: refused
    assert d['staff'].post(f"/spoc/agenda/{d['event_id']}", data=_form([])).status_code in (302, 403)
    assert len(_agenda(d)) == 3


# ── Criterion 2: a clash stops the save; what might be one is a warning ─────

def test_a_room_clash_is_refused_with_what_was_typed_and_warnings_do_not_stop_the_save(day):
    d = day
    before = _agenda(d)
    rows = [dict(sid=i['id'], time=i['time'], end=i.get('end', ''), title=i['title'], room=i['room']) for i in before]
    clash = rows + [{'time': '09:15', 'end': '09:45', 'title': 'Press briefing', 'room': 'hall a', 'owner': 'Asha'}]
    page = d['owner'].post(f"/spoc/agenda/{d['event_id']}", data=_form(clash))
    text = page.get_data(as_text=True)
    assert page.status_code == 400 and 'The schedule was not saved.' in text and 'data-schedule-problems' in text
    assert 'is needed twice at the same time' in text and 'Welcome' in text
    assert 'value="Press briefing"' in text and 'value="Asha"' in text       # nothing typed is lost
    assert text.count('agenda-row--wrong') >= 2
    assert _agenda(d) == before and 'Asha' not in str(runsheet.staff_fields(d['db'], d['event_id']))

    backwards = rows[:2] + [dict(rows[2], end='10:00')]
    page = d['owner'].post(f"/spoc/agenda/{d['event_id']}", data=_form(backwards))
    assert page.status_code == 400 and 'ends at 10:00, before it starts at 11:00' in page.get_data(as_text=True)
    assert _agenda(d) == before

    # the same person twice at once, and a room another event uses then: saved, with a warning each
    other = _create_event(d['owner'], d['db'], _unique('Next Door'), _gate.TODAY, team=False)   # Hall A at 10:00
    # a day no other test's event is on: the page shows the first eight warnings
    far = (datetime.date(2060, 1, 1) + datetime.timedelta(days=uuid.uuid4().int % 9000)).isoformat()
    for event_id in (d['event_id'], other):
        d['db'].collection('events').document(event_id).update({'date': far, 'end_date': far})
    busy = rows[:2] + [dict(rows[2], time='09:45', end='10:30', owner='Priya')]
    busy[1]['owner'] = 'Priya'
    text = _save(d, busy).get_data(as_text=True)
    assert 'Schedule saved!' in text
    assert 'Priya is responsible for two items at the same time' in text
    assert re.search(r'Hall A is also used by .*Next Door.* at 10:00', text)
    assert [i['time'] for i in _agenda(d)] == ['09:00', '09:30', '09:45']
    assert other

    # an event longer than a day: the clash is a warning, and it saves
    d['db'].collection('events').document(d['event_id']).update({'end_date': '2031-01-01'})
    text = _save(d, clash).get_data(as_text=True)
    assert 'Schedule saved!' in text and 'If they are on different days, ignore this.' in text
    assert len(_agenda(d)) == 4


# ── Criterion 3: the event's staff see who does what ────────────────────────

def test_the_events_staff_see_the_run_sheet_and_who_is_responsible(day):
    d = day
    url = f"/coordinator/runsheet/{d['event_id']}"
    page = d['staff'].get(url)
    text = page.get_data(as_text=True)
    assert page.status_code == 200
    order = [text.index(t) for t in ('Welcome', 'Round one', 'Results')]
    assert order == sorted(order)
    assert 'Mics from the store' in text and 'Responsible: <strong>In</strong> (you)' in text
    assert 'rs-item--mine' in text and 'Nobody is responsible yet' in text
    groups = re.findall(r'data-owner-group="([^"]+)"', text)
    assert groups == ['In', 'Priya', 'nobody']
    assert 'data-edit-schedule' not in text and 'Tell participants' not in text      # a coordinator doesn't edit or announce
    owner_view = d['owner'].get(url).get_data(as_text=True)
    assert 'data-edit-schedule' in owner_view and 'Tell participants' in owner_view

    # not on this event's staff, a participant, a visitor: no run sheet
    from tests.test_integration_flow import _login
    outsider = _login(d['app'], d['people']['coord_out'], 'EventCoordinator')
    assert outsider.get(url).status_code == 403
    assert d['student'].get(url).status_code in (302, 403)
    assert d['app'].test_client().get(url).status_code in (302, 401, 403)
    assert d['app'].test_client().get(f"/coordinator/runsheet/{_unique('nope')}").status_code in (302, 401, 404)

    # the links that lead here
    assert f'href="{url}"' in d['owner'].get(f"/spoc/agenda/{d['event_id']}").get_data(as_text=True)
    empty = _create_event(d['owner'], d['db'], _unique('No Plan'), _gate.TODAY, team=False)
    assert 'data-no-schedule' in d['owner'].get(f'/coordinator/runsheet/{empty}').get_data(as_text=True)


# ── Criterion 4: moving an item along ───────────────────────────────────────

def test_staff_move_items_along_and_only_the_organiser_delays_or_cancels(day):
    d = day
    ids = _ids(d)
    url = f"/coordinator/runsheet/{d['event_id']}/status"
    done = d['staff'].post(url, data={'item': ids['Welcome'], 'status': 'running'}, follow_redirects=True)
    assert 'is now: Running now.' in done.get_data(as_text=True)
    assert [i.get('status') for i in _agenda(d)] == ['running', None, None]
    assert re.search(r'data-item="%s" data-status="running"' % ids['Welcome'], done.get_data(as_text=True))
    d['staff'].post(url, data={'item': ids['Welcome'], 'status': 'planned'})
    assert 'status' not in _agenda(d)[0]

    for status in ('delayed', 'cancelled'):
        assert d['staff'].post(url, data={'item': ids['Results'], 'status': status}).status_code == 403
    assert 'status' not in _agenda(d)[2]
    assert 'Choose a status from the list.' in d['staff'].post(
        url, data={'item': ids['Results'], 'status': 'exploded'}, follow_redirects=True).get_data(as_text=True)
    assert 'no longer on the schedule' in d['staff'].post(
        url, data={'item': 'gone', 'status': 'done'}, follow_redirects=True).get_data(as_text=True)

    # the organiser delays it without telling anyone, then a coordinator can't take the mark off
    said = d['owner'].post(url, data={'item': ids['Results'], 'status': 'delayed'}, follow_redirects=True).get_data(as_text=True)
    assert 'is now: Delayed.' in said and 'Participants were not told' in said
    assert _agenda(d)[2]['status'] == 'delayed' and _announcements(d) == [] and _bell(d, d['people']['student']) == []
    assert d['staff'].post(url, data={'item': ids['Results'], 'status': 'done'}).status_code == 403
    from tests.test_integration_flow import _login
    outsider = _login(d['app'], d['people']['coord_out'], 'EventCoordinator')
    assert outsider.post(url, data={'item': ids['Welcome'], 'status': 'done'}).status_code == 403
    assert 'status' not in _agenda(d)[0]
    audit = [a.to_dict() for a in d['db'].collection('audit_log').where('action', '==', 'RUN_SHEET_STATUS').stream()]
    assert any(d['event_id'] in str(a.get('details')) and 'delayed' in str(a.get('details')) for a in audit)


# ── Criterion 5: participants are told what changed ─────────────────────────

def test_a_schedule_change_is_announced_to_registered_people_only_when_asked(day):
    d = day
    student = d['people']['student']
    rows = [dict(sid=i['id'], time=i['time'], end=i.get('end', ''), title=i['title'], room=i['room']) for i in _agenda(d)]
    # the builder ticks the box when someone is registered
    assert re.search(r'name="announce" value="1" id="announce-change"\s+checked',
                     d['owner'].get(f"/spoc/agenda/{d['event_id']}").get_data(as_text=True))

    # a change for the staff only: nothing to tell, box ticked or not
    quiet = [dict(r) for r in rows]
    quiet[0].update(owner='Asha', note='Use the side door', capacity='80')
    assert 'Schedule saved!' in _save(d, quiet, announce='1').get_data(as_text=True)
    assert _announcements(d) == [] and _bell(d, student) == []

    # a new time, box not ticked: saved, nobody told, and the page says so
    moved = [dict(r) for r in rows]
    moved[2]['time'] = '11:30'
    text = _save(d, moved).get_data(as_text=True)
    assert 'Participants were not told about this change' in text
    assert _agenda(d)[2]['time'] == '11:30' and _announcements(d) == [] and _bell(d, student) == []

    # a new room and a cancellation, box ticked
    d['db'].collection('registrations').add({'event_id': d['event_id'], 'lead_email': 'left@test.edu',
                                             'lead_name': 'Left Early', 'status': 'Cancelled'})
    changed = [dict(r) for r in moved]
    changed[1]['room'] = 'Lab 5'
    changed[0]['status'] = 'cancelled'
    text = _save(d, changed, announce='1').get_data(as_text=True)
    assert 'sent to 1 registered person as a notification' in text
    posted = _announcements(d)
    assert len(posted) == 1 and posted[0]['kind'] == 'schedule_change'
    assert posted[0]['message'] == ('Schedule change: “Welcome” (09:00) is cancelled. '
                                    '“Round one” has moved to Lab 5 (was Lab 2).')
    bell = _bell(d, student)
    assert len(bell) == 1 and bell[0]['link'] == f"/event/{d['event_id']}" and 'Lab 5' in bell[0]['message']
    assert _bell(d, 'left@test.edu') == []                       # a cancelled registration is told nothing
    assert d['mail'] == []                                       # no email at any point
    public = d['app'].test_client().get(f"/spoc/announcements/public/{d['event_id']}").get_json()
    assert 'Lab 5' in str(public)

    # from the run sheet: the organiser delays an item and tells people
    ids = _ids(d)
    said = d['owner'].post(f"/coordinator/runsheet/{d['event_id']}/status",
                           data={'item': ids['Results'], 'status': 'delayed', 'announce': '1'},
                           follow_redirects=True).get_data(as_text=True)
    assert 'sent to 1 registered person' in said and len(_bell(d, student)) == 2
    assert any('“Results” (11:30) is delayed.' in a['message'] for a in _announcements(d))
    # a coordinator's own status never announces, even with the box sent by hand
    d['staff'].post(f"/coordinator/runsheet/{d['event_id']}/status",
                    data={'item': ids['Round one'], 'status': 'running', 'announce': '1'})
    assert len(_bell(d, student)) == 2 and len(_announcements(d)) == 2


# ── Criterion 6: what is for the staff stays with the staff ─────────────────

def test_participants_see_delayed_and_cancelled_and_never_the_staff_fields(day):
    d = day
    ids = _ids(d)
    url = f"/coordinator/runsheet/{d['event_id']}/status"
    d['owner'].post(url, data={'item': ids['Welcome'], 'status': 'cancelled'})
    d['owner'].post(url, data={'item': ids['Round one'], 'status': 'delayed'})
    d['staff'].post(url, data={'item': ids['Results'], 'status': 'ready'})

    visitor = d['app'].test_client()
    for path in (f"/event/{d['event_id']}", f"/event/{d['event_id']}?fragment=1"):
        page = visitor.get(path).get_data(as_text=True)
        assert re.findall(r'data-agenda-status="(\w+)"', page) == ['cancelled', 'delayed'], path
        assert 'Mics from the store' not in page and 'Priya' not in page and 'Ready' not in page.split('Event schedule')[1][:1500]
    api = visitor.get(f"/api/v1/events/{d['event_id']}")
    assert api.status_code == 200
    body = api.get_data(as_text=True)
    assert 'Mics from the store' not in body and 'Priya' not in body and '"owner"' not in body and '"note"' not in body
    stored = str(d['db'].collection('events').document(d['event_id']).get().to_dict())
    assert 'Mics from the store' not in stored and 'Priya' not in stored      # not on the event at all

    mine = d['student'].get(f"/participant/agenda/{d['event_id']}").get_data(as_text=True)
    assert re.findall(r'data-agenda-status="(\w+)"', mine) == ['cancelled', 'delayed']
    assert 'Mics from the store' not in mine and 'Priya' not in mine
    for sid in ids.values():
        d['student'].post(f"/participant/agenda/{d['event_id']}/star", data={'session_id': sid, 'on': '1'})
    calendar = d['student'].get(f"/participant/agenda/{d['event_id']}.ics").get_data(as_text=True)
    assert 'Round one' in calendar and 'Results' in calendar and 'Welcome' not in calendar
