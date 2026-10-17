"""
tests/test_checkout_title.py — UPG-96: the checkout script receives the event
title as a JSON literal, so quotes, ampersands or a trailing backslash can't
break the script (and the Pay button with it).
"""
from tests.test_integration_flow import _create_event, _login, _unique, _user

TITLE = 'Rock & "Roll" \\'


def test_the_checkout_script_gets_the_title_as_a_json_literal(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('titlespoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Title'), '2030-06-01', fee=100, team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open', 'title': TITLE})

    payer = flask_app.test_client()
    resp = payer.post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes', 'full_name': 'Ti Tle',
                      'email': f"{_unique('title')}@test.edu", 'phone': '9876543210', 'usn': '1SN20CS012'})
    assert resp.headers['Location'] == f'/payment/checkout/{event_id}'
    page = payer.get(f'/payment/checkout/{event_id}').get_data(as_text=True)
    assert 'description: "Rock \\u0026 \\"Roll\\" \\\\",' in page          # valid JS, exact text
    assert 'description: "Rock &amp;' not in page
