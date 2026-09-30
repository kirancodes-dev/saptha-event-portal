# routes_onboarding.py — Onboarding wizard and self-service registration
# Python 3.9 compatible

import datetime
import logging
import secrets
from flask import Blueprint, abort, current_app, request, render_template, redirect, flash, session, jsonify
from werkzeug.security import generate_password_hash
def _db():
    from app import db
    return db
from utils import login_required, role_required, log_action

logger = logging.getLogger(__name__)
onboarding_bp = Blueprint('onboarding', __name__, url_prefix='/onboarding')

# A tenant's own administrator. Deliberately not SuperAdmin: that role is
# global (a wildcard in utils.role_required), so granting it here would hand
# the whole university's admin to anyone who fills in the form (BLK-14).
TENANT_ADMIN_ROLE = 'TenantAdmin'


@onboarding_bp.before_request
def _tenant_signup_disabled():
    """Self-service tenant sign-up exists only when multi-tenancy is switched on."""
    if not current_app.config.get('MULTI_TENANT_ENABLED'):
        abort(404)


@onboarding_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """GET/POST /onboarding/signup — Registers a new university tenant and its TenantAdmin (only with MULTI_TENANT_ENABLED)."""
    if request.method == 'POST':
        org_name = request.form.get('org_name', '').strip()
        org_domain = request.form.get('org_domain', '').strip().lower()
        admin_name = request.form.get('admin_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not org_name or not org_domain or not admin_name or not email or not password:
            flash("All fields are required.", "warning")
            return redirect('/onboarding/signup')

        org_slug = org_name.lower().replace(' ', '-').replace('_', '-')

        try:
            # Check existing org
            org_doc = _db().collection('organizations').document(org_slug).get()
            if org_doc.exists:
                flash(f"Organization slug '{org_slug}' is already taken.", "danger")
                return redirect('/onboarding/signup')

            # Check existing user
            user_doc = _db().collection('users').document(email).get()
            if user_doc.exists:
                flash("An account with this email address already exists.", "danger")
                return redirect('/onboarding/signup')

            # Create organization
            _db().collection('organizations').document(org_slug).set({
                'name': org_name,
                'slug': org_slug,
                'domain': org_domain,
                'plan': 'free',
                # organizations.apiKey is unique; give each tenant its own
                'api_key': 'sk_tenant_' + secrets.token_hex(16),
                'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()
            })

            # Create the tenant's administrator (never a global SuperAdmin)
            _db().collection('users').document(email).set({
                'email': email,
                'name': admin_name,
                'role': TENANT_ADMIN_ROLE,
                'org_id': org_slug,
                'password': generate_password_hash(password, method='pbkdf2:sha256'),
                'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'needs_password_reset': False
            })

            # Auto-log in the user
            session['user_id'] = email
            session['name'] = admin_name
            session['role'] = TENANT_ADMIN_ROLE
            session['org_id'] = org_slug
            session['category'] = 'General'

            log_action(_db(), "TENANT_CREATED", f"Registered new tenant organization '{org_name}' by {email}")
            flash(f"🎉 University tenant '{org_name}' registered successfully!", "success")

            return redirect('/onboarding/wizard')

        except Exception as e:
            logger.error("Tenant registration failed: %s", e)
            flash(f"Failed to create tenant: {e}", "danger")
            return redirect('/onboarding/signup')

    # Simple signup form rendering
    return render_template('onboarding/signup.html')


@onboarding_bp.route('/wizard', methods=['GET', 'POST'])
@login_required
@role_required([TENANT_ADMIN_ROLE, 'SuperAdmin', 'Super Admin'])
def wizard():
    """GET/POST /onboarding/wizard — Configuration step builder for organization settings."""
    org_id = session.get('org_id', '')
    if not org_id:
        return redirect('/')

    if request.method == 'POST':
        data = request.json or {}
        primary_color = data.get('primary_color', '#1a2557')
        logo_url = data.get('logo_url', '')
        departments = data.get('departments', [])

        try:
            # Update organization config settings
            _db().collection('organizations').document(org_id).update({
                'logo_url': logo_url,
                'settings': {
                    'primary_color': primary_color,
                    'departments': departments
                }
            })

            log_action(_db(), "TENANT_CONFIGURED", f"Completed onboarding wizard setup configurations for {org_id}")
            return jsonify({'status': 'success', 'redirect': '/coordinator/dashboard'})
        except Exception as e:
            logger.error("Wizard setup configuration save failed: %s", e)
            return jsonify({'error': str(e)}), 500

    return render_template('onboarding/wizard.html')
