"""
routes_waitlist.py — Waitlist System with Auto-Promotion for SapthaEvent

Manages event waitlists with automatic promotion when spots open up.
Sends email/push notifications on promotion.

Blueprint prefix: /waitlist
"""
import logging
import datetime
import uuid

from flask import Blueprint, request, session, jsonify
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from utils import login_required, role_required, safe_int

logger = logging.getLogger(__name__)
waitlist_bp = Blueprint("waitlist", __name__, url_prefix="/waitlist")


def _db():
    from app import db
    return db


@waitlist_bp.route("/join/<event_id>", methods=["POST"])
@login_required
def join_waitlist(event_id):
    """Join the waitlist for a full event."""
    db = _db()
    email = session["user_id"]
    data = request.get_json(silent=True) or {}

    # Check event exists and is full
    ev_doc = db.collection("events").document(event_id).get()
    if not ev_doc.exists:
        return jsonify({"error": "Event not found"}), 404

    ev = ev_doc.to_dict()
    if ev.get("status") != "active":
        return jsonify({"error": "Event is not active"}), 400

    # Check not already on waitlist
    existing = (
        db.collection("waitlists")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .where(filter=FieldFilter("user_email", "==", email))
        .where(filter=FieldFilter("status", "==", "waiting"))
        .limit(1)
        .stream()
    )
    if any(True for _ in existing):
        return jsonify({"error": "Already on waitlist"}), 409

    # Check not already registered
    existing_reg = (
        db.collection("registrations")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .where(filter=FieldFilter("lead_email", "==", email))
        .limit(1)
        .stream()
    )
    if any(True for _ in existing_reg):
        return jsonify({"error": "Already registered for this event"}), 409

    # Calculate position
    current_count = 0
    for _ in (
        db.collection("waitlists")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .where(filter=FieldFilter("status", "==", "waiting"))
        .stream()
    ):
        current_count += 1

    wl_id = str(uuid.uuid4())
    wl_data = {
        "id": wl_id,
        "event_id": event_id,
        "email": email,
        "user_email": email,
        "name": data.get("name", session.get("name", "")),
        "phone": data.get("phone", ""),
        "position": current_count + 1,
        "status": "waiting",
        "joined_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db.collection("waitlists").document(wl_id).set(wl_data)

    # Notify user
    try:
        from routes_notifications_v2 import create_notification
        create_notification(
            db, user_email=email, notif_type="system_alert",
            title=f"Waitlisted for {ev.get('title', 'event')}",
            message=f"You are #{current_count + 1} on the waitlist. We'll notify you if a spot opens.",
            link=f"/event/{event_id}",
        )
    except Exception:
        pass

    return jsonify({
        "message": "Added to waitlist",
        "position": current_count + 1,
        "waitlist_id": wl_id,
    }), 201


@waitlist_bp.route("/status/<event_id>", methods=["GET"])
@login_required
def waitlist_status(event_id):
    """Check waitlist position."""
    db = _db()
    email = session["user_id"]

    for doc in (
        db.collection("waitlists")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .where(filter=FieldFilter("user_email", "==", email))
        .where(filter=FieldFilter("status", "==", "waiting"))
        .limit(1)
        .stream()
    ):
        wl = doc.to_dict()
        return jsonify({"on_waitlist": True, "position": wl.get("position", 0), "id": doc.id})

    return jsonify({"on_waitlist": False})


@waitlist_bp.route("/leave/<event_id>", methods=["DELETE"])
@login_required
def leave_waitlist(event_id):
    """Leave the waitlist."""
    db = _db()
    email = session["user_id"]

    for doc in (
        db.collection("waitlists")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .where(filter=FieldFilter("user_email", "==", email))
        .where(filter=FieldFilter("status", "==", "waiting"))
        .limit(1)
        .stream()
    ):
        db.collection("waitlists").document(doc.id).update({"status": "cancelled"})
        return jsonify({"message": "Removed from waitlist"})

    return jsonify({"error": "Not on waitlist"}), 404


@waitlist_bp.route("/promote/<event_id>", methods=["POST"])
@role_required(["ClubSPOC", "Admin", "Coordinator"])
def promote_next(event_id):
    """Manually promote the next person on the waitlist."""
    db = _db()
    result = auto_promote(db, event_id)
    if result:
        return jsonify({"message": f"Promoted: {result['user_email']}", "promoted": result})
    return jsonify({"message": "No one on the waitlist to promote"})


@waitlist_bp.route("/list/<event_id>", methods=["GET"])
@role_required(["ClubSPOC", "Admin", "Coordinator"])
def view_waitlist(event_id):
    """View the waitlist for an event."""
    db = _db()
    waitlist = []
    for doc in (
        db.collection("waitlists")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .where(filter=FieldFilter("status", "==", "waiting"))
        .order_by("position")
        .stream()
    ):
        wl = doc.to_dict()
        wl["id"] = doc.id
        waitlist.append(wl)
    return jsonify({"waitlist": waitlist, "total": len(waitlist)})


def auto_promote(db, event_id: str):
    """Auto-promote the next person on the waitlist.

    Called when a registration is cancelled. Creates a registration
    for the promoted user and sends them a notification.
    """
    # Find next in line
    for doc in (
        db.collection("waitlists")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .where(filter=FieldFilter("status", "==", "waiting"))
        .order_by("position")
        .limit(1)
        .stream()
    ):
        wl = doc.to_dict()
        email = wl.get("user_email") or wl.get("email", "")
        name = wl.get("name", "Participant")

        # Update waitlist status
        db.collection("waitlists").document(doc.id).update({
            "status": "promoted",
            "promoted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

        # Create registration
        ev_doc = db.collection("events").document(event_id).get()
        ev = ev_doc.to_dict() if ev_doc.exists else {}

        reg_data = wl.get("reg_data") or {}
        reg_id = reg_data.get("reg_id") or str(uuid.uuid4())
        if reg_data:
            reg_data.update({
                "status": "Confirmed",
                "payment_status": "unpaid" if ev.get("fee", 0) > 0 or ev.get("entry_fee", 0) > 0 else "free",
                "attendance": "Pending",
                "source": "waitlist_promotion",
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
        else:
            reg_data = {
                "reg_id": reg_id,
                "event_id": event_id,
                "event_title": ev.get("title", ""),
                "lead_name": name,
                "lead_email": email,
                "lead_phone": wl.get("phone", ""),
                "status": "Confirmed",
                "payment_status": "unpaid" if ev.get("fee", 0) > 0 or ev.get("entry_fee", 0) > 0 else "free",
                "attendance": "Pending",
                "source": "waitlist_promotion",
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        db.collection("registrations").document(reg_id).set(reg_data)

        # Increment count
        from google.cloud.firestore_v1 import Increment
        db.collection("events").document(event_id).update({
            "registration_count": Increment(1),
        })

        # Notify
        try:
            from routes_notifications_v2 import create_notification
            create_notification(
                db, user_email=email, notif_type="waitlist_promoted",
                title=f"You're in! {ev.get('title', 'Event')}",
                message="A spot opened up and you've been promoted from the waitlist!",
                link=f"/event/{event_id}",
            )
        except Exception:
            pass

        # Send email notification
        try:
            from tasks.email_tasks import send_generic_email_task
            send_generic_email_task.delay(
                to_email=email,
                subject=f"Great news! Your waitlist spot for {ev.get('title', 'Event')} is confirmed",
                body=(
                    f"Hi {name},\n\n"
                    f"A seat has opened up and you've been promoted from the waitlist for "
                    f"{ev.get('title', 'Event')}!\n\n"
                    f"Your registration is now confirmed.\n"
                    f"Registration ID: {reg_id}\n"
                    f"Event Date: {ev.get('date', '')}\n"
                    f"Venue: {ev.get('venue', 'SNPSU Campus')}\n\n"
                    f"See you there!\n— SapthaEvent Team"
                ),
            )
        except Exception:
            pass

        logger.info("Waitlist promotion: %s for event %s", email, event_id)
        return {"user_email": email, "registration_id": reg_id}

    return None
