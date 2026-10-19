"""
tests/test_certificate_api.py — UPG-137 on the real database layer: API v1's
issue and verify endpoints use the same `certificates` records as the web, so
the web's /verify finds a certificate issued through the API (and the API
verifies one issued on the web). Older API certificate IDs still verify.
"""
import pytest

import services_certificates as certs
from auth_jwt import create_tokens
from tests.test_certificate_types import _signature
from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def api(real_app, monkeypatch):
    import services_signatories
    flask_app, db = real_app
    monkeypatch.setenv('TASK_INLINE_TIMEOUT', '120')
    owner, other = f"{_unique('apiowner')}@test.edu", f"{_unique('apiother')}@test.edu"
    _user(db, owner, 'ClubSPOC')
    _user(db, other, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, owner, 'ClubSPOC'), db, _unique('API Event'), '2030-09-09', team=False)
    db.collection('events').document(event_id).update({'status': 'completed', 'staff': []})
    for name in ('Api Anil', 'Api Bina'):
        db.collection('registrations').document(_unique('REG')).set({
            'event_id': event_id, 'lead_name': name, 'lead_email': f"{_unique('api')}@test.edu",
            'status': 'Confirmed', 'attendance': 'Present'})
    with flask_app.app_context():
        headers = {k: {'Authorization': f"Bearer {create_tokens(user_email=e, role='ClubSPOC')['access_token']}"}
                   for k, e in (('owner', owner), ('other', other))}

    def sign():
        services_signatories.add(db, event_id, name='Dr. A. Kumar', title='Principal', image=_signature(), actor=owner)
    return {'client': flask_app.test_client(), 'db': db, 'event_id': event_id, 'headers': headers, 'sign': sign}


def test_the_api_issues_into_the_same_store_and_the_web_verifies_it(api):
    d = api
    url = f"/api/v1/events/{d['event_id']}/issue-certificates"
    assert d['client'].post(url, json={}, headers=d['headers']['other']).status_code == 403
    refused = d['client'].post(url, json={}, headers=d['headers']['owner'])
    assert refused.status_code == 409 and 'signatory' in refused.get_json()['message']
    assert certs.for_event(d['event_id']) == []
    d['sign']()
    assert d['client'].post(url, json={'category': 'nonsense'}, headers=d['headers']['owner']).status_code == 400

    resp = d['client'].post(url, json={'category': 'participation'}, headers=d['headers']['owner'])
    assert resp.status_code == 202
    body = resp.get_json()['data']
    assert body['status'] == 'done' and body['issued'] == 2 and len(body['certificates']) == 2
    stored = {c['number']: c for c in certs.for_event(d['event_id'])}
    assert {c['number'] for c in body['certificates']} == set(stored)        # the web's own records
    for c in body['certificates']:
        page = d['client'].get(f"/verify/{c['number']}").get_data(as_text=True)
        assert 'Valid certificate' in page and c['name'] in page
        api_view = d['client'].get(f"/api/v1/certificates/{c['number']}").get_json()['data']
        assert api_view['verified'] is True and api_view['certificate']['name'] == c['name']

    again = d['client'].post(url, json={'category': 'participation'}, headers=d['headers']['owner']).get_json()['data']
    assert again['issued'] == 0 and len(certs.for_event(d['event_id'])) == 2          # never twice
    assert d['client'].get('/api/v1/certificates/SE-AAAA-BBBB-CCCC-D').status_code == 404


def test_a_web_issued_certificate_verifies_through_the_api(api):
    d = api
    d['sign']()
    certs.issue_event(d['db'], d['event_id'], '', only=['participation'])
    number = certs.for_event(d['event_id'])[0]['number']
    certs.update(certs.for_event(d['event_id'])[0]['id'], status='revoked')
    data = d['client'].get(f'/api/v1/certificates/{number}').get_json()['data']
    assert data['verified'] is False and data['certificate']['state'] == 'revoked'
