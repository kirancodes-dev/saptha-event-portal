"""
models_tenant.py — Multi-Tenant Organization Models for SapthaEvent

Enables the platform to serve multiple colleges/universities from a single
deployment.  Every user, event, and registration is scoped to an Organization.

Usage:
    from models_tenant import Organization, OrganizationMember
    org = get_org_by_slug('mit-manipal')
"""
import enum
import uuid
import secrets
from datetime import datetime, timezone
from typing import Optional
from google.cloud.firestore_v1.base_query import FieldFilter


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class OrgPlan(enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class MemberRole(enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


# ---------------------------------------------------------------------------
# Firestore-based Organization helpers  (primary storage)
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_api_key() -> str:
    return f"sk_live_{secrets.token_urlsafe(32)}"


# ---------------------------------------------------------------------------
# CRUD helpers — work with the Firestore `db` client passed in
# ---------------------------------------------------------------------------

def create_organization(
    db,
    *,
    name: str,
    slug: str,
    domain: str = "",
    logo_url: str = "",
    plan: str = "free",
    timezone_str: str = "Asia/Kolkata",
    currency: str = "INR",
    owner_email: str = "",
    theme: Optional[dict] = None,
) -> dict:
    """Create a new Organization document in Firestore.

    Returns the created org dict including its generated ``id``.
    """
    org_id = str(uuid.uuid4())
    org_data = {
        "id": org_id,
        "name": name,
        "slug": slug.lower().strip(),
        "domain": domain.lower().strip(),
        "logo_url": logo_url,
        "plan": plan,
        "timezone": timezone_str,
        "currency": currency,
        "theme": theme or {
            "primary_color": "#1a2557",
            "accent_color": "#c9a45e",
            "dark_mode": False,
        },
        "settings": {
            "max_events_per_semester": 999 if plan != "free" else 5,
            "max_participants_per_event": 9999 if plan != "free" else 200,
            "ai_reports_enabled": plan != "free",
            "custom_branding": plan in ("pro", "enterprise"),
            "api_access": plan == "enterprise",
        },
        "is_active": True,
        "api_key": _generate_api_key(),
        "owner_email": owner_email,
        "created_at": _utcnow(),
        "updated_at": _utcnow(),
    }
    db.collection("organizations").document(org_id).set(org_data)

    # Auto-add owner as OWNER member
    if owner_email:
        add_member(db, org_id=org_id, email=owner_email, role="owner")

    return org_data


def get_org_by_slug(db, slug: str) -> Optional[dict]:
    """Look up an organization by its URL slug."""
    docs = (
        db.collection("organizations")
        .where(filter=FieldFilter("slug", "==", slug.lower().strip()))
        .where(filter=FieldFilter("is_active", "==", True))
        .limit(1)
        .stream()
    )
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return None


def get_org_by_domain(db, domain: str) -> Optional[dict]:
    """Look up an organization by email domain (e.g. 'manipal.edu')."""
    docs = (
        db.collection("organizations")
        .where(filter=FieldFilter("domain", "==", domain.lower().strip()))
        .where(filter=FieldFilter("is_active", "==", True))
        .limit(1)
        .stream()
    )
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return None


def get_org_by_id(db, org_id: str) -> Optional[dict]:
    """Fetch organization by ID."""
    doc = db.collection("organizations").document(org_id).get()
    if doc.exists:
        data = doc.to_dict()
        data["id"] = doc.id
        return data
    return None


def list_organizations(db, *, active_only: bool = True, limit: int = 100) -> list:
    """List all organizations."""
    query = db.collection("organizations")
    if active_only:
        query = query.where(filter=FieldFilter("is_active", "==", True))
    query = query.limit(limit)
    results = []
    for doc in query.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)
    return results


def update_organization(db, org_id: str, updates: dict) -> bool:
    """Update organization fields."""
    updates["updated_at"] = _utcnow()
    try:
        db.collection("organizations").document(org_id).update(updates)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Organization Members
# ---------------------------------------------------------------------------

def add_member(
    db,
    *,
    org_id: str,
    email: str,
    role: str = "member",
) -> dict:
    """Add a user as a member of an organization."""
    member_id = str(uuid.uuid4())
    member_data = {
        "id": member_id,
        "org_id": org_id,
        "email": email.lower().strip(),
        "role": role,
        "is_active": True,
        "joined_at": _utcnow(),
    }
    db.collection("org_members").document(member_id).set(member_data)
    return member_data


def get_user_orgs(db, email: str) -> list:
    """Get all organizations a user belongs to."""
    docs = (
        db.collection("org_members")
        .where(filter=FieldFilter("email", "==", email.lower().strip()))
        .where(filter=FieldFilter("is_active", "==", True))
        .stream()
    )
    orgs = []
    for doc in docs:
        member = doc.to_dict()
        org = get_org_by_id(db, member["org_id"])
        if org:
            org["member_role"] = member["role"]
            orgs.append(org)
    return orgs


def get_org_members(db, org_id: str) -> list:
    """Get all members of an organization."""
    docs = (
        db.collection("org_members")
        .where(filter=FieldFilter("org_id", "==", org_id))
        .where(filter=FieldFilter("is_active", "==", True))
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def is_org_member(db, org_id: str, email: str) -> bool:
    """Check if a user is a member of an organization."""
    docs = (
        db.collection("org_members")
        .where(filter=FieldFilter("org_id", "==", org_id))
        .where(filter=FieldFilter("email", "==", email.lower().strip()))
        .where(filter=FieldFilter("is_active", "==", True))
        .limit(1)
        .stream()
    )
    return any(True for _ in docs)
