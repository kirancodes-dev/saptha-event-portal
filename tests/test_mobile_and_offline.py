"""
tests/test_mobile_and_offline.py — Unit & Integration Tests for Phase 5

Verifies:
1. Persistent mobile bottom navigation bar integration in templates.
2. Offline attendee/ticket manifest endpoint (/api/v1/events/<id>/ticket-manifest).
3. Batch offline check-in synchronization with conflict resolution (/api/v1/events/<id>/checkin-batch).
4. Dedicated Coordinator Scan HUD view (/coordinator/scan-hud/<event_id>).
"""

import pytest
import uuid
import datetime
from auth_jwt import create_tokens
from services_ticket import TicketService


@pytest.fixture
def coordinator_token():
    tokens = create_tokens(user_email="coord@saptha.org", role="EventCoordinator")
    return tokens["access_token"]


@pytest.fixture
def admin_token():
    tokens = create_tokens(user_email="admin@saptha.org", role="SuperAdmin")
    return tokens["access_token"]


class TestMobileBottomNavigation:
    """Verify persistent mobile navigation presence and links."""

    def test_mobile_nav_template_structure(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "mobile-nav-bar" in html
        assert "Explore" in html
        assert "Tickets" in html
        assert "Results" in html
        assert "Home" in html


class TestOfflineTicketManifest:
    """Verify offline ticket manifest download for IndexedDB caching."""

    def test_get_ticket_manifest_success(self, client, coordinator_token, mock_db):
        event_id = f"ev_manifest_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Offline Summit 2026",
            "capacity": 200,
        })

        # Issue 2 tickets for this event
        t1 = TicketService.issue_ticket(
            mock_db,
            event_id=event_id,
            registration_id="reg_1",
            user_email="user1@saptha.org",
            lead_name="Alice User",
            ticket_type="VIP",
        )
        t2 = TicketService.issue_ticket(
            mock_db,
            event_id=event_id,
            registration_id="reg_2",
            user_email="user2@saptha.org",
            lead_name="Bob User",
            ticket_type="Student",
        )

        resp = client.get(
            f"/api/v1/events/{event_id}/ticket-manifest",
            headers={"Authorization": f"Bearer {coordinator_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        manifest = data["data"]
        assert manifest["event_id"] == event_id
        assert manifest["total_tickets"] >= 2

        ticket_codes = [t["ticket_code"] for t in manifest["tickets"]]
        assert t1["ticket_code"] in ticket_codes
        assert t2["ticket_code"] in ticket_codes

    def test_manifest_nonexistent_event_returns_404(self, client, coordinator_token):
        resp = client.get(
            "/api/v1/events/nonexistent_event_xyz/ticket-manifest",
            headers={"Authorization": f"Bearer {coordinator_token}"},
        )
        assert resp.status_code == 404


class TestBatchCheckinSyncAndConflictResolution:
    """Verify batch synchronization and earliest-timestamp conflict resolution."""

    def test_batch_sync_with_conflict_resolution(self, client, coordinator_token, mock_db):
        event_id = f"ev_batch_{uuid.uuid4().hex[:6]}"
        reg_id = f"reg_batch_{uuid.uuid4().hex[:6]}"

        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Batch Sync Event",
        })
        mock_db.collection("registrations").document(reg_id).set({
            "id": reg_id,
            "event_id": event_id,
            "fee": 0.0,
            "status": "Confirmed",
        })

        tkt = TicketService.issue_ticket(
            mock_db,
            event_id=event_id,
            registration_id=reg_id,
            user_email="batch_user@saptha.org",
            lead_name="Charlie Test",
        )

        # 2 scanners scanned the same ticket offline at different timestamps
        payload = {
            "checkins": [
                {
                    "ticket_id": tkt["ticket_code"],
                    "scanned_at": "2026-09-16T10:05:00Z",  # Later scan
                    "actor_id": "scanner_device_2",
                },
                {
                    "ticket_id": tkt["ticket_code"],
                    "scanned_at": "2026-09-16T10:00:00Z",  # Earlier scan -> Should win!
                    "actor_id": "scanner_device_1",
                },
            ]
        }

        resp = client.post(
            f"/api/v1/events/{event_id}/checkin-batch",
            json=payload,
            headers={"Authorization": f"Bearer {coordinator_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        res_data = data["data"]
        assert res_data["processed_count"] == 2
        assert res_data["synced_count"] == 1
        assert res_data["duplicate_count"] == 1


class TestCoordinatorScanHUD:
    """Verify Coordinator Scan HUD page loads."""

    def test_scan_hud_page_renders(self, client, mock_db):
        event_id = f"ev_hud_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Scan HUD Test Event",
            "registration_count": 50,
            "checkin_count": 12,
        })

        with client.session_transaction() as sess:
            sess["user_id"] = "coord@saptha.org"
            sess["role"] = "EventCoordinator"

        resp = client.get(f"/coordinator/scan-hud/{event_id}")
        assert resp.status_code == 200
        assert b"Scan HUD Test Event" in resp.data
        assert b"qr-reader" in resp.data
        assert b"scan-laser" in resp.data
