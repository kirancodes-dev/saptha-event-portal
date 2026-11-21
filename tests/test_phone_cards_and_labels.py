"""
tests/test_phone_cards_and_labels.py — the second usability round (UPG-369 to
UPG-372):

- UPG-369: on a 390 px phone the admin's events and users pages are no wider
  than the screen: each row is a card.
- UPG-370: on a phone the admin dashboard's six number cards take at most
  three rows.
- UPG-371: an event without an image has a thin band on the coordinator's
  dashboard, not a 150 px empty banner.
- UPG-372: every field on the SPOC's tournament page has a label.
"""
import re
from html.parser import HTMLParser

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user
from tests.test_phone_journey import _routes
from tests.test_sports_tournament import _t, cup  # noqa: F401
from tests.test_tap_targets import PHONE

WIDTHS = """() => ({page: document.documentElement.scrollWidth,
  tables: [...document.querySelectorAll('[data-phone-cards]')].map(t => Math.round(t.getBoundingClientRect().right)),
  rows: [...document.querySelectorAll('[data-phone-cards] tbody tr')].length})"""

ROWS = """() => [...new Set([...document.querySelectorAll('.stat-grid > .stat-card')]
  .map(c => Math.round(c.getBoundingClientRect().top)))].length"""


def test_the_admin_lists_and_numbers_fit_a_phone(real_app):
    from tests.headless import chromium, live_server
    flask_app, db = real_app
    admin, spoc = f"{_unique('padmin')}@test.edu", f"{_unique('pspoc')}@test.edu"
    _user(db, admin, 'SuperAdmin', name='Asha Rao')
    _user(db, spoc, 'ClubSPOC', name='A SPOC with a rather long name')
    client = _login(flask_app, spoc, 'ClubSPOC')
    _create_event(client, db, _unique('An event with a long name to squeeze the column'), '2031-05-01', team=False)
    p, browser = chromium()
    try:
        with live_server(flask_app) as server:
            ctx = browser.new_context(viewport=PHONE)
            _routes(ctx, server.url)
            page = ctx.new_page()
            page.goto(server.url + '/login')                 # the Super Admin also types the master key
            page.select_option('#roleSelect', 'SuperAdmin')
            page.fill('#emailInput', admin)
            page.fill('#passwordInput', PASSWORD)
            page.fill('#secretKeyInput', flask_app.config.get('MASTER_SECRET_KEY', ''))
            page.click('button[type=submit]')
            page.wait_for_load_state('load')
            assert '/login' not in page.url, page.url
            for path in ('/admin/events', '/admin/users'):
                page.goto(server.url + path)
                page.wait_for_timeout(200)
                w = page.evaluate(WIDTHS)
                assert w['rows'] and w['tables'], (path, w)
                assert w['page'] <= PHONE['width'] and max(w['tables']) <= PHONE['width'], (path, w)
            page.goto(server.url + '/admin/dashboard')
            page.wait_for_timeout(200)
            assert page.evaluate(ROWS) <= 3
            ctx.close()
    finally:
        browser.close()
        p.stop()


def test_an_event_without_an_image_has_a_thin_band_on_the_coordinators_page(real_app):
    flask_app, db = real_app
    spoc, coord = f"{_unique('bspoc')}@test.edu", f"{_unique('bcoord')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    client = _login(flask_app, spoc, 'ClubSPOC')
    plain = _create_event(client, db, _unique('Plain Event'), '2031-05-02', team=False)
    pictured = _create_event(client, db, _unique('Pictured Event'), '2031-05-03', team=False)
    db.collection('events').document(pictured).update({'banner_url': '/static/img/email-logo.png'})
    for eid in (plain, pictured):
        assert client.post(f'/spoc/assign_coordinator/{eid}', data={
            'coordinator_email': coord, 'coordinator_name': 'Cora'}).status_code == 302
    page = _login(flask_app, coord, 'EventCoordinator').get('/coordinator/dashboard').get_data(as_text=True)

    def card(eid):
        start = page.index(f'data-event-card="{eid}"')
        return page[start:start + 2500]
    assert 'data-banner="none"' in card(plain) and 'class="ev-banner"' not in card(plain)
    assert re.search(r'data-organiser-status="\w+"', card(plain))
    assert 'class="ev-banner"' in card(pictured) and 'data-banner="none"' not in card(pictured)


class _Fields(HTMLParser):
    """Every visible field, and whether a label names it."""
    def __init__(self):
        super().__init__()
        self.labels_for, self.fields, self.in_label = set(), [], 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'label':
            self.in_label += 1
            if a.get('for'):
                self.labels_for.add(a['for'])
        elif tag in ('input', 'select', 'textarea') and a.get('type') not in ('hidden', 'submit', 'button'):
            self.fields.append((a.get('name'), a.get('id'), bool(a.get('aria-label')), self.in_label > 0))

    def handle_endtag(self, tag):
        if tag == 'label':
            self.in_label -= 1


def test_every_field_on_the_tournament_page_has_a_label(cup):  # noqa: F811
    d = cup
    event_id, _ = d['event'](['Ants', 'Bees', 'Cats', 'Dogs'])
    d['owner'].post(f'/tournament/{event_id}/generate', data={'format': 'knockout', 'third_place': 'yes'})
    assert _t(d, event_id)['matches']
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    parser = _Fields()
    parser.feed(page)
    names = {f[0] for f in parser.fields}
    assert {'home_score', 'away_score', 'date', 'time', 'venue', 'home', 'away'} <= names, names
    unlabelled = [f for f in parser.fields if not (f[2] or f[3] or (f[1] and f[1] in parser.labels_for))]
    assert not unlabelled, unlabelled
    assert re.search(r'for="hs-[^"]+"[^>]*>(Ants|Bees|Cats|Dogs) score</label>', page), 'the score box names its team'
