"""
tests/test_api_event_drafts.py — UPG-82 on the real database layer: events
created through the API start as drafts owned by the caller, are refused with
the wizard's own errors, and then go through the same review as the web wizard.
"""
import datetime

import pytest

from auth_jwt import create_tokens
from services_event_types import parse_form
from tests.test_integration_flow import _login, _unique, _user


@pytest.fixture
def spoc(real_app):
    flask_app, db = real_app
    email = f"{_unique('apispoc')}@test.edu"
    _user(db, email, 'ClubSPOC')
    with flask_app.app_context():
        token = create_tokens(user_email=email, role='ClubSPOC')['access_token']
    return {'app': flask_app, 'db': db, 'email': email, 'headers': {'Authorization': f'Bearer {token}'}}


def _future(days=30):
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


def test_an_api_event_starts_as_a_draft_owned_by_the_caller(spoc):
    client = spoc['app'].test_client()
    resp = client.post('/api/v1/events', headers=spoc['headers'], json={
        'title': _unique('API Workshop'), 'event_type': 'workshop', 'category': 'Technical',
        'date': _future(), 'venue': 'Lab 2', 'fee': 50, 'capacity': 40,
        'description': 'Hands-on session on building REST APIs for students of every year.'})
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()['data']
    assert data['status'] == 'draft' and data['spoc_id'] == spoc['email'] and data['source'] == 'api'
    stored = spoc['db'].collection('events').document(data['id']).get().to_dict()
    assert stored['status'] == 'draft' and stored['fees']['regular'] == 50 and stored['limits']['max_participants'] == 40
    assert spoc['db'].collection('event_forms').document(data['id']).get().exists   # the preset's form, as the wizard

    # The same review as the web wizard: the SPOC who owns it opens its review page
    owner = _login(spoc['app'], spoc['email'], 'ClubSPOC')
    assert owner.get(f"/spoc/event/{data['id']}/review").status_code == 200
    assert data['title'] not in client.get('/events').get_data(as_text=True)          # not public while a draft


@pytest.mark.parametrize('body', [
    {'title': '', 'event_type': 'seminar', 'date': '2030-01-01', 'venue': 'Hall'},
    {'title': 'Odd', 'event_type': 'seminar', 'date': '2030-01-01', 'venue': 'Hall', 'category': 'Nonsense'},
    {'title': 'No venue', 'event_type': 'seminar', 'date': '2030-01-01'},
    {'title': 'Bad fee', 'event_type': 'seminar', 'date': '2030-01-01', 'venue': 'Hall', 'reg_fee': '-5'},
])
def test_the_api_refuses_with_the_wizards_own_errors(spoc, body):
    from routes_api_v1 import _api_form
    expected = parse_form(_api_form(body))[1]
    assert expected                                             # the wizard refuses it
    resp = spoc['app'].test_client().post('/api/v1/events', headers=spoc['headers'], json=body)
    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'invalid_event' and resp.get_json()['details']['errors'] == expected


def test_from_template_is_a_draft_too_and_unknown_templates_are_refused(spoc):
    with spoc['app'].app_context():
        admin = create_tokens(user_email=spoc['email'], role='SuperAdmin')['access_token']
    headers = {'Authorization': f'Bearer {admin}'}
    client = spoc['app'].test_client()
    resp = client.post('/api/v1/events/from-template', headers=headers, json={
        'template_id': 'conference', 'title': _unique('Summit'), 'date': _future(40), 'venue': 'Grand Hall'})
    assert resp.status_code == 201
    assert resp.get_json()['data']['status'] == 'draft' and resp.get_json()['data']['event_type'] == 'conference'
    bad = client.post('/api/v1/events/from-template', headers=headers, json={
        'template_id': 'no_such_thing', 'title': 'X', 'date': _future(), 'venue': 'Hall'})
    assert bad.status_code == 400 and bad.get_json()['error'] == 'invalid_template'
