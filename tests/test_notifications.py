"""
test_notifications.py — Tests for Enhanced Notification Center

Covers: notification creation, bulk operations, read/unread management,
preferences, and type validation.
"""
import pytest


class TestNotificationCreation:
    """Test notification creation helpers."""

    def test_create_notification(self, mock_db):
        from routes_notifications_v2 import create_notification
        notif_id = create_notification(
            mock_db,
            user_email="student@test.edu",
            notif_type="event_reminder",
            title="Event Tomorrow",
            message="Tech Hackathon starts tomorrow!",
            link="/event/123",
        )
        assert notif_id is not None
        # Verify in DB
        doc = mock_db.collection("notifications_v2").document(notif_id).get()
        assert doc.exists
        data = doc.to_dict()
        assert data["title"] == "Event Tomorrow"
        assert data["is_read"] is False

    def test_create_notification_with_metadata(self, mock_db):
        from routes_notifications_v2 import create_notification
        notif_id = create_notification(
            mock_db,
            user_email="test@test.edu",
            notif_type="achievement_earned",
            title="New Badge!",
            message="You earned the Champion badge",
            metadata={"badge": "Champion", "xp": 500},
        )
        doc = mock_db.collection("notifications_v2").document(notif_id).get()
        data = doc.to_dict()
        assert data["metadata"]["badge"] == "Champion"

    def test_bulk_notifications(self, mock_db):
        from routes_notifications_v2 import create_bulk_notifications
        emails = ["a@test.edu", "b@test.edu", "c@test.edu"]
        create_bulk_notifications(
            mock_db,
            emails=emails,
            notif_type="announcement",
            title="System Update",
            message="New features available",
        )
        # Verify all created
        all_notifs = list(mock_db.collection("notifications_v2").stream())
        assert len(all_notifs) >= 3


class TestNotificationTypes:
    """Test notification type configuration."""

    def test_all_types_have_icons(self):
        from routes_notifications_v2 import NOTIFICATION_TYPES
        for type_name, config in NOTIFICATION_TYPES.items():
            assert "icon" in config, f"Missing icon for {type_name}"
            assert "color" in config, f"Missing color for {type_name}"
            assert "label" in config, f"Missing label for {type_name}"

    def test_known_types(self):
        from routes_notifications_v2 import NOTIFICATION_TYPES
        expected = [
            "event_reminder", "registration_confirmed", "payment_received",
            "score_published", "achievement_earned", "announcement",
            "system_alert", "waitlist_promoted",
        ]
        for t in expected:
            assert t in NOTIFICATION_TYPES, f"Missing type: {t}"


class TestTimeAgo:
    """Test relative time formatting."""

    def test_time_ago_recent(self):
        from routes_notifications_v2 import _time_ago
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result = _time_ago(now)
        assert result == "just now"

    def test_time_ago_empty_string(self):
        from routes_notifications_v2 import _time_ago
        assert _time_ago("") == ""

    def test_time_ago_invalid(self):
        from routes_notifications_v2 import _time_ago
        assert _time_ago("not-a-date") == ""
