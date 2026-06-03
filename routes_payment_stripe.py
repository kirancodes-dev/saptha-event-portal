# routes_payment_stripe.py — Stripe payment integration blueprint
# Python 3.9 compatible

import os
import time
import datetime
import logging
from flask import Blueprint, request, jsonify, session, redirect, url_for
from utils import log_action
from routes_payment import _complete_registration

logger = logging.getLogger(__name__)
stripe_bp = Blueprint('stripe_payment', __name__, url_prefix='/payment/stripe')

def _db():
    from app import db
    return db

# Stripe Keys
STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

try:
    import stripe
    stripe.api_key = STRIPE_API_KEY
except ImportError:
    stripe = None
    logger.warning("stripe library not installed. Payment gateway runs in simulation mode.")


@stripe_bp.route('/create_session', methods=['POST'])
def create_session():
    """Create a Stripe Checkout Session for event payment."""
    reg_data = session.get('pending_reg_data')
    if not reg_data:
        return jsonify({'error': 'No pending registration'}), 400

    event_id = request.json.get('event_id', '')
    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        return jsonify({'error': 'Event not found'}), 404

    event_data = event_doc.to_dict()
    amount = float(event_data.get('entry_fee', 0))
    currency = event_data.get('currency', 'USD').lower()

    if not STRIPE_API_KEY or stripe is None:
        # Fallback to simulation mode
        return jsonify({
            'simulate': True,
            'amount': amount,
            'event_id': event_id,
            'currency': currency.upper()
        })

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': currency,
                    'product_data': {
                        'name': event_data.get('title', 'Event Registration'),
                        'description': f"Registration fee for {event_data.get('title')}",
                    },
                    'unit_amount': int(amount * 100),  # Stripe uses cents/paise
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=request.host_url + 'payment/stripe/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.host_url + 'payment/stripe/cancel',
            metadata={
                'event_id': event_id,
                'email': reg_data.get('lead_email', ''),
                'name': reg_data.get('lead_name', ''),
                'reg_id': reg_data.get('reg_id', '')
            }
        )
        return jsonify({
            'session_id': checkout_session.id,
            'url': checkout_session.url
        })
    except Exception as e:
        logger.error("Stripe session creation failed: %s", e)
        return jsonify({'error': str(e)}), 500


@stripe_bp.route('/success')
def success():
    """Redirect target after successful card checkout."""
    session_id = request.args.get('session_id', '')
    reg_data = session.get('pending_reg_data')
    
    if not reg_data:
        # Check if already processed by webhook
        return redirect('/participant/dashboard')

    event_id = reg_data.get('event_id')
    amount = reg_data.get('amount_paid', 0)

    # Complete the registration directly (fallback if webhook is delayed)
    result = _complete_registration(
        event_id=event_id,
        reg_data=reg_data,
        payment_status='Paid (Stripe)',
        amount_paid=int(amount),
        razorpay_payment_id=session_id
    )
    
    if 'error' in result and result['error'] != 'already_registered':
        return redirect('/payment/failed')
        
    reg_id = result.get('reg_id') or reg_data.get('reg_id')
    return redirect(f"/ticket/{reg_id}")


@stripe_bp.route('/cancel')
def cancel():
    """Redirect target after cancelled card checkout."""
    return redirect('/payment/failed')


@stripe_bp.route('/webhook', methods=['POST'])
def webhook():
    """Secure Stripe webhook callback."""
    if stripe is None:
        return jsonify({'status': 'stripe_disabled'}), 400

    payload = request.data
    sig_header = request.headers.get('STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.error("Invalid Stripe webhook signature: %s", e)
        return jsonify({'error': 'Invalid signature'}), 400

    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        metadata = session_obj.get('metadata', {})
        event_id = metadata.get('event_id')
        email = metadata.get('email')
        
        # Look up pending registration or structure it
        reg_data = {
            'event_id': event_id,
            'lead_email': email,
            'lead_name': metadata.get('name'),
            'reg_id': metadata.get('reg_id') or f"REG-{int(time.time() * 1000)}",
            'registered_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        amount_paid = float(session_obj.get('amount_total', 0)) / 100.0

        _complete_registration(
            event_id=event_id,
            reg_data=reg_data,
            payment_status='Paid (Stripe Webhook)',
            amount_paid=int(amount_paid),
            razorpay_payment_id=session_obj.id
        )
        
        log_action(_db(), "STRIPE_WEBHOOK_PROCESSED", f"Stripe payment success for {email}")

    return jsonify({'status': 'success'})
