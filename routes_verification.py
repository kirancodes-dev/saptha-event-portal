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
