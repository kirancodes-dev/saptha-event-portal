from flask import Blueprint, render_template, request, redirect, session, flash
from models import db
from utils_email import send_ticket_email
import datetime

payment_bp = Blueprint('payment', __name__, url_prefix='/payment')

# --- 1. CHECKOUT PAGE ---
# Removed @login_required so brand new users can pay!
@payment_bp.route('/checkout/<event_id>')
def checkout(event_id):
    # 1. Grab the temporary registration data we saved in routes_participant
    reg_data = session.get('pending_reg_data')
    if not reg_data:
        flash("No pending registration found. Please register for an event first.", "warning")
        return redirect('/')

    # 2. Get Event Details
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return "Event not found", 404
    event = event_doc.to_dict()
    
    # 3. Build a temporary user profile for the checkout screen to display
    user = {
        'name': reg_data.get('lead_name'),
        'email': reg_data.get('lead_email')
    }

    amount = event.get('entry_fee', 0)
    
    return render_template('payment/checkout.html', event=event, user=user, amount=amount)

# --- 2. PROCESS PAYMENT (SIMULATION) ---
# Removed @login_required here as well
@payment_bp.route('/process', methods=['POST'])
def process_payment():
    event_id = request.form.get('event_id')
    amount = request.form.get('amount')
    
    # 1. Retrieve the pending registration data
    reg_data = session.get('pending_reg_data')
    if not reg_data:
        flash("Session expired. Please start the registration again.", "danger")
        return redirect('/')

    email = reg_data.get('lead_email')
    name = reg_data.get('lead_name')
    reg_id = reg_data.get('reg_id')

    try:
        # Check if already registered
        existing = db.collection('registrations').where('event_id', '==', event_id).where('lead_email', '==', email).stream()
        if len(list(existing)) > 0:
            flash("You are already registered for this event!", "warning")
            session.pop('pending_reg_data', None) # Clear the cache
            return redirect('/')

        # 2. Finalize Registration Data
        reg_data['status'] = 'Confirmed'
        reg_data['payment_status'] = 'Paid'
        reg_data['amount_paid'] = int(amount)
        # Note: 'registered_at' and 'attendance' were already set in routes_participant
        
        # 3. Save to Database
        db.collection('registrations').document(reg_id).set(reg_data)
        
        # 4. Update Event Count
        event_ref = db.collection('events').document(event_id)
        evt_data = event_ref.get().to_dict()
        current_count = evt_data.get('registration_count', 0)
        event_ref.update({'registration_count': current_count + 1})

        # 5. Send Ticket Email (The password was already sent in step 1!)
        event_title = evt_data.get('title', 'Event')
        send_ticket_email(email, name, event_title, reg_id)

        # 6. Clear the pending registration from session
        session.pop('pending_reg_data', None)

        # 7. --- MAGIC AUTO-LOGIN ---
        # Since they successfully paid and got their account, log them in instantly!
        session['user_id'] = email
        session['name'] = name
        session['role'] = 'Student'
        session['category'] = 'General'

        return render_template('payment/success.html', reg_id=reg_id, amount=amount, title=event_title)

    except Exception as e:
        print(e)
        flash("Payment Failed. Please try again.", "danger")
        return redirect('/')