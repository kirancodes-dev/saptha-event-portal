"""
routes_placement.py — the organiser's side of a placement drive (UPG-57)

/placement/<event_id> shows the company, the eligibility rules, how many
students on the roster are eligible against how many registered, and each
registrant's result per round. Whoever may edit the event adds rounds and
moves students to shortlisted or rejected in a round (each move notifies the
student once); whoever may export the event's data downloads a round's list
as CSV or Excel.
"""
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session

from models import db
from utils import log_action, login_required

placement_bp = Blueprint('placement', __name__, url_prefix='/placement')
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _event_or_abort(event_id, permission):
    from services_permission import can
    from services_placement import is_placement
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = dict(doc.to_dict() or {}, id=event_id)
    if not can(session, permission, event, db=db):
        abort(403)
    if not is_placement(event):
        abort(404)   # not a placement drive: mark it as one on the edit page
    return event


def _registrations(event_id):
    return [(d.id, d.to_dict() or {}) for d in db.collection('registrations').where('event_id', '==', event_id).stream()]


@placement_bp.route('/<event_id>')
@login_required
def drive(event_id):
    from services_permission import can
    from services_placement import academic_record, current_round, eligible_students, settings
    event = _event_or_abort(event_id, 'view_analytics')
    regs = _registrations(event_id)
    rows = []
    for rid, r in sorted(regs, key=lambda x: str(x[1].get('lead_name') or '')):
        prof = db.collection('users').document((r.get('lead_email') or '').lower()).get()
        rec = academic_record((prof.to_dict() or {}) if prof.exists else {})
        round_name, status = current_round(event, r)
        rows.append({'id': rid, 'reg': r, 'rec': rec, 'round': round_name, 'status': status,
                     'results': r.get('placement_rounds') or {}})
    return render_template('spoc/placement.html', event=event, rules=settings(event), rows=rows,
                           rounds=settings(event).get('rounds') or [],
                           eligible_count=len(eligible_students(db, event)), registered_count=len(regs),
                           can_edit=can(session, 'edit_event', event, db=db))


@placement_bp.route('/<event_id>/rounds', methods=['POST'])
@login_required
def add_round(event_id):
    from services_placement import add_round as with_round
    event = _event_or_abort(event_id, 'edit_event')
    name = (request.form.get('name') or '').strip()
    if not name:
        flash("Give the round a name, e.g. Aptitude.", "warning")
        return redirect(f'/placement/{event_id}')
    db.collection('events').document(event_id).update({'placement': with_round(event, name)})
    log_action(db, "PLACEMENT_ROUND_ADDED", f"{session.get('user_id')} added round '{name}' to {event_id}")
    flash(f"Round '{name}' added.", "success")
    return redirect(f'/placement/{event_id}')


@placement_bp.route('/<event_id>/move', methods=['POST'])
@login_required
def move_students(event_id):
    from services_placement import STATUSES, move
    event = _event_or_abort(event_id, 'edit_event')
    round_id, status = request.form.get('round_id', ''), request.form.get('status', '')
    reg_ids = request.form.getlist('reg_ids')
    if status not in STATUSES or not round_id or not reg_ids:
        flash("Choose students, a round and a result.", "warning")
        return redirect(f'/placement/{event_id}')
    regs = dict(_registrations(event_id))
    moved = 0
    for rid in reg_ids:
        if rid in regs and move(db, event_id=event_id, event=event, reg_id=rid, reg=regs[rid],
                                round_id=round_id, status=status, actor=session.get('user_id', '')):
            moved += 1
    log_action(db, "PLACEMENT_RESULTS", f"{session.get('user_id')} marked {moved} {status} in {round_id} of {event_id}")
    flash(f"{moved} student{'s' if moved != 1 else ''} marked {status}; each was notified.", "success")
    return redirect(f'/placement/{event_id}')


@placement_bp.route('/<event_id>/export/<round_id>.<fmt>')
@login_required
def export_round(event_id, round_id, fmt):
    import services_export
    event = _event_or_abort(event_id, 'export_data')
    status = request.args.get('status') or None
    rows = services_export.placement_round_rows(db, event_id, round_id, status)
    name = f"{(event.get('title') or 'placement').replace(' ', '_')}_{round_id}{'_' + status if status else ''}"
    if fmt == 'xlsx':
        return Response(services_export.to_xlsx([(round_id, services_export.PLACEMENT_ROUND_COLUMNS, rows)]),
                        mimetype=XLSX, headers={'Content-Disposition': f'attachment; filename="{name}.xlsx"'})
    if fmt == 'csv':
        return Response(services_export.to_csv(rows, columns=services_export.PLACEMENT_ROUND_COLUMNS),
                        mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename="{name}.csv"'})
    abort(404)
