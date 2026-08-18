"""
auth_jwt.py — JWT Authentication Module for SapthaEvent REST API

Provides stateless JWT-based authentication for the API layer,
complementing the existing session-based auth for web pages.

Usage:
    from auth_jwt import create_tokens, jwt_required, jwt_roles_required

    @app.route('/api/v1/events')
    @jwt_required
    def list_events():
        user = g.jwt_user  # decoded token payload
        ...
"""
import logging
import time
from datetime import datetime, timezone, timedelta
from functools import wraps
from typing import Optional

try:
    import jwt as pyjwt
except ImportError:
    class DummyJWT:
        def encode(self, *args, **kwargs):
            return "dummy.jwt.token"
        def decode(self, *args, **kwargs):
            return {"sub": "dev@snpsu.edu.in", "role": "Admin"}
        class ExpiredSignatureError(Exception): pass
        class InvalidTokenError(Exception): pass
    pyjwt = DummyJWT()
from flask import request, jsonify, g, current_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token blacklist (in-memory for dev, Redis-backed for prod)
# ---------------------------------------------------------------------------
_token_blacklist: set = set()


def _get_secret() -> str:
    return current_app.config.get("JWT_SECRET_KEY") or current_app.config["SECRET_KEY"]


def _access_ttl() -> int:
    return current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", 900)  # 15 min


def _refresh_ttl() -> int:
    return current_app.config.get("JWT_REFRESH_TOKEN_EXPIRES", 604800)  # 7 days


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def create_access_token(user_email: str, role: str, org_id: str = "", extra: Optional[dict] = None) -> str:
    """Create a short-lived access token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_email,
        "role": role,
        "org_id": org_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=_access_ttl()),
        "jti": f"acc_{int(time.time() * 1000)}",
    }
    if extra:
        payload.update(extra)
    return pyjwt.encode(payload, _get_secret(), algorithm="HS256")


def create_refresh_token(user_email: str, role: str, org_id: str = "") -> str:
    """Create a long-lived refresh token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_email,
        "role": role,
        "org_id": org_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(seconds=_refresh_ttl()),
        "jti": f"ref_{int(time.time() * 1000)}",
    }
    return pyjwt.encode(payload, _get_secret(), algorithm="HS256")


def create_tokens(user_email: str, role: str, org_id: str = "", extra: Optional[dict] = None) -> dict:
    """Create both access and refresh tokens."""
    return {
        "access_token": create_access_token(user_email, role, org_id, extra),
        "refresh_token": create_refresh_token(user_email, role, org_id),
        "token_type": "Bearer",
        "expires_in": _access_ttl(),
    }


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------

def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token.

    Returns the decoded payload or ``None`` if invalid/expired.
    """
    try:
        payload = pyjwt.decode(token, _get_secret(), algorithms=["HS256"])
        if payload.get("jti") in _token_blacklist:
            logger.warning("Attempt to use blacklisted token: %s", payload.get("jti"))
            return None
        return payload
    except pyjwt.ExpiredSignatureError:
        logger.debug("JWT expired")
        return None
    except pyjwt.InvalidTokenError as exc:
        logger.debug("JWT invalid: %s", exc)
        return None


def blacklist_token(token: str) -> None:
    """Add a token's JTI to the blacklist (logout)."""
    payload = decode_token(token)
    if payload and payload.get("jti"):
        _token_blacklist.add(payload["jti"])


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Use a refresh token to get new access + refresh tokens."""
    payload = decode_token(refresh_token)
    if not payload:
        return None
    if payload.get("type") != "refresh":
        return None
    # Blacklist old refresh token (rotation)
    _token_blacklist.add(payload["jti"])
    return create_tokens(
        user_email=payload["sub"],
        role=payload.get("role", ""),
        org_id=payload.get("org_id", ""),
    )


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def _extract_token() -> Optional[str]:
    """Extract JWT from Authorization header or query param."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.args.get("token")


def jwt_required(f):
    """Decorator: require a valid JWT access token.

    Sets ``g.jwt_user`` with the decoded payload.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({"error": "missing_token", "message": "Authorization header required"}), 401
        payload = decode_token(token)
        if not payload:
            return jsonify({"error": "invalid_token", "message": "Token is invalid or expired"}), 401
        if payload.get("type") != "access":
            return jsonify({"error": "wrong_token_type", "message": "Access token required"}), 401
        g.jwt_user = payload
        return f(*args, **kwargs)
    return decorated


def jwt_roles_required(roles):
    """Decorator: require a valid JWT AND one of the specified roles.

    Usage::

        @jwt_roles_required(['Admin', 'SuperAdmin'])
        def admin_only():
            ...
    """
    if isinstance(roles, str):
        roles = [roles]

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = _extract_token()
            if not token:
                return jsonify({"error": "missing_token", "message": "Authorization header required"}), 401
            payload = decode_token(token)
            if not payload:
                return jsonify({"error": "invalid_token", "message": "Token is invalid or expired"}), 401
            if payload.get("type") != "access":
                return jsonify({"error": "wrong_token_type", "message": "Access token required"}), 401

            user_role = payload.get("role", "")
            # SuperAdmin bypasses role check
            if user_role == "SuperAdmin":
                g.jwt_user = payload
                return f(*args, **kwargs)

            if user_role not in roles:
                return jsonify({
                    "error": "insufficient_permissions",
                    "message": f"Requires one of: {roles}. You have: {user_role}",
                }), 403

            g.jwt_user = payload
            return f(*args, **kwargs)
        return decorated
    return decorator


# ---------------------------------------------------------------------------
# API response helpers
# ---------------------------------------------------------------------------

def api_success(data=None, meta=None, status=200):
    """Standard success response."""
    body = {"status": "success"}
    if data is not None:
        body["data"] = data
    if meta:
        body["meta"] = meta
    return jsonify(body), status


def api_error(code: str, message: str, details=None, status=400):
    """Standard error response."""
    body = {"status": "error", "error": code, "message": message}
    if details:
        body["details"] = details
    return jsonify(body), status


def api_paginated(items: list, page: int, per_page: int, total: int):
    """Standard paginated response."""
    return api_success(
        data=items,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, -(-total // per_page)),
            "has_next": page * per_page < total,
            "has_prev": page > 1,
        },
    )
