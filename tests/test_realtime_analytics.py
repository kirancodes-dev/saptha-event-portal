"""
tests/test_realtime_analytics.py — Unit & Integration Tests for Phase 11

Verifies:
1. Registration-to-Attendance conversion funnel calculations and drop-off percentages.
2. Gate check-in velocity and peak hour scanner analytics.
3. Attendee demographic distributions (colleges, branches, t-shirt sizes).
4. Executive Business Intelligence report card generation.
5. REST API v1 endpoints for analytics and executive summaries.
"""

import pytest
import uuid
from auth_jwt import create_tokens
from services_analytics import AnalyticsService
from services_finance import FinanceEngine


@pytest.fixture
def admin_token():
    tokens = create_tokens(user_email="admin@saptha.org", role="SuperAdmin")
    return tokens["access_token"]


@pytest.fixture
def student_token():
    tokens = create_tokens(user_email="student@saptha.org", role="Student")
    return tokens["access_token"]


class TestConversionFunnelAndThroughput:
    """Verify conversion metrics and check-in velocity."""

    def test_conversion_funnel(self, mock_db):
        event_id = f"ev_funnel_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Global AI Summit",
            "view_count": 500,
            "capacity": 200,
        })

        # 4 registrations: 3 confirmed (2 checked-in), 1 pending
        mock_db.collection("registrations").document("r1").set({
            "id": "r1", "event_id": event_id, "payment_status": "paid", "attendance": "Present"
        })
        mock_db.collection("registrations").document("r2").set({
            "id": "r2", "event_id": event_id, "payment_status": "paid", "attendance": "Present"
        })
        mock_db.collection("registrations").document("r3").set({
            "id": "r3", "event_id": event_id, "payment_status": "paid", "attendance": "Absent"
        })
        mock_db.collection("registrations").document("r4").set({
            "id": "r4", "event_id": event_id, "payment_status": "pending", "attendance": "Absent"
        })

        res = AnalyticsService.get_event_conversion_funnel(mock_db, event_id)
        assert res["funnel"]["page_views"] == 500
        assert res["funnel"]["registrations_started"] == 4
        assert res["funnel"]["registrations_confirmed"] == 3
        assert res["funnel"]["attendees_checked_in"] == 2

        # Check conversion percentages
        assert res["conversion_rates"]["registration_to_confirmed_pct"] == 75.0
        assert round(res["conversion_rates"]["confirmed_to_attended_pct"], 1) == 66.7

    def test_gate_throughput_velocity(self, mock_db):
        event_id = f"ev_gate_{uuid.uuid4().hex[:6]}"

        # 2 tickets scanned at Gate 1, 1 at Gate VIP
        mock_db.collection("tickets").document("t1").set({
            "event_id": event_id, "status": "used", "gate_assignment": "Gate 1",
            "used_at": "2026-10-15T09:14:00Z"
        })
        mock_db.collection("tickets").document("t2").set({
            "event_id": event_id, "status": "used", "gate_assignment": "Gate 1",
            "used_at": "2026-10-15T09:42:00Z"
        })
        mock_db.collection("tickets").document("t3").set({
            "event_id": event_id, "status": "used", "gate_assignment": "Gate VIP",
            "used_at": "2026-10-15T10:05:00Z"
        })

        tp = AnalyticsService.get_gate_throughput_velocity(mock_db, event_id)
        assert tp["total_scanned"] == 3
        assert tp["gate_breakdown"]["Gate 1"] == 2
        assert tp["gate_breakdown"]["Gate VIP"] == 1
        assert tp["hourly_velocity"]["09:00"] == 2
        assert tp["hourly_velocity"]["10:00"] == 1
        assert tp["peak_hour"] == "09:00"


class TestDemographicsAndExecutiveSummary:
    """Verify demographic aggregation and executive report card."""

    def test_demographics_summary(self, mock_db):
        event_id = f"ev_demo_{uuid.uuid4().hex[:6]}"

        mock_db.collection("registrations").document("reg_d1").set({
            "event_id": event_id, "college": "MIT Manipal", "branch": "CSE", "tshirt_size": "L"
        })
        mock_db.collection("registrations").document("reg_d2").set({
            "event_id": event_id, "college": "MIT Manipal", "branch": "ISE", "tshirt_size": "M"
        })
        mock_db.collection("registrations").document("reg_d3").set({
            "event_id": event_id, "college": "RV College", "branch": "CSE", "tshirt_size": "L"
        })

        demo = AnalyticsService.get_demographics_summary(mock_db, event_id)
        assert demo["total_attendees"] == 3
        assert demo["institutions_breakdown"]["MIT Manipal"] == 2
        assert demo["institutions_breakdown"]["RV College"] == 1
        assert demo["branches_breakdown"]["CSE"] == 2
        assert demo["tshirt_sizes"]["L"] == 2
        assert demo["tshirt_sizes"]["M"] == 1

    def test_executive_summary_report(self, mock_db):
        event_id = f"ev_exec_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Hackathon 2026 Championship",
            "event_type": "hackathon",
            "capacity": 100,
            "view_count": 200,
        })

        mock_db.collection("registrations").document("reg_e1").set({
            "id": "reg_e1",
            "event_id": event_id,
            "payment_status": "paid",
            "attendance": "Present",
            "team_name": "AI Dynamos",
            "score_average": 96.5,
            "scores": {"j1": {"final_score": 96.5}},
        })

        FinanceEngine.record_transaction(
            mock_db,
            transaction_id="tx_e1",
            order_id="ord_e1",
            event_id=event_id,
            amount=5000.0,
            currency="INR",
            buyer_email="e1@saptha.org",
            status="success",
        )

        exec_sum = AnalyticsService.get_executive_summary(mock_db, event_id)
        assert exec_sum["event_title"] == "Hackathon 2026 Championship"
        assert exec_sum["capacity"] == 100
        assert exec_sum["capacity_utilization_pct"] == 1.0  # 1 confirmed / 100 capacity
        assert exec_sum["financial_summary"]["gross_revenue"] == 5000.0
        assert exec_sum["top_winner"]["team_name"] == "AI Dynamos"


class TestAnalyticsAPIEndpoints:
    """Verify REST API v1 endpoints for analytics."""

    def test_analytics_endpoints_require_admin(self, client, student_token, admin_token, mock_db):
        event_id = f"ev_api_an_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id, "title": "API Fest", "capacity": 50
        })

        # 1. Student access blocked
        resp_stud = client.get(
            f"/api/v1/analytics/events/{event_id}/funnel",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert resp_stud.status_code == 403

        # 2. Admin access succeeds
        resp_admin = client.get(
            f"/api/v1/analytics/events/{event_id}/funnel",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp_admin.status_code == 200
        assert "funnel" in resp_admin.get_json()["data"]

        # 3. Demographics API
        resp_demo = client.get(
            f"/api/v1/analytics/events/{event_id}/demographics",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp_demo.status_code == 200

        # 4. Executive Summary API
        resp_exec = client.get(
            f"/api/v1/analytics/events/{event_id}/executive-summary",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp_exec.status_code == 200
        assert resp_exec.get_json()["data"]["event_title"] == "API Fest"
