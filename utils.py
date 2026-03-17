from functools import wraps
from flask import session, redirect, flash, request
import datetime


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

    Usage:
        @role_required('Admin')
        @role_required(['Admin', 'SuperAdmin'])

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

    Call this any time a privileged action happens:
        log_action(db, "SCORE_SUBMITTED", f"Judge {email} scored team {reg_id}")
        log_action(db, "EVENT_DELETED",   f"Event {event_id} deleted by {email}")
    """
    try:
        db.collection('audit_log').add({
            'action':    action,
            'details':   details,
            'user':      session.get('user_id', 'anonymous'),
            'role':      session.get('role', 'unknown'),
            'ip':        request.remote_addr,
            'timestamp': datetime.datetime.utcnow()
        })
    except Exception as exc:
        # Never let logging crash the application
        print(f"[AUDIT LOG ERROR] {exc}")


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