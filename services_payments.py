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
import json
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
        'coupon':       coupon,
        'multiplier':   multiplier,
        'reason':       reason,
    }


# ── Coupon uses (UPG-36) ───────────────────────────────────────────────────
# An order with a coupon holds one use from the moment it's created. An
# unpaid order lets go of it after COUPON_HOLD_MINUTES, so a checkout that's
# abandoned doesn't block the last use for long.

def coupon_hold() -> datetime.timedelta:
    return datetime.timedelta(minutes=int(os.environ.get('COUPON_HOLD_MINUTES', '30') or 30))


def _coupon_key(event_id: str, code: str) -> str:
    return f"{event_id}:{(code or '').upper()}"


def take_coupon_use(event_id: str, code: str, max_uses: int, recorded_uses: int = 0) -> bool:
    """Take one use if one is free. One conditional UPDATE, so it's race-free.
    The counter starts at the uses the coupon already records."""
    from db_pg import get_session
    from models_pg import CouponUse
    release_expired_holds(event_id, code)
    key = _coupon_key(event_id, code)
    try:
        with get_session() as s:
            if s.get(CouponUse, key) is None:
                s.add(CouponUse(key=key, used=int(recorded_uses or 0)))
    except IntegrityError:
        pass  # another checkout created it first
    with get_session() as s:
        result = s.execute(update(CouponUse).where(CouponUse.key == key, CouponUse.used < int(max_uses))
                           .values(used=CouponUse.used + 1))
        return result.rowcount == 1


def give_back_coupon_use(event_id: str, code: str) -> None:
    from db_pg import get_session
    from models_pg import CouponUse
    with get_session() as s:
        s.execute(update(CouponUse).where(CouponUse.key == _coupon_key(event_id, code), CouponUse.used > 0)
                  .values(used=CouponUse.used - 1))


def release_payer_holds(event_id: str, email: str, code: str) -> None:
    """A payer starting checkout again gives back the use their earlier,
    unpaid order held, so retries don't hold two (UPG-36)."""
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        mine = [o.id for o in s.query(PaymentOrder.id).filter(
            PaymentOrder.event_id == str(event_id), PaymentOrder.email == (email or '').lower(),
            PaymentOrder.coupon_code == (code or '').upper(), PaymentOrder.status == 'created')]
    for order_id in mine:
        with get_session() as s:
            won = s.execute(update(PaymentOrder).where(PaymentOrder.id == order_id, PaymentOrder.status == 'created')
                            .values(status='replaced')).rowcount == 1
        if won:
            give_back_coupon_use(event_id, code)


def release_expired_holds(event_id: str, code: str) -> int:
    """Unpaid orders older than the hold give their coupon use back, each once."""
    from db_pg import get_session
    from models_pg import PaymentOrder
    cutoff = datetime.datetime.now(datetime.timezone.utc) - coupon_hold()
    with get_session() as s:
        stale = [o.id for o in s.query(PaymentOrder.id).filter(
            PaymentOrder.event_id == str(event_id), PaymentOrder.coupon_code == (code or '').upper(),
            PaymentOrder.status == 'created', PaymentOrder.created_at < cutoff)]
    released = 0
    for order_id in stale:
        with get_session() as s:
            result = s.execute(update(PaymentOrder).where(PaymentOrder.id == order_id, PaymentOrder.status == 'created')
                               .values(status='expired'))
            won = result.rowcount == 1
        if won:
            give_back_coupon_use(event_id, code)
            released += 1
    return released


def amount_inr(amount_paise: int):
    rupees = amount_paise / 100
    return int(rupees) if rupees == int(rupees) else rupees


# ── Orders ─────────────────────────────────────────────────────────────────

def record_order(order_id: str, event_id: str, email: str, amount_paise: int, coupon_code: str = '',
                 reg_data: Optional[dict] = None) -> None:
    """Record the order, and the registration it pays for, so the webhook can
    complete it if the browser never comes back (UPG-30)."""
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        s.add(PaymentOrder(id=order_id, event_id=str(event_id), email=email.lower(),
                           amount_paise=int(amount_paise), coupon_code=(coupon_code or '').upper() or None,
                           reg_data_json=json.dumps(reg_data, default=str) if reg_data else None))


def _order_dict(order) -> dict:
    return {
        'id': order.id, 'event_id': order.event_id, 'email': order.email,
        'amount_paise': order.amount_paise, 'coupon_code': order.coupon_code or '',
        'status': order.status, 'payment_id': order.payment_id or '', 'reg_id': order.reg_id or '',
        'created_at': order.created_at, 'paid_at': order.paid_at,
        'reg_data': json.loads(order.reg_data_json) if order.reg_data_json else {},
        'failure_reason': order.failure_reason or '', 'refund_id': order.refund_id or '',
        'refunded_at': order.refunded_at, 'refunded_by': order.refunded_by or '',
    }


def get_order(order_id: str) -> Optional[dict]:
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        order = s.get(PaymentOrder, order_id) if order_id else None
        return _order_dict(order) if order else None


def all_orders() -> list:
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        return [_order_dict(o) for o in s.query(PaymentOrder).order_by(PaymentOrder.created_at).all()]


def unmatched_orders() -> list:
    """Paid orders with no registration: money taken, nothing to show for it (UPG-30)."""
    return [o for o in all_orders() if o['status'] == 'paid' and not o['reg_id']]


def mark_unmatched(order_id: str, reason: str) -> None:
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        s.execute(update(PaymentOrder).where(PaymentOrder.id == order_id).values(failure_reason=reason[:500]))


def claim_paid_order(order_id: str, payment_id: str, amount_paise: int) -> Optional[dict]:
    """The webhook's claim: mark a recorded order paid, if Razorpay's amount
    matches and nobody claimed it yet. None when there's nothing to do."""
    from db_pg import get_session
    from models_pg import PaymentOrder
    order = get_order(order_id)
    if order is None or order['status'] not in ('created', 'expired') or int(amount_paise) != order['amount_paise']:
        return None
    was_expired = order['status'] == 'expired'
    try:
        with get_session() as s:
            result = s.execute(
                update(PaymentOrder)
                .where(PaymentOrder.id == order_id, PaymentOrder.status.in_(('created', 'expired')))
                .values(status='paid', payment_id=payment_id,
                        paid_at=datetime.datetime.now(datetime.timezone.utc)))
            if result.rowcount != 1:
                return None
    except IntegrityError:
        return None
    claimed = get_order(order_id)
    claimed['coupon_over_limit'] = _late_coupon_over_limit(
        order['event_id'], {'was_expired': was_expired, 'coupon_code': order['coupon_code']})
    return claimed


def start_refund(order_id: str) -> Optional[dict]:
    """Move a paid order with no registration to 'refunding', once; None if
    it isn't one (already refunded, has a registration, unknown)."""
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        result = s.execute(update(PaymentOrder)
                           .where(PaymentOrder.id == order_id, PaymentOrder.status == 'paid',
                                  PaymentOrder.reg_id.is_(None))
                           .values(status='refunding'))
        if result.rowcount != 1:
            return None
    return get_order(order_id)


def finish_refund(order_id: str, refund_id: str, by: str) -> None:
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        s.execute(update(PaymentOrder).where(PaymentOrder.id == order_id).values(
            status='refunded', refund_id=refund_id, refunded_by=by,
            refunded_at=datetime.datetime.now(datetime.timezone.utc)))


def undo_refund(order_id: str) -> None:
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        s.execute(update(PaymentOrder).where(PaymentOrder.id == order_id, PaymentOrder.status == 'refunding')
                  .values(status='paid'))


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
        if order.status not in ('created', 'expired'):
            raise PaymentError('This payment has already been used.', 409)
        snapshot = {'amount_paise': order.amount_paise, 'coupon_code': order.coupon_code or '',
                    'was_expired': order.status == 'expired'}

    try:
        with get_session() as s:
            result = s.execute(
                update(PaymentOrder)
                .where(PaymentOrder.id == order_id, PaymentOrder.status.in_(('created', 'expired')))
                .values(status='paid', payment_id=payment_id,
                        paid_at=datetime.datetime.now(datetime.timezone.utc))
            )
            if result.rowcount != 1:
                raise PaymentError('This payment has already been used.', 409)
    except IntegrityError:
        raise PaymentError('This payment has already been used.', 409)
    snapshot['coupon_over_limit'] = _late_coupon_over_limit(event_id, snapshot)
    return snapshot


def _late_coupon_over_limit(event_id: str, order: dict) -> bool:
    """An order paid after its coupon hold ran out takes a use again; True
    when none is free, so the payment is kept for the admin instead (UPG-36)."""
    if not (order.get('was_expired') and order.get('coupon_code')):
        return False
    coupon = None
    try:
        from models import db
        from google.cloud.firestore_v1.base_query import FieldFilter
        for doc in (db.collection('coupons').where(filter=FieldFilter('code', '==', order['coupon_code']))
                    .where(filter=FieldFilter('event_id', '==', str(event_id))).limit(1).stream()):
            coupon = doc.to_dict() or {}
    except Exception:
        coupon = None
    if not coupon:
        return True
    return not take_coupon_use(event_id, order['coupon_code'], int(coupon.get('max_uses', 0) or 0),
                               int(coupon.get('current_uses', 0) or 0))


def attach_registration(order_id: str, reg_id: str) -> None:
    from db_pg import get_session
    from models_pg import PaymentOrder
    with get_session() as s:
        s.execute(update(PaymentOrder).where(PaymentOrder.id == order_id).values(reg_id=reg_id))
