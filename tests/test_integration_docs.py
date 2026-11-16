"""
tests/test_integration_docs.py — UPG-271: the API reference lists exactly the
endpoints the app serves, the campus-connections guide claims nothing that
isn't built, and the calendar link it describes works.
"""
import datetime
import os
import re

from tests.test_integration_flow import _create_event, _login, _unique, _user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _doc(name):
    with open(os.path.join(ROOT, 'docs', name), encoding='utf-8') as fh:
        return fh.read()


def test_the_api_reference_lists_exactly_the_endpoints_the_app_serves(real_app):
    flask_app, _ = real_app
    served = set()
    for rule in flask_app.url_map.iter_rules():
        if rule.rule.startswith('/api/v1'):
            for method in rule.methods - {'HEAD', 'OPTIONS'}:
                served.add((method, re.sub(r'<(?:\w+:)?(\w+)>', r'<\1>', rule.rule)))
    listed = set(re.findall(r'^\| (GET|POST|PUT|DELETE|PATCH) \| `(/api/v1[^`]*)` \|', _doc('API.md'), re.M))
    assert listed - served == set(), f"documented but not served: {sorted(listed - served)}"
    assert served - listed == set(), f"served but not documented: {sorted(served - listed)}"
    assert len(served) > 40


def test_the_documents_claim_no_integration_that_is_not_built(real_app):
    flask_app, _ = real_app
    api, guide = ' '.join(_doc('API.md').split()), _doc('INTEGRATIONS.md')
    assert 'Outgoing webhooks do not exist' in api and 'does not send webhooks' in guide
    assert 'no API keys' in api and 'Not available: a connector for any particular ERP, LMS' in ' '.join(guide.split())
    # an outgoing webhook would need somewhere to register one: there is no such route
    rules = [r.rule for r in flask_app.url_map.iter_rules()]
    assert not [r for r in rules if 'webhook' in r and r != '/api/v1/webhooks/email' and 'payment' not in r
                and 'razorpay' not in r and 'whatsapp' not in r], rules
    # every address the guide names is served
    for path in ('/admin/users/import_csv', '/calendar/feed.ics', '/auth/google/callback', '/auth/google'):
        assert path in guide and path in rules, path
    # the secrets are named, never given
    for name in ('OAUTH_GOOGLE_CLIENT_ID', 'OAUTH_GOOGLE_CLIENT_SECRET', 'UNIVERSITY_EMAIL_DOMAIN'):
        assert name in guide
    assert not re.search(r'(SECRET|KEY|TOKEN)\s*=\s*\S{8,}', guide)
    assert 'Microsoft sign-in has routes in the code' in guide and 'Treat it as not available' in ' '.join(guide.split())


def test_sign_in_with_google_says_when_it_is_not_set_up(real_app, monkeypatch):
    flask_app, _ = real_app
    for key in ('OAUTH_GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_ID', 'OAUTH_GOOGLE_CLIENT_SECRET'):
        monkeypatch.setitem(flask_app.config, key, '')
    client = flask_app.test_client()
    assert 'Sign in with Google' not in client.get('/login').get_data(as_text=True)
    landed = client.get('/auth/google', follow_redirects=True)
    assert landed.request.path == '/login'
    assert 'Google login is not configured for this instance.' in landed.get_data(as_text=True)
    assert 'Google login is not configured for this instance.' in _doc('INTEGRATIONS.md')
    wrong = client.get('/auth/google/callback?state=made-up&code=x', follow_redirects=True)
    assert 'Invalid OAuth state. Please try again.' in wrong.get_data(as_text=True)


def test_the_calendar_link_gives_a_person_their_own_events_and_nobody_elses(real_app):
    flask_app, db = real_app
    owner, student, other = (f"{_unique('cal' + k)}@test.edu" for k in ('owner', 'stud', 'other'))
    _user(db, owner, 'ClubSPOC')
    _user(db, student, 'Student')
    _user(db, other, 'Student')
    day = (datetime.date.today() + datetime.timedelta(days=12)).isoformat()
    title = _unique('Calendar Feed Talk')
    event_id = _create_event(_login(flask_app, owner, 'ClubSPOC'), db, title, day, team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open'})
    flask_app.test_client().post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Cal Student', 'email': student, 'phone': '9876503333'})
    assert [r for r in db.collection('registrations').where('event_id', '==', event_id).stream()]

    page = _login(flask_app, student, 'Student').get('/participant/my_events').get_data(as_text=True)
    link = re.search(r'href="(/calendar/feed\.ics\?token=[^"]+)"', page).group(1).replace('&amp;', '&')
    anyone = flask_app.test_client()                       # a calendar app has no session
    feed = anyone.get(link)
    assert feed.status_code == 200 and feed.mimetype == 'text/calendar'
    text = feed.get_data(as_text=True)
    assert text.startswith('BEGIN:VCALENDAR') and title in text and day.replace('-', '') in text
    # no token, a made-up token, or naming someone: an empty calendar
    for url in ('/calendar/feed.ics', '/calendar/feed.ics?token=made-up', f'/calendar/feed.ics?user={student}'):
        assert title not in anyone.get(url).get_data(as_text=True)
    assert title not in _login(flask_app, other, 'Student').get('/calendar/feed.ics').get_data(as_text=True)
    # resetting the link stops the old one
    _login(flask_app, student, 'Student').post('/calendar/feed/rotate')
    assert title not in anyone.get(link).get_data(as_text=True)
