"""
routes_ticket.py

Responsibilities:
  /ticket/<reg_id>         — Student digital ticket page (with server QR)
  /ticket/qr/<reg_id>      — Serves QR PNG directly  (for img src / emails)
  /ticket/verify/<reg_id>  — Coordinator scans QR → green/red result page
  /ticket/api/verify/<id>  — JSON API for custom scanner apps
"""
import datetime
import os

from flask import (Blueprint, abort, flash, jsonify,
                   redirect, render_template, request, session)

def _db():
    from app import db
    return db
from utils import login_required, log_action
from utils_qr import generate_qr_base64, generate_qr_response

ticket_bp = Blueprint('ticket', __name__, url_prefix='/ticket')


# ── helpers ──────────────────────────────────────────────
def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")

def _base_url() -> str:
    """
    Returns the correct base URL for QR codes.
    Priority: BASE_URL env var > current request host > localhost fallback.
    """
    env_url = os.environ.get('BASE_URL', '').strip().rstrip('/')
    if env_url:
        return env_url
    try:
        host = request.host_url.rstrip('/')
        if host and '127.0.0.1' not in host and 'localhost' not in host:
            return host
        if host:
            return host
    except RuntimeError:
        pass  # outside request context
    return 'http://127.0.0.1:5000'


# =========================================================
# 1. DIGITAL TICKET PAGE
#    Student lands here after registration / from dashboard.
#    Requires login — only the ticket owner can view it.
# =========================================================
@ticket_bp.route('/<reg_id>')
@login_required
def view_ticket(reg_id):
    reg_doc = _db().collection('registrations').document(reg_id).get()

    if not reg_doc.exists:
        flash("Ticket not found.", "danger")
        return redirect('/participant/dashboard')

    reg = reg_doc.to_dict()

    # Security: only the lead registrant can view their own ticket
    if reg.get('lead_email') != session.get('user_id'):
        flash("Unauthorised — this is not your ticket.", "danger")
        return redirect('/participant/dashboard')

    # Fetch event details
    event_doc = _db().collection('events').document(reg.get('event_id', '')).get()
    event     = event_doc.to_dict() if event_doc.exists else {}

    # QR is only available from 1 day before the event onwards
    today_str      = datetime.datetime.now().strftime('%Y-%m-%d')
    event_date_str = str(event.get('date', ''))[:10]
    if event_date_str:
        from datetime import date
        try:
            event_d = date.fromisoformat(event_date_str)
            today_d = date.fromisoformat(today_str)
            # Show QR only from 1 day before the event up to and including event day
            show_qr = (event_d - datetime.timedelta(days=1)) <= today_d <= event_d
        except ValueError:
            show_qr = True
    else:
        show_qr = True

    qr_b64 = verify_url = None
    if show_qr:
        verify_url = f"{_base_url()}/ticket/verify/{reg_id}"
        qr_b64     = generate_qr_base64(verify_url)

    return render_template(
        'participant/ticket.html',
        reg=reg,
        event=event,
        qr_b64=qr_b64,
        verify_url=verify_url,
        show_qr=show_qr,
        event_date=event_date_str,
    )


# =========================================================
# 2. QR IMAGE ENDPOINT
#    Serves the QR as a raw PNG.
#    Use:  <img src="/ticket/qr/REG-123456">
#    Also useful for PDF certificate generation.
#    No login required — the reg_id is already a secret token.
# =========================================================
@ticket_bp.route('/qr/<reg_id>')
def qr_image(reg_id):
    reg_doc = _db().collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        abort(404)

    reg = reg_doc.to_dict()

    # Gate QR: only serve from 1 day before event onwards
    event_doc = _db().collection('events').document(reg.get('event_id', '')).get()
    if event_doc.exists:
        event_date_str = str(event_doc.to_dict().get('date', ''))[:10]
        if event_date_str:
            try:
                from datetime import date
                event_d = date.fromisoformat(event_date_str)
                today_d = date.today()
                if not ((event_d - datetime.timedelta(days=1)) <= today_d <= event_d):
                    abort(403)
            except ValueError:
                pass

    verify_url = f"{_base_url()}/ticket/verify/{reg_id}"
    return generate_qr_response(verify_url)


# =========================================================
# 3. VERIFY PAGE
#    Opens when coordinator scans QR with phone camera.
#    NO login required — coordinator uses their phone browser.
#    Auto-marks attendance on successful scan.
# =========================================================
@ticket_bp.route('/verify/<reg_id>')
def verify_ticket(reg_id):
    reg_doc = _db().collection('registrations').document(reg_id).get()

    # ── Invalid ticket ────────────────────────────────────
    if not reg_doc.exists:
        return render_template(
            'coordinator/verify_result.html',
            status='invalid',
            message='Invalid ticket — registration not found.',
            reg=None, event=None
        )

    reg       = reg_doc.to_dict()
    event_doc = _db().collection('events').document(reg.get('event_id', '')).get()
    event     = event_doc.to_dict() if event_doc.exists else {}

    # ── Payment not confirmed ─────────────────────────────
    payment_status = reg.get('payment_status', '')
    is_paid_or_free = payment_status == 'Free' or (payment_status and payment_status.startswith('Paid'))
    if not is_paid_or_free:
        return render_template(
            'coordinator/verify_result.html',
            status='unpaid',
            message='Payment pending — entry not allowed.',
            reg=reg, event=event
        )

    # ── Already checked in ────────────────────────────────
    if reg.get('attendance') == 'Present':
        return render_template(
            'coordinator/verify_result.html',
            status='already_in',
            message='This ticket was already scanned.',
            reg=reg, event=event
        )

    # ── All good — mark Present ───────────────────────────
    checkin_time = _now()
    _db().collection('registrations').document(reg_id).update({
        'attendance':   'Present',
        'checkin_time': checkin_time
    })
    # Award +150 XP for check-in
    try:
        from routes_gamification import award_xp
        award_xp(reg.get('lead_email'), 150)
    except Exception as e:
        pass

    reg['attendance']   = 'Present'
    reg['checkin_time'] = checkin_time

    log_action(_db(), "QR_CHECKIN",
               f"Reg {reg_id} checked in via QR scan at {checkin_time}")

    return render_template(
        'coordinator/verify_result.html',
        status='success',
        message='Entry granted!',
        reg=reg, event=event
    )


# =========================================================
# 4. JSON API VERIFY
#    For custom scanner apps or AJAX-based scanning UIs.
#    GET /ticket/api/verify/<reg_id>
# =========================================================
@ticket_bp.route('/api/verify/<reg_id>')
def api_verify(reg_id):
    reg_doc = _db().collection('registrations').document(reg_id).get()

    if not reg_doc.exists:
        return jsonify({'status': 'invalid', 'message': 'Ticket not found'}), 404

    reg = reg_doc.to_dict()

    payment_status = reg.get('payment_status', '')
    is_paid_or_free = payment_status == 'Free' or (payment_status and payment_status.startswith('Paid'))
    if not is_paid_or_free:
        return jsonify({
            'status':  'unpaid',
            'message': 'Payment pending — entry not allowed'
        }), 402

    if reg.get('attendance') == 'Present':
        return jsonify({
            'status':       'already_in',
            'message':      'Already checked in',
            'name':         reg.get('lead_name'),
            'team':         reg.get('team_name'),
            'checkin_time': reg.get('checkin_time')
        }), 200

    # Mark present
    checkin_time = _now()
    _db().collection('registrations').document(reg_id).update({
        'attendance':   'Present',
        'checkin_time': checkin_time
    })
    # Award +150 XP for check-in
    try:
        from routes_gamification import award_xp
        award_xp(reg.get('lead_email'), 150)
    except Exception as e:
        pass

    log_action(_db(), "API_QR_CHECKIN", f"Reg {reg_id} checked in via API at {checkin_time}")

    return jsonify({
        'status':       'success',
        'message':      'Entry granted',
        'name':         reg.get('lead_name'),
        'team':         reg.get('team_name'),
        'members':      len(reg.get('members', [])),
        'checkin_time': checkin_time
    }), 200
