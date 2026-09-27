"""
services_permission.py — Unified Scoped RBAC & Permission Enforcement Engine
=============================================================================

Roles:
  - UniversityAdmin: Global campus oversight, all permissions across all units & events.
  - UnitAdmin: Scoped to a specific OrgUnit (department/club). Full lifecycle within that unit.
  - EventOrganizer: Scoped to unit or specific event.
  - EventCoordinator: Scoped to assigned event(s). Check-in, registrations, exports.
  - Judge: Scoped to assigned event(s). Scoring.
  - Volunteer: Scoped to assigned event(s). Check-in.
  - Participant: Student / attendee.

Permissions:
  - create_event
  - edit_event
  - publish_event
  - approve_event
  - manage_registrations
  - check_in
  - score
  - publish_results
  - issue_certificates
  - view_analytics
  - export_data
"""

import uuid
import datetime
import logging
import re
from functools import wraps
from flask import session, request, redirect, flash, abort, jsonify, current_app

logger = logging.getLogger(__name__)

# ── 1. Roles & Permissions Definitions ───────────────────────────────────────

PERMISSIONS = {
    'create_event',
    'edit_event',
    'publish_event',
    'approve_event',
    'manage_registrations',
    'check_in',
    'score',
    'publish_results',
    'issue_certificates',
    'view_analytics',
    'export_data',
}

ROLE_PERMISSIONS = {
    'UniversityAdmin': {
        'create_event', 'edit_event', 'publish_event', 'approve_event',
        'manage_registrations', 'check_in', 'score', 'publish_results',
        'issue_certificates', 'view_analytics', 'export_data',
    },
    'UnitAdmin': {
        'create_event', 'edit_event', 'publish_event',
        'manage_registrations', 'check_in', 'score', 'publish_results',
        'issue_certificates', 'view_analytics', 'export_data',
        # NOTE: approve_event is restricted by default to UniversityAdmin
    },
    'EventOrganizer': {
        'create_event', 'edit_event', 'publish_event',
        'manage_registrations', 'check_in', 'publish_results',
        'issue_certificates', 'view_analytics', 'export_data',
    },
    'EventCoordinator': {
        'manage_registrations', 'check_in', 'export_data', 'view_analytics',
    },
    'Judge': {
        'score',
    },
    'Volunteer': {
        'check_in',
    },
    'Participant': set(),
}

ROLE_MAP = {
    'superadmin': 'UniversityAdmin',
    'super admin': 'UniversityAdmin',
    'admin': 'UniversityAdmin',
    'universityadmin': 'UniversityAdmin',
    'clubspoc': 'UnitAdmin',
    'spoc': 'UnitAdmin',
    'unitadmin': 'UnitAdmin',
    'eventorganizer': 'EventOrganizer',
    'organizer': 'EventOrganizer',
    'coordinator': 'EventCoordinator',
    'eventcoordinator': 'EventCoordinator',
    'judge': 'Judge',
    'volunteer': 'Volunteer',
    'student': 'Participant',
    'participant': 'Participant',
}


def _get_db(db_override=None):
    if db_override is not None:
        return db_override
    try:
        import app as app_module
        if hasattr(app_module, 'db') and app_module.db is not None:
            return app_module.db
    except Exception:
        pass
    try:
        from models import db as default_db
        return default_db
    except Exception:
        return None


# ── 2. Core Permission Check: can() ──────────────────────────────────────────

def can(user, permission: str, target=None, db=None) -> bool:
    """
    One permission check for all authorization decisions.

    can(user, permission, target) -> bool

    :param user: session dict, user dict, or user email string
    :param permission: one of PERMISSIONS
    :param target: None, event_id (str), event (dict/model), unit_id (str), or unit (dict)
    :param db: database client (optional)
    """
    if permission not in PERMISSIONS:
        logger.warning("Checking unregistered permission: %s", permission)

    # 1. Normalize user identity and role
    user_id = ""
    user_role = ""
    user_cat = "General"
    user_unit = None

    if isinstance(user, str):
        user_id = user.lower().strip()
    elif isinstance(user, dict) or hasattr(user, 'get'):
        user_id = str(user.get('user_id') or user.get('email') or '').lower().strip()
        user_role = str(user.get('role') or '').strip()
        user_cat = str(user.get('category') or 'General').strip()
        user_unit = user.get('org_unit_id') or user.get('unit_id')
    elif hasattr(user, 'email'):
        user_id = str(getattr(user, 'email', '')).lower().strip()
        user_role = str(getattr(user, 'role', '')).strip()

    if not user_id:
        return False

    norm_session_role = ROLE_MAP.get(user_role.lower(), user_role)

    # UniversityAdmin session role is always global wildcard
    if norm_session_role == 'UniversityAdmin' or user_role in ('SuperAdmin', 'Super Admin'):
        return True

    db_client = _get_db(db)

    # 2. Resolve target into event_id, event_data, org_unit_id
    target_event_id = None
    target_event_data = None
    target_unit_id = None

    if target is not None:
        if isinstance(target, str):
            # Check if target is an event_id in events collection
            target_str = target.strip()
            if db_client:
                try:
                    edoc = db_client.collection('events').document(target_str).get()
                    if edoc.exists:
                        target_event_id = edoc.id
                        target_event_data = edoc.to_dict() or {}
                        target_event_data['id'] = edoc.id
                        target_unit_id = target_event_data.get('org_unit_id') or target_event_data.get('orgUnitId')
                    else:
                        # Could be an org_unit_id
                        target_unit_id = target_str
                except Exception:
                    target_unit_id = target_str
            else:
                target_unit_id = target_str
        elif isinstance(target, dict) or hasattr(target, 'get'):
            target_event_id = target.get('id') or target.get('event_id')
            target_event_data = dict(target)
            target_unit_id = target.get('org_unit_id') or target.get('orgUnitId') or target.get('unit_id')

    # 3. Check explicit RoleAssignment table
    if db_client:
        try:
            ra_ref = db_client.collection('role_assignments')
            assignments = []
            try:
                for doc in ra_ref.where('user_id', '==', user_id).stream():
                    assignments.append(doc.to_dict() or {})
            except Exception:
                pass

            for ra in assignments:
                ra_role = ra.get('role', '')
                norm_ra_role = ROLE_MAP.get(ra_role.lower(), ra_role)
                scope_type = (ra.get('scope_type') or ra.get('scopeType') or 'university').lower().strip()
                scope_id = str(ra.get('scope_id') or ra.get('scopeId') or '').strip()

                # UniversityAdmin with university scope
                if norm_ra_role == 'UniversityAdmin' and scope_type in ('university', 'all'):
                    return True

                # University-scoped permissions
                if scope_type in ('university', 'all'):
                    allowed_perms = ROLE_PERMISSIONS.get(norm_ra_role, set())
                    if permission in allowed_perms:
                        if permission == 'approve_event' and norm_ra_role != 'UniversityAdmin':
                            continue
                        return True

                # Unit-scoped permissions
                elif scope_type == 'unit':
                    allowed_perms = ROLE_PERMISSIONS.get(norm_ra_role, set())
                    if permission in allowed_perms:
                        if permission == 'approve_event' and norm_ra_role != 'UniversityAdmin':
                            continue
                        # If target has a unit, it must match
                        if target_unit_id:
                            if scope_id.lower() == str(target_unit_id).lower():
                                return True
                        elif not target_event_id and not target_unit_id:
                            # Global unit actions (e.g. create_event inside own unit)
                            return True

                # Event-scoped permissions
                elif scope_type == 'event':
                    allowed_perms = ROLE_PERMISSIONS.get(norm_ra_role, set())
                    if permission in allowed_perms:
                        if target_event_id and scope_id == str(target_event_id):
                            return True

            if assignments:
                # If explicit role assignments exist for this user, do not let them cross unit boundaries!
                # If target has unit_id and user is a UnitAdmin of another unit, explicitly deny.
                user_unit_scopes = [
                    str(ra.get('scope_id') or '').lower()
                    for ra in assignments
                    if (ra.get('scope_type') or '').lower() == 'unit'
                ]
                if user_unit_scopes and target_unit_id:
                    if str(target_unit_id).lower() not in user_unit_scopes:
                        return False
        except Exception as e:
            logger.debug("Role assignment check note: %s", e)

    # 4. Fallback for legacy session roles and existing test fixtures
    if norm_session_role in ('UnitAdmin', 'ClubSPOC'):
        allowed_perms = ROLE_PERMISSIONS['UnitAdmin']
        if permission not in allowed_perms:
            return False
        if permission == 'approve_event':
            return False

        # Unit boundary check
        if target_unit_id:
            # If session has a unit or department specified
            if user_unit and str(user_unit).lower() != str(target_unit_id).lower():
                return False

        if target_event_data:
            # If target event specifies an org_unit_id and user specifies a department/unit
            ev_unit = target_event_data.get('org_unit_id') or target_event_data.get('orgUnitId')
            if ev_unit and user_unit and str(ev_unit).lower() != str(user_unit).lower():
                return False

            # Check SPOC ownership / category match
            is_owner = (
                target_event_data.get('created_by_email') == user_id or
                target_event_data.get('spoc_id') == user_id or
                target_event_data.get('spoc_email') == user_id or
                target_event_data.get('created_by') == user_id or
                (user_cat and user_cat != 'All' and target_event_data.get('category') == user_cat) or
                user_cat == 'All'
            )
            return is_owner
        return True

    elif norm_session_role in ('EventCoordinator', 'Coordinator'):
        allowed_perms = ROLE_PERMISSIONS['EventCoordinator']
        if permission not in allowed_perms:
            return False
        if target_event_data:
            assigned = (
                user_id in target_event_data.get('coordinators', []) or
                any(s.get('email') == user_id for s in target_event_data.get('staff', [])) or
                target_event_data.get('created_by_email') == user_id or
                target_event_data.get('created_by') == user_id or
                user_cat == 'All'
            )
            return assigned
        return True

    elif norm_session_role == 'Judge':
        if permission != 'score':
            return False
        if target_event_data:
            assigned = any(
                s.get('email') == user_id and s.get('role') == 'Judge'
                for s in target_event_data.get('staff', [])
            )
            return assigned
        return True

    elif norm_session_role == 'Volunteer':
        return permission == 'check_in'

    return False


# ── 3. Permission Decorator ──────────────────────────────────────────────────

def permission_required(permission: str, event_arg: str = 'event_id'):
    """
    Route decorator: restricts access based on can(session, permission, target).
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                flash('🔒 Please log in to continue.', 'danger')
                return redirect('/login')

            target_id = kwargs.get(event_arg) or request.args.get(event_arg) or request.form.get(event_arg)
            if not can(session, permission, target_id):
                flash(f"🛑 Access denied: You do not have '{permission}' permission for this resource.", "danger")
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'error': 'Forbidden', 'message': f"Permission '{permission}' denied"}), 403
                abort(403)

            return f(*args, **kwargs)
        return decorated
    return decorator


# ── 4. Migration Helper: migrate_roles_and_units() ───────────────────────────

def migrate_roles_and_units(db=None) -> dict:
    """
    Migrates legacy roles, backfills events to 'central', and sets up initial OrgUnits.

    - Seeds central, department, and club OrgUnits under organization 'default'.
    - Backfills existing events without an org_unit_id to 'central'.
    - 'SuperAdmin' & 'Super Admin' -> UniversityAdmin (university scope).
    - 'ClubSPOC' -> UnitAdmin of their matching department/club unit.
    - 'Coordinator' / 'EventCoordinator', 'Judge' -> event-scoped role assignments.
    - Returns summary dict with any unmapped users listed.
    """
    db_client = _get_db(db)
    if not db_client:
        return {"error": "No database connection available"}

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 1. Seed standard OrgUnits
    default_units = [
        {"id": "central", "type": "central", "name": "Central Administration", "slug": "central", "parent_id": None},
        {"id": "cse", "type": "department", "name": "Computer Science & Engineering", "slug": "cse", "parent_id": "central"},
        {"id": "ece", "type": "department", "name": "Electronics & Communication Engineering", "slug": "ece", "parent_id": "central"},
        {"id": "cultural-club", "type": "club", "name": "Cultural Club", "slug": "cultural-club", "parent_id": "central"},
        {"id": "sports-club", "type": "club", "name": "Sports Club", "slug": "sports-club", "parent_id": "central"},
        {"id": "management-club", "type": "club", "name": "Management Club", "slug": "management-club", "parent_id": "central"},
    ]

    for unit in default_units:
        uref = db_client.collection('org_units').document(unit['id'])
        if not uref.get().exists:
            uref.set({
                'id': unit['id'],
                'organization_id': 'default',
                'parent_id': unit['parent_id'],
                'type': unit['type'],
                'name': unit['name'],
                'slug': unit['slug'],
                'created_at': now_iso,
                'updated_at': now_iso,
            })

    # 2. Backfill existing events
    backfilled_events = []
    events_docs = list(db_client.collection('events').stream())
    events_map = {}
    for edoc in events_docs:
        edata = edoc.to_dict() or {}
        events_map[edoc.id] = edata
        if not edata.get('org_unit_id') and not edata.get('orgUnitId'):
            db_client.collection('events').document(edoc.id).update({
                'organization_id': edata.get('organization_id') or 'default',
                'org_unit_id': 'central',
            })
            backfilled_events.append(edoc.id)

    # 3. Migrate Users & Scoped Roles
    migrated_admins = []
    migrated_spocs = []
    migrated_coords = []
    migrated_judges = []
    unmapped_users = []

    try:
        users_stream = list(db_client.collection('users').stream())
    except Exception:
        users_stream = []

    for udoc in users_stream:
        udata = udoc.to_dict() or {}
        email = (udata.get('email') or udoc.id).lower().strip()
        role = udata.get('role', '')
        if hasattr(role, 'value'):
            role = role.value
        role = str(role).strip()

        # Normalise 'Super Admin' / 'SuperAdmin' -> UniversityAdmin
        if role in ('SuperAdmin', 'Super Admin', 'Admin'):
            db_client.collection('users').document(udoc.id).update({'role': 'UniversityAdmin'})
            ra_id = f"ra_{email}_univ"
            db_client.collection('role_assignments').document(ra_id).set({
                'id': ra_id,
                'user_id': email,
                'role': 'UniversityAdmin',
                'scope_type': 'university',
                'scope_id': 'default',
                'created_at': now_iso,
            })
            migrated_admins.append(email)

        # Map ClubSPOC -> UnitAdmin of their unit
        elif role in ('ClubSPOC', 'SPOC'):
            dept = str(udata.get('department') or '').lower()
            cat = str(udata.get('category') or '').lower()
            club = str(udata.get('club') or udata.get('club_name') or '').lower()
            combined = f"{dept} {cat} {club} {email}".lower()

            target_unit = None
            if re.search(r'\b(ec|ece)\b', combined) or 'electronics' in combined:
                target_unit = 'ece'
            elif re.search(r'\b(cs|cse|comp|computer|tech|ai|coding)\b', combined) or 'computer science' in combined:
                target_unit = 'cse'
            elif re.search(r'\b(cultural|art|dance|drama|theatre|music)\b', combined):
                target_unit = 'cultural-club'
            elif re.search(r'\b(sport|sports|cricket|athletic|football)\b', combined):
                target_unit = 'sports-club'
            elif re.search(r'\b(manage|management|b-plan|business|mba)\b', combined):
                target_unit = 'management-club'

            if target_unit:
                db_client.collection('users').document(udoc.id).update({'role': 'UnitAdmin', 'department': target_unit})
                ra_id = f"ra_{email}_{target_unit}"
                db_client.collection('role_assignments').document(ra_id).set({
                    'id': ra_id,
                    'user_id': email,
                    'role': 'UnitAdmin',
                    'scope_type': 'unit',
                    'scope_id': target_unit,
                    'created_at': now_iso,
                })
                migrated_spocs.append({'email': email, 'unit': target_unit})
            else:
                unmapped_users.append({'email': email, 'role': role, 'data': udata})

        # EventCoordinator -> event-scoped roles
        elif role in ('Coordinator', 'EventCoordinator'):
            assigned_events = []
            for eid, edata in events_map.items():
                staff = edata.get('staff', [])
                coords = edata.get('coordinators', [])
                if email in coords or any(s.get('email') == email for s in staff):
                    assigned_events.append(eid)
                    ra_id = f"ra_{email}_{eid}"
                    db_client.collection('role_assignments').document(ra_id).set({
                        'id': ra_id,
                        'user_id': email,
                        'role': 'EventCoordinator',
                        'scope_type': 'event',
                        'scope_id': str(eid),
                        'created_at': now_iso,
                    })
            db_client.collection('users').document(udoc.id).update({'role': 'EventCoordinator'})
            migrated_coords.append({'email': email, 'events': assigned_events})

        # Judge -> event-scoped roles
        elif role == 'Judge':
            assigned_events = []
            for eid, edata in events_map.items():
                staff = edata.get('staff', [])
                if any(s.get('email') == email and s.get('role') == 'Judge' for s in staff):
                    assigned_events.append(eid)
                    ra_id = f"ra_{email}_{eid}"
                    db_client.collection('role_assignments').document(ra_id).set({
                        'id': ra_id,
                        'user_id': email,
                        'role': 'Judge',
                        'scope_type': 'event',
                        'scope_id': str(eid),
                        'created_at': now_iso,
                    })
            db_client.collection('users').document(udoc.id).update({'role': 'Judge'})
            migrated_judges.append({'email': email, 'events': assigned_events})

        elif role in ('Student', 'Participant'):
            db_client.collection('users').document(udoc.id).update({'role': 'Participant'})

    return {
        "migrated_admins": migrated_admins,
        "migrated_spocs": migrated_spocs,
        "migrated_coords": migrated_coords,
        "migrated_judges": migrated_judges,
        "backfilled_events": backfilled_events,
        "unmapped_users": unmapped_users,
    }
