"""
tests/test_mobile_nav_links.py — UPG-334: the phone's bottom bar for students
and visitors. Its old "Results" tab linked to /live/streams, a demo page that
answers 404 in production, so the tab is now "Certificates" (My certificates);
no link in the bar answers 404 with the demo pages off.
"""
import re

from tests.test_integration_flow import _login, _unique, _user


def _bar(html):
    start = html.index('<nav class="mobile-nav-bar"')
    return html[start:html.index('</nav>', start)]


def _links(html):
    return re.findall(r'<a href="([^"]+)" class="mobile-nav-item"', _bar(html))


def test_no_link_in_the_phone_bar_answers_404(real_app):
    flask_app, db = real_app
    assert not flask_app.config.get('DEMO_PAGES_ENABLED')
    email = f"{_unique('navstu')}@test.edu"
    _user(db, email, 'Student')
    visitor, student = flask_app.test_client(), _login(flask_app, email, 'Student')
    for client in (visitor, student):
        links = _links(client.get('/', follow_redirects=True).get_data(as_text=True))
        assert '/certificates/mine' in links and '/live/streams' not in links
        for href in links:
            assert client.get(href).status_code != 404, href


def test_the_certificates_tab_opens_my_certificates_and_is_marked_current(real_app):
    flask_app, db = real_app
    email = f"{_unique('navstu')}@test.edu"
    _user(db, email, 'Student')
    student = _login(flask_app, email, 'Student')
    page = student.get('/certificates/mine')
    assert page.status_code == 200
    bar = _bar(page.get_data(as_text=True))
    tab = re.search(r'<a href="/certificates/mine"[^>]*>\s*<i class="fas fa-award"[^>]*></i>\s*<span>Certificates</span>', bar)
    assert tab and 'aria-current="page"' in tab.group(0)
    assert 'Results' not in bar
    assert student.get('/certificates/mine', follow_redirects=False).status_code == 200
    assert flask_app.test_client().get('/certificates/mine').status_code in (301, 302)   # visitors sign in first
