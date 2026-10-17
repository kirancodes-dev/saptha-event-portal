"""
tests/test_guest_registration.py — UPG-97 on the real database layer: an
email that already has an account can be registered without logging in.
Nobody is logged in and no account is created or changed; the account's
emails carry a "Not you? Cancel this registration" link, whose page asks
first and cancels once; the registration shows on the dashboard after login.
"""
import re

import pytest

from services_accounts import make_cancel_token
from tests import test_paid_events
from tests.test_integration_flow import _create_event, _login, _unique, _user
from tests.test_paid_events import _checkout, _verify

# UPG-30's fixtures: Razorpay keys, a fake client, captured mail and a paid event
rzp = test_paid_events.rzp
paid = test_paid_events.paid


@pytest.fixture
def free(real_app, monkeypatch):
    """A free event with open registration, and every email captured (the
    confirmation, which conftest silences, goes through the real sender)."""
    import routes_forms
    import utils_email
    flask_app, db = real_app
    mail = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k:
                        mail.append({'to': to, 'subject': subject, 'html': html}) or True)
    monkeypatch.setattr(routes_forms, 'send_registration_confirmed_email',
                        utils_email.send_registration_confirmed_email)
    spoc = f"{_unique('guestspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Open Day'), '2030-06-01',
                             fee=0, team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open'})
    return {'app': flask_app, 'db': db, 'event_id': event_id, 'mail': mail}


def _form(email):
    return {'privacy_consent': 'yes', 'full_name': 'Guest Er', 'email': email,
            'phone': '9876543210', 'usn': '1SN20CS077'}


def _cancel_links(mail, email):
    return [link for m in mail if m['to'] == email
            for link in re.findall(r'href="https?://[^/"]+(/forms/cancel/[^"]+)"', m['html'])]


def _reg_for(db, event_id, email):
    [(doc_id, reg)] = [(d.id, d.to_dict()) for d in db.collection('registrations')
                       .where('event_id', '==', event_id).stream() if d.to_dict().get('lead_email') == email]
    return doc_id, reg


ACCOUNT_FIELDS = ('email', 'name', 'role', 'password', 'phone', 'participant_type', 'email_verified')


def _account(db, email):
    """What registering must never change (XP for registering is fine)."""
    user = db.collection('users').document(email).get().to_dict() or {}
    return {k: user.get(k) for k in ACCOUNT_FIELDS}


def _count(db, event_id):
    return db.collection('events').document(event_id).get().to_dict().get('registration_count', 0)


def _registered_without_login(d):
    student = f"{_unique('guest')}@test.edu"
    _user(d['db'], student, 'Student')
    visitor = d['app'].test_client()
    resp = visitor.post(f"/forms/submit/{d['event_id']}", data=_form(student))
    return student, visitor, resp


# ── Criteria 1 and 2 ────────────────────────────────────────────────────────

def test_an_existing_account_registers_without_logging_in_and_gets_a_cancel_link(free):
    d = free
    student = f"{_unique('guest')}@test.edu"
    _user(d['db'], student, 'Student')
    before = _account(d['db'], student)

    visitor = d['app'].test_client()
    resp = visitor.post(f"/forms/submit/{d['event_id']}", data=_form(student))
    assert resp.status_code == 302 and resp.headers['Location'] == '/registration/confirmed'
    with visitor.session_transaction() as sess:
        assert 'user_id' not in sess
    _, reg = _reg_for(d['db'], d['event_id'], student)
    assert reg['status'] == 'Confirmed' and reg['registered_without_login'] is True
    assert _account(d['db'], student) == before
    mine = [m for m in d['mail'] if m['to'] == student]
    assert [m['subject'] for m in mine if 'Registration Confirmed' in m['subject']]
    assert not any('password' in m['subject'].lower() for m in mine)   # no set-password link
    assert len(_cancel_links(d['mail'], student)) == 1


def test_the_registration_shows_on_the_dashboard_after_login(free):
    d = free
    student, _, _ = _registered_without_login(d)
    title = d['db'].collection('events').document(d['event_id']).get().to_dict()['title']
    page = _login(d['app'], student, 'Student').get('/participant/dashboard')
    assert page.status_code == 200 and title in page.get_data(as_text=True)


def test_a_logged_in_registration_has_no_cancel_link(free):
    d = free
    student = f"{_unique('member')}@test.edu"
    _user(d['db'], student, 'Student')
    client = _login(d['app'], student, 'Student')
    client.post(f"/forms/submit/{d['event_id']}", data=_form(student))
    _, reg = _reg_for(d['db'], d['event_id'], student)
    assert 'registered_without_login' not in reg and _cancel_links(d['mail'], student) == []


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_a_paid_registration_without_login_gets_the_link_in_its_ticket_email(paid):
    d = paid
    student = f"{_unique('payguest')}@test.edu"
    _user(d['db'], student, 'Student')
    client, email, order = _checkout(d, email=student)   # sent to checkout, not to log in
    assert _verify(client, d, order['order_id'], f"pay_{_unique('g')}").status_code == 200
    tickets = [m for m in d['rzp']['mail'] if m['to'] == student and 'Registered —' in m['subject']]
    assert len(tickets) == 1 and len(_cancel_links(d['rzp']['mail'], student)) == 1

    # Cancelling it keeps the payment for the organisers to refund
    link = _cancel_links(d['rzp']['mail'], student)[0]
    page = d['app'].test_client().post(link)
    assert page.status_code == 200 and 'refund' in page.get_data(as_text=True)
    _, reg = _reg_for(d['db'], d['event_id'], student)
    assert reg['status'] == 'Cancelled' and reg['payment_status'] == 'Paid'
    assert 'refunded' in reg['cancel_reason']


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_cancel_link_asks_first_then_cancels_once(free):
    d = free
    student, _, _ = _registered_without_login(d)
    link = _cancel_links(d['mail'], student)[0]
    count = _count(d['db'], d['event_id'])
    stranger = d['app'].test_client()

    page = stranger.get(link)   # what a mail scanner does
    assert page.status_code == 200 and 'Cancel this registration?' in page.get_data(as_text=True)
    doc_id, reg = _reg_for(d['db'], d['event_id'], student)
    assert reg['status'] == 'Confirmed' and _count(d['db'], d['event_id']) == count

    done = stranger.post(link)
    assert done.status_code == 200 and 'Registration cancelled' in done.get_data(as_text=True)
    _, reg = _reg_for(d['db'], d['event_id'], student)
    assert reg['status'] == 'Cancelled' and 'emailed link' in reg['cancel_reason']
    assert _count(d['db'], d['event_id']) == count - 1
    audit = [e.to_dict() for e in d['db'].collection('audit_log').where('action', '==', 'REGISTRATION_CANCELLED').stream()]
    assert any(reg['reg_id'] in e.get('details', '') for e in audit)

    again = stranger.post(link)   # a second confirm changes nothing
    assert again.status_code == 200 and _count(d['db'], d['event_id']) == count - 1


def test_a_tampered_or_borrowed_cancel_token_changes_nothing(free):
    d = free
    student, _, _ = _registered_without_login(d)
    link = _cancel_links(d['mail'], student)[0]
    member = f"{_unique('member')}@test.edu"   # someone who registered while logged in
    _user(d['db'], member, 'Student')
    _login(d['app'], member, 'Student').post(f"/forms/submit/{d['event_id']}", data=_form(member))
    _, theirs = _reg_for(d['db'], d['event_id'], member)
    _, mine = _reg_for(d['db'], d['event_id'], student)
    with d['app'].app_context():
        borrowed = make_cancel_token(mine['reg_id'], member)        # my registration, another email
        not_guest = make_cancel_token(theirs['reg_id'], member)     # a logged-in registration
    count = _count(d['db'], d['event_id'])

    client = d['app'].test_client()
    for bad in (link[:-3] + 'xyz', f'/forms/cancel/{borrowed}', f'/forms/cancel/{not_guest}'):
        assert client.post(bad).status_code == 400, bad
    assert _reg_for(d['db'], d['event_id'], student)[1]['status'] == 'Confirmed'
    assert _reg_for(d['db'], d['event_id'], member)[1]['status'] == 'Confirmed'
    assert _count(d['db'], d['event_id']) == count


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_the_legacy_public_route_registers_an_existing_account_the_same_way(free):
    d = free
    student = f"{_unique('legacyguest')}@test.edu"
    _user(d['db'], student, 'Student')
    before = _account(d['db'], student)
    visitor = d['app'].test_client()
    resp = visitor.post(f"/participant/public_register/{d['event_id']}", data=_form(student))
    assert resp.headers['Location'] == '/registration/confirmed'
    with visitor.session_transaction() as sess:
        assert 'user_id' not in sess and sess['reg_confirmed']['is_new_user'] is False
    _, reg = _reg_for(d['db'], d['event_id'], student)
    assert reg['registered_without_login'] is True
    assert _account(d['db'], student) == before
    assert len(_cancel_links(d['mail'], student)) == 1
