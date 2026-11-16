from flask import Blueprint, abort, current_app, render_template

marketing_bp = Blueprint('marketing', __name__)


def _about():
    """What the portal is, for someone deciding whether an institution should
    use it: who it is for, what it covers, how to start, what a demo is, and
    who to write to. It states nothing the portal doesn't do (UPG-275)."""
    from services_event_types import TYPES
    return render_template('public/about.html', event_type_count=len(TYPES))


def _demo_page(view):
    """Pages behind DEMO_PAGES_ENABLED (UPG-65) answer 404 without it."""
    if not current_app.config.get('DEMO_PAGES_ENABLED'):
        abort(404)
    return view()


@marketing_bp.route('/about')
def about():
    return _about()


# /platform and /features used to invent tenants, prices, single sign-on and
# compliance. They stay behind the switch and now show the About page.
@marketing_bp.route('/platform')
def landing():
    return _demo_page(_about)


@marketing_bp.route('/features')
def features():
    return _demo_page(_about)


# The price list is untouched: it states prices and fees nobody has agreed, so
# it stays hidden unless DEMO_PAGES_ENABLED (see FEATURE_REVIEW.md).
@marketing_bp.route('/pricing')
def pricing():
    return _demo_page(lambda: render_template('marketing/pricing.html'))


@marketing_bp.route('/platform/wayfinder')
def wayfinder():
    return render_template('public/wayfinder.html')
