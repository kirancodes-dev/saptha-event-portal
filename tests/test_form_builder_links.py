"""
tests/test_form_builder_links.py — UPG-68: the form builder needs edit_event on
the event, so its buttons appear only to those who have it. Every builder link
a role is shown opens (200); an assigned coordinator sees none.
"""
import datetime
import re

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user


def _builder_links(html):
    return set(re.findall(r'href="(/forms/builder/[^"]+)"', html))


def test_builder_links_are_shown_only_to_those_who_can_open_them(real_app):
    flask_app, db = real_app
    owner, coord, admin = (f"{_unique(k)}@test.edu" for k in ('fbowner', 'fbcoord', 'fbadmin'))
    _user(db, owner, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    _user(db, admin, 'SuperAdmin')
    day = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    owner_client = _login(flask_app, owner, 'ClubSPOC')
    event_id = _create_event(owner_client, db, _unique('Form Day'), day, team=False)
    db.collection('events').document(event_id).update({
        'status': 'active', 'staff': [{'name': 'C', 'email': coord, 'role': 'EventCoordinator'}]})
    admin_client = flask_app.test_client()
    admin_client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                      'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    coord_client = _login(flask_app, coord, 'EventCoordinator')

    # The assigned coordinator sees the event but no builder button, and the
    # responses page offers no "Edit form"
    dash = coord_client.get('/coordinator/dashboard').get_data(as_text=True)
    assert event_id in dash and not _builder_links(dash)
    assert not _builder_links(coord_client.get(f'/forms/responses/{event_id}').get_data(as_text=True))
    assert coord_client.get(f'/forms/builder/{event_id}').status_code == 403   # the rule the button follows

    # Every builder link the owner and the Super Admin are shown opens
    pages = {owner_client: ['/spoc/dashboard', f'/spoc/event/{event_id}/review', f'/forms/responses/{event_id}'],
             admin_client: ['/coordinator/dashboard', f'/forms/responses/{event_id}']}
    seen = 0
    for client, paths in pages.items():
        for path in paths:
            for link in _builder_links(client.get(path).get_data(as_text=True)):
                if event_id in link:
                    assert client.get(link).status_code == 200, (path, link)
                    seen += 1
    assert seen >= 3
