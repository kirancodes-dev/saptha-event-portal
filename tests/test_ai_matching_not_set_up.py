"""
tests/test_ai_matching_not_set_up.py — UPG-109: without any AI provider
(Gemini or Zoho QuickML), judge matching says "AI matching isn't set up; assign
judges manually", answers 503 instead of 500, and saves no plan; the page shows
the notice and disables the button.
"""
import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user

MESSAGE = "AI matching isn't set up; assign judges manually."


@pytest.fixture
def matching(real_app, monkeypatch):
    flask_app, db = real_app
    for name in ('GEMINI_API_KEY', 'ZOHO_AUTH_TOKEN', 'CATALYST_AUTH_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(flask_app.config, 'GEMINI_API_KEY', '')
    spoc, judge = f"{_unique('aispoc')}@test.edu", f"{_unique('aijudge')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, judge, 'Judge')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Match Day'), '2030-06-01', team=False)
    db.collection('events').document(event_id).update({
        'status': 'registration_open', 'staff': [{'name': 'Judy', 'email': judge, 'role': 'Judge'}]})
    owner.post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes', 'full_name': 'Team Lead',
               'email': f"{_unique('ailead')}@test.edu", 'phone': '9876543210', 'usn': '1SN20CS014'})
    return {'app': flask_app, 'db': db, 'owner': owner, 'event_id': event_id}


def test_matching_without_an_ai_provider_says_so_and_saves_nothing(matching):
    resp = matching['owner'].post(f"/ai/match_judges/{matching['event_id']}")
    assert resp.status_code == 503
    assert resp.get_json() == {'status': 'not_configured', 'message': MESSAGE}
    event = matching['db'].collection('events').document(matching['event_id']).get().to_dict()
    assert not event.get('ai_match_plan')


def test_the_matching_page_shows_the_notice_and_disables_the_button(matching):
    page = matching['owner'].get(f"/ai/match_page/{matching['event_id']}").get_data(as_text=True)
    assert MESSAGE.replace("'", '&#39;') in page or MESSAGE in page
    button = page[page.index('id="runBtn"'):page.index('Generate Match Plan')]
    assert 'disabled' in button
    assert "data.status === 'not_configured'" in page   # a 503 shows as a notice, not "Matching failed"
