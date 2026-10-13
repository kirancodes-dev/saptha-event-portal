"""
tests/test_cron.py — UPG-07 on the real database layer: an outside scheduler
runs the reminder, lifecycle and clean-up jobs through POST /internal/cron/<job>
with a shared secret, and running a job twice does nothing new.
"""
import datetime
import pathlib
import time

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user

SECRET = 'cron-secret-for-pytest'
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


@pytest.fixture
def cron(real_app, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setenv('CRON_SECRET', SECRET)
    spoc = f"{_unique('cronspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')

    def event(date, timed=True, **fields):
        event_id = _create_event(owner, db, _unique('Cron Event'), date, team=False)
        if timed:  # saved without times, the SQL layer stores the save time (UPG-47)
            fields = {'start_datetime': f'{date}T10:00:00+05:30', 'end_datetime': f'{date}T17:00:00+05:30', **fields}
        if fields:
            db.collection('events').document(event_id).update(fields)
        return event_id

    def call(job, secret=SECRET):
        headers = {'X-Cron-Secret': secret} if secret is not None else {}
        return flask_app.test_client().post(f'/internal/cron/{job}', headers=headers)
    return {'app': flask_app, 'db': db, 'event': event, 'call': call}


def _day(offset):
    return (datetime.datetime.now(IST).date() + datetime.timedelta(days=offset)).isoformat()


def _status(d, event_id):
    return d['db'].collection('events').document(event_id).get().to_dict()['status']


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_endpoint_needs_the_secret_and_is_off_without_one(cron, monkeypatch):
    d = cron
    monkeypatch.setitem(d['app'].config, 'WTF_CSRF_ENABLED', True)   # the scheduler sends no CSRF token
    assert d['call']('cleanup', secret=None).status_code == 403
    assert d['call']('cleanup', secret='wrong-secret').status_code == 403
    assert d['call']('cleanup', secret=SECRET + 'x').status_code == 403
    ok = d['call']('cleanup')
    assert ok.status_code == 200 and ok.get_json()['status'] == 'ok'
    assert d['call']('nonsense').status_code == 404
    assert d['app'].test_client().get('/internal/cron/cleanup', headers={'X-Cron-Secret': SECRET}).status_code == 405

    monkeypatch.delenv('CRON_SECRET')
    assert d['call']('cleanup').status_code == 503
    assert d['call']('cleanup', secret='').status_code == 503


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_day_before_reminder_goes_out_once(cron, monkeypatch):
    d = cron
    import tasks.email_tasks
    import tasks.notification_tasks
    emails, whatsapps, briefings = [], [], []
    monkeypatch.setattr(tasks.email_tasks.send_ticket_email_task, 'delay', lambda **k: emails.append(k))
    monkeypatch.setattr(tasks.notification_tasks.send_reminder_whatsapp_task, 'delay', lambda **k: whatsapps.append(k))
    monkeypatch.setattr(tasks.email_tasks.send_generic_email_task, 'delay', lambda **k: briefings.append(k))

    # The reminder still looks only at the old `active` status (UPG-43)
    tomorrow = d['event'](_day(1), status='active')
    later = d['event'](_day(5), status='active')
    regs = {}
    for key, event_id, status, phone in (('ana', tomorrow, 'Confirmed', '9876543210'),
                                         ('ben', tomorrow, 'Confirmed', ''),
                                         ('gone', tomorrow, 'cancelled', '9876543211'),
                                         ('next', later, 'Confirmed', '9876543212')):
        reg_id = _unique('REG')
        regs[key] = f"{_unique(key)}@test.edu"
        d['db'].collection('registrations').document(reg_id).set({
            'reg_id': reg_id, 'event_id': event_id, 'lead_name': key.title(), 'lead_email': regs[key],
            'lead_phone': phone, 'status': status, 'payment_status': 'Free', 'members': []})

    first = d['call']('reminders')
    assert first.status_code == 200
    assert sorted(e['to_email'] for e in emails) == sorted([regs['ana'], regs['ben']])
    assert [w['phone'] for w in whatsapps] == ['9876543210']
    assert all(e['event_title'] and e['reg_id'] for e in emails)

    second = d['call']('reminders')
    assert second.status_code == 200
    assert len(emails) == 2 and len(whatsapps) == 1
    assert second.get_json()['result']['day_before']['skipped'] >= 2


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_lifecycle_completes_past_events_and_deletes_nothing(cron):
    d = cron
    ended = d['event'](_day(-1), status='registration_open')
    running = d['event'](_day(-2), status='in_progress')
    legacy = d['event'](_day(-1), status='active')
    long_ago = d['event'](_day(-40), status='registration_closed')
    multi_day = d['event'](_day(-1), status='in_progress', end_datetime=f"{_day(1)}T18:00")
    deadline_passed = d['event'](_day(7), status='registration_open', reg_deadline=_day(-1))
    today = d['event'](_day(0), status='registration_open', reg_deadline=_day(1))
    untimed = d['event'](_day(30), timed=False, status='registration_open')   # its end_datetime is now
    draft = d['event'](_day(-1), status='draft')
    cancelled = d['event'](_day(-1), status='cancelled')
    reg_id = _unique('REG')
    d['db'].collection('registrations').document(reg_id).set({
        'reg_id': reg_id, 'event_id': long_ago, 'lead_name': 'Old Timer', 'lead_email': f"{_unique('old')}@test.edu",
        'status': 'Confirmed', 'members': []})

    assert d['call']('lifecycle').status_code == 200
    statuses = {e: _status(d, e) for e in (ended, running, legacy, long_ago, multi_day, deadline_passed,
                                          today, untimed, draft, cancelled)}
    assert statuses == {ended: 'completed', running: 'completed', legacy: 'completed', long_ago: 'completed',
                        multi_day: 'in_progress', deadline_passed: 'registration_closed',
                        today: 'registration_open', untimed: 'registration_open', draft: 'draft',
                        cancelled: 'cancelled'}

    # Old events and their registrations stay; each move is in the audit trail
    assert d['db'].collection('registrations').document(reg_id).get().exists
    from services_workflow import WorkflowEngine

    def moves(event_id):
        return [(h['from_state'], h['to_state']) for h in WorkflowEngine.get_workflow_history(d['db'], 'event', event_id)]
    # _create_event sets the deadline to the event's date, so registration closes first
    assert moves(ended) == [('registration_open', 'registration_closed'), ('registration_closed', 'completed')]
    assert moves(legacy) == [('active', 'registration_closed'), ('registration_closed', 'completed')]
    assert moves(running) == [('in_progress', 'completed')]

    # A second run moves nothing
    assert d['call']('lifecycle').status_code == 200
    assert {e: _status(d, e) for e in statuses} == statuses
    assert len(moves(ended)) == 2 and len(moves(running)) == 1


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_clean_up_deletes_only_expired_sessions_and_old_login_attempts(cron):
    d = cron
    from db_pg import get_session
    from models_pg import FlaskSession, LoginAttempt
    now = datetime.datetime.now(datetime.timezone.utc)
    expired, live = _unique('sess-old'), _unique('sess-live')
    old_key, recent_key = _unique('k')[:64], _unique('k')[:64]
    with get_session() as s:
        s.add(FlaskSession(id=expired, data='{}', expiry=now - datetime.timedelta(minutes=1)))
        s.add(FlaskSession(id=live, data='{}', expiry=now + datetime.timedelta(days=1)))
        s.add(LoginAttempt(key=old_key, at=time.time() - 2 * 3600))
        s.add(LoginAttempt(key=recent_key, at=time.time() - 30 * 60))   # still counts for the hourly cap
    event_id = d['event'](_day(3))

    resp = d['call']('cleanup')
    assert resp.status_code == 200
    result = resp.get_json()['result']
    assert result['sessions'] >= 1 and result['login_attempts'] >= 1
    with get_session() as s:
        assert s.get(FlaskSession, expired) is None and s.get(FlaskSession, live) is not None
        assert s.query(LoginAttempt).filter_by(key=old_key).count() == 0
        assert s.query(LoginAttempt).filter_by(key=recent_key).count() == 1
    assert d['db'].collection('events').document(event_id).get().exists


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_the_github_workflow_and_the_deploy_guide_target_the_endpoint():
    root = pathlib.Path(__file__).resolve().parent.parent
    workflow = (root / '.github' / 'workflows' / 'cron.yml').read_text()
    assert 'schedule:' in workflow and 'workflow_dispatch:' in workflow
    assert '/internal/cron/$job' in workflow and 'X-Cron-Secret: $CRON_SECRET' in workflow
    assert all(f'job={job}' in workflow for job in ('reminders', 'lifecycle', 'cleanup'))

    guide = (root / 'docs' / 'DEPLOY.md').read_text()
    assert 'gcloud scheduler jobs create http' in guide
    assert all(f'/internal/cron/{job}' in guide for job in ('reminders', 'lifecycle', 'cleanup'))
    assert 'X-Cron-Secret' in guide and 'CRON_SECRET' in (root / '.env.example').read_text()
