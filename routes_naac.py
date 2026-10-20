"""
routes_naac.py — NAAC / AQAR pages (UPG-144): the post-event report for an
event's organiser, missing reports and reminders for the IQAC coordinator,
the yearly report builder with XLSX, PDF and evidence-ZIP exports, and the
Super Admin's list of NAAC categories. services_naac decides who sees what.
"""
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session

from models import db
from utils import login_required

naac_bp = Blueprint('naac', __name__, url_prefix='/naac')


def _event(event_id):
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    return dict(doc.to_dict() or {}, id=event_id)


@naac_bp.route('/')
@login_required
def index():
    import services_naac as naac
    from services_permission import can
    role = session.get('role')
    if not (naac.may_run_builder(session) or can(session, 'create_event', db=db) or role in ('ClubSPOC', 'SPOC')):
        abort(403)
    return render_template('naac/index.html', missing=naac.missing(db, session), sees_all=naac.sees_all(session),
                           builder=naac.may_run_builder(session), days=naac.report_days(),
                           admin=role in ('SuperAdmin', 'Super Admin'))


@naac_bp.route('/events/<event_id>/report', methods=['GET', 'POST'])
@login_required
def report(event_id):
    import services_naac as naac
    event = _event(event_id)
    if not naac.may_view(db, session, event):
        abort(403)
    editable = naac.may_edit(db, session, event)
    if request.method == 'POST':
        if not editable:
            abort(403)
        actor = session.get('user_id', '')
        try:
            if request.form.get('action') == 'category':
                naac.set_category(db, event_id, request.form.get('naac_category', ''), actor)
                flash("NAAC category saved.", 'success')
            else:
                submit = request.form.get('action') == 'submit'
                naac.save_report(db, event_id, request.form, actor, submit=submit)
                flash("Report submitted." if submit else "Draft saved.", 'success')
        except naac.NaacError as exc:
            flash(str(exc), 'danger')
        return redirect(f'/naac/events/{event_id}/report')
    due = naac.due_date(event)
    return render_template('naac/report.html', event=event, report=naac.get_report(db, event_id),
                           attendance=naac.attendance(db, event_id, event), categories=naac.categories(db),
                           editable=editable, due=due.isoformat() if due else '', remind=naac.sees_all(session),
                           kinds=naac.FILE_KINDS)


@naac_bp.route('/events/<event_id>/files', methods=['POST'])
@login_required
def upload(event_id):
    import services_naac as naac
    event = _event(event_id)
    if not naac.may_edit(db, session, event):
        abort(403)
    upload = request.files.get('file')
    try:
        entry = naac.add_file(db, event_id, request.form.get('kind', ''), upload.filename if upload else '',
                              upload.read(max(naac.MAX_BYTES.values()) + 1) if upload else b'',
                              session.get('user_id', ''), shareable=request.form.get('shareable') == 'on')
        flash(f"{entry['name']} added.", 'success')
    except naac.NaacError as exc:
        flash(str(exc), 'danger')
    return redirect(f'/naac/events/{event_id}/report')


@naac_bp.route('/events/<event_id>/files/<file_id>')
@login_required
def evidence(event_id, file_id):
    import services_naac as naac
    from utils_storage import StorageError, get_private
    event = _event(event_id)
    if not naac.may_view(db, session, event):
        abort(403)
    f = next((f for f in naac.get_report(db, event_id).get('files') or [] if f.get('id') == file_id), None)
    if not f:
        abort(404)
    try:
        data = get_private(f['key'])
    except StorageError:
        abort(404)
    mime = 'application/pdf' if f['ext'] == 'pdf' else f"image/{'jpeg' if f['ext'] == 'jpg' else 'png'}"
    return Response(data, mimetype=mime, headers={'Cache-Control': 'private, no-store',
                                                  'Content-Disposition': f"inline; filename={f['id']}.{f['ext']}"})


@naac_bp.route('/events/<event_id>/remind', methods=['POST'])
@login_required
def remind(event_id):
    import services_naac as naac
    _event(event_id)
    if not naac.sees_all(session):
        abort(403)
    sent = naac.remind(db, event_id, session.get('user_id', ''))
    flash("Reminder sent to the organiser." if sent else "The reminder couldn't be sent.", 'success' if sent else 'danger')
    return redirect(request.referrer if (request.referrer or '').startswith(request.host_url) else '/naac/')


def _built():
    import services_naac as naac
    if not naac.may_run_builder(session):
        abort(403)
    options = naac.filter_options(db, session)
    year = request.args.get('year') or options['years'][0]
    try:
        data = naac.build(db, session, year, request.args.get('unit', ''), request.args.get('category', ''),
                          request.args.get('event_type', ''))
    except ValueError:
        abort(400)
    return options, data


@naac_bp.route('/report')
@login_required
def builder():
    options, data = _built()
    return render_template('naac/builder.html', options=options, data=data, args=request.args)


@naac_bp.route('/report.<kind>')
@login_required
def export(kind):
    import services_naac as naac
    from urllib.parse import quote
    _, data = _built()
    name = quote(f"NAAC-{data['year']}")
    if kind == 'xlsx':
        return Response(naac.to_xlsx(data), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': f'attachment; filename={name}.xlsx'})
    if kind == 'pdf':
        return Response(naac.to_pdf(data), mimetype='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename={name}.pdf'})
    if kind == 'zip':
        return Response(naac.evidence_zip(db, data), mimetype='application/zip',
                        headers={'Content-Disposition': f'attachment; filename={name}-evidence.zip'})
    abort(404)


@naac_bp.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    import services_naac as naac
    if session.get('role') not in ('SuperAdmin', 'Super Admin'):
        abort(403)
    if request.method == 'POST':
        names = [n for n in request.form.getlist('name')]
        names += [request.form.get('new', '')]
        try:
            naac.save_categories(db, names, session.get('user_id', ''))
            flash("NAAC categories saved.", 'success')
        except naac.NaacError as exc:
            flash(str(exc), 'danger')
        return redirect('/naac/categories')
    return render_template('naac/categories.html', names=naac.categories(db))
