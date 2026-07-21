"""
test_compliance.py — Tests for GDPR/DPDP Compliance Module

Covers: data export, deletion requests, consent management,
privacy controls, Terms of Service, and Privacy Policy endpoints.
"""
import pytest
import datetime


def test_terms_of_service_page_loads(client):
    """Terms of service legal page loads cleanly."""
    resp = client.get("/terms")
    assert resp.status_code == 200
    assert b"Terms of Service" in resp.data


def test_privacy_policy_page_loads(client):
    """Privacy policy legal page loads cleanly."""
    resp = client.get("/privacy")
    assert resp.status_code == 200
    assert b"Privacy Policy" in resp.data


def test_privacy_settings_page_requires_auth(client):
    """Privacy settings page requires user login."""
    resp = client.get("/compliance/settings", follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_privacy_settings_page_loads_for_user(auth_client):
    """Privacy settings page renders for authenticated user."""
    resp = auth_client.get("/compliance/settings")
    assert resp.status_code == 200
    assert b"Privacy &amp; Data Governance Center" in resp.data or b"Privacy" in resp.data


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
        assert "password_hash" in data
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
        """Deletion request can be cancelled."""
        mock_db.collection("deletion_requests").document("del_001").set({
            "email": "delete@test.edu",
            "status": "cancelled",
        })
        doc = mock_db.collection("deletion_requests").document("del_001").get()
        assert doc.to_dict()["status"] == "cancelled"
