# routes_dynamic_pricing.py — Surge Pricing & Dynamic Ticket Engine Blueprint
import logging
from flask import Blueprint, jsonify
from google.cloud.firestore_v1.base_query import FieldFilter

dynamic_pricing_bp = Blueprint('dynamic_pricing', __name__, url_prefix='/api/pricing')
logger = logging.getLogger(__name__)

def _db():
    try:
        import app as app_module
        if hasattr(app_module, 'db') and app_module.db is not None:
            return app_module.db
    except Exception:
        pass
    try:
        from models import db
        return db
    except Exception:
        return None

def calculate_surge_price(event_id: str, base_price: float) -> tuple:
    """
    Computes ticket entry fee with dynamic surge multiplier based on registration capacity limits.
    Returns (surge_price, multiplier, reason)
    """
    db_conn = _db()
    if not db_conn:
        return base_price, 1.0, "Database unavailable"

    try:
        event_doc = db_conn.collection('events').document(event_id).get()
        if not event_doc.exists:
            return base_price, 1.0, "Event not found"

        event = event_doc.to_dict()
        limits = event.get('limits', {})
        max_p = float(limits.get('max_participants', 0) or 0)
        
        # Get registration count
        reg_count = float(event.get('registration_count', 0) or 0)
        if reg_count == 0 and max_p > 0:
            # backup count query
            regs = db_conn.collection('registrations').where(filter=FieldFilter('event_id', '==', event_id)).stream()
            reg_count = float(len(list(regs)))

        if max_p <= 0:
            return base_price, 1.0, "Unlimited capacity"

        capacity_ratio = reg_count / max_p
        multiplier = 1.0
        reason = "Standard Price"

        if capacity_ratio >= 0.8:
            multiplier = 1.5
            reason = "High Demand Surge (80%+ Filled)"
        elif capacity_ratio >= 0.6:
            multiplier = 1.25
            reason = "Moderate Demand Surge (60%+ Filled)"
        elif capacity_ratio >= 0.4:
            multiplier = 1.1
            reason = "Early Demand Rise (40%+ Filled)"

        surge_price = round(base_price * multiplier, 2)
        return surge_price, multiplier, reason
    except Exception as exc:
        logger.error("Surge calculation error: %s", exc)
        return base_price, 1.0, "Default pricing"

@dynamic_pricing_bp.route('/<event_id>')
def get_dynamic_price(event_id):
    db_conn = _db()
    if not db_conn:
        return jsonify({'success': False, 'error': 'Database connection unavailable'}), 500

    try:
        doc = db_conn.collection('events').document(event_id).get()
        if not doc.exists:
            return jsonify({'success': False, 'error': 'Event not found'}), 404

        event = doc.to_dict()
        base_price = float(event.get('entry_fee', 0) or 0)
        
        surge_price, mult, reason = calculate_surge_price(event_id, base_price)
        return jsonify({
            'success': True,
            'event_id': event_id,
            'base_price': base_price,
            'surge_price': surge_price,
            'multiplier': mult,
            'reason': reason
        })
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500
