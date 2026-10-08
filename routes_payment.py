import datetime
import hashlib
import hmac as _hmac  # alias to avoid shadowing module with local var
import json
import os
import time
from flask import (Blueprint, flash, jsonify, redirect, render_template, request, session)
from services_payments import (PaymentError, amount_inr, attach_registration, claim_order,
                               claim_paid_order, get_order, give_back_coupon_use, mark_unmatched,
                               record_order, release_payer_holds, server_price, simulation_enabled,
                               take_coupon_use)

COUPON_GONE = 'the coupon had no uses left when this late payment arrived'  # UPG-36
from utils import login_required, record_form_submission, safe_int

# What a payer sees when their money arrived but the registration couldn't be
# completed (UPG-30)
RECORDED_MESSAGE = ("Your payment is recorded, but we couldn't complete the registration (the event may be "
                    "full, or you may already be registered). The organisers will complete it or refund you; "
                    "you don't need to pay again.")

try:
    import razorpay
except ImportError:
    razorpay = None

try:
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    firestore = FieldFilter = None

try:
    from tasks.email_tasks import send_ticket_email_task, send_payment_receipt_email_task
except ImportError:
    def send_ticket_email_task(*a, **kw): pass
    def send_payment_receipt_email_task(*a, **kw): pass

try:
    from tasks.notification_tasks import send_ticket_whatsapp_task, send_payment_receipt_whatsapp_task
except ImportError:
    def send_ticket_whatsapp_task(*a, **kw): pass
    def send_payment_receipt_whatsapp_task(*a, **kw): pass

payment_bp = Blueprint('payment', __name__, url_prefix='/payment')

RAZORPAY_KEY_ID     = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')

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

def log_action(db_conn, action, details=""):
    try:
        from audit_logger import log_action as audit_log_action
        audit_log_action(action, details)
    except Exception:
        pass

def _rzp():
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# =========================================================
# 1a. CREATE RAZORPAY ORDER
# =========================================================
@payment_bp.route('/create_order', methods=['POST'])
def create_order():
    """Return a Razorpay order for the session's pending registration.

    The amount is computed on the server and the order is recorded
    (order ↔ event ↔ payer ↔ amount) so /verify can check it (BLK-03).
    """
    reg_data = session.get('pending_reg_data')
    if not reg_data:
        return jsonify({'error': 'No pending registration'}), 400

    body = request.get_json(silent=True) or {}
    event_id = str(reg_data.get('event_id') or body.get('event_id', ''))
    if body.get('event_id') and str(body['event_id']) != event_id:
        return jsonify({'error': 'This event does not match your registration'}), 400
    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        return jsonify({'error': 'Event not found'}), 404

    try:
        price = server_price(_db(), event_id, event_doc.to_dict() or {}, body.get('coupon', ''))
    except PaymentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    if price['amount_paise'] < 100:
        return jsonify({'error': 'The amount to pay must be at least ₹1'}), 400

    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        if simulation_enabled():
            return jsonify({'simulate': True, 'amount': price['amount_inr'], 'event_id': event_id,
                            'multiplier': price['multiplier'], 'reason': price['reason']})
        return jsonify({'error': 'Online payment is not configured. Please contact the organiser.'}), 503

    email = (reg_data.get('lead_email') or '').lower()
    coupon = price.get('coupon')
    if coupon:
        # Hold one use for this order, atomically; a retry gives back the
        # payer's earlier hold first (UPG-36)
        release_payer_holds(event_id, email, price['coupon_code'])
        if not take_coupon_use(event_id, price['coupon_code'], int(coupon.get('max_uses', 0) or 0),
                               int(coupon.get('current_uses', 0) or 0)):
            return jsonify({'error': 'Coupon usage limit reached'}), 400
    try:
        order = _rzp().order.create({  # type: ignore[union-attr]
            'amount':   price['amount_paise'],
            'currency': 'INR',
            'receipt':  f"reg_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}",
            'notes':    {'event_id': event_id, 'email': email},
        })
    except Exception:
        if coupon:
            give_back_coupon_use(event_id, price['coupon_code'])
        raise
    record_order(order['id'], event_id, email, price['amount_paise'], price['coupon_code'],
                 reg_data=dict(reg_data, event_id=event_id))  # the webhook completes from it (UPG-30)
    session['pending_reg_data'] = dict(reg_data, event_id=event_id)
    return jsonify({
        'order_id': order['id'],
        'key':      RAZORPAY_KEY_ID,
        'amount':   price['amount_paise'],
        'event_id': event_id,
        'name':     reg_data.get('lead_name', ''),
        'email':    email,
    })


# =========================================================
# 1b. VERIFY RAZORPAY PAYMENT
# =========================================================
@payment_bp.route('/verify', methods=['POST'])
def verify_payment():
    """Verify a Razorpay payment against the order this server recorded (BLK-03).

    Fails closed without keys; checks the signature AND that the order was
    created here for the session's pending event and payer; records the
    stored amount, never one from the request; a payment ID works once.
    """
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        return jsonify({'error': 'Online payment is not configured.'}), 503

    data = request.get_json(silent=True) or {}
    razorpay_order_id   = str(data.get('razorpay_order_id', ''))
    razorpay_payment_id = str(data.get('razorpay_payment_id', ''))
    razorpay_signature  = str(data.get('razorpay_signature', ''))
    if not (razorpay_order_id and razorpay_payment_id and razorpay_signature):
        return jsonify({'error': 'Missing payment details'}), 400

    expected = _hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not _hmac.compare_digest(expected, razorpay_signature):
        return jsonify({'error': 'Invalid signature'}), 400

    reg_data = session.get('pending_reg_data')
    if not reg_data:
        return jsonify({'error': 'Session expired'}), 400
    event_id = str(reg_data.get('event_id', ''))

    try:
        order = claim_order(razorpay_order_id, razorpay_payment_id, event_id,
                            reg_data.get('lead_email', ''))
    except PaymentError as exc:
        # The webhook may have finished this same payment first (UPG-30)
        done = get_order(razorpay_order_id)
        if (exc.status == 409 and done and done['payment_id'] == razorpay_payment_id
                and done['email'] == (reg_data.get('lead_email') or '').lower()):
            session.pop('pending_reg_data', None)
            if done['reg_id']:
                return jsonify({'redirect': _after_payment_url({'reg_id': done['reg_id'], 'email': done['email']})})
            return jsonify({'recorded': True, 'message': RECORDED_MESSAGE}), 202
        log_action(_db(), "PAYMENT_REJECTED",
                   f"Order {razorpay_order_id} / {razorpay_payment_id} for event {event_id}: {exc}")
        return jsonify({'error': str(exc)}), exc.status

    if order.get('coupon_over_limit'):  # paid after its coupon hold ran out, and none left (UPG-36)
        mark_unmatched(razorpay_order_id, COUPON_GONE)
        session.pop('pending_reg_data', None)
        return jsonify({'recorded': True, 'message': RECORDED_MESSAGE}), 202

    result = _complete_registration(
        event_id=event_id,
        reg_data=reg_data,
        payment_status='Paid',
        amount_paid=amount_inr(order['amount_paise']),
        razorpay_payment_id=razorpay_payment_id,
        razorpay_order_id=razorpay_order_id,
    )
    if 'error' in result:
        # Paid, but no registration: the order stays paid and appears on the
        # admin's payments page to complete or refund (UPG-30)
        mark_unmatched(razorpay_order_id, result['error'])
        log_action(_db(), "PAYMENT_UNMATCHED",
                   f"Paid order {razorpay_order_id} could not complete a registration: {result['error']}")
        session.pop('pending_reg_data', None)
        return jsonify({'recorded': True, 'message': RECORDED_MESSAGE}), 202
    attach_registration(razorpay_order_id, result['reg_id'])
    if order.get('coupon_code'):
        _use_coupon(event_id, order['coupon_code'])
    return jsonify({'redirect': _after_payment_url(result)})


def _use_coupon(event_id, code):
    try:
        for doc in (_db().collection('coupons')
                    .where(filter=FieldFilter('code', '==', code))
                    .where(filter=FieldFilter('event_id', '==', event_id))
                    .limit(1).stream()):
            _db().collection('coupons').document(doc.id).update({'current_uses': firestore.Increment(1)})
    except Exception as exc:
        log_action(_db(), "COUPON_USE_FAILED", f"{code} on {event_id}: {exc}")


# =========================================================
# 1. CHECKOUT PAGE
# =========================================================
@payment_bp.route('/checkout/<event_id>')
def checkout(event_id):
    reg_data = session.get('pending_reg_data')
    if not reg_data:
        flash("No pending registration found. Please register first.", "warning")
        return redirect('/')

    # Duplicate guard — catch it before showing payment UI
    email = reg_data.get('lead_email', '')
    if email:
        blocking, _ = _existing_registration(event_id, email, reg_data.get('reg_id', ''))
        if blocking is not None:
            session.pop('pending_reg_data', None)
            flash("You are already registered for this event. Here is your ticket.", "info")
            return redirect(f"/ticket/{blocking.id}")

    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/')

    event  = event_doc.to_dict()
    try:
        amount = server_price(_db(), event_id, event)['amount_inr']
    except PaymentError:
        amount = event.get('entry_fee', 0)
    user   = {
        'name':  reg_data.get('lead_name'),
        'email': reg_data.get('lead_email'),
    }

    return render_template('payment/checkout.html',
                            event=event,
                            event_id=event_id,
                            user=user,
                            amount=amount)


# =========================================================
# SHARED HELPER — write registration to Firestore + notify
# =========================================================
def _existing_registration(event_id, email, reg_id=''):
    """Return (blocking_doc, held_doc) for this payer and event.

    A registration held as pending_payment under the same reg_id (e.g. a
    waitlist promotion paid through /payment/pay) doesn't block payment.
    """
    for doc in (_db().collection('registrations')
                  .where(filter=FieldFilter('event_id', '==', event_id))
                  .where(filter=FieldFilter('lead_email', '==', email))
                  .limit(5).stream()):
        data = doc.to_dict() or {}
        held = (reg_id and (data.get('reg_id') == reg_id or doc.id == reg_id)
                and str(data.get('status', '')).lower() == 'pending_payment')
        if held:
            return None, doc
        return doc, None
    return None, None


def _complete_registration(event_id, reg_data, payment_status='Paid',
                            amount_paid=0, razorpay_payment_id='', razorpay_order_id=''):
    email  = reg_data.get('lead_email')
    name   = reg_data.get('lead_name')
    phone  = reg_data.get('lead_phone', '')
    reg_id = reg_data.get('reg_id') or f"REG-{int(time.time() * 1000)}"

    try:
        blocking, held = _existing_registration(event_id, email, reg_id)
        if blocking is not None:
            session.pop('pending_reg_data', None)
            return {'error': 'already_registered'}

        # The seat may have gone while they paid: never overbook (UPG-30). A
        # held (pending_payment) seat is already theirs.
        event_ref  = _db().collection('events').document(event_id)
        event_data = event_ref.get().to_dict() or {}
        max_cap = (safe_int((event_data.get('limits') or {}).get('max_participants', 0))
                   or safe_int(event_data.get('capacity', 0)))
        if held is None and max_cap and safe_int(event_data.get('registration_count', 0)) >= max_cap:
            return {'error': 'event_full'}

        reg_data.update({
            'reg_id':               reg_id,
            'status':               'Confirmed',
            'payment_status':       payment_status,
            'amount_paid':          amount_paid,
            'razorpay_payment_id':  razorpay_payment_id,
            'razorpay_order_id':    razorpay_order_id,
            'is_eliminated':        False,
            'current_round':        1,
        })
        _db().collection('registrations').document(reg_id).set(reg_data)
        if reg_data.get('form_answers'):
            record_form_submission(_db(), event_id, reg_id, email, name,
                                   reg_data['form_answers'])

        # Award +50 XP for registration
        try:
            from routes_gamification import award_xp
            award_xp(email, 50)
        except Exception as e:
            pass

        # Atomic increment — safe under concurrent registrations. A held
        # (pending_payment) seat was already counted when it was held.
        if held is None:
            event_ref.update({'registration_count': firestore.Increment(1)})

        event_title = event_data.get('title', 'Event')
        event_date  = event_data.get('date', '')
        venue       = event_data.get('venue', '')

        send_ticket_email_task.delay(
            to_email=email, name=name, event_title=event_title,
            reg_id=reg_id, event_date=event_date, venue=venue,
        )
        if str(payment_status).lower().startswith('paid') and float(amount_paid or 0) > 0:
            send_payment_receipt_email_task.delay(  # UPG-30
                to_email=email, name=name, event_title=event_title, amount=amount_paid,
                reg_id=reg_id, payment_id=razorpay_payment_id,
            )
        if phone:
            send_payment_receipt_whatsapp_task.delay(
                phone=phone, name=name, event_title=event_title,
                amount=str(amount_paid), reg_id=reg_id, payment_id=razorpay_payment_id,
            )
            send_ticket_whatsapp_task.delay(
                phone=phone, name=name, event_title=event_title,
                reg_id=reg_id, event_date=event_date, venue=venue,
            )

        # BLK-02: completing a payment never logs anyone in
        session.pop('pending_reg_data', None)

        log_action(_db(), "PAYMENT_CONFIRMED",
                   f"Registration {reg_id} confirmed for event {event_id} — ₹{amount_paid}")
        return {'reg_id': reg_id, 'email': email, 'event_title': event_title,
                'event_date': event_date, 'venue': venue}

    except Exception as exc:
        log_action(_db(), "PAYMENT_FAILED", f"Event {event_id}, email {email} — {exc}")
        return {'error': str(exc)}


def _after_payment_url(result):
    """The logged-in owner sees the ticket; anyone else the confirmation page."""
    if (session.get('user_id') or '').lower() == (result.get('email') or '').lower():
        return f"/ticket/{result['reg_id']}"
    session['reg_confirmed'] = {
        'reg_id':      result['reg_id'],
        'event_title': result.get('event_title', ''),
        'event_date':  result.get('event_date', ''),
        'venue':       result.get('venue', ''),
        'is_new_user': not session.get('user_id'),
        'user_email':  result.get('email', ''),
    }
    return '/registration/confirmed'


# =========================================================
# 1c. RAZORPAY WEBHOOK (UPG-30)
# =========================================================
@payment_bp.route('/webhook/razorpay', methods=['POST'])
def razorpay_webhook():
    """Razorpay's server-to-server events. payment.captured completes the
    registration stored with the order, once, whether or not the payer's
    browser came back to /payment/verify. Signed with RAZORPAY_WEBHOOK_SECRET."""
    secret = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
    if not secret:
        return jsonify({'error': 'Webhook not configured'}), 503
    body = request.get_data()
    expected = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not _hmac.compare_digest(expected, request.headers.get('X-Razorpay-Signature', '')):
        return jsonify({'error': 'Invalid signature'}), 400
    try:
        event = json.loads(body or b'{}')
        payment = event['payload']['payment']['entity'] if event.get('event') == 'payment.captured' else None
    except (ValueError, KeyError, TypeError):
        return jsonify({'error': 'Malformed event'}), 400
    if not payment:
        return jsonify({'status': 'ignored'})

    order_id, payment_id = str(payment.get('order_id', '')), str(payment.get('id', ''))
    order = claim_paid_order(order_id, payment_id, safe_int(payment.get('amount')))
    if order is None:  # unknown, already completed by the browser, or the amount differs
        return jsonify({'status': 'nothing to do'})
    if order.get('coupon_over_limit'):  # UPG-36
        mark_unmatched(order_id, COUPON_GONE)
        return jsonify({'status': 'recorded'})
    if not order['reg_data']:
        mark_unmatched(order_id, 'no registration details were stored with the order')
        return jsonify({'status': 'recorded'})
    result = _complete_registration(order['event_id'], dict(order['reg_data']), 'Paid',
                                    amount_inr(order['amount_paise']), payment_id, order_id)
    if 'error' in result:
        mark_unmatched(order_id, result['error'])
        log_action(_db(), "PAYMENT_UNMATCHED", f"Webhook: paid order {order_id} could not complete: {result['error']}")
        return jsonify({'status': 'recorded'})
    attach_registration(order_id, result['reg_id'])
    if order.get('coupon_code'):
        _use_coupon(order['event_id'], order['coupon_code'])
    log_action(_db(), "PAYMENT_WEBHOOK_COMPLETED", f"Order {order_id} completed registration {result['reg_id']}")
    return jsonify({'status': 'completed', 'reg_id': result['reg_id']})


# =========================================================
# 2. PROCESS PAYMENT (simulation fallback — no Razorpay keys)
# =========================================================
@payment_bp.route('/process', methods=['POST'])
def process_payment():
    """Simulated payment for development: only with PAYMENT_SIMULATION=true,
    never in production; the amount is always computed on the server."""
    if not simulation_enabled():
        return "Payment simulation is disabled.", 403

    reg_data = session.get('pending_reg_data')
    if not reg_data:
        flash("Session expired. Please start registration again.", "danger")
        return redirect('/')

    event_id = str(reg_data.get('event_id') or request.form.get('event_id', '').strip())
    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/')
    price = server_price(_db(), event_id, event_doc.to_dict() or {})

    result = _complete_registration(
        event_id=event_id,
        reg_data=reg_data,
        payment_status='Paid (Simulation)',
        amount_paid=amount_inr(price['amount_paise']),
    )
    if result.get('error') == 'already_registered':
        flash("You are already registered for this event.", "warning")
        return redirect('/')
    if 'error' in result:
        flash(f"Payment failed: {result['error']}", "danger")
        return redirect('/')
    return redirect(_after_payment_url(result))


# =========================================================
# 3. PAY FOR A HELD REGISTRATION (e.g. promoted from the waitlist)
# =========================================================
@payment_bp.route('/pay/<reg_id>')
@login_required
def pay_pending(reg_id):
    doc = _db().collection('registrations').document(reg_id).get()
    reg = doc.to_dict() if doc.exists else None
    if not reg or (reg.get('lead_email') or '').lower() != (session.get('user_id') or '').lower():
        flash("Registration not found.", "warning")
        return redirect('/participant/dashboard')
    if str(reg.get('status', '')).lower() != 'pending_payment':
        flash("This registration doesn't need a payment.", "info")
        return redirect(f"/ticket/{reg_id}")
    import json as _json
    pending = _json.loads(_json.dumps(reg, default=str))
    pending['reg_id'] = reg.get('reg_id') or reg_id
    session['pending_reg_data'] = pending
    return redirect(f"/payment/checkout/{reg.get('event_id')}")
