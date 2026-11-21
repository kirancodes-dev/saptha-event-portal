"""
tests/test_sports_lead_confirms.py — UPG-389: in a sports event the team is
confirmed when the lead registers. The members the lead lists get no email to
confirm, and no account is made for them; the registrations page says why. The
organiser can still turn member confirmation on, and other team events still
ask each member, as before.
"""
from tests.test_team_member_confirm import _flashes, team  # noqa: F401

SPORTS = {'category': 'Sports', 'event_type': 'sports_tournament', 'details': {'sport': 'Kabaddi'}}


def test_a_sports_team_is_confirmed_by_the_lead_alone(team):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    mates = t['mates'](3)
    t['sent'].clear()
    lead, reg_id = t['register'](event_id, mates, team_name='Garuda Sena')
    assert [m['to'] for m in t['sent']] == [lead]                                  # the lead's ticket, nothing else
    assert t['sent'][0]['subject'].startswith('Registration Confirmed')
    reg = t['reg'](reg_id)
    assert str(reg.get('status')).lower() == 'confirmed'
    assert not any(m.get('confirm_email') for m in reg['members'])
    assert not any(t['db'].collection('users').document(m).get().exists for m in mates)

    page = t['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert 'data-sports-lead-only' in page and 'the team is confirmed when the lead registers' in page
    assert 'A member not confirmed' not in page and 'Everyone confirmed' not in page   # nobody waits


def test_the_organiser_can_still_ask_a_sports_teams_members(team):  # noqa: F811
    t = team
    event_id = t['event'](**SPORTS)
    resp = t['owner'].post(f'/coordinator/registrations/{event_id}/member_confirm', data={'on': '1'})
    assert resp.status_code == 302 and 'get a link to confirm' in _flashes(t['owner'])
    mates = t['mates']()
    t['sent'].clear()
    lead, _ = t['register'](event_id, mates)
    assert [m['to'] for m in t['sent']] == [lead] + mates


def test_a_team_event_that_isnt_sports_still_asks_each_member(team):  # noqa: F811
    t = team
    event_id = t['event'](category='Technical')
    mates = t['mates']()
    t['sent'].clear()
    lead, _ = t['register'](event_id, mates)
    assert [m['to'] for m in t['sent']] == [lead] + mates
