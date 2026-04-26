"""
routes_push.py — Web Push subscription management + send helper
"""
import json
import os
import datetime
from flask import Blueprint, jsonify, request, session
from models import db
from utils import login_required

push_bp = Blueprint('push', __name__, url_prefix='/push')

VAPID_PUBLIC_KEY  = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_EMAIL       = os.environ.get('VAPID_EMAIL', 'mailto:admin@snpsu.edu.in')


@push_bp.route('/vapid_public_key')
def vapid_public_key():
    return jsonify({'key': VAPID_PUBLIC_KEY})


@push_bp.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    """Save a push subscription for the logged-in user."""
    sub = request.json
    if not sub or not sub.get('endpoint'):
        return jsonify({'error': 'Invalid subscription'}), 400
    uid = session.get('user_id')
    db.collection('push_subscriptions').document(uid).set({
        'user_id':      uid,
        'subscription': sub,
        'updated_at':   datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    return jsonify({'ok': True})


@push_bp.route('/unsubscribe', methods=['POST'])
@login_required
def unsubscribe():
    uid = session.get('user_id')
    db.collection('push_subscriptions').document(uid).delete()
    return jsonify({'ok': True})


# ── Helper: send push to one user ────────────────────────────────────
def send_push(user_id: str, title: str, body: str, url: str = '/'):
    """Fire a Web Push notification to a user. No-op if not subscribed or keys missing."""
    if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
        return
    try:
        from pywebpush import webpush, WebPushException
        doc = db.collection('push_subscriptions').document(user_id).get()
        if not doc.exists:
            return
        sub = doc.to_dict().get('subscription', {})
        webpush(
            subscription_info=sub,
            data=json.dumps({'title': title, 'body': body, 'url': url,
                             'icon': '/static/snpsu-logo.png'}),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={'sub': VAPID_EMAIL},
        )
    except Exception:
        pass
