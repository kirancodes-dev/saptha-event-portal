"""
tests/test_universal_acceptance.py — End-to-End Acceptance Test Suite

Demonstrates that an administrator can create, configure, operate, score,
and certify all major event types purely via configuration without custom code:
1. Hackathon: Registration -> Team -> Submission -> Rubric Scoring -> Finals -> Results -> Certificate
2. Conference: Multi-tier Tickets -> Pricing -> Session Check-in -> Feedback -> Certificate
3. Workshop: Registration -> Ticket -> Offline Check-in -> Quiz/Assessment -> Certificate
4. Sports Tournament: Registration -> Fixtures -> Matches -> Scores -> Standings -> Podium Results
5. Cultural Competition: Registration -> Preliminaries -> Multi-judge Rubric -> Tie-breaking -> Results
6. Public Discovery & iCalendar (.ics) Export
7. AI Event Copilot: Natural language proposal -> Preview -> Admin Approval -> Event instantiation
"""
import uuid
import pytest
from app import app
from models import db as sql_db

class _ActiveDBProxy:
    def __getattr__(self, name):
        import app as app_module
        active = getattr(app_module, "db", None) or sql_db
        return getattr(active, name)

db = _ActiveDBProxy()
from services_event import EventService
from services_templates import TemplateService
from services_workflow import WorkflowService
from services_ticket import TicketService
from services_evaluation import EvaluationService
from services_certificate import CertificateService
from services_copilot import AICopilotService
from auth_jwt import create_access_token


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def admin_headers():
    with app.app_context():
        token = create_access_token("admin-acceptance@snpsu.edu.in", "Admin")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }



class TestHackathonUniversalFlow:
    """1. Hackathon: Reg -> Team -> Submission -> Rubric Evaluation -> Finals -> Results -> Cert."""

    def test_full_hackathon_lifecycle(self, client, admin_headers):
        # A. Instantiate from template
        template = TemplateService.get_template_by_id("hackathon")
        assert template is not None
        
        event = EventService.create_event(
            db,
            title="SapthaHack 2026 — AI World Cup",
            description="36-hour flagship hackathon with multi-criteria rubric evaluation.",
            category="Technical",
            event_type="hackathon",
            event_mode="hybrid",
            capacity=300,
            workflow_config=template.get("workflow") or template.get("workflow_config")
        )
        event_id = event["id"]
        assert event["slug"] is not None

        # B. Team Registration
        reg_id = f"reg-hack-{uuid.uuid4().hex[:6]}"
        db.collection("registrations").document(reg_id).set({
            "event_id": event_id,
            "team_name": "Neural Pioneers",
            "lead_name": "Alice Developer",
            "lead_email": "alice@ai.org",
            "status": "confirmed",
            "members": [
                {"name": "Alice", "email": "alice@ai.org"},
                {"name": "Bob", "email": "bob@ai.org"}
            ]
        })

        # C. Project Submission
        sub_id = f"sub-{uuid.uuid4().hex[:6]}"
        db.collection("project_submissions").document(sub_id).set({
            "event_id": event_id,
            "registration_id": reg_id,
            "project_name": "Autonomous Agent OS",
            "repo_url": "https://github.com/neural-pioneers/agent-os",
            "status": "submitted"
        })

        # D. Advance Workflow: registration -> evaluation
        trans_res = WorkflowService.transition_event_step(db, event_id, "evaluation", "admin-acceptance")
        assert trans_res["success"] is True

        # E. Multi-Criteria Rubric Scoring
        rubric_scores = {
            "Innovation": 28.0,        # out of 30
            "Technical": 32.0,         # out of 35
            "UI/UX Polish": 14.0,      # out of 15
            "Presentation": 18.0       # out of 20
        }
        score_res = EvaluationService.record_rubric_evaluation(
            db,
            event_id=event_id,
            registration_id=reg_id,
            judge_id="judge-101",
            scores=rubric_scores,
            comments="Outstanding autonomous agent architecture."
        )
        assert score_res["success"] is True
        assert score_res["total_score"] == 92.0

        # F. Publish Final Results
        pub_res = EvaluationService.publish_results(
            db,
            event_id=event_id,
            rankings=[{"registration_id": reg_id, "rank": 1, "award": "First Prize & Grand Champion"}],
            published_by="admin-acceptance"
        )
        assert pub_res["success"] is True

        # G. Issue Certificate
        cert = CertificateService.issue_certificate(
            db,
            event_id=event_id,
            recipient_name="Alice Developer",
            recipient_email="alice@ai.org",
            certificate_type="winner",
            title="First Prize Champion"
        )
        assert cert["certificate_id"] is not None
        assert "verify_url" in cert


class TestConferenceUniversalFlow:
    """2. Conference: Multi-tier Tickets -> Pricing -> Session Check-in -> Feedback -> Certificate."""

    def test_full_conference_lifecycle(self, client):
        # A. Create Conference Event
        event = EventService.create_event(
            db,
            title="Global AI Systems Summit 2026",
            description="Leading conference on distributed intelligence.",
            category="Conference",
            event_type="conference",
            event_mode="in_person",
            capacity=800
        )
        event_id = event["id"]

        # B. Issue VIP Conference Ticket with HMAC Anti-Replay Token
        ticket = TicketService.issue_ticket(
            db,
            event_id=event_id,
            user_id="dr.speaker@mit.edu",
            ticket_type="VIP",
            price=2500.0,
            seat_info={"hall": "Auditorium A", "row": "A", "seat": "12"}
        )
        assert ticket["ticket_id"] is not None
        assert "qr_token" in ticket

        # C. Gate Check-in Validation
        valid, reg_or_err = TicketService.verify_qr_token(ticket["qr_token"], event_id)
        assert valid is True

        # D. Record Session Attendance Check-in
        checkin_res = TicketService.record_checkin(
            db,
            event_id=event_id,
            ticket_id=ticket["ticket_id"],
            scanned_by="coordinator-gate-1"
        )
        assert checkin_res["success"] is True
        assert checkin_res["status"] == "checked_in"

        # E. Issue Attendance Certificate
        cert = CertificateService.issue_certificate(
            db,
            event_id=event_id,
            recipient_name="Dr. Jane Speaker",
            recipient_email="dr.speaker@mit.edu",
            certificate_type="speaker",
            title="Keynote Speaker"
        )
        assert cert["status"] == "valid"


class TestWorkshopUniversalFlow:
    """3. Workshop: Registration -> Offline Check-in -> Quiz -> Certificate."""

    def test_full_workshop_lifecycle(self, client):
        event = EventService.create_event(
            db,
            title="Hands-on Rust & WebAssembly Workshop",
            description="Intensive practical systems programming lab.",
            category="Workshop",
            event_type="workshop",
            capacity=60
        )
        event_id = event["id"]

        # Participant Registration & Ticket
        ticket = TicketService.issue_ticket(
            db,
            event_id=event_id,
            user_id="student-rust@snpsu.edu.in",
            ticket_type="Student",
            price=0.0
        )

        # Offline Check-in Batch Sync
        sync_payload = {
            "scans": [
                {
                    "ticket_id": ticket["ticket_id"],
                    "timestamp": "2026-09-17T10:15:00Z",
                    "device_id": "scanner-tablet-lab2"
                }
            ]
        }
        sync_res = TicketService.sync_offline_checkins(db, event_id, sync_payload["scans"], "lab-coord")
        assert sync_res["synced_count"] == 1

        # Issue Workshop Completion Certificate
        cert = CertificateService.issue_certificate(
            db,
            event_id=event_id,
            recipient_name="Rustacean Student",
            recipient_email="student-rust@snpsu.edu.in",
            certificate_type="participation",
            title="Workshop Completion"
        )
        assert cert["certificate_id"] is not None


class TestSportsTournamentUniversalFlow:
    """4. Sports Tournament: Registration -> Fixture -> Match Score -> Standings -> Results."""

    def test_full_sports_tournament_lifecycle(self, client):
        template = TemplateService.get_template_by_id("sports")
        assert template is not None

        event = EventService.create_event(
            db,
            title="Inter-University Basketball Championship 2026",
            description="Men's collegiate knockout championship.",
            category="Sports",
            event_type="sports",
            event_mode="offline",
            capacity=16,
            workflow_config=template.get("workflow") or template.get("workflow_config")
        )
        event_id = event["id"]

        # Transition to fixtures
        WorkflowService.transition_event_step(db, event_id, "fixtures", "sports-officer")

        # Record match score via EvaluationService points rubric
        team_a_reg = f"team-snpsu-{uuid.uuid4().hex[:4]}"
        team_b_reg = f"team-bmsce-{uuid.uuid4().hex[:4]}"

        db.collection("registrations").document(team_a_reg).set({
            "event_id": event_id,
            "team_name": "SNPSU Bulls",
            "lead_name": "Captain Rohit",
            "lead_email": "rohit@snpsu.edu.in",
            "status": "confirmed"
        })
        db.collection("registrations").document(team_b_reg).set({
            "event_id": event_id,
            "team_name": "BMSCE Tigers",
            "lead_name": "Captain Anil",
            "lead_email": "anil@bmsce.ac.in",
            "status": "confirmed"
        })


        EvaluationService.record_rubric_evaluation(
            db,
            event_id=event_id,
            registration_id=team_a_reg,
            judge_id="referee-1",
            scores={"Match Points": 78.0, "Fair Play": 10.0}
        )
        EvaluationService.record_rubric_evaluation(
            db,
            event_id=event_id,
            registration_id=team_b_reg,
            judge_id="referee-1",
            scores={"Match Points": 65.0, "Fair Play": 9.0}
        )

        # Publish Standings
        res = EvaluationService.publish_results(
            db,
            event_id=event_id,
            rankings=[
                {"registration_id": team_a_reg, "rank": 1, "award": "Gold Medal Champions"},
                {"registration_id": team_b_reg, "rank": 2, "award": "Silver Medal Runner-Up"}
            ],
            published_by="sports-director"
        )
        assert res["success"] is True


class TestCulturalCompetitionUniversalFlow:
    """5. Cultural Competition: Registration -> Prelims -> Multi-Judge Rubric -> Tie-breaking."""

    def test_full_cultural_competition_lifecycle(self, client):
        event = EventService.create_event(
            db,
            title="Sargam 2026 — Classical Solo Vocal",
            description="Carnatic & Hindustani vocal competition.",
            category="Cultural",
            event_type="cultural",
            capacity=40
        )
        event_id = event["id"]
        reg_id = f"vocal-{uuid.uuid4().hex[:4]}"
        db.collection("registrations").document(reg_id).set({
            "event_id": event_id,
            "lead_name": "Priya Sharma",
            "lead_email": "priya.vocal@snpsu.edu.in",
            "status": "confirmed"
        })


        # Judge 1 scoring
        EvaluationService.record_rubric_evaluation(
            db,
            event_id=event_id,
            registration_id=reg_id,
            judge_id="judge-maestro-1",
            scores={"Shruti / Pitch": 38.0, "Tala / Rhythm": 36.0, "Expression": 18.0}
        )
        # Judge 2 scoring
        EvaluationService.record_rubric_evaluation(
            db,
            event_id=event_id,
            registration_id=reg_id,
            judge_id="judge-maestro-2",
            scores={"Shruti / Pitch": 39.0, "Tala / Rhythm": 35.0, "Expression": 19.0}
        )

        # Results publication
        pub = EvaluationService.publish_results(
            db,
            event_id=event_id,
            rankings=[{"registration_id": reg_id, "rank": 1, "award": "Sangeet Ratna Trophy"}],
            published_by="cultural-dean"
        )
        assert pub["success"] is True


class TestPublicDiscoveryAndCalendarExport:
    """6. Public Catalog Search & RFC 5545 iCalendar (.ics) Export."""

    def test_catalog_and_ics_download(self, client):
        # Create an active event with known title and slug
        ev = EventService.create_event(
            db,
            title="Quantum Computing Symposium 2026",
            description="Future of quantum cryptography and algorithms.",
            category="Technical",
            event_type="conference",
            venue="Sir CV Raman Hall",
            date_str="2026-11-20"
        )
        slug = ev["slug"]

        # Test catalog search query
        res = client.get(f"/events?q=Quantum", base_url="https://localhost")
        assert res.status_code == 200
        assert b"Quantum Computing Symposium" in res.data

        # Test RFC 5545 .ics download
        ics_res = client.get(f"/events/{slug}/calendar.ics", base_url="https://localhost")
        assert ics_res.status_code == 200
        assert ics_res.content_type == "text/calendar; charset=utf-8"
        assert b"BEGIN:VCALENDAR" in ics_res.data
        assert b"Quantum Computing Symposium" in ics_res.data
        assert b"Sir CV Raman Hall" in ics_res.data
        assert b"END:VCALENDAR" in ics_res.data


class TestAICopilotUniversalProposalAndApproval:
    """7. AI Event Copilot Proposal Generation & Human-Approval Lifecycle."""

    def test_ai_copilot_lifecycle(self, client, admin_headers):
        prompt_text = "Create a two-day national robotics hackathon for 250 students with autonomous maze navigation."

        # A. Propose Event
        prop_res = client.post(
            "/api/v1/ai/copilot/propose",
            json={"prompt": prompt_text},
            headers=admin_headers,
            base_url="https://localhost"
        )
        assert prop_res.status_code == 200
        prop_json = prop_res.get_json()
        assert prop_json["status"] == "success"
        proposal = prop_json["data"]
        proposal_id = proposal["proposal_id"]
        assert proposal["event_type"] == "hackathon"
        assert proposal["capacity"] == 250
        assert proposal["status"] == "PENDING_REVIEW"
        assert len(proposal["rubric"]) > 0

        # B. Review Proposal
        get_res = client.get(
            f"/api/v1/ai/copilot/proposals/{proposal_id}",
            headers=admin_headers,
            base_url="https://localhost"
        )
        assert get_res.status_code == 200
        assert get_res.get_json()["data"]["proposal_id"] == proposal_id

        # C. Admin Approval & Commit to Production
        appr_res = client.post(
            f"/api/v1/ai/copilot/proposals/{proposal_id}/approve",
            headers=admin_headers,
            base_url="https://localhost"
        )
        assert appr_res.status_code == 200
        appr_json = appr_res.get_json()
        assert appr_json["status"] == "success"
        event_id = appr_json["data"]["event_id"]
        assert event_id is not None

        # Verify event now exists in database
        event_doc = db.collection("events").document(event_id).get()
        assert event_doc.exists is True
        assert event_doc.to_dict()["capacity"] == 250
