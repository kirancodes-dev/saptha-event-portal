"""
routes_waitlist.py — Waitlist System with Auto-Promotion for SapthaEvent

Manages event waitlists with automatic promotion when spots open up.
Sends email/push notifications on promotion.

Blueprint prefix: /waitlist
"""
import logging
import datetime
import uuid
from typing import Optional

from flask import Blueprint, request, session, jsonify
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from utils import login_required, role_required, safe_int, venue_label

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
    from routes_forms import registration_closed
    if registration_closed(ev):              # the form's own rule (UPG-117), not only the old "active"
        return jsonify({"error": "Registration is closed for this event."}), 400

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
    from services_waitlist import place_in_line
    place = place_in_line(db, event_id, email) or current_count + 1   # join order (UPG-114)

    # Notify user
    try:
        from routes_notifications_v2 import create_notification
        create_notification(
            db, user_email=email, notif_type="system_alert",
            title=f"Waitlisted for {ev.get('title', 'event')}",
            message=f"You are #{place} on the waitlist. We'll notify you if a spot opens.",
            link=f"/event/{event_id}",
        )
    except Exception:
        pass

    return jsonify({
        "message": "Added to waitlist",
        "position": place,
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
        from services_waitlist import place_in_line
        return jsonify({"on_waitlist": True, "position": place_in_line(db, event_id, email), "id": doc.id})

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
    from services_waitlist import waiting
    db = _db()
    # In join order, each with their place now (UPG-114), not the place they joined at
    waitlist = [dict(wl, id=wl_id, position=place)
                for place, (wl_id, wl) in enumerate(waiting(db, event_id), start=1)]
    return jsonify({"waitlist": waitlist, "total": len(waitlist)})


def promotion_terms(ev: dict, reg_id: str, reg_data: Optional[dict] = None) -> dict:
    """How a waitlist promotion is recorded and announced (BLK-03).

    A paid event's seat is held as pending_payment with a pay link and is
    confirmed only after a verified payment; a free event is confirmed.
    Used by auto_promote and tasks.waitlist_tasks.promote_from_waitlist.
    An event with ticket types is paid when the chosen type costs something
    (UPG-155).
    """
    title = ev.get("title", "Event")
    is_paid = safe_int(ev.get("fee", 0)) > 0 or safe_int(ev.get("entry_fee", 0)) > 0
    import services_ticket_types as tt
    if tt.types_for(ev):
        ticket = tt.find(ev, (reg_data or {}).get("ticket_type_id", ""))
        members = (reg_data or {}).get("member_count") or len((reg_data or {}).get("members") or []) or 1
        is_paid = ticket is not None and tt.price(ticket, members) > 0
    pay_path = f"/payment/pay/{reg_id}"
    from utils_email import _base_url
    base_url = _base_url()
    if is_paid:
        return {
            "is_paid": True, "status": "pending_payment", "payment_status": "Pending",
            "notif_title": f"A spot opened: pay to confirm {title}",
            "notif_message": "A spot opened up for you. Pay the fee to confirm your registration.",
            "link": pay_path,
            "subject": f"A seat opened for {title}: pay to confirm",
            "email_line": f"Pay the fee to confirm your seat: {base_url}{pay_path}\n",
        }
    return {
        "is_paid": False, "status": "Confirmed", "payment_status": "Free",
        "notif_title": f"You're in! {title}",
        "notif_message": "A spot opened up and you've been promoted from the waitlist!",
        "link": f"/event/{ev.get('id', '')}" if ev.get("id") else "/participant/dashboard",
        "subject": f"Great news! Your waitlist spot for {title} is confirmed",
        "email_line": "Your registration is now confirmed.\n",
    }


def auto_promote(db, event_id: str):
    """Auto-promote the next person on the waitlist.

    Called when a registration is cancelled. Creates a registration
    for the promoted user and sends them a notification.
    """
    # The first in line by join order (UPG-112, UPG-114)
    from services_waitlist import waiting
    for wl_id, wl in waiting(db, event_id)[:1]:
        promoted = promote_entry(db, event_id, wl_id, wl)
        # Already registered another way: they don't need the seat; the next
        # person in line gets it (UPG-115)
        return promoted if promoted else auto_promote(db, event_id)
    return None


def promote_entry(db, event_id: str, wl_id: str, wl: dict):
    """Register this waitlist entry, as the first in line is (auto_promote),
    or as the SPOC chose it (UPG-230): a paid event holds the seat for
    payment, a free one is confirmed with a ticket; the person is told.
    None, with the entry marked already_registered, when they already
    have a registration for the event."""
    email = wl.get("user_email") or wl.get("email", "")
    name = wl.get("name", "Participant")

    # Update waitlist status
    db.collection("waitlists").document(wl_id).update({
        "status": "promoted",
        "promoted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })

    # Create registration
    ev_doc = db.collection("events").document(event_id).get()
    ev = ev_doc.to_dict() if ev_doc.exists else {}

    reg_data = wl.get("reg_data") or {}
    reg_id = reg_data.get("reg_id") or str(uuid.uuid4())
    terms = promotion_terms(dict(ev, id=event_id), reg_id, reg_data)
    status, payment_status = terms["status"], terms["payment_status"]
    if reg_data:
        reg_data.update({
            "reg_id": reg_id,
            "status": status,
            "payment_status": payment_status,
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
            "status": status,
            "payment_status": payment_status,
            "attendance": "Pending",
            "source": "waitlist_promotion",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    try:
        db.collection("registrations").document(reg_id).set(reg_data)
    except Exception as exc:
        from utils import is_active_duplicate
        if not is_active_duplicate(exc):
            raise
        db.collection("waitlists").document(wl_id).update({"status": "already_registered"})
        return None

    # The promoted seat counts against its ticket type (UPG-155); the
    # event's own seat limit already let them in
    import services_ticket_types as tt
    promoted_ticket = tt.find(ev, reg_data.get("ticket_type_id", ""))
    if promoted_ticket is not None:
        tt.take_seat(event_id, dict(promoted_ticket, seats=0))

    # Free promotions are confirmed immediately, so issue the same signed
    # ticket that a normal registration receives.  Paid promotions remain
    # pending payment and receive their ticket after payment is verified.
    if status == "Confirmed":
        from services_ticket import TicketService
        TicketService.issue_ticket(
            db,
            event_id=event_id,
            registration_id=reg_id,
            user_email=reg_data.get("lead_email") or email,
            lead_name=reg_data.get("lead_name") or name,
            ticket_type=(reg_data.get("ticket_type_name") or reg_data.get("ticket_tier")
                         or reg_data.get("ticket_type")
                         or "General"),
        )

    # Increment count
    try:
        from google.cloud.firestore_v1 import Increment
    except Exception:
        google = None
    db.collection("events").document(event_id).update({
        "registration_count": Increment(1),
    })

    # Notify
    try:
        from routes_notifications_v2 import create_notification
        create_notification(
            db, user_email=email, notif_type="waitlist_promoted",
            title=terms["notif_title"], message=terms["notif_message"],
            link=terms["link"],
        )
    except Exception:
        pass

    # Send email notification (not for a portal-only event: the notice above, UPG-195)
    import services_hackathon
    if services_hackathon.email_allowed(ev, 'waitlist'):
        try:
            from tasks.email_tasks import send_generic_email_task
            email_body = (
                f"Hi {name},\n\n"
                f"A seat has opened up and you've been promoted from the waitlist for "
                f"{ev.get('title', 'Event')}!\n\n"
                f"{terms['email_line']}"
                f"Registration ID: {reg_id}\n"
                f"Event Date: {ev.get('date', '')}\n"
                f"Venue: {venue_label(ev)}\n\n"
                f"See you there!\n— SapthaEvent Team"
            )
            send_generic_email_task.delay(
                to_email=email,
                subject=terms["subject"],
                body_text=email_body,
                body=email_body,
            )
        except Exception:
            pass

    logger.info("Waitlist promotion: %s for event %s", email, event_id)
    return {
        "user_email": email,
        "registration_id": reg_id,
        "reg_id": reg_id,
        "status": status,
    }
