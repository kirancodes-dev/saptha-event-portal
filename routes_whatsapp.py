"""
routes_whatsapp.py — WhatsApp consent and settings (UPG-147): a person's
on/off switch in their profile, the provider's webhook for replies (STOP),
and the Super Admin's monthly cap.

The webhook is called by the provider, not a browser: each request must carry
the provider's signature (Twilio's X-Twilio-Signature over BASE_URL + path and
the form; Meta's X-Hub-Signature-256 over the body with the app secret).
"""
import base64
import hashlib
import hmac
import os

from flask import Blueprint, abort, flash, redirect, render_template, request, session

from models import db
from utils import login_required

whatsapp_bp = Blueprint('whatsapp', __name__, url_prefix='/whatsapp')


@whatsapp_bp.route('/preference', methods=['POST'])
@login_required
def preference():
    import services_whatsapp as wa
    from utils import log_action
    email = str(session.get('user_id') or '').lower()
    user = db.collection('users').document(email).get().to_dict() or {}
    phone = request.form.get('phone') or user.get('phone') or ''
    on = request.form.get('whatsapp') == 'on'
    if not wa.set_consent(db, phone, on, 'profile'):
        flash("Add a 10-digit mobile number to your profile first.", 'warning')
    else:
        db.collection('users').document(email).update({'whatsapp_opt_in': on})
        log_action(db, "WHATSAPP_PREFERENCE", f"{email}: {'on' if on else 'off'}")
        flash("WhatsApp updates are on." if on else "WhatsApp updates are off.", 'success')
    return redirect('/profile/')


def _twilio_ok() -> bool:
    from utils_email import _base_url
    token = os.environ.get('TWILIO_AUTH_TOKEN', '')
    given = request.headers.get('X-Twilio-Signature', '')
    if not token or not given:
        return False
    data = _base_url().rstrip('/') + request.path + ''.join(k + v for k, v in sorted(request.form.items()))
    expected = base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, given)


def _meta_ok() -> bool:
    secret = os.environ.get('META_WA_APP_SECRET', '')
    given = request.headers.get('X-Hub-Signature-256', '')
    if not secret or not given.startswith('sha256='):
        return False
    expected = hmac.new(secret.encode(), request.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, given[7:])


@whatsapp_bp.route('/webhook', methods=['GET', 'POST'])
def webhook():
    import services_whatsapp as wa
    if request.method == 'GET':        # Meta's subscription check
        token = os.environ.get('META_WA_VERIFY_TOKEN', '')
        if token and request.args.get('hub.mode') == 'subscribe' and \
                hmac.compare_digest(request.args.get('hub.verify_token', ''), token):
            return request.args.get('hub.challenge', ''), 200
        abort(403)
    replies = []
    if request.headers.get('X-Hub-Signature-256'):
        if not _meta_ok():
            abort(403)
        for entry in (request.get_json(silent=True) or {}).get('entry', []):
            for change in entry.get('changes', []):
                for m in (change.get('value') or {}).get('messages', []) or []:
                    replies.append(('+' + str(m.get('from', '')), (m.get('text') or {}).get('body', '')))
    else:
        if not _twilio_ok():
            abort(403)
        replies.append((request.form.get('From', '').replace('whatsapp:', ''), request.form.get('Body', '')))
    for phone, text in replies:
        wa.handle_reply(db, phone, text)
    return '', 204


@whatsapp_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    import services_whatsapp as wa
    if session.get('role') not in ('SuperAdmin', 'Super Admin'):
        abort(403)
    if request.method == 'POST':
        try:
            wa.set_monthly_cap(db, int(request.form.get('monthly_cap', '')), session.get('user_id', ''))
            flash("Monthly cap saved.", 'success')
        except ValueError:
            flash("Give the cap as a whole number of messages.", 'danger')
        return redirect('/whatsapp/settings')
    return render_template('whatsapp/settings.html', enabled=wa.enabled(), configured=wa.configured(),
                           provider=wa.provider(), cap=wa.monthly_cap(db), used=wa.used_this_month(db))
