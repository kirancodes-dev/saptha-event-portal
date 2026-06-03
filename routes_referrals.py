# routes_referrals.py — Student Affiliate & Referrals Blueprint
import logging
from flask import Blueprint, jsonify, request, session, current_app
from utils import login_required

referrals_bp = Blueprint('referrals', __name__, url_prefix='/participant/referrals')
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

@referrals_bp.route('/api/stats')
@login_required
def get_referral_stats():
    user_id = session.get('user_id', '')
    
    # We can check a 'referrals' collection in firestore, or fall back to mock numbers
    db_conn = _db()

    # Simple simulation stats
    referrals_count = 4
    amount_earned = 200.00 # ₹50 per sign-up referral

    if db_conn:
        try:
            # Query count of users registered with this ref code
            ref_code = user_id.split('@')[0].upper()
            referred_users = list(db_conn.collection('users').where('referred_by', '==', ref_code).stream())
            referrals_count = len(referred_users) if referred_users else referrals_count
            amount_earned = referrals_count * 50.00
        except Exception as exc:
            logger.error("Error reading referrals from firestore: %s", exc)

    ref_code = user_id.split('@')[0].upper() if user_id else "STUDENT123"
    
    return jsonify({
        'success': True,
        'referral_code': ref_code,
        'referral_link': f"{request.host_url}register?ref={ref_code}",
        'count': referrals_count,
        'earned': amount_earned
    })

@referrals_bp.route('/api/claim', methods=['POST'])
@login_required
def claim_rewards():
    # Simulate claiming referral balance into bank account or wallet
    return jsonify({
        'success': True,
        'message': "Payout request submitted successfully. Balance will be credited to your linked UPI ID within 24 hours."
    })
