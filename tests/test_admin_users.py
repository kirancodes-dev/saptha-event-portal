"""
tests/test_admin_users.py — UPG-40 on the real database layer: the Super Admin
sees who still has to set a password and can email them a fresh
set-password link. Nobody else can, and accounts that already have a
password, or are Super Admins, never get one.
"""
import re

import pytest

from services_accounts import create_unverified_account
from tests.test_integration_flow import PASSWORD, _login, _unique, _user

NEW_PASSWORD = 'Brand-new-pass-42'


@pytest.fixture
def mail(real_app, monkeypatch):
    import utils_email
    sent = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k:
                        sent.append({'to': to, 'subject': subject, 'html': html}) or True)
    return sent


def _admin(flask_app, db):
    admin = f"{_unique('usersadmin')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    client = flask_app.test_client()
    resp = client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                       'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert resp.status_code == 302 and resp.headers['Location'] != '/login'
    return client, admin


def _row(html, email):
    rows = [r for r in re.findall(r'<tr>(.*?)</tr>', html, re.S) if f'<td>{email}</td>' in r]
    assert len(rows) == 1, f'{email} listed {len(rows)} times'
    return rows[0]


def _set_password_links(mail, email):
    return [link for m in mail if m['to'] == email
            for link in re.findall(r'href="https?://[^/"]+(/set_password/[^"]+)"', m['html'])]


def _resend(client, email):
    return client.post('/admin/users/resend_set_password', data={'email': email})


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_super_admin_sees_who_is_waiting_and_a_resend_button_only_for_them(real_app):
    flask_app, db = real_app
    client, _ = _admin(flask_app, db)
    waiting = f"{_unique('waiting')}@test.edu"
    create_unverified_account(db, waiting, 'Wanda Waiting', role='Judge')
    has_password = f"{_unique('haspw')}@test.edu"
    _user(db, has_password, 'ClubSPOC', name='Pat Password')

    resp = client.get('/admin/users')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="main-content"' in html and 'href="/admin/users"' in html  # shared layout, nav link

    row = _row(html, waiting)
    assert 'Wanda Waiting' in row and 'Judge' in row and 'Waiting for first password' in row
    form = re.search(r'<form method="POST" action="/admin/users/resend_set_password">(.*?)</form>', row, re.S)
    assert form and f'name="email" value="{waiting}"' in form.group(1)
    assert 'name="csrf_token"' in form.group(1) and 'Resend set-password link' in form.group(1)

    row = _row(html, has_password)
    assert 'Pat Password' in row and 'ClubSPOC' in row and 'Waiting' not in row
    assert '<form' not in row and 'Resend' not in row

    # The Super Admin's own dashboard links to the page
    assert 'href="/admin/users"' in client.get('/admin/dashboard').get_data(as_text=True)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_a_resend_emails_one_working_link_and_is_audit_logged(real_app, mail):
    flask_app, db = real_app
    client, admin = _admin(flask_app, db)
    spoc = f"{_unique('expiredspoc')}@test.edu"
    assert client.post('/admin/appoint_spoc', data={
        'name': 'Late Spoc', 'email': spoc, 'category': 'Technical'}).status_code == 302
    mail.clear()  # the first link has gone unused; send a new one

    resp = _resend(client, spoc)
    assert resp.status_code == 302 and resp.headers['Location'] == '/admin/users'
    assert [m['to'] for m in mail] == [spoc]
    links = _set_password_links(mail, spoc)
    assert len(links) == 1, links
    assert 'A new set-password link was emailed' in client.get('/admin/users').get_data(as_text=True)

    person = flask_app.test_client()
    resp = person.post(links[0], data={'new_password': NEW_PASSWORD, 'confirm_password': NEW_PASSWORD})
    assert resp.status_code == 302
    with person.session_transaction() as sess:
        assert sess.get('user_id') == spoc and sess.get('role') == 'ClubSPOC'
    later = flask_app.test_client()
    later.post('/login', data={'role': 'ClubSPOC', 'email': spoc, 'password': NEW_PASSWORD})
    with later.session_transaction() as sess:
        assert sess.get('user_id') == spoc

    entries = [d.to_dict() for d in db.collection('audit_log').where('actor_email', '==', admin).stream()]
    resent = [e for e in entries if e['action'] == 'SET_PASSWORD_LINK_RESENT']
    assert len(resent) == 1 and spoc in resent[0]['details']

    # Now that the password is set, the page offers no button for it
    assert 'Resend' not in _row(client.get('/admin/users').get_data(as_text=True), spoc)


# ── Criterion 3 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('role', ['ClubSPOC', 'Student', None])
def test_only_the_super_admin_can_open_the_page_or_resend(real_app, mail, role):
    flask_app, db = real_app
    waiting = f"{_unique('target')}@test.edu"
    create_unverified_account(db, waiting, 'Tess Target', role='EventCoordinator')
    if role:
        someone = f"{_unique('notadmin')}@test.edu"
        _user(db, someone, role)
        client = _login(flask_app, someone, role)
    else:
        client = flask_app.test_client()

    for resp in (client.get('/admin/users'), _resend(client, waiting)):
        assert resp.status_code == 403 or (resp.status_code == 302 and resp.headers['Location'] == '/login'), \
            (resp.status_code, resp.headers.get('Location'))
    assert mail == []
    assert db.collection('users').document(waiting).get().to_dict()['needs_password_reset'] is True


def test_accounts_with_a_password_and_super_admins_are_refused(real_app, mail):
    flask_app, db = real_app
    client, admin = _admin(flask_app, db)
    has_password = f"{_unique('haspw')}@test.edu"
    _user(db, has_password, 'Judge')
    other_admin = f"{_unique('newadmin')}@test.edu"
    create_unverified_account(db, other_admin, 'Second Admin', role='SuperAdmin')

    html = client.get('/admin/users').get_data(as_text=True)
    row = _row(html, other_admin)
    assert 'Waiting for first password' in row and '<form' not in row

    resp = _resend(client, has_password)
    assert resp.status_code == 302 and resp.headers['Location'] == '/admin/users'
    assert 'has already set a password' in client.get('/admin/users').get_data(as_text=True)
    resp = _resend(client, other_admin)
    assert resp.status_code == 302 and resp.headers['Location'] == '/admin/users'
    assert "can&#39;t be sent for Super Admin accounts" in client.get('/admin/users').get_data(as_text=True)
    resp = _resend(client, f"{_unique('nobody')}@test.edu")
    assert resp.status_code == 302 and resp.headers['Location'] == '/admin/users'

    assert mail == []
    entries = [d.to_dict() for d in db.collection('audit_log').where('actor_email', '==', admin).stream()]
    assert not [e for e in entries if e['action'] == 'SET_PASSWORD_LINK_RESENT']
