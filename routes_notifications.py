"""
routes_notifications.py — In-app notification bell (Firestore-backed)
"""
import datetime
from flask import Blueprint, jsonify, session
from models import db
from utils import login_required

notif_bp = Blueprint('notifications', __name__, url_prefix='/notifications')


@notif_bp.route('/feed')
@login_required
def feed():
    """Return the 20 most recent notifications for the logged-in user."""
    uid = session.get('user_id')
    try:
        docs = (
            db.collection('notifications')
              .where('user_id', '==', uid)
              .order_by('created_at', direction='DESCENDING')
              .limit(20)
              .stream()
        )
        items = []
        for d in docs:
            n = d.to_dict()
            n['id'] = d.id
            items.append(n)
        return jsonify(items)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@notif_bp.route('/mark_read/<notif_id>', methods=['POST'])
@login_required
def mark_read(notif_id):
    uid = session.get('user_id')
    doc = db.collection('notifications').document(notif_id).get()
    if doc.exists and doc.to_dict().get('user_id') == uid:
        db.collection('notifications').document(notif_id).update({'read': True})
    return jsonify({'ok': True})


@notif_bp.route('/mark_all_read', methods=['POST'])
@login_required
def mark_all_read():
    uid = session.get('user_id')
    docs = (
        db.collection('notifications')
          .where('user_id', '==', uid)
          .where('read', '==', False)
          .stream()
    )
    for d in docs:
        d.reference.update({'read': True})
    return jsonify({'ok': True})


# ── Helper called from other routes to push a notification ──────────────
def push_notification(user_id: str, title: str, body: str,
                       icon: str = 'bell', link: str = ''):
    """Write a notification document for a user."""
    try:
        db.collection('notifications').add({
            'user_id':    user_id,
            'title':      title,
            'body':       body,
            'icon':       icon,
            'link':       link,
            'read':       False,
            'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
    except Exception:
        pass
