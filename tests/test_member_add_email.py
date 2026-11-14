"""
tests/test_member_add_email.py — UPG-262 on the real database layer, every
email through the real send path (Brevo's sender replaced).

A member saved with no email ("Email: —") had no way to get one: the lead's
"Correct the email" and the SPOC's form find a member by their email. Now the
lead (team page) and the hosting SPOC (the registration's edit page) add an
email to such a member, on a team that already exists, and the new address
gets the link to confirm and set a password. With member confirmation off the
email is saved and nothing is sent.
"""
import re

from tests.test_integration_flow import _login, _unique, _user
from tests.test_team_member_confirm import _actions, _flashes, _link, _to, team  # noqa: F401  (fixture)

NAME = 'Rudra Pratab Singh'


def _without_email(t, event_id):
    """A registered team whose second member has a name and no email."""
    keep, drop = t['mates']()
    lead, reg_id = t['register'](event_id, [keep, drop])
    members = [dict(m, email='', name=NAME, confirm_email='', confirm_nonce='')
               if (m.get('email') or '').lower() == drop else m for m in t['reg'](reg_id)['members']]
    t['db'].collection('registrations').document(reg_id).update({'members': members})
    assert any(m.get('name') == NAME and not m.get('email') for m in t['reg'](reg_id)['members'])
    t['sent'].clear()
    return lead, reg_id


def _named(t, reg_id):
    return next(m for m in t['reg'](reg_id)['members'] if m.get('name') == NAME)


# ── Criterion 1: the lead adds the email on the team page ──────────────────

def test_the_lead_adds_an_email_to_a_member_who_has_none_and_they_get_their_link(team):  # noqa: F811
    t = team
    event_id = t['event']()
    lead, reg_id = _without_email(t, event_id)
    lead_c = t['lead_client'](lead)
    page = lead_c.get(f'/teams/{reg_id}').get_data(as_text=True)
    assert 'data-add-email' in page and 'has no email yet' in page
    assert f'value="name:{NAME}"' in page

    # A wrong address, and one already registered for the event, are refused
    url = f'/teams/{reg_id}/members/email'
    lead_c.post(url, data={'email': f'name:{NAME}', 'new_email': 'not-an-email'})
    assert 'valid email' in _flashes(lead_c)
    lead_c.post(url, data={'email': f'name:{NAME}', 'new_email': lead})
    assert 'already registered' in _flashes(lead_c)
    assert _named(t, reg_id)['email'] == '' and t['sent'] == []

    rudra = f"{_unique('rudra')}@test.edu"
    lead_c.post(url, data={'email': f'name:{NAME}', 'new_email': rudra.upper()})
    assert f'Email added {rudra}' in _flashes(lead_c)
    assert _named(t, reg_id)['email'] == rudra
    [mail] = _to(t['sent'], rudra)
    assert t['app'].test_client().get(_link(mail)).status_code == 200       # the link works
    assert 'TEAM_MEMBER_EMAIL_ADDED' in _actions(db=t['db'], needle=reg_id)

    page = lead_c.get(f'/teams/{reg_id}').get_data(as_text=True)
    assert 'has no email yet' not in page
    assert re.search(rf'data-member="{re.escape(rudra)}".*?data-status="waiting"', page, re.S)


def test_only_the_lead_adds_a_members_email_on_the_team_page(team):  # noqa: F811
    t = team
    event_id = t['event']()
    _, reg_id = _without_email(t, event_id)
    other_lead, _ = t['register'](event_id, t['mates'](1), team_name='Other Team')
    resp = t['lead_client'](other_lead).post(f'/teams/{reg_id}/members/email',
                                             data={'email': f'name:{NAME}', 'new_email': 'x@test.edu'})
    assert resp.status_code == 403 and _named(t, reg_id)['email'] == ''


# ── Criterion 2: the hosting SPOC adds it on the registration's edit page ──

def test_the_spoc_adds_an_email_to_a_member_who_has_none_and_another_spoc_cannot(team):  # noqa: F811
    t = team
    event_id = t['event']()
    _, reg_id = _without_email(t, event_id)
    edit = f'/coordinator/registrations/{event_id}/edit/{reg_id}'
    page = t['owner'].get(edit).get_data(as_text=True)
    assert 'data-add-email' in page and 'none yet' in page and f'value="name:{NAME}"' in page

    url = f'/coordinator/registrations/{event_id}/member_email'
    other = f"{_unique('otherspoc')}@test.edu"
    _user(t['db'], other, 'ClubSPOC')
    assert _login(t['app'], other, 'ClubSPOC').post(url, data={
        'reg_id': reg_id, 'email': f'name:{NAME}', 'new_email': 'y@test.edu'}).status_code == 403

    rudra = f"{_unique('rudra')}@test.edu"
    resp = t['owner'].post(url, data={'reg_id': reg_id, 'email': f'name:{NAME}', 'new_email': rudra})
    assert resp.status_code == 302 and resp.headers['Location'].endswith(edit)
    assert f'Email added {rudra}' in _flashes(t['owner'])
    assert _named(t, reg_id)['email'] == rudra
    [mail] = _to(t['sent'], rudra)
    assert len(re.findall(r'/teams/confirm/', mail['html'])) >= 1
    assert 'data-add-email' not in t['owner'].get(edit).get_data(as_text=True)


# ── Criterion 3: member confirmation off: saved, nothing sent ──────────────

def test_with_member_confirmation_off_the_email_is_saved_and_nothing_is_sent(team):  # noqa: F811
    t = team
    event_id = t['event'](member_confirm=False)
    _, reg_id = _without_email(t, event_id)
    rudra = f"{_unique('rudra')}@test.edu"
    t['owner'].post(f'/coordinator/registrations/{event_id}/member_email',
                    data={'reg_id': reg_id, 'email': f'name:{NAME}', 'new_email': rudra})
    assert 'no link is sent' in _flashes(t['owner'])
    assert _named(t, reg_id)['email'] == rudra and t['sent'] == []
