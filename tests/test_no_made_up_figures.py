"""
tests/test_no_made_up_figures.py — UPG-65 on the real database layer: no page
shows a figure or feature that no data or backend supports. Made-up figures are
removed, the simulated demo pages are hidden unless DEMO_PAGES_ENABLED, and
contact details come from SUPPORT_EMAIL.
"""
import glob
import re

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user

BANNED = ('99.9%', '500K+', 'Verified-2026')


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_home_page_and_platform_pages_show_no_invented_figures(real_app):
    flask_app, _ = real_app
    client = flask_app.test_client()
    home = client.get('/').get_data(as_text=True)
    assert 'data-count' not in home
    assert not re.search(r'\b\d+(\.\d+)?\s?[KkM]\+|\b\d+\+\s+(colleges|universities|students|events)', home)
    for path in ('/platform', '/pricing', '/features', '/live/streams', '/live/reels'):
        assert client.get(path).status_code == 404, path          # hidden by default

    flask_app.config['DEMO_PAGES_ENABLED'] = True
    try:
        landing = client.get('/platform').get_data(as_text=True)
        for invented in BANNED + ('10K+', '50+', '50 universities', 'GDPR Compliant'):
            assert invented not in landing, invented
    finally:
        flask_app.config['DEMO_PAGES_ENABLED'] = False


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_no_template_has_a_hard_coded_count_or_invented_figure():
    for path in glob.glob('templates/**/*.html', recursive=True):
        with open(path, encoding='utf-8') as fh:
            html = fh.read()
        assert not re.search(r'data-count="\d', html), path
        for invented in BANNED:
            assert invented not in html, (path, invented)


# ── Criterion 3 (chatbot; the certificate pages are deferred) ───────────────

@pytest.mark.parametrize('support', ['help@college.example', ''])
def test_the_chatbot_takes_its_contact_from_support_email(real_app, monkeypatch, support):
    flask_app, _ = real_app
    monkeypatch.setenv('SUPPORT_EMAIL', support)
    reply = flask_app.test_client().post('/chatbot/ask', json={'message': 'When is the next hackathon?'}).get_json()['reply']
    assert 'support@snpsu.edu.in' not in reply and 'help@sapthagiri.edu' not in reply and 'Zoho Zia' not in reply
    assert (support in reply) if support else ('write to' not in reply)
    with open('chatbot_routes.py', encoding='utf-8') as fh:
        assert 'help@sapthagiri.edu' not in fh.read()


# ── The rest of the item ────────────────────────────────────────────────────

def test_a_new_student_starts_with_zero_points(real_app):
    flask_app, db = real_app
    email = f"{_unique('zero')}@test.edu"
    _user(db, email, 'Student')
    page = _login(flask_app, email, 'Student').get('/participant/dashboard').get_data(as_text=True)
    assert re.search(r'class="score-metric-value">0<', page)


def test_an_event_without_venue_or_limit_shows_no_invented_values(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('defspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Plain'), '2030-06-01', team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open', 'venue': ''})
    event = db.collection('events').document(event_id).get().to_dict()
    event.pop('limits', None)
    db.collection('events').document(event_id).set(event, merge=False)   # no seat limit stored
    page = flask_app.test_client().get(f'/event/{event_id}').get_data(as_text=True)
    assert 'SNPSU Campus' not in page and 'of 200 seats' not in page


def test_without_zoho_the_ai_helpers_simulate_nothing(monkeypatch):
    import zoho_zia
    monkeypatch.setattr(zoho_zia, 'call_quickml_llm', lambda **k: None)   # not configured
    assert zoho_zia.ask_zia_chatbot('any events?', 'SECRET STUDENT CONTEXT') == ''
    with pytest.raises(RuntimeError):
        zoho_zia.match_teams_zia([{'name': 'J', 'email': 'j@x'}], [{'id': 'r1', 'team_name': 'T'}])


def test_the_status_page_and_nfc_terminal_simulate_nothing():
    with open('templates/spoc/nfc_scanner.html', encoding='utf-8') as fh:
        nfc = fh.read()
    assert '1200)' not in nfc and 'emulator' not in nfc.lower() and 'simulate RFID' not in nfc
    with open('templates/compliance/sla.html', encoding='utf-8') as fh:
        sla = fh.read()
    assert 'uptime-tick' not in sla and 'All Systems Operational' not in sla
