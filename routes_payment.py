import hashlib
import hmac as _hmac  # alias to avoid shadowing module with local var
import os
import time
import datetime

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
    from tasks.email_tasks import send_ticket_email_task
except ImportError:
    def send_ticket_email_task(*a, **kw): pass

try:
    from tasks.notification_tasks import send_ticket_whatsapp_task, send_payment_receipt_whatsapp_task
except ImportError:
    def send_ticket_whatsapp_task(*a, **kw): pass
    def send_payment_receipt_whatsapp_task(*a, **kw): pass

payment_bp = Blueprint('payment', __name__, url_prefix='/payment')

RAZORPAY_KEY_ID     = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')

def _rzp():
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# =========================================================
# 1a. CREATE RAZORPAY ORDER
# =========================================================
@payment_bp.route('/create_order', methods=['POST'])
def create_order():
    """Return a Razorpay order_id + key for the frontend to open the checkout popup."""
    reg_data = session.get('pending_reg_data')
    if not reg_data:
        return jsonify({'error': 'No pending registration'}), 400

    event_id = request.json.get('event_id', '')
    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        return jsonify({'error': 'Event not found'}), 404

    from routes_dynamic_pricing import calculate_surge_price
    base_price = float(event_doc.to_dict().get('entry_fee', 0) or 0)
    amount_inr, multiplier, reason = calculate_surge_price(event_id, base_price)
    amount_paise = int(amount_inr * 100)  # Razorpay uses paise

    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        # Keys not configured — fall through to simulation
        return jsonify({'simulate': True, 'amount': amount_inr, 'event_id': event_id, 'multiplier': multiplier, 'reason': reason})

    order = _rzp().order.create({  # type: ignore[union-attr]
        'amount':   amount_paise,
        'currency': 'INR',
        'receipt':  f"reg_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}",
        'notes':    {'event_id': event_id, 'email': reg_data.get('lead_email', '')},
    })
    return jsonify({
        'order_id': order['id'],
        'key':      RAZORPAY_KEY_ID,
        'amount':   amount_paise,
        'event_id': event_id,
        'name':     reg_data.get('lead_name', ''),
        'email':    reg_data.get('lead_email', ''),
    })


# =========================================================
# 1b. VERIFY RAZORPAY PAYMENT
# =========================================================
@payment_bp.route('/verify', methods=['POST'])
def verify_payment():
    """Verify Razorpay signature and complete registration."""
    data = request.json or {}
    razorpay_order_id   = data.get('razorpay_order_id', '')
    razorpay_payment_id = data.get('razorpay_payment_id', '')
    razorpay_signature  = data.get('razorpay_signature', '')
    event_id            = data.get('event_id', '')

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

    amount = data.get('amount_inr', 0)
    result = _complete_registration(
        event_id=event_id,
        reg_data=reg_data,
        payment_status='Paid',
        amount_paid=int(amount),
        razorpay_payment_id=razorpay_payment_id,
    )
    if 'error' in result:
        return jsonify(result), 400
    return jsonify({'redirect': f"/ticket/{result['reg_id']}"})


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
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
        except Exception:
            google = None
        existing = list(
            _db().collection('registrations')
              .where(filter=FieldFilter('event_id', '==', event_id))
              .where(filter=FieldFilter('lead_email', '==', email))
              .limit(1).stream()
        )
        if existing:
            session.pop('pending_reg_data', None)
            flash("You are already registered for this event. Here is your ticket.", "info")
            return redirect(f"/ticket/{existing[0].id}")

    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/')

    event  = event_doc.to_dict()
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
def _complete_registration(event_id, reg_data, payment_status='Paid',
                            amount_paid=0, razorpay_payment_id=''):
    email  = reg_data.get('lead_email')
    name   = reg_data.get('lead_name')
    phone  = reg_data.get('lead_phone', '')
    reg_id = reg_data.get('reg_id') or f"REG-{int(time.time() * 1000)}"

    try:
        existing = list(
            _db().collection('registrations')
              .where(filter=FieldFilter('event_id', '==', event_id))
              .where(filter=FieldFilter('lead_email', '==', email))
              .limit(1).stream()
        )
        if existing:
            session.pop('pending_reg_data', None)
            return {'error': 'already_registered'}

        reg_data.update({
            'reg_id':               reg_id,
            'status':               'Confirmed',
            'payment_status':       payment_status,
            'amount_paid':          amount_paid,
            'razorpay_payment_id':  razorpay_payment_id,
            'is_eliminated':        False,
            'current_round':        1,
        })
        _db().collection('registrations').document(reg_id).set(reg_data)

        # Award +50 XP for registration
        try:
            from routes_gamification import award_xp
            award_xp(email, 50)
        except Exception as e:
            pass

        event_ref  = _db().collection('events').document(event_id)
        event_data = event_ref.get().to_dict() or {}
        # Atomic increment — safe under concurrent registrations
        event_ref.update({'registration_count': firestore.Increment(1)})

        event_title = event_data.get('title', 'Event')
        event_date  = event_data.get('date', '')
        venue       = event_data.get('venue', '')

        send_ticket_email_task.delay(
            to_email=email, name=name, event_title=event_title,
            reg_id=reg_id, event_date=event_date, venue=venue,
        )
        if phone:
            send_payment_receipt_whatsapp_task.delay(
                phone=phone, name=name, event_title=event_title,
                amount=str(amount_paid), reg_id=reg_id,
            )
            send_ticket_whatsapp_task.delay(
                phone=phone, name=name, event_title=event_title,
                reg_id=reg_id, event_date=event_date, venue=venue,
            )

        session.pop('pending_reg_data', None)
        session['user_id']  = email
        session['name']     = name
        session['role']     = 'Student'
        session['category'] = 'General'

        log_action(_db(), "PAYMENT_CONFIRMED",
                   f"Registration {reg_id} confirmed for event {event_id} — ₹{amount_paid}")
        return {'reg_id': reg_id}

    except Exception as exc:
        log_action(_db(), "PAYMENT_FAILED", f"Event {event_id}, email {email} — {exc}")
        return {'error': str(exc)}


# =========================================================
# 2. PROCESS PAYMENT (simulation fallback — no Razorpay keys)
# =========================================================
@payment_bp.route('/process', methods=['POST'])
def process_payment():
    event_id = request.form.get('event_id', '').strip()
    amount   = int(request.form.get('amount', '0') or 0)

    reg_data = session.get('pending_reg_data')
    if not reg_data:
        flash("Session expired. Please start registration again.", "danger")
        return redirect('/')

    result = _complete_registration(
        event_id=event_id,
        reg_data=reg_data,
        payment_status='Paid (Simulation)',
        amount_paid=amount,
    )
    if result.get('error') == 'already_registered':
        flash("You are already registered for this event.", "warning")
        return redirect('/')
    if 'error' in result:
        flash(f"Payment failed: {result['error']}", "danger")
        return redirect('/')
    return redirect(f"/ticket/{result['reg_id']}")
