"""
tests/test_workflow_engine.py — Comprehensive Unit Tests for Universal Templates & Workflow State Machine

Verifies Phase 3 requirements:
1. Turnkey template library with 7 pre-built presets.
2. Event instantiation from template with form and rubric propagation.
3. Event lifecycle state machine with guarded transitions.
4. Participant workflow state machine with prerequisite guards.
5. Immutable audit logging for all state mutations.
6. REST API v1 endpoints for templates and workflow transitions.
"""

import pytest
import uuid
from datetime import datetime, timezone

from services_templates import TemplateService, TEMPLATES_CATALOG
from services_workflow import (
    WorkflowEngine,
    WorkflowError,
    EVENT_STATE_TRANSITIONS,
    PARTICIPANT_STATE_TRANSITIONS,
)
from auth_jwt import create_tokens


# ═══════════════════════════════════════════════════════════════════════
# 1. TEMPLATE LIBRARY TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestTemplateLibrary:
    """Test template catalog definitions and integrity."""

    EXPECTED_TEMPLATES = [
        "hackathon",
        "conference",
        "workshop",
        "seminar",
        "sports",
        "cultural",
        "webinar",
    ]

    def test_all_expected_templates_present(self):
        for t_id in self.EXPECTED_TEMPLATES:
            assert t_id in TEMPLATES_CATALOG, f"Template '{t_id}' missing from catalog"

    def test_templates_have_complete_specifications(self):
        required_keys = [
            "id",
            "name",
            "category",
            "event_type",
            "event_mode",
            "description",
            "pricing_type",
            "fee",
            "currency",
            "capacity",
            "workflow_config",
            "form_config",
            "evaluation_config",
            "ticket_tiers",
            "notification_rules",
            "certificate_config",
        ]
        for t_id, tmpl in TEMPLATES_CATALOG.items():
            for key in required_keys:
                assert key in tmpl, f"Template '{t_id}' missing required key '{key}'"

    def test_list_templates_returns_summaries(self):
        summaries = TemplateService.list_templates()
        assert len(summaries) >= 7
        ids = [s["id"] for s in summaries]
        for t_id in self.EXPECTED_TEMPLATES:
            assert t_id in ids

    def test_get_template_returns_deep_copy(self):
        t1 = TemplateService.get_template("hackathon")
        t2 = TemplateService.get_template("hackathon")
        assert t1 is not None
        assert t2 is not None
        assert t1["id"] == "hackathon"
        # Mutation in t1 should not affect t2
        t1["name"] = "Mutated Name"
        assert t2["name"] != "Mutated Name"

    def test_get_unknown_template_returns_none(self):
        assert TemplateService.get_template("nonexistent_template_xyz") is None


# ═══════════════════════════════════════════════════════════════════════
# 2. TEMPLATE INSTANTIATION TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestTemplateInstantiation:
    """Test creating live events and schemas from templates."""

    def test_instantiate_hackathon_event(self, mock_db):
        event = TemplateService.instantiate_event(
            mock_db,
            template_id="hackathon",
            title="Global AI Hackathon 2026",
            date_str="2026-11-20",
            venue="Tech Innovation Hub",
            created_by="lead@hackathon.org",
        )

        assert event["id"] is not None
        assert event["title"] == "Global AI Hackathon 2026"
        assert event["event_type"] == "hackathon"
        assert event["template_id"] == "hackathon"
        assert len(event["ticket_tiers"]) >= 4

        # Verify dynamic form was written to event_forms
        form_doc = mock_db.collection("event_forms").document(event["id"]).get()
        assert form_doc.exists
        form_data = form_doc.to_dict()
        assert len(form_data["fields"]) >= 4
        field_names = [f["field_name"] for f in form_data["fields"]]
        assert "team_name" in field_names
        assert "github_url" in field_names

    def test_instantiate_with_overrides(self, mock_db):
        overrides = {
            "capacity": 50,
            "pricing_type": "paid",
            "fee": 999.0,
            "description": "Overridden description",
        }
        event = TemplateService.instantiate_event(
            mock_db,
            template_id="workshop",
            title="Advanced Rust Workshop",
            date_str="2026-12-05",
            overrides=overrides,
        )

        assert event["capacity"] == 50
        assert event["pricing_type"] == "paid"
        assert event["fee"] == 999.0
        assert event["description"] == "Overridden description"

    def test_instantiate_invalid_template_raises_error(self, mock_db):
        with pytest.raises(ValueError) as exc:
            TemplateService.instantiate_event(
                mock_db,
                template_id="unknown_event_type",
                title="Bad Event",
                date_str="2026-10-10",
            )
        assert "Unknown event template" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════
# 3. EVENT WORKFLOW STATE MACHINE TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestEventWorkflowStateMachine:
    """Test guarded state transitions for event lifecycles."""

    def test_valid_lifecycle_progression(self, mock_db):
        event_id = f"ev_{uuid.uuid4().hex[:8]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "State Progression Test",
            "status": "draft",
        })

        # draft -> published
        updated = WorkflowEngine.transition_event(
            mock_db, event_id=event_id, target_state="published", actor_id="admin@saptha.org"
        )
        assert updated["status"] == "published"
        assert "published" in updated["stage_timestamps"]

        # published -> registration_open
        updated = WorkflowEngine.transition_event(
            mock_db, event_id=event_id, target_state="registration_open", actor_id="admin@saptha.org"
        )
        assert updated["status"] == "registration_open"

        # registration_open -> in_progress
        updated = WorkflowEngine.transition_event(
            mock_db, event_id=event_id, target_state="in_progress", actor_id="admin@saptha.org"
        )
        assert updated["status"] == "in_progress"

        # in_progress -> completed
        updated = WorkflowEngine.transition_event(
            mock_db, event_id=event_id, target_state="completed", actor_id="admin@saptha.org"
        )
        assert updated["status"] == "completed"

    def test_invalid_lifecycle_transition_rejected(self, mock_db):
        event_id = f"ev_{uuid.uuid4().hex[:8]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Invalid Transition Test",
            "status": "draft",
        })

        # draft cannot jump straight to completed
        with pytest.raises(WorkflowError) as exc:
            WorkflowEngine.transition_event(
                mock_db, event_id=event_id, target_state="completed", actor_id="spoc@saptha.org"
            )
        assert "Invalid event transition" in str(exc.value)

    def test_force_flag_bypasses_transition_restriction(self, mock_db):
        event_id = f"ev_{uuid.uuid4().hex[:8]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Emergency Bypass Test",
            "status": "draft",
        })

        # SuperAdmin forced jump directly from draft to completed
        updated = WorkflowEngine.transition_event(
            mock_db, event_id=event_id, target_state="completed", force=True, actor_id="super@saptha.org"
        )
        assert updated["status"] == "completed"


# ═══════════════════════════════════════════════════════════════════════
# 4. PARTICIPANT WORKFLOW STATE MACHINE TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestParticipantWorkflowStateMachine:
    """Test participant progression with prerequisite domain guards."""

    def test_valid_participant_progression(self, mock_db):
        reg_id = f"reg_{uuid.uuid4().hex[:8]}"
        mock_db.collection("registrations").document(reg_id).set({
            "id": reg_id,
            "event_id": "ev_test_123",
            "user_email": "participant@saptha.org",
            "status": "applied",
            "fee": 0.0,
        })

        # applied -> confirmed
        updated = WorkflowEngine.transition_participant(
            mock_db, registration_id=reg_id, target_state="confirmed"
        )
        assert updated["status"] == "confirmed"

        # confirmed -> checked_in
        updated = WorkflowEngine.transition_participant(
            mock_db, registration_id=reg_id, target_state="checked_in", actor_id="scanner@desk.com"
        )
        assert updated["status"] == "checked_in"
        assert updated["checked_in"] is True
        assert updated["checked_in_by"] == "scanner@desk.com"

        # checked_in -> shortlisted
        updated = WorkflowEngine.transition_participant(
            mock_db, registration_id=reg_id, target_state="shortlisted"
        )
        assert updated["status"] == "shortlisted"

        # shortlisted -> winner
        updated = WorkflowEngine.transition_participant(
            mock_db, registration_id=reg_id, target_state="winner"
        )
        assert updated["status"] == "winner"

        # winner -> certified
        updated = WorkflowEngine.transition_participant(
            mock_db, registration_id=reg_id, target_state="certified"
        )
        assert updated["status"] == "certified"

    def test_checkin_guard_requires_confirmed_status(self, mock_db):
        reg_id = f"reg_{uuid.uuid4().hex[:8]}"
        mock_db.collection("registrations").document(reg_id).set({
            "id": reg_id,
            "event_id": "ev_test_123",
            "status": "applied",  # Not confirmed yet
        })

        with pytest.raises(WorkflowError) as exc:
            WorkflowEngine.transition_participant(
                mock_db, registration_id=reg_id, target_state="checked_in"
            )
        assert "Cannot check in participant from 'applied'" in str(exc.value)

    def test_payment_guard_blocks_unpaid_confirmation(self, mock_db):
        reg_id = f"reg_{uuid.uuid4().hex[:8]}"
        mock_db.collection("registrations").document(reg_id).set({
            "id": reg_id,
            "event_id": "ev_test_paid",
            "status": "applied",
            "fee": 1500.0,
            "payment_status": "unpaid",
        })

        with pytest.raises(WorkflowError) as exc:
            WorkflowEngine.transition_participant(
                mock_db, registration_id=reg_id, target_state="confirmed"
            )
        assert "outstanding payment" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════
# 5. WORKFLOW AUDIT TRAIL TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestWorkflowAuditTrail:
    """Test that all state transitions create immutable audit records."""

    def test_audit_log_created_on_transition(self, mock_db):
        event_id = f"ev_audit_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Audit Trail Test",
            "status": "draft",
        })

        WorkflowEngine.transition_event(
            mock_db,
            event_id=event_id,
            target_state="published",
            actor_id="admin@saptha.org",
            reason="Public announcement approved",
            metadata={"source": "admin_portal"},
        )

        history = WorkflowEngine.get_workflow_history(mock_db, entity_type="event", entity_id=event_id)
        assert len(history) >= 1
        record = history[0]
        assert record["from_state"] == "draft"
        assert record["to_state"] == "published"
        assert record["actor_id"] == "admin@saptha.org"
        assert record["reason"] == "Public announcement approved"
        assert record["metadata"].get("source") == "admin_portal"


# ═══════════════════════════════════════════════════════════════════════
# 6. REST API V1 INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestWorkflowAPIEndpoints:
    """Test HTTP API routes for templates and workflow operations."""

    @pytest.fixture
    def admin_token(self):
        tokens = create_tokens(user_email="superadmin@saptha.org", role="SuperAdmin")
        return tokens["access_token"]

    def test_api_list_templates(self, client):
        resp = client.get("/api/v1/templates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["data"]["count"] >= 7

    def test_api_get_template(self, client):
        resp = client.get("/api/v1/templates/hackathon")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["data"]["id"] == "hackathon"
        assert "workflow_config" in data["data"]

    def test_api_get_unknown_template_returns_404(self, client):
        resp = client.get("/api/v1/templates/unknown_template_xyz")
        assert resp.status_code == 404

    def test_api_create_event_from_template(self, client, admin_token):
        payload = {
            "template_id": "conference",
            "title": "International Tech Summit 2026",
            "date": "2026-11-25",
            "venue": "Grand Hall",
        }
        resp = client.post(
            "/api/v1/events/from-template",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["data"]["event_type"] == "conference"
        assert data["data"]["template_id"] == "conference"

    def test_api_workflow_transition(self, client, admin_token, mock_db):
        event_id = f"ev_api_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "API Workflow Test",
            "status": "draft",
        })

        resp = client.post(
            f"/api/v1/events/{event_id}/workflow-transition",
            json={"target_state": "published", "reason": "Approved by Chair"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["data"]["status"] == "published"

    def test_api_workflow_history(self, client, admin_token, mock_db):
        event_id = f"ev_hist_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "History Test",
            "status": "draft",
        })

        # Perform transition first
        client.post(
            f"/api/v1/events/{event_id}/workflow-transition",
            json={"target_state": "published"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Get history
        resp = client.get(
            f"/api/v1/workflow/history/event/{event_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["data"]["count"] >= 1
