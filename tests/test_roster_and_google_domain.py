"""
tests/test_roster_and_google_domain.py — UPG-10 on the real database layer: a
Super Admin's roster CSV creates students with their USN, department and year;
uploading it again updates them in place; Google sign-in from outside the
university's domain is refused (Google's endpoints mocked).
"""
import io

import pytest

import auth_oauth
from tests.test_integration_flow import PASSWORD, _unique, _user


@pytest.fixture
def admin(real_app):
    flask_app, db = real_app
    email = f"{_unique('rosteradmin')}@test.edu"
    _user(db, email, 'SuperAdmin')
    client = flask_app.test_client()
    client.post('/login', data={'role': 'SuperAdmin', 'email': email, 'password': PASSWORD,
                                'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    return flask_app, db, client


def _upload(client, rows):
    body = 'email,name,usn,department,year,section\n' + '\n'.join(','.join(r) for r in rows) + '\n'
    return client.post('/admin/users/import_csv', data={'file': (io.BytesIO(body.encode()), 'roster.csv')},
                       content_type='multipart/form-data')


def test_a_roster_creates_students_and_a_second_upload_updates_them_in_place(admin):
    _, db, client = admin
    emails = [f"{_unique('roster')}@test.edu" for _ in range(3)]
    rows = [(e, f'Student {i}', f'1SN22CS00{i}', 'CSE', '2', 'A') for i, e in enumerate(emails)]
    assert _upload(client, rows).status_code == 302
    for i, e in enumerate(emails):
        user = db.collection('users').document(e).get().to_dict()
        assert user['usn'] == f'1SN22CS00{i}' and user['department'] == 'CSE' and user['year'] == '2'
        assert user['role'] == 'Student'

    rows[0] = (emails[0], 'Student Zero', '1SN22CS100', 'ECE', '3', 'B')
    _upload(client, rows)
    first = db.collection('users').document(emails[0]).get().to_dict()
    assert first['usn'] == '1SN22CS100' and first['department'] == 'ECE' and first['name'] == 'Student Zero'
    found = [d.id for d in db.collection('users').stream() if d.id in emails]
    assert sorted(found) == sorted(emails)                                 # no duplicates


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


@pytest.mark.parametrize('email,allowed', [('outsider@gmail.com', False), ('insider@snpsu.edu.in', True)])
def test_google_sign_in_is_limited_to_the_university_domain(real_app, monkeypatch, email, allowed):
    flask_app, db = real_app
    email = email.replace('@', f"-{_unique('g')}@")
    monkeypatch.setitem(flask_app.config, 'GOOGLE_ALLOWED_DOMAIN', 'snpsu.edu.in')
    monkeypatch.setitem(flask_app.config, 'UNIVERSITY_EMAIL_DOMAIN', '')
    monkeypatch.setitem(flask_app.config, 'OAUTH_GOOGLE_CLIENT_ID', 'client-id')
    monkeypatch.setitem(flask_app.config, 'OAUTH_GOOGLE_CLIENT_SECRET', 'client-secret')
    monkeypatch.setattr(auth_oauth.requests, 'post', lambda *a, **k: _Resp({'access_token': 'tok'}))
    monkeypatch.setattr(auth_oauth.requests, 'get', lambda *a, **k: _Resp({'email': email, 'name': 'G User'}))
    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess['oauth_state'] = 'state-1'
    resp = client.get('/auth/google/callback?state=state-1&code=abc')
    with client.session_transaction() as sess:
        signed_in = sess.get('user_id')
    if allowed:
        assert signed_in == email.lower() and db.collection('users').document(email.lower()).get().exists
    else:
        assert resp.headers['Location'] == '/login' and signed_in is None
        assert not db.collection('users').document(email.lower()).get().exists
