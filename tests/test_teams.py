"""
tests/test_teams.py — UPG-08 on the real database layer: a team is one
registration. Its form asks for members within the event's limits, others
join with the lead's invite code, the lead manages the roster, and tickets,
judging and check-in all work from the registration's members.
"""
import datetime
import re

import pytest

import routes_ticket
from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def team_event(real_app):
    """A team event for 2–4 people, today, with registration open."""
    flask_app, db = real_app
    spoc = f"{_unique('teamspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Team Hack'), datetime.date.today().isoformat(), team=True)
    db.collection('events').document(event_id).update({'status': 'registration_open'})
    return {'app': flask_app, 'db': db, 'owner': owner, 'event_id': event_id}


def _student(d, key='stu'):
    email = f"{_unique(key)}@test.edu"
    _user(d['db'], email, 'Student')
    d['db'].collection('users').document(email).update({'usn': f'1SN22CS{len(key):03d}'})
    return email, _login(d['app'], email, 'Student')


def _register(d, client, lead, mates, team='Byte Force', **extra):
    form = {'full_name': 'Lee Lead', 'email': lead, 'phone': '9876543210', 'usn': '1SN22CS100', 'team_name': team}
    for i, (name, email, usn) in enumerate(mates, start=1):
        form.update({f'member_{i}_name': name, f'member_{i}_email': email, f'member_{i}_usn': usn})
    form.update(extra)
    return client.post(f"/forms/submit/{d['event_id']}", data=form)


def _team_regs(d):
    return [(doc.id, doc.to_dict()) for doc in d['db'].collection('registrations').where('event_id', '==', d['event_id']).stream()]


def _reg(d, reg_id):
    return d['db'].collection('registrations').document(reg_id).get().to_dict()


def _emails(reg):
    return [m['email'] for m in reg['members']]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_form_asks_for_members_and_refuses_a_one_person_team(team_event):
    d = team_event
    lead, client = _student(d, 'lead')
    page = client.get(f"/forms/register/{d['event_id']}").get_data(as_text=True)
    names = re.findall(r'<(?:input|select|textarea)\b[^>]*\bname="([^"]*)"', page)
    assert 'team_name' in names
    assert [n for n in names if n.startswith('member_') and n.endswith('_name')] == \
        ['member_1_name', 'member_2_name', 'member_3_name']       # up to 4 people, the lead included

    resp = _register(d, client, lead, [])
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f"/forms/register/{d['event_id']}")
    assert _team_regs(d) == []

    mate = f"{_unique('mate')}@test.edu"
    assert _register(d, client, lead, [('Mo Mate', mate, '1SN22CS101')]).status_code == 302
    [(reg_id, reg)] = _team_regs(d)
    assert _emails(reg) == [lead, mate] and reg['member_count'] == 2
    assert re.fullmatch(r'[A-Z0-9]{6}', reg['team_code'])


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_joining_by_code_adds_the_member_and_they_can_open_the_ticket(team_event):
    d = team_event
    lead, lead_client = _student(d, 'lead')
    _register(d, lead_client, lead, [('Mo Mate', f"{_unique('mate')}@test.edu", '1SN22CS101')])
    [(reg_id, reg)] = _team_regs(d)

    joiner, joiner_client = _student(d, 'joiner')
    assert joiner_client.get(f'/ticket/{reg_id}').status_code == 302          # not yet on the team
    resp = joiner_client.post('/teams/join', data={'join_code': reg['team_code'].lower()})
    assert resp.status_code == 302 and resp.headers['Location'] == f'/teams/{reg_id}'
    reg = _reg(d, reg_id)
    assert joiner in _emails(reg) and reg['member_count'] == 3
    assert next(m for m in reg['members'] if m['email'] == joiner)['role'] == 'Member'

    ticket = joiner_client.get(f'/ticket/{reg_id}')
    assert ticket.status_code == 200 and 'data:image/png;base64,' in ticket.get_data(as_text=True)
    assert joiner_client.get(f'/teams/{reg_id}').status_code == 200
    assert reg['team_code'] not in joiner_client.get(f'/teams/{reg_id}').get_data(as_text=True)  # only the lead sees it

    # Someone already registered for the event can't join a second team
    other_lead, other_client = _student(d, 'otherlead')
    _register(d, other_client, other_lead, [('Ola Mate', f"{_unique('ola')}@test.edu", '1SN22CS102')], team='Other')
    before = _reg(d, reg_id)['members']
    other_client.post('/teams/join', data={'join_code': reg['team_code']})
    assert _reg(d, reg_id)['members'] == before


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_judge_sees_the_team_name(team_event):
    d = team_event
    lead, client = _student(d, 'lead')
    _register(d, client, lead, [('Mo Mate', f"{_unique('mate')}@test.edu", '1SN22CS101')], team='Quantum Quokkas')
    [(reg_id, _)] = _team_regs(d)
    judge = f"{_unique('judge')}@test.edu"
    _user(d['db'], judge, 'Judge')
    d['db'].collection('events').document(d['event_id']).update({
        'staff': [{'email': judge, 'name': 'Jude', 'role': 'Judge'}], 'judging_criteria': ['Overall Score']})
    d['db'].collection('registrations').document(reg_id).update({'attendance': 'Present', 'assigned_judge_email': judge})
    page = _login(d['app'], judge, 'Judge').get(f"/judge/event/{d['event_id']}")
    assert page.status_code == 200 and 'Quantum Quokkas' in page.get_data(as_text=True)


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_a_full_team_takes_nobody_else(team_event):
    d = team_event
    lead, client = _student(d, 'lead')
    mates = [(f'Mate {i}', f"{_unique(f'mate{i}')}@test.edu", f'1SN22CS20{i}') for i in range(1, 4)]
    # The browser sends a fifth person: refused, nothing created
    resp = _register(d, client, lead, mates, member_4_name='Extra Ed', member_4_email=f"{_unique('extra')}@test.edu")
    assert resp.status_code == 302 and _team_regs(d) == []

    assert _register(d, client, lead, mates).status_code == 302
    [(reg_id, reg)] = _team_regs(d)
    assert len(reg['members']) == 4
    joiner, joiner_client = _student(d, 'late')
    joiner_client.post('/teams/join', data={'join_code': reg['team_code']})
    assert len(_reg(d, reg_id)['members']) == 4 and joiner not in _emails(_reg(d, reg_id))


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_only_the_lead_manages_the_team_and_a_removed_member_loses_the_ticket(team_event):
    d = team_event
    lead, lead_client = _student(d, 'lead')
    _register(d, lead_client, lead, [('Mo Mate', f"{_unique('mate')}@test.edu", '1SN22CS101')])
    [(reg_id, reg)] = _team_regs(d)
    member, member_client = _student(d, 'member')
    member_client.post('/teams/join', data={'join_code': reg['team_code']})
    code = _reg(d, reg_id)['team_code']

    # A member can't remove anyone or change the code
    member_client.post(f'/teams/{reg_id}/remove', data={'email': lead})
    member_client.post(f'/teams/{reg_id}/regenerate')
    reg = _reg(d, reg_id)
    assert lead in _emails(reg) and member in _emails(reg) and reg['team_code'] == code

    # The lead can; the removed member loses the ticket, the old code stops working
    assert lead_client.post(f'/teams/{reg_id}/remove', data={'email': member}).status_code == 302
    assert member not in _emails(_reg(d, reg_id))
    assert member_client.get(f'/ticket/{reg_id}').status_code == 302
    assert member_client.get(f'/teams/{reg_id}').status_code == 302
    lead_client.post(f'/teams/{reg_id}/regenerate')
    new_code = _reg(d, reg_id)['team_code']
    assert new_code != code and new_code in lead_client.get(f'/teams/{reg_id}').get_data(as_text=True)
    member_client.post('/teams/join', data={'join_code': code})
    assert member not in _emails(_reg(d, reg_id))


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_a_team_check_in_records_exactly_the_members_who_came(team_event, monkeypatch):
    d = team_event
    lead, client = _student(d, 'lead')
    _register(d, client, lead, [('Ana', f"{_unique('ana')}@test.edu", '1SN22CS301'),
                                ('Ben', f"{_unique('ben')}@test.edu", '1SN22CS302')])
    [(reg_id, _)] = _team_regs(d)
    coord = f"{_unique('gate')}@test.edu"
    _user(d['db'], coord, 'EventCoordinator')
    d['db'].collection('events').document(d['event_id']).update({
        'staff': [{'email': coord, 'name': 'Gate', 'role': 'EventCoordinator'}]})
    desk = _login(d['app'], coord, 'EventCoordinator')

    with d['app'].app_context():
        token = routes_ticket.generate_ticket_token(reg_id, d['event_id'], 'Lee Lead')
    scan = desk.post('/ticket/api/checkin', json={'token': token, 'event_id': d['event_id']}).get_json()
    assert scan['status'] == 'success' and [m['usn'] for m in scan['members']] == ['1SN22CS100', '1SN22CS301', '1SN22CS302']
    resp = desk.post('/coordinator/mark_attendance_granular',
                     json={'reg_id': reg_id, 'present_usns': ['1SN22CS100', '1SN22CS302']})
    assert resp.get_json()['status'] == 'success'
    present = {m['usn']: m['attendance'] for m in _reg(d, reg_id)['members']}
    assert present == {'1SN22CS100': 'Present', '1SN22CS301': 'Absent', '1SN22CS302': 'Present'}
