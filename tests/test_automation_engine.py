"""
tests/test_automation_engine.py — Unit & Integration Tests for Phase 7

Verifies:
1. Template variable rendering and substitution.
2. User notification preference enforcement (email, push, whatsapp).
3. Automated trigger dispatching across multi-channels.
4. Idempotency deduplication keys preventing duplicate notifications.
5. Broadcast notification trigger to all event participants.
6. REST API v1 endpoints for automation triggers and broadcasts.
"""

import pytest
import uuid
from auth_jwt import create_tokens
from services_automation import NotificationAutomationEngine, SYSTEM_DEFAULT_RULES


@pytest.fixture
def admin_token():
    tokens = create_tokens(user_email="admin@saptha.org", role="SuperAdmin")
    return tokens["access_token"]


@pytest.fixture
def coord_token():
    tokens = create_tokens(user_email="coord@saptha.org", role="EventCoordinator")
    return tokens["access_token"]


class TestTemplateInterpolation:
    """Verify template engine variable resolution."""

    def test_variable_interpolation(self):
        tmpl = "Hello {{recipient_name}}, your ticket for {{event_title}} is {{ticket_code}}."
        ctx = {
            "recipient_name": "Rohan",
            "event_title": "AI Summit 2026",
            "ticket_code": "TICK-12345",
        }
        res = NotificationAutomationEngine.render_template(tmpl, ctx)
        assert res == "Hello Rohan, your ticket for AI Summit 2026 is TICK-12345."

    def test_missing_variable_leaves_placeholder(self):
        tmpl = "Welcome {{recipient_name}} to {{unknown_variable}}!"
        ctx = {"recipient_name": "Kiran"}
        res = NotificationAutomationEngine.render_template(tmpl, ctx)
        assert res == "Welcome Kiran to {{unknown_variable}}!"


class TestPreferenceGatingAndIdempotency:
    """Verify channel preference check and deduplication."""

    def test_user_preference_opt_out(self, mock_db):
        email = "optout@saptha.org"
        mock_db.collection("notification_preferences").document(email).set({
            "email_enabled": False,
            "whatsapp_enabled": False,
        })

        allowed_email = NotificationAutomationEngine.check_user_preferences(mock_db, email, "email", "announcement")
        assert allowed_email is False

        allowed_inapp = NotificationAutomationEngine.check_user_preferences(mock_db, email, "in_app", "announcement")
        assert allowed_inapp is True

    def test_idempotency_prevents_duplicate_dispatch(self, mock_db):
        key = f"dedup_key_{uuid.uuid4().hex[:8]}"
        ctx = {
            "recipient_name": "Kiran",
            "recipient_email": "kiran@saptha.org",
            "event_title": "Hackathon 2026",
            "ticket_url": "/tickets/123/pass",
        }

        # 1st dispatch
        res1 = NotificationAutomationEngine.dispatch_trigger(
            mock_db,
            trigger_name="on_registration_created",
            context=ctx,
            idempotency_key=key,
        )
        assert res1["status"] == "success"

        # 2nd dispatch with same key
        res2 = NotificationAutomationEngine.dispatch_trigger(
            mock_db,
            trigger_name="on_registration_created",
            context=ctx,
            idempotency_key=key,
        )
        assert res2["status"] == "skipped"
        assert "Already dispatched" in res2["reason"]


class TestAutomationBroadcastAndEndpoints:
    """Verify event-wide broadcast and API endpoints."""

    def test_broadcast_event_trigger(self, mock_db):
        event_id = f"ev_auto_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "National Tech Fest",
            "venue": {"name": "Convention Hall B"},
            "start_datetime": "2026-11-01T10:00:00Z",
        })

        # Register 2 attendees
        mock_db.collection("registrations").document("reg_b1").set({
            "id": "reg_b1", "event_id": event_id, "lead_name": "User 1", "lead_email": "user1@saptha.org",
        })
        mock_db.collection("registrations").document("reg_b2").set({
            "id": "reg_b2", "event_id": event_id, "lead_name": "User 2", "lead_email": "user2@saptha.org",
        })

        results = NotificationAutomationEngine.broadcast_event_trigger(
            mock_db,
            event_id=event_id,
            trigger_name="on_event_reminder",
        )
        assert len(results) == 2
        assert all(r["status"] == "success" for r in results)

    def test_api_broadcast_and_single_trigger(self, client, admin_token, coord_token, mock_db):
        event_id = f"ev_api_auto_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Cyber Conclave 2026",
            "venue": "Cyber Dome",
        })
        mock_db.collection("registrations").document("reg_c1").set({
            "id": "reg_c1", "event_id": event_id, "lead_name": "Alice", "lead_email": "alice@saptha.org",
        })

        # 1. API Broadcast
        resp = client.post(
            f"/api/v1/events/{event_id}/broadcast",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"trigger_name": "on_event_reminder"}
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["broadcast_count"] == 1

        # 2. Single Trigger API
        resp_single = client.post(
            "/api/v1/notifications/trigger",
            headers={"Authorization": f"Bearer {coord_token}"},
            json={
                "trigger_name": "on_checkin_verified",
                "context": {
                    "recipient_email": "alice@saptha.org",
                    "recipient_name": "Alice",
                    "event_title": "Cyber Conclave 2026",
                    "venue_name": "Cyber Dome",
                    "gate_assignment": "Gate VIP",
                }
            }
        )
        assert resp_single.status_code == 200
        data_single = resp_single.get_json()["data"]
        assert data_single["status"] == "success"
        assert "Welcome to Cyber Conclave 2026!" in data_single["title"]
