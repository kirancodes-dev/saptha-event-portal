"""
tests/test_builder_and_coordinator_view.py — UPG-79 (the form builder's Back
returns where you came from and says what every form gets), UPG-78 (the old
coordinator create-event form is gone; events are made in the wizard) and
UPG-80 (a Super Admin's "Coordinator view" is labelled as that view and
counts real registrations).
"""
import pytest

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user


@pytest.fixture
def s(real_app):
    flask_app, db = real_app
    people = {k: f"{_unique(k)}@test.edu" for k in ('admin', 'spoc', 'coord')}
    _user(db, people['admin'], 'SuperAdmin', name='Root Admin')
    _user(db, people['spoc'], 'ClubSPOC', name='Club Lead')
    _user(db, people['coord'], 'Coordinator', name='Coord One')
    admin = flask_app.test_client()
    resp = admin.post('/login', data={'role': 'SuperAdmin', 'email': people['admin'], 'password': PASSWORD,
                                      'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert resp.status_code == 302 and resp.headers['Location'] != '/login'
    spoc = _login(flask_app, people['spoc'], 'ClubSPOC')
    team_event = _create_event(spoc, db, _unique('Team Event'), '2030-06-01', team=True)
    solo_event = _create_event(spoc, db, _unique('Solo Event'), '2030-06-02', team=False)
    before = {d.id for d in db.collection('users').stream()} - set(people.values())
    yield {'app': flask_app, 'db': db, 'people': people, 'admin': admin, 'spoc': spoc,
           'team': team_event, 'solo': solo_event}
    # Leave the user list as it was (tests/test_admin_users.py reads its first page)
    for d in db.collection('users').stream():
        if d.id not in before:
            db.collection('users').document(d.id).delete()


def _back_href(page):
    marker = 'id="btn-back"'
    tag = page[page.rindex('<a', 0, page.index(marker)):page.index(marker)]
    return tag.split('href="', 1)[1].split('"', 1)[0]


# ── UPG-79: the form builder ───────────────────────────────────────────────

def test_builder_back_returns_to_the_page_that_opened_it(s):
    url = f"/forms/builder/{s['team']}"
    from utils_email import _base_url
    with s['app'].app_context():
        site = _base_url()                 # this site's address is BASE_URL (BLK-16)
    came_from = f"{site}/spoc/event/{s['team']}/review?tab=form"
    page = s['admin'].get(url, headers={'Referer': came_from}).get_data(as_text=True)
    assert _back_href(page) == f"/spoc/event/{s['team']}/review?tab=form"
    page = s['admin'].get(url + '?next=/admin/events?status=draft').get_data(as_text=True)
    assert _back_href(page) == '/admin/events?status=draft'


@pytest.mark.parametrize('bad', ['https://evil.example/phish', '//evil.example/x', '/\\evil.example',
                                 'javascript:alert(1)'])
def test_builder_back_never_leaves_the_site(s, bad):
    page = s['admin'].get(f"/forms/builder/{s['team']}?next={bad}",
                          headers={'Referer': bad}).get_data(as_text=True)
    assert _back_href(page) == '/admin/events'


def test_builder_back_without_an_origin_goes_to_the_roles_page_for_the_event(s):
    # Not the coordinator dashboard for a Super Admin, as it used to be
    assert _back_href(s['admin'].get(f"/forms/builder/{s['team']}").get_data(as_text=True)) == '/admin/events'
    assert _back_href(s['spoc'].get(f"/forms/builder/{s['team']}").get_data(as_text=True)) == \
        f"/spoc/event/{s['team']}/review"
    # A builder link to itself (after a reload) isn't a way back
    from utils_email import _base_url
    with s['app'].app_context():
        site = _base_url()
    page = s['spoc'].get(f"/forms/builder/{s['team']}",
                         headers={'Referer': f"{site}/forms/builder/{s['team']}"}).get_data(as_text=True)
    assert _back_href(page) == f"/spoc/event/{s['team']}/review"


def test_builder_says_what_every_form_gets_and_team_rows_come_from_the_event(s):
    team = s['spoc'].get(f"/forms/builder/{s['team']}").get_data(as_text=True)
    solo = s['spoc'].get(f"/forms/builder/{s['solo']}").get_data(as_text=True)
    for page in (team, solo):
        assert 'Name, email, phone and USN are always asked' in page
        assert 'Leave blank if solo' not in page        # no optional team name in the template
        assert "window.addEventListener('beforeunload'" in page
        assert 'loadSimpleTemplate(false)' in page      # no saved form: start from the standard one
    assert 'This is a team event (2–4 people)' in team and 'const IS_TEAM    = true' in team
    assert 'This is a team event' not in solo and 'const IS_TEAM    = false' in solo


# ── UPG-78: one way to create an event ────────────────────────────────────

def _event_count(db):
    return sum(1 for _ in db.collection('events').stream())


@pytest.mark.parametrize('who', ['admin', 'spoc', 'coord'])
def test_the_old_coordinator_create_route_no_longer_creates_events(s, who):
    client = s[who] if who != 'coord' else _login(s['app'], s['people']['coord'], 'EventCoordinator')
    before = _event_count(s['db'])
    resp = client.post('/coordinator/create_event', data={
        'title': _unique('Old Form'), 'date': '2030-07-01', 'deadline': '2030-06-30', 'venue': 'Hall',
        'overview': 'x', 'criteria': 'Score'})
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/spoc/create_event' if who != 'coord' else '/coordinator/dashboard')
    assert _event_count(s['db']) == before


def test_dashboards_have_no_old_create_form_and_send_creators_to_the_wizard(s):
    admin_coord = s['admin'].get('/coordinator/dashboard').get_data(as_text=True)
    admin_home = s['admin'].get('/admin/dashboard').get_data(as_text=True)
    coord = _login(s['app'], s['people']['coord'], 'EventCoordinator').get('/coordinator/dashboard').get_data(as_text=True)
    for page in (admin_coord, admin_home, coord):
        assert 'action="/coordinator/create_event"' not in page
        assert 'createEventWizard' not in page and 'id="createEventModal"' not in page
    assert 'href="/spoc/create_event"' in admin_coord
    assert 'href="/spoc/create_event"' not in coord                # coordinators ask their SPOC


# ── UPG-80: the Super Admin's coordinator view ─────────────────────────────

def test_super_admin_coordinator_view_is_labelled_as_that_view(s):
    page = s['admin'].get('/coordinator/dashboard').get_data(as_text=True)
    assert '<title>Coordinator view' in page
    assert 'Welcome, Root Admin' not in page
    assert 'Seen as Super Admin' in page
    # The admin's own home link isn't marked as the current page here
    assert 'href="/admin/dashboard" class="app-bar__link app-bar__link--ws is-active"' not in page
    coord = _login(s['app'], s['people']['coord'], 'EventCoordinator').get('/coordinator/dashboard').get_data(as_text=True)
    assert 'Welcome, Coord One' in coord and 'Seen as Super Admin' not in coord


def test_coordinator_view_counts_registrations_not_the_cached_counter(s):
    db = s['db']
    db.collection('events').document(s['solo']).update({'status': 'active', 'registration_count': 645})
    for i in range(2):
        db.collection('registrations').document(_unique('reg')).set({
            'event_id': s['solo'], 'lead_email': f'p{i}@test.edu', 'lead_name': f'P {i}', 'status': 'confirmed'})
    page = s['admin'].get(f"/coordinator/dashboard?q={db.collection('events').document(s['solo']).get().to_dict()['title']}")
    text = page.get_data(as_text=True)
    assert '645' not in text
