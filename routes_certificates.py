"""
routes_certificates.py — an event's certificates, for its organisers (UPG-123 onwards).

/certificates/events/<event_id> is the event's certificate page: its
signatories (1 to 3, with signature images), the template, and a live preview
with the real signatories and sample data. Whoever may edit the event manages
the signatories and the template (services_permission: edit_event); the
signature images are served only to the event's staff, never at a public URL.
"""
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session

from models import db
from utils import login_required

certificates_bp = Blueprint('certificates', __name__, url_prefix='/certificates')

SAMPLE = {'name': 'Sample Recipient', 'number': 'SE-SAMP-LE00-0000-0'}


def _event_or_abort(event_id, *permissions):
    """The event, if the person holds one of these permissions on it; else 404/403."""
    from services_permission import can
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = dict(doc.to_dict() or {}, id=event_id)
    if not any(can(session, p, event, db=db) for p in permissions):
        abort(403)
    return event


def _is_staff(event) -> bool:
    from services_permission import can
    email = (session.get('user_id') or '').lower()
    if any(can(session, p, event, db=db) for p in ('edit_event', 'issue_certificates', 'check_in')):
        return True
    return any(str(s.get('email') or '').lower() == email for s in event.get('staff') or [])


def _own_events_with_signatories(event_id):
    """The person's other events that have signatories (to copy from)."""
    from services_permission import can
    out = []
    for doc in db.collection('events').stream():
        if doc.id == event_id:
            continue
        ev = dict(doc.to_dict() or {}, id=doc.id)
        if ev.get('cert_signatories') and can(session, 'edit_event', ev, db=db):
            out.append({'id': doc.id, 'title': ev.get('title', 'Event'), 'date': ev.get('date', ''),
                        'count': len(ev['cert_signatories'])})
    return sorted(out, key=lambda e: str(e['date']), reverse=True)


@certificates_bp.route('/events/<event_id>')
@login_required
def manage(event_id):
    import certificate_pdf
    import services_signatories as sigs
    event = _event_or_abort(event_id, 'edit_event', 'issue_certificates')
    signatories = sigs.listing(db, event_id, event)
    return render_template('certificates/manage.html', event=event, signatories=signatories,
                           ready=sigs.ready(signatories), missing=sigs.missing_message(signatories),
                           styles=certificate_pdf.STYLES, style=event.get('cert_style') or 'classic',
                           copy_sources=_own_events_with_signatories(event_id),
                           can_edit=_can(event, 'edit_event'), max_signatories=sigs.MAX_SIGNATORIES)


def _can(event, permission):
    from services_permission import can
    return can(session, permission, event, db=db)


def _back(event_id):
    return redirect(f'/certificates/events/{event_id}')


@certificates_bp.route('/events/<event_id>/signatories', methods=['POST'])
@login_required
def add_signatory(event_id):
    import services_signatories as sigs
    _event_or_abort(event_id, 'edit_event')
    upload = request.files.get('signature')
    try:
        order = int(request.form.get('order') or 0) or None
    except ValueError:
        order = None
    try:
        entry = sigs.add(db, event_id, name=request.form.get('name', ''), title=request.form.get('title', ''),
                         image=upload.read() if upload else b'', order=order, actor=session.get('user_id', ''))
        flash(f"{entry['name']} added as a signatory.", 'success')
    except sigs.SignatoryError as exc:
        flash(str(exc), 'danger')
    return _back(event_id)


@certificates_bp.route('/events/<event_id>/signatories/<sig_id>/delete', methods=['POST'])
@login_required
def remove_signatory(event_id, sig_id):
    import services_signatories as sigs
    _event_or_abort(event_id, 'edit_event')
    try:
        sigs.remove(db, event_id, sig_id, actor=session.get('user_id', ''))
        flash("Signatory removed. Certificates already issued keep their signatures.", 'success')
    except sigs.SignatoryError as exc:
        flash(str(exc), 'danger')
    return _back(event_id)


@certificates_bp.route('/events/<event_id>/signatories/order', methods=['POST'])
@login_required
def order_signatories(event_id):
    import services_signatories as sigs
    _event_or_abort(event_id, 'edit_event')
    current = sigs.listing(db, event_id)

    def place(sig):
        try:
            return int(request.form.get(f"order_{sig['id']}") or sig.get('order', 0))
        except ValueError:
            return sig.get('order', 0)
    try:
        sigs.reorder(db, event_id, [s['id'] for s in sorted(current, key=place)], actor=session.get('user_id', ''))
        flash("Signatory order saved (left to right).", 'success')
    except sigs.SignatoryError as exc:
        flash(str(exc), 'danger')
    return _back(event_id)


@certificates_bp.route('/events/<event_id>/signatories/copy', methods=['POST'])
@login_required
def copy_signatories(event_id):
    import services_signatories as sigs
    _event_or_abort(event_id, 'edit_event')
    source_id = (request.form.get('source_event_id') or '').strip()
    _event_or_abort(source_id, 'edit_event')            # only from an event they may edit
    try:
        n = sigs.copy_from(db, event_id, source_id, actor=session.get('user_id', ''))
        flash(f"Copied {n} signator{'y' if n == 1 else 'ies'}.", 'success')
    except sigs.SignatoryError as exc:
        flash(str(exc), 'danger')
    return _back(event_id)


@certificates_bp.route('/events/<event_id>/signatories/<sig_id>/image')
@login_required
def signature_image(event_id, sig_id):
    """A signature, for the event's own staff only (never a public URL)."""
    import services_signatories as sigs
    from utils_storage import StorageError, get_private
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = dict(doc.to_dict() or {}, id=event_id)
    if not _is_staff(event):
        abort(403)
    sig = next((s for s in sigs.listing(db, event_id, event) if s.get('id') == sig_id), None)
    if not sig or not sig.get('image_key'):
        abort(404)
    try:
        data = get_private(sig['image_key'])
    except StorageError:
        abort(404)
    return Response(data, mimetype='image/png', headers={'Cache-Control': 'private, no-store'})


@certificates_bp.route('/events/<event_id>/style', methods=['POST'])
@login_required
def choose_style(event_id):
    import certificate_pdf
    from utils import log_action
    _event_or_abort(event_id, 'edit_event')
    style = request.form.get('style', '')
    if style not in certificate_pdf.STYLES:
        flash("Choose one of the templates.", 'danger')
    else:
        db.collection('events').document(event_id).update({'cert_style': style})
        log_action(db, "CERT_TEMPLATE_CHOSEN", f"{session.get('user_id')}: {style} for event {event_id}")
        flash("Template saved.", 'success')
    return _back(event_id)


@certificates_bp.route('/events/<event_id>/preview.png')
@login_required
def preview(event_id):
    """The certificate as it will look: the real signatories, sample data."""
    import certificate_pdf
    import services_certificates as certs
    import services_signatories as sigs
    event = _event_or_abort(event_id, 'edit_event', 'issue_certificates')
    kind = request.args.get('type') or certs.attendance_type(event)
    if kind not in certs.TYPES:
        kind = 'participation'
    sample = {'name': SAMPLE['name'], 'cert_type': kind, 'position': 1 if kind == 'position' else None,
              'designation': '', 'institution': '', 'hours': float(event.get('activity_hours') or 0) or None,
              'points': float(event.get('activity_points') or 0) or None}
    data = certs.wording(event, sample)
    signatories = sigs.listing(db, event_id, event)
    pdf = certificate_pdf.render(number=SAMPLE['number'], name=SAMPLE['name'], data=data, cert_type=kind,
                                 signatories=signatories, verify_url=certs.verify_url(SAMPLE['number']),
                                 issued_on='(issue date)', style=event.get('cert_style') or 'classic',
                                 signature_bytes=sigs.image_bytes(signatories))
    return Response(certificate_pdf.to_png(pdf, scale=1.4), mimetype='image/png',
                    headers={'Cache-Control': 'private, no-store'})
