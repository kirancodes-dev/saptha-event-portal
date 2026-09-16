"""
tests/test_control_plane.py — Unit & Integration Tests for Phase 9

Verifies:
1. Platform overview metrics aggregation across organizations, events, registrations.
2. Subscription tier quota enforcement (free vs pro vs enterprise).
3. Organization plan updates and setting adjustments.
4. Organization suspension / reactivation lifecycle.
5. SuperAdmin support impersonation audit trail.
6. SuperAdmin REST API v1 endpoints for multi-tenant control plane.
"""

import pytest
import uuid
from auth_jwt import create_tokens
from services_control_plane import ControlPlaneService


@pytest.fixture
def superadmin_token():
    tokens = create_tokens(user_email="superadmin@saptha.org", role="SuperAdmin")
    return tokens["access_token"]


@pytest.fixture
def student_token():
    tokens = create_tokens(user_email="student@saptha.org", role="Student")
    return tokens["access_token"]


class TestControlPlaneMetricsAndQuotas:
    """Verify metrics aggregation and plan limits."""

    def test_platform_overview_metrics(self, mock_db):
        mock_db.collection("organizations").document("org_1").set({
            "name": "MIT Manipal", "plan": "pro", "is_active": True, "status": "active"
        })
        mock_db.collection("organizations").document("org_2").set({
            "name": "RV College", "plan": "free", "is_active": True, "status": "active"
        })
        mock_db.collection("events").document("ev_1").set({"title": "Summit 1"})

        overview = ControlPlaneService.get_platform_overview(mock_db)
        assert overview["total_organizations"] == 2
        assert overview["active_organizations"] == 2
        assert overview["plans_distribution"]["pro"] == 1
        assert overview["plans_distribution"]["free"] == 1
        assert overview["total_events"] == 1

    def test_quota_enforcement_free_plan(self, mock_db):
        org_id = f"org_{uuid.uuid4().hex[:6]}"
        mock_db.collection("organizations").document(org_id).set({
            "name": "Free Academy",
            "plan": "free",
            "is_active": True,
            "status": "active",
        })

        # Add 5 events (free plan quota is 5)
        for i in range(5):
            mock_db.collection("events").document(f"ev_{org_id}_{i}").set({
                "organization_id": org_id,
                "title": f"Event {i}"
            })

        # Check quota for 6th event -> should be blocked
        allowed, reason, usage = ControlPlaneService.check_tenant_quota(mock_db, org_id, action="create_event")
        assert allowed is False
        assert "event limit reached" in reason

        # Upgrade to pro plan
        ControlPlaneService.update_organization_plan(mock_db, org_id, "pro", actor_email="super@saptha.org")

        # Re-check quota -> should now be allowed (pro allows 50 events)
        allowed_pro, reason_pro, usage_pro = ControlPlaneService.check_tenant_quota(mock_db, org_id, action="create_event")
        assert allowed_pro is True
        assert usage_pro["plan"] == "pro"


class TestTenantLifecycleAndAudit:
    """Verify tenant status toggles and impersonation logs."""

    def test_toggle_organization_status(self, mock_db):
        org_id = f"org_toggle_{uuid.uuid4().hex[:6]}"
        mock_db.collection("organizations").document(org_id).set({
            "name": "Test College",
            "plan": "free",
            "is_active": True,
            "status": "active",
        })

        # Suspend organization
        res = ControlPlaneService.toggle_organization_status(
            mock_db,
            org_id=org_id,
            status="suspended",
            actor_email="admin@saptha.org",
            reason="Violation of terms",
        )
        assert res["status"] == "suspended"
        assert res["is_active"] is False

        # Quota check on suspended org must fail
        allowed, reason, _ = ControlPlaneService.check_tenant_quota(mock_db, org_id, action="create_event")
        assert allowed is False
        assert "suspended" in reason

        # Reactivate organization
        res_active = ControlPlaneService.toggle_organization_status(
            mock_db,
            org_id=org_id,
            status="active",
            actor_email="admin@saptha.org",
        )
        assert res_active["status"] == "active"
        assert res_active["is_active"] is True

    def test_impersonation_session_logging(self, mock_db):
        log = ControlPlaneService.log_impersonation_session(
            mock_db,
            superadmin_email="super@saptha.org",
            target_org_id="org_support_1",
            reason="Fixing domain routing",
        )
        assert log["session_id"].startswith("imp_")
        assert log["superadmin_email"] == "super@saptha.org"
        assert log["target_org_id"] == "org_support_1"


class TestControlPlaneEndpoints:
    """Verify REST API v1 endpoints for Control Plane."""

    def test_overview_requires_superadmin(self, client, student_token, superadmin_token):
        # 1. Student access -> 403 Forbidden
        resp_stud = client.get(
            "/api/v1/control-plane/overview",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert resp_stud.status_code == 403

        # 2. SuperAdmin access -> 200 OK
        resp_admin = client.get(
            "/api/v1/control-plane/overview",
            headers={"Authorization": f"Bearer {superadmin_token}"}
        )
        assert resp_admin.status_code == 200
        data = resp_admin.get_json()["data"]
        assert "total_organizations" in data

    def test_update_plan_and_status_api(self, client, superadmin_token, mock_db):
        org_id = f"org_api_{uuid.uuid4().hex[:6]}"
        mock_db.collection("organizations").document(org_id).set({
            "name": "API Uni", "plan": "free", "is_active": True, "status": "active"
        })

        # Update plan via API
        resp_plan = client.post(
            f"/api/v1/control-plane/orgs/{org_id}/plan",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"plan": "enterprise"}
        )
        assert resp_plan.status_code == 200
        assert resp_plan.get_json()["data"]["new_plan"] == "enterprise"

        # Toggle status via API
        resp_status = client.post(
            f"/api/v1/control-plane/orgs/{org_id}/status",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"status": "suspended", "reason": "Audit hold"}
        )
        assert resp_status.status_code == 200
        assert resp_status.get_json()["data"]["status"] == "suspended"

        # Log impersonation via API
        resp_imp = client.post(
            "/api/v1/control-plane/impersonate",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"target_org_id": org_id, "reason": "Testing tenant config"}
        )
        assert resp_imp.status_code == 201
        assert resp_imp.get_json()["data"]["session_id"].startswith("imp_")
