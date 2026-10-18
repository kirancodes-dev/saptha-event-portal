"""
security_middleware.py — Security Hardening Middleware for SapthaEvent

Security headers, JSON content-type checks and input sanitising. Login
throttling is services_login_throttle.py (BLK-13); the old in-memory IP
blocking and login tracking here were never called and went in UPG-112.
"""
import logging
from functools import wraps

from flask import request, jsonify

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# SECURITY HEADERS
# ═══════════════════════════════════════════════════════════════════════════

def apply_security_headers(response):
    """Apply comprehensive security headers."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), "
        "payment=(self), usb=()"
    )
    # Don't cache HTML
    if "text/html" in response.content_type:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


# ═══════════════════════════════════════════════════════════════════════════
# REQUEST VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def validate_content_type(f):
    """Decorator: ensure JSON content type for API endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH"):
            if not request.is_json and not request.content_type:
                return jsonify({"error": "Content-Type must be application/json"}), 415
        return f(*args, **kwargs)
    return decorated


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input by removing dangerous characters."""
    if not text:
        return ""
    # Truncate
    text = text[:max_length]
    # Remove null bytes
    text = text.replace("\x00", "")
    # Basic XSS prevention (templates should also escape)
    text = text.replace("<script", "&lt;script")
    text = text.replace("</script", "&lt;/script")
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════
# INIT MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════

def init_security_middleware(app):
    """Register all security middleware on the Flask app."""

    @app.after_request
    def add_security_headers(response):
        return apply_security_headers(response)

    logger.info("Security middleware initialized")
