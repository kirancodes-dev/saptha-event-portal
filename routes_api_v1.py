"""
routes_api_v1.py — RESTful API v1 for SapthaEvent

Provides a JSON API consumed by mobile apps, third-party integrations,
and the future Next.js frontend.  Authenticated via JWT (see auth_jwt.py).

Blueprint prefix: /api/v1
"""
import os
import logging
import datetime

from flask import Blueprint, request, g
from werkzeug.security import generate_password_hash, check_password_hash
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from auth_jwt import (
    jwt_required, jwt_roles_required,
    create_tokens, refresh_access_token, blacklist_token,
    api_success, api_error, api_paginated,
)
from utils import safe_int

logger = logging.getLogger(__name__)

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


# ---------------------------------------------------------------------------
# Lazy Firestore access (imported at runtime to avoid circular imports)
# ---------------------------------------------------------------------------

def _db():
    from app import db
    return db


# ═══════════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/auth/login", methods=["POST"])
def api_login():
    """Authenticate and receive JWT tokens.

    Body: { "email": "...", "password": "...", "role": "Student" }
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role") or "Student"

    if not email or not password:
        return api_error("missing_fields", "Email and password are required")

    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    user_doc = db.collection("users").document(email).get()
    if not user_doc.exists:
        return api_error("invalid_credentials", "Invalid email or password", status=401)

    user = user_doc.to_dict()

    # Verify password
    stored_hash = user.get("password_hash") or user.get("password", "")
    if not stored_hash or not stored_hash.startswith(("scrypt:", "pbkdf2:")):
        return api_error("account_locked", "Account requires password reset", status=403)

    if not check_password_hash(stored_hash, password):
        return api_error("invalid_credentials", "Invalid email or password", status=401)

    # Verify role
    user_role = user.get("role", "Student")
    if role != user_role and user_role != "SuperAdmin":
        return api_error("role_mismatch", f"Account role is {user_role}, not {role}", status=403)

    tokens = create_tokens(
        user_email=email,
        role=user_role,
        org_id=user.get("org_id", ""),
        extra={"name": user.get("name", "")},
    )

    return api_success({
        "tokens": tokens,
        "user": {
            "email": email,
            "name": user.get("name", ""),
            "role": user_role,
            "phone": user.get("phone", ""),
            "college": user.get("college", ""),
            "department": user.get("department", ""),
            "xp": user.get("xp", 0),
        },
    })


@api_v1_bp.route("/auth/register", methods=["POST"])
def api_register():
    """Register a new student account.

    Body: { "email", "password", "name", "phone", "college", "department" }
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()

    if not email or not password or not name:
        return api_error("missing_fields", "Email, password, and name are required")

    if len(password) < 8:
        return api_error("weak_password", "Password must be at least 8 characters")

    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    # Check existing user
    if db.collection("users").document(email).get().exists:
        return api_error("email_exists", "An account with this email already exists", status=409)

    user_data = {
        "name": name,
        "email": email,
        "phone": data.get("phone", ""),
        "college": data.get("college", ""),
        "department": data.get("department", ""),
        "role": "Student",
        "password_hash": generate_password_hash(password),
        "xp": 0,
        "badges": [],
        "is_active": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db.collection("users").document(email).set(user_data)

    tokens = create_tokens(user_email=email, role="Student", extra={"name": name})

    return api_success({"tokens": tokens, "user": {
        "email": email, "name": name, "role": "Student",
    }}, status=201)


@api_v1_bp.route("/auth/refresh", methods=["POST"])
def api_refresh():
    """Exchange a refresh token for new tokens.

    Body: { "refresh_token": "..." }
    """
    data = request.get_json(silent=True) or {}
    refresh = data.get("refresh_token")
    if not refresh:
        return api_error("missing_token", "Refresh token required")

    tokens = refresh_access_token(refresh)
    if not tokens:
        return api_error("invalid_token", "Refresh token is invalid or expired", status=401)

    return api_success({"tokens": tokens})


@api_v1_bp.route("/auth/logout", methods=["POST"])
@jwt_required
def api_logout():
    """Invalidate the current access token."""
    token = request.headers.get("Authorization", "")[7:]
    blacklist_token(token)
    return api_success({"message": "Logged out successfully"})


# ═══════════════════════════════════════════════════════════════════════════
# EVENTS
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/events", methods=["GET"])
def api_list_events():
    """List events with pagination and filtering.

    Query params: page, per_page, category, status, search
    """
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    page = safe_int(request.args.get("page"), 1)
    per_page = min(safe_int(request.args.get("per_page"), 20), 100)
    category = request.args.get("category")
    status = request.args.get("status", "active")
    search = (request.args.get("search") or "").lower()

    query = db.collection("events")
    if status:
        query = query.where(filter=FieldFilter("status", "==", status))
    if category:
        query = query.where(filter=FieldFilter("category", "==", category))

    all_events = []
    for doc in query.stream():
        ev = doc.to_dict()
        ev["id"] = doc.id
        if search and search not in (ev.get("title", "").lower()):
            continue
        all_events.append(ev)

    # Sort by date descending
    all_events.sort(key=lambda x: x.get("date", ""), reverse=True)
    total = len(all_events)
    start = (page - 1) * per_page
    page_events = all_events[start : start + per_page]

    # Clean output
    clean = []
    for ev in page_events:
        clean.append({
            "id": ev.get("id"),
            "title": ev.get("title", ""),
            "description": ev.get("description", "")[:200],
            "category": ev.get("category", "General"),
            "date": ev.get("date", ""),
            "deadline": ev.get("deadline", ""),
            "venue": ev.get("venue", ""),
            "status": ev.get("status", "active"),
            "fee": ev.get("entry_fee", ev.get("fee", 0)),
            "registration_count": ev.get("registration_count", 0),
            "is_team_event": ev.get("is_team_event", False),
            "poster_url": ev.get("poster_url", ev.get("banner_url", "")),
        })

    return api_paginated(clean, page, per_page, total)


@api_v1_bp.route("/events/<event_id>", methods=["GET"])
def api_get_event(event_id):
    """Get full event details."""
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    doc = db.collection("events").document(event_id).get()
    if not doc.exists:
        return api_error("not_found", "Event not found", status=404)

    ev = doc.to_dict()
    ev["id"] = event_id
    return api_success(ev)


@api_v1_bp.route("/events", methods=["POST"])
@jwt_roles_required(["ClubSPOC", "Admin", "Coordinator"])
def api_create_event():
    """Create a new event.

    Body: { "title", "description", "category", "date", "venue", ... }
    """
    db = _db()
    data = request.get_json(silent=True) or {}

    required = ["title", "category", "date", "venue"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return api_error("missing_fields", f"Required fields: {missing}")

    event_data = {
        "title": data["title"],
        "description": data.get("description", ""),
        "category": data["category"],
        "date": data["date"],
        "deadline": data.get("deadline", data["date"]),
        "venue": data["venue"],
        "status": "active",
        "entry_fee": data.get("fee", 0),
        "fee": data.get("fee", 0),
        "is_team_event": data.get("is_team_event", False),
        "min_team_size": data.get("min_team_size", 1),
        "max_team_size": data.get("max_team_size", 1),
        "registration_count": 0,
        "rules": data.get("rules", ""),
        "prizes": data.get("prizes", ""),
        "poster_url": data.get("poster_url", ""),
        "created_by": g.jwt_user["sub"],
        "org_id": g.jwt_user.get("org_id", ""),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    doc_ref = db.collection("events").add(event_data)
    event_data["id"] = doc_ref[1].id

    return api_success(event_data, status=201)


@api_v1_bp.route("/events/<event_id>", methods=["PUT"])
@jwt_roles_required(["ClubSPOC", "Admin", "Coordinator"])
def api_update_event(event_id):
    """Update an existing event."""
    db = _db()
    data = request.get_json(silent=True) or {}

    doc = db.collection("events").document(event_id).get()
    if not doc.exists:
        return api_error("not_found", "Event not found", status=404)

    allowed_fields = [
        "title", "description", "category", "date", "deadline",
        "venue", "status", "entry_fee", "fee", "rules", "prizes",
        "poster_url", "is_team_event", "min_team_size", "max_team_size",
    ]
    updates = {k: v for k, v in data.items() if k in allowed_fields}
    updates["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    db.collection("events").document(event_id).update(updates)

    return api_success({"id": event_id, **updates})


# ═══════════════════════════════════════════════════════════════════════════
# REGISTRATIONS
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/events/<event_id>/register", methods=["POST"])
@jwt_required
def api_register_event(event_id):
    """Register for an event."""
    db = _db()
    data = request.get_json(silent=True) or {}
    user_email = g.jwt_user["sub"]

    # Check event exists
    ev_doc = db.collection("events").document(event_id).get()
    if not ev_doc.exists:
        return api_error("not_found", "Event not found", status=404)

    ev = ev_doc.to_dict()
    if ev.get("status") != "active":
        return api_error("event_closed", "Event is not accepting registrations")

    # Check duplicate
    existing = (
        db.collection("registrations")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .where(filter=FieldFilter("lead_email", "==", user_email))
        .limit(1)
        .stream()
    )
    if any(True for _ in existing):
        return api_error("already_registered", "You are already registered for this event", status=409)

    reg_data = {
        "event_id": event_id,
        "lead_name": data.get("name", g.jwt_user.get("name", "")),
        "lead_email": user_email,
        "lead_phone": data.get("phone", ""),
        "team_name": data.get("team_name", ""),
        "team_members": data.get("team_members", []),
        "status": "confirmed",
        "payment_status": "unpaid" if ev.get("fee", 0) > 0 else "free",
        "attendance": "Pending",
        "form_data": data.get("form_data", {}),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    doc_ref = db.collection("registrations").add(reg_data)
    reg_data["id"] = doc_ref[1].id

    # Increment registration count
    try:
        from google.cloud.firestore_v1 import Increment
    except Exception:
        google = None
    db.collection("events").document(event_id).update({
        "registration_count": Increment(1),
    })

    return api_success(reg_data, status=201)


@api_v1_bp.route("/registrations", methods=["GET"])
@jwt_required
def api_my_registrations():
    """Get current user's registrations."""
    db = _db()
    user_email = g.jwt_user["sub"]

    regs = []
    for doc in (
        db.collection("registrations")
        .where(filter=FieldFilter("lead_email", "==", user_email))
        .stream()
    ):
        r = doc.to_dict()
        r["id"] = doc.id
        # Attach event title
        ev_doc = db.collection("events").document(r.get("event_id", "")).get()
        if ev_doc.exists:
            ev = ev_doc.to_dict()
            r["event_title"] = ev.get("title", "")
            r["event_date"] = ev.get("date", "")
            r["event_venue"] = ev.get("venue", "")
        regs.append(r)

    return api_success(regs)


# ═══════════════════════════════════════════════════════════════════════════
# USER PROFILE
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/users/me", methods=["GET"])
@jwt_required
def api_get_profile():
    """Get current user's profile."""
    db = _db()
    email = g.jwt_user["sub"]

    doc = db.collection("users").document(email).get()
    if not doc.exists:
        return api_error("not_found", "User not found", status=404)

    user = doc.to_dict()
    # Remove sensitive fields
    user.pop("password_hash", None)
    user.pop("password", None)
    user["email"] = email

    return api_success(user)


@api_v1_bp.route("/users/me", methods=["PUT"])
@jwt_required
def api_update_profile():
    """Update current user's profile."""
    db = _db()
    email = g.jwt_user["sub"]
    data = request.get_json(silent=True) or {}

    allowed = ["name", "phone", "college", "department", "usn"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return api_error("no_changes", "No valid fields to update")

    updates["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.collection("users").document(email).update(updates)

    return api_success(updates)


# ═══════════════════════════════════════════════════════════════════════════
# ACHIEVEMENTS & LEADERBOARD
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/achievements", methods=["GET"])
@jwt_required
def api_achievements():
    """Get current user's XP and badges."""
    db = _db()
    email = g.jwt_user["sub"]

    doc = db.collection("users").document(email).get()
    if not doc.exists:
        return api_error("not_found", "User not found", status=404)

    user = doc.to_dict()
    return api_success({
        "xp": user.get("xp", 0),
        "badges": user.get("badges", []),
        "level": _calc_level(user.get("xp", 0)),
    })


def _calc_level(xp: int) -> dict:
    """Calculate user level from XP."""
    levels = [
        (0, "Freshman", "🌱"), (100, "Explorer", "🔍"),
        (300, "Achiever", "⭐"), (600, "Champion", "🏆"),
        (1000, "Legend", "👑"), (2000, "Grandmaster", "💎"),
    ]
    current = levels[0]
    for threshold, name, emoji in levels:
        if xp >= threshold:
            current = (threshold, name, emoji)
    return {"name": current[1], "emoji": current[2], "xp_threshold": current[0]}


@api_v1_bp.route("/leaderboard/<event_id>", methods=["GET"])
def api_leaderboard(event_id):
    """Get event leaderboard."""
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    # Fetch scores for this event
    regs = []
    for doc in (
        db.collection("registrations")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .stream()
    ):
        r = doc.to_dict()
        r["id"] = doc.id
        # Get scores
        scores = []
        for s in db.collection("registrations").document(doc.id).collection("scores").stream():
            scores.append(s.to_dict())
        if scores:
            avg_score = sum(s.get("total", 0) for s in scores) / len(scores)
            r["avg_score"] = round(avg_score, 2)
            r["judge_count"] = len(scores)
        else:
            r["avg_score"] = 0
            r["judge_count"] = 0
        regs.append(r)

    # Sort by score descending
    regs.sort(key=lambda x: x.get("avg_score", 0), reverse=True)

    # Add rank
    for i, r in enumerate(regs):
        r["rank"] = i + 1

    return api_success(regs)


# ═══════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/notifications", methods=["GET"])
@jwt_required
def api_notifications():
    """Get user's notifications."""
    db = _db()
    email = g.jwt_user["sub"]
    page = safe_int(request.args.get("page"), 1)
    per_page = min(safe_int(request.args.get("per_page"), 20), 50)

    notifs = []
    for doc in (
        db.collection("notifications_v2")
        .where(filter=FieldFilter("user_email", "==", email))
        .order_by("created_at", direction="DESCENDING")
        .limit(per_page)
        .stream()
    ):
        n = doc.to_dict()
        n["id"] = doc.id
        notifs.append(n)

    return api_success(notifs)


# ═══════════════════════════════════════════════════════════════════════════
# ORGANIZATIONS (Multi-tenant)
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/orgs", methods=["GET"])
@jwt_roles_required(["SuperAdmin"])
def api_list_orgs():
    """List all organizations (SuperAdmin only)."""
    from models_tenant import list_organizations
    db = _db()
    orgs = list_organizations(db)
    return api_success(orgs)


@api_v1_bp.route("/orgs", methods=["POST"])
@jwt_roles_required(["SuperAdmin"])
def api_create_org():
    """Create a new organization (SuperAdmin only)."""
    from models_tenant import create_organization
    db = _db()
    data = request.get_json(silent=True) or {}

    required = ["name", "slug"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return api_error("missing_fields", f"Required fields: {missing}")

    org = create_organization(
        db,
        name=data["name"],
        slug=data["slug"],
        domain=data.get("domain", ""),
        logo_url=data.get("logo_url", ""),
        plan=data.get("plan", "free"),
        timezone_str=data.get("timezone", "Asia/Kolkata"),
        currency=data.get("currency", "INR"),
        owner_email=data.get("owner_email", g.jwt_user["sub"]),
        theme=data.get("theme"),
    )

    return api_success(org, status=201)



@api_v1_bp.route("/webhooks/email", methods=["POST"])
def api_webhook_email():
    """Webhook handler for Brevo/Resend email delivery events.
    Updates the delivery status of registrations in Firestore.
    """
    data = request.get_json(silent=True) or {}
    logger.info("Received email webhook event: %s", data)
    
    target_email = None
    status = None
    
    # 1. Brevo webhook format
    if "event" in data:
        target_email = data.get("email")
        event = data.get("event")
        # Map Brevo events to nice display statuses
        if event == "delivered":
            status = "Delivered"
        elif event in ("opened", "clicks", "unique_opened"):
            status = "Opened"
        elif event in ("soft_bounce", "hard_bounce", "invalid_email", "blocked"):
            status = "Bounced"
        elif event == "request":
            status = "Sent"
            
    # 2. Resend webhook format
    elif "type" in data:
        event_type = data.get("type", "")
        if event_type.startswith("email."):
            resend_data = data.get("data", {})
            to_list = resend_data.get("to", [])
            if to_list:
                target_email = to_list[0]
            if event_type == "email.delivered":
                status = "Delivered"
            elif event_type == "email.opened":
                status = "Opened"
            elif event_type == "email.bounced":
                status = "Bounced"
            elif event_type == "email.sent":
                status = "Sent"

    if not target_email or not status:
        return api_error("bad_request", "Invalid webhook format or empty data", status=400)
        
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    # Find registrations matching lead_email and update delivery_status
    try:
        regs = list(
            db.collection("registrations")
            .where(filter=FieldFilter("lead_email", "==", target_email))
            .stream()
        )
        if not regs:
            return api_success({"message": f"No registrations found for {target_email}"})
            
        # Update the most recent registration
        regs.sort(key=lambda x: x.to_dict().get("registered_at", ""), reverse=True)
        regs[0].reference.update({
            "delivery_status": status
        })
        logger.info("Updated registration %s email status to %s", regs[0].id, status)
        return api_success({"message": f"Updated status to {status} for {target_email}"})
    except Exception as exc:
        logger.error("Failed to update registration status: %s", exc)
        return api_error("internal_error", str(exc), status=500)


# ═══════════════════════════════════════════════════════════════════════════
# EVENT TEMPLATES & WORKFLOW STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/templates", methods=["GET"])
def api_list_templates():
    """List all pre-built universal event templates."""
    from services_templates import TemplateService
    templates = TemplateService.list_templates()
    return api_success({"templates": templates, "count": len(templates)})


@api_v1_bp.route("/templates/<template_id>", methods=["GET"])
def api_get_template(template_id):
    """Retrieve full specification for a specific event template."""
    from services_templates import TemplateService
    template = TemplateService.get_template(template_id)
    if not template:
        return api_error("not_found", f"Template '{template_id}' not found", status=404)
    return api_success(template)


@api_v1_bp.route("/events/from-template", methods=["POST"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer"])
def api_create_event_from_template():
    """Create an event pre-configured from a turnkey template."""
    from services_templates import TemplateService
    data = request.get_json(silent=True) or {}
    template_id = (data.get("template_id") or "").strip().lower()
    title = (data.get("title") or "").strip()
    date_str = (data.get("date") or "").strip()

    if not template_id or not title or not date_str:
        return api_error("missing_fields", "template_id, title, and date are required")

    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    try:
        event = TemplateService.instantiate_event(
            db,
            template_id=template_id,
            title=title,
            date_str=date_str,
            deadline_str=(data.get("registration_deadline") or "").strip(),
            venue=(data.get("venue") or "").strip(),
            organization_id=data.get("organization_id"),
            created_by=g.jwt_user.get("sub", ""),
            overrides=data.get("overrides"),
        )
        return api_success(event, status=201)
    except ValueError as e:
        return api_error("invalid_template", str(e), status=400)
    except Exception as e:
        logger.error("Error creating event from template: %s", e)
        return api_error("server_error", str(e), status=500)


@api_v1_bp.route("/events/<event_id>/workflow-transition", methods=["POST"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer"])
def api_transition_event_workflow(event_id):
    """Execute guarded state transition on an event with audit trail."""
    from services_workflow import WorkflowEngine, WorkflowError
    data = request.get_json(silent=True) or {}
    target_state = (data.get("target_state") or "").strip().lower()
    reason = (data.get("reason") or "").strip()
    metadata = data.get("metadata") or {}
    force = bool(data.get("force", False) and g.jwt_user.get("role") in ("SuperAdmin", "Admin"))

    if not target_state:
        return api_error("missing_fields", "target_state is required")

    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    try:
        updated = WorkflowEngine.transition_event(
            db,
            event_id=event_id,
            target_state=target_state,
            actor_id=g.jwt_user.get("sub", "system"),
            reason=reason,
            metadata=metadata,
            force=force,
        )
        return api_success(updated)
    except WorkflowError as e:
        return api_error("workflow_violation", str(e), status=400)
    except Exception as e:
        logger.error("Error in event workflow transition: %s", e)
        return api_error("server_error", str(e), status=500)


@api_v1_bp.route("/registrations/<reg_id>/workflow-transition", methods=["POST"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer", "Judge", "Volunteer"])
def api_transition_participant_workflow(reg_id):
    """Execute guarded participant state transition with audit trail."""
    from services_workflow import WorkflowEngine, WorkflowError
    data = request.get_json(silent=True) or {}
    target_state = (data.get("target_state") or "").strip().lower()
    reason = (data.get("reason") or "").strip()
    metadata = data.get("metadata") or {}
    force = bool(data.get("force", False) and g.jwt_user.get("role") in ("SuperAdmin", "Admin"))

    if not target_state:
        return api_error("missing_fields", "target_state is required")

    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    try:
        updated = WorkflowEngine.transition_participant(
            db,
            registration_id=reg_id,
            target_state=target_state,
            actor_id=g.jwt_user.get("sub", "system"),
            reason=reason,
            metadata=metadata,
            force=force,
        )
        return api_success(updated)
    except WorkflowError as e:
        return api_error("workflow_violation", str(e), status=400)
    except Exception as e:
        logger.error("Error in participant workflow transition: %s", e)
        return api_error("server_error", str(e), status=500)


@api_v1_bp.route("/workflow/history/<entity_type>/<entity_id>", methods=["GET"])
@jwt_required
def api_get_workflow_history(entity_type, entity_id):
    """Retrieve complete audit history of workflow state transitions."""
    from services_workflow import WorkflowEngine
    if entity_type not in ("event", "registration"):
        return api_error("invalid_entity", "entity_type must be 'event' or 'registration'", status=400)

    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    history = WorkflowEngine.get_workflow_history(db, entity_type=entity_type, entity_id=entity_id)
    return api_success({"history": history, "count": len(history)})


# ═══════════════════════════════════════════════════════════════════════════
# OFFLINE CHECK-IN ROSTER & BATCH SYNC
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/events/<event_id>/ticket-manifest", methods=["GET"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer", "EventCoordinator"])
def api_get_ticket_manifest(event_id):
    """Download attendee & ticket manifest for offline scanner IndexedDB caching."""
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    event_doc = db.collection("events").document(event_id).get()
    if not event_doc.exists:
        return api_error("not_found", "Event not found", status=404)
    event_data = event_doc.to_dict()

    tickets = []
    try:
        if FieldFilter:
            docs = db.collection("tickets").where(filter=FieldFilter("event_id", "==", event_id)).stream()
        else:
            docs = db.collection("tickets").where("event_id", "==", event_id).stream()

        for d in docs:
            t = d.to_dict()
            t["id"] = d.id
            tickets.append({
                "ticket_id": t.get("id"),
                "ticket_code": t.get("ticket_code"),
                "qr_token_hash": t.get("qr_token_hash"),
                "lead_name": t.get("lead_name"),
                "ticket_type": t.get("ticket_type", "General"),
                "status": t.get("status", "active"),
                "gate_assignment": t.get("gate_assignment", "Gate 1"),
                "seat_assignment": t.get("seat_assignment", "General Open"),
            })
    except Exception as e:
        logger.error("Error fetching ticket manifest: %s", e)

    # Fallback: if no tickets generated yet, pull from registrations
    if not tickets:
        try:
            if FieldFilter:
                reg_docs = db.collection("registrations").where(filter=FieldFilter("event_id", "==", event_id)).stream()
            else:
                reg_docs = db.collection("registrations").where("event_id", "==", event_id).stream()

            for rd in reg_docs:
                r = rd.to_dict()
                tickets.append({
                    "ticket_id": r.get("ticket_id") or rd.id,
                    "ticket_code": r.get("ticket_code") or f"REG-{rd.id[:8]}",
                    "qr_token_hash": r.get("signed_token", ""),
                    "lead_name": r.get("lead_name", ""),
                    "ticket_type": r.get("ticket_type", "General"),
                    "status": "checked_in" if r.get("attendance") == "Present" else "active",
                    "gate_assignment": "Gate 1",
                    "seat_assignment": "General Open",
                })
        except Exception:
            pass

    return api_success({
        "event_id": event_id,
        "event_title": event_data.get("title", ""),
        "total_tickets": len(tickets),
        "manifest_version": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tickets": tickets,
    })


@api_v1_bp.route("/events/<event_id>/checkin-batch", methods=["POST"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer", "EventCoordinator"])
def api_sync_checkin_batch(event_id):
    """
    Synchronize offline check-ins queue to server with deterministic conflict resolution.
    Earliest verified scan timestamp wins.
    """
    from services_ticket import TicketService
    data = request.get_json(silent=True) or {}
    checkins = data.get("checkins", [])

    if not isinstance(checkins, list):
        return api_error("invalid_payload", "checkins must be an array of check-in entries")

    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    # Sort check-ins chronologically by scanned_at to enforce 'earliest timestamp wins'
    checkins.sort(key=lambda x: x.get("scanned_at", ""))

    synced = []
    duplicates = []
    errors = []

    for item in checkins:
        token_or_id = item.get("token_or_id") or item.get("ticket_id") or item.get("ticket_code")
        actor_id = item.get("actor_id") or g.jwt_user.get("sub", "offline_scanner")
        if not token_or_id:
            continue

        try:
            res = TicketService.checkin_ticket(db, token_or_id, actor_id=actor_id)
            if res["status"] == "success":
                synced.append({
                    "ticket_id": token_or_id,
                    "checked_in_at": item.get("scanned_at") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "status": "synced",
                })
            elif res["status"] == "already_used":
                duplicates.append({
                    "ticket_id": token_or_id,
                    "message": res.get("message"),
                    "status": "duplicate",
                })
            else:
                errors.append({
                    "ticket_id": token_or_id,
                    "message": res.get("message"),
                    "status": "error",
                })
        except Exception as e:
            errors.append({"ticket_id": token_or_id, "message": str(e), "status": "exception"})

    return api_success({
        "event_id": event_id,
        "processed_count": len(checkins),
        "synced_count": len(synced),
        "duplicate_count": len(duplicates),
        "error_count": len(errors),
        "synced": synced,
        "duplicates": duplicates,
        "errors": errors,
    })


# ═══════════════════════════════════════════════════════════════════════════
# EVALUATION & CERTIFICATION (Phase 6)
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/events/<event_id>/scores", methods=["POST"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer", "Judge", "EventCoordinator"])
def api_submit_score(event_id):
    """Submit an evaluation / score for a participant in an event."""
    from services_evaluation import EvaluationEngine
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    data = request.get_json(silent=True) or {}
    registration_id = data.get("registration_id")
    raw_scores = data.get("raw_scores") or data.get("scores") or {}
    round_num = safe_int(data.get("round"), 1)
    remarks = data.get("remarks", "")

    if not registration_id:
        return api_error("missing_fields", "registration_id is required", status=400)

    judge_id = g.jwt_user.get("sub", "anonymous_judge")
    judge_name = g.jwt_user.get("name") or judge_id

    try:
        res = EvaluationEngine.record_score(
            db,
            event_id=event_id,
            registration_id=registration_id,
            judge_id=judge_id,
            judge_name=judge_name,
            raw_scores=raw_scores,
            round_num=round_num,
            remarks=remarks,
        )
        return api_success(res, status=201)
    except ValueError as e:
        return api_error("not_found", str(e), status=404)
    except Exception as e:
        logger.error("Error recording score: %s", e)
        return api_error("internal_error", str(e), status=500)


@api_v1_bp.route("/events/<event_id>/leaderboard", methods=["GET"])
def api_event_leaderboard(event_id):
    """Retrieve ranked leaderboard for an event with rubric tie-breaking."""
    from services_evaluation import EvaluationEngine
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    round_arg = request.args.get("round")
    round_num = int(round_arg) if round_arg and round_arg.isdigit() else None

    leaderboard = EvaluationEngine.generate_leaderboard(db, event_id, round_num=round_num)
    return api_success({
        "event_id": event_id,
        "round": round_num,
        "total_participants": len(leaderboard),
        "leaderboard": leaderboard,
    })


@api_v1_bp.route("/events/<event_id>/issue-certificates", methods=["POST"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer"])
def api_bulk_issue_certificates(event_id):
    """Bulk issue certificates for an event (winners, runner ups, participants)."""
    from services_certificate import CertificateService
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    data = request.get_json(silent=True) or {}
    category = data.get("category")

    try:
        certs = CertificateService.bulk_issue_event_certificates(db, event_id, category=category)
        return api_success({
            "event_id": event_id,
            "issued_count": len(certs),
            "certificates": certs,
        }, status=201)
    except ValueError as e:
        return api_error("not_found", str(e), status=404)
    except Exception as e:
        logger.error("Error bulk issuing certificates: %s", e)
        return api_error("internal_error", str(e), status=500)


@api_v1_bp.route("/certificates/<cert_id>", methods=["GET"])
def api_verify_certificate(cert_id):
    """Public certificate verification endpoint."""
    from services_certificate import CertificateService
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    valid, message, cert_data = CertificateService.verify_certificate(db, cert_id)
    if not valid and not cert_data:
        return api_error("not_found", message, status=404)

    return api_success({
        "verified": valid,
        "message": message,
        "certificate": cert_data,
    })


# ═══════════════════════════════════════════════════════════════════════════
# AUTOMATION & EVENT TRIGGERS (Phase 7)
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/events/<event_id>/broadcast", methods=["POST"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer"])
def api_broadcast_event_trigger(event_id):
    """Broadcast an automated notification trigger to all event participants."""
    from services_automation import NotificationAutomationEngine
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    data = request.get_json(silent=True) or {}
    trigger_name = data.get("trigger_name") or data.get("trigger")
    if not trigger_name:
        return api_error("missing_fields", "trigger_name is required", status=400)

    try:
        results = NotificationAutomationEngine.broadcast_event_trigger(
            db,
            event_id=event_id,
            trigger_name=trigger_name,
            extra_context=data.get("context"),
        )
        return api_success({
            "event_id": event_id,
            "trigger_name": trigger_name,
            "broadcast_count": len(results),
            "results": results,
        })
    except ValueError as e:
        return api_error("not_found", str(e), status=404)
    except Exception as e:
        logger.error("Error in broadcast trigger: %s", e)
        return api_error("internal_error", str(e), status=500)


@api_v1_bp.route("/notifications/trigger", methods=["POST"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer", "EventCoordinator"])
def api_dispatch_single_trigger():
    """Dispatch an automated trigger to a specific participant."""
    from services_automation import NotificationAutomationEngine
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    data = request.get_json(silent=True) or {}
    trigger_name = data.get("trigger_name")
    context = data.get("context") or {}
    idempotency_key = data.get("idempotency_key")

    if not trigger_name or not context.get("recipient_email"):
        return api_error("missing_fields", "trigger_name and context.recipient_email are required", status=400)

    try:
        res = NotificationAutomationEngine.dispatch_trigger(
            db,
            trigger_name=trigger_name,
            context=context,
            idempotency_key=idempotency_key,
        )
        return api_success(res)
    except Exception as e:
        logger.error("Error dispatching notification trigger: %s", e)
        return api_error("internal_error", str(e), status=500)


# ═══════════════════════════════════════════════════════════════════════════
# FINANCIAL MANAGEMENT & MULTI-CURRENCY (Phase 8)
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/finance/checkout-preview", methods=["POST"])
def api_checkout_preview():
    """Calculate itemized pricing breakdown with discounts, taxes, and fees."""
    from services_finance import FinanceEngine
    data = request.get_json(silent=True) or {}
    unit_price = float(data.get("unit_price", 0.0))
    quantity = safe_int(data.get("quantity"), 1)
    currency = data.get("currency", "INR")
    coupon_data = data.get("coupon")
    tax_pct = float(data.get("tax_percentage", 18.0))
    fee_pct = float(data.get("convenience_fee_percentage", 2.0))

    breakdown = FinanceEngine.calculate_checkout(
        unit_price=unit_price,
        quantity=quantity,
        currency=currency,
        coupon_data=coupon_data,
        tax_percentage=tax_pct,
        convenience_fee_percentage=fee_pct,
    )
    return api_success(breakdown)


@api_v1_bp.route("/finance/convert", methods=["POST"])
def api_currency_convert():
    """Convert amount between supported currencies."""
    from services_finance import FinanceEngine
    data = request.get_json(silent=True) or {}
    amount = float(data.get("amount", 0.0))
    from_curr = data.get("from_currency", "INR")
    to_curr = data.get("to_currency", "USD")

    converted = FinanceEngine.convert_currency(amount, from_curr, to_curr)
    return api_success({
        "original_amount": amount,
        "from_currency": from_curr.upper(),
        "converted_amount": converted,
        "to_currency": to_curr.upper(),
        "formatted": FinanceEngine.format_currency(converted, to_curr),
    })


@api_v1_bp.route("/events/<event_id>/payout-summary", methods=["GET"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer"])
def api_event_payout_summary(event_id):
    """Aggregate financial ledger, revenue, and net payout for an event."""
    from services_finance import FinanceEngine
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    summary = FinanceEngine.calculate_event_payout_summary(db, event_id)
    return api_success(summary)


# ═══════════════════════════════════════════════════════════════════════════
# CONTROL PLANE & MULTI-TENANT GOVERNANCE (Phase 9)
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/control-plane/overview", methods=["GET"])
@jwt_roles_required(["SuperAdmin"])
def api_control_plane_overview():
    """Retrieve global platform health metrics and tenant distributions (SuperAdmin only)."""
    from services_control_plane import ControlPlaneService
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    overview = ControlPlaneService.get_platform_overview(db)
    return api_success(overview)


@api_v1_bp.route("/control-plane/orgs/<org_id>/plan", methods=["POST"])
@jwt_roles_required(["SuperAdmin"])
def api_control_plane_update_plan(org_id):
    """Upgrade or downgrade tenant subscription plan (SuperAdmin only)."""
    from services_control_plane import ControlPlaneService
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    data = request.get_json(silent=True) or {}
    new_plan = data.get("plan")
    if not new_plan:
        return api_error("missing_fields", "plan is required (free, pro, enterprise)", status=400)

    actor = g.jwt_user.get("sub", "superadmin")
    try:
        res = ControlPlaneService.update_organization_plan(db, org_id, new_plan, actor_email=actor)
        return api_success(res)
    except ValueError as e:
        return api_error("invalid_request", str(e), status=400)
    except Exception as e:
        logger.error("Error updating org plan: %s", e)
        return api_error("internal_error", str(e), status=500)


@api_v1_bp.route("/control-plane/orgs/<org_id>/status", methods=["POST"])
@jwt_roles_required(["SuperAdmin"])
def api_control_plane_toggle_status(org_id):
    """Suspend or reactivate tenant organization (SuperAdmin only)."""
    from services_control_plane import ControlPlaneService
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    data = request.get_json(silent=True) or {}
    status_val = data.get("status")
    reason = data.get("reason", "")
    if not status_val:
        return api_error("missing_fields", "status is required (active, suspended, archived)", status=400)

    actor = g.jwt_user.get("sub", "superadmin")
    try:
        res = ControlPlaneService.toggle_organization_status(db, org_id, status_val, actor_email=actor, reason=reason)
        return api_success(res)
    except ValueError as e:
        return api_error("invalid_request", str(e), status=400)
    except Exception as e:
        logger.error("Error toggling org status: %s", e)
        return api_error("internal_error", str(e), status=500)


@api_v1_bp.route("/control-plane/impersonate", methods=["POST"])
@jwt_roles_required(["SuperAdmin"])
def api_control_plane_impersonate():
    """Log an auditable SuperAdmin impersonation access to a tenant workspace."""
    from services_control_plane import ControlPlaneService
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    data = request.get_json(silent=True) or {}
    target_org_id = data.get("target_org_id")
    reason = data.get("reason", "Customer Support Investigation")
    if not target_org_id:
        return api_error("missing_fields", "target_org_id is required", status=400)

    superadmin = g.jwt_user.get("sub", "superadmin")
    log_entry = ControlPlaneService.log_impersonation_session(
        db,
        superadmin_email=superadmin,
        target_org_id=target_org_id,
        reason=reason,
    )
    return api_success(log_entry, status=201)


# ═══════════════════════════════════════════════════════════════════════════
# ZERO-TRUST SECURITY & INCIDENT LOGS (Phase 10)
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/security/incidents", methods=["GET"])
@jwt_roles_required(["SuperAdmin"])
def api_security_incidents():
    """List recent security incidents and tamper alerts (SuperAdmin only)."""
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    incidents = []
    for doc in db.collection("security_incidents").limit(50).stream():
        d = doc.to_dict()
        d["id"] = doc.id
        incidents.append(d)

    return api_success({"total": len(incidents), "incidents": incidents})


@api_v1_bp.route("/security/verify-nonce", methods=["POST"])
def api_verify_security_nonce():
    """Verify validity and expiration of a time-bound security nonce."""
    from security_guard import SecurityGuard
    data = request.get_json(silent=True) or {}
    nonce = data.get("nonce")
    subject = data.get("subject")
    secret = os.environ.get("SECRET_KEY", "default-salt-key-2026")

    if not nonce or not subject:
        return api_error("missing_fields", "nonce and subject are required", status=400)

    is_valid, reason = SecurityGuard.verify_time_bound_nonce(nonce, subject, secret)
    return api_success({"valid": is_valid, "message": reason})


# ═══════════════════════════════════════════════════════════════════════════
# REAL-TIME ANALYTICS & EXECUTIVE BI (Phase 11)
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/analytics/events/<event_id>/funnel", methods=["GET"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer"])
def api_event_conversion_funnel(event_id):
    """Retrieve registration-to-attendance conversion funnel metrics."""
    from services_analytics import AnalyticsService
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    try:
        funnel = AnalyticsService.get_event_conversion_funnel(db, event_id)
        return api_success(funnel)
    except ValueError as e:
        return api_error("not_found", str(e), status=404)
    except Exception as e:
        logger.error("Error calculating funnel: %s", e)
        return api_error("internal_error", str(e), status=500)


@api_v1_bp.route("/analytics/events/<event_id>/throughput", methods=["GET"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer", "EventCoordinator"])
def api_event_throughput(event_id):
    """Retrieve gate check-in scanner velocity and hourly peaks."""
    from services_analytics import AnalyticsService
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    throughput = AnalyticsService.get_gate_throughput_velocity(db, event_id)
    return api_success(throughput)


@api_v1_bp.route("/analytics/events/<event_id>/demographics", methods=["GET"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer"])
def api_event_demographics(event_id):
    """Retrieve attendee institution, branch, and demographic distributions."""
    from services_analytics import AnalyticsService
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    demographics = AnalyticsService.get_demographics_summary(db, event_id)
    return api_success(demographics)


@api_v1_bp.route("/analytics/events/<event_id>/executive-summary", methods=["GET"])
@jwt_roles_required(["SuperAdmin", "Admin", "SPOC", "Organizer"])
def api_event_executive_summary(event_id):
    """Retrieve unified executive BI report card for an event."""
    from services_analytics import AnalyticsService
    db = _db()
    if db is None:
        return api_error("service_unavailable", "Database not available", status=503)

    try:
        summary = AnalyticsService.get_executive_summary(db, event_id)
        return api_success(summary)
    except ValueError as e:
        return api_error("not_found", str(e), status=404)
    except Exception as e:
        logger.error("Error generating executive summary: %s", e)
        return api_error("internal_error", str(e), status=500)


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH / DOCS
# ═══════════════════════════════════════════════════════════════════════════

@api_v1_bp.route("/", methods=["GET"])
def api_root():
    """API information and available endpoints."""
    return api_success({
        "name": "SapthaEvent API",
        "version": "1.0.0",
        "description": "Industrial-grade college event management API",
        "endpoints": {
            "auth": {
                "POST /api/v1/auth/login": "Authenticate and receive JWT tokens",
                "POST /api/v1/auth/register": "Register a new account",
                "POST /api/v1/auth/refresh": "Refresh access token",
                "POST /api/v1/auth/logout": "Invalidate current token",
            },
            "events": {
                "GET /api/v1/events": "List events (paginated, filterable)",
                "GET /api/v1/events/<id>": "Get event details",
                "POST /api/v1/events": "Create event (SPOC/Admin)",
                "PUT /api/v1/events/<id>": "Update event",
                "POST /api/v1/events/<id>/register": "Register for event",
            },
            "templates": {
                "GET /api/v1/templates": "List pre-built event templates",
                "GET /api/v1/templates/<id>": "Get template specifications",
                "POST /api/v1/events/from-template": "Create event from template",
            },
            "workflow": {
                "POST /api/v1/events/<id>/workflow-transition": "Transition event lifecycle stage",
                "POST /api/v1/registrations/<id>/workflow-transition": "Transition participant stage",
                "GET /api/v1/workflow/history/<type>/<id>": "Get transition audit history",
            },
            "users": {
                "GET /api/v1/users/me": "Get your profile",
                "PUT /api/v1/users/me": "Update your profile",
                "GET /api/v1/achievements": "Get XP and badges",
                "GET /api/v1/registrations": "Your registrations",
            },
            "other": {
                "GET /api/v1/leaderboard/<event_id>": "Event leaderboard",
                "GET /api/v1/notifications": "Your notifications",
                "GET /api/v1/orgs": "List organizations (SuperAdmin)",
                "POST /api/v1/orgs": "Create organization (SuperAdmin)",
            },
        },
    })

