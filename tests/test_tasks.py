"""
tests/test_tasks.py — Celery task unit tests (synchronous, no broker needed)
=============================================================================
Tasks are called directly (not via .delay()) so tests run without Redis.
"""

from unittest.mock import MagicMock, patch


# ── Email tasks ───────────────────────────────────────────

class TestSendReminderEmailTask:
    def test_sends_email_when_mail_configured(self):
        try:
            from tasks.email_tasks import send_reminder_email_task
        except Exception:
            tasks = None

        with patch('utils_email._send', return_value=True) as mock_send:
            send_reminder_email_task(
                to_email='user@test.local',
                name='Test User',
                event_title='Hackathon',
                event_date='2026-05-01',
                venue='Main Hall',
                reg_id='REG-001',
            )
        mock_send.assert_called_once()

    def test_skips_when_mail_not_configured(self):
        try:
            from tasks.email_tasks import send_reminder_email_task
        except Exception:
            tasks = None

        mock_app = MagicMock()
        mock_app.extensions = {}

        with patch('flask.current_app', mock_app):
            # Should not raise, just log and return
            send_reminder_email_task(
                to_email='user@test.local',
                name='Test',
                event_title='Event',
                event_date='2026-05-01',
                venue='Hall',
                reg_id='REG-002',
            )


# ── Analytics tasks ───────────────────────────────────────

class TestDailyRollup:
    def test_rollup_writes_snapshot(self):
        try:
            from tasks.analytics_tasks import daily_rollup
        except Exception:
            tasks = None

        mock_event = MagicMock()
        mock_event.to_dict.return_value = {'status': 'active'}

        mock_reg = MagicMock()
        mock_reg.to_dict.return_value = {'status': 'Confirmed', 'payment_status': 'Paid', 'amount_paid': 100}

        mock_user = MagicMock()
        mock_user.to_dict.return_value = {'created_at': '2026-01-01'}

        mock_db = MagicMock()
        mock_db.collection.return_value.stream.side_effect = [
            iter([mock_event]),  # events
            iter([mock_reg]),    # registrations
            iter([mock_user]),   # users
        ]
        mock_db.collection.return_value.document.return_value.set = MagicMock()

        with patch('tasks.analytics_tasks.db', mock_db):
            result = daily_rollup()

        assert result['total_events'] == 1
        assert result['active_events'] == 1
        assert result['total_registrations'] == 1
        assert result['total_revenue'] == 100.0


# ── Webhook tasks ─────────────────────────────────────────

class TestProcessRazorpayPayment:
    def test_idempotent_on_already_paid(self):
        try:
            from tasks.webhook_tasks import process_razorpay_payment
        except Exception:
            tasks = None

        mock_reg_doc = MagicMock()
        mock_reg_doc.exists = True
        mock_reg_doc.to_dict.return_value = {'payment_status': 'Paid'}

        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_reg_doc

        with patch('tasks.webhook_tasks.db', mock_db):
            process_razorpay_payment({
                'reg_id': 'REG-PAID',
                'event_id': 'EVT-001',
                'razorpay_payment_id': 'pay_abc',
                'amount': 500,
                'lead_email': 'user@test.local',
                'lead_name': 'User',
                'lead_phone': '',
            })

        # Should NOT update if already paid (idempotency)
        mock_db.collection.return_value.document.return_value.update.assert_not_called()

    def test_missing_reg_id_exits_gracefully(self):
        try:
            from tasks.webhook_tasks import process_razorpay_payment
        except Exception:
            tasks = None

        mock_db = MagicMock()
        with patch('tasks.webhook_tasks.db', mock_db):
            process_razorpay_payment({})  # no reg_id

        mock_db.collection.assert_not_called()


# ── Scheduled tasks ───────────────────────────────────────

class TestRunEventLifecycle:
    def test_closes_overdue_registrations(self):
        import datetime
        try:
            from tasks.scheduled_tasks import run_event_lifecycle
        except Exception:
            tasks = None

        past_date = (datetime.date.today() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        mock_event_doc = MagicMock()
        mock_event_doc.id = 'EVT-001'
        mock_event_doc.to_dict.return_value = {
            'status': 'active',
            'reg_deadline': past_date,
            'date': past_date,
        }

        mock_db = MagicMock()
        mock_db.collection.return_value.stream.return_value = iter([mock_event_doc])
        mock_db.collection.return_value.where.return_value.stream.return_value = iter([])

        with patch('tasks.scheduled_tasks.db', mock_db):
            result = run_event_lifecycle()

        assert result['closed'] == 1
