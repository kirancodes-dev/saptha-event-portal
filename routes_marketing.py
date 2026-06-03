from flask import Blueprint, render_template

marketing_bp = Blueprint('marketing', __name__)


@marketing_bp.route('/platform')
def landing():
    return render_template('marketing/landing.html')


@marketing_bp.route('/pricing')
def pricing():
    return render_template('marketing/pricing.html')


@marketing_bp.route('/features')
def features():
    return render_template('marketing/features.html')


@marketing_bp.route('/platform/wayfinder')
def wayfinder():
    return render_template('public/wayfinder.html')
