"""
tests/test_reach.py — UPG-146 on the real database layer: campus-only or open
events, the public open-events page, a student from another college
registering, checking in and getting a certificate, share cards with valid
schema.org data, the listing kit, and the "Powered by SapthaEvent" switch.
"""
import datetime
import json
import re

import pytest
from werkzeug.security import generate_password_hash

import services_certificates as certs
import services_reach as reach
from tests.test_certificate_types import _signature
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user


@pytest.fixture
def site(real_app, monkeypatch):
    import utils_email
    flask_app, db = real_app
    mail = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k:
                        mail.append({'to': to, 'subject': subject, 'html': html}) or True)
    email = {k: f"{_unique('reach' + k)}@test.edu" for k in ('owner', 'other', 'admin')}
    _user(db, email['owner'], 'ClubSPOC')
    _user(db, email['other'], 'ClubSPOC')
    _user(db, email['admin'], 'SuperAdmin')
    admin = flask_app.test_client()
    admin.post('/login', data={'role': 'SuperAdmin', 'email': email['admin'], 'password': PASSWORD,
                               'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    owner = _login(flask_app, email['owner'], 'ClubSPOC')
    tag = _unique('Reach')

    def event(title, days=20, **fields):
        day = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
        event_id = _create_event(owner, db, f'{tag} {title}', day, team=False)
        db.collection('events').document(event_id).update(dict({'status': 'registration_open'}, **fields))
        return event_id
    return {'app': flask_app, 'db': db, 'email': email, 'owner': owner, 'admin': admin, 'mail': mail, 'tag': tag,
            'other': _login(flask_app, email['other'], 'ClubSPOC'), 'event': event, 'visitor': flask_app.test_client()}


def _ev(d, event_id):
    return d['db'].collection('events').document(event_id).get().to_dict()


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_organisers_open_events_and_the_public_page_lists_them(site):
    d = site
    robotics = d['event']('Robotics Open', category='Technical', event_type='competition')
    music = d['event']('Music Open', days=40, category='Cultural', event_type='show')
    campus = d['event']('Campus Talk')
    past = d['event']('Past Open', days=-5)
    draft = d['event']('Draft Open', status='draft')
    assert d['other'].post(f'/reach/events/{robotics}/audience', data={'audience': 'open'}).status_code == 403
    for event_id in (robotics, music, past, draft):
        d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'open'})
    assert _ev(d, robotics)['audience'] == 'open' and 'external' in _ev(d, robotics)['allowed_participants']

    page = d['visitor'].get(f"/open-events?q={d['tag']}").get_data(as_text=True)
    assert 'Robotics Open' in page and 'Music Open' in page
    assert 'Campus Talk' not in page and 'Past Open' not in page and 'Draft Open' not in page
    narrowed = d['visitor'].get(f"/open-events?q={d['tag']}&category=Cultural").get_data(as_text=True)
    assert 'Music Open' in narrowed and 'Robotics Open' not in narrowed
    by_type = d['visitor'].get(f"/open-events?q={d['tag']}&event_type=competition").get_data(as_text=True)
    assert 'Robotics Open' in by_type and 'Music Open' not in by_type
    later = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    assert 'Robotics Open' not in d['visitor'].get(f"/open-events?q={d['tag']}&from={later}").get_data(as_text=True)

    d['owner'].post(f'/reach/events/{robotics}/audience', data={'audience': 'campus'})
    assert _ev(d, robotics)['audience'] == 'campus' and 'external' not in _ev(d, robotics)['allowed_participants']
    assert campus


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_a_student_from_another_college_registers_checks_in_and_gets_a_certificate(site, monkeypatch):
    import services_signatories
    d = site
    monkeypatch.setattr(certs, 'render', lambda event, cert: b'%PDF-1.4 ' + cert['number'].encode())
    event_id = d['event']('Inter-college Hack')
    campus_only = d['event']('Campus Hack')
    d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'open'})
    guest = f"{_unique('guest')}@othercollege.edu"
    form = {'privacy_consent': 'yes', 'full_name': 'Gita Guest', 'email': guest, 'phone': '9876501111',
            'participant_type': 'external', 'designation': 'Student', 'institution': 'RV College of Engineering'}
    refused = d['visitor'].post(f'/forms/submit/{campus_only}', data=form, follow_redirects=True)
    assert 'This event is for students only' in refused.get_data(as_text=True), refused.get_data(as_text=True)[-1500:]
    assert not list(d['db'].collection('registrations').where('event_id', '==', campus_only).stream())

    d['app'].test_client().post(f'/forms/submit/{event_id}', data=form)
    [reg_doc] = list(d['db'].collection('registrations').where('event_id', '==', event_id).stream())
    reg = reg_doc.to_dict()
    assert reg['participant_type'] == 'external' and reg['institution'] == 'RV College of Engineering'
    d['db'].collection('users').document(guest).update({'password': generate_password_hash(PASSWORD), 'role': 'Student'})
    ticket = _login(d['app'], guest, 'Student').get(f'/ticket/{reg_doc.id}')
    assert ticket.status_code == 200, (ticket.headers.get('Location'), reg.get('status')) and 'Gita Guest' in ticket.get_data(as_text=True)

    d['db'].collection('events').document(event_id).update({'status': 'active'})
    with d['app'].app_context():
        from routes_ticket import generate_ticket_token
        token = generate_ticket_token(reg_doc.id, event_id, 'Gita Guest')
    assert d['owner'].post(f'/ticket/verify/{token}').status_code == 200
    assert d['db'].collection('registrations').document(reg_doc.id).get().to_dict()['attendance'] == 'Present'

    d['db'].collection('events').document(event_id).update({'status': 'completed'})
    services_signatories.add(d['db'], event_id, name='Dr. A. Kumar', title='Principal', image=_signature(),
                             actor=d['email']['owner'])
    certs.issue_event(d['db'], event_id, d['email']['owner'], only=['participation'])
    [cert] = [c for c in certs.for_event(event_id) if c['email'] == guest]
    assert cert['data']['institution'] == 'RV College of Engineering'


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def _json_ld(html):
    return json.loads(re.search(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S).group(1))


def test_event_pages_carry_share_cards_and_valid_schema_org_data(site):
    d = site
    event_id = d['event']('Quotes "and"\nLines', venue='', room_name='', event_mode='offline')
    html = d['visitor'].get(f'/event/{event_id}').get_data(as_text=True)
    for tag in ('og:title', 'og:description', 'og:url', 'og:image', 'twitter:card', 'twitter:image'):
        assert f'"{tag}"' in html, tag
    data = _json_ld(html)
    assert data['@type'] == 'Event' and data['name'] == f"{d['tag']} Quotes \"and\"\nLines".replace('\n', '\n')
    assert data['location']['name'] == 'Venue to be announced' and data['startDate'].startswith(_ev(d, event_id)['date'])
    assert 'og:description" content="' + _ev(d, event_id)['date'] + ' · Venue to be announced' in html
    assert 'api.whatsapp.com/send?text=' in html or 'wa.me/?text=' in html
    hall = d['event']('Hall Event', venue='Seminar Hall A')
    assert _json_ld(d['visitor'].get(f'/event/{hall}').get_data(as_text=True))['location']['name'] == 'Seminar Hall A'


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_listing_kit_is_for_the_events_editors(site):
    d = site
    event_id = d['event']('Listed Fest', description='A two-day robotics fest with workshops and a final.')
    page = d['owner'].get(f'/reach/events/{event_id}/listing-kit').get_data(as_text=True)
    for name in ('Unstop', 'KnowAFest', 'Festooo'):
        assert name in page
    assert f'/event/{event_id}' in page and 'A two-day robotics fest' in page
    assert 'never posts to these sites' in page
    assert d['other'].get(f'/reach/events/{event_id}/listing-kit').status_code == 403


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_the_powered_by_line_and_its_switch(site):
    import utils_email
    d = site
    reach._cache['at'] = 0
    assert 'Powered by SapthaEvent' in d['visitor'].get('/open-events').get_data(as_text=True)
    assert 'Powered by SapthaEvent' in utils_email._html_wrapper('<p>x</p>')
    assert d['owner'].post('/reach/settings', data={'powered_by': 'off'}).status_code == 403
    d['admin'].post('/reach/settings', data={'powered_by': 'off'})
    try:
        assert 'Powered by SapthaEvent' not in d['visitor'].get('/open-events').get_data(as_text=True)
        assert 'Powered by SapthaEvent' not in utils_email._html_wrapper('<p>x</p>')
        assert any(a.to_dict().get('action') == 'POWERED_BY_LINE' and str(a.to_dict().get('details')).endswith(': off')
                   for a in d['db'].collection('audit_log').stream())
    finally:
        d['admin'].post('/reach/settings', data={'powered_by': 'on'})
    assert 'Powered by SapthaEvent' in d['visitor'].get('/open-events').get_data(as_text=True)
