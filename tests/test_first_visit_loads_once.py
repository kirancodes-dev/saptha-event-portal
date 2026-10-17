"""
tests/test_first_visit_loads_once.py — UPG-72: on a first visit the service
worker takes control of the page without reloading it, so /profile/ loads once.
"""
from tests.headless import live_server, navigations_on_first_visit
from tests.test_integration_flow import _login, _unique, _user


def test_a_first_visit_to_the_profile_navigates_once(real_app):
    flask_app, db = real_app
    email = f"{_unique('firstvisit')}@test.edu"
    _user(db, email, 'Student')
    session_cookie = _login(flask_app, email, 'Student').get_cookie('session')
    with live_server(flask_app) as server:
        navigations, controlled = navigations_on_first_visit(
            f'{server.url}/profile/', cookies=[{'name': 'session', 'value': session_cookie.value, 'url': server.url}])
    assert controlled, 'the service worker should have taken control'
    assert len(navigations) == 1, navigations
    assert navigations[0].endswith('/profile/')
