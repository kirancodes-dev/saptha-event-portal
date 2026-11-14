"""
tests/test_member_own_details.py — UPG-251 on the real database layer, with a
mail provider configured (UPG-207's fixture).

A member the lead added with only a name and email opens their confirm link,
sees what the lead typed, corrects the name and fills in their USN and phone
while choosing a password. What they type is saved on the team (so the SPOC's
list and the export have it) and fills their profile where it was empty. A
member who already has an account confirms by signing in; a USN or phone the
team lacks comes from their profile.
"""
from tests import test_team_member_confirm as _tc
from tests.test_integration_flow import _login, _unique, _user
from tests.test_team_member_confirm import NEW_PASSWORD, _flashes, _link, _to

team = _tc.team   # UPG-207's fixture


def test_a_member_added_without_usn_or_phone_fills_them_in_when_confirming(team):
    t = team
    event_id = t['event']()
    lead, reg_id = t['register'](event_id, mates=t['mates'](1))
    client = t['lead_client'](lead)
    new = f"{_unique('bare')}@test.edu"
    t['sent'].clear()
    client.post(f'/teams/{reg_id}/members/add', data={'name': 'nina', 'email': new})
    member = t['member'](reg_id, new)
    assert not member.get('usn') and not member.get('phone')

    link = _link(_to(t['sent'], new)[0])
    visitor = t['app'].test_client()
    page = visitor.get(link).get_data(as_text=True)
    assert 'data-member-details' in page and 'value="nina"' in page and 'name="usn"' in page

    # A bad phone is refused and nothing is confirmed
    visitor.post(link, data={'details': '1', 'name': 'Nina Nair', 'usn': '1sn22cs301', 'phone': 'call me',
                             'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert 'Enter a valid phone number' in _flashes(visitor)
    assert not t['member'](reg_id, new).get('confirmed_at')

    visitor = t['app'].test_client()
    resp = visitor.post(link, data={'details': '1', 'name': 'Nina Nair', 'usn': '1sn22cs301', 'phone': '9123400000',
                                    'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert resp.status_code == 302
    member = t['member'](reg_id, new)
    assert member['confirmed_at'] and member['name'] == 'Nina Nair'
    assert member['usn'] == '1SN22CS301' and member['phone'] == '9123400000'
    profile = t['db'].collection('users').document(new).get().to_dict()
    assert profile.get('usn') == '1SN22CS301' and profile.get('phone') == '9123400000'

    spoc_page = t['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert '1SN22CS301' in spoc_page and '9123400000' in spoc_page


def test_blank_fields_keep_what_the_lead_typed(team):
    t = team
    event_id = t['event']()
    mate = t['mates'](1)
    lead, reg_id = t['register'](event_id, mates=mate)          # the fixture gives Mate 1 a USN
    link = _link(_to(t['sent'], mate[0])[0])
    t['app'].test_client().post(link, data={'details': '1', 'name': '', 'usn': '', 'phone': '',
                                            'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    member = t['member'](reg_id, mate[0])
    assert member['confirmed_at'] and member['name'] == 'Mate 1' and member['usn'] == '1SN22CS201'


def test_a_member_with_an_account_gets_a_missing_usn_and_phone_from_their_profile(team):
    t = team
    event_id = t['event']()
    lead, reg_id = t['register'](event_id, mates=t['mates'](1))
    known = f"{_unique('known')}@test.edu"
    _user(t['db'], known, 'Student', name='Kiran Known')
    t['db'].collection('users').document(known).update({'usn': '1SN21EC042', 'phone': '9000000042'})
    t['sent'].clear()
    t['lead_client'](lead).post(f'/teams/{reg_id}/members/add', data={'name': 'Kiran Known', 'email': known})
    link = _link(_to(t['sent'], known)[0])
    member_client = _login(t['app'], known, 'Student')
    member_client.get(link)
    member = t['member'](reg_id, known)
    assert member['confirmed_by'] == 'sign-in'
    assert member['usn'] == '1SN21EC042' and member['phone'] == '9000000042'
