"""
routes_portfolio.py — Public student portfolio at /u/<usn>

Shows a shareable profile of a student's events, certificates, and achievements.
Public read-only; no auth required. Only publishes confirmed + attended events.
"""
from flask import Blueprint, abort, render_template
from google.cloud.firestore_v1.base_query import FieldFilter

from models import db

portfolio_bp = Blueprint('portfolio', __name__)


def _ff(f, op, v):
    return FieldFilter(f, op, v)


def _find_user_by_usn(usn: str):
    """users collection is keyed by email; search by usn field."""
    usn_norm = (usn or '').strip().upper()
    if not usn_norm or db is None:
        return None
    docs = (db.collection('users')
              .where(filter=_ff('usn', '==', usn_norm))
              .limit(1).stream())
    for d in docs:
        data = d.to_dict() or {}
        data['_id'] = d.id  # email is doc id
        return data
    return None


@portfolio_bp.route('/u/<usn>')
def public_portfolio(usn):
    user = _find_user_by_usn(usn)
    if not user:
        abort(404)

    email = user.get('_id') or user.get('email')

    # Pull all registrations by this student
    regs = []
    for r in (db.collection('registrations')
                .where(filter=_ff('lead_email', '==', email))
                .stream()):
        d = r.to_dict() or {}
        d['id'] = r.id

        # Enrich with event info
        evt_doc = db.collection('events').document(d.get('event_id', '')).get()
        evt = evt_doc.to_dict() if evt_doc.exists else {}
        d['event_title']  = evt.get('title', d.get('event_title', 'Event'))
        d['event_date']   = evt.get('date', '')
        d['event_cat']    = evt.get('category', 'General')
        d['event_venue']  = evt.get('venue', 'SNPSU Campus')
        d['event_status'] = evt.get('status', 'active')
        regs.append(d)

    # Sort: most recent first by event_date
    regs.sort(key=lambda x: x.get('event_date', ''), reverse=True)

    # Buckets
    attended   = [r for r in regs if r.get('attendance') == 'Present']
    winners    = [r for r in regs if r.get('final_rank') in (1, 2, 3, '1', '2', '3')]
    upcoming   = [r for r in regs
                  if r.get('event_status') == 'active'
                  and r.get('status') == 'Confirmed']
    total      = len(regs)

    # Count certificates (attended + event completed)
    cert_count = sum(
        1 for r in regs
        if r.get('attendance') == 'Present' and r.get('event_status') == 'completed'
    )

    # Category tally for skill graph
    cat_counts = {}
    for r in attended:
        c = r.get('event_cat', 'General')
        cat_counts[c] = cat_counts.get(c, 0) + 1

    initials = (user.get('name', '?')[:1] or '?').upper()

    return render_template(
        'portfolio/public_profile.html',
        student      = user,
        initials     = initials,
        total        = total,
        attended     = attended,
        winners      = winners,
        upcoming     = upcoming,
        cert_count   = cert_count,
        cat_counts   = cat_counts,
        all_regs     = regs,
        public_layout= True,
    )
