"""
auth_2fa.py — Two-Factor Authentication (TOTP) for SapthaEvent

Provides TOTP-based 2FA for admin roles using pyotp.
Compatible with Google Authenticator, Authy, etc.
"""
import base64
import io
import logging
import secrets
from functools import wraps

import pyotp
import qrcode
from flask import Blueprint, request, session, redirect, flash, render_template_string, jsonify

from utils import login_required, role_required

logger = logging.getLogger(__name__)
twofa_bp = Blueprint("twofa", __name__, url_prefix="/auth/2fa")

# Roles that can enable 2FA
TWO_FA_ELIGIBLE_ROLES = {"Admin", "SuperAdmin", "Coordinator", "ClubSPOC"}


def _db():
    from app import db
    return db


def _generate_backup_codes(count: int = 8) -> list:
    """Generate one-time backup codes."""
    return [secrets.token_hex(4).upper() for _ in range(count)]


@twofa_bp.route("/setup", methods=["GET"])
@login_required
def setup_2fa():
    """Show 2FA setup page with QR code."""
    db = _db()
    email = session["user_id"]

    user_doc = db.collection("users").document(email).get()
    if not user_doc.exists:
        flash("User not found.", "danger")
        return redirect("/login")

    user = user_doc.to_dict()

    if user.get("totp_enabled"):
        flash("2FA is already enabled on your account.", "info")
        return redirect(f"/{session.get('role', 'participant').lower()}/dashboard")

    # Generate TOTP secret
    secret = pyotp.random_base32()
    session["pending_totp_secret"] = secret

    # Generate QR code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=email, issuer_name="SapthaEvent")

    qr = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return render_template_string(SETUP_TEMPLATE, qr_b64=qr_b64, secret=secret, email=email)


@twofa_bp.route("/verify-setup", methods=["POST"])
@login_required
def verify_setup():
    """Verify the TOTP code to complete 2FA setup."""
    db = _db()
    email = session["user_id"]
    code = (request.form.get("code") or "").strip()
    secret = session.get("pending_totp_secret")

    if not secret:
        flash("2FA setup session expired. Please try again.", "danger")
        return redirect("/auth/2fa/setup")

    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        flash("Invalid verification code. Please try again.", "danger")
        return redirect("/auth/2fa/setup")

    # Generate backup codes
    backup_codes = _generate_backup_codes()

    # Save to Firestore
    db.collection("users").document(email).update({
        "totp_secret": secret,
        "totp_enabled": True,
        "totp_backup_codes": backup_codes,
    })

    session.pop("pending_totp_secret", None)
    session["2fa_verified"] = True

    flash("2FA has been enabled successfully!", "success")
    return render_template_string(BACKUP_CODES_TEMPLATE, backup_codes=backup_codes)


@twofa_bp.route("/verify", methods=["GET", "POST"])
def verify_2fa():
    """Verify 2FA code during login."""
    if request.method == "GET":
        if "pending_2fa_email" not in session:
            return redirect("/login")
        return render_template_string(VERIFY_TEMPLATE)

    db = _db()
    email = session.get("pending_2fa_email")
    code = (request.form.get("code") or "").strip()

    if not email:
        flash("Session expired. Please log in again.", "danger")
        return redirect("/login")

    user_doc = db.collection("users").document(email).get()
    if not user_doc.exists:
        return redirect("/login")

    user = user_doc.to_dict()
    secret = user.get("totp_secret")

    # Check TOTP code
    totp = pyotp.TOTP(secret)
    if totp.verify(code, valid_window=1):
        _complete_2fa_login(user, email)
        return redirect(ROLE_REDIRECTS.get(session.get("role"), "/"))

    # Check backup codes
    backup_codes = user.get("totp_backup_codes", [])
    if code in backup_codes:
        backup_codes.remove(code)
        db.collection("users").document(email).update({
            "totp_backup_codes": backup_codes,
        })
        _complete_2fa_login(user, email)
        flash("Backup code used. Consider generating new ones.", "warning")
        return redirect(ROLE_REDIRECTS.get(session.get("role"), "/"))

    flash("Invalid 2FA code. Please try again.", "danger")
    return redirect("/auth/2fa/verify")


@twofa_bp.route("/disable", methods=["POST"])
@login_required
def disable_2fa():
    """Disable 2FA (requires password confirmation)."""
    db = _db()
    email = session["user_id"]
    password = request.form.get("password", "")

    user_doc = db.collection("users").document(email).get()
    if not user_doc.exists:
        return jsonify({"error": "User not found"}), 404

    user = user_doc.to_dict()
    from werkzeug.security import check_password_hash
    stored = user.get("password_hash", "")
    if not check_password_hash(stored, password):
        flash("Incorrect password.", "danger")
        return redirect("/profile/dashboard")

    db.collection("users").document(email).update({
        "totp_secret": None,
        "totp_enabled": False,
        "totp_backup_codes": [],
    })

    flash("2FA has been disabled.", "info")
    return redirect("/profile/dashboard")


def _complete_2fa_login(user: dict, email: str):
    """Finalize login after successful 2FA verification."""
    from utils import ROLE_REDIRECTS
    session.pop("pending_2fa_email", None)
    session.pop("pending_2fa_role", None)
    session["user_id"] = email
    session["role"] = user.get("role", "Student")
    session["name"] = user.get("name", "")
    session["2fa_verified"] = True


def requires_2fa_check(f):
    """Decorator for login route: redirect to 2FA if enabled."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("pending_2fa_email"):
            return redirect("/auth/2fa/verify")
        return f(*args, **kwargs)
    return decorated


# Need to import this here to avoid circular dependency
from utils import ROLE_REDIRECTS  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# INLINE TEMPLATES (minimal, extend base_classic.html in production)
# ═══════════════════════════════════════════════════════════════════════════

SETUP_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Setup 2FA — SapthaEvent</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/global.css">
</head>
<body class="bg-light">
<div class="container py-5" style="max-width:500px">
    <div class="card shadow-sm">
        <div class="card-body text-center p-4">
            <h3 class="mb-3">🔐 Set Up Two-Factor Authentication</h3>
            <p>Scan this QR code with your authenticator app:</p>
            <img src="data:image/png;base64,{{ qr_b64 }}" class="img-fluid mb-3" alt="2FA QR Code" style="max-width:200px">
            <p class="text-muted small">Or enter this key manually: <code>{{ secret }}</code></p>
            <hr>
            <form method="POST" action="/auth/2fa/verify-setup">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <div class="mb-3">
                    <label class="form-label">Enter the 6-digit code from your app:</label>
                    <input type="text" name="code" class="form-control text-center" maxlength="6"
                           pattern="[0-9]{6}" required autocomplete="one-time-code" inputmode="numeric">
                </div>
                <button type="submit" class="btn btn-primary w-100">Verify & Enable 2FA</button>
            </form>
        </div>
    </div>
</div>
</body></html>
"""

VERIFY_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>2FA Verification — SapthaEvent</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/global.css">
</head>
<body class="bg-light">
<div class="container py-5" style="max-width:400px">
    <div class="card shadow-sm">
        <div class="card-body text-center p-4">
            <h3>🔐 Two-Factor Authentication</h3>
            <p>Enter the code from your authenticator app:</p>
            <form method="POST" action="/auth/2fa/verify">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <input type="text" name="code" class="form-control text-center mb-3" maxlength="6"
                       pattern="[0-9A-Fa-f]+" required autocomplete="one-time-code" inputmode="numeric"
                       placeholder="000000" autofocus>
                <button type="submit" class="btn btn-primary w-100">Verify</button>
                <p class="mt-3 text-muted small">You can also use a backup code.</p>
            </form>
        </div>
    </div>
</div>
</body></html>
"""

BACKUP_CODES_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backup Codes — SapthaEvent</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/global.css">
    <style>@media print { .no-print { display: none; } }</style>
</head>
<body class="bg-light">
<div class="container py-5" style="max-width:500px">
    <div class="card shadow-sm">
        <div class="card-body p-4">
            <h3 class="text-center">✅ 2FA Enabled Successfully</h3>
            <div class="alert alert-warning mt-3">
                <strong>Save these backup codes!</strong> Each code can only be used once.
                Store them securely — you'll need them if you lose access to your authenticator.
            </div>
            <div class="row g-2 mb-3">
                {% for code in backup_codes %}
                <div class="col-6"><code class="d-block text-center p-2 bg-light border rounded">{{ code }}</code></div>
                {% endfor %}
            </div>
            <div class="d-flex gap-2 no-print">
                <button onclick="window.print()" class="btn btn-outline-secondary flex-fill">🖨 Print</button>
                <a href="/" class="btn btn-primary flex-fill">Continue</a>
            </div>
        </div>
    </div>
</div>
</body></html>
"""
