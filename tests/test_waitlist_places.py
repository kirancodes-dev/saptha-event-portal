"""
tests/test_waitlist_places.py — UPG-114 on the real database layer: a place on
a waitlist comes from join order and never repeats. After one promotion and one
departure, everyone still waiting sees a distinct place that matches the order
they'll be promoted in: on the status endpoint, the student's waitlist badge,
the organiser's list and the "joined at position #N" message.
"""
import time

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def line(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('plspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Full House'), '2031-07-07', team=False)   # status active

    def student(label):
        email = f"{_unique(label)}@test.edu"
        _user(db, email, 'Student', name=label.title())
        return email, _login(flask_app, email, 'Student')

    def join(client):
        resp = client.post(f'/waitlist/join/{event_id}', json={'name': 'W', 'phone': '9876543210'})
        assert resp.status_code == 201, resp.data
        time.sleep(0.01)
        return resp.get_json()['position']

    def place(client):
        return client.get(f'/waitlist/status/{event_id}').get_json()['position']

    return {'app': flask_app, 'db': db, 'owner': owner, 'event_id': event_id, 'student': student, 'join': join,
            'place': place}


def test_places_follow_join_order_and_never_repeat(line):
    d = line
    people = {k: d['student'](k) for k in ('ana', 'ben', 'cleo', 'dev')}
    assert [d['join'](people[k][1]) for k in ('ana', 'ben', 'cleo')] == [1, 2, 3]

    d['owner'].post(f"/waitlist/promote/{d['event_id']}")                       # Ana promoted
    assert people['ben'][1].delete(f"/waitlist/leave/{d['event_id']}").status_code == 200   # Ben leaves
    joined_at = d['join'](people['dev'][1])                                      # Dev joins last
    assert joined_at == 2                                                        # behind Cleo, the one left

    places = {k: d['place'](people[k][1]) for k in ('cleo', 'dev')}
    assert places == {'cleo': 1, 'dev': 2}
    listed = d['owner'].get(f"/waitlist/list/{d['event_id']}").get_json()['waitlist']
    assert [(w['user_email'], w['position']) for w in listed] == [(people['cleo'][0], 1), (people['dev'][0], 2)]
    badge = people['dev'][1].get('/participant/waitlist_status').get_json()
    assert [b['position'] for b in badge if b['event_id'] == d['event_id']] == [2]

    # Promotion takes them in that order
    from routes_waitlist import auto_promote
    assert auto_promote(d['db'], d['event_id'])['user_email'] == people['cleo'][0]
    assert d['place'](people['dev'][1]) == 1


def test_two_who_joined_in_the_same_instant_still_get_different_places(line):
    d = line
    same = '2026-10-19T10:00:00+00:00'
    for wl_id, email in (('wl-b', 'second@test.edu'), ('wl-a', 'first@test.edu')):
        d['db'].collection('waitlists').document(f"{wl_id}-{d['event_id'][:8]}").set({
            'event_id': d['event_id'], 'user_email': email, 'email': email, 'status': 'waiting', 'joined_at': same,
            'position': 1})                                                      # the old stored value repeats
    from services_waitlist import place_in_line
    assert sorted([place_in_line(d['db'], d['event_id'], 'first@test.edu'),
                   place_in_line(d['db'], d['event_id'], 'second@test.edu')]) == [1, 2]


def test_the_registration_form_says_the_right_place(line):
    d = line
    first, first_client = d['student']('formfirst')
    second, second_client = d['student']('formsecond')
    d['join'](first_client)                 # the JSON join takes only `active` events (UPG-117), so join first
    d['db'].collection('events').document(d['event_id']).update({   # one seat, and it's taken
        'status': 'registration_open', 'limits': {'max_participants': 1}, 'registration_count': 1})
    d['db'].collection('waitlists').document(_unique('WL')).set({
        'event_id': d['event_id'], 'user_email': 'gone@test.edu', 'email': 'gone@test.edu', 'status': 'promoted',
        'joined_at': '2026-01-01T00:00:00+00:00', 'position': 1})              # promoted long ago: doesn't count
    resp = second_client.post(f"/forms/submit/{d['event_id']}", data={
        'privacy_consent': 'yes', 'full_name': 'Form Second', 'email': second, 'phone': '9876543210',
        'usn': '1SN20CS990'}, follow_redirects=True)
    assert "joined the waitlist at position #2" in resp.get_data(as_text=True)


@pytest.mark.parametrize('status, joins', [('registration_open', True), ('active', True), ('published', False),
                                          ('registration_closed', False), ('completed', False), ('cancelled', False)])
def test_upg117_the_json_join_follows_the_forms_rule(line, status, joins):
    d = line
    d['db'].collection('events').document(d['event_id']).update({'status': status})
    _, client = d['student'](f'json{status}')
    resp = client.post(f"/waitlist/join/{d['event_id']}", json={})
    if joins:
        assert resp.status_code == 201, resp.data
    else:
        assert resp.status_code == 400 and resp.get_json()['error'] == 'Registration is closed for this event.'
