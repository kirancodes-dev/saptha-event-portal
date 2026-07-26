"""
routes_notifications_v2.py — Enhanced Notification Center for SapthaEvent

Unified notification system supporting in-app, email, push, and WhatsApp
channels with user preference management.

Blueprint prefix: /notifications
"""
import logging
import datetime
import uuid

from flask import Blueprint, request, session, redirect, flash, render_template, jsonify, g
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from utils import login_required, safe_int

logger = logging.getLogger(__name__)
notif_v2_bp = Blueprint("notif_v2", __name__, url_prefix="/notifications")

NOTIFICATION_TYPES = {
    "event_reminder":         {"icon": "🔔", "color": "info",    "label": "Event Reminder"},
    "registration_confirmed": {"icon": "✅", "color": "success", "label": "Registration"},
    "payment_received":       {"icon": "💳", "color": "success", "label": "Payment"},
    "score_published":        {"icon": "📊", "color": "primary", "label": "Score"},
    "achievement_earned":     {"icon": "🏆", "color": "warning", "label": "Achievement"},
    "announcement":           {"icon": "📢", "color": "secondary", "label": "Announcement"},
    "system_alert":           {"icon": "⚠️", "color": "danger",  "label": "System"},
    "waitlist_promoted":      {"icon": "🎉", "color": "success", "label": "Waitlist"},
}


def _db():
    from app import db
    return db


# ═══════════════════════════════════════════════════════════════════════════
# HELPER: Create notification
# ═══════════════════════════════════════════════════════════════════════════

def create_notification(
    db, *, user_email: str, notif_type: str, title: str, message: str,
    link: str = "", metadata: dict = None
) -> str:
    """Create a notification for a user.

    Returns the notification ID. Can be called from any module::

        from routes_notifications_v2 import create_notification
        create_notification(db, user_email=email, notif_type="achievement_earned",
                           title="New Badge!", message="You earned Champion badge")
    """
    notif_id = str(uuid.uuid4())
    notif_data = {
        "id": notif_id,
        "user_email": user_email.lower().strip(),
        "type": notif_type,
        "title": title,
        "message": message,
        "link": link,
        "is_read": False,
        "metadata": metadata or {},
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    try:
        db.collection("notifications_v2").document(notif_id).set(notif_data)
    except Exception as exc:
        logger.error("Failed to create notification: %s", exc)
    return notif_id


def create_bulk_notifications(db, *, emails: list, notif_type: str, title: str, message: str, link: str = ""):
    """Create notifications for multiple users (batch)."""
    batch = db.batch()
    for email in emails:
        notif_id = str(uuid.uuid4())
        ref = db.collection("notifications_v2").document(notif_id)
        batch.set(ref, {
            "id": notif_id,
            "user_email": email.lower().strip(),
            "type": notif_type,
            "title": title,
            "message": message,
            "link": link,
            "is_read": False,
            "metadata": {},
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
    try:
        batch.commit()
    except Exception as exc:
        logger.error("Bulk notification error: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@notif_v2_bp.route("/api/list", methods=["GET"])
@login_required
def api_list_notifications():
    """Get user's notifications (paginated)."""
    db = _db()
    email = session["user_id"]
    page = safe_int(request.args.get("page"), 1)
    per_page = min(safe_int(request.args.get("per_page"), 20), 50)
    filter_type = request.args.get("type")
    unread_only = request.args.get("unread") == "true"

    query = db.collection("notifications_v2").where(
        filter=FieldFilter("user_email", "==", email)
    )
    if unread_only:
        query = query.where(filter=FieldFilter("is_read", "==", False))

    all_notifs = []
    for doc in query.order_by("created_at", direction="DESCENDING").stream():
        n = doc.to_dict()
        n["id"] = doc.id
        if filter_type and n.get("type") != filter_type:
            continue
        type_info = NOTIFICATION_TYPES.get(n.get("type", ""), {})
        n["icon"] = type_info.get("icon", "🔔")
        n["color"] = type_info.get("color", "secondary")
        n["label"] = type_info.get("label", "Notification")
        n["time_ago"] = _time_ago(n.get("created_at", ""))
        all_notifs.append(n)

    total = len(all_notifs)
    start = (page - 1) * per_page
    paged = all_notifs[start : start + per_page]

    return jsonify({
        "notifications": paged,
        "total": total,
        "page": page,
        "per_page": per_page,
        "unread_count": sum(1 for n in all_notifs if not n.get("is_read")),
    })


@notif_v2_bp.route("/api/unread-count", methods=["GET"])
@login_required
def api_unread_count():
    """Get unread notification count (for navbar badge)."""
    db = _db()
    email = session["user_id"]
    count = 0
    for _ in (
        db.collection("notifications_v2")
        .where(filter=FieldFilter("user_email", "==", email))
        .where(filter=FieldFilter("is_read", "==", False))
        .stream()
    ):
        count += 1
    return jsonify({"unread_count": count})


@notif_v2_bp.route("/api/mark-read", methods=["POST"])
@login_required
def api_mark_read():
    """Mark specific notification(s) as read."""
    db = _db()
    data = request.get_json(silent=True) or {}
    notif_ids = data.get("ids", [])
    if isinstance(notif_ids, str):
        notif_ids = [notif_ids]

    for nid in notif_ids:
        try:
            db.collection("notifications_v2").document(nid).update({"is_read": True})
        except Exception:
            pass

    return jsonify({"marked": len(notif_ids)})


@notif_v2_bp.route("/api/mark-all-read", methods=["POST"])
@login_required
def api_mark_all_read():
    """Mark all notifications as read."""
    db = _db()
    email = session["user_id"]
    batch = db.batch()
    count = 0
    for doc in (
        db.collection("notifications_v2")
        .where(filter=FieldFilter("user_email", "==", email))
        .where(filter=FieldFilter("is_read", "==", False))
        .stream()
    ):
        batch.update(doc.reference, {"is_read": True})
        count += 1
    if count:
        batch.commit()
    return jsonify({"marked": count})


@notif_v2_bp.route("/api/<notif_id>", methods=["DELETE"])
@login_required
def api_delete_notification(notif_id):
    """Delete a notification."""
    db = _db()
    try:
        db.collection("notifications_v2").document(notif_id).delete()
        return jsonify({"deleted": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@notif_v2_bp.route("/api/preferences", methods=["GET"])
@login_required
def api_get_preferences():
    """Get notification preferences."""
    db = _db()
    email = session["user_id"]
    doc = db.collection("notification_preferences").document(email).get()
    defaults = {
        "email_enabled": True,
        "push_enabled": True,
        "whatsapp_enabled": False,
        "event_reminders": True,
        "score_updates": True,
        "announcements": True,
        "marketing": False,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
    }
    if doc.exists:
        prefs = doc.to_dict()
        defaults.update(prefs)
    return jsonify(defaults)


@notif_v2_bp.route("/api/preferences", methods=["PUT"])
@login_required
def api_update_preferences():
    """Update notification preferences."""
    db = _db()
    email = session["user_id"]
    data = request.get_json(silent=True) or {}
    allowed = [
        "email_enabled", "push_enabled", "whatsapp_enabled",
        "event_reminders", "score_updates", "announcements", "marketing",
        "quiet_hours_start", "quiet_hours_end",
    ]
    updates = {k: v for k, v in data.items() if k in allowed}
    updates["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.collection("notification_preferences").document(email).set(updates, merge=True)
    return jsonify({"updated": True})


def _time_ago(iso_str: str) -> str:
    """Convert ISO timestamp to human-readable relative time."""
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = now - dt
        seconds = delta.total_seconds()
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{int(seconds // 60)}m ago"
        if seconds < 86400:
            return f"{int(seconds // 3600)}h ago"
        if seconds < 604800:
            return f"{int(seconds // 86400)}d ago"
        return dt.strftime("%b %d")
    except Exception:
        return ""
