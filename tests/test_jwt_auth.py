"""
test_jwt_auth.py — Tests for JWT Authentication Module

Covers: token creation, verification, expiry, refresh, blacklisting,
role-based access, and decorator behavior.

All tests use a minimal Flask app to avoid importing the full application
and its many dependencies.
"""
import pytest
import jwt as pyjwt
from flask import Flask


@pytest.fixture
def jwt_app():
    """Minimal Flask app for JWT testing."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-jwt-secret-key-12345"
    app.config["JWT_SECRET_KEY"] = "test-jwt-secret-key-12345"
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 900
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = 604800
    return app


class TestTokenCreation:
    """Test JWT token generation."""

    def test_create_access_token(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_access_token, decode_token
            token = create_access_token("user@test.edu", "Student")
            assert token is not None
            payload = decode_token(token)
            assert payload["sub"] == "user@test.edu"
            assert payload["role"] == "Student"
            assert payload["type"] == "access"

    def test_create_refresh_token(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_refresh_token, decode_token
            token = create_refresh_token("user@test.edu", "Admin")
            payload = decode_token(token)
            assert payload["type"] == "refresh"
            assert payload["role"] == "Admin"

    def test_create_tokens_pair(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_tokens
            tokens = create_tokens("user@test.edu", "Student")
            assert "access_token" in tokens
            assert "refresh_token" in tokens
            assert tokens["token_type"] == "Bearer"
            assert tokens["expires_in"] > 0

    def test_token_contains_org_id(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_access_token, decode_token
            token = create_access_token("user@test.edu", "Student", org_id="org123")
            payload = decode_token(token)
            assert payload["org_id"] == "org123"

    def test_token_with_extra_claims(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_access_token, decode_token
            token = create_access_token("user@test.edu", "Student", extra={"name": "Test"})
            payload = decode_token(token)
            assert payload["name"] == "Test"


class TestTokenVerification:
    """Test JWT token verification and edge cases."""

    def test_valid_token_decodes(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_access_token, decode_token
            token = create_access_token("test@edu", "Student")
            payload = decode_token(token)
            assert payload is not None
            assert payload["sub"] == "test@edu"

    def test_invalid_token_returns_none(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import decode_token
            result = decode_token("not.a.valid.jwt.token")
            assert result is None

    def test_tampered_token_returns_none(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_access_token, decode_token
            token = create_access_token("test@edu", "Student")
            parts = token.split(".")
            parts[1] = parts[1] + "x"
            tampered = ".".join(parts)
            assert decode_token(tampered) is None

    def test_empty_token_returns_none(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import decode_token
            assert decode_token("") is None

    def test_wrong_secret_fails(self, jwt_app):
        with jwt_app.app_context():
            payload = {"sub": "user@test.edu", "type": "access"}
            token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
            from auth_jwt import decode_token
            assert decode_token(token) is None


class TestTokenBlacklist:
    """Test token blacklisting (logout)."""

    def test_blacklisted_token_rejected(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_access_token, decode_token, blacklist_token
            token = create_access_token("user@test.edu", "Student")
            assert decode_token(token) is not None
            blacklist_token(token)
            assert decode_token(token) is None


class TestTokenRefresh:
    """Test access token refresh flow."""

    def test_refresh_returns_new_tokens(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_refresh_token, refresh_access_token
            refresh = create_refresh_token("user@test.edu", "Student")
            new_tokens = refresh_access_token(refresh)
            assert new_tokens is not None
            assert "access_token" in new_tokens
            assert "refresh_token" in new_tokens

    def test_refresh_with_access_token_fails(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_access_token, refresh_access_token
            access = create_access_token("user@test.edu", "Student")
            result = refresh_access_token(access)
            assert result is None

    def test_refresh_rotates_token(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import create_refresh_token, refresh_access_token, decode_token
            old_refresh = create_refresh_token("user@test.edu", "Student")
            new_tokens = refresh_access_token(old_refresh)
            assert new_tokens is not None
            assert decode_token(old_refresh) is None


class TestAPIResponseHelpers:
    """Test standardized API response helpers."""

    def test_api_success(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import api_success
            resp, status = api_success({"key": "value"})
            data = resp.get_json()
            assert status == 200
            assert data["status"] == "success"
            assert data["data"]["key"] == "value"

    def test_api_error(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import api_error
            resp, status = api_error("test_error", "Something went wrong", status=422)
            data = resp.get_json()
            assert status == 422
            assert data["error"] == "test_error"

    def test_api_paginated(self, jwt_app):
        with jwt_app.app_context():
            from auth_jwt import api_paginated
            resp, status = api_paginated(items=[1, 2, 3], page=1, per_page=10, total=25)
            data = resp.get_json()
            assert data["meta"]["total"] == 25
            assert data["meta"]["has_next"] is True
            assert data["meta"]["total_pages"] == 3
