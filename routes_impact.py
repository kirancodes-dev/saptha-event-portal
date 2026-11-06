"""
routes_impact.py — the track record (UPG-145): the Super Admin's impact
dashboard, testimonials and their approval, the 2-page impact report, the
organiser's hours-saved answer, the testimonial form behind each emailed
link, and the optional public Impact page.
"""
import datetime

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session

from models import db
from utils import login_required

impact_bp = Blueprint('impact', __name__)
ADMIN = ('SuperAdmin', 'Super Admin')


def _admin():
    if session.get('role') not in ADMIN:
        abort(403)


@impact_bp.route('/impact/dashboard')
@login_required
def dashboard():
    import services_impact as impact
    _admin()
    year = request.args.get('year', '')
    data = impact.dashboard(db, year or None)
    this = datetime.date.today().strftime('%Y-%m')
    return render_template('impact/dashboard.html', data=data, year=year, testimonials=impact.testimonials(db),
                           public=impact.public_on(db), start=f"{this[:4]}-01", end=this)


@impact_bp.route('/impact/public', methods=['POST'])
@login_required
def switch_public():
    import services_impact as impact
    _admin()
    impact.set_public(db, request.form.get('public') == 'on', session.get('user_id', ''))
    flash("The public Impact page is " + ("on." if request.form.get('public') == 'on' else "off."), 'success')
    return redirect('/impact/dashboard')


@impact_bp.route('/impact/testimonials/<testimonial_id>/<action>', methods=['POST'])
@login_required
def approve(testimonial_id, action):
    import services_impact as impact
    _admin()
    if action not in ('approve', 'withdraw'):
        abort(404)
    try:
        impact.set_approved(db, testimonial_id, action == 'approve', session.get('user_id', ''))
        flash("Testimonial approved for public use." if action == 'approve' else "Testimonial withdrawn.", 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect('/impact/dashboard#testimonials')


@impact_bp.route('/impact/report.pdf')
@login_required
def report():
    import re
    import services_impact as impact
    _admin()
    start, end = request.args.get('start', ''), request.args.get('end', '')
    if not (re.fullmatch(r'\d{4}-\d{2}', start) and re.fullmatch(r'\d{4}-\d{2}', end)) or start > end:
        abort(400)
    return Response(impact.report_pdf(db, start, end), mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename=SapthaEvent-impact-{start}-to-{end}.pdf'})


@impact_bp.route('/impact/events/<event_id>/hours', methods=['POST'])
@login_required
def hours_saved(event_id):
    import services_impact as impact
    import services_naac as naac
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    if not naac.may_edit(db, session, dict(doc.to_dict() or {}, id=event_id)):
        abort(403)
    try:
        impact.save_hours_saved(db, event_id, request.form.get('hours_saved'), session.get('user_id', ''))
        flash("Thanks: your estimate is saved.", 'success')
    except ValueError as exc:
        flash(str(exc), 'danger')
    return redirect(f'/naac/events/{event_id}/report')


@impact_bp.route('/impact/testimonial/<token>', methods=['GET', 'POST'])
def testimonial(token):
    import services_impact as impact
    from itsdangerous import BadSignature
    try:
        claim = impact.read_token(token)
    except BadSignature:
        abort(404)
    doc = db.collection('events').document(claim['e']).get()
    event = doc.to_dict() or {} if doc.exists else {}
    saved = None
    if request.method == 'POST':
        try:
            saved = impact.save_testimonial(db, claim, request.form.get('rating'), request.form.get('comment', ''),
                                            request.form.get('may_quote') == 'on')
        except ValueError as exc:
            flash(str(exc), 'danger')
    return render_template('impact/testimonial.html', claim=claim, event=event, saved=saved)


@impact_bp.route('/impact')
def public_page():
    import services_impact as impact
    if not impact.public_on(db):
        abort(404)
    data = impact.dashboard(db)
    return render_template('impact/public.html', years=data['years'], time_saved=data['time_saved'],
                           quotes=impact.testimonials(db, approved_only=True)[:12])
