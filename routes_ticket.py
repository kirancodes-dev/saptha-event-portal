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

from models import db
from utils import login_required, log_action
from utils_qr import generate_qr_base64, generate_qr_response

ticket_bp = Blueprint('ticket', __name__, url_prefix='/ticket')


# ── helpers ──────────────────────────────────────────────
def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")

def _base_url() -> str:
    """
    Returns the correct base URL for QR codes.
    Set BASE_URL environment variable on Render to your real domain.
    Falls back to localhost for local development.
    """
    return os.environ.get('BASE_URL', 'http://127.0.0.1:5000')


# =========================================================
# 1. DIGITAL TICKET PAGE
#    Student lands here after registration / from dashboard.
#    Requires login — only the ticket owner can view it.
# =========================================================
@ticket_bp.route('/<reg_id>')
@login_required
def view_ticket(reg_id):
    reg_doc = db.collection('registrations').document(reg_id).get()

    if not reg_doc.exists:
        flash("Ticket not found.", "danger")
        return redirect('/participant/dashboard')

    reg = reg_doc.to_dict()

    # Security: only the lead registrant can view their own ticket
    if reg.get('lead_email') != session.get('user_id'):
        flash("Unauthorised — this is not your ticket.", "danger")
        return redirect('/participant/dashboard')

    # Fetch event details
    event_doc = db.collection('events').document(reg.get('event_id', '')).get()
    event     = event_doc.to_dict() if event_doc.exists else {}

    # Build verification URL (this is what gets encoded into the QR)
    verify_url = f"{_base_url()}/ticket/verify/{reg_id}"

    # Generate QR as base64 — embedded inline, no extra HTTP request needed
    qr_b64 = generate_qr_base64(verify_url)

    return render_template(
        'participant/ticket.html',
        reg=reg,
        event=event,
        qr_b64=qr_b64,
        verify_url=verify_url
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
    reg_doc = db.collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        abort(404)

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
    reg_doc = db.collection('registrations').document(reg_id).get()

    # ── Invalid ticket ────────────────────────────────────
    if not reg_doc.exists:
        return render_template(
            'coordinator/verify_result.html',
            status='invalid',
            message='Invalid ticket — registration not found.',
            reg=None, event=None
        )

    reg       = reg_doc.to_dict()
    event_doc = db.collection('events').document(reg.get('event_id', '')).get()
    event     = event_doc.to_dict() if event_doc.exists else {}

    # ── Payment not confirmed ─────────────────────────────
    if reg.get('payment_status') not in ('Paid', 'Free'):
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
    db.collection('registrations').document(reg_id).update({
        'attendance':   'Present',
        'checkin_time': checkin_time
    })
    reg['attendance']   = 'Present'
    reg['checkin_time'] = checkin_time

    log_action(db, "QR_CHECKIN",
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
    reg_doc = db.collection('registrations').document(reg_id).get()

    if not reg_doc.exists:
        return jsonify({'status': 'invalid', 'message': 'Ticket not found'}), 404

    reg = reg_doc.to_dict()

    if reg.get('payment_status') not in ('Paid', 'Free'):
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
    db.collection('registrations').document(reg_id).update({
        'attendance':   'Present',
        'checkin_time': checkin_time
    })
    log_action(db, "API_QR_CHECKIN", f"Reg {reg_id} checked in via API at {checkin_time}")

    return jsonify({
        'status':       'success',
        'message':      'Entry granted',
        'name':         reg.get('lead_name'),
        'team':         reg.get('team_name'),
        'members':      len(reg.get('members', [])),
        'checkin_time': checkin_time
    }), 200