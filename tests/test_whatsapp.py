"""
tests/test_whatsapp.py — UPG-147 on the real database layer: WhatsApp only
when switched on and configured, the four template messages once each to
opted-in people, the templates file, opt-in and STOP (signed webhooks), the
email fallback with outbox retries, and the monthly cap.
"""
import base64
import datetime
import hashlib
import hmac
import json
import re

import pytest

import services_whatsapp as wa
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user


@pytest.fixture
def world(real_app, monkeypatch):
    import utils_email
    import utils_whatsapp
    flask_app, db = real_app
    monkeypatch.delenv('WHATSAPP_ENABLED', raising=False)
    monkeypatch.setenv('TWILIO_ACCOUNT_SID', 'AC' + 'x' * 32)
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'test-auth-token')
    monkeypatch.setenv('TASK_INLINE_TIMEOUT', '60')
    sent, mail = [], []
    monkeypatch.setattr(utils_whatsapp, '_provider_send', lambda to, body: sent.append((wa.normalise(to), body)) or True)
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k:
                        mail.append({'to': to, 'subject': subject}) or True)
    spoc, admin = f"{_unique('waspoc')}@test.edu", f"{_unique('waadmin')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, admin, 'SuperAdmin')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    admin_client = flask_app.test_client()
    admin_client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                      'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    counter = iter(range(10 ** 6))

    def phone():
        return '9' + str(int(hashlib.sha1(_unique('ph').encode()).hexdigest(), 16) % 10 ** 9 + next(counter)).zfill(9)[-9:]

    def event(days=1, **fields):
        day = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
        event_id = _create_event(owner, db, _unique('WA Event'), day, team=False)
        db.collection('events').document(event_id).update(dict({'status': 'registration_open'}, **fields))
        return event_id

    def register(event_id, number, opt_in=True, name='Wendy Whats'):
        email = f"{_unique('wa')}@test.edu"
        data = {'privacy_consent': 'yes', 'full_name': name, 'email': email, 'phone': number}
        if opt_in:
            data['whatsapp_opt_in'] = 'yes'
        flask_app.test_client().post(f'/forms/submit/{event_id}', data=data)
        return email
    return {'app': flask_app, 'db': db, 'sent': sent, 'mail': mail, 'owner': owner, 'admin': admin_client,
            'phone': phone, 'event': event, 'register': register, 'spoc': spoc}


def _to(d, number):
    return [body for to, body in d['sent'] if to == wa.normalise(number)]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_nothing_goes_unless_switched_on_and_configured(world, monkeypatch):
    d = world
    number = d['phone']()
    wa.set_consent(d['db'], number, True, 'test')
    for env in ({'TWILIO_ACCOUNT_SID': '', 'TWILIO_AUTH_TOKEN': ''}, {'WHATSAPP_ENABLED': 'false'}):
        with monkeypatch.context() as m:
            for k, v in env.items():
                m.setenv(k, v)
            assert wa.notify(d['db'], 'event_cancelled', number, {'name': 'A', 'event': 'E', 'date': 'D'},
                             key=_unique('k')) == 'off'
    assert _to(d, number) == []
    assert wa.notify(d['db'], 'event_cancelled', number, {'name': 'A', 'event': 'Twilio Fest', 'date': 'D'},
                     key=_unique('k')) == 'queued'
    assert any('Twilio Fest' in b for b in _to(d, number))

    calls = []
    monkeypatch.setenv('WHATSAPP_PROVIDER', 'meta')
    monkeypatch.setenv('META_WA_TOKEN', 'meta-token')
    monkeypatch.setenv('META_WA_PHONE_ID', '123456')

    class Ok:
        status_code = 200
    import requests
    monkeypatch.setattr(requests, 'post', lambda url, json=None, headers=None, timeout=None: calls.append((url, json)) or Ok())
    wa.notify(d['db'], 'event_cancelled', number, {'name': 'A', 'event': 'Meta Fest', 'date': 'D'}, key=_unique('k'))
    [(url, payload)] = calls
    assert url.endswith('/123456/messages') and payload['type'] == 'template'
    assert payload['template']['name'] == 'event_cancelled' and payload['template']['components'][0]['parameters'][1]['text'] == 'Meta Fest'


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_each_of_the_four_messages_goes_once(world):
    from services_venue import notify_event_details_changed
    from services_workflow import WorkflowEngine
    from tasks.scheduled_tasks import send_24h_reminders
    d = world
    event_id = d['event'](days=1, venue='Hall A')
    number = d['phone']()
    d['register'](event_id, number)
    [reg] = [r for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()]
    first = _to(d, number)
    assert len(first) == 1 and 'registered for' in first[0] and f"/ticket/{reg.to_dict()['reg_id']}" in first[0]

    d['db'].collection('events').document(event_id).update({'status': 'active'})
    send_24h_reminders.run()
    send_24h_reminders.run()
    reminders = [b for b in _to(d, number) if 'Tomorrow' in b]
    assert len(reminders) == 1
    from tasks.notification_tasks import send_reminder_whatsapp_task     # the task again: still once
    day = d['db'].collection('events').document(event_id).get().to_dict()['date']
    send_reminder_whatsapp_task.run(phone=number, name='W', event_title='E', event_date=day, venue='V',
                                    reg_id=reg.to_dict()['reg_id'])
    assert len([b for b in _to(d, number) if 'Tomorrow' in b]) == 1

    event = d['db'].collection('events').document(event_id).get().to_dict()
    for _ in range(2):
        notify_event_details_changed(d['db'], event_id=event_id, previous_data=event, new_data={**event, 'venue': 'Hall B'})
    assert len([b for b in _to(d, number) if 'has changed' in b and 'Hall B' in b]) == 1
    for _ in range(2):
        WorkflowEngine._notify_participants_of_cancellation(d['db'], event_id=event_id, event_data=event)
    assert len([b for b in _to(d, number) if 'has been cancelled' in b]) == 1


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_templates_are_ready_for_approval():
    templates = wa.templates()
    assert set(templates) == {'registration_confirmed', 'event_reminder', 'event_changed', 'event_cancelled'}
    for name, spec in templates.items():
        numbers = sorted(int(n) for n in re.findall(r'\{\{(\d+)\}\}', spec['body']))
        assert numbers == list(range(1, len(spec['variables']) + 1)), name
        assert spec['category'] == 'UTILITY' and spec['language'] == 'en' and 'STOP' in spec['body']
    guide = open('docs/DEPLOY.md', encoding='utf-8').read()
    assert '## WhatsApp' in guide and 'config/whatsapp_templates.json' in guide and 'WhatsApp Manager' in guide


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def _twilio_signed(d, number, body):
    form = {'From': f'whatsapp:{wa.normalise(number)}', 'Body': body}
    from utils_email import _base_url
    with d['app'].test_request_context('/whatsapp/webhook'):
        base = _base_url().rstrip('/')
    data = base + '/whatsapp/webhook' + ''.join(k + v for k, v in sorted(form.items()))
    sig = base64.b64encode(hmac.new(b'test-auth-token', data.encode(), hashlib.sha1).digest()).decode()
    return d['app'].test_client().post('/whatsapp/webhook', data=form, headers={'X-Twilio-Signature': sig})


def test_opt_in_stop_and_the_profile_switch(world, monkeypatch):
    d = world
    event_id = d['event'](days=5)
    quiet, keen = d['phone'](), d['phone']()
    d['register'](event_id, quiet, opt_in=False)
    d['register'](event_id, keen)
    assert _to(d, quiet) == [] and len(_to(d, keen)) == 1
    regs = {r.to_dict().get('lead_phone') or (r.to_dict().get('form_answers') or {}).get('phone'): r.to_dict()
            for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()}
    keen_reg = next(r for r in regs.values() if r.get('whatsapp_opt_in'))
    assert keen_reg['whatsapp_opt_in_at'][:10] == datetime.datetime.now(datetime.timezone.utc).date().isoformat()

    unsigned = d['app'].test_client().post('/whatsapp/webhook', data={'From': f'whatsapp:{wa.normalise(keen)}', 'Body': 'STOP'})
    assert unsigned.status_code == 403 and wa.has_consent(d['db'], keen)
    assert _twilio_signed(d, keen, 'STOP').status_code == 204 and not wa.has_consent(d['db'], keen)
    assert wa.notify(d['db'], 'event_cancelled', keen, {'name': 'K', 'event': 'E', 'date': 'D'}, key=_unique('k')) == 'no consent'

    meta = d['phone']()
    wa.set_consent(d['db'], meta, True, 'test')
    monkeypatch.setenv('META_WA_APP_SECRET', 'meta-secret')
    body = json.dumps({'entry': [{'changes': [{'value': {'messages': [{'from': wa.normalise(meta).lstrip('+'),
                                                                        'text': {'body': 'stop'}}]}}]}]}).encode()
    signature = 'sha256=' + hmac.new(b'meta-secret', body, hashlib.sha256).hexdigest()
    assert d['app'].test_client().post('/whatsapp/webhook', data=body, content_type='application/json',
                                       headers={'X-Hub-Signature-256': signature}).status_code == 204
    assert not wa.has_consent(d['db'], meta)
    assert d['app'].test_client().post('/whatsapp/webhook', data=body, content_type='application/json',
                                       headers={'X-Hub-Signature-256': 'sha256=' + '0' * 64}).status_code == 403

    student = f"{_unique('wastu')}@test.edu"
    own = d['phone']()
    _user(d['db'], student, 'Student')
    d['db'].collection('users').document(student).update({'phone': own})
    client = _login(d['app'], student, 'Student')
    client.post('/whatsapp/preference', data={'whatsapp': 'on'})
    assert wa.has_consent(d['db'], own)
    client.post('/whatsapp/preference', data={'whatsapp': 'off'})
    assert not wa.has_consent(d['db'], own)


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_a_failed_whatsapp_waits_in_the_outbox_and_email_still_goes(world, monkeypatch):
    import utils_whatsapp
    from sqlalchemy import select
    from models_pg import OutboxTask
    from services_outbox import _session
    from tasks.scheduled_tasks import send_24h_reminders
    d = world
    event_id = d['event'](days=1)
    number = d['phone']()
    email = d['register'](event_id, number)
    monkeypatch.setattr(utils_whatsapp, '_provider_send', lambda to, body: False)
    d['db'].collection('events').document(event_id).update({'status': 'active'})
    before = len([m for m in d['mail'] if m['to'] == email])
    send_24h_reminders.run()
    assert len([m for m in d['mail'] if m['to'] == email]) == before + 1                    # the reminder email went
    with _session() as s:
        waiting = s.execute(select(OutboxTask).where(OutboxTask.task_name.like('tasks.notification_tasks.%'),
                                                     OutboxTask.status == 'pending')).scalars().all()
    assert any(number in t.args_json + t.kwargs_json for t in waiting)


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_the_monthly_cap_pauses_whatsapp_and_tells_the_admin_once(world):
    d = world
    assert d['owner'].post('/whatsapp/settings', data={'monthly_cap': '5'}).status_code == 403
    cap = wa.used_this_month(d['db']) + 2
    d['admin'].post('/whatsapp/settings', data={'monthly_cap': str(cap)})
    assert wa.monthly_cap(d['db']) == cap
    results = []
    for _ in range(4):
        number = d['phone']()
        wa.set_consent(d['db'], number, True, 'test')
        results.append(wa.notify(d['db'], 'event_cancelled', number, {'name': 'C', 'event': 'Capped', 'date': 'D'},
                                 key=_unique('k')))
    assert results == ['queued', 'queued', 'cap reached', 'cap reached']
    alerts = [m for m in d['mail'] if m['subject'] == 'WhatsApp cap reached']
    assert alerts and len({m['to'] for m in alerts}) == len(alerts)                         # each admin told once
    d['admin'].post('/whatsapp/settings', data={'monthly_cap': '100000'})
