"""
routes_api_v1.py — RESTful API v1 for SapthaEvent

Provides a JSON API consumed by mobile apps, third-party integrations,
and the future Next.js frontend.  Authenticated via JWT (see auth_jwt.py).

Blueprint prefix: /api/v1
"""
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
    from google.cloud.firestore_v1 import Increment
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
