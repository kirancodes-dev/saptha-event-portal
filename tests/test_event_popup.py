"""
tests/test_event_popup.py — UPG-92: the home page's event popup and the event
page show one and the same content (public/_event_content.html), the popup
without the page-only parts (breadcrumb, live countdown, copy button) and with
no invented "highlights"; and "Back" on the registration page returns to the
page the visitor came from on this site, never another site.
"""
import datetime
import os

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def event(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('popspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    date = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    title = _unique('Popup Event')
    eid = _create_event(client, db, title, date, team=False)
    db.collection('events').document(eid).update({'status': 'registration_open'})
    yield flask_app, db, eid, title
    db.collection('events').document(eid).delete()
    db.collection('users').document(spoc).delete()


def _section_titles(html):
    return [t for t in ('About this event', 'Rules', 'Registrations', 'Key dates', 'Share this event')
            if t in html]


def test_popup_shows_the_event_page_content_without_page_only_parts(event):
    flask_app, db, eid, title = event
    client = flask_app.test_client()
    popup = client.get(f'/event/{eid}?fragment=1').get_data(as_text=True)
    page = client.get(f'/event/{eid}').get_data(as_text=True)
    assert popup.lstrip().startswith('<div class="ev-fragment"') and '<html' not in popup
    assert f'data-event-title="{title}"' in popup
    # Same sections in both: one source of content
    assert _section_titles(popup) == _section_titles(page) and len(_section_titles(popup)) == 5
    # The page keeps its own parts; the popup leaves them out
    assert 'aria-label="Breadcrumb"' in page and 'id="cd-band"' in page and 'id="s-cp"' in page
    assert 'aria-label="Breadcrumb"' not in popup and 'id="cd-band"' not in popup and 'id="s-cp"' not in popup
    assert 'In 5 days' in popup
    # Register returns to this popup afterwards
    assert f'href="/forms/register/{eid}?next=/%3Fevent%3D{eid}"' in popup


def test_popup_shows_closed_registration_instead_of_a_register_link(event):
    flask_app, db, eid, _ = event
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    db.collection('events').document(eid).update({'reg_deadline': yesterday, 'deadline': yesterday})
    popup = flask_app.test_client().get(f'/event/{eid}?fragment=1').get_data(as_text=True)
    assert 'Registration closed' in popup and f'/forms/register/{eid}' not in popup


def test_registrations_shown_are_counted_not_cached(event):
    flask_app, db, eid, _ = event
    db.collection('events').document(eid).update({'registered_count': 999})
    for i, status in enumerate(('confirmed', 'cancelled', 'Confirmed')):
        db.collection('registrations').document(f'{eid}-pop{i}').set(
            {'event_id': eid, 'status': status, 'user_id': f'p{i}@test.edu'})
    try:
        popup = flask_app.test_client().get(f'/event/{eid}?fragment=1').get_data(as_text=True)
        assert '999' not in popup and '<span class="cap-count">2</span>' in popup and '48 spots remaining' in popup
    finally:
        for i in range(3):
            db.collection('registrations').document(f'{eid}-pop{i}').delete()


def test_home_page_opens_the_popup_and_invents_nothing():
    js = open(os.path.join(ROOT, 'static/js/pages/index.js'), encoding='utf-8').read()
    home = open(os.path.join(ROOT, 'templates/index.html'), encoding='utf-8').read()
    assert '?fragment=1' in js and 'data-open-event' in js
    assert 'Event Highlights' not in js and 'showEventModalFromCol' not in js
    assert 'data-open-event="{{ ev.id }}"' in home and 'modal-dialog-scrollable' in home
    assert 'event-details.css' in home


# ── "Back" on the registration page ────────────────────────────────────────

def _back_href(html):
    start = html.index('class="reg-wrap"')
    tag = html[html.index('<a href="', start) + 9:]
    return tag[:tag.index('"')]


@pytest.mark.parametrize('came_from', ['/?event=X', '/events?category=Technical', '/student/dashboard'])
def test_back_returns_to_the_page_given_in_next(event, came_from):
    flask_app, db, eid, _ = event
    came_from = came_from.replace('X', eid)
    from urllib.parse import quote
    html = flask_app.test_client().get(f'/forms/register/{eid}?next={quote(came_from, safe="")}').get_data(as_text=True)
    assert _back_href(html) == came_from.replace('&', '&amp;')


def test_back_follows_a_trusted_referrer_and_is_remembered(event):
    flask_app, db, eid, _ = event
    client = flask_app.test_client()
    html = client.get(f'/forms/register/{eid}', headers={'Referer': 'http://localhost/events'}).get_data(as_text=True)
    assert _back_href(html) == '/events'
    # Reloaded (no next, the page itself as referrer): still goes back there
    html = client.get(f'/forms/register/{eid}',
                      headers={'Referer': f'http://localhost/forms/register/{eid}'}).get_data(as_text=True)
    assert _back_href(html) == '/events'


@pytest.mark.parametrize('bad', ['https://evil.example/phish', '//evil.example/x', 'javascript:alert(1)',
                                 '/\\evil.example', 'http://evil.example/events'])
def test_back_never_leaves_the_site(event, bad):
    flask_app, db, eid, _ = event
    from urllib.parse import quote
    html = flask_app.test_client().get(f'/forms/register/{eid}?next={quote(bad, safe="")}',
                                       headers={'Referer': 'https://attacker.example/'}).get_data(as_text=True)
    assert _back_href(html) == f'/event/{eid}'
