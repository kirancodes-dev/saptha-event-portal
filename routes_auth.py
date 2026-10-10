import datetime
import hmac
import logging
from flask import Blueprint, render_template, request, redirect, session, flash, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from models import db

from utils import log_action, ROLE_REDIRECTS, validate_password_strength
import services_login_throttle as throttle
import utils_email
from utils_email import send_password_reset_email

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__)

# One answer for every failed login, and one for every reset request, so
# neither tells whether an email has an account (UPG-35)
LOGIN_FAILED_MESSAGE = 'Email or password is incorrect.'
RESET_REQUESTED_MESSAGE = "If an account exists for this email, we've sent a reset link."

# Password-reset tokens: services_accounts.make_reset_token / load_reset_token
# (one hour, bound to the current password so each link works once, UPG-33).

# NOTE: ROLE_REDIRECTS is now defined in utils.py — single source of truth.


def _redirect_by_role(role: str):
    return redirect(ROLE_REDIRECTS.get(role, '/'))


# Stored role -> the role a user logs in as. Includes the scoped names the
# old "Migrate roles" button wrote (UniversityAdmin, UnitAdmin), so accounts
# it touched can log in again (BLK-07).
_LOGIN_ROLE = {
    'Super Admin': 'SuperAdmin', 'Admin': 'SuperAdmin', 'UniversityAdmin': 'SuperAdmin',
    'Coordinator': 'EventCoordinator',
    'SPOC': 'ClubSPOC', 'UnitAdmin': 'ClubSPOC',
    'Participant': 'Student',
}


def _login_role(stored_role) -> str:
    role = getattr(stored_role, 'value', stored_role)
    role = str(role or '').strip()
    return _LOGIN_ROLE.get(role, role)


def _safe_next():
    from services_accounts import is_safe_next
    target = (request.form.get('next') or request.args.get('next') or '').strip()
    return target if is_safe_next(target) else ''


def _throttled(template, wait):
    """429 with the page and a "try again in N seconds" message (BLK-13)."""
    flash(throttle.message(wait), 'danger')
    return render_template(template), 429, {'Retry-After': str(wait)}


# =========================================================
# 1. LOGIN
# =========================================================
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, go home (or back to the page that sent them here)
    if 'user_id' in session:
        return redirect(_safe_next()) if _safe_next() else _redirect_by_role(session.get('role', ''))

    if request.method == 'POST':
        role        = request.form.get('role', '').strip()
        email       = request.form.get('email', '').lower().strip()
        password    = request.form.get('password', '')
        secret_key  = request.form.get('secret_key', '').strip()
        remember_me = request.form.get('remember_me') == 'on'  # checkbox

        # Normalise legacy DB value
        if role == 'Super Admin':
            role = 'SuperAdmin'

        # Too many recent failures from this IP or on this account (BLK-13).
        # Checked before anything about the account, so the answer doesn't
        # reveal whether it exists.
        wait = throttle.retry_after(throttle.LOGIN, request.remote_addr, email)
        if wait:
            log_action("LOGIN_THROTTLED", f"Login refused for {email} for {wait}s")
            return _throttled('login.html', wait)

        # Master key check for SuperAdmin
        MASTER_KEY = current_app.config.get('MASTER_SECRET_KEY', '')
        if role == 'SuperAdmin' and MASTER_KEY and not hmac.compare_digest(secret_key, MASTER_KEY):
            throttle.record_failure(throttle.LOGIN, request.remote_addr, email)
            flash('🔒 Invalid Master Security Key. Access denied.', 'danger')
            log_action("LOGIN_FAILED", f"Bad master key attempt for {email}")
            return redirect('/login')

        if not email or not password:
            flash('Please enter both email and password.', 'warning')
            return redirect('/login')

        try:
            user_doc = db.collection('users').document(email).get()
            user = None
            if user_doc.exists:
                user = user_doc.to_dict()

            if not user:
                # Auto-create SuperAdmin on very first boot
                SUPER_EMAIL = current_app.config.get('SUPER_ADMIN_EMAIL', '')
                SUPER_PASS  = current_app.config.get('SUPER_ADMIN_DEFAULT_PASS', '')
                if (role == 'SuperAdmin' and SUPER_EMAIL and SUPER_PASS
                        and email == SUPER_EMAIL
                        and hmac.compare_digest(password, SUPER_PASS)):
                    db.collection('users').document(email).set({
                        'name': 'System Super Admin',
                        'role': 'SuperAdmin',
                        'category': 'All',
                        'password': generate_password_hash(password, method='pbkdf2:sha256'),
                        'needs_password_reset': False
                    })
                    _set_session(email, 'System Super Admin', 'SuperAdmin', 'All', remember_me=remember_me)
                    throttle.clear_account(throttle.LOGIN, email)
                    flash("👑 Super Admin account initialised!", "success")
                    log_action("SUPER_ADMIN_INIT", f"First-boot SuperAdmin created: {email}")
                    return redirect('/admin/dashboard')

                throttle.record_failure(throttle.LOGIN, request.remote_addr, email)
                flash(LOGIN_FAILED_MESSAGE, 'danger')  # same as a wrong password (UPG-35)
                return redirect('/login')

            db_role = _login_role(user.get('role', 'Participant'))

            # Password verification — hashed only.
            stored_pw = user.get('password') or user.get('password_hash') or ''
            if isinstance(stored_pw, (int, float)):
                stored_pw = str(int(stored_pw))

            if stored_pw.startswith(('scrypt:', 'pbkdf2:', 'argon2:')):
                valid = check_password_hash(stored_pw, password)
            else:
                valid = False
                logger.warning(
                    "Login blocked — legacy unhashed password on %s. "
                    "Admin must trigger password reset.", email)
                log_action("LOGIN_BLOCKED_LEGACY_HASH",
                           f"Unhashed password on account {email}")

            if not valid or db_role != role:
                throttle.record_failure(throttle.LOGIN, request.remote_addr, email)
                # Unknown email, wrong password and an old unhashed password all
                # get the same answer (UPG-35). Only someone who already has the
                # right password learns that the role was wrong.
                flash(LOGIN_FAILED_MESSAGE if not valid else
                      'Wrong role selected for this account. Choose your role and try again.', 'danger')
                log_action("LOGIN_FAILED", f"Bad credentials for {email} (role={role})")
                return redirect('/login')

            user_name = user.get('name', 'User')
            user_category = user.get('category', 'General')
            if hasattr(user_category, 'value'):
                user_category = user_category.value
            user_category = str(user_category)

            _set_session(email,
                         user_name,
                         role,
                         user_category,
                         remember_me=remember_me)
            throttle.clear_account(throttle.LOGIN, email)

            # Force password reset for auto-generated accounts
            if user.get('needs_password_reset', False):
                session['force_reset'] = True
                flash("Welcome! You must set a new password before continuing.", "warning")
                return redirect('/reset_password')

            flash(f"Welcome back, {user_name}! 👋", "success")
            log_action("LOGIN_SUCCESS", f"{email} logged in as {role}")
            if _safe_next():
                return redirect(_safe_next())
            return _redirect_by_role(role)

        except Exception as exc:
            flash(f"Login error: {exc}", "danger")
            current_app.logger.error("Login exception: %s", exc)

    return render_template('login.html')


# =========================================================
# 2. FORCE PASSWORD RESET (on first login)
# =========================================================
@auth_bp.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if 'user_id' not in session or not session.get('force_reset'):
        return redirect('/login')

    if request.method == 'POST':
        new_pw      = request.form.get('new_password', '')
        confirm_pw  = request.form.get('confirm_password', '')

        ok, pw_err = validate_password_strength(new_pw)
        if new_pw != confirm_pw:
            flash("Passwords do not match.", "danger")
            return redirect('/reset_password')
        if not ok:
            flash(pw_err, "danger")
            return redirect('/reset_password')

        try:
            email = session['user_id']
            user_ref = db.collection('users').document(email)
            if user_ref.get().exists:
                user_ref.update({
                    'password': generate_password_hash(new_pw, method='pbkdf2:sha256'),
                    'needs_password_reset': False
                })
            session.pop('force_reset', None)
            flash("✅ Password updated. Welcome to your dashboard!", "success")
            log_action("PASSWORD_RESET", f"{email} changed forced password")
            return _redirect_by_role(session.get('role', ''))

        except Exception as exc:
            flash(f"Error updating password: {exc}", "danger")

    return render_template('reset_password.html')


# =========================================================
# 2b. SET PASSWORD — one-time link for accounts created by a registration
# =========================================================
@auth_bp.route('/set_password/<token>', methods=['GET', 'POST'])
def set_password(token):
    from services_accounts import load_set_password_token

    email, user, error = load_set_password_token(token, db)
    if error:
        messages = {
            'expired': "This link has expired. Use \"Forgot password\" to get a new one.",
            'used':    "This link has already been used. Log in, or use \"Forgot password\".",
        }
        flash(messages.get(error, "Invalid link."), "danger")
        return redirect('/forgot_password' if error == 'expired' else '/login')

    if request.method == 'POST':
        new_pw     = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')
        ok, pw_err = validate_password_strength(new_pw)
        if new_pw != confirm_pw:
            flash("Passwords do not match.", "danger")
            return redirect(request.path)
        if not ok:
            flash(pw_err, "danger")
            return redirect(request.path)

        db.collection('users').document(email).update({
            'password':             generate_password_hash(new_pw, method='pbkdf2:sha256'),
            'needs_password_reset': False,
            'email_verified':       True,
        })
        role = _login_role(user.get('role', 'Student')) or 'Student'
        category = user.get('category', 'General')
        if hasattr(category, 'value'):
            category = category.value
        _set_session(email, user.get('name', 'User'), role, str(category), remember_me=False)
        log_action("PASSWORD_SET_LINK", f"{email} set a password via the registration link")
        flash("✅ Password set. Welcome to SapthaEvent!", "success")
        return _redirect_by_role(role)

    return render_template('reset_password_token.html', email=email, name=user.get('name', 'User'))


# =========================================================
# 3. STUDENT SELF-REGISTRATION
# =========================================================
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return _redirect_by_role(session.get('role', ''))

    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        usn      = request.form.get('usn', '').strip().upper()
        email    = request.form.get('email', '').lower().strip()
        phone    = request.form.get('phone', '').strip()
        password = request.form.get('password', '')

        if not name or not email or not password:
            flash('Name, email, and password are required.', 'warning')
            return redirect('/register')

        ok, pw_err = validate_password_strength(password)
        if not ok:
            flash(pw_err, 'warning')
            return redirect('/register')

        try:
            existing_doc = db.collection('users').document(email).get()
            if existing_doc.exists:
                flash('An account with this email already exists. Please log in.', 'warning')
                return redirect('/login')

            from services_privacy import consent_given, consent_record, record_consent
            if not consent_given(request.form):
                flash("Please tick the box to agree to the privacy notice; we can't create your account "
                      "without it.", 'warning')
                return redirect('/register')

            db.collection('users').document(email).set({
                'name':                name,
                'usn':                 usn,
                'phone':               phone,
                'role':                'Student',
                'category':            'General',
                'password':            generate_password_hash(password, method='pbkdf2:sha256'),
                'created_at':          datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'needs_password_reset': False,
                'privacy_consent':     consent_record(),   # UPG-22
            })
            record_consent(db, email)
            _set_session(email, name, 'Student', 'General')
            log_action("USER_REGISTERED", f"New student self-registered: {email}")
            flash(f"🎉 Welcome, {name}! Your account is ready.", "success")
            return redirect('/participant/dashboard')

        except Exception as exc:
            current_app.logger.error("Registration exception: %s", exc)
            flash(f"Could not create account: {exc}", "danger")
            return redirect('/register')

    return render_template('register.html')


# =========================================================
# 4. FORGOT PASSWORD — request reset link via email
# =========================================================
@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if 'user_id' in session:
        return _redirect_by_role(session.get('role', ''))

    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()

        if not email:
            flash("Please enter your email address.", "warning")
            return redirect('/forgot_password')

        # Every request counts, for known and unknown emails alike (BLK-13)
        wait = throttle.retry_after(throttle.RESET, request.remote_addr, email)
        if wait:
            log_action("RESET_REQ_THROTTLED", f"Reset request refused for {email} for {wait}s")
            return _throttled('forgot_password.html', wait)
        throttle.record_failure(throttle.RESET, request.remote_addr, email)

        # Generic response in all cases — never reveal whether the email exists
        generic_msg = RESET_REQUESTED_MESSAGE  # the same for every email (UPG-35)

        try:
            user_doc = db.collection('users').document(email).get()
            if not user_doc.exists:
                flash(generic_msg, "info")
                log_action("RESET_REQ_NOACCT", f"Reset requested for unknown {email}")
                return redirect('/forgot_password')

            user = user_doc.to_dict()
            role = _login_role(user.get('role', 'Participant'))

            # SuperAdmin cannot reset via email — use master key recovery path
            if role == 'SuperAdmin':
                flash(generic_msg, "info")
                log_action("RESET_REQ_BLOCKED_SUPER",
                           f"SuperAdmin {email} attempted email-based reset")
                return redirect('/forgot_password')

            # Bound to the current password, so the link works once (UPG-33)
            from services_accounts import make_reset_token
            token = make_reset_token(email, user.get('password', ''))
            # BASE_URL, never the request's host: a forged Host would send
            # the victim's token to another site (BLK-16)
            reset_url = f"{utils_email._base_url()}/reset_token/{token}"

            user_name = user.get('name', 'User')
            sent = send_password_reset_email(email,
                                             user_name,
                                             reset_url)
            if sent:
                log_action("RESET_LINK_SENT",
                           f"Reset link emailed to {email} (role={role})")
            else:
                log_action("RESET_LINK_FAIL",
                           f"Email send failed for {email}")

            flash(generic_msg, "info")
            return redirect('/forgot_password')

        except Exception as exc:
            current_app.logger.error("Forgot-password error: %s", exc)
            flash("Something went wrong. Please try again.", "danger")
            return redirect('/forgot_password')

    return render_template('forgot_password.html')


# =========================================================
# 5. RESET WITH TOKEN — link from email
# =========================================================
@auth_bp.route('/reset_token/<token>', methods=['GET', 'POST'])
def reset_token(token):
    from services_accounts import load_reset_token
    email, _, error = load_reset_token(token, db)
    if error:
        flash({'expired': "This reset link has expired. Please request a new one.",
               'used':    "This reset link has already been used. Request a new one if you need it.",
               }.get(error, "Invalid reset link."), "danger")
        return redirect('/forgot_password')

    try:
        user_doc = db.collection('users').document(email).get()
        if not user_doc.exists:
            flash("Account no longer exists.", "danger")
            return redirect('/login')
        user = user_doc.to_dict()

        role = _login_role(user.get('role', 'Participant'))
        if role == 'SuperAdmin':
            flash("SuperAdmin cannot be reset via email.", "danger")
            return redirect('/login')

        if request.method == 'POST':
            new_pw     = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')

            ok, pw_err = validate_password_strength(new_pw)
            if new_pw != confirm_pw:
                flash("Passwords do not match.", "danger")
                return redirect(request.path)
            if not ok:
                flash(pw_err, "danger")
                return redirect(request.path)

            try:
                db.collection('users').document(email).update({
                    'password': generate_password_hash(new_pw, method='pbkdf2:sha256'),
                    'needs_password_reset': False
                })
                log_action("PASSWORD_RESET_EMAIL",
                           f"{email} reset password via email token")
                flash("✅ Password updated. You can now log in.", "success")
                return redirect('/login')
            except Exception as exc:
                current_app.logger.error("Reset-token update error: %s", exc)
                flash("Could not update password. Try again.", "danger")
                return redirect(request.path)

        user_name = user.get('name', 'User')
        return render_template('reset_password_token.html',
                               email=email, name=user_name)

    except Exception as exc:
        current_app.logger.error("Reset-token flow error: %s", exc)
        flash("Something went wrong. Please try again.", "danger")
        return redirect('/forgot_password')
# =========================================================
@auth_bp.route('/logout')
def logout():
    user = session.get('user_id', 'unknown')
    log_action("LOGOUT", f"{user} logged out")
    session.clear()
    flash("You have been logged out.", "info")
    return redirect('/')


# =========================================================
# 7. EMAIL DIAGNOSTIC — SuperAdmin only
#    Usage: /diag/email?to=you@example.com
# =========================================================
@auth_bp.route('/diag/email')
def diag_email():
    import os as _os

    if session.get('role') not in ('SuperAdmin', 'Super Admin'):
        return {"error": "forbidden"}, 403

    to = (request.args.get('to') or session.get('user_id') or '').strip()
    if not to:
        return {"error": "pass ?to=email@address"}, 400

    if _os.environ.get('BREVO_API_KEY'):
        provider = "Brevo"
    elif _os.environ.get('RESEND_API_KEY'):
        provider = "Resend"
    else:
        provider = "Gmail SMTP"

    from_addr = _os.environ.get(
        'MAIL_FROM',
        f"SapthaEvent <{_os.environ.get('MAIL_USER', '(unset)')}>"
    )

    utils_email.LAST_EMAIL_ERROR = ""
    ok = utils_email._send(
        to, "SapthaEvent — Email Diagnostic",
        "<p>If you can read this, email delivery is working. ✅</p>"
    )

    hints = {
        "Brevo":     "Brevo: free 300/day, sends to anyone. If failing check BREVO_API_KEY and MAIL_FROM.",
        "Resend":    "Resend free plan only sends to the Resend account owner's email until domain is verified.",
        "Gmail SMTP":"Gmail SMTP is blocked by Railway's outbound SMTP firewall. Use Brevo instead.",
    }
    return {
        "provider":        provider,
        "from":            from_addr,
        "to":              to,
        "sent":            ok,
        "error":           utils_email.LAST_EMAIL_ERROR or None,
        "brevo_key_set":   bool(_os.environ.get('BREVO_API_KEY')),
        "resend_key_set":  bool(_os.environ.get('RESEND_API_KEY')),
        "mail_user_set":   bool(_os.environ.get('MAIL_USER')),
        "mail_pass_set":   bool(_os.environ.get('MAIL_PASS')),
        "hint":            hints.get(provider, ""),
    }


# =========================================================
# INTERNAL HELPER
# =========================================================
def _set_session(email: str, name: str, role: str, category: str,
                 remember_me: bool = True):
    """
    Stores user identity into the Flask session.

    remember_me=True  → persistent cookie (PERMANENT_SESSION_LIFETIME, 30 days)
    remember_me=False → browser-session cookie, cleared when the browser closes

    The lifetime is app-wide config, so it must not be changed per login.
    """
    session.permanent = bool(remember_me)

    session['user_id']      = email
    session['name']         = name
    session['role']         = role
    session['category']     = category
    session['remember_me']  = remember_me
