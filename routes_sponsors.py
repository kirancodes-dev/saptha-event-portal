"""
routes_sponsors.py — Event Sponsors management

Admin:
  GET  /admin/sponsors             — list + add form
  POST /admin/sponsors             — create sponsor
  POST /admin/sponsors/<id>/delete — remove sponsor

Public API:
  GET  /api/sponsors               — JSON feed of active sponsors (used by home page)

Firestore collection: sponsors
  { name, tier: 'Platinum|Gold|Silver|Partner',
    website, logo_url, description, active, created_at }
"""
import datetime
import uuid

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session

from models import db
from utils import login_required, role_required, log_action

sponsors_bp = Blueprint('sponsors', __name__)

SUPER_ROLES = ['SuperAdmin', 'Super Admin', 'Admin']
TIERS = ['Platinum', 'Gold', 'Silver', 'Partner']


# ──────────────────────────────────────────
# ADMIN: manage sponsors
# ──────────────────────────────────────────
@sponsors_bp.route('/admin/sponsors', methods=['GET', 'POST'])
@login_required
@role_required(SUPER_ROLES)
def admin_sponsors():
    if request.method == 'POST':
        name       = (request.form.get('name') or '').strip()
        tier       = request.form.get('tier') or 'Partner'
        website    = (request.form.get('website') or '').strip()
        logo_url   = (request.form.get('logo_url') or '').strip()
        desc       = (request.form.get('description') or '').strip()

        if not name:
            flash("Sponsor name is required.", "danger")
            return redirect('/admin/sponsors')
        if tier not in TIERS:
            tier = 'Partner'

        sid = f"SPON-{uuid.uuid4().hex[:8].upper()}"
        db.collection('sponsors').document(sid).set({
            'id': sid,
            'name': name,
            'tier': tier,
            'website': website,
            'logo_url': logo_url,
            'description': desc,
            'active': True,
            'created_at': datetime.datetime.utcnow().isoformat(),
            'created_by': session.get('user_id'),
        })
        log_action(session.get('user_id'), 'sponsor_add', f"{sid} {name} ({tier})")
        flash(f"Sponsor '{name}' added.", "success")
        return redirect('/admin/sponsors')

    # GET — list
    tier_order = {t: i for i, t in enumerate(TIERS)}
    sponsors = []
    for s in db.collection('sponsors').stream():
        d = s.to_dict() or {}
        d['id'] = s.id
        sponsors.append(d)
    sponsors.sort(key=lambda x: (tier_order.get(x.get('tier'), 99), x.get('name', '')))

    return render_template(
        'admin/sponsors.html',
        sponsors=sponsors, tiers=TIERS,
        user_role=session.get('role'), current_page='sponsors',
        user_initials=(session.get('name', 'U') or 'U')[:1].upper(),
    )


@sponsors_bp.route('/admin/sponsors/<sid>/delete', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def admin_sponsor_delete(sid):
    doc = db.collection('sponsors').document(sid).get()
    if doc.exists:
        db.collection('sponsors').document(sid).delete()
        log_action(session.get('user_id'), 'sponsor_delete', sid)
        flash("Sponsor removed.", "success")
    else:
        flash("Sponsor not found.", "warning")
    return redirect('/admin/sponsors')


@sponsors_bp.route('/admin/sponsors/<sid>/toggle', methods=['POST'])
@login_required
@role_required(SUPER_ROLES)
def admin_sponsor_toggle(sid):
    ref = db.collection('sponsors').document(sid)
    doc = ref.get()
    if not doc.exists:
        flash("Sponsor not found.", "warning")
        return redirect('/admin/sponsors')
    current = (doc.to_dict() or {}).get('active', True)
    ref.update({'active': not current})
    flash("Sponsor visibility updated.", "success")
    return redirect('/admin/sponsors')


# ──────────────────────────────────────────
# PUBLIC: sponsors JSON (for home page strip)
# ──────────────────────────────────────────
@sponsors_bp.route('/api/sponsors')
def api_sponsors():
    if db is None:
        return jsonify([])
    tier_order = {t: i for i, t in enumerate(TIERS)}
    items = []
    for s in db.collection('sponsors').stream():
        d = s.to_dict() or {}
        if not d.get('active', True):
            continue
        items.append({
            'name': d.get('name'),
            'tier': d.get('tier'),
            'website': d.get('website'),
            'logo_url': d.get('logo_url'),
        })
    items.sort(key=lambda x: (tier_order.get(x.get('tier'), 99), x.get('name', '')))
    return jsonify(items)
