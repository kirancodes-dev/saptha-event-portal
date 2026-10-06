"""
routes_ticket.py

Responsibilities:
  /ticket/<reg_id>         — Student digital ticket page (with server QR)
  /ticket/qr/<reg_id>      — Serves QR PNG directly (for img src / emails)
  /ticket/verify/<token>   — Coordinator scans QR → GET validates (read-only), POST marks attendance
  /ticket/api/verify/<tok> — JSON API for scanner apps: GET validates, POST marks attendance
  /ticket/wallet/<tok>     — Digital Ticket Wallet view
  /ticket/api/wallet/<tok> — JSON API for digital ticket wallet details
"""
import datetime
import logging
from typing import Optional, Tuple, Dict, Any

from flask import (Blueprint, abort, flash, jsonify,
                   redirect, render_template, request, session, current_app)
from itsdangerous import URLSafeSerializer

from utils import login_required, log_action
from utils_qr import generate_qr_base64, generate_qr_response
from routes_checkin import _can_manage_event, COORD_ROLES

logger = logging.getLogger(__name__)

ticket_bp = Blueprint('ticket', __name__, url_prefix='/ticket')


def _db():
    from app import db
    return db


# ── Serializer & Token Helpers ──────────────────────────
def _get_serializer():
    secret = current_app.config.get('SECRET_KEY')
    if not secret:
        raise RuntimeError("SECRET_KEY must be configured in Flask application.")
    return URLSafeSerializer(secret, salt='qr-ticket-salt')


def generate_ticket_token(reg_id: str, event_id: str, lead_name: str) -> str:
    s = _get_serializer()
    return s.dumps([str(reg_id), str(event_id), str(lead_name)])


def verify_ticket_token(token: str):
    try:
        s = _get_serializer()
        return s.loads(token)
    except Exception:
        return None


def _parse_signed_token(token: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str], Dict[str, Any]]:
    """
    Validates and decodes signed tokens only.
    Rejects raw registration IDs and malformed tokens.
    Returns: (is_valid, reg_id, event_id, lead_name, extra_data)
    """
    if not token or not isinstance(token, str):
        return False, None, None, None, {}

    # Format 1: itsdangerous URLSafeSerializer token
    token_data = verify_ticket_token(token)
    if token_data and isinstance(token_data, (list, tuple)) and len(token_data) >= 3:
        return True, str(token_data[0]), str(token_data[1]), str(token_data[2]), {}

    # Format 2: TicketService HMAC-SHA256 token (<b64>.<sig>)
    try:
        from services_ticket import TicketService
        if "." in token:
            valid, msg, payload = TicketService.verify_signed_qr_token(token)
            if valid and payload:
                reg_id = payload.get("rid") or payload.get("tid")
                event_id = payload.get("eid")
                lead_name = payload.get("lead_name") or payload.get("em", "")
                return True, str(reg_id) if reg_id else None, str(event_id) if event_id else None, str(lead_name), payload
    except Exception:
        pass

    # Token decoding failed - reject raw ID fallback!
    return False, None, None, None, {}


def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _base_url() -> str:
    """The public address for ticket QR codes: BASE_URL, never the request's host (BLK-16)."""
    from utils_email import _base_url as public_base_url
    return public_base_url()


# =========================================================
# 1. DIGITAL TICKET PAGE
#    Student lands here after registration / from dashboard.
#    Requires login — only the ticket owner can view it.
# =========================================================
@ticket_bp.route('/<reg_id>')
@login_required
def view_ticket(reg_id):
    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')

    reg_doc = _db().collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        flash("Ticket not found.", "danger")
        return redirect('/participant/dashboard')

    reg = reg_doc.to_dict() or {}

    # Fetch event details
    event_doc = _db().collection('events').document(reg.get('event_id', '')).get()
    event     = event_doc.to_dict() if event_doc.exists else {}

    # Security: only the lead registrant, team members, or authorized staff can view
    is_lead = reg.get('lead_email') == user_email
    is_member = any((m.get('email') or '').lower() == (user_email or '').lower() for m in reg.get('members', []))
    is_staff = _can_manage_event(user_email, user_role, event, user_cat)

    if not (is_lead or is_member or is_staff):
        flash("Unauthorised — this is not your ticket.", "danger")
        return redirect('/participant/dashboard')

    # QR is only available from 1 day before the event onwards (staff can always preview)
    show_qr = True
    event_date_str = str(event.get('date', ''))[:10]
    if not is_staff and event_date_str:
        from datetime import date
        try:
            event_d = date.fromisoformat(event_date_str)
            today_d = date.fromisoformat(datetime.datetime.now().strftime('%Y-%m-%d'))
            show_qr = (event_d - datetime.timedelta(days=1)) <= today_d <= event_d
        except ValueError:
            show_qr = True

    qr_b64 = verify_url = None
    if show_qr:
        # Generate cryptographically signed token for QR code
        token = generate_ticket_token(reg_id, reg.get('event_id', ''), reg.get('lead_name', ''))
        verify_url = f"{_base_url()}/ticket/verify/{token}"
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
#    Security: Protected against IDOR. Requires login and ownership or staff permissions.
# =========================================================
@ticket_bp.route('/qr/<reg_id>')
@login_required
def qr_image(reg_id):
    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')

    reg_doc = _db().collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        abort(404)

    reg = reg_doc.to_dict() or {}

    event_doc = _db().collection('events').document(reg.get('event_id', '')).get()
    event = event_doc.to_dict() if event_doc.exists else {}

    is_owner = (reg.get('lead_email') == user_email) or any(
        (m.get('email') or '').lower() == (user_email or '').lower() for m in reg.get('members', [])
    )
    is_staff = _can_manage_event(user_email, user_role, event, user_cat)

    if not (is_owner or is_staff):
        abort(403)

    # Gate QR: only serve from 1 day before event onwards (staff can preview anytime)
    if not is_staff and event_doc.exists:
        event_date_str = str(event.get('date', ''))[:10]
        if event_date_str:
            try:
                from datetime import date
                event_d = date.fromisoformat(event_date_str)
                today_d = date.today()
                if not ((event_d - datetime.timedelta(days=1)) <= today_d <= event_d):
                    abort(403)
            except ValueError:
                pass

    # Generate cryptographically signed token for QR code
    token = generate_ticket_token(reg_id, reg.get('event_id', ''), reg.get('lead_name', ''))
    verify_url = f"{_base_url()}/ticket/verify/{token}"
    return generate_qr_response(verify_url)


# =========================================================
# 3. VERIFY PAGE (Split: GET validates, POST marks attendance)
# =========================================================
@ticket_bp.route('/verify/<token>', methods=['GET', 'POST'])
def verify_ticket(token):
    is_valid, reg_id, event_id, lead_name, extra = _parse_signed_token(token)
    if not is_valid:
        if request.method == 'POST':
            return jsonify({'success': False, 'error': 'Invalid or unauthenticated ticket token. Raw IDs are not permitted.'}), 400
        return render_template(
            'coordinator/verify_result.html',
            status='invalid',
            message='Invalid or forged ticket token — raw registration IDs are not permitted.',
            reg=None,
            event=None,
            can_checkin=False
        ), 400

    # Fetch registration & event from database
    db_exists = False
    reg = None
    event = None
    if reg_id:
        try:
            reg_doc = _db().collection('registrations').document(reg_id).get()
            if reg_doc.exists:
                db_exists = True
                reg = reg_doc.to_dict() or {}
                event_id = reg.get('event_id') or event_id
                lead_name = reg.get('lead_name') or lead_name
        except Exception:
            db_exists = False

    if event_id:
        try:
            event_doc = _db().collection('events').document(str(event_id)).get()
            if event_doc.exists:
                event = event_doc.to_dict() or {}
        except Exception:
            event = {}

    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')
    can_checkin = bool(user_email and user_role in COORD_ROLES and _can_manage_event(user_email, user_role, event or {}, user_cat))

    # --- GET: Read-only validation (name + event only; never mutates data) ---
    if request.method == 'GET':
        if db_exists and reg:
            # Payment check
            payment_status = reg.get('payment_status', '')
            is_paid_or_free = payment_status == 'Free' or (payment_status and payment_status.startswith('Paid'))
            if not is_paid_or_free:
                return render_template(
                    'coordinator/verify_result.html',
                    status='unpaid',
                    message='Payment pending — entry not allowed.',
                    reg={'lead_name': lead_name, 'reg_id': reg_id},
                    event={'title': event.get('title', 'Event') if event else 'Event'},
                    can_checkin=False,
                    token=token
                )

            # Already checked in check
            if reg.get('attendance') == 'Present':
                return render_template(
                    'coordinator/verify_result.html',
                    status='already_in',
                    message='This ticket was already scanned.',
                    reg={'lead_name': lead_name, 'attendance': 'Present', 'checkin_time': reg.get('checkin_time'), 'reg_id': reg_id},
                    event={'title': event.get('title', 'Event') if event else 'Event'},
                    can_checkin=False,
                    token=token
                )

            # Ticket is valid and ready
            return render_template(
                'coordinator/verify_result.html',
                status='valid',
                message='Ticket is valid.',
                reg={'lead_name': lead_name, 'attendance': reg.get('attendance', 'Pending'), 'reg_id': reg_id},
                event={'title': event.get('title', 'Event') if event else 'Event'},
                can_checkin=can_checkin,
                token=token
            )
        else:
            # DB offline / not found but token cryptographically verified
            return render_template(
                'coordinator/verify_result.html',
                status='valid_offline',
                message='Ticket is valid (Cryptographically Verified Offline)',
                reg={'lead_name': lead_name, 'attendance': 'Pending (Offline)', 'reg_id': reg_id},
                event={'title': f"Event ID: {event_id}" if event_id else "Event"},
                can_checkin=can_checkin,
                token=token
            )

    # --- POST: Mark attendance (requires logged-in staff with event access) ---
    if not user_email:
        flash("Please log in as staff to check in attendees.", "danger")
        return redirect('/login')

    if user_role not in COORD_ROLES:
        abort(403)

    if db_exists and event and not can_checkin:
        abort(403)

    checkin_time = _now()

    if db_exists and reg:
        payment_status = reg.get('payment_status', '')
        is_paid_or_free = payment_status == 'Free' or (payment_status and payment_status.startswith('Paid'))
        if not is_paid_or_free:
            return render_template(
                'coordinator/verify_result.html',
                status='unpaid',
                message='Payment pending — entry not allowed.',
                reg={'lead_name': lead_name, 'reg_id': reg_id},
                event={'title': event.get('title', 'Event') if event else 'Event'},
                can_checkin=False
            )

        if reg.get('attendance') == 'Present':
            return render_template(
                'coordinator/verify_result.html',
                status='already_in',
                message='This ticket was already scanned.',
                reg={'lead_name': lead_name, 'attendance': 'Present', 'checkin_time': reg.get('checkin_time'), 'reg_id': reg_id},
                event={'title': event.get('title', 'Event') if event else 'Event'},
                can_checkin=False
            )

        try:
            _db().collection('registrations').document(reg_id).update({
                'attendance': 'Present',
                'checkin_time': checkin_time
            })
            if reg.get('ticket_id'):
                try:
                    _db().collection('tickets').document(reg['ticket_id']).update({
                        'status': 'checked_in',
                        'checked_in': True,
                        'checked_in_at': checkin_time,
                        'checked_in_by': user_email,
                    })
                except Exception:
                    pass
            try:
                from routes_gamification import award_xp
                award_xp(reg.get('lead_email'), 150)
            except Exception:
                pass
            log_action(_db(), "QR_CHECKIN", f"Reg {reg_id} checked in via QR scan at {checkin_time}")
        except Exception:
            pass

        return render_template(
            'coordinator/verify_result.html',
            status='success',
            message='Entry granted! Attendance marked.',
            reg={'lead_name': lead_name, 'attendance': 'Present', 'checkin_time': checkin_time, 'reg_id': reg_id},
            event={'title': event.get('title', 'Event') if event else 'Event'},
            can_checkin=False
        )
    else:
        # DB offline: offline verification for staff
        return render_template(
            'coordinator/verify_result.html',
            status='success',
            message='Entry granted! (Cryptographically Verified Offline)',
            reg={'lead_name': lead_name, 'attendance': 'Present (Offline)', 'checkin_time': checkin_time, 'reg_id': reg_id},
            event={'title': f"Event ID: {event_id}" if event_id else "Event"},
            can_checkin=False
        )


# =========================================================
# 4. JSON API VERIFY
#    GET: Public read-only validity check (returns name + event only)
#    POST: Attendance check-in requiring authenticated staff
# =========================================================
@ticket_bp.route('/api/verify/<token>', methods=['GET', 'POST'])
def api_verify(token):
    is_valid, reg_id, event_id, lead_name, extra = _parse_signed_token(token)
    if not is_valid:
        return jsonify({'status': 'invalid', 'error': 'Invalid or unauthenticated ticket token. Raw IDs are not accepted.'}), 400

    # Universal ticket check via TicketService if extra payload has tid
    ticket_data = None
    if extra and extra.get("tid"):
        try:
            tdoc = _db().collection("tickets").document(extra["tid"]).get()
            if tdoc.exists:
                ticket_data = tdoc.to_dict() or {}
                event_id = ticket_data.get("event_id") or event_id
                lead_name = ticket_data.get("lead_name") or lead_name
        except Exception:
            pass

    reg = None
    event = None
    if reg_id:
        try:
            reg_doc = _db().collection('registrations').document(reg_id).get()
            if reg_doc.exists:
                reg = reg_doc.to_dict() or {}
                event_id = reg.get('event_id') or event_id
                lead_name = reg.get('lead_name') or lead_name
        except Exception:
            pass

    if event_id:
        try:
            edoc = _db().collection('events').document(str(event_id)).get()
            if edoc.exists:
                event = edoc.to_dict() or {}
        except Exception:
            pass

    # Authenticate caller for POST (Session or JWT Bearer)
    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')

    if not user_email:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            jwt_token = auth_header[7:].strip()
            try:
                from auth_jwt import decode_access_token
                payload = decode_access_token(jwt_token)
                if payload:
                    user_email = payload.get("sub") or payload.get("user_id")
                    user_role  = payload.get("role", "")
                    user_cat   = payload.get("category", "General")
            except Exception:
                pass

    # --- GET: Public read-only validity check (never modifies data) ---
    if request.method == 'GET':
        if ticket_data:
            if ticket_data.get("checked_in"):
                return jsonify({
                    'status': 'already_in',
                    'message': 'Already checked in',
                    'name': lead_name,
                    'event': event.get('title') if event else '',
                    'ticket_type': ticket_data.get('ticket_type', 'General')
                }), 200
            return jsonify({
                'status': 'success',
                'message': 'Ticket is valid',
                'name': lead_name,
                'event': event.get('title') if event else '',
                'ticket_type': ticket_data.get('ticket_type', 'General')
            }), 200

        if reg:
            payment_status = reg.get('payment_status', '')
            is_paid_or_free = payment_status == 'Free' or (payment_status and payment_status.startswith('Paid'))
            if not is_paid_or_free:
                return jsonify({'status': 'unpaid', 'message': 'Payment pending — entry not allowed'}), 402

            if reg.get('attendance') == 'Present':
                return jsonify({
                    'status': 'already_in',
                    'message': 'Already checked in',
                    'name': lead_name,
                    'event': event.get('title') if event else '',
                    'checkin_time': reg.get('checkin_time')
                }), 200

            return jsonify({
                'status': 'success',
                'message': 'Ticket is valid',
                'name': lead_name,
                'event': event.get('title') if event else ''
            }), 200

        # DB offline / not found but token cryptographically verified
        return jsonify({
            'status': 'success',
            'message': 'Ticket token cryptographically valid (offline)',
            'name': lead_name,
            'event': event.get('title') if event else (str(event_id) if event_id else '')
        }), 200

    # --- POST: Mark attendance (requires staff authorization) ---
    if not user_email or user_role not in COORD_ROLES:
        return jsonify({'status': 'error', 'message': 'Staff authentication required to mark attendance'}), 403

    if event and not _can_manage_event(user_email, user_role, event, user_cat):
        return jsonify({'status': 'error', 'message': 'Forbidden: You cannot manage attendance for this event'}), 403

    checkin_time = _now()

    if ticket_data:
        from services_ticket import TicketService
        tkt_res = TicketService.checkin_ticket(_db(), token)
        if tkt_res.get("status") == "success":
            return jsonify({
                'status': 'success',
                'message': 'Entry granted',
                'name': lead_name,
                'checkin_time': checkin_time,
                'ticket_type': ticket_data.get('ticket_type', 'General')
            }), 200
        elif tkt_res.get("status") == "already_used":
            return jsonify({'status': 'already_in', 'message': 'Already checked in', 'name': lead_name}), 200
        else:
            return jsonify({'status': tkt_res.get("status", "error"), 'message': tkt_res.get("message", "Error")}), 400

    if reg:
        payment_status = reg.get('payment_status', '')
        is_paid_or_free = payment_status == 'Free' or (payment_status and payment_status.startswith('Paid'))
        if not is_paid_or_free:
            return jsonify({'status': 'unpaid', 'message': 'Payment pending — entry not allowed'}), 402

        if reg.get('attendance') == 'Present':
            return jsonify({
                'status': 'already_in',
                'message': 'Already checked in',
                'name': lead_name,
                'checkin_time': reg.get('checkin_time')
            }), 200

        try:
            _db().collection('registrations').document(reg_id).update({
                'attendance': 'Present',
                'checkin_time': checkin_time
            })
            if reg.get('ticket_id'):
                try:
                    _db().collection('tickets').document(reg['ticket_id']).update({
                        'status': 'checked_in',
                        'checked_in': True,
                        'checked_in_at': checkin_time,
                        'checked_in_by': user_email,
                    })
                except Exception:
                    pass
            try:
                from routes_gamification import award_xp
                award_xp(reg.get('lead_email'), 150)
            except Exception:
                pass
            log_action(_db(), "API_QR_CHECKIN", f"Reg {reg_id} checked in via API at {checkin_time}")
        except Exception:
            pass

        return jsonify({
            'status': 'success',
            'message': 'Entry granted',
            'name': lead_name,
            'checkin_time': checkin_time
        }), 200

    # Offline verified checkin
    return jsonify({
        'status': 'success',
        'message': 'Entry granted (Cryptographically Verified Offline)',
        'name': lead_name,
        'checkin_time': checkin_time
    }), 200


# =========================================================
# 5. DIGITAL TICKET WALLET VIEW & JSON API
# =========================================================
@ticket_bp.route('/wallet/<ticket_code_or_id>')
def ticket_wallet(ticket_code_or_id):
    """Mobile-first responsive Digital Ticket Wallet view."""
    from services_ticket import TicketService
    wallet_data = TicketService.get_wallet_pass(_db(), ticket_code_or_id)
    if not wallet_data:
        abort(404)

    ticket = wallet_data.get("ticket") or {}
    event = wallet_data.get("event") or {}

    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')

    is_staff = _can_manage_event(user_email, user_role, event, user_cat)
    is_owner = bool(user_email and (
        ticket.get("lead_email") == user_email or
        ticket.get("user_id") == user_email or
        ticket.get("email") == user_email
    ))

    # Allow anonymous access ONLY when presented with the secret ticket_code (possession token)
    secret_code = ticket.get("ticket_code")
    is_possession = bool(secret_code and ticket_code_or_id == secret_code and len(secret_code) >= 8)

    if not (is_owner or is_staff or is_possession):
        if not user_email:
            flash("Please log in to view this wallet pass.", "warning")
            return redirect('/login')
        abort(403)

    if request.headers.get("Accept") == "application/json" or request.args.get("format") == "json":
        return jsonify({"status": "success", "data": wallet_data})

    return render_template(
        'tickets/digital_wallet.html',
        ticket=wallet_data["ticket"],
        event=wallet_data["event"],
        qr_b64=wallet_data["qr_image_base64"],
        theme=wallet_data["theme"],
        is_valid=wallet_data["is_valid"],
    )


@ticket_bp.route('/api/wallet/<ticket_code_or_id>')
def api_ticket_wallet(ticket_code_or_id):
    """JSON API for digital ticket wallet details."""
    from services_ticket import TicketService
    wallet_data = TicketService.get_wallet_pass(_db(), ticket_code_or_id)
    if not wallet_data:
        return jsonify({"status": "error", "message": "Ticket not found"}), 404

    ticket = wallet_data.get("ticket") or {}
    event = wallet_data.get("event") or {}

    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')

    is_staff = _can_manage_event(user_email, user_role, event, user_cat)
    is_owner = bool(user_email and (
        ticket.get("lead_email") == user_email or
        ticket.get("user_id") == user_email or
        ticket.get("email") == user_email
    ))

    secret_code = ticket.get("ticket_code")
    is_possession = bool(secret_code and ticket_code_or_id == secret_code and len(secret_code) >= 8)

    if not (is_owner or is_staff or is_possession):
        return jsonify({"status": "error", "message": "Forbidden: You are not authorized to view this ticket."}), 403

    return jsonify({"status": "success", "data": wallet_data})
