"""
tests/test_seat_email.py — UPG-240 on the real database layer.

When the SPOC cancels or deletes a team, the count goes down by one, the first
in line on the waitlist is registered and the count goes back up, and the one
who joined gets ONE email: registered (or the pay link), with a set-password
link in the same email when their account has no password yet. Their team
gets a portal notice each. A portal-mode hackathon sends it too (UPG-237).
If they still haven't set a password or paid a day later, one reminder; never
two. The SPOC's Accept sends the same single email.
"""
import datetime

import services_seat_email as seat
from tests import test_spoc_waitlist as _wl
from tests.test_integration_flow import _user
from tests.test_spoc_waitlist import _accept, _full_event, _join, _regs_of

host = _wl.host   # UPG-211's fixture, through UPG-230's tests


def _taker(h, event_id):
    """The registration holding the event's one seat."""
    [reg_id] = [d.id for d in h['db'].collection('registrations').where('event_id', '==', event_id).stream()
                if d.to_dict().get('team_name') == 'Seat Takers']
    return reg_id


def _mails_to(h, email):
    return [m for m in h['emails'] if m['to'] == email]


def _later(hours=25):
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours)


def _reminder(h, reg_id):
    doc = h['db'].collection('seat_reminders').document(reg_id).get()
    return doc.to_dict() if doc.exists else None


def _remind(h, now=None):
    """The hourly job's seat reminders, as the cron endpoint runs them (in the app)."""
    with h['app'].app_context():
        return seat.send_reminders(h['db'], now=now)


def _delete(client, event_id, reg_id):
    return client.post(f'/coordinator/registrations/{event_id}/delete_team',
                       data={'reg_id': reg_id, 'confirm': 'yes'})


# ── Criterion 1: cancel → count down → next in → one email with the link ───

def test_a_cancelled_team_frees_its_seat_and_the_next_gets_one_email_with_a_password_link(host):
    h = host
    event_id = _full_event(h)
    title = h['db'].collection('events').document(event_id).get().to_dict()['title']
    _, lead, mate = _join(h, event_id, 'Next Up')
    _join(h, event_id, 'After Them')
    h['emails'].clear()

    h['cancel'](h['owner'], event_id, _taker(h, event_id), 'Duplicate team')
    assert h['count'](event_id) == 1                          # one out, one in
    [reg] = _regs_of(h, event_id, lead)
    assert reg['status'] == 'Confirmed'

    [mail] = _mails_to(h, lead)                               # ONE email
    assert mail['subject'] == f"You're in: a seat opened for {title}"
    assert 'Next Up' in mail['message'] and reg['reg_id'] in mail['message']
    assert "you haven't set a password yet" in mail['message'] and '/set_password/' in mail['message']
    assert '/participant/dashboard' in mail['message']
    assert reg['seat_email']['status'] == 'sent' and reg['seat_email']['password_link'] is True
    user = h['db'].collection('users').document(lead).get().to_dict()
    assert user['login_link']['status'] == 'sent' and user['login_link']['expires_at']

    # The team member gets a portal notice
    notes = [n.to_dict() for n in h['db'].collection('notifications_v2').stream()
             if n.to_dict().get('user_email') == mate and n.to_dict().get('type') == 'waitlist_promoted']
    assert len(notes) == 1

    # The set-password link in the email works
    link = mail['message'].split('/set_password/', 1)[1].split()[0]
    resp = h['app'].test_client().get(f'/set_password/{link}')
    assert resp.status_code == 200


# ── Criterion 2: delete does the same; deleting a cancelled team doesn't ────

def test_deleting_a_team_promotes_the_next_once_and_a_cancelled_team_not_again(host):
    h = host
    event_id = _full_event(h)
    _, first, _ = _join(h, event_id, 'First In')
    _, second, _ = _join(h, event_id, 'Second In')
    taker = _taker(h, event_id)
    h['emails'].clear()

    assert _delete(h['owner'], event_id, taker).status_code == 302
    assert not h['db'].collection('registrations').document(taker).get().exists
    assert h['count'](event_id) == 1 and len(_mails_to(h, first)) == 1
    assert _regs_of(h, event_id, second) == []                # only one seat freed

    # Cancel the promoted team, then delete it: one promotion, not two
    [first_reg] = _regs_of(h, event_id, first)
    h['cancel'](h['owner'], event_id, first_reg['id'], 'Changed their mind')
    assert h['count'](event_id) == 1 and len(_mails_to(h, second)) == 1
    _delete(h['owner'], event_id, first_reg['id'])
    assert h['count'](event_id) == 1 and len(_mails_to(h, second)) == 1


# ── Criterion 3: an account with a password gets no link ───────────────────

def test_someone_with_a_password_gets_the_email_without_a_link(host):
    h = host
    event_id = _full_event(h)
    _, lead, _ = _join(h, event_id, 'Has Password')
    _user(h['db'], lead, 'Student', name='Pat Password')        # a password they chose
    h['db'].collection('users').document(lead).update({'needs_password_reset': False})
    h['emails'].clear()
    h['cancel'](h['owner'], event_id, _taker(h, event_id), 'Duplicate team')
    [mail] = _mails_to(h, lead)
    assert '/set_password/' not in mail['message'] and 'Log in with this email and your password' in mail['message']
    [reg] = _regs_of(h, event_id, lead)
    assert _reminder(h, reg['reg_id']) is None                # nothing left to do: no reminder
    _remind(h, now=_later())
    assert len(_mails_to(h, lead)) == 1


# ── Criterion 4: paid: the pay link, and one reminder a day later ──────────

def test_a_paid_seat_emails_the_pay_link_and_reminds_once(host):
    h = host
    event_id = _full_event(h, fee=200)
    title = h['db'].collection('events').document(event_id).get().to_dict()['title']
    wl_id, lead, _ = _join(h, event_id, 'Pay Later')
    h['db'].collection('users').document(lead).update({'needs_password_reset': False})
    h['emails'].clear()
    _accept(h['owner'], event_id, wl_id)
    [reg] = _regs_of(h, event_id, lead)
    pay = f"/payment/pay/{reg['reg_id']}"
    [mail] = _mails_to(h, lead)
    assert pay in mail['message'] and mail['subject'] == f"Accepted from the waitlist: pay to confirm {title}"
    assert _reminder(h, reg['reg_id'])['status'] == 'due'

    h['emails'].clear()
    _remind(h)                                                # not yet a day
    assert _mails_to(h, lead) == [] and _reminder(h, reg['reg_id'])['status'] == 'due'
    _remind(h, now=_later())
    [reminder] = _mails_to(h, lead)
    assert reminder['subject'] == f"Reminder: pay to confirm your seat for {title}" and pay in reminder['message']
    assert _reminder(h, reg['reg_id'])['status'] == 'sent'
    _remind(h, now=_later(50))                                # never twice
    assert len(_mails_to(h, lead)) == 1


# ── Criterion 5: the password reminder; none once it's set ──────────────────

def test_the_password_reminder_goes_once_and_not_after_the_password_is_set(host):
    h = host
    event_id = _full_event(h)
    title = h['db'].collection('events').document(event_id).get().to_dict()['title']
    _, lead, _ = _join(h, event_id, 'Forgetful')
    _, other, _ = _join(h, event_id, 'Diligent')
    h['cancel'](h['owner'], event_id, _taker(h, event_id), 'Duplicate team')
    [lead_reg] = _regs_of(h, event_id, lead)
    h['cancel'](h['owner'], event_id, lead_reg['id'], 'Swapped')                # the next one moves up too
    _, filler, _ = _join(h, event_id, 'Filler')
    [other_reg] = _regs_of(h, event_id, other)
    h['emails'].clear()
    h['db'].collection('users').document(other).update({'needs_password_reset': False})   # set meanwhile

    _remind(h, now=_later())
    # The cancelled team, and the one who set a password: closed, no email
    assert _reminder(h, lead_reg['reg_id'])['status'] == 'done'
    assert _reminder(h, other_reg['reg_id'])['status'] == 'done'
    assert _mails_to(h, lead) == [] and _mails_to(h, other) == []

    # A fresh promotion whose person never sets a password gets one reminder with a new link
    h['cancel'](h['owner'], event_id, other_reg['id'], 'Swapped again')
    assert len(_mails_to(h, filler)) == 1
    h['emails'].clear()
    _remind(h, now=_later())
    [reminder] = _mails_to(h, filler)
    assert reminder['subject'] == f"Reminder: set your password for {title}" and '/set_password/' in reminder['message']
    _remind(h, now=_later(60))
    assert len(_mails_to(h, filler)) == 1


# ── Criterion 6: a portal-mode hackathon emails the automatic promotion ─────

def test_a_portal_mode_hackathon_emails_the_person_moved_up(host):
    h = host
    event_id = _full_event(h, event_type='hackathon', timezone='Asia/Kolkata')
    import services_hackathon as hk
    assert hk.portal_only(h['db'].collection('events').document(event_id).get().to_dict())
    _, lead, _ = _join(h, event_id, 'Hack Next')
    h['emails'].clear()
    h['cancel'](h['owner'], event_id, _taker(h, event_id), 'Duplicate team')
    [mail] = _mails_to(h, lead)
    assert 'a seat opened' in mail['subject'] and '/set_password/' in mail['message']


# ── Criterion 7: the SPOC's Accept sends the same one email ────────────────

def test_the_spocs_accept_sends_one_email_with_the_password_link(host):
    h = host
    event_id = _full_event(h)
    wl_id, lead, _ = _join(h, event_id, 'Chosen')
    h['emails'].clear()
    resp = _accept(h['owner'], event_id, wl_id)
    assert resp.status_code == 302
    [mail] = _mails_to(h, lead)
    assert 'accepted' in mail['message'] and '/set_password/' in mail['message']
    with h['owner'].session_transaction() as s:
        flashes = [m for _, m in s.get('_flashes', [])]
    assert any('It has a link to set their password.' in m for m in flashes)
