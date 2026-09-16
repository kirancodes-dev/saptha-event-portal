"""
tests/test_ticketing_and_forms.py — Unit & Integration Tests for Phase 4

Verifies:
1. Dynamic Form Builder regex validation and conditional field display (depends_on).
2. Multi-tier Ticket generation (General, VIP, Speaker, Judge, Student).
3. HMAC-SHA256 cryptographically signed QR ticket tokens with tamper protection.
4. Anti-replay protection preventing double check-in.
5. Digital Ticket Wallet pass generation and HTTP endpoints.
"""

import pytest
import uuid
import time
import base64
import json
import hmac
import hashlib

from routes_forms import _validate_submission
from services_ticket import TicketService


# ═══════════════════════════════════════════════════════════════════════
# 1. DYNAMIC FORM BUILDER VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestDynamicFormValidation:
    """Test regex patterns and conditional field dependency logic."""

    def test_regex_pattern_validation_success(self):
        schema = {
            "fields": [
                {
                    "id": "github_handle",
                    "label": "GitHub Handle",
                    "type": "text",
                    "required": True,
                    "pattern": r"^[a-zA-Z0-9_-]{3,20}$",
                    "pattern_error": "GitHub username must be 3-20 alphanumeric characters.",
                }
            ]
        }
        form_data = {"github_handle": "alice_dev"}
        errors = _validate_submission(schema, form_data)
        assert len(errors) == 0

    def test_regex_pattern_validation_failure(self):
        schema = {
            "fields": [
                {
                    "id": "github_handle",
                    "label": "GitHub Handle",
                    "type": "text",
                    "required": True,
                    "pattern": r"^[a-zA-Z0-9_-]{3,20}$",
                    "pattern_error": "GitHub username must be 3-20 alphanumeric characters.",
                }
            ]
        }
        form_data = {"github_handle": "a!"}  # Invalid special character & too short
        errors = _validate_submission(schema, form_data)
        assert len(errors) == 1
        assert "GitHub username must be 3-20 alphanumeric characters." in errors[0]

    def test_conditional_field_depends_on_satisfied(self):
        schema = {
            "fields": [
                {
                    "id": "attendee_type",
                    "label": "Attendee Type",
                    "type": "select",
                    "required": True,
                },
                {
                    "id": "student_usn",
                    "label": "University Roll Number / USN",
                    "type": "text",
                    "required": True,
                    "depends_on": {"field": "attendee_type", "value": "Student"},
                },
            ]
        }
        # Condition matched ('Student'), so student_usn is required and empty -> should fail
        form_data = {"attendee_type": "Student", "student_usn": ""}
        errors = _validate_submission(schema, form_data)
        assert len(errors) == 1
        assert "'University Roll Number / USN' is required." in errors[0]

    def test_conditional_field_depends_on_skipped_when_condition_unmet(self):
        schema = {
            "fields": [
                {
                    "id": "attendee_type",
                    "label": "Attendee Type",
                    "type": "select",
                    "required": True,
                },
                {
                    "id": "student_usn",
                    "label": "University Roll Number / USN",
                    "type": "text",
                    "required": True,
                    "depends_on": {"field": "attendee_type", "value": "Student"},
                },
            ]
        }
        # Condition not matched ('Industry Professional'), so student_usn is skipped
        form_data = {"attendee_type": "Industry Professional", "student_usn": ""}
        errors = _validate_submission(schema, form_data)
        assert len(errors) == 0

    def test_conditional_field_depends_on_in_operator(self):
        schema = {
            "fields": [
                {
                    "id": "experience_years",
                    "label": "Years of Experience",
                    "type": "number",
                    "required": True,
                    "depends_on": {"field": "role", "in": ["Senior Engineer", "Tech Lead"]},
                }
            ]
        }
        # Not in list
        errors1 = _validate_submission(schema, {"role": "Intern", "experience_years": ""})
        assert len(errors1) == 0

        # In list but missing
        errors2 = _validate_submission(schema, {"role": "Tech Lead", "experience_years": ""})
        assert len(errors2) == 1


# ═══════════════════════════════════════════════════════════════════════
# 2. HMAC-SHA256 TOKEN & ANTI-TAMPER TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestTicketHMACSignatures:
    """Test cryptographic token generation, verification, and tampering detection."""

    def test_generate_and_verify_valid_token(self):
        token = TicketService.generate_signed_qr_token(
            ticket_id="tkt_12345",
            registration_id="reg_67890",
            event_id="ev_summit_2026",
            tier="VIP",
            lead_name="Sarah Connor",
        )
        assert "." in token
        parts = token.split(".")
        assert len(parts) == 2

        is_valid, msg, payload = TicketService.verify_signed_qr_token(token)
        assert is_valid is True
        assert msg == "Token valid"
        assert payload["tid"] == "tkt_12345"
        assert payload["rid"] == "reg_67890"
        assert payload["tier"] == "VIP"
        assert payload["name"] == "Sarah Connor"

    def test_tampered_payload_rejected(self):
        token = TicketService.generate_signed_qr_token(
            ticket_id="tkt_legit",
            registration_id="reg_legit",
            event_id="ev_legit",
            tier="General",
            lead_name="Bob Builder",
        )
        payload_b64, sig = token.split(".")

        # Attacker tries to upgrade tier to VIP in payload
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        data["tier"] = "VIP"
        tampered_b64 = base64.urlsafe_b64encode(json.dumps(data).encode("utf-8")).decode("utf-8").rstrip("=")

        tampered_token = f"{tampered_b64}.{sig}"
        is_valid, msg, _ = TicketService.verify_signed_qr_token(tampered_token)
        assert is_valid is False
        assert "signature mismatch" in msg.lower()

    def test_tampered_signature_rejected(self):
        token = TicketService.generate_signed_qr_token(
            ticket_id="tkt_1",
            registration_id="reg_1",
            event_id="ev_1",
            tier="Speaker",
            lead_name="Dr. Smith",
        )
        payload_b64, sig = token.split(".")
        fake_sig = sig[:-4] + "dead"
        tampered_token = f"{payload_b64}.{fake_sig}"

        is_valid, msg, _ = TicketService.verify_signed_qr_token(tampered_token)
        assert is_valid is False
        assert "signature mismatch" in msg.lower()

    def test_expired_token_rejected_when_max_age_set(self):
        secret = b"test-secret-key"
        old_time = int(time.time()) - 5000
        payload = {"tid": "tkt_old", "ts": old_time, "tier": "General"}
        payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
        sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        token = f"{payload_b64}.{sig}"

        is_valid, msg, _ = TicketService.verify_signed_qr_token(
            token, max_age_seconds=3600, secret_key=secret
        )
        assert is_valid is False
        assert "expired" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════
# 3. TICKET ISSUANCE & CHECK-IN ANTI-REPLAY TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestTicketIssuanceAndCheckin:
    """Test ticket persistence, check-in, and anti-replay double-entry protection."""

    def test_issue_ticket_persists_and_updates_registration(self, mock_db):
        event_id = f"ev_{uuid.uuid4().hex[:6]}"
        reg_id = f"reg_{uuid.uuid4().hex[:6]}"

        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Cloud DevFest 2026",
            "date": "2026-10-15",
            "venue": "Convention Center",
        })

        mock_db.collection("registrations").document(reg_id).set({
            "id": reg_id,
            "event_id": event_id,
            "lead_name": "Maya Patel",
            "lead_email": "maya@devfest.org",
            "status": "Confirmed",
            "fee": 0.0,
        })

        ticket = TicketService.issue_ticket(
            mock_db,
            event_id=event_id,
            registration_id=reg_id,
            user_email="maya@devfest.org",
            lead_name="Maya Patel",
            ticket_type="VIP",
            gate_assignment="Gate VIP",
            seat_assignment="Front Row A4",
        )

        assert ticket["id"] is not None
        assert ticket["ticket_code"].startswith("TKT-")
        assert ticket["ticket_type"] == "VIP"
        assert ticket["status"] == "active"

        # Verify registration updated
        reg_doc = mock_db.collection("registrations").document(reg_id).get()
        assert reg_doc.to_dict()["ticket_code"] == ticket["ticket_code"]

    def test_checkin_success_and_anti_replay(self, mock_db):
        event_id = f"ev_{uuid.uuid4().hex[:6]}"
        reg_id = f"reg_{uuid.uuid4().hex[:6]}"

        mock_db.collection("registrations").document(reg_id).set({
            "id": reg_id,
            "event_id": event_id,
            "lead_name": "John Doe",
            "lead_email": "john@example.com",
            "fee": 0.0,
            "status": "Confirmed",
        })

        ticket = TicketService.issue_ticket(
            mock_db,
            event_id=event_id,
            registration_id=reg_id,
            user_email="john@example.com",
            lead_name="John Doe",
            ticket_type="General",
        )

        # First check-in: SUCCESS
        res1 = TicketService.checkin_ticket(mock_db, ticket["signed_token"], actor_id="scanner_1")
        assert res1["status"] == "success"
        assert res1["ticket"]["status"] == "checked_in"

        # Registration should now be checked in
        reg_data = mock_db.collection("registrations").document(reg_id).get().to_dict()
        assert reg_data["attendance"] == "Present"
        assert reg_data["status"] == "checked_in"

        # Second check-in with the same token: ANTI-REPLAY REJECTION
        res2 = TicketService.checkin_ticket(mock_db, ticket["signed_token"], actor_id="scanner_2")
        assert res2["status"] == "already_used"
        assert "already checked in" in res2["message"].lower()

    def test_unpaid_ticket_checkin_blocked(self, mock_db):
        event_id = f"ev_paid_{uuid.uuid4().hex[:6]}"
        reg_id = f"reg_unpaid_{uuid.uuid4().hex[:6]}"

        mock_db.collection("registrations").document(reg_id).set({
            "id": reg_id,
            "event_id": event_id,
            "lead_name": "Unpaid Attendee",
            "lead_email": "unpaid@test.com",
            "fee": 500.0,
            "payment_status": "unpaid",
        })

        ticket = TicketService.issue_ticket(
            mock_db,
            event_id=event_id,
            registration_id=reg_id,
            user_email="unpaid@test.com",
            lead_name="Unpaid Attendee",
        )

        res = TicketService.checkin_ticket(mock_db, ticket["id"])
        assert res["status"] == "unpaid"
        assert "payment pending" in res["message"].lower()


# ═══════════════════════════════════════════════════════════════════════
# 4. DIGITAL WALLET PASS & API INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestDigitalTicketWalletRoutes:
    """Test web and JSON wallet pass endpoints and scanner checkin."""

    def test_get_wallet_pass_metadata(self, mock_db):
        event_id = f"ev_wallet_{uuid.uuid4().hex[:6]}"
        reg_id = f"reg_wallet_{uuid.uuid4().hex[:6]}"

        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "AI Summit 2026",
            "date": "2026-12-01",
            "venue": "Silicon Auditorium",
        })
        mock_db.collection("registrations").document(reg_id).set({"id": reg_id})

        ticket = TicketService.issue_ticket(
            mock_db,
            event_id=event_id,
            registration_id=reg_id,
            user_email="delegate@ai.org",
            lead_name="Dr. Alan Turing",
            ticket_type="Speaker",
        )

        wallet = TicketService.get_wallet_pass(mock_db, ticket["ticket_code"])
        assert wallet is not None
        assert wallet["ticket"]["lead_name"] == "Dr. Alan Turing"
        assert wallet["event"]["title"] == "AI Summit 2026"
        assert len(wallet["qr_image_base64"]) > 50
        assert wallet["is_valid"] is True

    def test_wallet_web_view_renders_html(self, client, mock_db):
        event_id = f"ev_view_{uuid.uuid4().hex[:6]}"
        reg_id = f"reg_view_{uuid.uuid4().hex[:6]}"

        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Tech Expo 2026",
            "venue": "Hall A",
        })
        mock_db.collection("registrations").document(reg_id).set({"id": reg_id})

        ticket = TicketService.issue_ticket(
            mock_db,
            event_id=event_id,
            registration_id=reg_id,
            user_email="visitor@expo.com",
            lead_name="Visitor One",
            ticket_type="Student",
        )

        resp = client.get(f"/ticket/wallet/{ticket['ticket_code']}")
        assert resp.status_code == 200
        assert b"Student PASS" in resp.data
        assert b"Visitor One" in resp.data

    def test_wallet_api_returns_json(self, client, mock_db):
        event_id = f"ev_api_tkt_{uuid.uuid4().hex[:6]}"
        reg_id = f"reg_api_tkt_{uuid.uuid4().hex[:6]}"

        mock_db.collection("events").document(event_id).set({"id": event_id, "title": "API Test Expo"})
        mock_db.collection("registrations").document(reg_id).set({"id": reg_id})

        ticket = TicketService.issue_ticket(
            mock_db,
            event_id=event_id,
            registration_id=reg_id,
            user_email="api@test.com",
            lead_name="API User",
            ticket_type="VIP",
        )

        resp = client.get(f"/ticket/api/wallet/{ticket['ticket_code']}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["data"]["ticket"]["ticket_type"] == "VIP"

    def test_api_verify_with_signed_token(self, client, mock_db):
        event_id = f"ev_scan_{uuid.uuid4().hex[:6]}"
        reg_id = f"reg_scan_{uuid.uuid4().hex[:6]}"

        mock_db.collection("registrations").document(reg_id).set({
            "id": reg_id,
            "event_id": event_id,
            "lead_name": "Scanner Test User",
            "fee": 0.0,
            "status": "Confirmed",
        })

        ticket = TicketService.issue_ticket(
            mock_db,
            event_id=event_id,
            registration_id=reg_id,
            user_email="scanner_test@saptha.org",
            lead_name="Scanner Test User",
            ticket_type="Judge",
        )

        # Scan via JSON API
        resp = client.get(f"/ticket/api/verify/{ticket['signed_token']}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["name"] == "Scanner Test User"
        assert data["ticket_type"] == "Judge"
