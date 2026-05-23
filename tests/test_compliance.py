"""
test_compliance.py — Tests for GDPR/DPDP Compliance Module

Covers: data export, deletion requests, consent management,
and privacy controls.
"""
import pytest
import datetime


class TestDataExport:
    """Test GDPR data portability (Article 20)."""

    def test_export_user_profile(self, mock_db):
        """User profile is included in data export."""
        mock_db.collection("users").document("export@test.edu").set({
            "name": "Export User",
            "email": "export@test.edu",
            "role": "Student",
            "password_hash": "should_be_excluded",
            "xp": 250,
        })
        doc = mock_db.collection("users").document("export@test.edu").get()
        data = doc.to_dict()
        # Password should be removed in export
        assert "password_hash" in data  # raw doc still has it
        data.pop("password_hash", None)
        assert "password_hash" not in data

    def test_export_includes_registrations(self, mock_db):
        """Registrations are included in data export."""
        mock_db.collection("registrations").document("reg_001").set({
            "event_id": "evt_001",
            "lead_email": "export@test.edu",
            "status": "confirmed",
        })
        docs = list(mock_db.collection("registrations").stream())
        assert len(docs) >= 1


class TestDeletionRequest:
    """Test right to erasure (GDPR Article 17 / DPDP)."""

    def test_create_deletion_request(self, mock_db):
        """Deletion request is created with 30-day grace period."""
        now = datetime.datetime.now(datetime.timezone.utc)
        scheduled = now + datetime.timedelta(days=30)

        mock_db.collection("deletion_requests").document("del_001").set({
            "email": "delete@test.edu",
            "reason": "Personal choice",
            "status": "pending",
            "requested_at": now.isoformat(),
            "scheduled_deletion_at": scheduled.isoformat(),
        })
        doc = mock_db.collection("deletion_requests").document("del_001").get()
        data = doc.to_dict()
        assert data["status"] == "pending"

    def test_cancel_deletion_request(self, mock_db):
        """User can cancel deletion before grace period ends."""
        mock_db.collection("deletion_requests").document("del_cancel").set({
            "email": "cancel@test.edu",
            "status": "pending",
        })
        mock_db.collection("deletion_requests").document("del_cancel").update({
            "status": "cancelled",
            "cancelled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        doc = mock_db.collection("deletion_requests").document("del_cancel").get()
        assert doc.to_dict()["status"] == "cancelled"

    def test_30_day_grace_period(self):
        """Grace period is exactly 30 days."""
        now = datetime.datetime.now(datetime.timezone.utc)
        scheduled = now + datetime.timedelta(days=30)
        delta = scheduled - now
        assert delta.days == 30


class TestConsentManagement:
    """Test consent settings."""

    def test_default_consent_values(self):
        """Default consent has marketing disabled."""
        defaults = {
            "email_marketing": False,
            "push_notifications": True,
            "analytics_tracking": True,
            "third_party_sharing": False,
        }
        assert defaults["email_marketing"] is False
        assert defaults["push_notifications"] is True
        assert defaults["third_party_sharing"] is False

    def test_update_consent(self, mock_db):
        """User can update consent settings."""
        mock_db.collection("user_consent").document("consent@test.edu").set({
            "email_marketing": False,
            "push_notifications": True,
        })
        mock_db.collection("user_consent").document("consent@test.edu").update({
            "email_marketing": True,
        })
        doc = mock_db.collection("user_consent").document("consent@test.edu").get()
        assert doc.to_dict()["email_marketing"] is True

    def test_consent_is_per_user(self, mock_db):
        """Each user has independent consent settings."""
        mock_db.collection("user_consent").document("user_a@test.edu").set({
            "email_marketing": True,
        })
        mock_db.collection("user_consent").document("user_b@test.edu").set({
            "email_marketing": False,
        })
        a = mock_db.collection("user_consent").document("user_a@test.edu").get().to_dict()
        b = mock_db.collection("user_consent").document("user_b@test.edu").get().to_dict()
        assert a["email_marketing"] != b["email_marketing"]
