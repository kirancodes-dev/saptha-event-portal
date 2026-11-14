"""
tests/test_member_logins.py — UPG-260, UPG-209 and UPG-261 on the real
database layer, every email through the real send path (Brevo replaced).

UPG-260: an account that exists always gets its password-reset link; nobody
is sent to "contact the organizer" for a reset (PARTICIPANT_RESET_LIMIT is 0
by default; the request throttle and the daily email limit still apply).

UPG-209: a team accepted from the waitlist sends each member the link to
confirm and set a password, as a sign-up from the form does.

UPG-261: the SPOC's "Send password link" on a team also sends each member who
hasn't confirmed their own link, not only the lead.
"""
import datetime

from services_accounts import ORGANIZER_MESSAGE, REGISTERED_AT
from tests.test_integration_flow import _login, _unique, _user
from tests.test_low_email_auth import _flashes, _links, _to, _user_doc, low  # noqa: F401  (fixture)


def _reset(app, email):
    client = app.test_client()
    page = client.post('/forgot_password', data={'email': email}, follow_redirects=True).get_data(as_text=True)
    return page


# ── UPG-260: an account that exists always gets its reset link ─────────────

def test_a_registration_account_gets_a_reset_link_every_time_and_never_the_organizer_message(low):  # noqa: F811
    app, db = low['app'], low['db']
    event_id, _ = low['event'](team=False)
    lead, _ = low['register'](event_id)
    low['sent'].clear()

    for _ in range(2):
        page = _reset(app, lead)
        assert ORGANIZER_MESSAGE not in page
    mails = _to(low['sent'], lead)
    assert len(mails) == 2 and all(len(_links(m, 'reset_token')) == 1 for m in mails)

    # Registered long ago: still a link
    db.collection('users').document(lead).update(
        {REGISTERED_AT: (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()})
    page = _reset(app, lead)
    assert ORGANIZER_MESSAGE not in page and len(_to(low['sent'], lead)) == 3
    assert _user_doc(db, lead)['reset_last']['status'] == 'sent'

    # An unknown email: the same answer, nothing sent
    nobody = f"{_unique('nobody')}@test.edu"
    page = _reset(app, nobody)
    assert "If an account exists for this email" in page and _to(low['sent'], nobody) == []


# ── UPG-209: a team accepted from the waitlist: each member gets a link ────

def _full(low, **fields):  # noqa: F811
    db = low['db']
    event_id, _ = low['event']()
    limits = db.collection('events').document(event_id).get().to_dict().get('limits') or {}
    db.collection('events').document(event_id).update(dict({'limits': dict(limits, max_participants=1)}, **fields))
    low['register'](event_id, mates=low['mates'](1))
    return event_id


def _wait(low, event_id):  # noqa: F811
    mates = low['mates'](2)
    lead, _ = low['register'](event_id, mates=mates)
    [wl_id] = [d.id for d in low['db'].collection('waitlists').where('event_id', '==', event_id).stream()
               if d.to_dict().get('email') == lead]
    return wl_id, lead, mates


def test_a_team_accepted_from_the_waitlist_sends_each_member_a_link(low):  # noqa: F811
    event_id = _full(low)
    wl_id, lead, mates = _wait(low, event_id)
    low['sent'].clear()
    resp = low['owner'].post(f'/coordinator/registrations/{event_id}/accept_waitlist', data={'wl_id': wl_id})
    assert resp.status_code == 302
    for mate in mates:
        [mail] = _to(low['sent'], mate)
        assert len(_links(mail, 'teams/confirm')) == 1
    assert _to(low['sent'], lead)                                       # the lead's own email, as before


def test_with_member_confirmation_off_an_accepted_team_sends_members_nothing(low):  # noqa: F811
    event_id = _full(low, member_confirm=False)
    wl_id, _, mates = _wait(low, event_id)
    low['sent'].clear()
    low['owner'].post(f'/coordinator/registrations/{event_id}/accept_waitlist', data={'wl_id': wl_id})
    assert all(_to(low['sent'], mate) == [] for mate in mates)


# ── UPG-261: the SPOC's "Send password link" reaches every member ──────────

def _reg(low, event_id, lead):  # noqa: F811
    [doc] = [d for d in low['db'].collection('registrations').where('event_id', '==', event_id).stream()
             if d.to_dict().get('lead_email') == lead]
    return doc.id, doc.to_dict()


def test_the_spocs_send_password_link_also_sends_each_unconfirmed_member_theirs(low):  # noqa: F811
    db = low['db']
    event_id, _ = low['event']()
    mates = low['mates'](2)
    lead, _ = low['register'](event_id, mates=mates)
    reg_id, reg = _reg(low, event_id, lead)
    # The first mate has confirmed: they have their login already
    members = [dict(m, confirmed_at='2026-11-14T10:00:00') if str(m.get('email')).lower() == mates[0] else m
               for m in reg['members']]
    db.collection('registrations').document(reg_id).update({'members': members})
    low['sent'].clear()

    page = low['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert 'Send password links' in page
    owner = low['owner']
    owner.post(f'/coordinator/registrations/{event_id}/login_link', data={'reg_id': reg_id})
    assert len(_to(low['sent'], lead)) == 1                             # the lead's set-password link
    assert _to(low['sent'], mates[0]) == []                             # confirmed: nothing
    [mail] = _to(low['sent'], mates[1])
    assert len(_links(mail, 'teams/confirm')) == 1
    assert any('Team members: 1 sent' in f for f in _flashes(owner))

    # Another SPOC can't send anyone's link
    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    low['sent'].clear()
    resp = _login(low['app'], other, 'ClubSPOC').post(f'/coordinator/registrations/{event_id}/login_link',
                                                      data={'reg_id': reg_id})
    assert resp.status_code == 403 and low['sent'] == []
