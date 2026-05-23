"""
test_security.py — Tests for Security Middleware & Hardening

Covers: IP blocking, login attempt tracking, account lockout,
security headers, input sanitization, and audit logging.
"""
import pytest
import time


class TestIPBlocking:
    """Test IP blocking and unblocking."""

    def test_block_ip(self):
        from security_middleware import block_ip, is_ip_blocked, unblock_ip
        block_ip("192.168.1.100", duration_seconds=10)
        assert is_ip_blocked("192.168.1.100") is True
        unblock_ip("192.168.1.100")
        assert is_ip_blocked("192.168.1.100") is False

    def test_unblocked_ip_allowed(self):
        from security_middleware import is_ip_blocked
        assert is_ip_blocked("10.0.0.1") is False

    def test_block_expires(self):
        from security_middleware import block_ip, is_ip_blocked
        block_ip("10.0.0.99", duration_seconds=1)
        assert is_ip_blocked("10.0.0.99") is True
        time.sleep(1.5)
        assert is_ip_blocked("10.0.0.99") is False


class TestLoginAttemptTracking:
    """Test login attempt rate limiting."""

    def test_record_successful_login(self):
        from security_middleware import record_login_attempt, _login_attempts
        record_login_attempt("10.0.0.1", email="user@test.edu", success=True)
        # Should clear any tracked attempts
        assert len(_login_attempts.get("10.0.0.1", [])) == 0

    def test_record_failed_login(self):
        from security_middleware import record_login_attempt, _login_attempts
        ip = "10.0.0.50"
        record_login_attempt(ip, email="fail@test.edu", success=False)
        assert len(_login_attempts.get(ip, [])) >= 1

    def test_account_lockout_after_5_failures(self):
        from security_middleware import record_login_attempt, is_account_locked
        email = "locked@test.edu"
        for i in range(5):
            record_login_attempt(f"10.0.{i}.1", email=email, success=False)
        assert is_account_locked(email) is True

    def test_lockout_has_remaining_time(self):
        from security_middleware import record_login_attempt, get_remaining_lockout
        email = "timed@test.edu"
        for i in range(5):
            record_login_attempt(f"10.1.{i}.1", email=email, success=False)
        remaining = get_remaining_lockout(email)
        assert remaining > 0

    def test_unlocked_account_returns_zero(self):
        from security_middleware import get_remaining_lockout
        assert get_remaining_lockout("free@test.edu") == 0


class TestSecurityHeaders:
    """Test that security headers are properly applied."""

    def test_apply_security_headers(self):
        from flask import Flask
        test_app = Flask(__name__)
        with test_app.test_request_context():
            from security_middleware import apply_security_headers
            from flask import make_response
            response = make_response("test", 200)
            response.content_type = "text/html"
            result = apply_security_headers(response)
            assert result.headers["X-Content-Type-Options"] == "nosniff"
            assert result.headers["X-Frame-Options"] == "SAMEORIGIN"
            assert "camera" in result.headers["Permissions-Policy"]
            assert result.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"


class TestInputSanitization:
    """Test input sanitization functions."""

    def test_sanitize_removes_script_tags(self):
        from security_middleware import sanitize_input
        result = sanitize_input("<script>alert('xss')</script>")
        assert "<script" not in result
        assert "&lt;script" in result

    def test_sanitize_removes_null_bytes(self):
        from security_middleware import sanitize_input
        result = sanitize_input("hello\x00world")
        assert "\x00" not in result

    def test_sanitize_truncates_long_input(self):
        from security_middleware import sanitize_input
        result = sanitize_input("a" * 5000, max_length=100)
        assert len(result) == 100

    def test_sanitize_empty_string(self):
        from security_middleware import sanitize_input
        assert sanitize_input("") == ""

    def test_sanitize_normal_text(self):
        from security_middleware import sanitize_input
        assert sanitize_input("Hello, World!") == "Hello, World!"


class TestAuditLogger:
    """Test the enhanced audit logging system."""

    def test_mask_email(self):
        from audit_logger import _mask_email
        assert _mask_email("john@gmail.com") != "john@gmail.com"
        assert "@" in _mask_email("john@gmail.com")

    def test_mask_phone(self):
        from audit_logger import _mask_phone
        result = _mask_phone("9876543210")
        assert "98" in result
        assert "*" in result

    def test_mask_sensitive_text(self):
        from audit_logger import mask_sensitive
        text = "User john@test.edu with phone 9876543210"
        result = mask_sensitive(text)
        assert "john@test.edu" not in result
        assert "9876543210" not in result

    def test_audit_log_write(self, mock_db):
        from flask import Flask
        test_app = Flask(__name__)
        test_app.secret_key = "test-secret"
        with test_app.test_request_context():
            from flask import session
            session["user_id"] = "tester@test.edu"
            session["role"] = "Admin"
            from audit_logger import AuditLogger
            logger = AuditLogger(mock_db)
            log_id = logger.log(
                "TEST_ACTION",
                target_type="test",
                target_id="123",
                details="Test audit entry",
            )
            assert log_id is not None

    def test_audit_batch_write(self, mock_db):
        from flask import Flask
        test_app = Flask(__name__)
        test_app.secret_key = "test-secret"
        with test_app.test_request_context():
            from flask import session
            session["user_id"] = "batch@test.edu"
            from audit_logger import AuditLogger
            logger = AuditLogger(mock_db)
            count = logger.log_batch([
                {"action": "BATCH_1", "details": "First"},
                {"action": "BATCH_2", "details": "Second"},
                {"action": "BATCH_3", "details": "Third"},
            ])
            assert count == 3

    def test_audit_severity_levels(self, mock_db):
        from flask import Flask
        test_app = Flask(__name__)
        test_app.secret_key = "test-secret"
        with test_app.test_request_context():
            from flask import session
            session["user_id"] = "admin@test.edu"
            from audit_logger import AuditLogger, SEVERITY_CRITICAL
            logger = AuditLogger(mock_db)
            log_id = logger.log(
                "CRITICAL_ACTION",
                severity=SEVERITY_CRITICAL,
                details="Security breach detected",
            )
            assert log_id is not None
