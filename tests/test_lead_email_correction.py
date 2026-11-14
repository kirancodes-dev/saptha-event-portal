"""
tests/test_lead_email_correction.py — UPG-256 on the real database layer, with
a mail provider configured (UPG-207's fixture).

A lead who mistyped their email at registration gets no login. The event's
SPOC types the right address on the registration's edit page: the team moves
to it, it gets a set-password link (or, with an account already, an email
to sign in), the old address loses the team and the account nobody used is
removed; the ticket's generation goes up, so the old QR stops working.
"""
import re

import services_team_confirm
from tests import test_team_member_confirm as _tc
from tests.test_integration_flow import PASSWORD, _login, _unique, _user
from tests.test_team_member_confirm import _flashes, _to

team = _tc.team   # UPG-207's fixture


def _correct(client, event_id, reg_id, new):
    return client.post(f'/coordinator/registrations/{event_id}/lead_email/{reg_id}', data={'new_email': new})


def _user_doc(t, email):
    doc = t['db'].collection('users').document(email).get()
    return (doc.to_dict() or {}) if doc.exists else None


def test_the_spoc_moves_the_team_to_the_right_address_which_gets_the_login(team):
    t = team
    event_id = t['event']()
    typo = f"{_unique('lena')}@tset.edu"
    mates = t['mates'](1)
    _, reg_id = t['register'](event_id, mates=mates, lead=typo)
    assert _user_doc(t, typo)['needs_password_reset'] is True           # made at registration, never used
    gen = int(t['reg'](reg_id).get('ticket_gen') or 0)

    page = t['owner'].get(f'/coordinator/registrations/{event_id}/edit/{reg_id}').get_data(as_text=True)
    assert 'data-lead-email' in page and typo in page

    right = f"{_unique('lena')}@test.edu"
    t['sent'].clear()
    resp = _correct(t['owner'], event_id, reg_id, right)
    assert resp.status_code == 302
    assert f"The lead's email is now {right}" in _flashes(t['owner'])
    reg = t['reg'](reg_id)
    assert reg['lead_email'] == right and int(reg.get('ticket_gen') or 0) == gen + 1
    assert reg['email_corrections'][-1]['from'] == typo
    lead_row = next(m for m in reg['members'] if str(m.get('role')).lower() == 'lead')
    assert lead_row['email'] == right
    assert mates[0] in [m['email'] for m in reg['members']]              # the team stays

    [mail] = _to(t['sent'], right)
    assert re.search(r'/set_password/', mail['html'])
    assert _user_doc(t, typo) is None                                   # nobody used it: removed
    assert _user_doc(t, right)['needs_password_reset'] is True

    # The right address, once it has a password, leads the team
    from werkzeug.security import generate_password_hash
    t['db'].collection('users').document(right).update({'password': generate_password_hash(PASSWORD),
                                                         'needs_password_reset': False})
    page = _login(t['app'], right, 'Student').get(f'/teams/{reg_id}').get_data(as_text=True)
    assert 'data-add-member' in page and 'Make a new code' in page              # the lead's own tools
    assert any(a.to_dict().get('action') == 'LEAD_EMAIL_CORRECTED' for a in t['db'].collection('audit_log').stream())


def test_an_address_with_an_account_is_told_to_sign_in_and_a_used_old_account_stays(team):
    t = team
    event_id = t['event']()
    typo = f"{_unique('used')}@test.edu"
    _, reg_id = t['register'](event_id, mates=t['mates'](1), lead=typo)
    t['db'].collection('users').document(typo).update({'needs_password_reset': False, 'email_verified': True})
    known = f"{_unique('known')}@test.edu"
    _user(t['db'], known, 'Student', name='Known Lead')
    t['sent'].clear()
    _correct(t['owner'], event_id, reg_id, known)
    assert 'already has an account' in _flashes(t['owner'])
    [mail] = _to(t['sent'], known)
    assert 'Sign in' in mail['html'] and '/set_password/' not in mail['html']
    assert _user_doc(t, typo) is not None                               # someone used it: kept
    assert t['reg'](reg_id)['lead_email'] == known
    from werkzeug.security import generate_password_hash
    t['db'].collection('users').document(typo).update({'password': generate_password_hash(PASSWORD)})
    old_client = _login(t['app'], typo, 'Student')
    old_client.get(f'/teams/{reg_id}')
    assert "You don't have access to this team." in _flashes(old_client)


def test_refused_after_check_in_with_a_certificate_for_a_taken_address_and_for_other_staff(team, monkeypatch):
    t = team
    db = t['db']
    event_id = t['event']()
    lead, reg_id = t['register'](event_id, mates=t['mates'](1))
    other_lead, _ = t['register'](event_id, mates=t['mates'](1), team_name='Taken')

    for bad, message in (('not-an-email', 'Enter a valid email address.'),
                         (lead, "That's the email the lead already has."),
                         (other_lead, 'is already registered for this event')):
        _correct(t['owner'], event_id, reg_id, bad)
        assert message in _flashes(t['owner']), message
    assert t['reg'](reg_id)['lead_email'] == lead

    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    assert _correct(_login(t['app'], other, 'ClubSPOC'), event_id, reg_id,
                    f"{_unique('x')}@test.edu").status_code == 403

    real = services_team_confirm._has_certificate   # put back by hand: undoing all would also undo real_app's db
    monkeypatch.setattr(services_team_confirm, '_has_certificate', lambda event_id, email: True)
    _correct(t['owner'], event_id, reg_id, f"{_unique('x')}@test.edu")
    assert 'A certificate has already been issued' in _flashes(t['owner'])
    monkeypatch.setattr(services_team_confirm, '_has_certificate', real)

    db.collection('registrations').document(reg_id).update({'attendance': 'Present'})
    page = t['owner'].get(f'/coordinator/registrations/{event_id}/edit/{reg_id}').get_data(as_text=True)
    assert 'data-lead-email' not in page
    _correct(t['owner'], event_id, reg_id, f"{_unique('x')}@test.edu")
    assert 'checked in' in _flashes(t['owner']) and t['reg'](reg_id)['lead_email'] == lead


def test_each_row_of_the_spocs_list_links_straight_to_the_lead_email_form(team):
    t = team
    event_id = t['event']()
    _, reg_id = t['register'](event_id, mates=t['mates'](1))
    _, done_id = t['register'](event_id, mates=t['mates'](1), team_name='Checked In')
    t['db'].collection('registrations').document(done_id).update({'attendance': 'Present'})
    page = t['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)

    def doc_id(public):
        [d] = [d.id for d in t['db'].collection('registrations').where('event_id', '==', event_id).stream()
               if (d.to_dict() or {}).get('reg_id') == public or d.id == public]
        return d
    link = f'/coordinator/registrations/{event_id}/edit/{doc_id(reg_id)}#lead-email'
    assert f'href="{link}"' in page
    assert f'/edit/{doc_id(done_id)}#lead-email' not in page            # checked in: the email can't change
    edit = t['owner'].get(link.split('#')[0]).get_data(as_text=True)
    assert 'id="lead-email"' in edit
