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

    # Award +150 XP for self check-in
    try:
        from routes_gamification import award_xp
        award_xp(email, 150)
    except Exception as e:
        pass

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


# ── 5. Live Self-Serve Check-in Kiosk Interface ────────────────────────────

@checkin_bp.route('/kiosk')
def kiosk_page():
    return render_template('public/kiosk.html')


@checkin_bp.route('/kiosk/search', methods=['POST'])
def kiosk_search():
    query = (request.json or {}).get('query', '').strip()
    if not query:
        return jsonify({'success': True, 'results': []})

    query_lower = query.lower()
    results = []
    seen_ids = set()

    def add_to_results(doc_id, reg_data):
        if doc_id in seen_ids:
            return
        event_id = reg_data.get('event_id')
        evt_title = 'Event'
        if event_id:
            try:
                evt_doc = db.collection('events').document(str(event_id)).get()
                if evt_doc.exists:
                    evt_data = evt_doc.to_dict()
                    evt_title = evt_data.get('title', 'Event')
            except Exception:
                pass
        results.append({
            'reg_id': doc_id,
            'event_title': evt_title,
            'lead_name': reg_data.get('lead_name', ''),
            'lead_email': reg_data.get('lead_email', ''),
            'team_name': reg_data.get('team_name', ''),
            'attendance': reg_data.get('attendance', 'Pending'),
            'members': reg_data.get('members', [])
        })
        seen_ids.add(doc_id)

    # 1. Exact Reg ID Lookup
    try:
        reg_doc = db.collection('registrations').document(query).get()
        if reg_doc.exists:
            add_to_results(reg_doc.id, reg_doc.to_dict())
    except Exception:
        pass

    # 2. Email Query
    try:
        regs = db.collection('registrations').where(filter=FieldFilter('lead_email', '==', query_lower)).stream()
        for r in regs:
            add_to_results(r.id, r.to_dict())
    except Exception:
        pass

    # 3. Stream check for partial matches (lead name, team name, member USN/email/name)
    try:
        regs = db.collection('registrations').stream()
        for r in regs:
            reg = r.to_dict()
            lead_name = reg.get('lead_name', '').lower()
            team_name = reg.get('team_name', '').lower()

            if query_lower in lead_name or query_lower in team_name:
                add_to_results(r.id, reg)
                continue

            for m in reg.get('members', []):
                m_usn = m.get('usn', '').lower()
                m_email = m.get('email', '').lower()
                m_name = m.get('name', '').lower()
                if query_lower == m_usn or query_lower == m_email or query_lower in m_name:
                    add_to_results(r.id, reg)
                    break
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Error streaming registrations in kiosk search: %s", e)

    return jsonify({'success': True, 'results': results})


@checkin_bp.route('/kiosk/confirm/<reg_id>', methods=['POST'])
def kiosk_confirm(reg_id):
    try:
        reg_doc = db.collection('registrations').document(reg_id).get()
        if not reg_doc.exists:
            return jsonify({'success': False, 'error': 'Registration not found.'}), 404

        reg = reg_doc.to_dict()
        event_id = reg.get('event_id')
        event_title = 'Event'
        if event_id:
            try:
                evt_doc = db.collection('events').document(str(event_id)).get()
                if evt_doc.exists:
                    evt = evt_doc.to_dict()
                    event_title = evt.get('title', 'Event')
                    if evt.get('status') != 'active':
                        return jsonify({'success': False, 'error': f"Event '{event_title}' is not active."}), 400
            except Exception:
                pass

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
        db.collection('registrations').document(reg_id).update({
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
        import logging
        logging.getLogger(__name__).error("Error in kiosk confirm: %s", exc)
        return jsonify({'success': False, 'error': str(exc)}), 500
