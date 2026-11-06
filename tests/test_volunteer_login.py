"""
tests/test_volunteer_login.py — UPG-120: a volunteer can log in. Their account's
role is "Volunteer", which the login form didn't offer, so every attempt failed
the role check; the form now has the option, and a volunteer lands on the
scanner page, which lists and opens only the events they're staff on.
"""
import datetime

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user


def test_the_login_form_offers_the_five_roles_the_owner_chose(real_app):
    # UPG-120 added "Volunteer" to the menu; the owner took it off again for
    # now (UPG-204, 2026-11-06). A volunteer's login still works when the role
    # is posted, which the next test checks.
    flask_app, _ = real_app
    page = flask_app.test_client().get('/login').get_data(as_text=True)
    for role in ('Student', 'EventCoordinator', 'ClubSPOC', 'Judge', 'SuperAdmin'):
        assert f'<option value="{role}">' in page, role
    assert '<option value="Volunteer">' not in page


def test_a_volunteer_logs_in_and_lands_on_the_scanner(real_app):
    flask_app, db = real_app
    email = f"{_unique('vol')}@test.edu"
    _user(db, email, 'Volunteer', name='Val Volunteer')
    client = flask_app.test_client()
    resp = client.post('/login', data={'role': 'Volunteer', 'email': email, 'password': PASSWORD})
    assert resp.status_code == 302 and resp.headers['Location'] == '/coordinator/scanner'
    with client.session_transaction() as sess:
        assert sess.get('user_id') == email and sess.get('role') == 'Volunteer'
    assert client.get('/coordinator/scanner').status_code == 200


def test_a_volunteer_cant_log_in_as_another_role(real_app):
    flask_app, db = real_app
    email = f"{_unique('vol2')}@test.edu"
    _user(db, email, 'Volunteer')
    resp = flask_app.test_client().post('/login', data={'role': 'EventCoordinator', 'email': email, 'password': PASSWORD})
    assert resp.headers['Location'] == '/login'


def test_a_volunteer_scans_only_the_events_they_are_staff_on(real_app):
    flask_app, db = real_app
    vol, spoc = f"{_unique('vol3')}@test.edu", f"{_unique('volspoc')}@test.edu"
    _user(db, vol, 'Volunteer')
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    today = datetime.date.today().isoformat()
    mine = _create_event(owner, db, _unique('Volunteer Day'), today, team=False)
    other = _create_event(owner, db, _unique('Not Mine'), today, team=False)
    for event_id, staff in ((mine, [{'name': 'Val', 'email': vol, 'role': 'Volunteer'}]), (other, [])):
        db.collection('events').document(event_id).update({'status': 'in_progress', 'staff': staff})
    client = _login(flask_app, vol, 'Volunteer')
    listing = client.get('/coordinator/scanner').get_data(as_text=True)
    titles = {e: db.collection('events').document(e).get().to_dict()['title'] for e in (mine, other)}
    assert titles[mine] in listing and titles[other] not in listing
    assert client.get(f'/coordinator/scan/{mine}').status_code == 200
    refused = client.get(f'/coordinator/scan/{other}')
    assert refused.status_code == 302 and refused.headers['Location'] == '/coordinator/scanner'
