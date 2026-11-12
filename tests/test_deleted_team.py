"""
tests/test_deleted_team.py — UPG-245 on the real database layer.

Owner, 2026-11-12: "a student who was deleted must be deleted from that event,
but the portal account exists, and for the next event, added by hand or
registered, they can take part". Deleting a team removes it from that event
only: the lead's and members' accounts stay and they log in; the event leaves
their portal, including a waitlist card that said "Accepted"; they register
again (this event or another), or the SPOC adds them by hand.
"""
from tests import test_spoc_waitlist as _wl
from tests.test_spoc_add_team import _add
from tests.test_integration_flow import _login, _user
from tests.test_spoc_waitlist import _accept, _entry, _full_event, _join, _regs_of

host = _wl.host   # UPG-211's fixture, through UPG-230's tests


def _delete(h, event_id, reg_id):
    return h['owner'].post(f'/coordinator/registrations/{event_id}/delete_team',
                           data={'reg_id': reg_id, 'confirm': 'yes'})


def _sign_up(h, event_id, lead, team):
    return h['app'].test_client().post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Back Again', 'email': lead, 'phone': '9876543210',
        'usn': '1SN22CS600', 'team_name': team,
        'member_1_name': 'New Mate', 'member_1_email': f'{team.replace(" ", "").lower()}@test.edu',
        'member_1_usn': '1SN22CS601'})


def test_a_deleted_team_leaves_the_event_but_keeps_its_accounts_and_signs_up_again(host):
    h = host
    db = h['db']
    event_id, other = h['event'](), h['event']()
    reg_id, lead, mate = h['register'](event_id)
    assert _delete(h, event_id, reg_id).status_code == 302
    assert not db.collection('registrations').document(reg_id).get().exists
    assert db.collection('users').document(lead).get().exists               # the portal account stays

    _user(db, lead, 'Student')                                              # (a password, to log in here)
    client = _login(h['app'], lead, 'Student')
    title = db.collection('events').document(event_id).get().to_dict()['title']
    assert title not in client.get('/participant/my_events').get_data(as_text=True)

    assert _sign_up(h, other, lead, 'Next Event Team').status_code == 302    # another event
    assert [r['status'] for r in _regs_of(h, other, lead)] == ['Confirmed']
    assert _sign_up(h, event_id, lead, 'Same Event Again').status_code == 302   # this event again
    assert [r['status'] for r in _regs_of(h, event_id, lead)] == ['Confirmed']
    assert _sign_up(h, other, mate, 'Mate Leads Now').status_code == 302     # a member, now as a lead
    assert [r['status'] for r in _regs_of(h, other, mate)] == ['Confirmed']


def test_the_spoc_adds_a_deleted_lead_by_hand_to_another_event(host):
    h = host
    event_id, other = h['event'](), h['event']()
    reg_id, lead, _ = h['register'](event_id)
    _delete(h, event_id, reg_id)
    resp, _, _ = _add(h['owner'], other, team='Second Chance', lead=lead)
    assert resp.status_code == 302
    [reg] = _regs_of(h, other, lead)
    assert reg['status'] == 'Confirmed' and reg['team_name'] == 'Second Chance'


def test_a_team_accepted_from_the_waitlist_then_deleted_no_longer_shows_accepted(host):
    h = host
    db = h['db']
    event_id = _full_event(h)
    wl_id, lead, mate = _join(h, event_id, 'Came Off The List')
    _accept(h['owner'], event_id, wl_id)
    [reg] = _regs_of(h, event_id, lead)
    _user(db, lead, 'Student')
    client = _login(h['app'], lead, 'Student')
    mine = client.get('/participant/my_events?tab=waitlisted').get_data(as_text=True)
    assert 'data-waitlist-standing="accepted"' in mine and 'Came Off The List' in mine

    _delete(h, event_id, reg['id'])
    assert _entry(h, wl_id)['status'] == 'removed'
    import services_waitlist
    assert services_waitlist.standing(db, lead) == [] and services_waitlist.standing(db, mate) == []
    mine = client.get('/participant/my_events?tab=waitlisted').get_data(as_text=True)
    assert 'data-waitlist-standing' not in mine and 'Came Off The List' not in mine


def test_an_old_promoted_entry_whose_team_is_gone_is_not_shown(host):
    """Data from before this change: the entry still says promoted, the registration is gone."""
    h = host
    db = h['db']
    event_id = _full_event(h)
    wl_id, lead, _ = _join(h, event_id, 'Old Data Team')
    _accept(h['owner'], event_id, wl_id)
    [reg] = _regs_of(h, event_id, lead)
    db.collection('registrations').document(reg['id']).delete()             # deleted the old way
    assert _entry(h, wl_id)['status'] == 'promoted'
    import services_waitlist
    assert services_waitlist.standing(db, lead) == []
