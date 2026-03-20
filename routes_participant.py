import io
import datetime
from flask import (Blueprint, Response, flash, redirect,
                   render_template, request, session, send_file)
from google.cloud.firestore_v1.base_query import FieldFilter
from models import db
from utils import login_required

participant_bp = Blueprint('participant', __name__, url_prefix='/participant')

def _ff(f, op, v):
    return FieldFilter(f, op, v)


# =========================================================
# DASHBOARD
# =========================================================
@participant_bp.route('/dashboard')
@login_required
def dashboard():
    email = session.get('user_id')
    name  = session.get('name', 'Student')

    try:
        regs_raw = list(
            db.collection('registrations')
              .where(filter=_ff('lead_email', '==', email))
              .stream()
        )
    except Exception as exc:
        flash(f"Error loading your registrations: {exc}", "danger")
        regs_raw = []

    registrations = []
    for r in regs_raw:
        d         = r.to_dict()
        d['id']   = r.id
        d['reg_id'] = d.get('reg_id', r.id)
        event_id  = d.get('event_id', '')

        # Fetch event details
        try:
            ev_doc  = db.collection('events').document(event_id).get()
            ev_data = ev_doc.to_dict() if ev_doc.exists else {}
        except Exception:
            ev_data = {}

        d['event']          = ev_data
        d['event_title']    = ev_data.get('title',  d.get('event_title', 'Event'))
        d['event_date']     = ev_data.get('date',   'TBD')
        d['event_venue']    = ev_data.get('venue',  'SNPSU Campus')
        d['event_status']   = ev_data.get('status', 'active')
        d['event_category'] = ev_data.get('category', 'General')

        # Score / rank
        d['final_score'] = d.get('final_score', '')
        d['final_rank']  = d.get('final_rank',  '')

        # Attendance
        d['attendance']   = d.get('attendance', 'Pending')
        d['checkin_time'] = d.get('checkin_time', '')

        # Status flags
        d['is_eliminated']   = d.get('is_eliminated', False)
        d['payment_status']  = d.get('payment_status', 'Free')
        d['current_round']   = d.get('current_round', 1)

        registrations.append(d)

    # Sort: active events first, then by registration date descending
    registrations.sort(
        key=lambda x: (
            0 if x['event_status'] == 'active' else 1,
            x.get('registered_at', ''),
        ),
        reverse=False
    )
    registrations.sort(key=lambda x: x.get('registered_at', ''), reverse=True)

    active_count    = sum(1 for r in registrations if r['event_status'] == 'active')
    completed_count = sum(1 for r in registrations if r['event_status'] != 'active')
    present_count   = sum(1 for r in registrations if r['attendance'] == 'Present')

    return render_template(
        'participant/dashboard.html',
        registrations=registrations,
        name=name,
        email=email,
        active_count=active_count,
        completed_count=completed_count,
        present_count=present_count,
        total=len(registrations),
    )


# =========================================================
# QR TICKET DOWNLOAD
# =========================================================
@participant_bp.route('/qr/<reg_id>')
@login_required
def download_qr(reg_id):
    """Generate and return QR code PNG for a registration."""
    try:
        reg_doc = db.collection('registrations').document(reg_id).get()
        if not reg_doc.exists:
            flash("Registration not found.", "danger")
            return redirect('/participant/dashboard')

        reg_data = reg_doc.to_dict()
        # Security: only the owner can download
        if reg_data.get('lead_email') != session.get('user_id'):
            flash("Access denied.", "danger")
            return redirect('/participant/dashboard')

        from utils_qr import generate_qr_bytes
        from flask import current_app
        base_url   = current_app.config.get('BASE_URL', '')
        verify_url = f"{base_url}/ticket/verify/{reg_id}" if base_url else reg_id
        qr_bytes   = generate_qr_bytes(verify_url)

        return send_file(
            io.BytesIO(qr_bytes),
            mimetype='image/png',
            as_attachment=True,
            download_name=f"QR_{reg_id}.png"
        )
    except Exception as exc:
        flash(f"QR generation failed: {exc}", "danger")
        return redirect('/participant/dashboard')


# =========================================================
# CERTIFICATE DOWNLOAD — regenerate PDF on demand
# =========================================================
@participant_bp.route('/certificate/<reg_id>')
@login_required
def download_certificate(reg_id):
    """Regenerate and download the participant's certificate PDF."""
    try:
        reg_doc = db.collection('registrations').document(reg_id).get()
        if not reg_doc.exists:
            flash("Registration not found.", "danger")
            return redirect('/participant/dashboard')

        reg_data = reg_doc.to_dict()

        # Security: only owner
        if reg_data.get('lead_email') != session.get('user_id'):
            flash("Access denied.", "danger")
            return redirect('/participant/dashboard')

        if reg_data.get('attendance') != 'Present':
            flash("Certificate only available for participants who attended.", "warning")
            return redirect('/participant/dashboard')

        event_id  = reg_data.get('event_id', '')
        ev_doc    = db.collection('events').document(event_id).get()
        ev_data   = ev_doc.to_dict() if ev_doc.exists else {}

        from utils_certificate import generate_certificate_pdf
        from flask import current_app

        base_url    = current_app.config.get('BASE_URL', '')
        final_rank  = reg_data.get('final_rank', 0)
        final_score = reg_data.get('final_score', 0)
        cert_type   = 'winner' if final_rank and int(final_rank) <= 3 else 'participation'
        template_id = int(ev_data.get('cert_template', 1))

        pdf_bytes = generate_certificate_pdf(
            student_name=reg_data.get('lead_name', session.get('name', '')),
            event_title=ev_data.get('title', 'Event'),
            reg_id=reg_id,
            cert_type=cert_type,
            rank=int(final_rank) if final_rank else 0,
            score=float(final_score) if final_score else 0.0,
            event_date=ev_data.get('date', ''),
            base_url=base_url,
            template_id=template_id,
        )

        safe_title = ev_data.get('title', 'Event').replace(' ', '_')[:30]
        label      = 'Achievement' if cert_type == 'winner' else 'Participation'
        filename   = f"Certificate_{label}_{safe_title}.pdf"

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except Exception as exc:
        flash(f"Certificate download failed: {exc}", "danger")
        return redirect('/participant/dashboard')


# =========================================================
# TICKET VIEW PAGE  (keep existing if present)
# =========================================================
@participant_bp.route('/ticket/<reg_id>')
@login_required
def view_ticket(reg_id):
    try:
        reg_doc = db.collection('registrations').document(reg_id).get()
        if not reg_doc.exists:
            flash("Ticket not found.", "danger")
            return redirect('/participant/dashboard')
        d = reg_doc.to_dict()
        if d.get('lead_email') != session.get('user_id'):
            flash("Access denied.", "danger")
            return redirect('/participant/dashboard')
        ev = db.collection('events').document(d.get('event_id','')).get()
        ev_data = ev.to_dict() if ev.exists else {}
        return render_template('participant/ticket.html',
                               reg=d, event=ev_data, reg_id=reg_id)
    except Exception as exc:
        flash(f"Error loading ticket: {exc}", "danger")
        return redirect('/participant/dashboard')