"""
tests/test_account_emails.py — UPG-33 on the real database layer: an account
someone else creates (walk-in, staff, SPOC) is opened with a one-time
set-password link, and no password ever travels by email or WhatsApp;
password-reset links work once.

To prove "no password", every plaintext handed to generate_password_hash
during the request is recorded, and none may appear in any message.
"""
import datetime
import io
import os
import re
import subprocess
import sys

import pytest
import werkzeug.security

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

NEW_PASSWORD = 'Brand-new-pass-42'


@pytest.fixture
def outbox(real_app, monkeypatch):
    """Every email and WhatsApp message, and every plaintext that was hashed."""
    import utils_email
    import utils_whatsapp
    import routes_coordinator
    sent = {'mail': [], 'whatsapp': [], 'plaintexts': []}
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k:
                        sent['mail'].append({'to': to, 'subject': subject, 'html': html}) or True)
    monkeypatch.setattr(utils_whatsapp, '_send', lambda phone, body:
                        sent['whatsapp'].append({'to': phone, 'body': body}) or True)
    monkeypatch.setattr(routes_coordinator, '_WA', True)  # send WhatsApp even without Twilio keys

    # Wrap every module's own generate_password_hash (some modules hold
    # werkzeug's, others a wrapper installed by a script at import time)
    def recording(original):
        def recording_hash(password, *a, **k):
            sent['plaintexts'].append(password)
            return original(password, *a, **k)
        recording_hash.recording = True
        return recording_hash
    for module in [werkzeug.security] + list(sys.modules.values()):
        original = getattr(module, 'generate_password_hash', None)
        if callable(original) and not getattr(original, 'recording', False):
            monkeypatch.setattr(module, 'generate_password_hash', recording(original))
    return sent


def _set_password_links(outbox, email):
    return [link for m in outbox['mail'] if m['to'] == email
            for link in re.findall(r'href="https?://[^/"]+(/set_password/[^"]+)"', m['html'])]


def _no_password_anywhere(outbox, email):
    secrets_ = [p for p in outbox['plaintexts'] if p and p != PASSWORD]
    assert secrets_, 'no account password was generated'
    for message in [m['subject'] + m['html'] for m in outbox['mail']] + [w['body'] for w in outbox['whatsapp']]:
        for plaintext in secrets_:
            assert plaintext not in message, f'a generated password was sent: {message[:200]}'


def _opens_with_the_link(flask_app, db, outbox, email, role):
    """The account can't be logged into yet; its one link sets a password once."""
    user = db.collection('users').document(email).get().to_dict()
    assert user['email_verified'] is False and user['needs_password_reset'] is True
    links = _set_password_links(outbox, email)
    assert len(links) == 1, links
    client = flask_app.test_client()
    resp = client.post(links[0], data={'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get('user_id') == email and sess.get('role') == role
    again = flask_app.test_client().get(links[0])
    assert again.status_code == 302 and again.headers['Location'] == '/login'  # used


def _spoc_and_event(flask_app, db):
    spoc = f"{_unique('acctspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(client, db, _unique('Staff Event'), datetime.date.today().isoformat(), team=False)
    title = db.collection('events').document(event_id).get().to_dict()['title']
    return client, event_id, title


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_walk_in_gets_a_set_password_link_and_no_password(real_app, outbox):
    flask_app, db = real_app
    spoc_client, event_id, title = _spoc_and_event(flask_app, db)
    coordinator = f"{_unique('desk')}@test.edu"
    _user(db, coordinator, 'EventCoordinator')
    db.collection('events').document(event_id).update({
        'staff': [{'email': coordinator, 'name': 'Desk', 'role': 'EventCoordinator'}]})
    desk = _login(flask_app, coordinator, 'EventCoordinator')
    walk_in = f"{_unique('walkin')}@test.edu"

    resp = desk.post('/coordinator/process_walkin', data={
        'event_id': event_id, 'email': walk_in, 'name': 'Walk In', 'usn': '1SN20CS111',
        'phone': '9876543210', 'payment_mode': 'Cash'})
    assert resp.status_code == 302

    _no_password_anywhere(outbox, walk_in)
    ticket = [m for m in outbox['mail'] if m['to'] == walk_in and 'set_password' not in m['html']]
    assert ticket, 'the walk-in still gets their ticket'
    assert any(title in m['html'] for m in outbox['mail'] if m['to'] == walk_in)
    _opens_with_the_link(flask_app, db, outbox, walk_in, 'Student')


@pytest.mark.parametrize('path', ['coordinator assign_staff', 'spoc assign_coordinator',
                                  'spoc add_judge', 'spoc judges csv'])
def test_new_staff_get_a_set_password_link_and_no_password(real_app, outbox, path):
    flask_app, db = real_app
    spoc_client, event_id, title = _spoc_and_event(flask_app, db)
    staff = f"{_unique('staff')}@test.edu"

    if path == 'coordinator assign_staff':
        resp = spoc_client.post(f'/coordinator/assign_staff/{event_id}', data={
            'name': 'Sam Staff', 'email': staff, 'role': 'Judge', 'phone': '9876500000'})
        role = 'Judge'
    elif path == 'spoc assign_coordinator':
        resp = spoc_client.post(f'/spoc/assign_coordinator/{event_id}', data={
            'coordinator_email': staff, 'coordinator_name': 'Sam Staff'})
        role = 'EventCoordinator'
    elif path == 'spoc add_judge':
        resp = spoc_client.post(f'/spoc/add_judge/{event_id}', data={'judge_name': 'Sam Staff', 'judge_email': staff})
        role = 'Judge'
    else:
        resp = spoc_client.post(f'/spoc/upload_judges_csv/{event_id}', content_type='multipart/form-data', data={
            'judges_csv': (io.BytesIO(f'name,email\nSam Staff,{staff}\n'.encode()), 'judges.csv')})
        role = 'Judge'
    assert resp.status_code == 302

    _no_password_anywhere(outbox, staff)
    if path == 'coordinator assign_staff':
        assert len(outbox['whatsapp']) == 1  # an appointment notice, without credentials
        assert title in outbox['whatsapp'][0]['body'] and staff in outbox['whatsapp'][0]['body']
    _opens_with_the_link(flask_app, db, outbox, staff, role)


def test_appointed_spoc_gets_a_set_password_link_and_the_form_asks_no_password(real_app, outbox):
    flask_app, db = real_app
    admin = f"{_unique('appointer')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    client = flask_app.test_client()
    client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert 'name="password"' not in client.get('/admin/dashboard').get_data(as_text=True).split('/admin/appoint_spoc')[1][:1500]

    spoc = f"{_unique('newspoc')}@test.edu"
    resp = client.post('/admin/appoint_spoc', data={'name': 'New Spoc', 'email': spoc, 'category': 'Technical',
                                                    'password': 'Typed-by-admin-1'})  # ignored if sent
    assert resp.status_code == 302
    user = db.collection('users').document(spoc).get().to_dict()
    assert user['role'] == 'ClubSPOC' and user['category'] == 'Technical'
    assert 'Typed-by-admin-1' not in outbox['plaintexts']
    _no_password_anywhere(outbox, spoc)
    _opens_with_the_link(flask_app, db, outbox, spoc, 'ClubSPOC')


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def _reset_links(outbox, email):
    return [link for m in outbox['mail'] if m['to'] == email
            for link in re.findall(r'href="https?://[^/"]+(/reset_token/[^"]+)"', m['html'])]


def _can_log_in(flask_app, email, password):
    client = flask_app.test_client()
    client.post('/login', data={'role': 'Student', 'email': email, 'password': password})
    with client.session_transaction() as sess:
        return sess.get('user_id') == email


def test_a_reset_link_works_once(real_app, outbox):
    flask_app, db = real_app
    student = f"{_unique('forgetful')}@test.edu"
    _user(db, student, 'Student')

    flask_app.test_client().post('/forgot_password', data={'email': student})
    flask_app.test_client().post('/forgot_password', data={'email': student})
    first, second = _reset_links(outbox, student)

    assert flask_app.test_client().get(first).status_code == 200
    resp = flask_app.test_client().post(first, data={'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert resp.status_code == 302 and resp.headers['Location'] == '/login'
    assert _can_log_in(flask_app, student, NEW_PASSWORD)

    # The same link again, and the other link issued before the change: refused
    for link in (first, second):
        assert flask_app.test_client().get(link).headers['Location'] == '/forgot_password'
        resp = flask_app.test_client().post(link, data={'new_password': 'Another-pass-99', 'confirm_password': 'Another-pass-99'})
        assert resp.status_code == 302 and resp.headers['Location'] == '/forgot_password'
    assert _can_log_in(flask_app, student, NEW_PASSWORD)
    assert not _can_log_in(flask_app, student, 'Another-pass-99')


def test_no_app_module_sends_credentials():
    """The password-carrying senders are gone from app code (scratch/ and the
    functions/ copy are removed by UPG-15)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(['git', 'grep', '-n', '-E', r'send_credentials_email\(|send_staff_credentials_whatsapp|raw_password=[A-Z_a-z]',
                          '--', '*.py', ':!functions/', ':!scratch/', ':!tests/', ':!utils_email.py', ':!tasks/email_tasks.py'],
                         cwd=root, capture_output=True, text=True)
    assert out.stdout == ''
