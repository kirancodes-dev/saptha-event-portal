"""
tests/test_ux_first_pages.py — UPG-294: the home page and each role's first
page are easier to use. Events a visitor can register for come first, dates
read as dates, organisers see an event's status in plain words, the student's
tickets come before the profile card, and a coordinator with no events is told
what is true (real database layer).
"""
import datetime
import re

import pytest

import services_registration_state as rs
from tests.test_integration_flow import _create_event, _login, _unique, _user


def _text(response):
    return response.get_data(as_text=True)


@pytest.fixture
def d(real_app):
    """One organiser with an event that is over and one that is open, the
    older one first by date; both titles share a word no other test uses."""
    flask_app, db = real_app
    spoc = f"{_unique('uxspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    word = _unique('Uxfirst')
    past = (rs.today() - datetime.timedelta(days=4)).isoformat()
    over = _create_event(client, db, f"{word} Over", '2031-04-05', team=False)
    db.collection('events').document(over).update(
        {'status': 'registration_open', 'date': past, 'end_date': past, 'deadline': past, 'reg_deadline': past})
    opened = _create_event(client, db, f"{word} Open", '2031-04-06', team=False)
    db.collection('events').document(opened).update({'status': 'registration_open'})
    return {'app': flask_app, 'db': db, 'spoc': spoc, 'client': client, 'word': word,
            'over': over, 'open': opened, 'past': past}


# ── Criterion 1: what can be registered for comes first ─────────────────────

def test_the_listing_order_puts_what_can_be_registered_for_first():
    def key(state, date):
        return rs.listing_key({'key': state}, date)
    rows = [('ended', '2031-01-01'), ('ended', '2031-02-01'), ('cancelled', '2031-05-01'), ('closed', '2031-03-09'),
            ('not_open', '2031-03-08'), ('waitlist', '2031-03-07'), ('open', '2031-03-20'), ('programme', '2031-03-10'),
            ('open', ''), ('unpublished', '2031-03-01')]
    ordered = sorted(rows, key=lambda r: key(*r))
    assert ordered == [
        ('waitlist', '2031-03-07'), ('programme', '2031-03-10'), ('open', '2031-03-20'), ('open', ''),   # soonest first, undated last
        ('not_open', '2031-03-08'), ('closed', '2031-03-09'),
        ('cancelled', '2031-05-01'), ('unpublished', '2031-03-01'), ('ended', '2031-02-01'), ('ended', '2031-01-01'),  # latest first
    ]


def test_the_home_page_and_the_catalogue_list_open_events_before_finished_ones(d):
    visitor = d['app'].test_client()
    listed = visitor.get(f"/?q={d['word']}&format=json").get_json()['events']
    assert [e['id'] for e in listed] == [d['open'], d['over']]        # by date alone the finished one was first

    for path in (f"/?q={d['word']}", f"/events?q={d['word']}"):
        page = _text(visitor.get(path))
        assert f"{d['word']} Open" in page and f"{d['word']} Over" in page, path
        assert page.index(f"{d['word']} Open") < page.index(f"{d['word']} Over"), path


# ── Criterion 2: dates read as dates ────────────────────────────────────────

def test_a_stored_date_is_worded_for_people():
    assert rs.day_text('2026-11-25') == '25 Nov 2026'
    assert rs.day_text('2026-01-05') == '5 Jan 2026'
    assert rs.day_text('2026-11-25T10:00') == '25 Nov 2026, 10:00'
    assert rs.day_text('2026-11-25 09:30:00') == '25 Nov 2026, 09:30'
    assert rs.day_text('TBA') == 'TBA' and rs.day_text('Date to be announced') == 'Date to be announced'
    assert rs.day_text('') == '' and rs.day_text(None) == ''
    assert rs.day_text('2026-13-45') == '2026-13-45'                  # not a date: left as typed


def test_the_first_pages_show_the_date_in_words(d):
    visitor = d['app'].test_client()
    home = _text(visitor.get(f"/?q={d['word']}"))
    dates = re.findall(r'data-info="date"><i[^>]*></i>([^<]*)</span>', home)
    assert dates == ['6 Apr 2031', rs.day_text(d['past'])]
    assert '6 Apr 2031' in _text(visitor.get(f"/events?q={d['word']}"))

    console = _text(d['client'].get(f"/spoc/dashboard?q={d['word']}"))
    assert re.search(r'fa-calendar"[^>]*></i>6 Apr 2031</span>', console)
    assert '></i>2031-04-06</span>' not in console

    admin = f"{_unique('uxadmin')}@test.edu"
    _user(d['db'], admin, 'SuperAdmin')
    table = _text(_login(d['app'], admin, 'SuperAdmin').get(f"/admin/dashboard?q={d['word']}"))
    assert '>6 Apr 2031</td>' in table and '>2031-04-06</td>' not in table

    student = f"{_unique('uxstud')}@test.edu"
    _user(d['db'], student, 'Student')
    d['db'].collection('registrations').document(_unique('REG')).set({
        'event_id': d['open'], 'lead_email': student, 'lead_name': 'Ux Student', 'status': 'Confirmed',
        'payment_status': 'Free', 'attendance': 'Pending', 'registered_at': datetime.datetime.now().isoformat()})
    dash = _text(_login(d['app'], student, 'Student').get('/participant/dashboard'))
    ticket = dash[dash.index('id="tickets-section"'):]
    assert f"{d['word']} Open" in ticket and '6 Apr 2031' in ticket[:ticket.index('ticket-body-lms')]


@pytest.mark.parametrize('path, expected', [
    ('templates/judge/dashboard.html', "(event.date or 'Date to be announced')|day"),
    ('templates/coordinator/scanner_selector.html', "'Tomorrow · ' ~ ev.date|day"),
    ('templates/coordinator/scanner_selector.html', "ev.category ~ ' · ' ~ ev.date|day"),
    ('templates/coordinator/dashboard.html', '{{ event.date|day }}'),
    ('templates/events/catalog.html', "(ev.start_datetime or ev.date or 'Date to be announced')|day"),
    ('templates/participant/dashboard.html', '{{ evt.date|day }}'),
    ('templates/participant/dashboard.html', '{{ reg.event_date|day }}'),
])
def test_the_staff_pages_word_the_date_the_same_way(path, expected):
    with open(path, encoding='utf-8') as fh:
        assert expected in fh.read()


# ── Criterion 3: organisers see the status in plain words ───────────────────

def test_the_organiser_status_is_the_registration_state_or_why_it_is_not_public():
    on = datetime.date(2031, 3, 10)

    def words(**fields):
        event = dict({'id': 'e1', 'status': 'registration_open', 'date': '2031-03-20'}, **fields)
        return rs.organiser_status(event, rs.state(event, on=on))['label']

    assert words() == 'Registration open'
    assert words(date='2031-03-01') == 'Event over'
    assert words(reg_opens='2031-03-15') == 'Opens soon'
    assert words(reg_deadline='2031-03-05') == 'Registration closed'
    assert words(capacity=2, registration_count=2) == 'Full: waitlist open'
    assert words(status='draft') == 'Draft'
    assert words(status='pending_approval') == 'Waiting for approval'
    assert words(status='changes_requested') == 'Changes requested'
    assert words(status='rejected') == 'Rejected'
    assert words(status='cancelled') == 'Cancelled'
    assert words(status='published', is_fest=True) == 'Published'
    for status in ('draft', 'registration_open', 'cancelled', 'completed'):
        view = rs.organiser_status({'status': status, 'date': '2031-03-20'})
        assert view['label'] and view['tone'] and view['explanation'] and '_' not in view['label']


def test_the_console_and_the_admin_table_say_event_over_not_registration_open(d):
    draft = _create_event(d['client'], d['db'], f"{d['word']} Draft", '2031-04-07', team=False)
    d['db'].collection('events').document(draft).update({'status': 'draft'})

    def statuses(page):
        return sorted(re.findall(r'data-organiser-status="(\w+)">([^<]+)</span>', page))

    expected = [('ended', 'Event over'), ('open', 'Registration open'), ('unpublished', 'Draft')]
    console = _text(d['client'].get(f"/spoc/dashboard?q={d['word']}"))
    assert statuses(console) == expected
    assert 'Registration_open' not in console

    admin = f"{_unique('uxadmin')}@test.edu"
    _user(d['db'], admin, 'SuperAdmin')
    table = _text(_login(d['app'], admin, 'SuperAdmin').get(f"/admin/dashboard?q={d['word']}"))
    assert statuses(table) == expected
    assert 'Registration_open' not in table


# ── Criterion 4: the student's tickets come before the profile card ─────────

def test_the_student_dashboard_starts_with_updates_and_tickets(d):
    student = f"{_unique('uxstud')}@test.edu"
    _user(d['db'], student, 'Student')
    page = _text(_login(d['app'], student, 'Student').get('/participant/dashboard'))
    order = [page.index(mark) for mark in (
        'id="page-title"', 'aria-label="Filter tickets"', 'id="tickets-section"',
        'class="profile-hero"', 'aria-label="Your activity"', '<span>Event attendance</span>')]
    assert order == sorted(order), order
    assert 'id="scoreModal"' not in page      # teams see no score breakdown (UPG-336)
    # nothing was dropped on the way
    # the campus photo is now below the first screen, so it loads when it is reached
    assert re.search(r'<img src="/static/campus.jpg"[^>]*loading="lazy"', page)
    for kept in ('My active tickets', 'Activity score', 'Event attendance', 'Register number', 'id="tab-empty"'):
        assert kept in page, kept


def test_an_announcement_is_above_the_tickets():
    with open('templates/participant/dashboard.html', encoding='utf-8') as fh:
        source = fh.read()
    body = source[source.index('{% block content %}'):]
    assert body.index('{% if announcements %}') < body.index('id="tickets-section"') < body.index('ui.profile_hero(')
    assert body.index('data-unconfirmed-reminder') < body.index('id="tickets-section"')


# ── Criterion 5: a coordinator with no events is told what is true ──────────

def test_a_coordinator_with_no_events_is_pointed_to_the_scanner(d):
    coordinator = f"{_unique('uxcoord')}@test.edu"
    _user(d['db'], coordinator, 'EventCoordinator')
    client = _login(d['app'], coordinator, 'EventCoordinator')
    page = _text(client.get('/coordinator/dashboard'))
    assert 'Start building one' not in page                       # a coordinator can't create events
    assert "You aren't on the staff of any event that is still to come." in page
    assert re.search(r'data-coordinator-empty><a class="btn btn-primary" href="/coordinator/scanner"', page)

    searched = _text(client.get('/coordinator/dashboard?q=zzznothing'))
    assert 'No events match' in searched and 'data-coordinator-empty' not in searched
