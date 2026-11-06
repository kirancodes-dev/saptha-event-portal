"""
tests/test_whatsapp_and_escaping.py — UPG-49: the automation's WhatsApp
channel sends through Twilio (mocked) once for a user who opted in; with no
Twilio settings it's skipped, not attempted; a refused send is recorded as a
failure, not a fallback. UPG-50: a registrant named <b>Ann</b> gets a
confirmation showing that text, not bold; the coordinators' briefing and the
3-day reminder show an event title's markup as text.
"""
import datetime
import sys
import types

import pytest

from services_automation import NotificationAutomationEngine as Engine
from tests.test_integration_flow import _create_event, _login, _unique, _user

RULE = {'title': 'Reminder', 'message': 'See you tomorrow, {{name}}', 'channels': ['whatsapp'],
        'notif_type': 'event_reminder'}
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


# ── UPG-49 ──────────────────────────────────────────────────────────────────

@pytest.fixture
def twilio(real_app, monkeypatch):
    flask_app, db = real_app
    calls = {'created': [], 'fail': False}

    class Messages:
        def create(self, **kw):
            if calls['fail']:
                raise RuntimeError('Twilio refused the number')
            calls['created'].append(kw)
            return types.SimpleNamespace(sid='SM123')

    class Client:
        def __init__(self, sid, token):
            calls.setdefault('clients', []).append(sid)
            self.messages = Messages()
    rest = types.ModuleType('twilio.rest')
    rest.Client = Client
    monkeypatch.setitem(sys.modules, 'twilio', types.ModuleType('twilio'))
    monkeypatch.setitem(sys.modules, 'twilio.rest', rest)
    monkeypatch.setenv('TWILIO_ACCOUNT_SID', 'AC' + 'x' * 32)
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'token-for-the-test')
    email = f"{_unique('wa')}@test.edu"
    db.collection('notification_preferences').document(email).set({'whatsapp_enabled': True})
    return {'db': db, 'calls': calls, 'email': email, 'monkeypatch': monkeypatch}


def _dispatch(d, email=None, rule=RULE, trigger='on_event_reminder'):
    return Engine.dispatch_trigger(d['db'], trigger_name=trigger, custom_rule=rule, context={
        'recipient_email': email or d['email'], 'phone': '9876543210', 'name': 'Asha'})


def test_an_opted_in_user_gets_one_whatsapp_message(twilio):
    d = twilio
    result = _dispatch(d)
    assert result['dispatched_channels'] == ['whatsapp']
    [msg] = d['calls']['created']
    assert msg['to'] == 'whatsapp:+919876543210' and msg['body'] == 'See you tomorrow, Asha'


def test_the_default_reminder_rule_reaches_whatsapp_too(twilio):
    d = twilio
    result = Engine.dispatch_trigger(d['db'], trigger_name='on_event_reminder', context={
        'recipient_email': d['email'], 'phone': '9876543210', 'name': 'Asha', 'event_title': 'Hack'})
    assert 'whatsapp' in result['dispatched_channels'] and len(d['calls']['created']) == 1


def test_a_user_who_didnt_opt_in_gets_none(twilio):
    d = twilio
    result = _dispatch(d, email=f"{_unique('nowa')}@test.edu")
    assert d['calls']['created'] == [] and result['skipped_channels'] == ['whatsapp (disabled or missing phone)']


def test_without_twilio_settings_the_channel_is_off(twilio):
    d = twilio
    d['monkeypatch'].delenv('TWILIO_ACCOUNT_SID')
    result = _dispatch(d)
    assert result['skipped_channels'] == ['whatsapp (not configured)']
    assert d['calls']['created'] == [] and not d['calls'].get('clients')


def test_a_refused_send_is_a_failure_not_a_fallback(twilio):
    d = twilio
    d['calls']['fail'] = True
    result = _dispatch(d)
    assert result['skipped_channels'] == ['whatsapp (failed)'] and result['dispatched_channels'] == []
    assert not any('fallback' in c for c in result['dispatched_channels'] + result['skipped_channels'])


# ── UPG-50 ──────────────────────────────────────────────────────────────────

@pytest.fixture
def inbox(real_app, monkeypatch):
    flask_app, db = real_app
    import tasks.email_tasks as email_tasks
    import utils_email
    mail = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: mail.append(
        {'to': to, 'subject': subject, 'html': html}) or True)
    import routes_forms                 # real_app stubs the confirmation out; build it for real, captured at _send
    monkeypatch.setattr(routes_forms, 'send_registration_confirmed_email', utils_email.send_registration_confirmed_email)

    class Capture:
        def delay(self, **kw):
            mail.append({'to': kw['to_email'], 'subject': kw['subject'], 'html': kw.get('body_html') or ''})
    monkeypatch.setattr(email_tasks, 'send_generic_email_task', Capture())
    spoc = f"{_unique('escspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    return {'app': flask_app, 'db': db, 'mail': mail, 'owner': _login(flask_app, spoc, 'ClubSPOC')}


TITLE = 'Fest & <i>Fun</i>'


def _event(d, day, **fields):
    event_id = _create_event(d['owner'], d['db'], _unique('Esc'), day, team=False)
    d['db'].collection('events').document(event_id).update(dict({'title': TITLE, 'status': 'registration_open'},
                                                                **fields))
    return event_id


def _shows_as_text(html, raw, escaped):
    return escaped in html and raw not in html


def test_a_name_with_markup_shows_as_text_in_the_confirmation(inbox):
    d = inbox
    event_id = _event(d, '2031-04-04')
    student = f"{_unique('ann')}@test.edu"
    _user(d['db'], student, 'Student')
    _login(d['app'], student, 'Student').post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': '<b>Ann</b>', 'email': student, 'phone': '9876543210',
        'usn': '1SN20CS888'})
    [mail] = [m for m in d['mail'] if m['to'] == student]
    assert _shows_as_text(mail['html'], '<b>Ann</b>', '&lt;b&gt;Ann&lt;/b&gt;')
    assert _shows_as_text(mail['html'], '<i>Fun</i>', '&lt;i&gt;Fun&lt;/i&gt;')


def test_the_briefing_and_the_3_day_reminder_show_a_title_as_text(inbox):
    d = inbox
    today = datetime.datetime.now(IST).date()
    coord = f"{_unique('esccoord')}@test.edu"
    _user(d['db'], coord, 'EventCoordinator')
    _event(d, (today + datetime.timedelta(days=1)).isoformat(),
           staff=[{'name': 'C', 'email': coord, 'role': 'EventCoordinator'}])
    soon = _event(d, (today + datetime.timedelta(days=3)).isoformat())
    attendee = f"{_unique('escatt')}@test.edu"
    d['db'].collection('registrations').document(_unique('REG')).set({
        'event_id': soon, 'lead_email': attendee, 'lead_name': '<script>x</script>', 'status': 'Confirmed'})
    from tasks.scheduled_tasks import send_3day_reminders, send_24h_reminders
    with d['app'].app_context():
        send_24h_reminders.apply()
        send_3day_reminders.apply()
    [brief] = [m for m in d['mail'] if m['to'] == coord]
    [early] = [m for m in d['mail'] if m['to'] == attendee]
    for mail in (brief, early):
        assert _shows_as_text(mail['html'], '<i>Fun</i>', '&lt;i&gt;Fun&lt;/i&gt;'), mail['subject']
    assert '<script>x</script>' not in early['html']
