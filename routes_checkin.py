"""
routes_checkin.py — Secure Check-in Engine (Self check-in & Kiosk)
=================================================================
Roles & Permissions:
- Kiosk search and confirm: Requires staff login (COORD_ROLES) and event management permission.
- Venue QR code: Generates a short-lived (10-minute) cryptographically signed token.
- Self check-in submit: Requires logged-in participant owning the registration + valid signed venue code.
- Kiosk search: Requires event_id, queries only that event, caps at 20, returns NO emails or phone numbers.
"""
import datetime
import logging
from flask import (Blueprint, flash, jsonify, redirect, render_template,
                   request, session, current_app, Response, abort)
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None

from models import db
from utils import login_required, role_required

logger = logging.getLogger(__name__)

checkin_bp = Blueprint('checkin', __name__, url_prefix='/checkin')

COORD_ROLES = ['ClubSPOC', 'Coordinator', 'EventCoordinator', 'SuperAdmin', 'Super Admin', 'Admin']


def _db():
    try:
        from app import db as app_db
        if app_db is not None:
            return app_db
    except Exception:
        pass
    return db


def _get_venue_serializer():
    secret = current_app.config.get('SECRET_KEY')
    if not secret:
        raise RuntimeError("SECRET_KEY must be configured in Flask application.")
    return URLSafeTimedSerializer(secret, salt='venue-qr-checkin-salt')


def _can_manage_event(user_email: str, user_role: str, event_data: dict, user_category: str = 'General') -> bool:
    if not user_email:
        return False
    from services_permission import can
    user_dict = {
        'user_id': user_email,
        'email': user_email,
        'role': user_role,
        'category': user_category,
    }
    if event_data:
        evt_dict = dict(event_data)
        return can(user_dict, 'check_in', evt_dict, db=_db())
    return can(user_dict, 'check_in', None, db=_db())


# ── 1. Venue QR landing page ──────────────────────────────────────────
@checkin_bp.route('/<event_id>')
def self_checkin_page(event_id):
    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        return render_template('404.html'), 404

    event = event_doc.to_dict()
    event['id'] = event_id

    if not event.get('allow_self_checkin'):
        return render_template('public/checkin_disabled.html', event=event)

    if event.get('status') != 'active':
        return render_template('public/checkin_closed.html', event=event)

    code = request.args.get('code', '').strip()
    pre_email = session.get('user_id') if session.get('role') == 'Student' else ''
    return render_template('public/self_checkin.html', event=event, pre_email=pre_email, code=code)


# ── 2. Submit self check-in ───────────────────────────────────────────
@checkin_bp.route('/<event_id>/submit', methods=['POST'])
@login_required
def submit_self_checkin(event_id):
    # Require logged-in participant
    user_email = session.get('user_id', '').lower().strip()
    if not user_email:
        flash("Please log in to check in to this event.", "warning")
        return redirect('/login')

    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        return jsonify({'error': 'Event not found'}), 404

    event = event_doc.to_dict()
    if not event.get('allow_self_checkin'):
        return jsonify({'error': 'Self check-in is not enabled for this event'}), 403
    if event.get('status') != 'active':
        return jsonify({'error': 'Event is not active'}), 400

    # Validate short-lived venue code
    code = (request.form.get('code') or request.args.get('code') or '').strip()
    if not code:
        flash("Invalid or missing venue QR code. Please scan the current venue QR code at the desk.", "danger")
        return redirect(f'/checkin/{event_id}')

    serializer = _get_venue_serializer()
    try:
        payload = serializer.loads(code, max_age=600)  # ~10 minutes
        if str(payload.get('event_id')) != str(event_id):
            flash("Venue QR code is for a different event.", "danger")
            return redirect(f'/checkin/{event_id}')
    except SignatureExpired:
        flash("Venue QR code has expired. Please rescan the live venue screen.", "danger")
        return redirect(f'/checkin/{event_id}')
    except (BadSignature, Exception):
        flash("Invalid venue QR code. Tampering detected.", "danger")
        return redirect(f'/checkin/{event_id}')

    # Find registration belonging to the logged-in user
    regs = list(
        _db().collection('registrations')
          .where(filter=FieldFilter('event_id', '==', event_id))
          .where(filter=FieldFilter('lead_email', '==', user_email))
          .limit(1).stream()
    )
    if not regs:
        # Check team member
        all_regs = _db().collection('registrations').where(filter=FieldFilter('event_id', '==', event_id)).stream()
        for r in all_regs:
            r_data = r.to_dict()
            if any((m.get('email') or '').lower() == user_email for m in r_data.get('members', [])):
                regs = [r]
                break

    if not regs:
        flash("No registration found under your account for this event.", "danger")
        return redirect(f'/checkin/{event_id}')

    reg_doc  = regs[0]
    reg      = reg_doc.to_dict()
    reg_id   = reg_doc.id

    if reg.get('attendance') == 'Present':
        return render_template('public/checkin_already.html',
                               event=event, name=reg.get('lead_name', ''))

    checkin_time = datetime.datetime.now().strftime("%H:%M:%S")
    _db().collection('registrations').document(reg_id).update({
        'attendance':        'Present',
        'checkin_time':      checkin_time,
        'self_checkin':      True,
    })

    # Award +150 XP for self check-in
    try:
        from routes_gamification import award_xp
        award_xp(user_email, 150)
    except Exception:
        pass

    return render_template('public/checkin_success.html',
                           event=event,
                           name=reg.get('lead_name', ''),
                           team=reg.get('team_name', ''),
                           checkin_time=checkin_time)


# ── 3. SPOC: toggle self-checkin on/off ────────────────────────────────
@checkin_bp.route('/toggle/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def toggle_self_checkin(event_id):
    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')

    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect('/spoc/dashboard')

    event_data = event_doc.to_dict() or {}
    if not _can_manage_event(user_email, user_role, event_data, user_cat):
        abort(403)

    current = event_data.get('allow_self_checkin', False)
    _db().collection('events').document(event_id).update({'allow_self_checkin': not current})
    state = 'enabled' if not current else 'disabled'
    flash(f"Self check-in {state} for this event.", "success")
    return redirect('/spoc/dashboard')


# ── 4. SPOC: get venue QR PNG ─────────────────────────────────────────
@checkin_bp.route('/venue_qr/<event_id>')
@login_required
@role_required(COORD_ROLES)
def venue_qr(event_id):
    """Return a short-lived (~10 min) QR code PNG for the venue self-checkin URL."""
    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')

    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        return jsonify({'error': 'Event not found'}), 404

    event_data = event_doc.to_dict() or {}
    if not _can_manage_event(user_email, user_role, event_data, user_cat):
        return jsonify({'error': 'Forbidden'}), 403

    import io
    try:
        import qrcode
    except ImportError:
        return jsonify({'error': 'qrcode library not installed'}), 500

    # Generate ~10-minute signed token
    serializer = _get_venue_serializer()
    venue_code = serializer.dumps({'event_id': str(event_id)})

    from utils_email import _base_url  # BASE_URL, never the request's host (BLK-16)
    url = f"{_base_url()}/checkin/{event_id}?code={venue_code}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return Response(buf.read(), mimetype='image/png')


# ── 5. Live Self-Serve Check-in Kiosk Interface ────────────────────────
@checkin_bp.route('/kiosk')
@login_required
@role_required(COORD_ROLES)
def kiosk_page():
    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')
    event_id   = request.args.get('event_id', '').strip()

    all_events = _db().collection('events').stream()
    managed_events = []
    for edoc in all_events:
        edata = edoc.to_dict() or {}
        edata['id'] = edoc.id
        if _can_manage_event(user_email, user_role, edata, user_cat):
            managed_events.append(edata)

    return render_template('public/kiosk.html', events=managed_events, selected_event_id=event_id)


@checkin_bp.route('/kiosk/search', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def kiosk_search():
    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')

    data = request.get_json(silent=True) or {}
    event_id = (data.get('event_id') or request.args.get('event_id') or '').strip()
    if not event_id:
        return jsonify({'success': False, 'error': 'event_id is required'}), 400

    event_doc = _db().collection('events').document(event_id).get()
    if not event_doc.exists:
        return jsonify({'success': False, 'error': 'Event not found'}), 404

    event_data = event_doc.to_dict() or {}
    if not _can_manage_event(user_email, user_role, event_data, user_cat):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({'success': True, 'results': []})

    query_lower = query.lower()
    event_title = event_data.get('title', 'Event')
    results = []
    seen_ids = set()

    def add_to_results(doc_id, reg_data):
        if doc_id in seen_ids or len(results) >= 20:
            return
        # ONLY return reg id, name, team name, attendance status, event_title.
        # NEVER return lead_email, member emails, or phone numbers.
        results.append({
            'reg_id': str(doc_id),
            'event_title': event_title,
            'lead_name': reg_data.get('lead_name', ''),
            'team_name': reg_data.get('team_name', ''),
            'attendance': reg_data.get('attendance', 'Pending')
        })
        seen_ids.add(doc_id)

    # 1. Exact Reg ID Lookup (within this event only)
    try:
        reg_doc = _db().collection('registrations').document(query).get()
        if reg_doc.exists:
            r_dict = reg_doc.to_dict()
            if str(r_dict.get('event_id')) == str(event_id):
                add_to_results(reg_doc.id, r_dict)
    except Exception:
        pass

    # 2. Query only this event
    try:
        regs = _db().collection('registrations').where(filter=FieldFilter('event_id', '==', str(event_id))).stream()
        for r in regs:
            if len(results) >= 20:
                break
            reg = r.to_dict()
            if str(reg.get('event_id')) != str(event_id):
                continue
            lead_name = (reg.get('lead_name') or '').lower()
            team_name = (reg.get('team_name') or '').lower()

            if query_lower in lead_name or query_lower in team_name or query_lower == str(r.id).lower():
                add_to_results(r.id, reg)
                continue

            for m in reg.get('members', []):
                m_name = (m.get('name') or '').lower()
                m_usn  = (m.get('usn') or '').lower()
                if query_lower in m_name or query_lower == m_usn:
                    add_to_results(r.id, reg)
                    break
    except Exception as exc:
        logger.error("Error searching registrations in kiosk: %s", exc)

    return jsonify({'success': True, 'results': results})


@checkin_bp.route('/kiosk/confirm/<reg_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def kiosk_confirm(reg_id):
    user_email = session.get('user_id')
    user_role  = session.get('role', '')
    user_cat   = session.get('category', 'General')

    try:
        reg_doc = _db().collection('registrations').document(reg_id).get()
        if not reg_doc.exists:
            return jsonify({'success': False, 'error': 'Registration not found.'}), 404

        reg = reg_doc.to_dict() or {}
        event_id = reg.get('event_id')
        if not event_id:
            return jsonify({'success': False, 'error': 'Registration has no associated event.'}), 400

        event_doc = _db().collection('events').document(str(event_id)).get()
        if not event_doc.exists:
            return jsonify({'success': False, 'error': 'Event not found.'}), 404

        evt = event_doc.to_dict() or {}
        if not _can_manage_event(user_email, user_role, evt, user_cat):
            return jsonify({'success': False, 'error': 'Forbidden: You cannot manage this event.'}), 403

        event_title = evt.get('title', 'Event')
        if evt.get('status') != 'active':
            return jsonify({'success': False, 'error': f"Event '{event_title}' is not active."}), 400

        if reg.get('attendance') == 'Present':
            return jsonify({
                'success': True,
                'already_present': True,
                'message': f"{reg.get('lead_name')} is already checked in.",
                'lead_name': reg.get('lead_name'),
                'team_name': reg.get('team_name', ''),
                'event_title': event_title
            })

        checkin_time = datetime.datetime.now().strftime("%H:%M:%S")
        _db().collection('registrations').document(reg_id).update({
            'attendance': 'Present',
            'checkin_time': checkin_time,
            'kiosk_checkin': True
        })

        try:
            from routes_gamification import award_xp
            award_xp(reg.get('lead_email', ''), 150)
        except Exception:
            pass

        return jsonify({
            'success': True,
            'message': f"Successfully checked in {reg.get('lead_name')}!",
            'lead_name': reg.get('lead_name'),
            'team_name': reg.get('team_name', ''),
            'checkin_time': checkin_time,
            'event_title': event_title
        })
    except Exception as exc:
        logger.error("Error in kiosk confirm: %s", exc)
        return jsonify({'success': False, 'error': str(exc)}), 500
