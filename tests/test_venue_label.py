"""
tests/test_venue_label.py — UPG-111: an event with no venue shows "Venue to be
announced" (or "Online" for an online event) everywhere, never an invented
place such as "SNPSU Campus": the scanner list, the calendar, the event page,
the student's dashboard and the coordinators' briefing email, through one
helper (utils.venue_label).
"""
import datetime
import os
import subprocess

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user
from utils import venue_label

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
INVENTED = ('SNPSU Campus', 'Main Campus')


@pytest.mark.parametrize('event, label', [
    ({'room_name': 'Seminar Hall 2', 'venue': 'Old text'}, 'Seminar Hall 2'),
    ({'venue': 'Main Auditorium'}, 'Main Auditorium'),
    ({'venue': '', 'event_mode': 'online'}, 'Online'),
    ({'event_mode': 'hybrid'}, 'Venue to be announced'),
    ({'venue': '   '}, 'Venue to be announced'),
    ({}, 'Venue to be announced'),
    (None, 'Venue to be announced'),
])
def test_the_label_never_invents_a_place(event, label):
    assert venue_label(event) == label


def test_no_app_code_or_page_falls_back_to_an_invented_place():
    # The certificate preview's wording is deferred with certificates
    hits = subprocess.run(['git', 'grep', '-n', '-E', "'SNPSU Campus'|'Main Campus'|get\\('venue', ?'SNPSU'|or 'Campus'",
                           '--', '*.py', '*.html', ':!tests/', ':!seeds/', ':!db_adapter.py',
                           ':!templates/public/certificate_preview_embed.html', ':!routes_verification.py'],
                          cwd=ROOT, capture_output=True, text=True).stdout.strip()
    assert hits == ''


@pytest.fixture
def placeless(real_app, monkeypatch):
    flask_app, db = real_app
    spoc, coord, student = (f"{_unique(k)}@test.edu" for k in ('vlspoc', 'vlcoord', 'vlstudent'))
    _user(db, spoc, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    _user(db, student, 'Student')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    tomorrow = (datetime.datetime.now(IST).date() + datetime.timedelta(days=1)).isoformat()
    staff = [{'name': 'Cora', 'email': coord, 'role': 'EventCoordinator'}]

    def event(mode='offline'):
        event_id = _create_event(owner, db, _unique('Placeless'), tomorrow, team=False)
        db.collection('events').document(event_id).update({'venue': '', 'event_mode': mode, 'staff': staff,
                                                           'status': 'registration_open'})
        return event_id
    return {'app': flask_app, 'db': db, 'event': event, 'coord': coord, 'student': student,
            'monkeypatch': monkeypatch}


def _shows(html, expected):
    return expected in html and not any(place in html for place in INVENTED)


def test_pages_say_venue_to_be_announced(placeless):
    d = placeless
    event_id = d['event']()
    student = _login(d['app'], d['student'], 'Student')
    student.post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes', 'full_name': 'Vee', 'email': d['student'],
                                                    'phone': '9876543210', 'usn': '1SN20CS444'})
    pages = {
        'scanner list': _login(d['app'], d['coord'], 'EventCoordinator').get('/coordinator/scanner'),
        'calendar': d['app'].test_client().get('/calendar'),
        'event page': d['app'].test_client().get(f'/event/{event_id}'),
        'student dashboard': student.get('/participant/dashboard'),
    }
    title = d['db'].collection('events').document(event_id).get().to_dict()['title']
    for name, resp in pages.items():
        assert resp.status_code == 200, name
        html = resp.get_data(as_text=True)
        if name == 'calendar':       # lists every event, some with a real venue of their own: look at this one
            at = html.index(title)
            html = html[at:at + 2500]
        assert _shows(html, 'Venue to be announced'), name
    feed = [e for e in d['app'].test_client().get('/api/calendar').get_json() if e['id'] == event_id]
    assert feed and feed[0]['venue'] == 'Venue to be announced'


def test_an_online_event_says_online(placeless):
    d = placeless
    event_id = d['event']('online')
    page = d['app'].test_client().get(f'/event/{event_id}').get_data(as_text=True)
    assert 'Online' in page and not any(place in page for place in INVENTED)
    [entry] = [e for e in d['app'].test_client().get('/api/calendar').get_json() if e['id'] == event_id]
    assert entry['venue'] == 'Online'


@pytest.mark.parametrize('mode, expected', [('offline', 'Venue to be announced'), ('online', 'Online')])
def test_the_briefing_email_never_invents_a_venue(placeless, mode, expected):
    d = placeless
    import tasks.email_tasks as email_tasks
    sent = []

    class Capture:
        def delay(self, **kw):
            sent.append(kw)
    d['monkeypatch'].setattr(email_tasks, 'send_generic_email_task', Capture())
    d['event'](mode)
    from tasks.scheduled_tasks import send_24h_reminders
    with d['app'].app_context():
        send_24h_reminders.apply()
    briefings = [m for m in sent if m['to_email'] == d['coord']]
    assert briefings
    for mail in briefings:
        assert _shows(mail.get('body_html') or '', expected) and expected in mail['body_text']
