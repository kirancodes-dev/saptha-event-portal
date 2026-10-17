from flask import Blueprint, abort, current_app, render_template

marketing_bp = Blueprint('marketing', __name__)


def _demo_page(template):
    """The SaaS marketing pages invent customers, prices and uptime, so they
    are hidden unless DEMO_PAGES_ENABLED (UPG-65)."""
    if not current_app.config.get('DEMO_PAGES_ENABLED'):
        abort(404)
    return render_template(template)


@marketing_bp.route('/platform')
def landing():
    return _demo_page('marketing/landing.html')


@marketing_bp.route('/pricing')
def pricing():
    return _demo_page('marketing/pricing.html')


@marketing_bp.route('/features')
def features():
    return _demo_page('marketing/features.html')


@marketing_bp.route('/platform/wayfinder')
def wayfinder():
    return render_template('public/wayfinder.html')
