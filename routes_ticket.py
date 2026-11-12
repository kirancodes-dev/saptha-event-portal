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

from utils import login_required, log_action, safe_int
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


def generate_ticket_token(reg_id: str, event_id: str, lead_name: str, gen: int = 0) -> str:
    """The signed ticket token. `gen` is the registration's ticket generation:
    0 until the ticket is first transferred (the token is then exactly as
    before UPG-161), and one more on each transfer, so older tokens stop working."""
    s = _get_serializer()
    payload = [str(reg_id), str(event_id), str(lead_name)]
    if int(gen or 0):
        payload.append(int(gen))
    return s.dumps(payload)


def ticket_token_for(reg_id: str, reg: dict) -> str:
    """The current ticket token of a registration (UPG-161)."""
    return generate_ticket_token(reg_id, reg.get('event_id', ''), reg.get('lead_name', ''),
                                 reg.get('ticket_gen') or 0)


def token_is_current(reg: dict, extra: dict) -> bool:
    """False for a ticket replaced by a transfer (UPG-161)."""
    try:
        return int((extra or {}).get('gen') or 0) == int((reg or {}).get('ticket_gen') or 0)
    except (TypeError, ValueError):
        return False


TRANSFERRED_MESSAGE = "This ticket was transferred to someone else; it no longer works."


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
        extra = {'gen': token_data[3]} if len(token_data) >= 4 else {}
        return True, str(token_data[0]), str(token_data[1]), str(token_data[2]), extra

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


# ── Check-in: one implementation for every scanner and desk (UPG-02) ──
ENTRY_PAYMENT_STATUSES = ('free', 'waived', 'exempt', 'paid', 'completed')


def payment_allows_entry(reg: dict, event: Optional[dict]) -> bool:
    """Free, waived and paid registrations may enter, in any case and with a
    suffix such as 'Paid (Stripe)'. On an event with a fee, anything else
    (Pending, unpaid, Refunded, none) may not; on a free event nothing is owed."""
    status = str(reg.get('payment_status') or '').strip().lower()
    if status in ENTRY_PAYMENT_STATUSES or status.startswith('paid'):
        return True
    event = event or {}
    fee = safe_int(event.get('entry_fee')) or safe_int((event.get('fees') or {}).get('regular')) \
        or safe_int(event.get('fee'))
    return fee <= 0


def _token_from_scan(scanned: str) -> str:
    """A scanner reads either the ticket's verify link or a bare token."""
    scanned = (scanned or '').strip()
    if '/ticket/verify/' in scanned:
        scanned = scanned.split('/ticket/verify/', 1)[1]
        for sep in ('?', '#', '/'):
            scanned = scanned.split(sep, 1)[0]
    return scanned


def _ist_today() -> str:
    """Today's date where the university is (attendance is counted per day there)."""
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=5, minutes=30))).date().isoformat()


def check_in(reg_id: str, actor, expected_event_id: Optional[str] = None,
             source: str = 'scan', token_extra: Optional[dict] = None) -> Tuple[Dict[str, Any], int]:
    """Mark one registration present. Returns (JSON body, HTTP status).

    The registration's event must exist and the actor needs check_in on it.
    A second check-in changes nothing and reports the first time. Payment
    must allow entry (payment_allows_entry). `expected_event_id` is the
    event the scanner is working; another event's ticket is refused.
    `token_extra` is what the scanned token carried: a ticket replaced by a
    transfer is refused (UPG-161)."""
    from services_permission import can

    def answer(status, message, http, **extra):
        body = {'status': status, 'success': status in ('success', 'already_in'),
                'already_present': status == 'already_in', 'message': message}
        body.update(extra)
        return body, http

    user_email = (actor.get('user_id') or '') if actor else ''
    if not user_email:
        return answer('login_required', 'Log in as event staff to check people in.', 401)

    db = _db()
    reg_doc = db.collection('registrations').document(reg_id).get() if reg_id else None
    if reg_doc is None or not reg_doc.exists:
        return answer('invalid', 'Ticket not found.', 404)
    reg = reg_doc.to_dict() or {}
    event_id = str(reg.get('event_id') or '')
    event_doc = db.collection('events').document(event_id).get() if event_id else None
    if event_doc is None or not event_doc.exists:
        return answer('invalid', "This ticket's event no longer exists.", 404)
    event = dict(event_doc.to_dict() or {}, id=event_id)
    if not can(actor, 'check_in', event, db=db):
        return answer('forbidden', "You're not on this event's check-in staff.", 403)
    if expected_event_id and str(expected_event_id) != event_id:
        return answer('wrong_event', f"This ticket is for {event.get('title', 'another event')}.", 409)

    details = {
        'reg_id':      reg_id,
        'name':        reg.get('lead_name', ''),
        'team':        reg.get('team_name', ''),
        'event_title': event.get('title', 'Event'),
        'room':        reg.get('assigned_room') or reg.get('allocated_room') or '',
        'members':     [{'name': m.get('name', ''), 'usn': m.get('usn', ''), 'attendance': m.get('attendance', '')}
                        for m in (reg.get('members') or [])],
        'badge_url':   f"/ticket/{reg_id}/badge.pdf",   # print at the door (UPG-158)
    }
    details.update(lead_name=details['name'], team_name=details['team'])

    if token_extra is not None and not token_is_current(reg, token_extra):
        log_action(db, "CHECKIN_REFUSED", f"Reg {reg_id}: a transferred ticket was scanned ({source})")
        return answer('transferred', TRANSFERRED_MESSAGE, 409, **details)

    if str(reg.get('status') or '').strip().lower() in ('cancelled', 'refunded'):
        return answer('cancelled', f"This registration was {str(reg.get('status')).lower()}; no entry.", 409, **details)

    # The SPOC's entry list (UPG-214): a team not on it is turned away, quietly
    import services_entry
    if not services_entry.may_enter(event, reg):
        services_entry.note_refused(db, reg_id, reg)
        log_action(db, "CHECKIN_REFUSED", f"Reg {reg_id}: not on the entry list ({source})")
        return answer('not_selected', services_entry.REFUSED, 409, **details)

    # Each day attended is recorded, so a multi-day event can certify people who
    # came on enough of its days (UPG-122). A second scan on the same day changes nothing.
    today = _ist_today()
    days = list(reg.get('attendance_days') or [])
    if str(reg.get('attendance') or '').strip().lower() == 'present':
        first = reg.get('checkin_time') or ''
        if days and today not in days:
            db.collection('registrations').document(reg_id).update({'attendance_days': days + [today]})
            log_action(db, "CHECKIN", f"Reg {reg_id} checked in for another day, {today} ({source})")
            return answer('success', f'Entry granted (day {len(days) + 1}).', 200, checkin_time=first, **details)
        if not days:   # checked in before days were recorded: today counts as that day
            db.collection('registrations').document(reg_id).update({'attendance_days': [today]})
        message = f"Already checked in at {first[:5]}." if first else "Already checked in."
        return answer('already_in', message, 200, checkin_time=first, **details)

    if not payment_allows_entry(reg, event):
        return answer('unpaid', 'Payment pending — entry not allowed.', 402, **details)

    checkin_time = _now()
    # Activity points and hours aren't written here: the ledger credits a
    # registration once from its attendance (services_ledger, UPG-11).
    db.collection('registrations').document(reg_id).update({
        'attendance':      'Present',
        'checkin_time':    checkin_time,
        'checked_in_by':   user_email,
        'attendance_days': sorted(set(days + [today])),
    })
    if reg.get('ticket_id'):
        try:
            db.collection('tickets').document(reg['ticket_id']).update({
                'status': 'checked_in', 'checked_in': True,
                'checked_in_at': checkin_time, 'checked_in_by': user_email,
            })
        except Exception:
            logger.warning("Ticket %s not updated on check-in", reg.get('ticket_id'))
    try:
        from routes_gamification import award_xp
        award_xp(reg.get('lead_email'), 150)
    except Exception:
        pass
    log_action(db, "CHECKIN", f"Reg {reg_id} checked in at {checkin_time} ({source})")
    return answer('success', 'Entry granted.', 200, checkin_time=checkin_time, **details)


@ticket_bp.route('/api/checkin', methods=['POST'])
def api_checkin():
    """The check-in endpoint every scanner uses: the coordinator, SPOC and HUD
    scanners, a USB scanner typing into the kiosk, and the offline queue.
    Takes the scanned ticket link or token, never a registration ID."""
    data = request.get_json(silent=True) or request.form
    token = _token_from_scan(data.get('token', ''))
    is_valid, reg_id, token_event_id, _, extra = _parse_signed_token(token)
    if not is_valid or not reg_id:
        return jsonify({'status': 'invalid', 'success': False,
                        'message': "Not a valid ticket. Scan the ticket's QR code; registration IDs aren't accepted."}), 400
    body, status = check_in(reg_id, session, expected_event_id=(data.get('event_id') or '').strip() or None,
                            source=(data.get('source') or 'scan')[:20], token_extra=extra)
    return jsonify(body), status


@ticket_bp.route('/api/session_checkin', methods=['POST'])
def api_session_checkin():
    """A scan in the scanner's session mode (UPG-159): the same signed ticket,
    recorded at one agenda session. The person is checked in to the event
    first, through the shared check-in, if they aren't yet (so the gate's
    rules hold). A session at capacity answers 409 session_full and records
    nothing, unless the scanner admits them anyway (allow_over)."""
    import services_sessions
    data = request.get_json(silent=True) or request.form
    token = _token_from_scan(data.get('token', ''))
    is_valid, reg_id, _, _, extra = _parse_signed_token(token)
    if not is_valid or not reg_id:
        return jsonify({'status': 'invalid', 'success': False,
                        'message': "Not a valid ticket. Scan the ticket's QR code."}), 400
    event_id = (data.get('event_id') or '').strip()
    if not event_id:
        return jsonify({'status': 'invalid', 'success': False, 'message': 'Choose the event first.'}), 400
    ev_doc = _db().collection('events').document(event_id).get()
    sess = services_sessions.find(ev_doc.to_dict() or {}, data.get('session_id')) if ev_doc.exists else None
    if sess is None:
        return jsonify({'status': 'invalid', 'success': False,
                        'message': 'That session is not on the schedule. Reload the scanner.'}), 404

    # The event's check-in first: permission, the right event, payment, cancellation
    body, status = check_in(reg_id, session, expected_event_id=event_id, source='session scan', token_extra=extra)
    if status != 200:
        return jsonify(body), status
    entered_event = body['status'] == 'success'
    allow_over = str(data.get('allow_over') or '').lower() in ('1', 'true', 'yes')
    first = services_sessions.scanned_at(reg_id, sess['id'])
    if first is None:
        if services_sessions.is_full(event_id, sess) and not allow_over:
            return jsonify(dict(body, status='session_full', success=False, entered_event=entered_event,
                                session=services_sessions.label(sess),
                                message=f"{sess.get('title')} is full ({sess.get('capacity')} seats). "
                                        "Admit anyway only if there's room.")), 409
        first = services_sessions.attend(event_id, sess['id'], reg_id, session.get('user_id') or '',
                                         over_capacity=allow_over)
    if first is not None:   # scanned into this session before (or by another scanner just now)
        return jsonify(dict(body, status='already_in', success=True, already_present=True,
                            entered_event=entered_event, session=services_sessions.label(sess),
                            message=f"Already in {sess.get('title')}" + (f" since {first[:5]}." if first else "."))), 200
    log_action(_db(), "SESSION_CHECKIN", f"Reg {reg_id} into session {sess['id']} of {event_id}"
               + (" (over capacity)" if allow_over else ""))
    return jsonify(dict(body, status='success', success=True, already_present=False, entered_event=entered_event,
                        session=services_sessions.label(sess), seats_taken=services_sessions.count(event_id, sess['id']),
                        capacity=sess.get('capacity') or None,
                        message=f"In {sess.get('title')}." + (" Also checked in to the event." if entered_event else ""))), 200


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
        token = ticket_token_for(reg_id, reg)
        verify_url = f"{_base_url()}/ticket/verify/{token}"
        qr_b64     = generate_qr_base64(verify_url)

    # A placement drive shows the student's current round and result (UPG-57)
    from services_placement import current_round, is_placement
    placement_status = current_round(event, reg) if is_placement(event) else None
    from services_rounds import status_for   # a multi-round competition (UPG-149)
    round_status = None if placement_status is not None else status_for(event, reg)

    # Add to Apple / Google Wallet, each only once its keys are set (UPG-156)
    import services_wallet
    active = str(reg.get('status') or '').lower() != 'cancelled'
    wallet = {'apple': bool(show_qr and active and services_wallet.apple_configured()),
              'google': bool(show_qr and active and services_wallet.google_configured())}

    import services_event_contact   # the event's own guidelines and support email (UPG-242)
    return render_template(
        'participant/ticket.html',
        ticket_guidelines=services_event_contact.guidelines(event),
        support_email=services_event_contact.support_email(event),
        reg=reg,
        reg_id=reg_id,
        event=event,
        qr_b64=qr_b64,
        verify_url=verify_url,
        show_qr=show_qr,
        event_date=event_date_str,
        placement_status=placement_status,
        round_status=round_status,
        wallet=wallet,
    )


# =========================================================
# 1b. WALLET PASSES (UPG-156)
#    The same people as the ticket page, from the same day as its QR; the
#    pass carries the ticket's verify link with its signed token.
# =========================================================
def _wallet_ticket(reg_id):
    """(reg, event, verify_url) for a pass the user may have, else aborts."""
    user_email = (session.get('user_id') or '').lower()
    reg_doc = _db().collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        abort(404)
    reg = reg_doc.to_dict() or {}
    event_doc = _db().collection('events').document(reg.get('event_id', '')).get()
    event = (event_doc.to_dict() or {}) if event_doc.exists else {}
    is_owner = (reg.get('lead_email') or '').lower() == user_email or any(
        (m.get('email') or '').lower() == user_email for m in reg.get('members') or [])
    is_staff = _can_manage_event(session.get('user_id'), session.get('role', ''), event,
                                 session.get('category', 'General'))
    if not (is_owner or is_staff):
        abort(403)
    if str(reg.get('status') or '').lower() == 'cancelled':
        abort(404)
    event_date = str(event.get('date', ''))[:10]
    if not is_staff and event_date:
        try:
            event_d = datetime.date.fromisoformat(event_date)
            today_d = datetime.date.fromisoformat(_ist_today())
            if not (event_d - datetime.timedelta(days=1)) <= today_d <= event_d:
                abort(403)   # the QR, and so the pass, opens the day before
        except ValueError:
            pass
    token = ticket_token_for(reg_id, reg)
    return reg, event, f"{_base_url()}/ticket/verify/{token}"


# =========================================================
# 1c. NAME BADGES (UPG-158) — the event's check-in staff only
# =========================================================
def _staff_event_or_abort(event_id):
    from services_permission import can
    doc = _db().collection('events').document(event_id).get() if event_id else None
    if doc is None or not doc.exists:
        abort(404)
    event = dict(doc.to_dict() or {}, id=event_id)
    if not can(session, 'check_in', event, db=_db()):
        abort(403)
    return event


def _badge_pdf(body, name):
    from flask import Response
    return Response(body, mimetype='application/pdf', headers={
        'Content-Disposition': f'inline; filename="{name}.pdf"', 'Cache-Control': 'no-store'})


def _qr_text(reg_id, reg):
    token = ticket_token_for(reg_id, reg)
    return f"{_base_url()}/ticket/verify/{token}"


@ticket_bp.route('/badges/<event_id>.pdf')
@login_required
def event_badges_pdf(event_id):
    """Every confirmed registration's badges, 8 to an A4 page, then staff badges."""
    import services_badges
    event = _staff_event_or_abort(event_id)
    badges = services_badges.event_badges(_db(), event_id, event, _qr_text)
    log_action(_db(), "BADGES_PRINTED", f"{session.get('user_id')} printed {len(badges)} badges for {event_id}")
    return _badge_pdf(services_badges.render(badges, event), f"badges-{event_id}")


@ticket_bp.route('/<reg_id>/badge.pdf')
@login_required
def registration_badge_pdf(reg_id):
    """One registration's badges (a team's members each), for the door."""
    import services_badges
    reg_doc = _db().collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        abort(404)
    reg = reg_doc.to_dict() or {}
    event = _staff_event_or_abort(str(reg.get('event_id') or ''))
    if str(reg.get('status') or '').strip().lower() in ('cancelled', 'refunded'):
        abort(404)
    badges = services_badges.participant_badges(reg_id, reg, event, _qr_text(reg_id, reg))
    return _badge_pdf(services_badges.render(badges, event, single=True), f"badge-{reg.get('reg_id') or reg_id}")


@ticket_bp.route('/<reg_id>/wallet/apple.pkpass')
@login_required
def apple_wallet_pass(reg_id):
    import services_wallet
    if not services_wallet.apple_configured():
        abort(404)
    reg, event, verify_url = _wallet_ticket(reg_id)
    body = services_wallet.build_pkpass(reg_id, reg, event, verify_url)
    from flask import Response
    return Response(body, mimetype='application/vnd.apple.pkpass', headers={
        'Content-Disposition': f'attachment; filename="ticket-{reg.get("reg_id") or reg_id}.pkpass"',
        'Cache-Control': 'no-store'})


@ticket_bp.route('/<reg_id>/wallet/google')
@login_required
def google_wallet_pass(reg_id):
    import services_wallet
    if not services_wallet.google_configured():
        abort(404)
    reg, event, verify_url = _wallet_ticket(reg_id)
    return redirect(services_wallet.google_save_url(reg_id, reg, reg.get('event_id', ''), event, verify_url,
                                                    origin=_base_url().rstrip('/')))


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
    token = ticket_token_for(reg_id, reg)
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
    # Whoever may check in at this event gets the button (UPG-02: can(), as the POST)
    can_checkin = bool(user_email and event and _can_manage_event(user_email, user_role, dict(event, id=event_id), user_cat))

    # --- GET: Read-only validation (name + event only; never mutates data) ---
    if request.method == 'GET':
        if db_exists and reg:
            if not token_is_current(reg, extra):   # UPG-161
                return render_template(
                    'coordinator/verify_result.html',
                    status='invalid',
                    message=TRANSFERRED_MESSAGE,
                    reg={'lead_name': '', 'reg_id': reg_id},
                    event={'title': event.get('title', 'Event') if event else 'Event'},
                    can_checkin=False,
                    token=token
                ), 409
            if not payment_allows_entry(reg, event):
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
                can_checkin=False,
                token=token
            )

    # --- POST: Mark attendance through the shared check-in (UPG-02) ---
    if not user_email:
        flash("Please log in as staff to check in attendees.", "danger")
        return redirect('/login')

    result, http = check_in(reg_id, session, source='verify page', token_extra=extra)
    if http == 403:
        abort(403)
    page_status = {'success': 'success', 'already_in': 'already_in', 'unpaid': 'unpaid'}.get(result['status'], 'invalid')
    message = 'Entry granted! Attendance marked.' if page_status == 'success' else result['message']
    return render_template(
        'coordinator/verify_result.html',
        status=page_status,
        message=message,
        reg={'lead_name': result.get('name') or lead_name, 'reg_id': reg_id,
             'attendance': 'Present' if result['success'] else 'Pending',
             'checkin_time': result.get('checkin_time')},
        event={'title': result.get('event_title') or (event.get('title', 'Event') if event else 'Event')},
        can_checkin=False
    ), (404 if http == 404 else 200)


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
            if not token_is_current(reg, extra):   # UPG-161
                return jsonify({'status': 'transferred', 'message': TRANSFERRED_MESSAGE}), 409
            if not payment_allows_entry(reg, event):
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
    if not user_email:
        return jsonify({'status': 'error', 'message': 'Staff authentication required to mark attendance'}), 403
    actor = {'user_id': user_email, 'role': user_role, 'category': user_cat}

    if reg:  # the shared check-in (UPG-02)
        body, http = check_in(reg_id, actor, source='api verify', token_extra=extra)
        return jsonify(body), http

    if ticket_data:  # a wallet ticket with no registration behind it
        if user_role not in COORD_ROLES or (event and not _can_manage_event(user_email, user_role, event, user_cat)):
            return jsonify({'status': 'error', 'message': 'Forbidden: You cannot manage attendance for this event'}), 403
        from services_ticket import TicketService
        tkt_res = TicketService.checkin_ticket(_db(), token)
        if tkt_res.get("status") == "success":
            return jsonify({
                'status': 'success',
                'message': 'Entry granted',
                'name': lead_name,
                'checkin_time': _now(),
                'ticket_type': ticket_data.get('ticket_type', 'General')
            }), 200
        elif tkt_res.get("status") == "already_used":
            return jsonify({'status': 'already_in', 'message': 'Already checked in', 'name': lead_name}), 200
        else:
            return jsonify({'status': tkt_res.get("status", "error"), 'message': tkt_res.get("message", "Error")}), 400

    return jsonify({'status': 'invalid', 'message': 'Ticket not found.'}), 404


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
