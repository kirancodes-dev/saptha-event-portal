"""
routes_push.py — browser push subscriptions (UPG-157). The sending is in
services_push; everything here is off until the VAPID keys are set.
"""
from flask import Blueprint, jsonify, request, session

import services_push

push_bp = Blueprint('push', __name__, url_prefix='/push')


@push_bp.route('/vapid_public_key')
def vapid_public_key():
    return jsonify({'key': services_push.public_key() if services_push.configured() else ''})


@push_bp.route('/subscribe', methods=['POST'])
def subscribe():
    """Save this browser's subscription for the logged-in user."""
    if not session.get('user_id'):
        return jsonify({'error': 'Log in to get notifications on this device.'}), 401
    if not services_push.configured():
        return jsonify({'error': 'Notifications are not set up.'}), 404
    if not services_push.subscribe(session['user_id'], request.get_json(silent=True) or {}):
        return jsonify({'error': 'Invalid subscription'}), 400
    return jsonify({'ok': True})


@push_bp.route('/unsubscribe', methods=['POST'])
def unsubscribe():
    if not session.get('user_id'):
        return jsonify({'error': 'Log in first.'}), 401
    endpoint = str((request.get_json(silent=True) or {}).get('endpoint') or '')
    services_push.unsubscribe(session['user_id'], endpoint)
    return jsonify({'ok': True})

