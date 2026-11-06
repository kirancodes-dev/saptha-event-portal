"""
tests/test_push_notifications.py — UPG-157: browser push, switched on. One
subscription per browser for the logged-in user; change notices (and the
other notices) go to the event's subscribers once; a 410 removes the
subscription; with no VAPID keys there's no prompt and nothing is sent.
The push service is replaced by a recorder; nothing leaves the machine.
"""
import pytest

import services_push
from tests.test_integration_flow import _create_event, _login, _unique, _user


def _sub(name):
    return {'endpoint': f'https://push.example.test/{name}-{_unique("ep")}',
            'keys': {'p256dh': 'BPkey-' + name, 'auth': 'auth-' + name}}


@pytest.fixture
def pushes(monkeypatch):
    sent = []
    monkeypatch.setenv('VAPID_PUBLIC_KEY', 'BPublicKeyForPytest')
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'private-key-for-pytest')
    monkeypatch.setattr(services_push, '_webpush', lambda info, payload: sent.append((info['endpoint'], payload)))
    return sent


def _rows(email):
    return services_push.subscriptions(email)


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_subscribing_keeps_one_subscription_per_browser(real_app, pushes):
    flask_app, db = real_app
    email = f"{_unique('pusher')}@test.edu"
    _user(db, email, 'Student')
    client = _login(flask_app, email, 'Student')
    phone, laptop = _sub('phone'), _sub('laptop')
    for _ in range(2):                                    # the same browser twice
        assert client.post('/push/subscribe', json=phone).status_code == 200
    assert [r['endpoint'] for r in _rows(email)] == [phone['endpoint']]
    assert client.post('/push/subscribe', json=laptop).status_code == 200
    assert sorted(r['endpoint'] for r in _rows(email)) == sorted([phone['endpoint'], laptop['endpoint']])

    # A browser someone else logs in on becomes theirs, not both people's
    other = f"{_unique('other')}@test.edu"
    _user(db, other, 'Student')
    assert _login(flask_app, other, 'Student').post('/push/subscribe', json=laptop).status_code == 200
    assert [r['endpoint'] for r in _rows(email)] == [phone['endpoint']]
    assert [r['endpoint'] for r in _rows(other)] == [laptop['endpoint']]

    # Turning it off on one browser leaves the other
    assert client.post('/push/unsubscribe', json={'endpoint': phone['endpoint']}).status_code == 200
    assert _rows(email) == []


def test_logged_out_and_malformed_subscriptions_are_refused(real_app, pushes):
    flask_app, db = real_app
    anon = flask_app.test_client()
    assert anon.post('/push/subscribe', json=_sub('anon')).status_code == 401
    email = f"{_unique('bad')}@test.edu"
    _user(db, email, 'Student')
    client = _login(flask_app, email, 'Student')
    assert client.post('/push/subscribe', json={'endpoint': 'http://insecure.test/x', 'keys': {}}).status_code == 400
    assert _rows(email) == []


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_a_change_notice_is_pushed_once_to_each_subscriber_of_the_event(real_app, pushes):
    flask_app, db = real_app
    owner = f"{_unique('pushspoc')}@test.edu"
    _user(db, owner, 'ClubSPOC')
    spoc = _login(flask_app, owner, 'ClubSPOC')
    title = _unique('Push Night')
    event_id = _create_event(spoc, db, title, '2030-07-01', team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open'})

    registrants = [f"{_unique(n)}@test.edu" for n in ('ana', 'ben')]
    for email in registrants:
        assert flask_app.test_client().post(f'/forms/submit/{event_id}', data={
            'privacy_consent': 'yes', 'full_name': 'Pu Sh', 'email': email, 'phone': '9876543210',
            'usn': '1SN22CS001'}).status_code == 302
    outsider = f"{_unique('outsider')}@test.edu"
    endpoints = {}
    for email in registrants + [outsider]:
        sub = _sub(email.split('@')[0])
        assert services_push.subscribe(email, sub)
        endpoints[email] = sub['endpoint']

    for _ in range(2):                                    # the same change saved twice
        assert spoc.post(f'/spoc/edit_event/{event_id}', data={'venue': 'Hall B', 'title': title}).status_code == 302
    got = sorted(endpoint for endpoint, _ in pushes)
    assert got == sorted(endpoints[e] for e in registrants)
    assert all(title in payload and 'Hall B' in payload for _, payload in pushes)

    # Cancelling the event pushes once more to each, and to nobody else
    pushes.clear()
    for _ in range(2):
        spoc.post(f'/spoc/event/{event_id}/transition', data={'target_state': 'cancelled'})
    assert sorted(endpoint for endpoint, _ in pushes) == sorted(endpoints[e] for e in registrants)


def test_published_results_push_once_to_each_registrant(real_app, pushes):
    flask_app, db = real_app
    owner = f"{_unique('resspoc')}@test.edu"
    _user(db, owner, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, owner, 'ClubSPOC'), db, _unique('Results'), '2030-07-02', team=False)
    email = f"{_unique('res')}@test.edu"
    db.collection('registrations').document(_unique('REG')).set(
        {'event_id': event_id, 'lead_email': email, 'lead_name': 'R', 'members': [], 'status': 'Confirmed'})
    services_push.subscribe(email, _sub('res'))
    for _ in range(2):
        services_push.push_to_registrants(db, event_id, 'results', 'Results are out: X', 'See where you placed.')
    assert len(pushes) == 1


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_a_410_from_the_push_service_deletes_the_subscription(real_app, monkeypatch):
    monkeypatch.setenv('VAPID_PUBLIC_KEY', 'BPublicKeyForPytest')
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'private-key-for-pytest')
    email = f"{_unique('gone')}@test.edu"
    dead, alive = _sub('dead'), _sub('alive')
    services_push.subscribe(email, dead)
    services_push.subscribe(email, alive)

    class Gone(Exception):
        class response:
            status_code = 410

    def webpush(info, payload):
        if info['endpoint'] == dead['endpoint']:
            raise Gone('expired')

    monkeypatch.setattr(services_push, '_webpush', webpush)
    assert services_push.send(email, 'T', 'B') == 1
    assert [r['endpoint'] for r in _rows(email)] == [alive['endpoint']]


def test_another_failure_keeps_the_subscription(real_app, monkeypatch):
    monkeypatch.setenv('VAPID_PUBLIC_KEY', 'BPublicKeyForPytest')
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'private-key-for-pytest')
    email = f"{_unique('flaky')}@test.edu"
    services_push.subscribe(email, _sub('flaky'))

    def webpush(info, payload):
        raise ConnectionError('timeout')

    monkeypatch.setattr(services_push, '_webpush', webpush)
    assert services_push.send(email, 'T', 'B') == 0
    assert len(_rows(email)) == 1


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_without_vapid_keys_no_prompt_and_nothing_is_sent(real_app, monkeypatch):
    flask_app, db = real_app
    sent = []
    monkeypatch.setattr(services_push, '_webpush', lambda info, payload: sent.append(info))
    email = f"{_unique('nokeys')}@test.edu"
    _user(db, email, 'Student')
    client = _login(flask_app, email, 'Student')
    assert 'data-push-optin' not in client.get('/profile/').get_data(as_text=True)
    assert client.get('/push/vapid_public_key').get_json() == {'key': ''}
    assert client.post('/push/subscribe', json=_sub('x')).status_code == 404
    services_push.subscribe(email, _sub('stored-earlier'))
    assert services_push.send(email, 'T', 'B') == 0
    assert services_push.push_to_registrants(db, 'any', 'results', 'T', 'B') == 0
    assert sent == []

    # With the keys the profile page offers it (the browser asks only on the button)
    monkeypatch.setenv('VAPID_PUBLIC_KEY', 'BPublicKeyForPytest')
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'private-key-for-pytest')
    page = client.get('/profile/').get_data(as_text=True)
    assert 'data-push-optin' in page and 'data-key="BPublicKeyForPytest"' in page
    assert 'Notification.requestPermission' not in page
