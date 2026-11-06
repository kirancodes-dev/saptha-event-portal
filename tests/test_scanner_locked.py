"""
tests/test_scanner_locked.py — UPG-67: the coordinator scanner for an event on
another day (locked, no camera view) runs its script without an error, and
today's open scanner still starts the camera.
"""
import datetime

from tests.headless import page_problems
from tests.test_integration_flow import _create_event, _login, _unique, _user


def _scanner_html(real_app, day):
    flask_app, db = real_app
    owner, coord = f"{_unique('scanowner')}@test.edu", f"{_unique('scancoord')}@test.edu"
    _user(db, owner, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    event_id = _create_event(_login(flask_app, owner, 'ClubSPOC'), db, _unique('Scan Day'), day, team=False)
    db.collection('events').document(event_id).update({
        'status': 'registration_open', 'staff': [{'name': 'C', 'email': coord, 'role': 'EventCoordinator'}]})
    resp = _login(flask_app, coord, 'EventCoordinator').get(f'/coordinator/scan/{event_id}')
    assert resp.status_code == 200
    return event_id, resp.get_data(as_text=True)


def test_a_locked_scanner_logs_no_page_error(real_app):
    other_day = (datetime.date.today() + datetime.timedelta(days=9)).isoformat()
    event_id, html = _scanner_html(real_app, other_day)
    assert 'id="cam-placeholder"' not in html                 # locked: no camera view
    errors, _, _ = page_problems(html, f'/coordinator/scan/{event_id}')
    assert errors == []


def test_todays_scanner_still_has_its_camera_view(real_app):
    _, html = _scanner_html(real_app, datetime.date.today().isoformat())
    assert 'id="cam-placeholder"' in html and "if (!document.getElementById('cam-placeholder')) return;" in html
