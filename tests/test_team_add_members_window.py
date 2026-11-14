"""
tests/test_team_add_members_window.py — UPG-250 on the real database layer, with a
mail provider configured (UPG-207's fixture).

After registration closes, the event's SPOC opens a window for a set time:
registered teams' leads add and remove members and teammates join with the
invite code, while new teams still can't register. The window ends by itself
or when the SPOC closes it; then the team is fixed again. Opening it tells
each lead whose team has room, in the portal and (if the SPOC chooses) by
email, when it closes.
"""
import datetime
from zoneinfo import ZoneInfo

import services_team_members as tm
from tests import test_team_member_confirm as _tc
from tests.test_integration_flow import _login, _unique, _user
from tests.test_team_member_confirm import _flashes, _to

team = _tc.team   # UPG-207's fixture

YESTERDAY = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def _close_registration(t, event_id):
    t['db'].collection('events').document(event_id).update({'deadline': YESTERDAY})


def _open(client, event_id, length='60', until='', email=True):
    data = {'action': 'open', 'length': length, 'until': until}
    if email:
        data['email'] = 'yes'
    return client.post(f'/coordinator/registrations/{event_id}/add_members_window', data=data)


def _add(client, reg_id, email, name='Nina New'):
    return client.post(f'/teams/{reg_id}/members/add', data={'name': name, 'email': email})


def _emails(t, reg_id):
    return [str(m.get('email') or '').lower() for m in t['reg'](reg_id)['members']]


def _student(t, prefix='joiner'):
    email = f"{_unique(prefix)}@test.edu"
    _user(t['db'], email, 'Student')
    return email, _login(t['app'], email, 'Student')


def _event(t, event_id):
    return t['db'].collection('events').document(event_id).get().to_dict()


def _notices(t, email, kind='team_window'):
    return [n.to_dict() for n in t['db'].collection('notifications_v2').stream()
            if n.to_dict().get('user_email') == email and n.to_dict().get('type') == kind]


# ── Criterion 1: in the window, teams grow; new teams still can't register ──

def test_with_the_window_open_leads_add_teammates_join_and_new_teams_stay_out(team):
    t = team
    event_id = t['event']()
    lead, reg_id = t['register'](event_id, mates=t['mates'](2))            # 3 of 4
    lead2, reg2 = t['register'](event_id, mates=t['mates'](1), team_name='Second')   # 2 of 4
    code2 = t['reg'](reg2)['team_code']
    _close_registration(t, event_id)
    client = t['lead_client'](lead)

    # Closed, no window: the lead is told, as before
    assert 'Registration for this event has closed' in client.get(f'/teams/{reg_id}').get_data(as_text=True)

    resp = _open(t['owner'], event_id, '60')
    assert resp.status_code == 302 and 'Teams can add and remove members until' in _flashes(t['owner'])

    new = f"{_unique('late')}@test.edu"
    _add(client, reg_id, new)
    assert 'Nina New is added. Your team now has 4 of 4.' in _flashes(client)
    assert new in _emails(t, reg_id)

    joiner, joiner_client = _student(t)
    resp = joiner_client.post('/teams/join', data={'join_code': code2})
    assert resp.status_code == 302 and 'You joined Second.' in _flashes(joiner_client)
    assert joiner in _emails(t, reg2)

    # A new team still can't register
    page = t['app'].test_client().get(f'/forms/register/{event_id}').get_data(as_text=True)
    assert 'data-add-member' not in page
    before = len(list(t['db'].collection('registrations').where('event_id', '==', event_id).stream()))
    t['app'].test_client().post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Late Lara', 'email': f"{_unique('newteam')}@test.edu",
        'phone': '9876500000', 'team_name': 'Too Late'})
    after = len(list(t['db'].collection('registrations').where('event_id', '==', event_id).stream()))
    assert after == before


# ── Criterion 2: the window ends (time, or "Close now"); removing in it ─────

def test_removing_works_in_the_window_and_everything_stops_when_it_ends(team, monkeypatch):
    t = team
    event_id = t['event']()
    mates = t['mates'](2)
    lead, reg_id = t['register'](event_id, mates=mates)
    lead2, reg2 = t['register'](event_id, mates=t['mates'](1), team_name='Other')
    code2 = t['reg'](reg2)['team_code']
    _close_registration(t, event_id)
    client = t['lead_client'](lead)

    # Closed and no window: removing is refused too, and the button is gone
    client.post(f'/teams/{reg_id}/remove', data={'email': mates[0]})
    assert "Registration for this event has closed, so the team can't change" in _flashes(client)
    assert mates[0] in _emails(t, reg_id)
    assert f'action="/teams/{reg_id}/remove"' not in client.get(f'/teams/{reg_id}').get_data(as_text=True)

    _open(t['owner'], event_id, '30')
    assert f'action="/teams/{reg_id}/remove"' in client.get(f'/teams/{reg_id}').get_data(as_text=True)
    client.post(f'/teams/{reg_id}/remove', data={'email': mates[0]})
    assert mates[0] not in _emails(t, reg_id)                               # replaced: remove...
    replacement = f"{_unique('swap')}@test.edu"
    _add(client, reg_id, replacement, name='Sam Swap')                      # ...then add
    assert replacement in _emails(t, reg_id)

    # 31 minutes later the window has closed by itself
    later = tm._now() + datetime.timedelta(minutes=31)
    real = tm._now   # put back by hand: undoing all would also undo real_app's db
    monkeypatch.setattr(tm, '_now', lambda: later)
    _add(client, reg_id, f"{_unique('toolate')}@test.edu")
    assert 'Registration for this event has closed' in _flashes(client)
    client.post(f'/teams/{reg_id}/remove', data={'email': mates[1]})
    assert "can't change" in _flashes(client) and mates[1] in _emails(t, reg_id)
    _, joiner_client = _student(t)
    joiner_client.post('/teams/join', data={'join_code': code2})
    assert "isn't taking registrations" in _flashes(joiner_client)
    monkeypatch.setattr(tm, '_now', real)

    # Opened again, then closed early by the SPOC
    _open(t['owner'], event_id, '120')
    assert t['owner'].post(f'/coordinator/registrations/{event_id}/add_members_window',
                           data={'action': 'close'}).status_code == 302
    assert "Closed: teams can't change any more." in _flashes(t['owner'])
    _add(client, reg_id, f"{_unique('afterclose')}@test.edu")
    assert 'Registration for this event has closed' in _flashes(client)


# ── Criterion 3: who may open it, bad input, who is told ────────────────────

def test_only_the_hosting_spoc_opens_it_and_bad_lengths_are_refused(team):
    t = team
    event_id = t['event']()
    lead, _ = t['register'](event_id, mates=t['mates'](1))

    # Registration still open: nothing to open
    _open(t['owner'], event_id, '60')
    assert 'Registration is still open' in _flashes(t['owner'])
    assert not tm.window_open(_event(t, event_id))

    _close_registration(t, event_id)
    other = f"{_unique('otherspoc')}@test.edu"
    _user(t['db'], other, 'ClubSPOC')
    assert _open(_login(t['app'], other, 'ClubSPOC'), event_id, '60').status_code == 403
    assert _open(t['lead_client'](lead), event_id, '60').status_code in (302, 403)   # a lead: not staff
    assert not tm.window_open(_event(t, event_id))

    for length, until, message in (('', '', 'Choose how long teams have.'),
                                   ('999', '', 'Choose how long teams have.'),
                                   ('until', '', 'Choose the date and time the window closes.'),
                                   ('until', '2020-01-01T10:00', 'That time has passed'),
                                   ('until', (datetime.datetime.now() + datetime.timedelta(days=9)).strftime('%Y-%m-%dT%H:%M'),
                                    '7 days at most')):
        _open(t['owner'], event_id, length, until)
        assert message in _flashes(t['owner']), message
        assert not tm.window_open(_event(t, event_id))

    until = (datetime.datetime.now(ZoneInfo('Asia/Kolkata')) + datetime.timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M')
    _open(t['owner'], event_id, 'until', until)
    assert tm.window_open(_event(t, event_id))
    assert any(a.to_dict().get('action') == 'ADD_MEMBERS_WINDOW_OPENED'
               for a in t['db'].collection('audit_log').stream())


def test_opening_tells_each_lead_with_room_once_and_not_a_full_team(team):
    t = team
    event_id = t['event']()
    lead_room, reg_room = t['register'](event_id, mates=t['mates'](2), team_name='Room')
    lead_full, _ = t['register'](event_id, mates=t['mates'](3), team_name='Full')
    _close_registration(t, event_id)
    t['sent'].clear()
    _open(t['owner'], event_id, '60')
    assert '1 team with room was told in their portal, 1 by email.' in _flashes(t['owner'])
    [mail] = _to(t['sent'], lead_room)
    closes = tm.window_closes(_event(t, event_id))
    assert closes and closes in mail['subject'] and f'/teams/{reg_room}#add-member' in mail['html']
    assert not _to(t['sent'], lead_full)
    [notice] = _notices(t, lead_room)
    assert closes in notice['title'] and notice['link'] == f'/teams/{reg_room}#add-member'
    assert not _notices(t, lead_full)

    # Without "email the leads too": a portal notice only
    t['sent'].clear()
    _open(t['owner'], event_id, '120', email=False)
    assert not _to(t['sent'], lead_room) and len(_notices(t, lead_room)) == 2


# ── Criterion 4: the pages show when it closes ──────────────────────────────

def test_the_team_page_and_the_spocs_page_show_when_it_closes(team):
    t = team
    event_id = t['event']()
    lead, reg_id = t['register'](event_id, mates=t['mates'](1))
    _close_registration(t, event_id)
    spoc_page = t['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert 'data-add-members-window="closed"' in spoc_page and 'data-window-form' in spoc_page

    _open(t['owner'], event_id, '60')
    closes = tm.window_closes(_event(t, event_id))
    page = t['lead_client'](lead).get(f'/teams/{reg_id}').get_data(as_text=True)
    assert 'data-window-open' in page and closes in page and 'data-add-member-form' in page
    spoc_page = t['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert 'data-add-members-window="open"' in spoc_page and closes in spoc_page and 'Close now' in spoc_page


# ── UPG-259: removing is refused when adding is, for the team itself ────────

def test_removing_is_refused_after_check_in_for_a_cancelled_team_and_after_the_event(team):
    t = team
    db = t['db']
    yesterday = YESTERDAY
    cases = (
        ({'attendance': 'Present'}, {}, 'checked in'),
        ({'status': 'cancelled'}, {}, 'cancelled'),
        ({}, {'date': yesterday, 'end_date': yesterday, 'status': 'completed'}, 'over'),
    )
    for reg_change, event_change, message in cases:
        event_id = t['event']()
        mates = t['mates'](2)
        lead, reg_id = t['register'](event_id, mates=mates, team_name=f'Team {message}')
        client = t['lead_client'](lead)
        if reg_change:
            db.collection('registrations').document(reg_id).update(reg_change)
        if event_change:
            db.collection('events').document(event_id).update(event_change)
        client.post(f'/teams/{reg_id}/remove', data={'email': mates[0]})
        assert message in _flashes(client), message
        assert mates[0] in _emails(t, reg_id), message
        assert f'action="/teams/{reg_id}/remove"' not in client.get(f'/teams/{reg_id}').get_data(as_text=True)

    # An open team still removes
    event_id = t['event']()
    mates = t['mates'](2)
    lead, reg_id = t['register'](event_id, mates=mates, team_name='Open Team')
    client = t['lead_client'](lead)
    client.post(f'/teams/{reg_id}/remove', data={'email': mates[0]})
    assert mates[0] not in _emails(t, reg_id)
