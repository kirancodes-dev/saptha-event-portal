import datetime
import logging
from flask import Blueprint, render_template, request, redirect, session, flash, current_app, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import check_password_hash, generate_password_hash
from models import db
from utils import log_action
import utils_email
from utils_email import send_password_reset_email

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__)

RESET_TOKEN_SALT    = 'sapthaevent-password-reset'
RESET_TOKEN_MAX_AGE = 3600  # 1 hour


def _reset_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=RESET_TOKEN_SALT)

# Role → dashboard URL map (single source of truth)
ROLE_REDIRECTS = {
    'Student':          '/participant/dashboard',
    'SuperAdmin':       '/admin/dashboard',
    'Super Admin':      '/admin/dashboard',
    'Admin':            '/admin/dashboard',
    'Coordinator':      '/coordinator/dashboard',
    'ClubSPOC':         '/spoc/dashboard',
    'EventCoordinator': '/coordinator/scanner',
    'Judge':            '/judge/dashboard',
}


def _redirect_by_role(role: str):
    return redirect(ROLE_REDIRECTS.get(role, '/'))


# =========================================================
# 1. LOGIN
# =========================================================
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, go home
    if 'user_id' in session:
        return _redirect_by_role(session.get('role', ''))

    if request.method == 'POST':
        role       = request.form.get('role', '').strip()
        email      = request.form.get('email', '').lower().strip()
        password   = request.form.get('password', '')
        secret_key = request.form.get('secret_key', '').strip()

        # Normalise legacy DB value
        if role == 'Super Admin':
            role = 'SuperAdmin'

        # Master key check for SuperAdmin
        # In development mode the key is optional so local demos aren't blocked.
        MASTER_KEY = current_app.config.get('MASTER_SECRET_KEY', '')
        is_production = current_app.config.get('FLASK_ENV') == 'production'
        if role == 'SuperAdmin' and is_production and secret_key != MASTER_KEY:
            flash('🔒 Invalid Master Security Key. Access denied.', 'danger')
            log_action(db, "LOGIN_FAILED", f"Bad master key attempt for {email}")
            return redirect('/login')

        if not email or not password:
            flash('Please enter both email and password.', 'warning')
            return redirect('/login')

        try:
            user_doc = db.collection('users').document(email).get()

            if not user_doc.exists:
                # Auto-create SuperAdmin on very first boot
                SUPER_EMAIL = current_app.config.get('SUPER_ADMIN_EMAIL', '')
                SUPER_PASS  = current_app.config.get('SUPER_ADMIN_DEFAULT_PASS', '')
                if role == 'SuperAdmin' and email == SUPER_EMAIL and password == SUPER_PASS:
                    db.collection('users').document(email).set({
                        'email':               email,
                        'name':                'System Super Admin',
                        'role':                'SuperAdmin',
                        'category':            'All',
                        'password':            generate_password_hash(password),
                        'created_at':          datetime.datetime.now().strftime("%Y-%m-%d"),
                        'needs_password_reset': False
                    })
                    _set_session(email, 'System Super Admin', 'SuperAdmin', 'All')
                    flash("👑 Super Admin account initialised!", "success")
                    log_action(db, "SUPER_ADMIN_INIT", f"First-boot SuperAdmin created: {email}")
                    return redirect('/admin/dashboard')

                flash('Account not found. Please register or contact admin.', 'warning')
                return redirect('/login')

            user_data = user_doc.to_dict()
            db_role = user_data.get('role', '').strip()
            if db_role == 'Super Admin':
                db_role = 'SuperAdmin'

            # Password verification — hashed only. Legacy plaintext rows are
            # rejected and flagged for admin-triggered password reset.
            stored_pw = user_data.get('password', '')
            if isinstance(stored_pw, (int, float)):
                stored_pw = str(int(stored_pw))

            if stored_pw.startswith(('scrypt:', 'pbkdf2:', 'argon2:')):
                valid = check_password_hash(stored_pw, password)
            else:
                valid = False
                logger.warning(
                    "Login blocked — legacy unhashed password on %s. "
                    "Admin must trigger password reset.", email)
                log_action(db, "LOGIN_BLOCKED_LEGACY_HASH",
                           f"Unhashed password on account {email}")

            if not valid or db_role != role:
                flash('Incorrect password or wrong role selected.', 'danger')
                log_action(db, "LOGIN_FAILED", f"Bad credentials for {email} (role={role})")
                return redirect('/login')

            _set_session(email,
                         user_data.get('name'),
                         role,
                         user_data.get('category', 'General'))

            # Force password reset for auto-generated accounts
            if user_data.get('needs_password_reset'):
                session['force_reset'] = True
                flash("Welcome! You must set a new password before continuing.", "warning")
                return redirect('/reset_password')

            flash(f"Welcome back, {user_data.get('name')}! 👋", "success")
            log_action(db, "LOGIN_SUCCESS", f"{email} logged in as {role}")
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

        if new_pw != confirm_pw:
            flash("Passwords do not match.", "danger")
            return redirect('/reset_password')

        if len(new_pw) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect('/reset_password')

        # Must contain at least one digit
        if not any(c.isdigit() for c in new_pw):
            flash("Password must contain at least one number.", "danger")
            return redirect('/reset_password')

        try:
            email = session['user_id']
            db.collection('users').document(email).update({
                'password':            generate_password_hash(new_pw),
                'needs_password_reset': False
            })
            session.pop('force_reset', None)
            flash("✅ Password updated. Welcome to your dashboard!", "success")
            log_action(db, "PASSWORD_RESET", f"{email} changed forced password")
            return _redirect_by_role(session.get('role', ''))

        except Exception as exc:
            flash(f"Error updating password: {exc}", "danger")

    return render_template('reset_password.html')


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

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'warning')
            return redirect('/register')

        try:
            existing = db.collection('users').document(email).get()
            if existing.exists:
                flash('An account with this email already exists. Please log in.', 'warning')
                return redirect('/login')

            db.collection('users').document(email).set({
                'email':               email,
                'name':                name,
                'usn':                 usn,
                'phone':               phone,
                'role':                'Student',
                'category':            'General',
                'password':            generate_password_hash(password),
                'created_at':          datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'needs_password_reset': False
            })
            _set_session(email, name, 'Student', 'General')
            log_action(db, "USER_REGISTERED", f"New student self-registered: {email}")
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

        # Generic response in all cases — never reveal whether the email exists
        generic_msg = ("If an account exists for that email, a reset link "
                       "has been sent. Check your inbox (and spam folder).")

        try:
            user_doc = db.collection('users').document(email).get()
            if not user_doc.exists:
                flash(generic_msg, "info")
                log_action(db, "RESET_REQ_NOACCT", f"Reset requested for unknown {email}")
                return redirect('/forgot_password')

            user_data = user_doc.to_dict()
            role      = (user_data.get('role', '') or '').strip()
            if role == 'Super Admin':
                role = 'SuperAdmin'

            # SuperAdmin cannot reset via email — use master key recovery path
            if role == 'SuperAdmin':
                flash(generic_msg, "info")
                log_action(db, "RESET_REQ_BLOCKED_SUPER",
                           f"SuperAdmin {email} attempted email-based reset")
                return redirect('/forgot_password')

            token = _reset_serializer().dumps(email)
            base  = request.host_url.rstrip('/')
            reset_url = f"{base}/reset_token/{token}"

            sent = send_password_reset_email(email,
                                             user_data.get('name', ''),
                                             reset_url)
            if sent:
                log_action(db, "RESET_LINK_SENT",
                           f"Reset link emailed to {email} (role={role})")
            else:
                log_action(db, "RESET_LINK_FAIL",
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
    try:
        email = _reset_serializer().loads(token, max_age=RESET_TOKEN_MAX_AGE)
    except SignatureExpired:
        flash("This reset link has expired. Please request a new one.", "danger")
        return redirect('/forgot_password')
    except BadSignature:
        flash("Invalid reset link.", "danger")
        return redirect('/forgot_password')

    user_doc = db.collection('users').document(email).get()
    if not user_doc.exists:
        flash("Account no longer exists.", "danger")
        return redirect('/login')

    user_data = user_doc.to_dict()
    role      = (user_data.get('role', '') or '').strip()
    if role == 'Super Admin':
        role = 'SuperAdmin'
    if role == 'SuperAdmin':
        flash("SuperAdmin cannot be reset via email.", "danger")
        return redirect('/login')

    if request.method == 'POST':
        new_pw     = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if new_pw != confirm_pw:
            flash("Passwords do not match.", "danger")
            return redirect(request.path)
        if len(new_pw) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(request.path)
        if not any(c.isdigit() for c in new_pw):
            flash("Password must contain at least one number.", "danger")
            return redirect(request.path)

        try:
            db.collection('users').document(email).update({
                'password':             generate_password_hash(new_pw),
                'needs_password_reset': False
            })
            log_action(db, "PASSWORD_RESET_EMAIL",
                       f"{email} reset password via email token")
            flash("✅ Password updated. You can now log in.", "success")
            return redirect('/login')
        except Exception as exc:
            current_app.logger.error("Reset-token update error: %s", exc)
            flash("Could not update password. Try again.", "danger")
            return redirect(request.path)

    return render_template('reset_password_token.html',
                           email=email, name=user_data.get('name', ''))


# =========================================================
# 6. LOGOUT
# =========================================================
@auth_bp.route('/logout')
def logout():
    user = session.get('user_id', 'unknown')
    log_action(db, "LOGOUT", f"{user} logged out")
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

    to = (request.args.get('to') or session.get('user_id') or '').strip()
    if not to:
        return {"error": "pass ?to=email@address"}, 400

    provider = "Resend" if _os.environ.get('RESEND_API_KEY') else "Gmail SMTP"
    from_addr = _os.environ.get(
        'MAIL_FROM',
        f"SapthaEvent <{_os.environ.get('MAIL_USER', '(unset)')}>"
    )

    utils_email.LAST_EMAIL_ERROR = ""
    ok = utils_email._send(
        to, "SapthaEvent — Email Diagnostic",
        "<p>If you can read this, email delivery is working.</p>"
    )
    return {
        "provider":         provider,
        "from":             from_addr,
        "to":               to,
        "sent":             ok,
        "error":            utils_email.LAST_EMAIL_ERROR or None,
        "resend_key_set":   bool(_os.environ.get('RESEND_API_KEY')),
        "mail_user_set":    bool(_os.environ.get('MAIL_USER')),
        "mail_pass_set":    bool(_os.environ.get('MAIL_PASS')),
        "hint": (
            "Resend free plan: MAIL_FROM must be 'onboarding@resend.dev' "
            "OR a verified domain, AND you can only send to the email that "
            "owns the Resend account until you verify a domain."
            if provider == "Resend" else
            "Gmail: MAIL_PASS must be a 16-char App Password (no spaces), "
            "generated at myaccount.google.com/apppasswords."
        ),
    }


# =========================================================
# INTERNAL HELPER
# =========================================================
def _set_session(email: str, name: str, role: str, category: str):
    session.permanent = True
    session['user_id']  = email
    session['name']     = name
    session['role']     = role
    session['category'] = category
   