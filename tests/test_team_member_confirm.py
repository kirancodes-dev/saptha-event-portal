"""
tests/test_team_member_confirm.py — UPG-207 on the real database layer, with a
mail provider configured (Brevo's sender replaced, so nothing leaves the
machine and the daily limit counts): each member the team lead lists gets one
email to confirm and get a portal login, in a portal-mode hackathon too;
setting a password (or signing in) from the link confirms them, without a
second account; the lead sees who confirmed, can resend (3 a day) and correct
an email, and others can't; a confirmed member sees their own certificate; an
email can't move away from an issued certificate; the daily limit holds sends
back and the organiser's button sends them once; the export shows each
member's status.
"""
import csv
import datetime
import io
import random
import re

import pytest
from werkzeug.security import check_password_hash

import routes_forms
import services_certificate_design as design
import services_certificates as certs
import services_email_quota as quota
import services_team_confirm as confirm
import utils_email
from tests.test_certificate_design import artwork
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user
from tests.test_low_email_auth import NEW_PASSWORD, REAL_CONFIRM, REAL_SEND


@pytest.fixture
def team(real_app, monkeypatch, tmp_path):
    flask_app, db = real_app
    monkeypatch.setenv('PRIVATE_STORAGE_DIR', str(tmp_path / 'private'))
    monkeypatch.setattr(utils_email, '_send', REAL_SEND)
    monkeypatch.setattr(routes_forms, 'send_registration_confirmed_email', REAL_CONFIRM)
    monkeypatch.setenv('BREVO_API_KEY', 'test-brevo-key')
    monkeypatch.setenv('MAIL_FROM', 'SapthaEvent <events@test.edu>')
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 450)
    fresh = f"{random.randint(2100, 2899)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    monkeypatch.setattr(quota, 'today', lambda: fresh)                    # a day of its own, nothing sent yet
    sent = []
    monkeypatch.setattr(utils_email, '_send_via_brevo', lambda to, subject, html, attachments=None: sent.append(
        {'to': to, 'subject': subject, 'html': html}) or True)

    spoc = f"{_unique('tcspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()

    def event(**fields):
        event_id = _create_event(owner, db, _unique('Team Confirm'), day, team=True)
        db.collection('events').document(event_id).update(dict({'status': 'registration_open', 'venue': 'Hall A'},
                                                                **fields))
        return event_id

    def register(event_id, mates=(), lead=None, team_name='Byte Force'):
        lead = lead or f"{_unique('lead')}@test.edu"
        form = {'privacy_consent': 'yes', 'full_name': 'Lena Lead', 'email': lead, 'phone': '9876543210',
                'usn': '1SN22CS200', 'team_name': team_name}
        for i, email in enumerate(mates, start=1):
            form.update({f'member_{i}_name': f'Mate {i}', f'member_{i}_email': email,
                         f'member_{i}_usn': f'1SN22CS20{i}'})
        resp = flask_app.test_client().post(f'/forms/submit/{event_id}', data=form)
        assert resp.status_code == 302, resp.data[:300]
        [reg_id] = [d.to_dict().get('reg_id') or d.id for d in db.collection('registrations')
                    .where('event_id', '==', event_id).stream() if d.to_dict().get('lead_email') == lead]
        return lead, reg_id

    def mates(n=2):
        return [f"{_unique(f'mate{i}')}@test.edu" for i in range(1, n + 1)]

    def reg(reg_id):
        return db.collection('registrations').document(reg_id).get().to_dict()

    def member(reg_id, email):
        return next(m for m in reg(reg_id)['members'] if (m.get('email') or '').lower() == email)

    def lead_client(lead):
        # The lead's account came from the registration: give it a password to log in with
        from werkzeug.security import generate_password_hash
        db.collection('users').document(lead).update({'password': generate_password_hash(PASSWORD),
                                                      'needs_password_reset': False})
        return _login(flask_app, lead, 'Student')

    return {'app': flask_app, 'db': db, 'owner': owner, 'spoc': spoc, 'event': event, 'register': register,
            'mates': mates, 'sent': sent, 'reg': reg, 'member': member, 'lead_client': lead_client}


def _to(sent, email):
    return [m for m in sent if m['to'] == email]


def _link(mail):
    [path] = re.findall(r'href="https?://[^/"]+(/teams/confirm/[^"]+)"', mail['html'])
    return path


def _flashes(client):
    with client.session_transaction() as sess:
        return ' '.join(m for _, m in sess.get('_flashes', []))


def _actions(db, needle):
    return [a.to_dict().get('action') for a in db.collection('audit_log').stream()
            if needle in str(a.to_dict().get('details') or '')]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_a_team_of_three_sends_the_lead_one_email_and_each_member_one_link(team):
    t = team
    for fields in ({}, {'event_type': 'hackathon', 'timezone': 'Asia/Kolkata'}):   # also in portal mode
        event_id = t['event'](**fields)
        if fields:
            import services_hackathon as hk
            assert hk.portal_only(t['db'].collection('events').document(event_id).get().to_dict())
        mates = t['mates']()
        t['sent'].clear()
        lead, reg_id = t['register'](event_id, mates)
        assert [m['to'] for m in t['sent']] == [lead] + mates, fields
        assert t['sent'][0]['subject'].startswith('Registration Confirmed')
        for mate in mates:
            [mail] = _to(t['sent'], mate)
            assert mail['subject'].startswith('Confirm your place in Byte Force')
            assert 'Lena Lead' in mail['html'] and 'Confirm and set your password' in mail['html']
            assert _link(mail)
            account = t['db'].collection('users').document(mate).get().to_dict()
            assert account['needs_password_reset'] is True             # unverified until the link is used
            assert confirm.status(t['member'](reg_id, mate))['key'] == 'waiting'

    # Switched off: members get nothing, as before
    event_id = t['event'](member_confirm=False)
    mates = t['mates']()
    t['sent'].clear()
    lead, _ = t['register'](event_id, mates)
    assert [m['to'] for m in t['sent']] == [lead]
    assert not any(t['db'].collection('users').document(m).get().exists for m in mates)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_setting_a_password_or_signing_in_from_the_link_confirms_without_a_second_account(team):
    t = team
    db, flask_app = t['db'], t['app']
    known = f"{_unique('known')}@test.edu"
    _user(db, known, 'Student', name='Kim Known')
    new = f"{_unique('fresh')}@test.edu"
    event_id = t['event']()
    lead, reg_id = t['register'](event_id, [new, known])

    # A new member: the link's page asks for a password; a weak one is refused
    [mail] = _to(t['sent'], new)
    client = flask_app.test_client()
    page = client.get(_link(mail)).get_data(as_text=True)
    assert 'Confirm your team place' in page and 'name="new_password"' in page
    resp = client.post(_link(mail), data={'new_password': 'short', 'confirm_password': 'short'})
    assert resp.status_code == 302 and not t['member'](reg_id, new).get('confirmed_at')
    resp = client.post(_link(mail), data={'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/teams/{reg_id}')
    member = t['member'](reg_id, new)
    assert member['confirmed_at'] and member['confirmed_by'] == 'link'
    assert datetime.datetime.fromisoformat(member['confirmed_at']) <= datetime.datetime.now(datetime.timezone.utc)
    account = db.collection('users').document(new).get().to_dict()
    assert account['needs_password_reset'] is False and check_password_hash(account['password'], NEW_PASSWORD)
    with client.session_transaction() as sess:
        assert sess['user_id'] == new                                    # signed in
    assert client.get(f'/teams/{reg_id}').status_code == 200
    # The link works once
    again = flask_app.test_client()
    again.get(_link(mail))
    assert 'already confirmed' in _flashes(again)

    # A member with an account: "Sign in to confirm"; signing in from the link confirms
    [mail] = _to(t['sent'], known)
    assert 'Sign in to confirm' in mail['html']
    anon = flask_app.test_client()
    resp = anon.get(_link(mail))
    assert resp.status_code == 302 and resp.headers['Location'].startswith('/login?next=/teams/confirm/')
    assert not t['member'](reg_id, known).get('confirmed_at')
    signed = _login(flask_app, known, 'Student')
    resp = signed.get(_link(mail))
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/teams/{reg_id}')
    assert t['member'](reg_id, known)['confirmed_by'] == 'sign-in'
    account = db.collection('users').document(known).get().to_dict()
    assert check_password_hash(account['password'], PASSWORD) and account['name'] == 'Kim Known'   # untouched
    users = [d for d in db.collection('users').where('email', '==', known).stream()]
    assert len(users) == 1                                               # no second account


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_lead_sees_status_resends_three_times_and_corrects_an_email_others_cannot(team):
    t = team
    db, flask_app = t['db'], t['app']
    event_id = t['event']()
    a, b = t['mates']()
    lead, reg_id = t['register'](event_id, [a, b])
    client = flask_app.test_client()
    client.post(_link(_to(t['sent'], a)[0]), data={'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})

    lead_c = t['lead_client'](lead)
    page = lead_c.get(f'/teams/{reg_id}').get_data(as_text=True)
    assert re.search(rf'data-member="{re.escape(a)}".*?data-status="confirmed"', page, re.S)
    assert re.search(rf'data-member="{re.escape(b)}".*?data-status="waiting"', page, re.S)
    assert '3 of 3 resends left today' in page

    # Resends: three, then refused
    first_link = _link(_to(t['sent'], b)[0])
    for n in range(3):
        lead_c.post(f'/teams/{reg_id}/members/resend', data={'email': b})
        assert 'A new link was sent' in _flashes(lead_c), n
    lead_c.post(f'/teams/{reg_id}/members/resend', data={'email': b})
    assert 'already resent 3 times' in _flashes(lead_c)
    assert len(_to(t['sent'], b)) == 4                                   # the first and three resends
    stale = flask_app.test_client()
    stale.get(first_link)
    assert 'no longer works' in _flashes(stale)                          # a resend replaced the first link

    # Correcting the email: the new address gets a link; the old one stops working
    fixed = f"{_unique('fixed')}@test.edu"
    old_link = _link(_to(t['sent'], b)[-1])
    lead_c.post(f'/teams/{reg_id}/members/email', data={'email': b, 'new_email': fixed})
    assert f'Email changed to {fixed}' in _flashes(lead_c)
    assert [m['email'] for m in t['reg'](reg_id)['members']].count(fixed) == 1
    [mail] = _to(t['sent'], fixed)
    gone = flask_app.test_client()
    gone.get(old_link)
    assert 'no longer works' in _flashes(gone)
    ok = flask_app.test_client()
    assert ok.get(_link(mail)).status_code == 200                        # the new link works
    assert 'TEAM_CONFIRM_EMAIL' in _actions(db, reg_id) and 'TEAM_MEMBER_EMAIL_CORRECTED' in _actions(db, reg_id)

    # Another team's lead, and a member, can do neither
    other_lead, _ = t['register'](event_id, t['mates'](1), team_name='Other Team')
    for c in (t['lead_client'](other_lead), client):                    # `client` is `a`, signed in by the link
        assert c.post(f'/teams/{reg_id}/members/resend', data={'email': fixed}).status_code == 403
        assert c.post(f'/teams/{reg_id}/members/email', data={'email': fixed, 'new_email': 'x@test.edu'}).status_code == 403
    assert t['member'](reg_id, fixed)


# ── Criteria 4 and 5 ────────────────────────────────────────────────────────

def _ended_with_design(t, event_id):
    t['db'].collection('events').document(event_id).update({
        'date': '2020-01-10', 'end_date': '2020-01-10', 'start_datetime': '2020-01-10T10:00',
        'end_datetime': '2020-01-10T17:00', 'reg_deadline': '2020-01-09', 'status': 'completed'})
    design.upload(t['db'], event_id, artwork(), 'design.png', t['spoc'])


def test_a_confirmed_member_sees_and_downloads_their_certificate_and_a_waiting_one_is_issued(team):
    t = team
    db, flask_app = t['db'], t['app']
    event_id = t['event'](event_type='hackathon', timezone='Asia/Kolkata')    # portal mode
    joined, waiting = t['mates']()
    lead, reg_id = t['register'](event_id, [joined, waiting])
    member_c = flask_app.test_client()
    member_c.post(_link(_to(t['sent'], joined)[0]), data={'new_password': NEW_PASSWORD,
                                                         'confirm_password': NEW_PASSWORD})
    db.collection('registrations').document(reg_id).update({'attendance': 'Present'})
    _ended_with_design(t, event_id)
    certs.issue_event(db, event_id, t['spoc'], only=['participation'])

    issued = {c['email']: c for c in certs.for_event(event_id)}
    assert {lead, joined, waiting} <= set(issued)                        # the waiting member's too
    page = member_c.get('/certificates/mine').get_data(as_text=True)
    number = issued[joined]['number']
    assert number in page and issued[waiting]['number'] not in page
    pdf = member_c.get(f'/certificates/c/{number}/pdf')
    assert pdf.status_code == 200 and pdf.data[:5] == b'%PDF-'

    # Criterion 5: the waiting member's email can't move away from their certificate
    lead_c = t['lead_client'](lead)
    lead_c.post(f'/teams/{reg_id}/members/email', data={'email': waiting, 'new_email': f"{_unique('n')}@test.edu"})
    message = _flashes(lead_c)
    assert 'certificate has already been issued' in message and "organiser" in message
    assert t['member'](reg_id, waiting)['email'] == waiting
    page = lead_c.get(f'/teams/{reg_id}').get_data(as_text=True)
    assert waiting in page


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_the_daily_limit_holds_links_back_and_the_organisers_button_sends_them_once(team, monkeypatch):
    t = team
    flask_app = t['app']
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 1)
    event_id = t['event']()
    mates = t['mates']()
    lead, reg_id = t['register'](event_id, mates)
    assert [m['to'] for m in t['sent']] == [lead]                        # the limit took the members' links
    assert {confirm.status(t['member'](reg_id, m))['key'] for m in mates} == {'held'}
    page = t['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert '2 held back by the daily email limit' in page and page.count('data-member-status="held"') == 2
    assert 'Send confirmation links to waiting members' in page

    # Still at the limit: nothing sent, still held
    t['owner'].post(f'/coordinator/registrations/{event_id}/member_links')
    assert len(t['sent']) == 1
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 450)     # a new day's room
    t['owner'].post(f'/coordinator/registrations/{event_id}/member_links')
    t['owner'].post(f'/coordinator/registrations/{event_id}/member_links')
    assert sorted(m['to'] for m in t['sent'][1:]) == sorted(mates)       # once each
    assert {confirm.status(t['member'](reg_id, m))['key'] for m in mates} == {'waiting'}


# ── Criterion 7 ─────────────────────────────────────────────────────────────

def test_the_organisers_button_sends_earlier_teams_once_and_skips_confirmed_and_invite_members(team):
    t = team
    db, flask_app = t['db'], t['app']
    event_id = t['event'](member_confirm=False)                            # teams registered before
    early = t['mates'](3)
    lead, reg_id = t['register'](event_id, early[:2])
    lead2, reg2 = t['register'](event_id, early[2:], team_name='Second')
    joiner = f"{_unique('joiner')}@test.edu"
    _user(db, joiner, 'Student')
    _login(flask_app, joiner, 'Student').post('/teams/join', data={'join_code': t['reg'](reg_id)['team_code']})
    assert t['member'](reg_id, joiner)['confirmed_by'] == 'invite'

    # The organiser switches it on for the event
    t['owner'].post(f'/coordinator/registrations/{event_id}/member_confirm', data={'on': '1'})
    assert db.collection('events').document(event_id).get().to_dict()['member_confirm'] is True
    confirm.confirm(db, reg2, early[2], 'sign-in')                       # already confirmed somehow
    t['sent'].clear()
    t['owner'].post(f'/coordinator/registrations/{event_id}/member_links')
    assert sorted(m['to'] for m in t['sent']) == sorted(early[:2])      # not the confirmed or the joiner
    t['owner'].post(f'/coordinator/registrations/{event_id}/member_links')
    assert len(t['sent']) == 2                                           # nothing on a second press
    assert 'TEAM_CONFIRM_BULK' in _actions(db, event_id)
    student = _login(flask_app, joiner, 'Student')
    assert student.post(f'/coordinator/registrations/{event_id}/member_links').status_code in (302, 403)
    assert len(t['sent']) == 2


# ── Criterion 8 ─────────────────────────────────────────────────────────────

def test_the_registrations_export_shows_each_members_status(team):
    t = team
    event_id = t['event']()
    a, b = t['mates']()
    lead, reg_id = t['register'](event_id, [a, b])
    confirm.confirm(t['db'], reg_id, a, 'link')
    resp = t['owner'].get(f'/coordinator/export_registrations/{event_id}')
    assert resp.status_code == 200
    rows = list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))
    [row] = [r for r in rows if r['Lead Email'] == lead]
    assert 'Mate 1 (1SN22CS201) [Confirmed]' in row['Members']
    assert 'Mate 2 (1SN22CS202) [Waiting]' in row['Members']
