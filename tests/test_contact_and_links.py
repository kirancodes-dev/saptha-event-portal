"""
tests/test_contact_and_links.py — UPG-42: the privacy, terms and payment-failed
pages give SUPPORT_EMAIL as the contact (no address at all when it's unset),
and the old team mail account appears nowhere. UPG-46: the coordinators'
day-before briefing and the SPOC's low-registration alert link only to
BASE_URL, never to a fixed domain.
"""
import datetime
import subprocess
import os
import re

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD_ACCOUNT = 'sapthhack@gmail.com'
PAGES = ('/privacy', '/terms', '/payment/failed')


# ── UPG-42 ──────────────────────────────────────────────────────────────────

def test_the_contact_pages_show_support_email(real_app, monkeypatch):
    flask_app, _ = real_app
    monkeypatch.setenv('SUPPORT_EMAIL', 'events@university.example')
    client = flask_app.test_client()
    for path in PAGES:
        resp = client.get(path)
        assert resp.status_code == 200, path
        html = resp.get_data(as_text=True)
        assert 'href="mailto:events@university.example"' in html, path
        assert OLD_ACCOUNT not in html


def test_without_support_email_the_pages_show_no_address(real_app, monkeypatch):
    flask_app, _ = real_app
    monkeypatch.delenv('SUPPORT_EMAIL', raising=False)
    client = flask_app.test_client()
    for path in PAGES:
        resp = client.get(path)
        assert resp.status_code == 200 and 'mailto:' not in resp.get_data(as_text=True), path


def test_the_old_account_is_in_no_tracked_file():
    hits = subprocess.run(['git', 'grep', '-l', '-i', OLD_ACCOUNT, '--', '.', ':!docs/',
                           ':!tests/test_contact_and_links.py'],
                          cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert hits == []


# ── UPG-46 ──────────────────────────────────────────────────────────────────

BASE = 'https://events.example.edu'
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


@pytest.fixture
def mailed(real_app, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setitem(flask_app.config, 'BASE_URL', BASE)
    monkeypatch.setenv('BASE_URL', BASE)
    import tasks.email_tasks as email_tasks
    sent = []

    class Capture:
        def delay(self, **kwargs):
            sent.append(kwargs)
    monkeypatch.setattr(email_tasks, 'send_generic_email_task', Capture())
    spoc, coord = f"{_unique('lnkspoc')}@test.edu", f"{_unique('lnkcoord')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    return {'app': flask_app, 'db': db, 'sent': sent, 'spoc': spoc, 'coord': coord,
            'owner': _login(flask_app, spoc, 'ClubSPOC')}


def _links(mail):
    text = ' '.join(str(mail.get(k) or '') for k in ('body_html', 'body_text', 'body'))
    return re.findall(r'https?://[^\s"\'<>]+', text), text


def test_the_coordinator_briefing_links_to_base_url(mailed):
    d = mailed
    tomorrow = (datetime.datetime.now(IST).date() + datetime.timedelta(days=1)).isoformat()
    event_id = _create_event(d['owner'], d['db'], _unique('Briefed Hack'), tomorrow, team=False)
    d['db'].collection('events').document(event_id).update({
        'status': 'registration_open', 'staff': [{'name': 'Cora', 'email': d['coord'], 'role': 'EventCoordinator'}]})
    from tasks.scheduled_tasks import send_24h_reminders
    with d['app'].app_context():
        send_24h_reminders.apply()
    [brief] = [m for m in d['sent'] if m['to_email'] == d['coord']]
    links, text = _links(brief)
    assert links and all(link.startswith(BASE + '/') for link in links), links
    assert 'sapthaevent.in' not in text
    # and it leads somewhere real
    path = next(link for link in links if '/coordinator/' in link)[len(BASE):]
    assert d['app'].test_client().get(path).status_code in (200, 302)


def test_the_low_registration_alert_links_to_base_url(mailed):
    d = mailed
    deadline = (datetime.datetime.now(IST).date() + datetime.timedelta(days=3)).isoformat()
    event_id = _create_event(d['owner'], d['db'], _unique('Quiet Talk'), '2031-03-03', team=False)
    d['db'].collection('events').document(event_id).update({'status': 'registration_open', 'reg_deadline': deadline,
                                                            'registration_count': 1, 'velocity_alert_sent': False})
    from tasks.scheduled_tasks import check_registration_velocity
    with d['app'].app_context():
        check_registration_velocity.apply()
    [alert] = [m for m in d['sent'] if m['to_email'] == d['spoc']]
    links, text = _links(alert)
    assert f'{BASE}/forms/register/{event_id}' in links
    assert all(link.startswith(BASE + '/') for link in links), links
    assert 'sapthaevent.in' not in text
