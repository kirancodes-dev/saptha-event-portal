"""
tests/test_spoc_event_panel.py — UPG-253 on the real database layer.

The SPOC's event panel on /spoc/dashboard puts first what's needed now: a top
row with the numbers that matter and the Registrations, Share and Scanner
buttons, then a "What to do now" card for the event's stage. Every tool the
old panel had is still there, in labelled groups; the hackathon, round,
placement and sports tools show only on those events. Each "Advance to …"
button says what the stage means. The panel fits a 375px phone.
"""
import datetime
import re

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user

# Every link and form target the panel had before UPG-253 (templates/spoc/dashboard.html
# at e7afca9), but for removing a coordinator, which shows only with one assigned
OLD_PANEL = [
    '/spoc/event/{id}/review', '/spoc/event/{id}/setup', '/spoc/event/{id}/transition', '/spoc/scan/{id}',
    '/checkin/toggle/{id}', '/checkin/venue_qr/{id}', '/spoc/room_allocation/{id}', '/spoc/hackathon/{id}',
    '/spoc/round_panel/{id}', '/spoc/schedule/optimize/{id}', '/spoc/ticket/nfc-verify/{id}', '/spoc/announce/{id}',
    '/forms/builder/{id}', '/spoc/agenda/{id}', '/spoc/toggle_openhall/{id}', '/placement/{id}', '/tournament/{id}',
    '/spoc/results/{id}', '/spoc/event_report/{id}', '/feedback/analytics/{id}', '/coordinator/registrations/{id}',
    '/spoc/export_excel/{id}', '/spoc/export_csv/{id}', '/ticket/badges/{id}.pdf', '/interact/{id}/host',
    '/spoc/event/{id}/share', '/spoc/judging/audit/{id}', '/spoc/bulk_certs/{id}', '/spoc/edit_event/{id}',
    '/spoc/clone_event/{id}', '/spoc/toggle_status/{id}', '/spoc/delete_event/{id}',
]


@pytest.fixture
def panel(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('panelspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    future = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()

    def event(team=True, **fields):
        event_id = _create_event(client, db, _unique('Panel Event'), future, team=team)
        if fields:
            db.collection('events').document(event_id).update(fields)
        return event_id

    def page():
        return client.get('/spoc/dashboard').get_data(as_text=True)
    return {'app': flask_app, 'db': db, 'client': client, 'event': event, 'page': page}


def _panel(page, event_id):
    start = page.index(f'id="detail-panel-{event_id}"')
    end = page.index('<!-- /event-detail-panel -->', start)
    return page[start:end]


def _section(html, marker):
    start = html.index(marker)
    return html[start:html.index('</section>', start)]


# ── Criterion 1: the top row, and "What to do now" by stage ────────────────

def test_the_top_row_links_to_registrations_and_the_card_follows_the_stage(panel):
    p = panel
    draft = p['event'](status='draft')
    live = p['event']()                                   # active, registration open
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    over = p['event'](status='completed', date=yesterday, end_date=yesterday)
    page = p['page']()

    for event_id in (draft, live, over):
        top = _section(_panel(page, event_id), 'data-top-row')
        assert f'href="/coordinator/registrations/{event_id}"' in top
        assert f'href="/spoc/event/{event_id}/share"' in top and f'href="/spoc/scan/{event_id}"' in top
        assert 'registered' in top and 'waiting' in top and 'checked in' in top

    card = _section(_panel(page, draft), 'data-next-steps')
    assert 'data-stage="draft"' in card and f'/spoc/event/{draft}/review' in card and 'Review and publish' in card

    card = _section(_panel(page, live), 'data-next-steps')
    assert 'data-stage="open"' in card
    for href in (f'/coordinator/registrations/{live}"', f'/coordinator/registrations/{live}#waitlist',
                 f'/spoc/event/{live}/share'):
        assert href in card, href

    card = _section(_panel(page, over), 'data-next-steps')
    assert 'data-stage="after"' in card
    for href in (f'/spoc/results/{over}', f'/certificates/events/{over}', f'/spoc/event_report/{over}',
                 f'/feedback/analytics/{over}'):
        assert href in card, href


def test_a_closed_team_event_points_to_the_add_members_window_and_each_stage_button_says_what_it_means(panel):
    p = panel
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    closed = p['event'](deadline=yesterday, status='registration_open')
    staged = p['event'](status='published')
    page = p['page']()
    card = _section(_panel(page, closed), 'data-next-steps')
    assert 'data-stage="closed"' in card
    assert f'/coordinator/registrations/{closed}#add-members-window' in card and '#documents' in card

    head = _panel(page, staged)
    buttons = re.findall(r'<form[^>]*data-stage-button>(.*?)</form>', head, re.S)
    assert buttons and all('data-stage-meaning' in b for b in buttons)
    assert 'People can register.' in head                 # under "Advance to Registration Open"


def test_the_panel_counts_waiting_and_unconfirmed_members(panel):
    p = panel
    db = p['db']
    event_id = p['event']()
    db.collection('waitlists').document(_unique('WL')).set({'event_id': event_id, 'status': 'waiting',
                                                            'joined_at': '2026-11-01T10:00:00'})
    db.collection('registrations').document(_unique('REG')).set({
        'event_id': event_id, 'lead_email': 'lead@test.edu', 'status': 'Confirmed', 'team_code': 'ABC123',
        'attendance': 'Present',
        'members': [{'role': 'Lead', 'email': 'lead@test.edu'},
                    {'role': 'Member', 'email': 'm1@test.edu', 'confirmed_at': '2026-11-01T10:00:00'},
                    {'role': 'Member', 'email': 'm2@test.edu'}]})
    top = _section(_panel(p['page'](), event_id), 'data-top-row')
    nums = dict((label, val) for val, label in re.findall(
        r'panel-num-val[^>]*>(\d+)(?:<small>[^<]*</small>)?</span><span class="panel-num-label">([^<]+)<', top))
    assert nums == {'registered': '1', 'waiting': '1', 'members not confirmed': '1', 'checked in': '1'}


# ── Criterion 2: kind-specific tools only on those events ──────────────────

def test_a_seminar_has_no_hackathon_round_or_tournament_tools_and_a_hackathon_has(panel):
    p = panel
    seminar = p['event'](team=False, event_type='seminar')
    hackathon = p['event'](event_type='hackathon')
    sports = p['event'](event_type='sports_tournament', category='Sports')
    page = p['page']()

    html = _panel(page, seminar)
    for gone in (f'/spoc/hackathon/{seminar}', f'/spoc/round_panel/{seminar}', f'/tournament/{seminar}',
                 f'/placement/{seminar}'):
        assert gone not in html, gone
    assert 'For this kind of event' not in html

    html = _panel(page, hackathon)
    assert f'/spoc/hackathon/{hackathon}' in html and f'/spoc/round_panel/{hackathon}' in html
    assert f'/tournament/{hackathon}' not in html

    html = _panel(page, sports)
    assert f'/tournament/{sports}' in html and f'/spoc/hackathon/{sports}' not in html


# ── Criterion 3: nothing the old panel linked to is gone ───────────────────

def test_every_link_the_old_panel_had_is_still_there(panel):
    p = panel
    # An event of no type (as before types) with every switch that showed a tool on
    event_id = p['event'](is_placement=True, tournament=True, allow_self_checkin=True)
    html = _panel(p['page'](), event_id)
    missing = [t for t in OLD_PANEL if t.format(id=event_id) not in html]
    assert missing == []
    tabs = re.findall(r'data-tab="([a-z]+)"', html)
    panes = re.findall(r'data-tab-pane="([a-z]+)"', html)
    assert sorted(tabs) == sorted(panes) and 'people' in tabs


# ── Criterion 4: at 375px the panel doesn't scroll sideways ────────────────

def test_the_open_panel_fits_a_375px_phone(panel):
    from tests.headless import ORIGIN, _serve_static, chromium
    from tests.test_shared_layout import BOOTSTRAP, DESKTOP_ONLY, MEASURE
    p = panel
    event_id = p['event'](event_type='hackathon', allow_self_checkin=True)
    html = p['page']()
    with open(BOOTSTRAP, 'rb') as f:
        bootstrap = f.read()
    pw, browser = chromium()
    try:
        page = browser.new_page(viewport={'width': 375, 'height': 812})
        # A returning SPOC: the first-visit tour (static/js/pages/spoc__dashboard__5.js) is done
        page.add_init_script("localStorage.setItem('spoc-dashboard-tour-completed', 'true')")

        def handle(route):
            url = route.request.url
            if route.request.resource_type == 'document' and url.split('?')[0] == ORIGIN + '/spoc/dashboard':
                return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
            if 'bootstrap@5.3.3/dist/css/bootstrap.min.css' in url:
                return route.fulfill(status=200, body=bootstrap, content_type='text/css')
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + '/spoc/dashboard', wait_until='load')
        page.wait_for_timeout(300)
        page.click(f'#card-{event_id}')
        page.wait_for_timeout(300)
        assert page.is_visible(f'#detail-panel-{event_id} [data-next-steps]')
        measure = MEASURE.replace('DESKTOP_ONLY', repr(DESKTOP_ONLY))
        problems = []
        for tab in ('overview', 'people', 'logistics', 'comms', 'certs', 'settings'):
            page.click(f'#detail-panel-{event_id} .tab-btn[data-tab="{tab}"]')
            page.wait_for_timeout(100)
            seen = page.evaluate(measure)
            if seen['scrolled'] or seen['cut']:
                problems.append((tab, seen['scrolled'], seen['cut']))
        assert problems == []
    finally:
        browser.close()
        pw.stop()
