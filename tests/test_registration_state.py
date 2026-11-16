"""
tests/test_registration_state.py — UPG-266: one registration state for every
page. The rules (unit), and the home page, catalogue, event page, popup,
open-events page, registration form, student dashboard and organiser lists
showing the same state and action for the same event, also after the
organiser changes dates, seats or status (real database layer).
"""
import datetime
import re

import pytest

import services_registration_state as rs
from tests.test_integration_flow import _create_event, _login, _unique, _user

TODAY = datetime.date(2031, 3, 10)


def _event(**fields):
    base = {'id': 'e1', 'status': 'registration_open', 'date': '2031-03-20', 'reg_deadline': '2031-03-15'}
    base.update(fields)
    return base


def _key(**fields):
    return rs.state(_event(**fields), on=TODAY)['key']


# ── Criterion 1: the rules ──────────────────────────────────────────────────

def test_each_state_has_its_own_rule_label_and_action():
    assert _key() == 'open'
    assert _key(reg_opens='2031-03-12') == 'not_open'
    assert _key(reg_opens='2031-03-10') == 'open'                      # opens at the start of that day
    assert _key(status='published') == 'not_open'
    assert _key(reg_deadline='2031-03-09') == 'closed'
    assert _key(reg_deadline='2031-03-10') == 'open'                   # the deadline day still counts
    assert _key(status='registration_closed') == 'closed'
    assert _key(capacity=10, registration_count=10) == 'waitlist'
    assert _key(limits={'max_participants': 3}, registration_count=5) == 'waitlist'
    assert _key(capacity=10, registration_count=9) == 'open'
    assert _key(status='cancelled') == 'cancelled'
    assert _key(status='draft') == 'unpublished'
    assert _key(status='pending_approval') == 'unpublished'
    assert _key(status='completed') == 'ended'
    assert _key(date='2031-03-01', reg_deadline='') == 'ended'
    assert _key(date='2031-03-08', end_date='2031-03-10', reg_deadline='') == 'open'   # a multi-day event's last day
    assert _key(status='published', is_fest=True) == 'programme'
    assert rs.state(_event(capacity=10, registration_count=10), waitlist_open=False, on=TODAY)['key'] == 'full'
    assert rs.state(_event(capacity=10, registration_count=2), waiting_for_organiser=True, on=TODAY)['key'] == 'waitlist'

    for fields in ({}, {'reg_opens': '2031-03-12'}, {'reg_deadline': '2031-03-09'}, {'status': 'cancelled'},
                   {'capacity': 1, 'registration_count': 1}, {'status': 'draft'}, {'status': 'completed'}):
        view = rs.state(_event(**fields), on=TODAY)
        assert view['label'] and view['explanation'], view
        # an action exactly when the form would take the sign-up
        assert bool(view['action']) == view['registerable'] == (view['key'] in ('open', 'waitlist'))
        assert (view['action_url'] == '/forms/register/e1') == bool(view['action'])

    assert rs.state(_event(reg_opens='2031-03-12'), on=TODAY)['explanation'] == "Registration opens on 12 March 2031."
    assert rs.state(_event(reg_deadline='2031-03-09'), on=TODAY)['explanation'] == "Registration closed on 9 March 2031."
    assert "until 15 March 2031" in rs.state(_event(), on=TODAY)['explanation']
    assert "1 seat left" in rs.state(_event(capacity=10, registration_count=9), on=TODAY)['explanation']


def test_the_forms_gate_is_the_same_rule():
    from routes_forms import registration_closed
    far = (rs.today() + datetime.timedelta(days=30)).isoformat()
    soon = (rs.today() + datetime.timedelta(days=3)).isoformat()
    past = (rs.today() - datetime.timedelta(days=3)).isoformat()
    assert registration_closed({'status': 'registration_open', 'date': far}) is False
    assert registration_closed({'status': 'active', 'date': far, 'capacity': 1, 'registration_count': 1}) is False  # waitlist
    assert registration_closed({'status': 'registration_open', 'date': far, 'reg_opens': soon}) is True
    assert registration_closed({'status': 'registration_open', 'date': far, 'reg_deadline': past}) is True
    assert registration_closed({'status': 'published', 'date': far}) is True
    assert registration_closed({'status': 'cancelled', 'date': far}) is True
    assert registration_closed({'status': 'registration_open', 'date': past}) is True     # the event is over


# ── Criteria 2–4: the pages ─────────────────────────────────────────────────

@pytest.fixture
def site(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('statespoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (rs.today() + datetime.timedelta(days=40)).isoformat()

    def event(**fields):
        title = _unique('State Event')
        event_id = _create_event(owner, db, title, day, team=False)
        db.collection('events').document(event_id).update(dict({'status': 'registration_open',
                                                                'reg_deadline': day}, **fields))
        return event_id, title

    return {'app': flask_app, 'db': db, 'owner': owner, 'spoc': spoc, 'event': event, 'day': day,
            'visitor': flask_app.test_client()}


def _card(html, title):
    """The home page's card for one event."""
    at = html.index(f'<h5 class="ev-title">{title}</h5>')
    start = html.rindex('ev-col', 0, at)
    end = html.find('ev-col scroll-animator', at)
    return html[start:end if end != -1 else at + 3000]


def _states_everywhere(d, event_id, title):
    """{page: state key} for one event on every visitor page."""
    visitor = d['visitor']
    home = visitor.get('/').get_data(as_text=True)
    out = {'home': re.search(r'data-reg-state="(\w+)"', _card(home, title))}
    catalog = visitor.get(f'/events?q={title}').get_data(as_text=True)
    out['catalog'] = re.search(r'data-reg-state="(\w+)"', catalog[catalog.index('ev-grid'):])
    out['page'] = re.search(r'data-reg-state="(\w+)"', visitor.get(f'/event/{event_id}').get_data(as_text=True))
    out['popup'] = re.search(r'data-reg-state="(\w+)"',
                             visitor.get(f'/event/{event_id}?fragment=1').get_data(as_text=True))
    return {page: (m.group(1) if m else None) for page, m in out.items()}


def test_every_page_shows_the_same_state_and_never_an_unexplained_closed(site):
    d = site
    soon = (rs.today() + datetime.timedelta(days=5)).isoformat()
    past = (rs.today() - datetime.timedelta(days=2)).isoformat()
    cases = {
        'open': {},
        'not_open': {'reg_opens': soon},
        'closed': {'reg_deadline': past},
        'waitlist': {'capacity': 2, 'limits': {'max_participants': 2}, 'registration_count': 2},
        'cancelled': None,
    }
    for expected, fields in cases.items():
        event_id, title = d['event'](**(fields or {}))
        if expected == 'cancelled':
            # A cancelled event leaves the public lists; its page and form still explain
            d['db'].collection('events').document(event_id).update({'status': 'cancelled'})
            assert title not in d['visitor'].get('/').get_data(as_text=True)
        else:
            seen = _states_everywhere(d, event_id, title)
            assert set(seen.values()) == {expected}, (expected, seen)
            card = _card(d['visitor'].get('/').get_data(as_text=True), title)
            if expected in ('open', 'waitlist'):
                assert f'href="/forms/register/{event_id}"' in card
                assert ('Join the waitlist' in card) == (expected == 'waitlist')
            else:
                # no register link, never a bare "Closed": the reason is on the card
                assert f'/forms/register/{event_id}' not in card
                assert 'data-reg-explanation' in card and '>Closed<' not in card.replace('\n', '')
                assert rs.for_event(d['db'], event_id, d['db'].collection('events').document(event_id)
                                    .get().to_dict())['explanation'] in card

        form = d['visitor'].get(f'/forms/register/{event_id}')
        body = form.get_data(as_text=True)
        if expected in ('open', 'waitlist'):
            assert 'data-reg-state' not in body and 'name="email"' in body
        else:
            assert f'data-reg-state="{expected}"' in body and 'name="email"' not in body
            assert 'deadline for' not in body or expected == 'closed'
    not_open = d['visitor'].get('/forms/register/' + d['event'](reg_opens=soon)[0]).get_data(as_text=True)
    assert "Registration isn&#39;t open yet" in not_open or "Registration isn't open yet" in not_open
    assert 'Registration opens on' in not_open


def test_a_not_yet_open_event_takes_no_registration(site):
    d = site
    soon = (rs.today() + datetime.timedelta(days=5)).isoformat()
    event_id, _ = d['event'](reg_opens=soon)
    email = f"{_unique('early')}@test.edu"
    resp = d['visitor'].post(f'/forms/submit/{event_id}', data={
        'full_name': 'Early Bird', 'email': email, 'phone': '9876543210', 'privacy_consent': 'on'})
    assert resp.status_code in (302, 200)
    regs = list(d['db'].collection('registrations').where('event_id', '==', event_id).stream())
    assert regs == []


def test_after_the_organiser_changes_dates_seats_or_status_every_page_follows(site):
    d = site
    event_id, title = d['event']()
    ref = d['db'].collection('events').document(event_id)
    assert set(_states_everywhere(d, event_id, title).values()) == {'open'}

    ref.update({'capacity': 1, 'limits': {'max_participants': 1}, 'registration_count': 1})   # seats
    assert set(_states_everywhere(d, event_id, title).values()) == {'waitlist'}
    ref.update({'capacity': 50, 'limits': {'max_participants': 50}})
    assert set(_states_everywhere(d, event_id, title).values()) == {'open'}

    ref.update({'reg_deadline': (rs.today() - datetime.timedelta(days=1)).isoformat()})         # dates
    assert set(_states_everywhere(d, event_id, title).values()) == {'closed'}
    ref.update({'reg_deadline': d['day']})

    # status, through the organiser's own transition
    resp = d['owner'].post(f'/spoc/event/{event_id}/transition', data={'target_state': 'registration_closed'})
    assert resp.status_code in (302, 200)
    assert ref.get().to_dict()['status'] == 'registration_closed'
    assert set(_states_everywhere(d, event_id, title).values()) == {'closed'}
    # the organisers' own pages say what visitors see
    panel = d['owner'].get('/spoc/dashboard').get_data(as_text=True)
    assert 'data-visitor-state="closed"' in panel

    ref.update({'visibility': 'Private'})                                                       # visibility
    assert title not in d['visitor'].get('/').get_data(as_text=True)
    assert event_id not in d['visitor'].get(f'/events?q={title}').get_data(as_text=True)   # the search box echoes the title


def test_check_back_soon_only_when_nothing_is_listed(site):
    d = site
    event_id, title = d['event'](reg_deadline=(rs.today() - datetime.timedelta(days=1)).isoformat())
    home = d['visitor'].get(f'/?q={title}').get_data(as_text=True)
    assert title in home
    assert 'Check back soon' not in home
    empty = d['visitor'].get('/?q=' + _unique('nothing-matches')).get_data(as_text=True)
    assert 'Check back soon' in empty


def test_the_student_dashboard_offers_the_same_action(site):
    d = site
    student = f"{_unique('statestudent')}@test.edu"
    _user(d['db'], student, 'Student')
    client = _login(d['app'], student, 'Student')
    soon = (rs.today() + datetime.timedelta(days=1)).isoformat()
    # earliest dates, so they are among the six the dashboard lists
    open_id, open_title = d['event'](date=soon, reg_deadline=soon)
    wait_id, wait_title = d['event'](date=soon, reg_deadline=soon, capacity=1, limits={'max_participants': 1},
                                     registration_count=1)
    later_id, later_title = d['event'](date=soon, reg_deadline=soon, reg_opens=soon)
    page = client.get('/participant/dashboard').get_data(as_text=True)
    if open_title in page:   # the list shows six events; other tests' events may fill it
        assert f'href="/forms/register/{open_id}" class="btn btn-sm btn-primary" data-reg-action="register"' in page
    if wait_title in page:
        assert f'href="/forms/register/{wait_id}" class="btn btn-sm btn-primary" data-reg-action="waitlist"' in page
    if later_title in page:
        assert f'/forms/register/{later_id}' not in page
    assert any(t in page for t in (open_title, wait_title, later_title)) or 'data-reg-action' in page


def test_the_open_events_page_and_the_admin_list_show_the_state(site):
    d = site
    event_id, title = d['event'](audience='open', reg_opens=(rs.today() + datetime.timedelta(days=5)).isoformat())
    listing = d['visitor'].get(f'/open-events?q={title}').get_data(as_text=True)
    assert title in listing and 'data-reg-state="not_open"' in listing and 'Registration opens on' in listing

    admin = f"{_unique('stateadmin')}@test.edu"
    _user(d['db'], admin, 'SuperAdmin')
    page = _login(d['app'], admin, 'SuperAdmin').get(f'/admin/events?q={title}').get_data(as_text=True)
    assert title in page and 'data-visitor-state="not_open"' in page


def test_a_full_events_seat_meter_says_what_the_state_says(site):
    """The seat meter on the event page used to say "Fully booked" beside
    "Join the waitlist"; and one seat is not "All 1 seats"."""
    d = site
    event_id, _ = d['event'](limits={'max_participants': 1})
    d['app'].test_client().post(f'/forms/submit/{event_id}', data={
        'full_name': 'Sole Seat', 'email': f"{_unique('sole')}@test.edu", 'phone': '9876543210',
        'privacy_consent': 'yes'})
    for url in (f'/event/{event_id}', f'/event/{event_id}?fragment=1'):
        page = d['visitor'].get(url).get_data(as_text=True)
        assert 'data-seats-full="waitlist"' in page and 'All seats taken: waitlist open' in page, url
        assert 'Fully booked' not in page and 'All 1 seats' not in page, url
        assert 'The one seat is taken. You can join the waitlist' in page, url
    assert rs.state({'status': 'registration_open', 'limits': {'max_participants': 1}, 'registration_count': 1},
                    waitlist_open=False)['explanation'] == 'The one seat is taken.'
    assert rs.state({'status': 'registration_open', 'limits': {'max_participants': 40}, 'registration_count': 40},
                    )['explanation'].startswith('All 40 seats are taken.')
    # a seat still free: the meter counts it, and says nothing about a waitlist
    open_id, _ = d['event'](limits={'max_participants': 5})
    page = d['visitor'].get(f'/event/{open_id}').get_data(as_text=True)
    assert 'data-seats-full' not in page and '5 spots remaining' in page
