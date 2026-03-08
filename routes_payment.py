from flask import Blueprint, render_template, request, redirect, session, flash
from models import db
from utils import login_required
from utils_email import send_ticket_email
import datetime

payment_bp = Blueprint('payment', __name__, url_prefix='/payment')

# --- 1. CHECKOUT PAGE ---
@payment_bp.route('/checkout/<event_id>')
@login_required
def checkout(event_id):
    # Get Event Details
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return "Event not found", 404
    event = event_doc.to_dict()
    
    # Get User Details
    user_doc = db.collection('users').document(session['user_id']).get()
    user = user_doc.to_dict()

    # Calculate Total (For now, 1 ticket)
    amount = event.get('entry_fee', 0)
    
    return render_template('payment/checkout.html', event=event, user=user, amount=amount)

# --- 2. PROCESS PAYMENT (SIMULATION) ---
@payment_bp.route('/process', methods=['POST'])
@login_required
def process_payment():
    event_id = request.form.get('event_id')
    amount = request.form.get('amount')
    
    # 1. SIMULATE BANK DELAY (Optional, strictly logic here)
    # In a real app, you would verify signature from Razorpay here.
    
    # 2. CREATE REGISTRATION ENTRY (Confirmed)
    try:
        # Check if already registered
        existing = db.collection('registrations').where('event_id', '==', event_id).where('lead_email', '==', session['user_id']).stream()
        if len(list(existing)) > 0:
            flash("You are already registered!", "warning")
            return redirect(f'/event/{event_id}')

        # Generate Unique Registration ID
        reg_id = f"REG-{int(datetime.datetime.now().timestamp())}"
        
        # Save to DB
        reg_data = {
            'reg_id': reg_id,
            'event_id': event_id,
            'lead_name': session.get('name'),
            'lead_email': session['user_id'],
            'status': 'Confirmed',          # <--- DIRECTLY CONFIRMED
            'payment_status': 'Paid',       # <--- MARKED AS PAID
            'amount_paid': int(amount),
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'attendance': 'Absent',
            'scores': {}
        }
        
        db.collection('registrations').document(reg_id).set(reg_data)
        
        # 3. Update Event Count
        event_ref = db.collection('events').document(event_id)
        # Use Firestore increment if possible, or manual read-write
        evt_data = event_ref.get().to_dict()
        current_count = evt_data.get('registration_count', 0)
        event_ref.update({'registration_count': current_count + 1})

        # 4. Send Ticket Email
        event_title = evt_data.get('title')
        send_ticket_email(session['user_id'], session.get('name'), event_title, reg_id)

        return render_template('payment/success.html', reg_id=reg_id, amount=amount, title=event_title)

    except Exception as e:
        print(e)
        flash("Payment Failed. Please try again.", "danger")
        return redirect(f'/event/{event_id}')