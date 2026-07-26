"""
routes_coupons.py — Coupon Code System for SapthaEvent

Allows SPOCs and Admins to create discount coupons for events.
Supports percentage and fixed-amount discounts with usage limits.

Blueprint prefix: /coupons
"""
import logging
import datetime
import uuid
import secrets

from flask import Blueprint, request, session, jsonify
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from utils import login_required, role_required

logger = logging.getLogger(__name__)
coupons_bp = Blueprint("coupons", __name__, url_prefix="/coupons")


def _db():
    from app import db
    return db


def _generate_code(length: int = 8) -> str:
    """Generate a random coupon code like 'SAPTHA-X7K9'."""
    chars = secrets.token_hex(length // 2).upper()
    return f"SAPTHA-{chars}"


@coupons_bp.route("/create", methods=["POST"])
@role_required(["ClubSPOC", "Admin", "SuperAdmin"])
def create_coupon():
    """Create a new coupon code.

    Body: { event_id, discount_type, discount_value, max_uses, code?, valid_from?, valid_until? }
    """
    db = _db()
    data = request.get_json(silent=True) or {}

    event_id = data.get("event_id")
    if not event_id:
        return jsonify({"error": "event_id is required"}), 400

    discount_type = data.get("discount_type", "percentage")
    if discount_type not in ("percentage", "fixed"):
        return jsonify({"error": "discount_type must be 'percentage' or 'fixed'"}), 400

    discount_value = float(data.get("discount_value", 0))
    if discount_value <= 0:
        return jsonify({"error": "discount_value must be positive"}), 400
    if discount_type == "percentage" and discount_value > 100:
        return jsonify({"error": "Percentage discount cannot exceed 100%"}), 400

    code = (data.get("code") or _generate_code()).upper().strip()

    # Check uniqueness
    existing = (
        db.collection("coupons")
        .where(filter=FieldFilter("code", "==", code))
        .where(filter=FieldFilter("event_id", "==", event_id))
        .limit(1)
        .stream()
    )
    if any(True for _ in existing):
        return jsonify({"error": f"Coupon code '{code}' already exists for this event"}), 409

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    coupon_id = str(uuid.uuid4())
    coupon_data = {
        "id": coupon_id,
        "code": code,
        "event_id": event_id,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "max_uses": int(data.get("max_uses", 50)),
        "current_uses": 0,
        "valid_from": data.get("valid_from", now),
        "valid_until": data.get("valid_until", ""),
        "is_active": True,
        "created_by": session.get("user_id", ""),
        "created_at": now,
    }
    db.collection("coupons").document(coupon_id).set(coupon_data)

    return jsonify({"message": "Coupon created", "coupon": coupon_data}), 201


@coupons_bp.route("/validate", methods=["POST"])
@login_required
def validate_coupon():
    """Validate a coupon code and return discount amount.

    Body: { code, event_id, original_amount }
    """
    db = _db()
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").upper().strip()
    event_id = data.get("event_id", "")
    original_amount = float(data.get("original_amount", 0))

    if not code or not event_id:
        return jsonify({"valid": False, "error": "Code and event_id required"}), 400

    # Find coupon
    coupon = None
    for doc in (
        db.collection("coupons")
        .where(filter=FieldFilter("code", "==", code))
        .where(filter=FieldFilter("event_id", "==", event_id))
        .where(filter=FieldFilter("is_active", "==", True))
        .limit(1)
        .stream()
    ):
        coupon = doc.to_dict()
        coupon["_doc_id"] = doc.id

    if not coupon:
        return jsonify({"valid": False, "error": "Invalid or expired coupon code"})

    # Check usage limit
    if coupon["current_uses"] >= coupon["max_uses"]:
        return jsonify({"valid": False, "error": "Coupon usage limit reached"})

    # Check validity period
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if coupon.get("valid_until") and now > coupon["valid_until"]:
        return jsonify({"valid": False, "error": "Coupon has expired"})
    if coupon.get("valid_from") and now < coupon["valid_from"]:
        return jsonify({"valid": False, "error": "Coupon is not yet active"})

    # Calculate discount
    if coupon["discount_type"] == "percentage":
        discount = round(original_amount * coupon["discount_value"] / 100, 2)
    else:
        discount = min(coupon["discount_value"], original_amount)

    final_amount = max(0, original_amount - discount)

    return jsonify({
        "valid": True,
        "code": code,
        "discount_type": coupon["discount_type"],
        "discount_value": coupon["discount_value"],
        "discount_amount": discount,
        "original_amount": original_amount,
        "final_amount": final_amount,
    })


@coupons_bp.route("/apply", methods=["POST"])
@login_required
def apply_coupon():
    """Apply a coupon (increment usage count). Called after successful payment."""
    db = _db()
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").upper().strip()
    event_id = data.get("event_id", "")

    for doc in (
        db.collection("coupons")
        .where(filter=FieldFilter("code", "==", code))
        .where(filter=FieldFilter("event_id", "==", event_id))
        .limit(1)
        .stream()
    ):
        from google.cloud.firestore_v1 import Increment
        db.collection("coupons").document(doc.id).update({
            "current_uses": Increment(1),
        })
        return jsonify({"applied": True})

    return jsonify({"applied": False, "error": "Coupon not found"}), 404


@coupons_bp.route("/list/<event_id>", methods=["GET"])
@role_required(["ClubSPOC", "Admin", "SuperAdmin"])
def list_coupons(event_id):
    """List all coupons for an event."""
    db = _db()
    coupons = []
    for doc in (
        db.collection("coupons")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .stream()
    ):
        c = doc.to_dict()
        c["id"] = doc.id
        c["usage_pct"] = round(c.get("current_uses", 0) / max(c.get("max_uses", 1), 1) * 100, 1)
        coupons.append(c)

    return jsonify({"coupons": coupons, "total": len(coupons)})


@coupons_bp.route("/<coupon_id>/deactivate", methods=["PUT"])
@role_required(["ClubSPOC", "Admin", "SuperAdmin"])
def deactivate_coupon(coupon_id):
    """Deactivate a coupon."""
    db = _db()
    try:
        db.collection("coupons").document(coupon_id).update({"is_active": False})
        return jsonify({"message": "Coupon deactivated"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@coupons_bp.route("/analytics/<event_id>", methods=["GET"])
@role_required(["ClubSPOC", "Admin", "SuperAdmin"])
def coupon_analytics(event_id):
    """Get coupon usage analytics for an event."""
    db = _db()
    coupons = []
    total_discount = 0
    total_uses = 0

    for doc in (
        db.collection("coupons")
        .where(filter=FieldFilter("event_id", "==", event_id))
        .stream()
    ):
        c = doc.to_dict()
        uses = c.get("current_uses", 0)
        discount_per_use = c.get("discount_value", 0)
        if c.get("discount_type") == "fixed":
            total_discount += discount_per_use * uses
        total_uses += uses
        coupons.append({
            "code": c.get("code"),
            "type": c.get("discount_type"),
            "value": discount_per_use,
            "uses": uses,
            "max_uses": c.get("max_uses", 0),
            "is_active": c.get("is_active", False),
        })

    return jsonify({
        "event_id": event_id,
        "total_coupons": len(coupons),
        "total_uses": total_uses,
        "estimated_discount_given": total_discount,
        "coupons": coupons,
    })
