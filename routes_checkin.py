"""
routes_checkin.py — Self check-in via venue QR code
=====================================================
SPOC toggles self-checkin per event.
When enabled, participants scan a venue QR that links to /checkin/<event_id>.
They confirm their identity and mark themselves Present.
When disabled, only the coordinator scanner can mark attendance.
"""
import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session
from google.cloud.firestore_v1.base_query import FieldFilter

from models import db
from utils import login_required, role_required

checkin_bp = Blueprint('checkin', __name__, url_prefix='/checkin')


# ── 1. Venue QR landing page (no auth required) ───────────────────────────
@checkin_bp.route('/<event_id>')
def self_checkin_page(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return render_template('404.html'), 404

    event = event_doc.to_dict()
    event['id'] = event_id

    if not event.get('allow_self_checkin'):
        return render_template('public/checkin_disabled.html', event=event)

    if event.get('status') != 'active':
        return render_template('public/checkin_closed.html', event=event)

    # If already logged in as a student, pre-fill
    pre_email = session.get('user_id') if session.get('role') == 'Student' else ''
    return render_template('public/self_checkin.html', event=event, pre_email=pre_email)


# ── 2. Submit self check-in (no auth — participant submits their email) ────
@checkin_bp.route('/<event_id>/submit', methods=['POST'])
def submit_self_checkin(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return jsonify({'error': 'Event not found'}), 404

    event = event_doc.to_dict()
    if not event.get('allow_self_checkin'):
        return jsonify({'error': 'Self check-in is not enabled for this event'}), 403
    if event.get('status') != 'active':
        return jsonify({'error': 'Event is not active'}), 400

    email = (request.form.get('email') or '').lower().strip()
    if not email:
        flash("Please enter your registered email.", "warning")
        return redirect(f'/checkin/{event_id}')

    # Find registration
    regs = list(
        db.collection('registrations')
          .where(filter=FieldFilter('event_id', '==', event_id))
          .where(filter=FieldFilter('lead_email', '==', email))
          .limit(1).stream()
    )
    if not regs:
        flash("No registration found for this email. Please check and try again.", "danger")
        return redirect(f'/checkin/{event_id}')

    reg_doc  = regs[0]
    reg      = reg_doc.to_dict()
    reg_id   = reg_doc.id

    if reg.get('attendance') == 'Present':
        return render_template('public/checkin_already.html',
                               event=event, name=reg.get('lead_name', ''))

    checkin_time = datetime.datetime.now().strftime("%H:%M:%S")
    db.collection('registrations').document(reg_id).update({
        'attendance':        'Present',
        'checkin_time':      checkin_time,
        'self_checkin':      True,
    })
    return render_template('public/checkin_success.html',
                           event=event,
                           name=reg.get('lead_name', ''),
                           team=reg.get('team_name', ''),
                           checkin_time=checkin_time)


# ── 3. SPOC: toggle self-checkin on/off ────────────────────────────────────
@checkin_bp.route('/toggle/<event_id>', methods=['POST'])
@login_required
@role_required('ClubSPOC')
def toggle_self_checkin(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/spoc/dashboard')

    current = (event_doc.to_dict() or {}).get('allow_self_checkin', False)
    db.collection('events').document(event_id).update({'allow_self_checkin': not current})
    state = 'enabled' if not current else 'disabled'
    flash(f"Self check-in {state} for this event.", "success")
    return redirect('/spoc/dashboard')


# ── 4. SPOC: get venue QR PNG (links to /checkin/<event_id>) ──────────────
@checkin_bp.route('/venue_qr/<event_id>')
@login_required
@role_required('ClubSPOC')
def venue_qr(event_id):
    """Return a QR code PNG for the venue self-checkin URL."""
    import io
    try:
        import qrcode
    except ImportError:
        return jsonify({'error': 'qrcode library not installed'}), 500

    base_url = request.host_url.rstrip('/')
    url = f"{base_url}/checkin/{event_id}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')  # type: ignore[call-arg]
    buf.seek(0)
    from flask import Response
    return Response(buf.read(), mimetype='image/png')
