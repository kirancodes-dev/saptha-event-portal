"""
auth_oauth.py — OAuth 2.0 / SSO Module for SapthaEvent

Supports Google and Microsoft OAuth flows for single sign-on.
Gracefully falls back to traditional login when credentials aren't configured.
"""
import logging
import secrets
from urllib.parse import urlencode

try:
    import requests
except Exception:
    requests = None
from flask import Blueprint, redirect, request, session, flash, current_app

from utils import ROLE_REDIRECTS

logger = logging.getLogger(__name__)
oauth_bp = Blueprint("oauth", __name__, url_prefix="/auth")


# ═══════════════════════════════════════════════════════════════════════════
# GOOGLE OAUTH 2.0
# ═══════════════════════════════════════════════════════════════════════════

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@oauth_bp.route("/google")
def google_login():
    """Redirect to Google OAuth consent screen."""
    client_id = current_app.config.get("OAUTH_GOOGLE_CLIENT_ID")
    if not client_id:
        flash("Google login is not configured for this instance.", "warning")
        return redirect("/login")

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = {
        "client_id": client_id,
        "redirect_uri": f"{current_app.config['BASE_URL']}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


@oauth_bp.route("/google/callback")
def google_callback():
    """Handle Google OAuth callback."""
    if request.args.get("state") != session.pop("oauth_state", None):
        flash("Invalid OAuth state. Please try again.", "danger")
        return redirect("/login")

    error = request.args.get("error")
    if error:
        flash(f"Google login cancelled: {error}", "warning")
        return redirect("/login")

    code = request.args.get("code")
    if not code:
        flash("No authorization code received.", "danger")
        return redirect("/login")

    # Exchange code for tokens
    try:
        token_resp = requests.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": current_app.config["OAUTH_GOOGLE_CLIENT_ID"],
            "client_secret": current_app.config["OAUTH_GOOGLE_CLIENT_SECRET"],
            "redirect_uri": f"{current_app.config['BASE_URL']}/auth/google/callback",
            "grant_type": "authorization_code",
        }, timeout=10)
        token_data = token_resp.json()

        if "access_token" not in token_data:
            flash("Failed to authenticate with Google.", "danger")
            return redirect("/login")

        # Get user info
        userinfo = requests.get(GOOGLE_USERINFO_URL, headers={
            "Authorization": f"Bearer {token_data['access_token']}",
        }, timeout=10).json()

        return _complete_oauth_login(
            email=userinfo.get("email", ""),
            name=userinfo.get("name", ""),
            provider="google",
            avatar_url=userinfo.get("picture", ""),
        )

    except Exception as exc:
        logger.error("Google OAuth error: %s", exc)
        flash("Google authentication failed. Please try again.", "danger")
        return redirect("/login")


# ═══════════════════════════════════════════════════════════════════════════
# MICROSOFT OAUTH 2.0
# ═══════════════════════════════════════════════════════════════════════════

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"


@oauth_bp.route("/microsoft")
def microsoft_login():
    """Redirect to Microsoft OAuth consent screen."""
    client_id = current_app.config.get("OAUTH_MICROSOFT_CLIENT_ID")
    if not client_id:
        flash("Microsoft login is not configured for this instance.", "warning")
        return redirect("/login")

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = {
        "client_id": client_id,
        "redirect_uri": f"{current_app.config['BASE_URL']}/auth/microsoft/callback",
        "response_type": "code",
        "scope": "openid email profile User.Read",
        "state": state,
        "prompt": "select_account",
    }
    return redirect(f"{MS_AUTH_URL}?{urlencode(params)}")


@oauth_bp.route("/microsoft/callback")
def microsoft_callback():
    """Handle Microsoft OAuth callback."""
    if request.args.get("state") != session.pop("oauth_state", None):
        flash("Invalid OAuth state. Please try again.", "danger")
        return redirect("/login")

    error = request.args.get("error")
    if error:
        flash(f"Microsoft login cancelled: {error}", "warning")
        return redirect("/login")

    code = request.args.get("code")
    if not code:
        flash("No authorization code received.", "danger")
        return redirect("/login")

    try:
        token_resp = requests.post(MS_TOKEN_URL, data={
            "code": code,
            "client_id": current_app.config["OAUTH_MICROSOFT_CLIENT_ID"],
            "client_secret": current_app.config["OAUTH_MICROSOFT_CLIENT_SECRET"],
            "redirect_uri": f"{current_app.config['BASE_URL']}/auth/microsoft/callback",
            "grant_type": "authorization_code",
            "scope": "openid email profile User.Read",
        }, timeout=10)
        token_data = token_resp.json()

        if "access_token" not in token_data:
            flash("Failed to authenticate with Microsoft.", "danger")
            return redirect("/login")

        userinfo = requests.get(MS_USERINFO_URL, headers={
            "Authorization": f"Bearer {token_data['access_token']}",
        }, timeout=10).json()

        return _complete_oauth_login(
            email=userinfo.get("mail") or userinfo.get("userPrincipalName", ""),
            name=userinfo.get("displayName", ""),
            provider="microsoft",
        )

    except Exception as exc:
        logger.error("Microsoft OAuth error: %s", exc)
        flash("Microsoft authentication failed. Please try again.", "danger")
        return redirect("/login")


# ═══════════════════════════════════════════════════════════════════════════
# COMMON OAUTH HANDLER
# ═══════════════════════════════════════════════════════════════════════════

def _complete_oauth_login(email: str, name: str, provider: str, avatar_url: str = ""):
    """Complete the OAuth flow: create/find user and set session."""
    from app import db

    if not email:
        flash("No email address received from provider.", "danger")
        return redirect("/login")

    email = email.lower().strip()
    user_doc = db.collection("users").document(email).get()

    if user_doc.exists:
        # Existing user — log in
        user = user_doc.to_dict()
        role = user.get("role", "Student")
    else:
        # New user — auto-register as Student
        import datetime
        user = {
            "name": name,
            "email": email,
            "role": "Student",
            "oauth_provider": provider,
            "avatar_url": avatar_url,
            "xp": 0,
            "badges": [],
            "is_active": True,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        db.collection("users").document(email).set(user)
        role = "Student"
        logger.info("OAuth auto-registered: %s via %s", email, provider)

    # Auto-detect org from email domain
    domain = email.split("@")[1] if "@" in email else ""
    if domain:
        from models_tenant import get_org_by_domain
        org = get_org_by_domain(db, domain)
        if org:
            session["org_id"] = org["id"]

    # Set session
    session["user_id"] = email
    session["role"] = role
    session["name"] = user.get("name", name)
    session["oauth_provider"] = provider

    flash(f"Welcome, {user.get('name', name)}! Signed in via {provider.title()}.", "success")
    return redirect(ROLE_REDIRECTS.get(role, "/"))
