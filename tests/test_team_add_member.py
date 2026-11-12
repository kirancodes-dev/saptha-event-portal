"""
tests/test_team_add_member.py — UPG-241 on the real database layer, with a
mail provider configured (UPG-207's fixture: Brevo's sender replaced).

A team lead who registered fewer people than the event allows adds members
from the team page, up to the limit (here 4, the lead included): the new
member is on the registration (so the ticket, check-in and the SPOC's list see
them), gets a link to confirm and set a password, and a portal notice. To
replace someone, the lead removes them and adds the new person. Refused: a
full team, someone already registered for the event, a bad email, after
registration closes, after check-in, a per-person fee; only the lead may add.
"""
import datetime

from tests import test_team_member_confirm as _tc
from tests.test_integration_flow import _login, _unique, _user
from tests.test_team_member_confirm import _flashes, _to

team = _tc.team   # UPG-207's fixture


def _add(client, reg_id, email, name='Nina New', usn='1sn22cs299', phone='9123456789'):
    return client.post(f'/teams/{reg_id}/members/add',
                       data={'name': name, 'email': email, 'usn': usn, 'phone': phone})


def _emails(t, reg_id):
    return [str(m.get('email') or '').lower() for m in t['reg'](reg_id)['members']]


# ── Criterion 1: the lead adds members up to the limit ──────────────────────

def test_a_lead_with_three_of_four_adds_one_more_and_then_the_team_is_full(team):
    t = team
    event_id = t['event']()
    mates = t['mates'](2)
    lead, reg_id = t['register'](event_id, mates=mates)       # 3 of 4
    client = t['lead_client'](lead)
    page = client.get(f'/teams/{reg_id}').get_data(as_text=True)
    assert 'data-add-member-form' in page and 'Room for 1 more.' in page

    new = f"{_unique('newbie')}@test.edu"
    t['sent'].clear()
    resp = _add(client, reg_id, new)
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/teams/{reg_id}')
    flashes = _flashes(client)
    assert 'Nina New is added. Your team now has 4 of 4.' in flashes and 'confirm and set a password' in flashes
    assert new in _emails(t, reg_id) and len(_emails(t, reg_id)) == 4
    member = t['member'](reg_id, new)
    assert member['usn'] == '1SN22CS299' and member['phone'] == '9123456789' and member['added_by'] == lead
    assert t['reg'](reg_id)['member_count'] == 4

    # One email: the link to confirm and set a password; one portal notice
    [mail] = _to(t['sent'], new)
    assert '/teams/confirm/' in mail['html']
    assert any(n.to_dict().get('type') == 'team_added' for n in t['db'].collection('notifications_v2').stream()
               if n.to_dict().get('user_email') == new)
    assert any(a.to_dict().get('action') == 'TEAM_MEMBER_ADDED' for a in t['db'].collection('audit_log').stream())

    # Now full: the form is gone and a fifth is refused
    page = client.get(f'/teams/{reg_id}').get_data(as_text=True)
    assert 'data-add-member-form' not in page and 'Your team is full: 4 people' in page
    _add(client, reg_id, f"{_unique('fifth')}@test.edu")
    assert 'Your team is full' in _flashes(client) and len(_emails(t, reg_id)) == 4

    # The SPOC's list shows the new member
    spoc_page = t['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert new in spoc_page


# ── Criterion 2: replace = remove, then add ─────────────────────────────────

def test_the_lead_replaces_a_member_by_removing_then_adding(team):
    t = team
    event_id = t['event']()
    mates = t['mates'](3)
    lead, reg_id = t['register'](event_id, mates=mates)       # 4 of 4: full
    client = t['lead_client'](lead)
    assert 'data-add-member-form' not in client.get(f'/teams/{reg_id}').get_data(as_text=True)
    client.post(f'/teams/{reg_id}/remove', data={'email': mates[0]})
    replacement = f"{_unique('swap')}@test.edu"
    _add(client, reg_id, replacement, name='Sam Swap')
    emails = _emails(t, reg_id)
    assert mates[0] not in emails and replacement in emails and len(emails) == 4


# ── Criterion 3: what's refused ─────────────────────────────────────────────

def test_bad_input_someone_already_registered_and_the_lead_twice_are_refused(team):
    t = team
    event_id = t['event']()
    lead, reg_id = t['register'](event_id, mates=t['mates'](1))
    other_lead, _ = t['register'](event_id, mates=t['mates'](1), team_name='Others')
    client = t['lead_client'](lead)
    before = _emails(t, reg_id)
    cases = [
        ({'email': 'not-an-email'}, 'Enter a valid email address'),
        ({'email': f"{_unique('x')}@test.edu", 'name': ''}, "Enter the new member's name."),
        ({'email': f"{_unique('x')}@test.edu", 'phone': 'call me'}, 'Enter a valid phone number'),
        ({'email': lead}, 'is already on your team'),
        ({'email': other_lead}, 'is already registered for this event with another team'),
    ]
    for extra, message in cases:
        kwargs = dict({'name': 'Nina New'}, **extra)
        _add(client, reg_id, kwargs.pop('email'), **kwargs)
        assert message in _flashes(client), message
    assert _emails(t, reg_id) == before


def test_only_the_lead_may_add(team):
    t = team
    event_id = t['event']()
    mates = t['mates'](1)
    lead, reg_id = t['register'](event_id, mates=mates)
    stranger = f"{_unique('stranger')}@test.edu"
    _user(t['db'], stranger, 'Student')
    assert _add(_login(t['app'], stranger, 'Student'), reg_id, f"{_unique('x')}@test.edu").status_code == 403
    _user(t['db'], mates[0], 'Student')
    member_client = _login(t['app'], mates[0], 'Student')
    assert _add(member_client, reg_id, f"{_unique('x')}@test.edu").status_code == 403
    assert 'data-add-member-form' not in member_client.get(f'/teams/{reg_id}').get_data(as_text=True)
    assert len(_emails(t, reg_id)) == 2


# ── Criterion 4: closed registration, check-in, a per-person fee ────────────

def test_no_adding_after_registration_closes_after_check_in_or_with_a_per_person_fee(team):
    t = team
    db = t['db']
    closed = t['event']()
    lead, reg_id = t['register'](closed, mates=t['mates'](1))
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    db.collection('events').document(closed).update({'deadline': yesterday})
    client = t['lead_client'](lead)
    assert 'Registration for this event has closed' in client.get(f'/teams/{reg_id}').get_data(as_text=True)
    _add(client, reg_id, f"{_unique('late')}@test.edu")
    assert 'Registration for this event has closed' in _flashes(client) and len(_emails(t, reg_id)) == 2

    arrived = t['event']()
    lead2, reg2 = t['register'](arrived, mates=t['mates'](1), team_name='Here Already')
    db.collection('registrations').document(reg2).update({'attendance': 'Present'})
    client2 = t['lead_client'](lead2)
    _add(client2, reg2, f"{_unique('late')}@test.edu")
    assert 'checked in' in _flashes(client2) and len(_emails(t, reg2)) == 2

    per_person = t['event']()
    lead3, reg3 = t['register'](per_person, mates=t['mates'](1), team_name='Per Head')
    db.collection('events').document(per_person).update({'ticket_types': [
        {'id': 'std', 'name': 'Standard', 'price': 100, 'per': 'person', 'seats': 0}]})
    db.collection('registrations').document(reg3).update({'ticket_type_id': 'std'})
    client3 = t['lead_client'](lead3)
    _add(client3, reg3, f"{_unique('extra')}@test.edu")
    assert 'The fee for this event is per person' in _flashes(client3) and len(_emails(t, reg3)) == 2
