"""
tests/test_evaluation_and_certs.py — Unit & Integration Tests for Phase 6

Verifies:
1. Pluggable scoring rubrics (Weighted Rubric, Star Rating, Pass/Fail, Match Points, Time-based).
2. Deterministic leaderboard generation and automated tie-breaking.
3. Cryptographic certificate issuance, anti-tampering verification, and revocation.
4. Bulk certificate issuance based on leaderboard ranking and attendance.
5. REST API v1 endpoints for scoring, leaderboard, and certificate verification.
"""

import pytest
import uuid
from auth_jwt import create_tokens
from services_evaluation import EvaluationEngine
from services_certificate import CertificateService


@pytest.fixture
def judge_token():
    tokens = create_tokens(user_email="judge@saptha.org", role="Judge")
    return tokens["access_token"]


@pytest.fixture
def admin_token():
    tokens = create_tokens(user_email="admin@saptha.org", role="SuperAdmin")
    return tokens["access_token"]


class TestEvaluationEngineScoringModels:
    """Verify all 5 pluggable scoring rubric engines."""

    def test_weighted_rubric_calculation(self):
        rubric = {
            "type": "rubric",
            "criteria": [
                {"key": "innovation", "name": "Innovation", "max_score": 10, "weight": 40},
                {"key": "technical", "name": "Technical Execution", "max_score": 20, "weight": 40},
                {"key": "presentation", "name": "Pitch & Demo", "max_score": 10, "weight": 20},
            ]
        }
        # Raw scores: Innovation: 10/10 (100%), Technical: 10/20 (50%), Presentation: 10/10 (100%)
        # Weighted: (100 * 40 + 50 * 40 + 100 * 20) / 100 = (4000 + 2000 + 2000) / 100 = 80.0
        raw_scores = {"innovation": 10, "technical": 10, "presentation": 10}
        score, breakdown = EvaluationEngine.calculate_score(rubric, raw_scores)
        assert score == 80.0
        assert breakdown["final_score"] == 80.0
        assert "innovation" in breakdown

    def test_star_rating_calculation(self):
        rubric = {
            "type": "star_rating",
            "criteria": [
                {"key": "usability", "name": "Usability"},
                {"key": "design", "name": "Visual Design"},
            ]
        }
        # Max stars = 10. Received = 4 + 5 = 9. Normalized = 90%
        raw_scores = {"usability": 4, "design": 5}
        score, breakdown = EvaluationEngine.calculate_score(rubric, raw_scores)
        assert score == 90.0
        assert breakdown["total_stars"] == 9

    def test_pass_fail_calculation(self):
        rubric = {"type": "pass_fail", "pass_score": 75}
        score_pass, breakdown_pass = EvaluationEngine.calculate_score(rubric, {"score": 80})
        assert score_pass == 80.0
        assert breakdown_pass["passed"] is True

        score_fail, breakdown_fail = EvaluationEngine.calculate_score(rubric, {"score": 60})
        assert score_fail == 0.0
        assert breakdown_fail["passed"] is False

    def test_match_points_calculation(self):
        rubric = {"type": "match_points"}
        raw = {"match_score": 50, "fair_play": 5, "mvp_rating": 2}
        # total = 50 + (5 * 2) + (2 * 5) = 70
        score, breakdown = EvaluationEngine.calculate_score(rubric, raw)
        assert score == 70.0
        assert breakdown["total_points"] == 70.0

    def test_time_based_calculation(self):
        rubric = {"type": "time_based"}
        raw = {"duration_seconds": 99, "penalty_seconds": 0}
        score, breakdown = EvaluationEngine.calculate_score(rubric, raw)
        # 100,000 / (99 + 1) = 1,000.0
        assert score == 1000.0


class TestEvaluationAndTieBreaking:
    """Verify judge scoring persistence and deterministic leaderboard tie-breaking."""

    def test_judge_scoring_and_average(self, mock_db):
        event_id = f"ev_{uuid.uuid4().hex[:6]}"
        reg_id = f"reg_{uuid.uuid4().hex[:6]}"

        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "AI Hackathon",
            "evaluation_config": {
                "type": "rubric",
                "criteria": [
                    {"key": "code", "max_score": 10, "weight": 50},
                    {"key": "ui", "max_score": 10, "weight": 50},
                ]
            }
        })

        mock_db.collection("registrations").document(reg_id).set({
            "id": reg_id,
            "event_id": event_id,
            "team_name": "DeepMind Innovators",
            "lead_name": "Alice",
            "lead_email": "alice@saptha.org",
        })

        # Judge 1 gives 10/10 and 10/10 -> 100%
        EvaluationEngine.record_score(
            mock_db,
            event_id=event_id,
            registration_id=reg_id,
            judge_id="judge_1",
            judge_name="Dr. Alan",
            raw_scores={"code": 10, "ui": 10},
        )

        # Judge 2 gives 6/10 and 6/10 -> 60%
        EvaluationEngine.record_score(
            mock_db,
            event_id=event_id,
            registration_id=reg_id,
            judge_id="judge_2",
            judge_name="Prof. Turing",
            raw_scores={"code": 6, "ui": 6},
        )

        reg_data = mock_db.collection("registrations").document(reg_id).get().to_dict()
        assert reg_data["score_average"] == 80.0
        assert len(reg_data["scores"]) == 2

    def test_deterministic_tie_breaking(self, mock_db):
        event_id = f"ev_tie_{uuid.uuid4().hex[:6]}"

        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Code Sprint",
            "evaluation_config": {
                "type": "rubric",
                "criteria": [
                    {"key": "code_quality", "max_score": 10, "weight": 70},  # Primary tie-breaker
                    {"key": "presentation", "max_score": 10, "weight": 30},
                ]
            }
        })

        # Team Alpha: code_quality 8, presentation 10 -> score = (80*70 + 100*30)/100 = 86.0
        # Team Beta: code_quality 10, presentation 5.33 -> let's make total exactly 86.0
        # For Alpha:
        # code=8 (80%), pres=10 (100%) -> weighted = 56 + 30 = 86
        # For Beta:
        # code=10 (100%), pres=5.333333333333334 (53.333%) -> weighted = 70 + 16 = 86
        mock_db.collection("registrations").document("reg_alpha").set({
            "id": "reg_alpha",
            "event_id": event_id,
            "team_name": "Team Alpha",
            "lead_name": "Alpha Lead",
        })
        mock_db.collection("registrations").document("reg_beta").set({
            "id": "reg_beta",
            "event_id": event_id,
            "team_name": "Team Beta",
            "lead_name": "Beta Lead",
        })

        EvaluationEngine.record_score(
            mock_db,
            event_id=event_id,
            registration_id="reg_alpha",
            judge_id="j1",
            judge_name="Judge",
            raw_scores={"code_quality": 8, "presentation": 10},
        )
        EvaluationEngine.record_score(
            mock_db,
            event_id=event_id,
            registration_id="reg_beta",
            judge_id="j1",
            judge_name="Judge",
            raw_scores={"code_quality": 10, "presentation": 5.333333333333334},
        )

        leaderboard = EvaluationEngine.generate_leaderboard(mock_db, event_id)
        assert len(leaderboard) == 2
        # Team Beta has higher score on the primary key (code_quality 10 vs 8) -> Beta should rank 1
        assert leaderboard[0]["registration_id"] == "reg_beta"
        assert leaderboard[0]["rank"] == 1
        assert leaderboard[1]["registration_id"] == "reg_alpha"
        assert leaderboard[1]["rank"] == 2


class TestCertificateEngine:
    """Verify certificate issuance, cryptographic tamper-proofing, and bulk generation."""

    def test_certificate_issuance_and_verification(self, mock_db):
        cert = CertificateService.issue_certificate(
            mock_db,
            event_id="ev_cert_1",
            event_title="National AI Summit",
            recipient_name="Grace Hopper",
            recipient_email="grace@saptha.org",
            category="winner",
            rank=1,
        )

        cert_id = cert["cert_id"]
        assert cert["category"] == "winner"
        assert cert["title"] == "Certificate of Achievement — 1st Place"
        assert cert["verification_hash"] is not None

        # Verify authentic certificate
        is_valid, msg, cert_obj = CertificateService.verify_certificate(mock_db, cert_id)
        assert is_valid is True
        assert "authentic and verified" in msg
        assert cert_obj["recipient_name"] == "Grace Hopper"

    def test_tampered_certificate_fails_verification(self, mock_db):
        cert = CertificateService.issue_certificate(
            mock_db,
            event_id="ev_cert_tamper",
            event_title="Cyber Defense Day",
            recipient_name="Eve Hacker",
            recipient_email="eve@saptha.org",
            category="participant",
        )
        cert_id = cert["cert_id"]

        # Tamper with recipient email in database
        mock_db.collection("certificates").document(cert_id).set({
            "recipient_email": "malicious@attacker.com"
        }, merge=True)

        is_valid, msg, cert_obj = CertificateService.verify_certificate(mock_db, cert_id)
        assert is_valid is False
        assert "tampered record" in msg

    def test_revoked_certificate_status(self, mock_db):
        cert = CertificateService.issue_certificate(
            mock_db,
            event_id="ev_cert_revoke",
            event_title="Ethics in AI",
            recipient_name="Bob Disqualified",
            recipient_email="bob@saptha.org",
            category="participant",
        )
        cert_id = cert["cert_id"]

        mock_db.collection("certificates").document(cert_id).set({
            "status": "revoked"
        }, merge=True)

        is_valid, msg, _ = CertificateService.verify_certificate(mock_db, cert_id)
        assert is_valid is False
        assert "revoked" in msg

    def test_bulk_certificate_issuance(self, mock_db):
        event_id = f"ev_bulk_{uuid.uuid4().hex[:6]}"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Quantum Hackathon 2026",
            "evaluation_config": {"type": "rubric", "criteria": [{"key": "score", "max_score": 100, "weight": 100}]}
        })

        # Register 3 teams
        mock_db.collection("registrations").document("reg_1").set({
            "id": "reg_1", "event_id": event_id, "lead_name": "Alice Winner", "lead_email": "alice@saptha.org",
            "attendance": "Present",
        })
        mock_db.collection("registrations").document("reg_2").set({
            "id": "reg_2", "event_id": event_id, "lead_name": "Bob RunnerUp", "lead_email": "bob@saptha.org",
            "attendance": "Present",
        })
        mock_db.collection("registrations").document("reg_3").set({
            "id": "reg_3", "event_id": event_id, "lead_name": "Charlie Attendant", "lead_email": "charlie@saptha.org",
            "attendance": "Present",
        })

        # Give scores to rank them
        EvaluationEngine.record_score(mock_db, event_id=event_id, registration_id="reg_1", judge_id="j1", judge_name="J", raw_scores={"score": 95})
        EvaluationEngine.record_score(mock_db, event_id=event_id, registration_id="reg_2", judge_id="j1", judge_name="J", raw_scores={"score": 85})

        issued = CertificateService.bulk_issue_event_certificates(mock_db, event_id)
        assert len(issued) == 3

        cat_map = {c["recipient_email"]: c["category"] for c in issued}
        assert cat_map["alice@saptha.org"] == "winner"
        assert cat_map["bob@saptha.org"] == "runner_up"
        assert cat_map["charlie@saptha.org"] == "participant"


class TestEvaluationAndCertificateEndpoints:
    """Verify REST API v1 endpoints."""

    def test_submit_score_and_retrieve_leaderboard(self, client, judge_token, mock_db):
        event_id = f"ev_api_{uuid.uuid4().hex[:6]}"
        reg_id = f"reg_api_{uuid.uuid4().hex[:6]}"

        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Hackathon API Test",
            "evaluation_config": {
                "type": "rubric",
                "criteria": [{"key": "innovation", "max_score": 10, "weight": 100}]
            }
        })
        mock_db.collection("registrations").document(reg_id).set({
            "id": reg_id,
            "event_id": event_id,
            "team_name": "Rocket Team",
            "lead_name": "Dave",
            "lead_email": "dave@saptha.org",
        })

        # Submit score via API
        resp = client.post(
            f"/api/v1/events/{event_id}/scores",
            headers={"Authorization": f"Bearer {judge_token}"},
            json={
                "registration_id": reg_id,
                "scores": {"innovation": 9},
                "remarks": "Superb project",
            }
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["final_score"] == 90.0

        # Retrieve leaderboard
        lb_resp = client.get(f"/api/v1/events/{event_id}/leaderboard")
        assert lb_resp.status_code == 200
        lb_data = lb_resp.get_json()["data"]
        assert lb_data["total_participants"] == 1
        assert lb_data["leaderboard"][0]["team_name"] == "Rocket Team"
        assert lb_data["leaderboard"][0]["composite_score"] == 90.0

    def test_verify_certificate_api(self, client, mock_db):
        cert = CertificateService.issue_certificate(
            mock_db,
            event_id="ev_api_cert",
            event_title="Web3 Showcase",
            recipient_name="Satoshi",
            recipient_email="satoshi@saptha.org",
            category="speaker",
        )
        cert_id = cert["cert_id"]

        resp = client.get(f"/api/v1/certificates/{cert_id}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["verified"] is True
        assert data["certificate"]["recipient_name"] == "Satoshi"
        assert data["certificate"]["category"] == "speaker"
