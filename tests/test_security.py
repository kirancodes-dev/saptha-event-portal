"""
test_security.py — Tests for Security Middleware & Hardening

Covers: security headers, input sanitization, and audit logging. (The tests
of the never-called in-memory IP blocking and login tracking went with that
code in UPG-112; login throttling is tested in tests/test_login_throttle.py.)
"""


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
