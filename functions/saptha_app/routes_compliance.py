"""
routes_compliance.py — GDPR / DPDP Compliance Toolkit for SapthaEvent

Provides data export, deletion requests, and consent management
per Indian DPDP Act 2023 and GDPR requirements.

Blueprint prefix: /compliance
"""
import logging
import json
import datetime
import uuid

from flask import Blueprint, request, session, jsonify, render_template
from google.cloud.firestore_v1.base_query import FieldFilter

from utils import login_required

logger = logging.getLogger(__name__)
compliance_bp = Blueprint("compliance", __name__, url_prefix="/compliance")


@compliance_bp.route("/sla", methods=["GET"])
def sla_page():
    """GET /compliance/sla — Public SLA & service status page."""
    services = [
        {"name": "Database API", "status": "Operational", "uptime": "99.98%", "icon": "fa-database"},
        {"name": "Email Gateway", "status": "Operational", "uptime": "100.0%", "icon": "fa-envelope"},
        {"name": "Stripe Gateway", "status": "Operational", "uptime": "99.99%", "icon": "fa-credit-card"},
        {"name": "WhatsApp Service", "status": "Operational", "uptime": "99.95%", "icon": "fa-whatsapp"},
        {"name": "AI Generation API", "status": "Operational", "uptime": "99.90%", "icon": "fa-robot"}
    ]
    return render_template("compliance/sla.html", services=services)


@compliance_bp.route("/settings", methods=["GET"])
@login_required
def privacy_settings_page():
    """GET /compliance/settings — Privacy & DPDP Act 2023 User Controls."""
    return render_template("compliance/privacy_settings.html")


def _db():
    from app import db
    return db


@compliance_bp.route("/export-data", methods=["POST"])
@login_required
def export_user_data():
    """Export all user data as JSON (GDPR Article 20 — Data Portability)."""
    db = _db()
    email = session["user_id"]

    export = {
        "export_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "user_email": email,
        "sections": {},
    }

    # 1. Profile
    user_doc = db.collection("users").document(email).get()
    if user_doc.exists:
        profile = user_doc.to_dict()
        profile.pop("password_hash", None)
        profile.pop("password", None)
        profile.pop("totp_secret", None)
        profile.pop("totp_backup_codes", None)
        export["sections"]["profile"] = profile

    # 2. Registrations
    regs = []
    for doc in db.collection("registrations").where(
        filter=FieldFilter("lead_email", "==", email)
    ).stream():
        r = doc.to_dict()
        r["id"] = doc.id
        regs.append(r)
    export["sections"]["registrations"] = regs

    # 3. Feedback
    feedback = []
    for r in regs:
        fd = r.get("feedback")
        if fd and isinstance(fd, dict):
            fb_item = dict(fd)
            fb_item["registration_id"] = r["id"]
            fb_item["event_id"] = r.get("event_id")
            fb_item["event_title"] = r.get("event_title")
            feedback.append(fb_item)
    export["sections"]["feedback"] = feedback

    # 4. Notifications
    notifs = []
    for doc in db.collection("notifications_v2").where(
        filter=FieldFilter("user_email", "==", email)
    ).stream():
        n = doc.to_dict()
        n["id"] = doc.id
        notifs.append(n)
    export["sections"]["notifications"] = notifs

    # 5. Audit log entries (about this user)
    audit = []
    for doc in db.collection("audit_log_v2").where(
        filter=FieldFilter("actor_email", "==", email)
    ).limit(500).stream():
        a = doc.to_dict()
        a["id"] = doc.id
        audit.append(a)
    export["sections"]["audit_trail"] = audit

    # Log the export
    try:
        from audit_logger import AuditLogger
        AuditLogger(db).log("DATA_EXPORT_REQUESTED", target_type="user",
                            target_id=email, severity="INFO")
    except Exception:
        pass

    return jsonify(export)


@compliance_bp.route("/delete-request", methods=["POST"])
@login_required
def request_deletion():
    """Request account and data deletion (30-day grace period).

    GDPR Article 17 — Right to Erasure
    DPDP Act 2023 — Right to Erasure
    """
    db = _db()
    email = session["user_id"]
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "User requested deletion")

    # Check if already pending
    existing = (
        db.collection("deletion_requests")
        .where(filter=FieldFilter("email", "==", email))
        .where(filter=FieldFilter("status", "==", "pending"))
        .limit(1)
        .stream()
    )
    if any(True for _ in existing):
        return jsonify({"error": "Deletion request already pending"}), 409

    req_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc)
    scheduled_at = now + datetime.timedelta(days=30)

    try:
        db.collection("deletion_requests").document(req_id).set({
            "id": req_id,
            "email": email,
            "reason": reason,
            "status": "pending",
            "requested_at": now.isoformat(),
            "scheduled_deletion_at": scheduled_at.isoformat(),
            "cancelled_at": None,
        })
    except Exception as exc:
        return jsonify({"error": "Failed to persist deletion request", "detail": str(exc)}), 500

    # Notify user
    try:
        from routes_notifications_v2 import create_notification
        create_notification(
            db, user_email=email, notif_type="system_alert",
            title="Account Deletion Scheduled",
            message=f"Your account will be deleted on {scheduled_at.strftime('%B %d, %Y')}. "
                    "You can cancel this from Privacy Settings.",
            link="/compliance/consent",
        )
    except Exception:
        pass

    return jsonify({
        "message": "Deletion request submitted",
        "request_id": req_id,
        "scheduled_deletion": scheduled_at.isoformat(),
        "can_cancel_until": scheduled_at.isoformat(),
    })


@compliance_bp.route("/cancel-deletion", methods=["POST"])
@login_required
def cancel_deletion():
    """Cancel a pending deletion request."""
    db = _db()
    email = session["user_id"]

    for doc in (
        db.collection("deletion_requests")
        .where(filter=FieldFilter("email", "==", email))
        .where(filter=FieldFilter("status", "==", "pending"))
        .limit(1)
        .stream()
    ):
        db.collection("deletion_requests").document(doc.id).update({
            "status": "cancelled",
            "cancelled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        return jsonify({"message": "Deletion request cancelled"})

    return jsonify({"error": "No pending deletion request found"}), 404


@compliance_bp.route("/consent", methods=["GET"])
@login_required
def get_consent():
    """Get user's consent settings."""
    db = _db()
    email = session["user_id"]

    defaults = {
        "email_marketing": False,
        "push_notifications": True,
        "analytics_tracking": True,
        "third_party_sharing": False,
        "data_processing": True,      # Required for service
        "accepted_privacy_policy": True,
        "accepted_terms": True,
        "consent_updated_at": None,
    }

    doc = db.collection("user_consent").document(email).get()
    if doc.exists:
        consent = doc.to_dict()
        defaults.update(consent)

    # Check for pending deletion
    deletion_pending = False
    for _ in (
        db.collection("deletion_requests")
        .where(filter=FieldFilter("email", "==", email))
        .where(filter=FieldFilter("status", "==", "pending"))
        .limit(1)
        .stream()
    ):
        deletion_pending = True

    defaults["deletion_pending"] = deletion_pending

    return jsonify(defaults)


@compliance_bp.route("/consent", methods=["PUT"])
@login_required
def update_consent():
    """Update consent settings."""
    db = _db()
    email = session["user_id"]
    data = request.get_json(silent=True) or {}

    allowed = [
        "email_marketing", "push_notifications", "analytics_tracking",
        "third_party_sharing",
    ]
    updates = {k: bool(v) for k, v in data.items() if k in allowed}
    updates["consent_updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        db.collection("user_consent").document(email).set(updates, merge=True)
    except Exception as exc:
        return jsonify({"error": "Failed to update consent preferences", "detail": str(exc)}), 500

    # Log consent change
    try:
        from audit_logger import AuditLogger
        AuditLogger(db).log(
            "CONSENT_UPDATED", target_type="user", target_id=email,
            details=f"Updated: {list(updates.keys())}",
        )
    except Exception:
        pass

    return jsonify({"message": "Consent updated", "updated": updates})
