"""
tests/test_zero_trust_security.py — Unit & Integration Tests for Phase 10

Verifies:
1. Object-Level Access Control (IDOR mitigation) for registration and ticket objects.
2. File upload sanitization: path traversal, dangerous extension blocking, MIME spoofing.
3. Cryptographic time-bound nonces (anti-replay, expiration, signature verification).
4. Security incident and tamper attempt logging.
5. REST API v1 endpoints for security incident retrieval and nonce verification.
"""

import pytest
import time
import hmac
import hashlib
from auth_jwt import create_tokens
from security_guard import SecurityGuard


@pytest.fixture
def superadmin_token():
    tokens = create_tokens(user_email="superadmin@saptha.org", role="SuperAdmin")
    return tokens["access_token"]


class TestObjectLevelAccessControl:
    """Verify IDOR prevention on registration records."""

    def test_lead_and_members_have_access(self):
        reg = {
            "id": "reg_team_1",
            "lead_email": "lead@saptha.org",
            "members": [
                {"email": "member1@saptha.org", "name": "M1"},
                {"email": "member2@saptha.org", "name": "M2"},
            ]
        }

        # Lead attendee has access
        assert SecurityGuard.verify_registration_access(reg, "lead@saptha.org", "Student") is True

        # Team members have access
        assert SecurityGuard.verify_registration_access(reg, "member1@saptha.org", "Student") is True
        assert SecurityGuard.verify_registration_access(reg, "member2@saptha.org", "Student") is True

        # Unrelated student is blocked (IDOR defense)
        assert SecurityGuard.verify_registration_access(reg, "intruder@saptha.org", "Student") is False

        # Staff roles have override access
        assert SecurityGuard.verify_registration_access(reg, "admin@saptha.org", "Admin") is True
        assert SecurityGuard.verify_registration_access(reg, "spoc@saptha.org", "SPOC") is True


class TestFileUploadHardening:
    """Verify upload path traversal, extension blacklists, and MIME magic."""

    def test_path_traversal_blocked(self):
        valid, msg = SecurityGuard.validate_file_upload("../../etc/passwd.pdf")
        assert valid is False
        assert "traversal" in msg.lower()

    def test_executable_extension_blocked(self):
        for bad in ["shell.php", "malware.exe", "script.sh", "run.bat", "attack.js"]:
            valid, msg = SecurityGuard.validate_file_upload(bad)
            assert valid is False
            assert "strictly prohibited" in msg

    def test_mime_spoofing_blocked(self):
        # File named .pdf but containing plain text or bash script
        fake_pdf = b"echo 'hacked'"
        valid, msg = SecurityGuard.validate_file_upload("whitepaper.pdf", content_bytes=fake_pdf)
        assert valid is False
        assert "spoofed" in msg

    def test_valid_pdf_file_allowed(self):
        genuine_pdf = b"%PDF-1.5 \n genuine content"
        valid, msg = SecurityGuard.validate_file_upload("project_report.pdf", content_bytes=genuine_pdf)
        assert valid is True


class TestCryptographicNoncesAndIncidents:
    """Verify anti-replay nonces and security audit logging."""

    def test_time_bound_nonce_lifecycle(self):
        secret = "super-secret-key-32-bytes-minimum"
        subject = "user_login:alice@saptha.org"

        # 1. Valid nonce
        nonce = SecurityGuard.generate_time_bound_nonce(subject, secret, ttl_seconds=60)
        valid, msg = SecurityGuard.verify_time_bound_nonce(nonce, subject, secret)
        assert valid is True

        # 2. Tampered subject
        valid_bad_sub, msg_bad_sub = SecurityGuard.verify_time_bound_nonce(nonce, "user_login:bob@saptha.org", secret)
        assert valid_bad_sub is False
        assert "signature" in msg_bad_sub.lower()

        # 3. Expired nonce (timestamp from 100 seconds ago with 60s TTL)
        past_ts = int(time.time()) - 100
        msg = f"{subject}:{past_ts}:60".encode("utf-8")
        sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:16]
        expired_nonce = f"{past_ts}.60.{sig}"
        valid_exp, msg_exp = SecurityGuard.verify_time_bound_nonce(expired_nonce, subject, secret)
        assert valid_exp is False
        assert "expired" in msg_exp.lower()

    def test_security_incident_logging(self, mock_db):
        inc_id = SecurityGuard.log_security_incident(
            mock_db,
            incident_type="IDOR_ATTEMPT",
            actor_email="attacker@external.com",
            severity="HIGH",
            details={"attempted_id": "reg_private_123"},
        )
        assert inc_id.startswith("sec_")
        doc = mock_db.collection("security_incidents").document(inc_id).get()
        assert doc.exists
        assert doc.to_dict()["incident_type"] == "IDOR_ATTEMPT"


class TestSecurityAPIEndpoints:
    """Verify REST API v1 security endpoints."""

    def test_verify_nonce_endpoint(self, client):
        import os
        secret = os.environ.get("SECRET_KEY", "default-salt-key-2026")
        subject = "payment_checkout:order_123"
        nonce = SecurityGuard.generate_time_bound_nonce(subject, secret, ttl_seconds=120)

        resp = client.post(
            "/api/v1/security/verify-nonce",
            json={"nonce": nonce, "subject": subject}
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["valid"] is True

    def test_security_incidents_api(self, client, superadmin_token, mock_db):
        SecurityGuard.log_security_incident(
            mock_db,
            incident_type="SQLI_PROBE",
            actor_email="scanner@bot.net",
            severity="CRITICAL",
        )

        resp = client.get(
            "/api/v1/security/incidents",
            headers={"Authorization": f"Bearer {superadmin_token}"}
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] >= 1
