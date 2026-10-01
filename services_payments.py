"""
services_payments.py — server-side pricing and Razorpay order records (BLK-03).

  * The price is always computed here: event fee, then a coupon if one is
    applied, then dynamic pricing. An amount sent by the browser is ignored.
  * create_order records order ↔ event ↔ payer ↔ amount in payment_orders;
    verification accepts only a recorded order for the same event and payer,
    and a payment ID can be used once (unique column).
  * The simulated payment path exists only when PAYMENT_SIMULATION=true and
    never in production.
"""
import datetime
import os
from typing import Optional, Tuple

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError


class PaymentError(Exception):
    """Raised when an order can't be accepted. ``status`` is the HTTP code."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def simulation_enabled() -> bool:
    if os.environ.get('FLASK_ENV', '').strip().lower() == 'production':
        return False
    return os.environ.get('PAYMENT_SIMULATION', '').strip().lower() in ('1', 'true', 'yes')


# ── Coupons ────────────────────────────────────────────────────────────────

def find_valid_coupon(db, code: str, event_id: str) -> Tuple[Optional[dict], str]:
    """Return (coupon, error). The coupon dict carries its document id as _doc_id."""
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
    except ImportError:
        FieldFilter = None  # noqa: N806
    code = (code or '').upper().strip()
    if not code or not event_id:
        return None, 'Code and event_id required'
    coupon = None
    for doc in (
        db.collection('coupons')
        .where(filter=FieldFilter('code', '==', code))
        .where(filter=FieldFilter('event_id', '==', event_id))
        .where(filter=FieldFilter('is_active', '==', True))
        .limit(1)
        .stream()
    ):
        coupon = doc.to_dict()
        coupon['_doc_id'] = doc.id
    if not coupon:
        return None, 'Invalid or expired coupon code'
    if coupon.get('current_uses', 0) >= coupon.get('max_uses', 0):
        return None, 'Coupon usage limit reached'
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if coupon.get('valid_until') and now > coupon['valid_until']:
        return None, 'Coupon has expired'
    if coupon.get('valid_from') and now < coupon['valid_from']:
        return None, 'Coupon is not yet active'
    return coupon, ''


def coupon_discount(coupon: dict, amount: float) -> float:
    if coupon.get('discount_type') == 'percentage':
        return round(amount * float(coupon.get('discount_value', 0)) / 100, 2)
    return min(float(coupon.get('discount_value', 0)), amount)


# ── Price ──────────────────────────────────────────────────────────────────

def server_price(db, event_id: str, event_data: dict, coupon_code: str = '') -> dict:
    """The amount to charge, computed only from server-side data."""
    from routes_dynamic_pricing import calculate_surge_price

    fee = float(event_data.get('entry_fee', 0) or 0)
    discount, coupon = 0.0, None
    if coupon_code:
        coupon, error = find_valid_coupon(db, coupon_code, event_id)
        if not coupon:
            raise PaymentError(error)
        discount = coupon_discount(coupon, fee)
    after_coupon = max(0.0, fee - discount)
    amount, multiplier, reason = calculate_surge_price(event_id, after_coupon)
    amount = round(float(amount), 2)
    return {
        'amount_inr':   amount,
        'amount_paise': int(round(amount * 100)),
        'fee':          fee,
        'discount':     discount,
        'coupon_code':  coupon.get('code', '') if coupon else '',
        'multiplier':   multiplier,
        'reason':       reason,
    }


def amount_inr(amount_paise: int):
    rupees = amount_paise / 100
    return int(rupees) if rupees == int(rupees) else rupees


# ── Orders ─────────────────────────────────────────────────────────────────

def record_order(order_id: str, event_id: str, email: str, amount_paise: int, coupon_code: str = '') -> None:
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        s.add(PaymentOrder(id=order_id, event_id=str(event_id), email=email.lower(),
                           amount_paise=int(amount_paise), coupon_code=coupon_code or None))


def claim_order(order_id: str, payment_id: str, event_id: str, email: str) -> dict:
    """Mark a recorded order paid by payment_id, exactly once.

    The order must have been created by this server for the same event and
    payer. Raises PaymentError (400 mismatch, 409 already used).
    """
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        order = s.get(PaymentOrder, order_id)
        if (order is None or order.event_id != str(event_id)
                or order.email != (email or '').lower()):
            raise PaymentError('This payment does not match your registration.', 400)
        if order.status != 'created':
            raise PaymentError('This payment has already been used.', 409)
        snapshot = {'amount_paise': order.amount_paise, 'coupon_code': order.coupon_code or ''}

    try:
        with get_session() as s:
            result = s.execute(
                update(PaymentOrder)
                .where(PaymentOrder.id == order_id, PaymentOrder.status == 'created')
                .values(status='paid', payment_id=payment_id,
                        paid_at=datetime.datetime.now(datetime.timezone.utc))
            )
            if result.rowcount != 1:
                raise PaymentError('This payment has already been used.', 409)
    except IntegrityError:
        raise PaymentError('This payment has already been used.', 409)
    return snapshot


def attach_registration(order_id: str, reg_id: str) -> None:
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        s.execute(update(PaymentOrder).where(PaymentOrder.id == order_id).values(reg_id=reg_id))
