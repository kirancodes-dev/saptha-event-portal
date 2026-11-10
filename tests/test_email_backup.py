"""
tests/test_email_backup.py — UPG-224 on the real database layer: a backup
Brevo account (BREVO_BACKUP_API_KEY) sends what the main account can't, once
the main account reaches its daily limit or when it refuses an email, counted
against its own daily limit; without the key nothing changes. Nothing leaves
the machine: both Brevo senders are replaced, and the HTTP call is captured.
"""
import json
import urllib.request

import pytest

import services_email_quota as quota
import utils_email
from tests.test_integration_flow import _unique, _user
from tests.test_low_email_auth import _user_doc, low  # noqa: F401  (fixture)


@pytest.fixture
def backup(low, monkeypatch):  # noqa: F811
    monkeypatch.setenv('BREVO_BACKUP_API_KEY', 'test-backup-key')
    monkeypatch.setitem(low['app'].config, 'EMAIL_BACKUP_DAILY_LIMIT', 2)
    sent = []

    def brevo_backup(to, subject, html, attachments=None):
        sent.append({'to': to, 'subject': subject})
        return True
    monkeypatch.setattr(utils_email, '_send_via_brevo_backup', brevo_backup)
    return dict(low, backup_sent=sent)


def _send(to='a@test.edu'):
    return utils_email._send(to, 'Hi', '<p>x</p>')


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_backup_sends_once_the_main_account_is_at_its_limit(backup, monkeypatch):
    flask_app = backup['app']
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 1)
    with flask_app.app_context():
        assert _send('one@test.edu') and [m['to'] for m in backup['sent']] == ['one@test.edu']
        assert _send('two@test.edu') and _send('three@test.edu')          # main full: the backup
        assert [m['to'] for m in backup['backup_sent']] == ['two@test.edu', 'three@test.edu']
        assert (quota.sent_today(), quota.sent_today(quota.BACKUP)) == (1, 2)
        # Both full: nothing is sent, and pages show the organizer message
        assert not quota.available() and _send('four@test.edu') is False
        assert len(backup['sent']) == 1 and len(backup['backup_sent']) == 2
        # A new UTC day starts both from zero
        monkeypatch.setattr(quota, 'today', lambda: '2999-01-01')
        assert quota.available() and quota.sent_today(quota.BACKUP) == 0


def test_a_registration_past_the_main_limit_is_emailed_through_the_backup(backup, monkeypatch):
    flask_app, db = backup['app'], backup['db']
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 1)
    event_id, _ = backup['event'](team=False)
    first, _ = backup['register'](event_id)
    second, client = backup['register'](event_id)
    assert [m['to'] for m in backup['sent']] == [first]
    assert [m['to'] for m in backup['backup_sent']] == [second]
    assert _user_doc(db, second)['login_link']['status'] == 'sent'


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_backup_sends_what_the_main_account_refuses(backup):
    flask_app = backup['app']
    backup['provider']['ok'] = False            # e.g. Brevo's own daily limit on the main account
    with flask_app.app_context():
        assert _send(['a@test.edu', 'b@test.edu'])
        assert backup['backup_sent'] == [{'to': ['a@test.edu', 'b@test.edu'], 'subject': 'Hi'}]
        assert (quota.sent_today(), quota.sent_today(quota.BACKUP)) == (0, 2)   # the refused places given back


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_without_a_backup_key_nothing_changes(backup, monkeypatch):
    flask_app = backup['app']
    monkeypatch.delenv('BREVO_BACKUP_API_KEY')
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 1)
    with flask_app.app_context():
        assert _send('one@test.edu') and _send('two@test.edu') is False
        assert not quota.available() and backup['backup_sent'] == []
        assert quota.sent_today(quota.BACKUP) == 0


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_backup_uses_its_own_key_and_sender(monkeypatch):
    calls = []

    class Resp:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        calls.append((dict(req.header_items()), json.loads(req.data)))
        return Resp()
    monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
    monkeypatch.setenv('BREVO_API_KEY', 'main-key')
    monkeypatch.setenv('BREVO_BACKUP_API_KEY', 'backup-key')
    monkeypatch.setenv('MAIL_FROM', 'SapthaEvent <events@test.edu>')
    monkeypatch.delenv('MAIL_FROM_BACKUP', raising=False)
    assert utils_email._send_via_brevo_backup('x@test.edu', 'S', '<p>b</p>')
    monkeypatch.setenv('MAIL_FROM_BACKUP', 'Saptha Backup <backup@test.edu>')
    assert utils_email._send_via_brevo_backup('x@test.edu', 'S', '<p>b</p>')
    assert utils_email._send_via_brevo('x@test.edu', 'S', '<p>b</p>')
    keys = [h.get('Api-key') for h, _ in calls]
    senders = [p['sender'] for _, p in calls]
    assert keys == ['backup-key', 'backup-key', 'main-key']
    assert senders == [{'name': 'SapthaEvent', 'email': 'events@test.edu'},
                       {'name': 'Saptha Backup', 'email': 'backup@test.edu'},
                       {'name': 'SapthaEvent', 'email': 'events@test.edu'}]


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_the_admin_tests_the_backup_from_the_email_check(backup, monkeypatch):
    flask_app, db = backup['app'], backup['db']
    admin = f"{_unique('mailadmin')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    client = flask_app.test_client()
    client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': 'Str0ng!Pass#1',
                                'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    out = client.get('/diag/email?to=check@test.edu&via=backup').get_json()
    assert out['provider'] == 'Brevo backup' and out['sent'] is True and out['backup_key_set'] is True
    assert (out['backup_emails_sent_today'], out['backup_daily_limit']) == (1, 2)
    assert [m['to'] for m in backup['backup_sent']] == ['check@test.edu'] and backup['sent'] == []
    # Without the key it says so
    monkeypatch.delenv('BREVO_BACKUP_API_KEY')
    out = client.get('/diag/email?to=check@test.edu&via=backup').get_json()
    assert out['sent'] is False and "BREVO_BACKUP_API_KEY isn't set" in out['error']
    assert client.get('/diag/email?to=check@test.edu').get_json()['provider'] == 'Brevo'
