"""
routes_reach.py — reaching beyond one campus (UPG-146): the public open-events
page, the organiser's campus-only / open switch and listing kit, and the
Super Admin's "Powered by SapthaEvent" switch.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, session

from models import db
from utils import login_required

reach_bp = Blueprint('reach', __name__)


def _event_for_editor(event_id):
    from services_permission import can
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = dict(doc.to_dict() or {}, id=event_id)
    if not can(session, 'edit_event', event, db=db):
        abort(403)
    return event


@reach_bp.route('/open-events')
def open_events():
    import services_reach as reach
    from utils_pagination import paginate_items
    args = {k: (request.args.get(k) or '').strip() for k in ('q', 'category', 'event_type', 'from', 'to')}
    rows = reach.open_events(db, args['q'], args['category'], args['event_type'], args['from'], args['to'])
    every = reach.open_events(db)
    return render_template('reach/open_events.html', page=paginate_items(rows), args=args,
                           categories=sorted({str(e.get('category')) for e in every if e.get('category')}),
                           event_types=sorted({str(e.get('event_type')) for e in every if e.get('event_type')}))


@reach_bp.route('/reach/events/<event_id>/audience', methods=['POST'])
@login_required
def audience(event_id):
    import services_reach as reach
    _event_for_editor(event_id)
    try:
        reach.set_audience(db, event_id, request.form.get('audience', ''), session.get('user_id', ''))
        flash("This event is now open to other colleges." if request.form.get('audience') == 'open'
              else "This event is now for this campus only.", 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(f'/spoc/event/{event_id}/review')


@reach_bp.route('/reach/events/<event_id>/listing-kit')
@login_required
def listing_kit(event_id):
    import services_reach as reach
    event = _event_for_editor(event_id)
    return render_template('reach/listing_kit.html', event=event, sites=reach.listing_kit(event))


@reach_bp.route('/reach/settings', methods=['GET', 'POST'])
@login_required
def settings():
    import services_reach as reach
    if session.get('role') not in ('SuperAdmin', 'Super Admin'):
        abort(403)
    if request.method == 'POST':
        reach.set_powered_by(db, request.form.get('powered_by') == 'on', session.get('user_id', ''))
        flash("Saved.", 'success')
        return redirect('/reach/settings')
    return render_template('reach/settings.html', powered_by=reach.powered_by(db))
