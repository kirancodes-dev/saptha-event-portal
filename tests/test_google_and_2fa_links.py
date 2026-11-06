"""
tests/test_google_and_2fa_links.py — UPG-55: the login page links Google
sign-in only when Google OAuth is configured, and the profile page offers the
2FA set-up only when 2FA is available; each link opens.
"""
from tests.test_integration_flow import _login, _unique, _user


def test_the_login_page_links_google_only_when_configured(real_app, monkeypatch):
    flask_app, _ = real_app
    monkeypatch.setitem(flask_app.config, 'OAUTH_GOOGLE_CLIENT_ID', '')
    monkeypatch.setitem(flask_app.config, 'GOOGLE_CLIENT_ID', '')
    client = flask_app.test_client()
    assert 'href="/auth/google"' not in client.get('/login').get_data(as_text=True)

    monkeypatch.setitem(flask_app.config, 'OAUTH_GOOGLE_CLIENT_ID', 'client-id.apps.googleusercontent.com')
    assert 'href="/auth/google"' in client.get('/login').get_data(as_text=True)
    resp = client.get('/auth/google')
    assert resp.status_code == 302 and resp.headers['Location'].startswith('https://accounts.google.com/')


def test_the_profile_offers_2fa_only_when_available(real_app, monkeypatch):
    flask_app, db = real_app
    email = f"{_unique('twofa')}@test.edu"
    _user(db, email, 'Student')
    client = _login(flask_app, email, 'Student')
    monkeypatch.setitem(flask_app.config, 'TWO_FA_AVAILABLE', True)
    assert 'href="/auth/2fa/setup"' in client.get('/profile/').get_data(as_text=True)
    assert client.get('/auth/2fa/setup').status_code == 200

    monkeypatch.setitem(flask_app.config, 'TWO_FA_AVAILABLE', False)
    page = client.get('/profile/').get_data(as_text=True)
    assert 'href="/auth/2fa/setup"' not in page and 'Two-Factor Authentication' not in page
