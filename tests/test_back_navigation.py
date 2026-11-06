"""
tests/test_back_navigation.py — UPG-103: every page but a role's home has a
Back link (the installed app has no browser toolbar), pointing back on this
site only; the full-screen and standalone pages that had none get one.
"""
import re

import pytest

from tests.test_integration_flow import _login, _unique, _user

STANDALONE = ('participant/certificate.html', 'tickets/digital_wallet.html', 'public/verify_success.html',
              'live/leaderboard.html', 'login.html', 'register.html')


@pytest.fixture
def student(real_app):
    flask_app, db = real_app
    email = f"{_unique('back')}@test.edu"
    _user(db, email, 'Student')
    return _login(flask_app, email, 'Student')


def _back_href(html):
    m = re.search(r'<a href="([^"]*)" class="app-bar__back"', html)
    return m.group(1) if m else None


# ── UPG-103 ─────────────────────────────────────────────────────────────────

def test_inner_pages_have_back_to_the_referring_page_on_this_site(student):
    html = student.get('/participant/my_events', headers={'Referer': 'http://localhost/events'}).get_data(as_text=True)
    assert _back_href(html) == '/events' and 'data-h-click="se:back-in-site"' in html
    # No referrer: the role's home. Another site's referrer is never used.
    assert _back_href(student.get('/participant/my_events').get_data(as_text=True)) == '/participant/dashboard'
    foreign = student.get('/participant/my_events', headers={'Referer': 'https://evil.example/phish'})
    assert _back_href(foreign.get_data(as_text=True)) == '/participant/dashboard'


def test_the_role_home_has_no_back(student):
    assert _back_href(student.get('/participant/dashboard').get_data(as_text=True)) is None


def test_the_pages_without_the_app_bar_get_a_floating_back(real_app):
    flask_app, _ = real_app
    for name in STANDALONE:
        with open(f'templates/{name}', encoding='utf-8') as fh:
            assert '{% include "includes/back_link.html" %}' in fh.read(), name
    visitor = flask_app.test_client()
    for path in ('/login', '/register'):
        html = visitor.get(path, headers={'Referer': 'http://localhost/events'}).get_data(as_text=True)
        assert re.search(r'<a href="/events" class="page-back-float no-print" data-h-click="se:back-in-site"', html), path


def test_the_in_site_back_handler_uses_history_only_for_this_site():
    with open('static/js/handlers.js', encoding='utf-8') as fh:
        js = fh.read()
    handler = js[js.index("'se:back-in-site'"):js.index("'se:call'")]
    assert 'new URL(ref).origin === window.location.origin' in handler and 'history.back()' in handler

