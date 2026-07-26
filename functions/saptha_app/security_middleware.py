"""
security_middleware.py — Security Hardening Middleware for SapthaEvent

Enhanced rate limiting, IP blocking, login attempt tracking,
and suspicious activity detection.
"""
import logging
import datetime
import time
from functools import wraps

from flask import request, jsonify, session, g

logger = logging.getLogger(__name__)

# In-memory stores (use Redis in production)
_login_attempts: dict = {}     # IP -> list of timestamps
_blocked_ips: dict = {}        # IP -> block_until timestamp
_failed_logins: dict = {}      # email -> {"count": N, "last": timestamp}


# ═══════════════════════════════════════════════════════════════════════════
# IP BLOCKING
# ═══════════════════════════════════════════════════════════════════════════

def is_ip_blocked(ip: str) -> bool:
    """Check if an IP is currently blocked."""
    if ip in _blocked_ips:
        if time.time() < _blocked_ips[ip]:
            return True
        del _blocked_ips[ip]
    return False


def block_ip(ip: str, duration_seconds: int = 900):
    """Block an IP for a specified duration (default 15 min)."""
    _blocked_ips[ip] = time.time() + duration_seconds
    logger.warning("IP blocked: %s for %d seconds", ip, duration_seconds)


def unblock_ip(ip: str):
    """Manually unblock an IP."""
    _blocked_ips.pop(ip, None)


# ═══════════════════════════════════════════════════════════════════════════
# LOGIN ATTEMPT TRACKING
# ═══════════════════════════════════════════════════════════════════════════

def record_login_attempt(ip: str, email: str = "", success: bool = False):
    """Record a login attempt for rate limiting."""
    now = time.time()

    if success:
        # Clear failed attempts on success
        _login_attempts.pop(ip, None)
        _failed_logins.pop(email, None)
        return

    # Track by IP
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    _login_attempts[ip].append(now)
    # Keep only last 15 minutes
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < 900]

    # Track by email
    if email:
        if email not in _failed_logins:
            _failed_logins[email] = {"count": 0, "last": now}
        _failed_logins[email]["count"] += 1
        _failed_logins[email]["last"] = now

    # Auto-block IP after 10 failed attempts in 15 minutes
    if len(_login_attempts.get(ip, [])) >= 10:
        block_ip(ip, 1800)  # 30 minutes
        logger.critical("Auto-blocked IP %s after 10 failed logins", ip)

    # Auto-lock account after 5 failed attempts
    if email and _failed_logins.get(email, {}).get("count", 0) >= 5:
        logger.warning("Account lockout threshold reached for %s", email)


def is_account_locked(email: str) -> bool:
    """Check if an account is locked due to too many failed attempts."""
    info = _failed_logins.get(email)
    if not info:
        return False
    # Lock for 15 minutes after 5 failures
    if info["count"] >= 5 and time.time() - info["last"] < 900:
        return True
    # Auto-unlock after cooldown
    if time.time() - info["last"] >= 900:
        _failed_logins.pop(email, None)
    return False


def get_remaining_lockout(email: str) -> int:
    """Get remaining lockout time in seconds."""
    info = _failed_logins.get(email)
    if not info or info["count"] < 5:
        return 0
    elapsed = time.time() - info["last"]
    remaining = 900 - elapsed
    return max(0, int(remaining))


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

    @app.before_request
    def check_ip_block():
        """Block requests from banned IPs."""
        ip = request.remote_addr
        if is_ip_blocked(ip):
            logger.warning("Blocked request from banned IP: %s", ip)
            return jsonify({
                "error": "ip_blocked",
                "message": "Too many failed attempts. Please try again later.",
            }), 429

    @app.after_request
    def add_security_headers(response):
        return apply_security_headers(response)

    logger.info("Security middleware initialized")
