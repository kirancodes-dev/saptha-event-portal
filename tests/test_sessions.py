"""
tests/test_sessions.py — UPG-159: agenda sessions. Staff scan the same signed
ticket into a session (checking the person in to the event first if needed);
a repeat says "already in"; a full session warns the scanner; attendees star
sessions into "My agenda" and its .ics; per-session hours reach the ledger;
the export has a column per session.
"""
import csv
import io
import re

import services_sessions
from services_ledger import credit_for
from tests.test_checkin_unified import _reg, _registration, _scan, gate  # noqa: F401  (fixture)
from tests.test_integration_flow import _login, _unique, _user


def _schedule(d, rows):
    """Save the agenda through the schedule builder, as the organiser does."""
    data = {k: [] for k in ('time[]', 'end[]', 'title[]', 'desc[]', 'room[]', 'capacity[]', 'hours[]', 'sid[]')}
    for row in rows:
        for k in ('time', 'end', 'title', 'desc', 'room', 'capacity', 'hours', 'sid'):
            data[f'{k}[]'].append(str(row.get(k, '')))
    assert d['owner'].post(f"/spoc/agenda/{d['event_id']}", data=data).status_code == 302
    event = d['db'].collection('events').document(d['event_id']).get().to_dict()
    return services_sessions.sessions_for(event)


def _session_scan(client, token, event_id, session_id, **extra):
    return client.post('/ticket/api/session_checkin',
                       json=dict({'token': token, 'event_id': event_id, 'session_id': session_id}, **extra))


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_a_session_scan_records_one_row_and_a_repeat_says_already_in(gate):  # noqa: F811
    d = gate
    keynote, workshop = _schedule(d, [{'time': '09:30', 'end': '10:30', 'title': 'Keynote', 'room': 'Hall A'},
                                      {'time': '11:00', 'title': 'Workshop', 'room': 'Lab 2'}])
    assert keynote['room'] == 'Hall A' and keynote['id'] != workshop['id']
    reg_id, token = _registration(d, lead_name='Sana Session')

    first = _session_scan(d['staff'], token, d['event_id'], keynote['id'])
    body = first.get_json()
    assert first.status_code == 200 and body['status'] == 'success'
    assert body['entered_event'] is True                     # checked in to the event too
    assert _reg(d, reg_id)['attendance'] == 'Present'

    again = _session_scan(d['staff'], token, d['event_id'], keynote['id'])
    assert again.status_code == 200 and again.get_json()['status'] == 'already_in'
    assert 'Already in Keynote' in again.get_json()['message']
    assert services_sessions.attended(d['event_id']) == {reg_id: {keynote['id']}}
    assert services_sessions.count(d['event_id'], keynote['id']) == 1

    # Another session is its own row; the event check-in isn't repeated
    other = _session_scan(d['staff'], token, d['event_id'], workshop['id']).get_json()
    assert other['status'] == 'success' and other['entered_event'] is False
    assert services_sessions.attended(d['event_id']) == {reg_id: {keynote['id'], workshop['id']}}

    # Saving the schedule again keeps the session IDs, so attendance stays attached
    again_saved = _schedule(d, [dict(keynote, sid=keynote['id']), dict(workshop, sid=workshop['id'])])
    assert [s['id'] for s in again_saved] == [keynote['id'], workshop['id']]


def test_a_session_scan_keeps_the_gates_rules(gate):  # noqa: F811
    d = gate
    (talk,) = _schedule(d, [{'time': '10:00', 'title': 'Talk'}])
    _, cancelled = _registration(d, status='Cancelled')
    assert _session_scan(d['staff'], cancelled, d['event_id'], talk['id']).status_code == 409
    _, token = _registration(d)
    outsider = _login(d['app'], d['people']['coord_out'], 'EventCoordinator')
    assert _session_scan(outsider, token, d['event_id'], talk['id']).status_code == 403
    assert _session_scan(d['staff'], token, d['event_id'], 'no-such-session').status_code == 404
    assert _session_scan(d['staff'], 'forged', d['event_id'], talk['id']).status_code == 400
    assert services_sessions.attended(d['event_id']) == {}

    # Event-level check-in is unchanged
    assert _scan(d['staff'], token, d['event_id']).get_json()['status'] == 'success'


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_a_session_at_capacity_warns_the_scanner(gate):  # noqa: F811
    d = gate
    (small,) = _schedule(d, [{'time': '14:00', 'title': 'Masterclass', 'capacity': '2'}])
    tokens = [_registration(d)[1] for _ in range(4)]
    for token in tokens[:2]:
        assert _session_scan(d['staff'], token, d['event_id'], small['id']).get_json()['status'] == 'success'

    full = _session_scan(d['staff'], tokens[2], d['event_id'], small['id'])
    assert full.status_code == 409 and full.get_json()['status'] == 'session_full'
    assert 'is full (2 seats)' in full.get_json()['message']
    assert services_sessions.count(d['event_id'], small['id']) == 2

    # Someone already in still says "already in", not "full"
    assert _session_scan(d['staff'], tokens[0], d['event_id'], small['id']).get_json()['status'] == 'already_in'

    # The scanner can admit anyway
    over = _session_scan(d['staff'], tokens[2], d['event_id'], small['id'], allow_over=True)
    assert over.status_code == 200 and over.get_json()['status'] == 'success'
    assert services_sessions.count(d['event_id'], small['id']) == 3

    # Both scanners offer the session mode
    page = d['owner'].get(f"/spoc/scan/{d['event_id']}").get_data(as_text=True)
    assert 'id="scanMode"' in page and f'value="{small["id"]}"' in page and '2 seats' in page
    coord = d['staff'].get(f"/coordinator/scan/{d['event_id']}").get_data(as_text=True)
    assert 'id="scanMode"' in coord and f'value="{small["id"]}"' in coord


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_my_agenda_lists_only_starred_sessions_and_its_ics_has_them(gate):  # noqa: F811
    d = gate
    a, b, c = _schedule(d, [{'time': '09:00', 'end': '10:00', 'title': 'Opening, and welcome', 'room': 'Hall A'},
                            {'time': '11:00', 'title': 'Robotics Lab'},
                            {'time': '15:00', 'title': 'Panel'}])
    student = d['student']
    for s in (a, c):
        assert student.post(f"/participant/agenda/{d['event_id']}/star",
                            data={'session_id': s['id'], 'on': '1'}).status_code == 302
    student.post(f"/participant/agenda/{d['event_id']}/star", data={'session_id': a['id'], 'on': '1'})  # twice

    page = student.get(f"/participant/agenda/{d['event_id']}").get_data(as_text=True)
    mine = page.split('id="my-agenda"', 1)[1].split('id="all-sessions"', 1)[0]
    assert 'Opening, and welcome' in mine and 'Panel' in mine and 'Robotics Lab' not in mine
    assert 'Robotics Lab' in page.split('id="all-sessions"', 1)[1]

    ics = student.get(f"/participant/agenda/{d['event_id']}.ics")
    assert ics.status_code == 200 and ics.mimetype == 'text/calendar'
    text = ics.get_data(as_text=True)
    assert text.count('BEGIN:VEVENT') == 2 and 'Robotics' not in text
    assert 'SUMMARY:Opening\\, and welcome' in text and 'LOCATION:Hall A' in text
    day = d['db'].collection('events').document(d['event_id']).get().to_dict()['date'][:10].replace('-', '')
    assert f'DTSTART:{day}T033000Z' in text and f'DTEND:{day}T043000Z' in text   # 09:00–10:00 IST

    # Un-starring takes it off; another person's agenda is their own
    student.post(f"/participant/agenda/{d['event_id']}/star", data={'session_id': c['id'], 'on': '0'})
    assert student.get(f"/participant/agenda/{d['event_id']}.ics").get_data(as_text=True).count('BEGIN:VEVENT') == 1
    other = f"{_unique('other')}@test.edu"
    _user(d['db'], other, 'Student')
    other_page = _login(d['app'], other, 'Student').get(f"/participant/agenda/{d['event_id']}").get_data(as_text=True)
    assert 'Opening' not in other_page.split('id="my-agenda"', 1)[1].split('id="all-sessions"', 1)[0]

    # The event page links to it; logged out, the agenda asks for a login
    assert f"/participant/agenda/{d['event_id']}" in d['app'].test_client().get(f"/event/{d['event_id']}").get_data(as_text=True)
    assert d['app'].test_client().get(f"/participant/agenda/{d['event_id']}").status_code == 302


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_per_session_hours_credit_only_the_attended_sessions(gate):  # noqa: F811
    d = gate
    d['db'].collection('events').document(d['event_id']).update({'activity_points': 5, 'activity_hours': 12})
    day1, day2, day3 = _schedule(d, [{'time': '09:00', 'title': 'FDP module 1', 'hours': '3'},
                                     {'time': '12:00', 'title': 'FDP module 2', 'hours': '2.5'},
                                     {'time': '15:00', 'title': 'FDP module 3', 'hours': '4'}])
    email = d['people']['student']
    reg_id = d['reg_id']
    with d['app'].app_context():
        from routes_ticket import generate_ticket_token
        token = generate_ticket_token(reg_id, d['event_id'], 'Tara Ticket')
    for s in (day1, day3):
        assert _session_scan(d['staff'], token, d['event_id'], s['id']).get_json()['status'] == 'success'

    event = d['db'].collection('events').document(d['event_id']).get().to_dict()
    assert credit_for(_reg(d), event, reg_id) == (5.0, 7.0)          # 3 + 4, not the event's 12
    ledger = d['student'].get('/participant/api/ledger?format=json')
    page = ledger.get_data(as_text=True)
    assert ledger.status_code == 200 and re.search(r'"total_hours":\s*7(\.0)?\b', page), page[:400]

    # The department export adds them up the same way
    import services_export
    d['db'].collection('users').document(email).update({'department': 'CSE-SESS'})
    rows = services_export.department_activity_data(d['db'], department='CSE-SESS')
    assert [(r['email'], r['total_hours']) for r in rows if r['email'] == email] == [(email, 7.0)]

    # An event without session hours keeps crediting its own hours
    plain = dict(event, agenda=[{'id': 'x1', 'time': '09:00', 'title': 'Talk'}])
    assert credit_for(_reg(d), plain, reg_id) == (5.0, 12.0)


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_the_export_has_a_column_per_session(gate):  # noqa: F811
    d = gate
    one, two = _schedule(d, [{'time': '10:00', 'title': 'Hackathon kickoff'}, {'time': '16:00', 'title': 'Demo hour'}])
    with d['app'].app_context():
        from routes_ticket import generate_ticket_token
        token = generate_ticket_token(d['reg_id'], d['event_id'], 'Tara Ticket')
    _session_scan(d['staff'], token, d['event_id'], two['id'])

    resp = d['owner'].get(f"/spoc/export_csv/{d['event_id']}")
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    header = rows[0]
    assert header[-2:] == ['Session: 10:00 Hackathon kickoff', 'Session: 16:00 Demo hour']
    tara = next(r for r in rows[1:] if r[1] == 'Tara Ticket')
    assert len(tara) == len(header) and tara[-2:] == ['', 'Yes']

    import openpyxl
    xlsx = d['owner'].get(f"/spoc/export_excel/{d['event_id']}")
    sheet = openpyxl.load_workbook(io.BytesIO(xlsx.data)).active
    assert [c.value for c in sheet[1]][-1] == 'Session: 16:00 Demo hour'
