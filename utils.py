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


ROLE_ALIASES = {
    'SuperAdmin': ['SuperAdmin', 'Super Admin', 'UniversityAdmin', 'Admin'],
    'Super Admin': ['SuperAdmin', 'Super Admin', 'UniversityAdmin', 'Admin'],
    'UniversityAdmin': ['SuperAdmin', 'Super Admin', 'UniversityAdmin', 'Admin'],
    'Admin': ['SuperAdmin', 'Super Admin', 'UniversityAdmin', 'Admin'],
    'ClubSPOC': ['ClubSPOC', 'UnitAdmin', 'EventOrganizer', 'SPOC'],
    'UnitAdmin': ['ClubSPOC', 'UnitAdmin', 'EventOrganizer', 'SPOC'],
    'EventOrganizer': ['ClubSPOC', 'UnitAdmin', 'EventOrganizer'],
    'Coordinator': ['Coordinator', 'EventCoordinator'],
    'EventCoordinator': ['Coordinator', 'EventCoordinator'],
    'Student': ['Student', 'Participant'],
    'Participant': ['Student', 'Participant'],
}


def role_required(roles):
    """
    Restrict a route to one or more roles.
    Works as a compatibility shim bridging legacy roles and new scoped roles.

    Pass a single role string or a list of role strings.
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
            # Normalise "Super Admin" -> "SuperAdmin"
            if user_role == 'Super Admin':
                user_role = 'SuperAdmin'

            # UniversityAdmin and SuperAdmin are wildcards: always permitted on any @role_required route.
            if user_role in ('SuperAdmin', 'UniversityAdmin'):
                return f(*args, **kwargs)

            raw_roles = [roles] if isinstance(roles, str) else list(roles)
            valid_roles = set()
            for r in raw_roles:
                valid_roles.add(r)
                for alias in ROLE_ALIASES.get(r, []):
                    valid_roles.add(alias)

            # Check if user's role or any of its aliases match
            user_roles_to_test = {user_role} | set(ROLE_ALIASES.get(user_role, []))
            if not user_roles_to_test.intersection(valid_roles):
                flash(
                    f"🛑 Access denied. You are logged in as '{session.get('role')}', "
                    f"but this page requires {list(valid_roles)}.",
                    "danger"
                )
                return redirect('/login')
            return f(*args, **kwargs)
        return decorated
    return decorator


# =========================================================
# AUDIT LOGGING
# =========================================================

def log_action(*args, **kwargs):
    """
    Write an immutable audit entry.
    Supports both styles:
      log_action(action, details)
      log_action(db, action, details)
    """
    from models import db as default_db
    from flask import has_request_context

    if len(args) == 3:
        db_client, action, details = args
    elif len(args) == 2:
        if isinstance(args[0], str):
            db_client = default_db
            action = args[0]
            details = args[1]
        else:
            db_client = args[0]
            action = args[1]
            details = ""
    elif len(args) == 1:
        db_client = default_db
        action = args[0]
        details = ""
    else:
        db_client = kwargs.get('db', default_db)
        action = kwargs.get('action', '')
        details = kwargs.get('details', '')

    try:
        if db_client is not None:
            ip_addr = '127.0.0.1'
            user, role = 'system', 'system'     # a background task or job (UPG-140)
            if has_request_context():
                try:
                    ip_addr = request.remote_addr
                except Exception:
                    pass
                user, role = session.get('user_id', 'anonymous'), session.get('role', 'unknown')

            db_client.collection('audit_log').add({
                'action':    action,
                'details':   details,
                'user':      user,
                'role':      role,
                'ip':        ip_addr,
                'timestamp': datetime.datetime.now(datetime.timezone.utc)
            })
    except Exception as exc:
        logger.warning("[AUDIT LOG ERROR] %s", exc)


# =========================================================
# HELPER UTILITIES
# =========================================================

def generate_reg_id(prefix: str = 'REG') -> str:
    """A registration (or waitlist) ID that can't collide: the prefix and 20
    hex characters of a random UUID. The old millisecond IDs repeated when two
    people registered in the same millisecond (UPG-95)."""
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:20].upper()}"


class RegistrationExists(Exception):
    """A new registration's ID is already taken; nothing was written (UPG-95)."""


class AlreadyRegistered(Exception):
    """This person already holds an active registration for the event: the
    database refused a second (UPG-115). Nothing was written."""


def is_active_duplicate(exc) -> bool:
    """Whether a database error is the one-active-registration index refusing."""
    from models_pg import ACTIVE_LEAD_INDEX
    text = str(getattr(exc, 'orig', exc))
    return ACTIVE_LEAD_INDEX in text or ('UNIQUE constraint failed' in text and 'registrations' in text
                                         and 'registrations.id' not in text)


def create_registration(db, reg_id: str, data: dict, collection: str = 'registrations') -> None:
    """Write a new registration (or waitlist entry) under reg_id, never over an
    existing one: the database layer's set() merges into whatever is there (UPG-95).
    Raises AlreadyRegistered when the person already holds an active
    registration for the event (the database's unique index, UPG-115)."""
    ref = db.collection(collection).document(reg_id)
    if ref.get().exists:
        raise RegistrationExists(reg_id)
    try:
        ref.set(data)
    except Exception as exc:
        if collection == 'registrations' and is_active_duplicate(exc):
            raise AlreadyRegistered(data.get('lead_email', '')) from exc
        raise


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
    'Participant':      '/participant/dashboard',
    'SuperAdmin':       '/admin/dashboard',
    'Super Admin':      '/admin/dashboard',
    'Admin':            '/admin/dashboard',
    'UniversityAdmin':  '/admin/dashboard',
    'Coordinator':      '/coordinator/dashboard',
    'EventCoordinator': '/coordinator/scanner',
    'ClubSPOC':         '/spoc/dashboard',
    'UnitAdmin':        '/spoc/dashboard',
    'EventOrganizer':   '/spoc/dashboard',
    'Judge':            '/judge/dashboard',
    'IQACCoordinator':  '/naac/',
    'DepartmentAdmin':  '/naac/',
    'Volunteer':        '/coordinator/scanner',
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


# =========================================================
# FORM SUBMISSION RECORD  (for /forms/responses analytics)
# =========================================================
def record_form_submission(db, event_id, reg_id, email, name, answers):
    """Store the raw form answers for a registration.

    Must run after the registration is saved: form_submissions references
    registrations with a foreign key.
    """
    import datetime as _dt
    db.collection('form_submissions').add({
        'event_id':     event_id,
        'reg_id':       reg_id,
        'email':        email,
        'name':         name,
        'answers':      answers,
        'submitted_at': _dt.datetime.now(_dt.timezone.utc).isoformat(),
    })


TO_BE_ANNOUNCED = 'Venue to be announced'


def venue_label(event) -> str:
    """Where an event is, for any page or email: its room or venue; "Online" for an
    online event with neither; else "Venue to be announced". Never an invented
    place such as "SNPSU Campus" (UPG-111)."""
    event = event or {}
    get = event.get if hasattr(event, 'get') else (lambda k, d=None: getattr(event, k, d))
    place = str(get('room_name') or get('venue') or '').strip()
    if place:
        return place
    if str(get('event_mode') or get('mode') or '').strip().lower() == 'online':
        return 'Online'
    return TO_BE_ANNOUNCED
