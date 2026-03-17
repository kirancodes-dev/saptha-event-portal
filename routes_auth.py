import datetime
from flask import Blueprint, render_template, request, redirect, session, flash, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from models import db
from utils import log_action

auth_bp = Blueprint('auth', __name__)

# Role → dashboard URL map (single source of truth)
ROLE_REDIRECTS = {
    'Student':          '/participant/dashboard',
    'SuperAdmin':       '/admin/dashboard',
    'Super Admin':      '/admin/dashboard',
    'Admin':            '/admin/dashboard',
    'Coordinator':      '/coordinator/dashboard',
    'ClubSPOC':         '/coordinator/dashboard',
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
        MASTER_KEY = current_app.config.get('MASTER_SECRET_KEY', '')
        if role == 'SuperAdmin' and secret_key != MASTER_KEY:
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

            # Password verification — handles hashed and legacy plain-text
            stored_pw = user_data.get('password', '')
            if isinstance(stored_pw, (int, float)):
                stored_pw = str(int(stored_pw))

            if stored_pw.startswith(('scrypt:', 'pbkdf2:')):
                valid = check_password_hash(stored_pw, password)
            else:
                # Legacy plain-text fallback — migrate on successful login
                valid = (stored_pw == str(password))
                if valid:
                    db.collection('users').document(email).update({
                        'password': generate_password_hash(password)
                    })

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
# 3. LOGOUT
# =========================================================
@auth_bp.route('/logout')
def logout():
    user = session.get('user_id', 'unknown')
    log_action(db, "LOGOUT", f"{user} logged out")
    session.clear()
    flash("You have been logged out.", "info")
    return redirect('/')


# =========================================================
# INTERNAL HELPER
# =========================================================
def _set_session(email: str, name: str, role: str, category: str):
    session.permanent = True
    session['user_id']  = email
    session['name']     = name
    session['role']     = role
    session['category'] = category