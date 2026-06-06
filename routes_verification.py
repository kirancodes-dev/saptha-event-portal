# routes_verification.py — Cryptographic Certificate & Registration Verification Blueprint
import logging
from flask import Blueprint, render_template

verification_bp = Blueprint('verification', __name__)
logger = logging.getLogger(__name__)

def _db():
    try:
        import app as app_module
        if hasattr(app_module, 'db') and app_module.db is not None:
            return app_module.db
    except Exception:
        pass
    try:
        from models import db
        return db
    except Exception:
        return None

@verification_bp.route('/verify/<cert_hash>')
def verify_certificate(cert_hash):
    db_conn = _db()
    if not db_conn:
        return render_template('public/verify_certificate.html', 
                               success=False, 
                               error="Database connection unavailable"), 500

    try:
        # 1. Try to find in verified_certificates (cryptographic hash)
        doc = db_conn.collection('verified_certificates').document(cert_hash).get()
        if doc.exists:
            cert_data = doc.to_dict()
            return render_template('public/verify_certificate.html', 
                                   success=True, 
                                   cert=cert_data)

        # 2. Otherwise try to find in registrations (legacy verification by ID)
        reg_doc = db_conn.collection('registrations').document(cert_hash).get()
        if reg_doc.exists:
            data = reg_doc.to_dict()
            if data.get('attendance') != 'Present':
                return render_template('public/verify_fail.html',
                                       reg_id=cert_hash, reason='Absent'), 400
            
            event_doc = db_conn.collection('events').document(data['event_id']).get()
            event = event_doc.to_dict() if event_doc.exists else {}
            
            student_usn = None
            lead_email = data.get('lead_email')
            if lead_email:
                user_doc = db_conn.collection('users').document(lead_email).get()
                if user_doc.exists:
                    student_usn = (user_doc.to_dict() or {}).get('usn')
                    
            return render_template(
                'public/verify_success.html',
                data=data, event=event, student_usn=student_usn)

        # 3. Not found in either (Invalid Hash/ID -> return 404 for REST compliance and testing)
        return render_template('public/verify_certificate.html', 
                               success=False, 
                               error="This certificate hash is invalid or was not issued by our system."), 404
    except Exception as exc:
        logger.error("Verification error: %s", exc)
        return render_template('public/verify_certificate.html', 
                               success=False, 
                               error="An internal error occurred during verification."), 500


@verification_bp.route('/verify/<cert_hash>/preview')
def verify_certificate_preview(cert_hash):
    db_conn = _db()
    if not db_conn:
        return "Database connection unavailable", 500

    try:
        # Try finding in verified_certificates (cryptographic hash)
        doc = db_conn.collection('verified_certificates').document(cert_hash).get()
        if doc.exists:
            cert_data = doc.to_dict()
            student_name = cert_data.get('student_name', 'Participant')
            event_title = cert_data.get('event_title', 'Event')
            cert_type = cert_data.get('cert_type', 'participation')
            rank = cert_data.get('rank', 0)
            score = cert_data.get('score', 0)
            event = {
                'title': event_title,
                'date': cert_data.get('issued_at', '')[:10],
                'venue': 'Main Campus'
            }
            return render_template('public/certificate_preview_embed.html',
                                   student_name=student_name,
                                   event=event,
                                   cert_type=cert_type,
                                   rank=rank,
                                   score=score)

        # Otherwise find in registrations (legacy verification by ID)
        reg_doc = db_conn.collection('registrations').document(cert_hash).get()
        if reg_doc.exists:
            data = reg_doc.to_dict()
            student_name = data.get('lead_name', 'Participant')
            cert_type = 'winner' if data.get('final_rank') else 'participation'
            rank = data.get('final_rank', 0)
            score = data.get('final_score', 0)

            event_doc = db_conn.collection('events').document(data['event_id']).get()
            event = event_doc.to_dict() if event_doc.exists else {'title': 'Event'}

            return render_template('public/certificate_preview_embed.html',
                                   student_name=student_name,
                                   event=event,
                                   cert_type=cert_type,
                                   rank=rank,
                                   score=score)

        return "Certificate not found", 404
    except Exception as exc:
        logger.error("Preview certificate error: %s", exc)
        return "Internal server error", 500


@verification_bp.route('/verify/<cert_hash>/download')
def verify_certificate_download(cert_hash):
    db_conn = _db()
    if not db_conn:
        return "Database connection unavailable", 500

    try:
        # 1. Fetch info
        doc = db_conn.collection('verified_certificates').document(cert_hash).get()
        if doc.exists:
            cert_data = doc.to_dict()
            student_name = cert_data.get('student_name', 'Participant')
            event_title = cert_data.get('event_title', 'Event')
            cert_type = cert_data.get('cert_type', 'participation')
            rank = cert_data.get('rank', 0)
            score = cert_data.get('score', 0)
            event_date = cert_data.get('issued_at', '')[:10]
            college_name = cert_data.get('college_name', 'Sapthagiri NPS University')
        else:
            reg_doc = db_conn.collection('registrations').document(cert_hash).get()
            if not reg_doc.exists:
                return "Certificate not found", 404
            data = reg_doc.to_dict()
            student_name = data.get('lead_name', 'Participant')
            cert_type = 'winner' if data.get('final_rank') else 'participation'
            rank = data.get('final_rank', 0)
            score = data.get('final_score', 0)

            event_doc = db_conn.collection('events').document(data['event_id']).get()
            event = event_doc.to_dict() if event_doc.exists else {}
            event_title = event.get('title', 'Event')
            event_date = event.get('date', '')
            college_name = 'Sapthagiri NPS University'

        # 2. Generate PDF bytes dynamically
        from utils_certificate import generate_certificate_pdf
        from utils_email import _base_url
        from flask import send_file
        import io

        pdf_bytes = generate_certificate_pdf(
            student_name=student_name,
            event_title=event_title,
            reg_id=cert_hash,
            cert_type=cert_type,
            rank=rank,
            score=score,
            event_date=event_date,
            base_url=_base_url(),
            college_name=college_name
        )

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"Certificate_{student_name.replace(' ', '_')}_{cert_hash}.pdf"
        )
    except Exception as exc:
        logger.error("Download certificate error: %s", exc)
        return "Internal server error generating PDF", 500

