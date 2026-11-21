"""
tests/test_first_pages_review.py — UPG-297, the usability findings from the
first-pages review, (a) to (g):

(a) the Super Admin's "Recent activity" says what happened in words, at the
    time in India, without signing in and out, and shows each entry's details;
(b) at 1280 px the page's name in the top bar is whole, a long user name
    shortens instead;
(c) the student's dashboard greets them by name, and without tickets has no
    second "no registrations" card;
(d) the campus photo on the student's dashboard is a short banner;
(e) the SPOC's event header shows no stored status beside "Visitors see"; it
    says "Draft" (and the like) only when that adds something;
(f) the coordinator's figures say that events that are over are left out;
(g) the home page shows the next 6 events and "See all events".
"""
import datetime
import re

import pytest

import services_activity as activity
from tests.test_integration_flow import _create_event, _login, _unique, _user
from tests.test_phone_journey import _login_in_browser, _routes

FUTURE = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()


# ── (a) Recent activity ─────────────────────────────────────────────────────

@pytest.mark.parametrize('code, words', [
    ('LOGIN_SUCCESS', 'Signed in'), ('EVENT_CREATED', 'Event created'), ('CERT_ISSUED_BY_HAND', 'Certificate issued by hand'),
    ('ROOMS_ALLOCATED', 'Rooms allocated'), ('AI_MATCH_APPLIED', 'AI match applied'), ('NAAC_FILE_ADDED', 'NAAC file added'),
    ('RESET_REQ_THROTTLED', 'Reset request throttled'), ('', 'Action'), ('Something said in words', 'Something said in words'),
])
def test_an_action_code_reads_as_words(code, words):
    assert activity.action_text(code) == words


def test_a_stored_time_is_the_time_in_india():
    utc = datetime.datetime(2026, 11, 15, 23, 35, tzinfo=datetime.timezone.utc)
    assert activity.when_text(utc) == '16 Nov 2026, 05:05'
    assert activity.when_text(utc.replace(tzinfo=None)) == '16 Nov 2026, 05:05'      # no zone is UTC
    assert activity.when_text('2026-11-15T23:35:00+00:00') == '16 Nov 2026, 05:05'
    assert activity.when_text('not a time') == 'not a time'
    assert activity.when_text(None) == ''


def test_the_dashboard_feed_leaves_out_signing_in_and_out_and_keeps_15():
    entries = [{'action': 'LOGIN_SUCCESS'}, {'action': 'LOGOUT'}, {'action': 'LOGIN_FAILED'}] + \
              [{'action': 'EVENT_CREATED'}] * 20
    feed = activity.dashboard_feed(entries)
    assert len(feed) == 15 and feed[0] == {'action': 'LOGIN_FAILED'}
    assert not any(e['action'] in ('LOGIN_SUCCESS', 'LOGOUT') for e in feed)


def test_the_admin_dashboard_shows_activity_in_words_at_the_time_in_india(real_app):
    flask_app, db = real_app
    admin = f"{_unique('aadmin')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    client = _login(flask_app, admin, 'SuperAdmin')
    tag = _unique('Robotics')
    at = datetime.datetime(2099, 1, 1, 6, 0, tzinfo=datetime.timezone.utc)       # newest of all
    for i, (action, details) in enumerate((('EVENT_PUBLISHED', f'{tag} is live'),
                                           ('LOGIN_SUCCESS', f'{tag} signed in'))):
        db.collection('audit_log').add({'action': action, 'details': details, 'user': admin, 'role': 'SuperAdmin',
                                        'ip': '127.0.0.1', 'timestamp': at + datetime.timedelta(minutes=i)})
    html = client.get('/admin/dashboard').get_data(as_text=True)
    feed = html[html.index('Recent Activity'):]
    feed = feed[:feed.index('<!-- /content-wrapper -->')]
    row = re.search(r'data-activity="EVENT_PUBLISHED">(.*?)class="log-time">[^<]*</div>', feed, re.S)
    assert row, feed[:2000]
    row = row.group(0)
    assert 'Event published' in row and f'{tag} is live' in row
    assert '1 Jan 2099, 11:30' in row                       # 06:00 UTC is 11:30 in India
    assert 'EVENT_PUBLISHED</div>' not in feed and '2099-01-01T' not in feed
    assert f'{tag} signed in' not in feed and 'data-activity="LOGIN_SUCCESS"' not in feed
    # the audit log page still has the sign-in
    assert f'{tag} signed in' in client.get('/admin/audit_log').get_data(as_text=True)


# ── (c) the student's dashboard ─────────────────────────────────────────────

def test_the_student_dashboard_greets_by_name_and_has_no_second_empty_card(real_app):
    flask_app, db = real_app
    email = f"{_unique('greet')}@test.edu"
    _user(db, email, 'Student', name='Asha Rao')
    html = _login(flask_app, email, 'Student').get('/participant/dashboard').get_data(as_text=True)
    assert re.search(r'<h1 class="page-head__title" id="page-title">Hello, Asha</h1>', html)
    assert "You haven't registered for any upcoming events yet." in html       # said once, above
    assert 'data-widget="my-registrations"' not in html and 'No upcoming registrations' not in html


def test_with_a_ticket_the_my_registrations_card_is_there(real_app):
    flask_app, db = real_app
    spoc, student = f"{_unique('rspoc')}@test.edu", f"{_unique('rstud')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, student, 'Student', name='Ravi Kumar')
    title = _unique('Card Event')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, title, FUTURE, team=False)
    client = _login(flask_app, student, 'Student')
    assert client.post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Ravi Kumar', 'email': student, 'phone': '9876543210',
        'usn': '1SN21CS001'}).status_code == 302
    html = client.get('/participant/dashboard').get_data(as_text=True)
    assert title in html, 'registration did not go through'
    card = html[html.index('data-widget="my-registrations"'):]
    assert title in card[:1500] and '1 active' in card[:1500]


# ── (e) the SPOC's event header ─────────────────────────────────────────────

def _head(page, event_id):
    start = page.index(f'id="detail-panel-{event_id}"')
    end = page.index('data-visitor-state', start)
    return page[start:end + 400]


def test_the_spoc_event_header_shows_no_stored_status_beside_visitors_see(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('hspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    over = _create_event(client, db, _unique('Over Event'), yesterday, team=False)
    db.collection('events').document(over).update({'status': 'registration_open', 'end_date': yesterday})
    draft = _create_event(client, db, _unique('Draft Event'), FUTURE, team=False)
    db.collection('events').document(draft).update({'status': 'draft'})
    page = client.get('/spoc/dashboard').get_data(as_text=True)

    head = _head(page, over)
    assert 'Visitors see: <strong data-live-label>Event over</strong>' in head
    assert 'Registration Open' not in head and 'data-organiser-status' not in head

    head = _head(page, draft)
    assert re.search(r'data-organiser-status="[^"]*"[^>]*>Draft<', head), head


# ── (f) the coordinator's figures ───────────────────────────────────────────

def test_the_coordinator_figures_say_finished_events_are_left_out(real_app):
    flask_app, db = real_app
    coord, admin = f"{_unique('fcoord')}@test.edu", f"{_unique('fadmin')}@test.edu"
    _user(db, coord, 'EventCoordinator')
    _user(db, admin, 'SuperAdmin')
    html = _login(flask_app, coord, 'EventCoordinator').get('/coordinator/dashboard').get_data(as_text=True)
    note = html.index('data-stats-note')
    assert html.index('Staff appointed') < note < html.index('Event control centre')
    assert "Events that are over aren't shown or counted here." in html
    # the Super Admin sees every event, so no note
    html = _login(flask_app, admin, 'SuperAdmin').get('/coordinator/dashboard').get_data(as_text=True)
    assert 'data-stats-note' not in html


# ── (b), (d), (g) in a browser ──────────────────────────────────────────────

TITLE = """() => { const n = document.querySelector('.app-bar__name'), u = document.querySelector('.app-bar__user > span:not(.app-bar__avatar)');
  const inner = document.querySelector('.app-bar__inner').getBoundingClientRect();
  const last = [...document.querySelectorAll('.app-bar__nav > *')].pop().getBoundingClientRect();
  return {title: n.textContent.trim(), cut: n.scrollWidth > n.clientWidth, shown: n.clientWidth > 0,
          userCut: u.scrollWidth > u.clientWidth, overflow: last.right > inner.right + 1,
          page: document.documentElement.scrollWidth}; }"""
BANNER = "() => document.querySelector('.profile-hero__banner img').getBoundingClientRect().height"
HOME = """() => { const shown = [...document.querySelectorAll('.ev-col')].filter(c => c.offsetHeight > 0);
  const all = document.querySelector('[data-see-all-events]');
  return {shown: shown.length, total: document.querySelectorAll('.ev-col').length,
          seeAll: all && all.offsetHeight > 0 && all.getAttribute('href')}; }"""


@pytest.fixture
def long_names(real_app):
    flask_app, db = real_app
    who = {'ClubSPOC': f"{_unique('bspoc')}@test.edu", 'Student': f"{_unique('bstud')}@test.edu"}
    for role, email in who.items():
        _user(db, email, role, name='Dr. Kavitha Ramachandran Srinivasan')
    return flask_app, db, who


def test_the_page_name_is_whole_at_1280_and_the_banner_is_short(long_names):
    from tests.headless import chromium, live_server
    flask_app, _db, who = long_names
    p, browser = chromium()
    try:
        with live_server(flask_app) as server:
            for role, title in (('ClubSPOC', 'SPOC console'), ('Student', 'Student portal')):
                ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
                _routes(ctx, server.url)
                page = ctx.new_page()
                _login_in_browser(page, server.url, who[role], role)
                got = page.evaluate(TITLE)
                assert got['title'] == title and got['shown'] and not got['cut'], (role, got)        # (b)
                assert got['userCut'] and not got['overflow'] and got['page'] <= 1280, (role, got)
                if role == 'Student':                                                              # (d)
                    assert page.evaluate(BANNER) <= 141
                ctx.close()
            ctx = browser.new_context(viewport={'width': 390, 'height': 844})
            _routes(ctx, server.url)
            page = ctx.new_page()
            _login_in_browser(page, server.url, who['Student'], 'Student')
            assert page.evaluate(BANNER) <= 97
            ctx.close()
    finally:
        browser.close()
        p.stop()


def test_the_home_page_shows_the_next_6_events_and_see_all(real_app):
    from tests.headless import chromium, live_server
    flask_app, db = real_app
    spoc = f"{_unique('gspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    tag = _unique('Zephyr')
    for i in range(8):
        event_id = _create_event(client, db, f'{tag} {i}', FUTURE, team=False)
        db.collection('events').document(event_id).update({'status': 'active'})
    p, browser = chromium()
    try:
        with live_server(flask_app) as server:
            ctx = browser.new_context(viewport={'width': 390, 'height': 844})
            _routes(ctx, server.url)
            page = ctx.new_page()
            page.goto(server.url + '/')
            got = page.evaluate(HOME)
            assert got['total'] >= 8 and got['shown'] == 6 and got['seeAll'] == '/events', got
            page.fill('#evSearch', tag.lower())               # search still looks through every event
            page.dispatch_event('#evSearch', 'input')
            got = page.evaluate(HOME)
            assert got['shown'] == 6 and got['seeAll'] == '/events', got
            assert server.url and page.goto(server.url + '/events').status == 200
            ctx.close()
    finally:
        browser.close()
        p.stop()
