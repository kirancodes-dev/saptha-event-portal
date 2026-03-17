import time
import datetime

from flask import (Blueprint, flash, redirect, render_template,
                   request, session)

from models import db
from utils import log_action
from utils_email import send_ticket_email
from utils_whatsapp import send_ticket_whatsapp, send_payment_receipt_whatsapp  # ← NEW

payment_bp = Blueprint('payment', __name__, url_prefix='/payment')


# =========================================================
# 1. CHECKOUT PAGE
# =========================================================
@payment_bp.route('/checkout/<event_id>')
def checkout(event_id):
    reg_data = session.get('pending_reg_data')
    if not reg_data:
        flash("No pending registration found. Please register first.", "warning")
        return redirect('/')

    event_doc = db.collection('events').document(event_id).get()
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
# 2. PROCESS PAYMENT (SIMULATION)
#    Replace with Razorpay webhook when ready.
# =========================================================
@payment_bp.route('/process', methods=['POST'])
def process_payment():
    event_id = request.form.get('event_id', '').strip()
    amount   = request.form.get('amount', '0')

    reg_data = session.get('pending_reg_data')
    if not reg_data:
        flash("Session expired. Please start registration again.", "danger")
        return redirect('/')

    email  = reg_data.get('lead_email')
    name   = reg_data.get('lead_name')
    phone  = reg_data.get('lead_phone', '')           # ← phone for WhatsApp
    reg_id = reg_data.get('reg_id') or f"REG-{int(time.time() * 1000)}"

    try:
        # Duplicate guard
        existing = list(
            db.collection('registrations')
              .where('event_id', '==', event_id)
              .where('lead_email', '==', email)
              .limit(1).stream()
        )
        if existing:
            flash("You are already registered for this event.", "warning")
            session.pop('pending_reg_data', None)
            return redirect('/')

        reg_data.update({
            'reg_id':         reg_id,
            'status':         'Confirmed',
            'payment_status': 'Paid',
            'amount_paid':    int(amount),
            'is_eliminated':  False,
            'current_round':  1,
        })

        db.collection('registrations').document(reg_id).set(reg_data)

        event_ref  = db.collection('events').document(event_id)
        event_data = event_ref.get().to_dict() or {}
        event_ref.update({
            'registration_count': event_data.get('registration_count', 0) + 1
        })

        # ── NOTIFICATIONS ─────────────────────────────────
        # Email ticket
        send_ticket_email(email, name, event_data.get('title', 'Event'), reg_id)

        # WhatsApp payment receipt (if phone on record)
        if phone:
            send_payment_receipt_whatsapp(
                phone=phone,
                name=name,
                event_title=event_data.get('title', 'Event'),
                reg_id=reg_id,
                amount=int(amount)
            )
            # Also send the ticket WhatsApp with event details
            send_ticket_whatsapp(
                phone=phone,
                name=name,
                event_title=event_data.get('title', 'Event'),
                reg_id=reg_id,
                event_date=event_data.get('date', ''),
                venue=event_data.get('venue', '')
            )
        # ──────────────────────────────────────────────────

        session.pop('pending_reg_data', None)

        # Auto-login the participant
        session['user_id']  = email
        session['name']     = name
        session['role']     = 'Student'
        session['category'] = 'General'

        log_action(db, "PAYMENT_CONFIRMED",
                   f"Registration {reg_id} confirmed for event {event_id} — ₹{amount}")

        return redirect(f'/ticket/{reg_id}')

    except Exception as exc:
        flash(f"Payment failed: {exc}", "danger")
        log_action(db, "PAYMENT_FAILED", f"Event {event_id}, email {email} — {exc}")
        return redirect('/')