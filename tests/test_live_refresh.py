"""
tests/test_live_refresh.py — UPG-267: pages that are already open follow what
changes during an event. The public answer (/live/state.json) carries only the
registration state; the organisers' answer (/live/ops.json) adds counts and is
permission-checked; the page script (static/js/live-refresh.js) applies the
answer, backs off when the server can't be reached, says the page is stale,
and asks nothing while the tab is hidden (real database layer, headless
Chromium for the script).
"""
import datetime
import json

import pytest

import services_registration_state as rs
from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def site(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('livespoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (rs.today() + datetime.timedelta(days=40)).isoformat()

    def event(**fields):
        title = _unique('Live Event')
        event_id = _create_event(owner, db, title, day, team=False)
        db.collection('events').document(event_id).update(dict({'status': 'registration_open',
                                                                'reg_deadline': day}, **fields))
        return event_id, title

    return {'app': flask_app, 'db': db, 'owner': owner, 'spoc': spoc, 'event': event, 'day': day,
            'visitor': flask_app.test_client()}


def _register(d, event_id, name='Asha Rao'):
    email = f"{_unique('liveperson')}@test.edu"
    resp = d['app'].test_client().post(f'/forms/submit/{event_id}', data={
        'full_name': name, 'email': email, 'phone': '9876543210', 'usn': '1SN22CS101', 'privacy_consent': 'yes'})
    assert resp.status_code in (200, 302)
    return email


# ── Criterion 1: the public answer ──────────────────────────────────────────

def test_the_public_answer_is_the_state_every_page_shows_and_nothing_personal(site):
    d = site
    event_id, _ = d['event']()
    hidden_id, _ = d['event'](visibility='Private')
    draft_id, _ = d['event'](status='draft')
    email = _register(d, event_id, name='Asha Private-Name')

    resp = d['visitor'].get(f'/live/state.json?events={event_id},{hidden_id},{draft_id},no-such-event')
    assert resp.status_code == 200 and resp.headers['Cache-Control'] == 'no-store'
    data = resp.get_json()
    # private, unpublished and unknown events are left out, as if they didn't exist
    assert list(data['events']) == [event_id]
    view = data['events'][event_id]
    assert set(view) == {'key', 'label', 'tone', 'explanation', 'action', 'action_label', 'action_url'}
    event = d['db'].collection('events').document(event_id).get().to_dict()
    assert view == rs.public(rs.for_event(d['db'], event_id, event))
    assert view['key'] == 'open' and view['action_url'] == f'/forms/register/{event_id}'
    body = resp.get_data(as_text=True)
    assert email not in body and 'Asha' not in body and '9876543210' not in body
    assert data['poll'] >= 10 and data['at']

    # the organiser closes registration: the next answer says so
    d['db'].collection('events').document(event_id).update({'status': 'registration_closed'})
    view = d['visitor'].get(f'/live/state.json?events={event_id}').get_json()['events'][event_id]
    assert view['key'] == 'closed' and view['action'] == '' and view['action_url'] == ''

    assert d['visitor'].get('/live/state.json').get_json()['events'] == {}


# ── Criterion 2: the organisers' answer ─────────────────────────────────────

def test_the_organisers_answer_has_counts_and_only_for_their_own_events(site):
    d = site
    event_id, _ = d['event'](capacity=2, limits={'max_participants': 2})
    _register(d, event_id)
    _register(d, event_id, name='Bala K')
    _register(d, event_id, name='Chitra W')        # the third joins the waitlist

    assert d['visitor'].get(f'/live/ops.json?events={event_id}').status_code == 401

    data = d['owner'].get(f'/live/ops.json?events={event_id}').get_json()
    view = data['events'][event_id]
    regs = [r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()]
    waiting = [w for w in d['db'].collection('waitlists').where('event_id', '==', event_id).stream()
               if w.to_dict().get('status') == 'waiting']
    assert view['registered'] == len(regs) == 2 and view['waiting'] == len(waiting) == 1
    assert view['checked_in'] == 0 and view['key'] == 'waitlist'
    assert view['seats_limit'] == 2 and view['seats_free'] == 0

    # one is checked in: the count follows the record
    reg_id = d['db'].collection('registrations').where('event_id', '==', event_id).stream().__iter__().__next__().id
    d['db'].collection('registrations').document(reg_id).update({'attendance': 'Present'})
    assert d['owner'].get(f'/live/ops.json?events={event_id}').get_json()['events'][event_id]['checked_in'] == 1

    # another club's SPOC and a student get nothing about this event
    other = f"{_unique('otherspoc')}@test.edu"
    _user(d['db'], other, 'ClubSPOC')
    assert _login(d['app'], other, 'ClubSPOC').get(f'/live/ops.json?events={event_id}').get_json()['events'] == {}
    student = f"{_unique('livestudent')}@test.edu"
    _user(d['db'], student, 'Student')
    assert _login(d['app'], student, 'Student').get(f'/live/ops.json?events={event_id}').get_json()['events'] == {}
    body = d['owner'].get(f'/live/ops.json?events={event_id}').get_data(as_text=True)
    assert 'Bala' not in body and '@test.edu' not in body


def test_the_pages_carry_the_live_regions(site):
    d = site
    event_id, title = d['event']()
    home = d['visitor'].get(f'/?q={title}').get_data(as_text=True)
    assert f'data-live-event="{event_id}"' in home and '/static/js/live-refresh.js' in home
    page = d['visitor'].get(f'/event/{event_id}').get_data(as_text=True)
    assert f'data-live-event="{event_id}"' in page and '/static/js/live-refresh.js' in page
    catalog = d['visitor'].get(f'/events?q={title}').get_data(as_text=True)
    assert f'data-live-event="{event_id}"' in catalog and '/static/js/live-refresh.js' in catalog
    panel = d['owner'].get('/spoc/dashboard').get_data(as_text=True)
    assert f'data-live-event="{event_id}" data-live-scope="ops"' in panel and '/static/js/live-refresh.js' in panel


# ── Criterion 3: the open page follows, backs off and says when it's stale ──

def test_an_open_event_page_follows_a_change_and_says_when_it_is_stale(site):
    from tests.headless import chromium, live_server
    d = site
    event_id, _ = d['event']()
    ref = d['db'].collection('events').document(event_id)
    p, browser = chromium()
    try:
        with live_server(d['app']) as server:
            page = browser.new_page()
            asked, down = [], {'on': False}

            def handle(route):
                url = route.request.url
                if not url.startswith(server.url):
                    return route.abort()             # nothing leaves the machine
                if '/live/state.json' in url:
                    asked.append(url)
                    if down['on']:
                        return route.abort()
                return route.continue_()
            page.route('**/*', handle)
            page.goto(f'{server.url}/event/{event_id}', wait_until='load')
            region = f'[data-live-event="{event_id}"]'
            assert page.get_attribute(region, 'data-reg-state') == 'open'
            assert page.is_visible(f'{region} [data-live-action]')
            assert page.get_attribute(f'{region} [data-live-action]', 'href') == f'/forms/register/{event_id}'

            # the organiser fills the event: the open page offers the waitlist
            ref.update({'capacity': 1, 'limits': {'max_participants': 1}, 'registration_count': 1})
            page.evaluate('window.SELive.refresh()')
            page.wait_for_selector(f'{region}[data-reg-state="waitlist"]', state='attached')
            assert page.inner_text(f'{region} [data-live-action-label]') == 'Join the waitlist'
            assert 'seat' in page.inner_text(f'{region} [data-live-explanation]')

            # the organiser closes registration: the link goes, the reason shows
            ref.update({'status': 'registration_closed'})
            page.evaluate('window.SELive.refresh()')
            page.wait_for_selector(f'{region}[data-reg-state="closed"]', state='attached')
            assert not page.is_visible(f'{region} [data-live-action]')
            assert page.get_attribute(f'{region} [data-live-action]', 'href') is None
            assert page.is_visible(f'{region} [data-live-locked]')
            assert page.inner_text(f'{region} [data-live-label]') == 'Registration closed'
            assert page.inner_text(f'{region} [data-live-explanation]') == 'The organisers have closed registration.'
            assert not page.is_visible('[data-live-status]')          # nothing to say while it's current

            # the server can't be reached: the page says so, keeps what it knew, and waits longer
            before = page.evaluate('window.SELive.wait()')
            down['on'] = True
            page.evaluate('window.SELive.refresh()')
            page.wait_for_selector('[data-live-status].live-status--stale', state='visible')
            assert 'Showing what was true at' in page.inner_text('[data-live-status]')
            assert page.get_attribute(region, 'data-reg-state') == 'closed'
            assert page.evaluate('window.SELive.wait()') == before * 2
            for _ in range(8):
                page.evaluate('window.SELive.refresh()')
                page.wait_for_timeout(60)
            assert page.evaluate('window.SELive.wait()') == 300       # never more than five minutes

            # a hidden tab asks nothing; shown again, it catches up at once
            down['on'] = False
            page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});"
                          "document.dispatchEvent(new Event('visibilitychange'))")
            count = len(asked)
            page.evaluate('window.SELive.refresh()')
            page.wait_for_timeout(200)
            assert len(asked) == count
            ref.update({'status': 'registration_open', 'capacity': 50, 'limits': {'max_participants': 50}})
            page.wait_for_timeout(5100)                                # past the "just asked" guard
            page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false});"
                          "document.dispatchEvent(new Event('visibilitychange'))")
            page.wait_for_selector(f'{region}[data-reg-state="open"]', state='attached')
            assert len(asked) == count + 1
            assert page.is_visible(f'{region} [data-live-action]') and not page.is_visible('[data-live-status]')
            assert page.evaluate('window.SELive.wait()') == json.loads('30')
    finally:
        browser.close()
        p.stop()
