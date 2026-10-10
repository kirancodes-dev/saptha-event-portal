"""
tests/test_forms_feed_api_authz.py — BLK-04b on the real SQL database layer:
per-event checks on the form builder and responses, a tokenised personal
calendar feed, and CSRF for session-cookie calls to /api/v1.
"""
import re

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def setup(real_app):
    flask_app, db = real_app
    people = {k: f"{_unique(k)}@test.edu" for k in ('spoc_a', 'spoc_b', 'coord', 'student')}
    _user(db, people['spoc_a'], 'ClubSPOC')
    _user(db, people['spoc_b'], 'ClubSPOC')
    _user(db, people['coord'], 'Coordinator')
    _user(db, people['student'], 'Student')
    spoc_b = _login(flask_app, people['spoc_b'], 'ClubSPOC')
    title = _unique('Feed Event')
    event_b = _create_event(spoc_b, db, title, '2030-06-01', fee=0, team=False)
    db.collection('events').document(event_b).update(
        {'staff': [{'name': 'C', 'email': people['coord'], 'role': 'Coordinator'}]})
    student = _login(flask_app, people['student'], 'Student')
    student.post(f'/forms/submit/{event_b}', data={'privacy_consent': 'yes',
        'full_name': 'Stu Dent', 'email': people['student'], 'phone': '9876543210', 'usn': '1SN20CS555'})
    return {'app': flask_app, 'db': db, 'people': people, 'event_b': event_b, 'title': title,
            'spoc_b': spoc_b, 'student': student}


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_form_builder_and_responses_are_per_event(setup):
    s = setup
    event_b = s['event_b']
    spoc_a = _login(s['app'], s['people']['spoc_a'], 'ClubSPOC')

    assert spoc_a.get(f'/forms/builder/{event_b}').status_code == 403
    assert spoc_a.get(f'/forms/responses/{event_b}').status_code == 403
    assert spoc_a.get(f'/forms/responses/export/{event_b}').status_code == 403
    before = s['db'].collection('event_forms').document(event_b).get().to_dict()
    save = spoc_a.post(f'/forms/save/{event_b}', json={'fields': [{'id': 'hacked', 'label': 'Hacked'}]})
    assert save.status_code == 403
    assert s['db'].collection('event_forms').document(event_b).get().to_dict() == before

    # The owner can do all of it; assigned staff can see responses but not edit the form
    assert s['spoc_b'].get(f'/forms/builder/{event_b}').status_code == 200
    assert s['spoc_b'].get(f'/forms/responses/{event_b}').status_code == 200
    export = s['spoc_b'].get(f'/forms/responses/export/{event_b}')
    assert export.status_code == 200 and s['people']['student'] in export.get_data(as_text=True)
    coord = _login(s['app'], s['people']['coord'], 'EventCoordinator')  # login maps Coordinator → EventCoordinator
    assert coord.get(f'/forms/responses/{event_b}').status_code == 200
    assert coord.get(f'/forms/builder/{event_b}').status_code == 403


# ── Criteria 2 and 7 (calendar feed) ───────────────────────────────────────

def _events_in(resp):
    return resp.get_data(as_text=True).count('BEGIN:VEVENT')


def test_calendar_feed_ignores_user_param_and_works_with_a_rotatable_token(setup):
    s = setup
    anonymous = s['app'].test_client()

    leaked = anonymous.get(f"/calendar/feed.ics?user={s['people']['student']}")
    assert leaked.status_code == 200
    assert _events_in(leaked) == 0
    assert s['title'] not in leaked.get_data(as_text=True)

    # Logged in, the student's own feed has the event, and pages link a token URL
    assert _events_in(s['student'].get('/calendar/feed.ics')) == 1
    page = s['student'].get('/participant/my_events').get_data(as_text=True)
    feed_url = re.search(r'href="(/calendar/feed\.ics\?token=[^"]+)"', page).group(1)

    # A calendar app (no cookie) gets the same feed with the token ...
    assert _events_in(anonymous.get(feed_url)) == 1
    # ... a tampered token gets nothing ...
    assert _events_in(anonymous.get(feed_url[:-3] + 'xyz')) == 0
    # ... and after a reset the old link is dead
    assert s['student'].post('/calendar/feed/rotate').status_code == 302
    assert _events_in(anonymous.get(feed_url)) == 0
    new_page = s['student'].get('/participant/my_events').get_data(as_text=True)
    new_url = re.search(r'href="(/calendar/feed\.ics\?token=[^"]+)"', new_page).group(1)
    assert new_url != feed_url and _events_in(anonymous.get(new_url)) == 1


# ── Criterion 6 (/api/v1 CSRF) ─────────────────────────────────────────────

def test_session_cookie_api_writes_need_csrf_but_bearer_tokens_dont(setup, monkeypatch):
    s = setup
    db, student = s['db'], s['student']
    email = s['people']['student']
    # Pages carry a CSRF token tied to this session
    page = student.get('/participant/my_events').get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    monkeypatch.setitem(s['app'].config, 'WTF_CSRF_ENABLED', True)

    forged = student.put('/api/v1/users/me', json={'name': 'Forged Name'})
    assert forged.status_code == 400
    assert db.collection('users').document(email).get().to_dict()['name'] != 'Forged Name'

    # Reads still work with the session alone
    assert student.get('/api/v1/users/me').status_code == 200

    ok = student.put('/api/v1/users/me', json={'name': 'Real Name'}, headers={'X-CSRFToken': csrf})
    assert ok.status_code == 200
    assert db.collection('users').document(email).get().to_dict()['name'] == 'Real Name'

    # Mobile apps use Bearer tokens and need no CSRF token
    from auth_jwt import create_tokens
    with s['app'].app_context():
        token = create_tokens(email, 'Student')['access_token']
    app_client = s['app'].test_client()
    bearer = app_client.put('/api/v1/users/me', json={'name': 'App Name'},
                            headers={'Authorization': f'Bearer {token}'})
    assert bearer.status_code == 200
    assert db.collection('users').document(email).get().to_dict()['name'] == 'App Name'
