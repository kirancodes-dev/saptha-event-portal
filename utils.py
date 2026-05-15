from functools import wraps
from flask import session, redirect, flash, request
import datetime
import logging

logger = logging.getLogger(__name__)


# =========================================================
# AUTH DECORATORS
# =========================================================

def login_required(f):
    """Redirect to login if no active session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('🔒 Session expired. Please log in again.', 'danger')
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


def role_required(roles):
    """
    Restrict a route to one or more roles.

    Pass a single role string or a list of role strings.
    Common mistake guard: if someone writes @role_required without ()
    Flask passes the view function as `roles` — we catch that and
    raise a clear error instead of a cryptic AttributeError.
    """
    if callable(roles):
        raise SyntaxError(
            f"\n\n🚨 DECORATOR TYPO DETECTED!\n"
            f"You wrote '@role_required' without brackets above '{roles.__name__}'.\n"
            f"Fix it to: @role_required(['RoleName'])\n"
        )

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_role = session.get('role', '')
            # Normalise "Super Admin" (old DB entries) -> "SuperAdmin"
            if user_role == 'Super Admin':
                user_role = 'SuperAdmin'

            valid_roles = [roles] if isinstance(roles, str) else list(roles)
            # Also accept the legacy spaced variant
            legacy = [r.replace('SuperAdmin', 'Super Admin') for r in valid_roles]
            valid_roles = valid_roles + legacy

            # SuperAdmin is a wildcard: always permitted on any @role_required route.
            if user_role == 'SuperAdmin':
                return f(*args, **kwargs)

            if user_role not in valid_roles:
                flash(
                    f"🛑 Access denied. You are logged in as '{session.get('role')}', "
                    f"but this page requires {list(set(valid_roles))}.",
                    "danger"
                )
                return redirect('/login')
            return f(*args, **kwargs)
        return decorated
    return decorator


# =========================================================
# AUDIT LOGGING
# =========================================================

def log_action(db, action: str, details: str = ""):
    """
    Write an immutable audit entry to Firestore.

    Call this any time a privileged action happens, passing the db client,
    an action string (e.g. SCORE_SUBMITTED, EVENT_DELETED), and a details string.
    """
    try:
        db.collection('audit_log').add({
            'action':    action,
            'details':   details,
            'user':      session.get('user_id', 'anonymous'),
            'role':      session.get('role', 'unknown'),
            'ip':        request.remote_addr,
            'timestamp': datetime.datetime.now(datetime.timezone.utc)
        })
    except Exception as exc:
        # Never let logging crash the application
        logger.warning("[AUDIT LOG ERROR] %s", exc)


# =========================================================
# HELPER UTILITIES
# =========================================================

def generate_reg_id() -> str:
    """Unique, timestamp-based registration ID."""
    import time
    return f"REG-{int(time.time() * 1000)}"


def safe_int(value, default: int = 0) -> int:
    """Convert a value to int without raising."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def paginate_list(items: list, page: int, per_page: int = 20) -> dict:
    """Simple in-memory pagination helper."""
    total   = len(items)
    start   = (page - 1) * per_page
    end     = start + per_page
    return {
        'items':       items[start:end],
        'total':       total,
        'page':        page,
        'per_page':    per_page,
        'total_pages': max(1, -(-total // per_page)),  # ceiling division
        'has_prev':    page > 1,
        'has_next':    end < total,
    }


# =========================================================
# ROLE → DASHBOARD MAP  (single source of truth)
# Import this in routes_auth.py and app.py instead of
# defining the same dict twice.
# =========================================================
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


# =========================================================
# PASSWORD STRENGTH VALIDATOR  (single policy for all flows)
# =========================================================
def validate_password_strength(password: str) -> tuple:
    """
    Returns (is_valid: bool, error_message: str).
    Policy: min 8 chars, at least 1 digit.
    Used in: register, force-reset, token-reset.
    """
    if not password or len(password) < 8:
        return False, 'Password must be at least 8 characters.'
    if not any(c.isdigit() for c in password):
        return False, 'Password must contain at least one number.'
    return True, ''
