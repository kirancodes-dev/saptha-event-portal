"""
tests/test_email_paid_plan.py — UPG-255 on the real database layer.

A paid mail plan gives a monthly allowance: EMAIL_MONTHLY_LIMIT caps the main
account's month beside the daily limit. With Brevo main and MAIL_USER/MAIL_PASS
set, Gmail SMTP sends what Brevo can't, before the backup Brevo account, against
its own daily limit. The admin's mail page shows this month's count and limit.
Nothing leaves the machine: every sender is replaced.
"""
import html

import pytest

import services_email_quota as quota
import utils_email
from tests.test_integration_flow import _login, _unique, _user
from tests.test_low_email_auth import low  # noqa: F401  (fixture)


@pytest.fixture
def paid(low, monkeypatch):  # noqa: F811
    gmail = []

    def smtp(to, subject, html, attachments=None):
        gmail.append({'to': to, 'subject': subject})
        return True
    monkeypatch.setattr(utils_email, '_send_via_gmail', smtp)
    return dict(low, gmail=gmail)


def _send(to):
    return utils_email._send(to, 'Hi', '<p>x</p>')


# ── Criterion 1: the month's limit stops the main account ──────────────────

def test_at_the_monthly_limit_nothing_more_goes_from_the_main_account_though_the_day_has_room(paid, monkeypatch):
    flask_app = paid['app']
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 100)
    monkeypatch.setitem(flask_app.config, 'EMAIL_MONTHLY_LIMIT', 2)
    with flask_app.app_context():
        assert _send('one@test.edu') and _send('two@test.edu')
        assert (quota.sent_today(), quota.sent_this_month()) == (2, 2)
        assert not quota.available()
        assert _send('three@test.edu') is False                 # the day has room; the month hasn't
        assert [m['to'] for m in paid['sent']] == ['one@test.edu', 'two@test.edu']
        assert quota.sent_today() == 2                          # the refused one took no day's place
        # The month carries over days, and a new month starts from zero
        monkeypatch.setattr(quota, 'today', lambda: '2999-01-31')
        assert quota.sent_this_month() == 0 and quota.available()
        assert _send('four@test.edu') and _send('five@test.edu')
        monkeypatch.setattr(quota, 'today', lambda: '2999-01-30')
        assert quota.sent_today() == 0 and _send('six@test.edu') is False
        monkeypatch.setattr(quota, 'today', lambda: '2999-02-01')
        assert _send('seven@test.edu')


def test_a_refused_email_gives_back_its_place_in_the_month(paid, monkeypatch):
    flask_app = paid['app']
    monkeypatch.setitem(flask_app.config, 'EMAIL_MONTHLY_LIMIT', 5)
    with flask_app.app_context():
        paid['provider']['ok'] = False
        assert _send('x@test.edu') is False
        assert (quota.sent_today(), quota.sent_this_month()) == (0, 0)


def test_without_a_monthly_limit_nothing_changes(paid, monkeypatch):
    flask_app = paid['app']
    monkeypatch.setitem(flask_app.config, 'EMAIL_DAILY_LIMIT', 1)
    with flask_app.app_context():
        assert quota.monthly_limit() == 0
        assert _send('one@test.edu') and _send('two@test.edu') is False
        assert quota.sent_this_month() == 0


# ── Criterion 2: Gmail SMTP sends what Brevo can't ─────────────────────────

def test_with_brevo_main_and_gmail_set_an_email_brevo_refuses_goes_by_gmail(paid, monkeypatch):
    flask_app = paid['app']
    monkeypatch.setenv('MAIL_USER', 'sender@gmail.com')
    monkeypatch.setenv('MAIL_PASS', 'app-password')
    monkeypatch.setitem(flask_app.config, 'EMAIL_SMTP_DAILY_LIMIT', 1)
    backup = []
    monkeypatch.setenv('BREVO_BACKUP_API_KEY', 'test-backup-key')
    monkeypatch.setattr(utils_email, '_send_via_brevo_backup',
                        lambda to, *a, **k: backup.append(to) or True)
    with flask_app.app_context():
        paid['provider']['ok'] = False                          # Brevo refuses
        assert _send('one@test.edu')
        assert [m['to'] for m in paid['gmail']] == ['one@test.edu'] and backup == []
        assert (quota.sent_today(), quota.sent_today(quota.SMTP)) == (0, 1)
        # Gmail at its own limit: the backup Brevo account is next
        assert _send('two@test.edu') and backup == ['two@test.edu']


def test_brevo_at_its_monthly_limit_hands_over_to_gmail(paid, monkeypatch):
    flask_app = paid['app']
    monkeypatch.setenv('MAIL_USER', 'sender@gmail.com')
    monkeypatch.setenv('MAIL_PASS', 'app-password')
    monkeypatch.setitem(flask_app.config, 'EMAIL_MONTHLY_LIMIT', 1)
    with flask_app.app_context():
        assert _send('one@test.edu') and _send('two@test.edu')
        assert [m['to'] for m in paid['sent']] == ['one@test.edu']
        assert [m['to'] for m in paid['gmail']] == ['two@test.edu']
        assert quota.available()                                # Gmail still has room


def test_without_gmail_set_brevo_refusing_sends_nothing_by_smtp(paid):
    flask_app = paid['app']
    with flask_app.app_context():
        assert not quota.smtp_fallback_configured()
        paid['provider']['ok'] = False
        assert _send('one@test.edu') is False and paid['gmail'] == []


# ── Criterion 3: the admin's mail page shows the month ─────────────────────

def test_the_admin_mail_page_shows_this_months_count_and_limit(paid, monkeypatch):
    flask_app, db = paid['app'], paid['db']
    monkeypatch.setitem(flask_app.config, 'EMAIL_MONTHLY_LIMIT', 20000)
    with flask_app.app_context():
        assert _send('one@test.edu') and _send(['two@test.edu', 'three@test.edu'])
    admin = f"{_unique('mailadmin')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    client = _login(flask_app, admin, 'SuperAdmin')
    page = html.unescape(client.get('/admin/send_email').get_data(as_text=True))
    counts = page[page.index('data-mail-counts'):]
    counts = counts[:counts.index('Compose')]
    assert 'Sent this month' in counts
    assert '3 of 20000' in counts[counts.index('data-sent-month'):]
    assert '3 of 450' in counts[counts.index('data-sent-today'):]

    monkeypatch.setitem(flask_app.config, 'EMAIL_MONTHLY_LIMIT', 0)
    page = client.get('/admin/send_email').get_data(as_text=True)
    assert 'no monthly limit set' in page
