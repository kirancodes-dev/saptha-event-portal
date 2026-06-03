# routes_i18n.py — Language switching blueprint for SapthaEvent
# Python 3.9 compatible

from typing import Optional
from flask import Blueprint, request, session, redirect, jsonify, make_response, url_for
from i18n import SUPPORTED_LOCALES, DEFAULT_LOCALE, get_locale, get_translations

i18n_bp = Blueprint('i18n', __name__)


@i18n_bp.route('/set-language/<locale>')
def set_language(locale: str):
    """Switch the active language, persist in session + cookie, then redirect back."""
    if locale in SUPPORTED_LOCALES:
        session['locale'] = locale
        referrer = request.referrer or '/'
        resp = make_response(redirect(referrer))
        resp.set_cookie(
            'locale',
            locale,
            max_age=365 * 24 * 60 * 60,   # 1 year
            samesite='Lax',
            httponly=False,                 # JS needs to read it
        )
        return resp
    return redirect('/')


@i18n_bp.route('/api/translations')
def api_translations():
    """Return the translation dict for the current (or requested) locale."""
    locale = request.args.get('locale')  # optional override
    if locale and locale not in SUPPORTED_LOCALES:
        locale = None
    return jsonify(get_translations(locale))


@i18n_bp.route('/api/translations/<locale>')
def api_translations_for(locale: str):
    """Return translations for a specific locale."""
    if locale not in SUPPORTED_LOCALES:
        return jsonify({'error': 'Unsupported locale'}), 404
    return jsonify(get_translations(locale))


@i18n_bp.route('/api/locales')
def api_locales():
    """List all supported locales + the currently active one."""
    return jsonify({
        'locales': SUPPORTED_LOCALES,
        'current': get_locale(),
        'default': DEFAULT_LOCALE,
    })
