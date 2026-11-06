"""
routes_hackathon.py — Hack2skill-Style Hackathon Ideation, Milestone Pipeline & Multi-Criterion Rubric Blueprint
"""
import uuid
import logging
from flask import (Blueprint, Response, abort, render_template, request, redirect, url_for, flash,
                   jsonify, session)
from models import db
from utils import login_required, role_required
import services_hackathon
import services_hackathon_eval

logger = logging.getLogger(__name__)

hackathon_bp = Blueprint('hackathon', __name__)

try:
    from db_adapter import to_uuid
except ImportError:
    to_uuid = lambda x: str(x)


@hackathon_bp.route('/hackathon/submit/<event_id>', methods=['GET', 'POST'])
@login_required
def submit_project(event_id):
    """Participant Hackathon Project Submission Portal."""
    user_email = session.get('user_id') or session.get('user_email')

    # Fetch event details
    event_ref = db.collection('events').document(event_id)
    event_doc = event_ref.get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect(url_for('participant.dashboard'))

    event_data = event_doc.to_dict()
    event_data['id'] = event_doc.id

    # A hackathon with the SPOC's own form submits on its page (UPG-191)
    if services_hackathon.has_form(event_data):
        return redirect(url_for('hackathon.portal', event_id=event_id))

    # Verify registration: this event's registrations only, not every one (UPG-191)
    reg_id, reg_data = services_hackathon.team_for(db, event_id, user_email)
    if not reg_id:
        from services_event_types import id_variants
        for eid in id_variants(event_id):
            for r in db.collection('registrations').where('event_id', '==', eid).stream():
                if str((r.to_dict() or {}).get('student_email') or '').lower() == str(user_email or '').lower():
                    reg_id, reg_data = r.id, r.to_dict() or {}
                    break
            if reg_id:
                break
    if not reg_id:
        flash("You must be registered for this hackathon to submit a project.", "warning")
        return redirect(url_for('event_details', event_id=event_id))

    reg_data = reg_data or {}
    team_name = reg_data.get('team_name') or reg_data.get('lead_name') or 'Team'

    # Check for existing submission
    existing = list(db.collection('project_submissions').where('registration_id', '==', str(reg_id)).limit(1).stream())

    if request.method == 'POST':
        project_title = request.form.get('project_title', '').strip()
        tagline = request.form.get('tagline', '').strip()
        problem_statement = request.form.get('problem_statement', '').strip()
        solution_overview = request.form.get('solution_overview', '').strip()
        tech_stack = request.form.get('tech_stack', '').strip()
        github_url = request.form.get('github_url', '').strip()
        demo_url = request.form.get('demo_url', '').strip()
        video_url = request.form.get('video_url', '').strip()
        slide_deck_url = request.form.get('slide_deck_url', '').strip()

        if not project_title or not solution_overview:
            flash("Project title and solution overview are required.", "danger")
            return redirect(url_for('hackathon.submit_project', event_id=event_id))

        submission_data = {
            'event_id': str(event_id),
            'registration_id': str(reg_id),
            'team_name': team_name,
            'project_title': project_title,
            'tagline': tagline,
            'problem_statement': problem_statement,
            'solution_overview': solution_overview,
            'tech_stack': tech_stack,
            'github_url': github_url,
            'demo_url': demo_url,
            'video_url': video_url,
            'slide_deck_url': slide_deck_url,
            'milestone_stage': 'Ideation',
            'submitted_at': session.get('_id', str(uuid.uuid4()))
        }

        if existing:
            sub_id = existing[0].id
            db.collection('project_submissions').document(sub_id).set(submission_data, merge=True)
            flash("✨ Your hackathon project submission has been updated!", "success")
        else:
            sub_id = f"sub_{uuid.uuid4().hex[:12]}"
            db.collection('project_submissions').document(sub_id).set(submission_data)
            flash("🚀 Project successfully submitted to the hackathon pipeline!", "success")

        return redirect(url_for('hackathon.project_detail', submission_id=sub_id))

    current_sub = existing[0].to_dict() if existing else {}
    return render_template('hackathon/submit_project.html',
                           event=event_data,
                           submission=current_sub,
                           team_name=team_name)


@hackathon_bp.route('/hackathon/pipeline/<event_id>')
def kanban_pipeline(event_id):
    """Public / SPOC Hackathon Kanban Pipeline View."""
    event_ref = db.collection('events').document(event_id)
    event_doc = event_ref.get()
    if not event_doc.exists:
        flash("Event not found.", "danger")
        return redirect(url_for('home'))

    event_data = event_doc.to_dict()
    event_data['id'] = event_doc.id

    all_subs = [s.to_dict() for s in db.collection('project_submissions').stream()]
    target_event_ids = {str(event_id), str(to_uuid(event_id))}
    event_subs = [s for s in all_subs if str(s.get('event_id')) in target_event_ids]

    # Group submissions by milestone stages
    pipeline = {
        'Ideation': [s for s in event_subs if s.get('milestone_stage', 'Ideation') == 'Ideation'],
        'Prototype': [s for s in event_subs if s.get('milestone_stage') == 'Prototype'],
        'Finalist': [s for s in event_subs if s.get('milestone_stage') == 'Finalist'],
        'Winner': [s for s in event_subs if s.get('milestone_stage') == 'Winner']
    }

    return render_template('hackathon/kanban_pipeline.html',
                           event=event_data,
                           pipeline=pipeline,
                           total_submissions=len(event_subs))


@hackathon_bp.route('/hackathon/project/<submission_id>')
def project_detail(submission_id):
    """Detailed Hackathon Project View with multi-criterion scoring rubric."""
    sub_doc = db.collection('project_submissions').document(submission_id).get()
    if not sub_doc.exists:
        flash("Project submission not found.", "danger")
        return redirect(url_for('home'))

    sub_data = sub_doc.to_dict()
    sub_data['id'] = sub_doc.id

    # Fetch event title
    event_doc = db.collection('events').document(str(sub_data.get('event_id'))).get()
    event_title = event_doc.to_dict().get('title', 'Hackathon') if event_doc.exists else 'Hackathon'

    return render_template('hackathon/project_detail.html',
                           project=sub_data,
                           event_title=event_title)


@hackathon_bp.route('/api/hackathon/stage/<submission_id>', methods=['POST'])
@login_required
@role_required('ClubSPOC')
def update_milestone_stage(submission_id):
    """SPOC endpoint to transition project milestone stage on the Kanban pipeline."""
    data = request.get_json() or {}
    new_stage = data.get('stage')

    if new_stage not in ['Ideation', 'Prototype', 'Finalist', 'Winner']:
        return jsonify({'status': 'error', 'message': 'Invalid milestone stage.'}), 400

    sub_ref = db.collection('project_submissions').document(submission_id)
    sub_doc = sub_ref.get()
    if not sub_doc.exists:
        return jsonify({'status': 'error', 'message': 'Submission not found.'}), 404

    sub_ref.set({'milestone_stage': new_stage}, merge=True)
    return jsonify({'status': 'ok', 'stage': new_stage})


@hackathon_bp.route('/api/hackathon/score/<submission_id>', methods=['POST'])
@login_required
def score_project_rubric(submission_id):
    """Judge Multi-Criterion Rubric Scoring endpoint (Impact, Tech Stack, UX, Pitch)."""
    user_role = session.get('role', '')
    if user_role not in ['Judge', 'ClubSPOC', 'Admin', 'SuperAdmin']:
        return jsonify({'status': 'error', 'message': 'Permission denied.'}), 403

    data = request.get_json() or {}
    impact = float(data.get('impact', 0.0))
    tech = float(data.get('tech', 0.0))
    ux = float(data.get('ux', 0.0))
    pitch = float(data.get('pitch', 0.0))

    total = round((impact + tech + ux + pitch) / 4.0, 2)

    sub_ref = db.collection('project_submissions').document(submission_id)
    sub_ref.set({
        'score_impact': impact,
        'score_tech': tech,
        'score_ux': ux,
        'score_pitch': pitch,
        'total_score': total
    }, merge=True)

    return jsonify({
        'status': 'ok',
        'total_score': total,
        'breakdown': {'impact': impact, 'tech': tech, 'ux': ux, 'pitch': pitch}
    })


# ═══════════════════════════════════════════════════════════════════════════
# The hackathon portal (UPG-190, UPG-191, UPG-195, UPG-196)
# ═══════════════════════════════════════════════════════════════════════════

def _event(event_id):
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = doc.to_dict() or {}
    event['id'] = doc.id
    return event


def _me():
    return str(session.get('user_id') or session.get('user_email') or '').strip().lower()


def _staff(event) -> bool:
    """The event's owner (or anyone the permission model lets edit it)."""
    from services_permission import can
    return can(session, 'edit_event', event, db=db)


def _my_team(event_id):
    reg_id, reg = services_hackathon.team_for(db, event_id, _me())
    return reg_id, (reg or {})


def _portal_context(event, reg_id, reg):
    h = services_hackathon
    sub_id, submission = h.submission_for(db, reg_id)
    now = h._now()
    released = h.released_problems(event, now)
    upcoming = h.next_release(event, now)
    return {
        'event': event, 'reg_id': reg_id, 'reg': reg, 'submission': submission, 'sub_id': sub_id,
        'stages': h.stages(event, reg, submission, now), 'problems': released,
        'next_release': h.show(h._iso(upcoming), event) if upcoming else '',
        'form': h.form(event), 'window': h.window(event, now),
        'opens': h.show(h.form(event).get('opens_at'), event), 'closes': h.show(h.form(event).get('closes_at'), event),
        'closes_iso': h.form(event).get('closes_at') or '', 'updates': h.updates(event),
        'group_link': h.group_link(event), 'members': [m for m in (reg.get('members') or []) if isinstance(m, dict)],
        'version': h.page_version(event, reg, submission, now), 'show': lambda v: h.show(v, event),
        'problem_titles': {p['id']: p['title'] for p in h.problems(event)},
        'pdf_limit': h.DEFAULT_PDF_MB,
        'results': (services_hackathon_eval.results_for(db, event['id'], event, reg)
                    if event.get('results_published') else None),
        'certificates': services_hackathon_eval.certificates_for(event['id'], reg),
    }


@hackathon_bp.route('/hackathon/<event_id>')
@login_required
def portal(event_id):
    """The registered team's hackathon page (UPG-196)."""
    event = _event(event_id)
    reg_id, reg = _my_team(event_id)
    if not reg_id:
        if _staff(event):
            return redirect(url_for('hackathon.manage', event_id=event_id))
        flash("This page is for teams registered for this hackathon. Team leads log in with the email they registered with.",
              "warning")
        return redirect(url_for('event_details', event_id=event_id))
    errors = session.pop('hackathon_errors', {}) if request.args.get('errors') else {}
    return render_template('hackathon/portal.html', errors=errors, **_portal_context(event, reg_id, reg))


@hackathon_bp.route('/hackathon/<event_id>/state')
@login_required
def portal_state(event_id):
    """What the page polls every 60 seconds; the page reloads when `version` changes."""
    event = _event(event_id)
    reg_id, reg = _my_team(event_id)
    if not reg_id:
        return jsonify({'error': 'not registered'}), 403
    _sub_id, submission = services_hackathon.submission_for(db, reg_id)
    return jsonify({'version': services_hackathon.page_version(event, reg, submission),
                    'now': services_hackathon._iso(services_hackathon._now())})


@hackathon_bp.route('/hackathon/<event_id>/submit', methods=['POST'])
@login_required
def portal_submit(event_id):
    """The team lead's submission (UPG-191). The deadline is checked here."""
    event = _event(event_id)
    reg_id, reg = _my_team(event_id)
    if not reg_id:
        abort(403)
    ok, message, errors = services_hackathon.submit(db, event_id, event, reg_id, reg, request.form,
                                                    request.files, _me())
    flash(message, 'success' if ok else 'danger')
    if errors:
        session['hackathon_errors'] = errors
        return redirect(url_for('hackathon.portal', event_id=event_id, errors=1) + '#submission')
    return redirect(url_for('hackathon.portal', event_id=event_id) + '#submission')


def _pdf(key, name):
    from utils_storage import StorageError, get_private
    try:
        raw = get_private(key)
    except StorageError:
        abort(404)
    return Response(raw, mimetype='application/pdf', headers={
        'Content-Disposition': f'inline; filename="{name or "file.pdf"}"',
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})


@hackathon_bp.route('/hackathon/<event_id>/problem/<pid>/pdf')
@login_required
def problem_pdf(event_id, pid):
    """A problem statement's PDF: registered teams after its release, and staff."""
    event = _event(event_id)
    problem = services_hackathon.find_problem(event, pid)
    if not problem or not problem.get('pdf_key'):
        abort(404)
    if not _staff(event):
        reg_id, _reg = _my_team(event_id)
        if not reg_id or not services_hackathon.is_released(problem):
            abort(403)
    return _pdf(problem['pdf_key'], problem.get('pdf_name'))


@hackathon_bp.route('/hackathon/<event_id>/file/<reg_id>/<fid>')
@login_required
def submission_file(event_id, reg_id, fid):
    """A submitted PDF: the team's lead, the event's staff, and a judge who
    may score that team in the current round (the finale, UPG-194)."""
    event = _event(event_id)
    if not _staff(event) and _judged_team(event, reg_id) is None:
        mine, _reg = _my_team(event_id)
        if not mine or str(mine) != str(reg_id):
            abort(403)
    _sub_id, submission = services_hackathon.submission_for(db, reg_id)
    if str(submission.get('event_id') or '') not in services_hackathon_ids(event_id):
        abort(404)
    answer = (submission.get('answers') or {}).get(fid)
    if not isinstance(answer, dict) or not answer.get('key'):
        abort(404)
    return _pdf(answer['key'], answer.get('name'))


def services_hackathon_ids(event_id):
    from services_event_types import id_variants
    return set(id_variants(event_id)) | {str(to_uuid(event_id))}


# ── The SPOC's side ─────────────────────────────────────────────────────────

def _managed(event_id):
    event = _event(event_id)
    if not _staff(event):
        abort(403)
    return event


@hackathon_bp.route('/spoc/hackathon/<event_id>')
@login_required
def manage(event_id):
    """Problem statements, the submission form, the deadline, updates and
    the email setting, on one page (UPG-190, UPG-191, UPG-195)."""
    event = _managed(event_id)
    h, ev = services_hackathon, services_hackathon_eval
    subs = h.submissions(db, event_id)
    form = h.form(event)
    sort = 'ai' if request.args.get('sort') == 'ai' else 'rank'
    undo_ok, undo_why = ev.can_undo(db, event_id, event)
    from services_rounds import round_info
    return render_template(
        'hackathon/manage.html', event=event, problems=h.problems(event),
        is_released=h.is_released, show=lambda v: h.show(v, event), local=lambda v: h.local_input(v, event),
        form=form, fields=form.get('fields') or [], kinds=h.FIELD_KINDS, window=h.window(event),
        extensions=list(reversed(form.get('extensions') or [])), choices=h.EXTENSION_CHOICES,
        duration=h._duration, updates=h.updates(event), submissions=subs,
        problem_titles={p['id']: p['title'] for p in h.problems(event)},
        email_mode=h.email_mode(event), is_hackathon=h.is_hackathon(event), group_link=h.group_link(event),
        max_pdf=h.MAX_PDF_MB, default_pdf=h.DEFAULT_PDF_MB,
        ai_on=ev.ai_enabled(), ai_off=ev.OFF, ai=ev.progress(db, event_id, event, subs),
        criteria=ev.criteria(event), max_criteria=ev.MAX_CRITERIA, ranking=ev.ranking(db, event_id, event, sort),
        sort=sort, shortlist=ev.shortlist(event), undo_ok=undo_ok, undo_why=undo_why,
        round=round_info(event)['current'], unsent_results=_unsent_results(event_id, event))


def _unsent_results(event_id, event):
    """Team leads whose result email hasn't gone yet (today's limit), after results."""
    if not event.get('results_published') or not services_hackathon.portal_only(event):
        return 0
    return sum(1 for _id, reg in services_hackathon_eval._event_regs(db, event_id)
               if reg.get('lead_email') and not reg.get('result_emailed'))


def _back(event_id, anchor):
    return redirect(url_for('hackathon.manage', event_id=event_id) + f'#{anchor}')


def _audit(action, detail):
    try:
        from utils import log_action
        log_action(db, action, detail)
    except Exception:
        logger.warning("Audit line %s failed", action, exc_info=True)


@hackathon_bp.route('/spoc/hackathon/<event_id>/problems', methods=['POST'])
@login_required
def add_problem(event_id):
    event = _managed(event_id)
    upload = request.files.get('pdf')
    raw = upload.read() if upload and upload.filename else b''
    ok, message = services_hackathon.add_problem(
        db, event_id, event, title=request.form.get('title', ''), description=request.form.get('description', ''),
        track=request.form.get('track', ''), release=request.form.get('release', 'now'),
        release_at=request.form.get('release_at', ''), pdf=raw, pdf_name=(upload.filename or '') if upload else '',
        by=_me())
    if ok:
        _audit('HACKATHON_PROBLEM_ADDED', f"{_me()} added a problem statement to {event_id}")
    flash(message, 'success' if ok else 'danger')
    return _back(event_id, 'problems')


@hackathon_bp.route('/spoc/hackathon/<event_id>/problems/<pid>/release', methods=['POST'])
@login_required
def release_problem(event_id, pid):
    event = _managed(event_id)
    ok, message = services_hackathon.release_now(db, event_id, event, pid, by=_me())
    flash(message, 'success' if ok else 'warning')
    return _back(event_id, 'problems')


@hackathon_bp.route('/spoc/hackathon/<event_id>/problems/<pid>/delete', methods=['POST'])
@login_required
def delete_problem(event_id, pid):
    event = _managed(event_id)
    ok, message = services_hackathon.remove_problem(db, event_id, event, pid)
    flash(message, 'success' if ok else 'warning')
    return _back(event_id, 'problems')


@hackathon_bp.route('/spoc/hackathon/<event_id>/form', methods=['POST'])
@login_required
def save_form(event_id):
    event = _managed(event_id)
    ok, message = services_hackathon.save_form(db, event_id, event, request.form, by=_me())
    if ok:
        _audit('HACKATHON_FORM_SAVED', f"{_me()} saved the submission form of {event_id}")
    flash(message, 'success' if ok else 'danger')
    return _back(event_id, 'form')


@hackathon_bp.route('/spoc/hackathon/<event_id>/extend', methods=['POST'])
@login_required
def extend(event_id):
    """Move the submission deadline later by a chosen time (UPG-191)."""
    event = _managed(event_id)
    minutes = request.form.get('minutes', '')
    if minutes == 'custom':
        try:
            minutes = int(request.form.get('custom_hours') or 0) * 60 + int(request.form.get('custom_minutes') or 0)
        except ValueError:
            minutes = 0
    ok, message = services_hackathon.extend_deadline(db, event_id, event, minutes,
                                                     request.form.get('reason', ''), by=_me())
    if ok:
        _audit('HACKATHON_DEADLINE_EXTENDED', f"{_me()} extended {event_id}: {message}")
    flash(message, 'success' if ok else 'danger')
    return _back(event_id, 'deadline')


@hackathon_bp.route('/spoc/hackathon/<event_id>/update', methods=['POST'])
@login_required
def post_update(event_id):
    event = _managed(event_id)
    title = request.form.get('title', '').strip()
    if not title:
        flash("An update needs a title.", 'danger')
        return _back(event_id, 'updates')
    services_hackathon.post_update(db, event_id, event, title, request.form.get('message', '').strip(),
                                   kind='announcement', by=_me())
    flash("Update posted. Registered teams see it on their hackathon page.", 'success')
    return _back(event_id, 'updates')


@hackathon_bp.route('/spoc/hackathon/<event_id>/emails', methods=['POST'])
@login_required
def email_setting(event_id):
    _managed(event_id)
    mode = request.form.get('mode', '')
    if services_hackathon.set_email_mode(db, event_id, mode):
        _audit('HACKATHON_EMAIL_MODE', f"{_me()} set participant emails of {event_id} to {mode}")
        flash("Participant emails: " + ("registration, password and result only; the rest is in the portal."
                                        if mode == services_hackathon.PORTAL else "all notices by email."), 'success')
    else:
        flash("Unknown setting.", 'danger')
    return _back(event_id, 'emails')


# ── After the deadline: AI scoring (UPG-192) ────────────────────────────────

def _wants_json():
    return request.is_json or 'application/json' in (request.headers.get('Accept') or '')


@hackathon_bp.route('/spoc/hackathon/<event_id>/ai/criteria', methods=['POST'])
@login_required
def ai_criteria(event_id):
    event = _managed(event_id)
    labels = [request.form.get(f'criterion_{i}', '') for i in range(services_hackathon_eval.MAX_CRITERIA + 2)]
    ok, message = services_hackathon_eval.set_criteria(db, event_id, event, labels)
    flash(message, 'success' if ok else 'danger')
    return _back(event_id, 'evaluation')


@hackathon_bp.route('/spoc/hackathon/<event_id>/ai/start', methods=['POST'])
@login_required
def ai_start(event_id):
    """Start (or resume) AI scoring; the page then asks for the next few until done."""
    event = _managed(event_id)
    ok, message = services_hackathon_eval.start(db, event_id, event, by=_me())
    if ok:
        _audit('HACKATHON_AI_STARTED', f"{_me()} started AI scoring of {event_id}")
    if _wants_json():
        return jsonify({'ok': ok, 'message': message}), (200 if ok else 400)
    flash(message, 'success' if ok else 'danger')
    return _back(event_id, 'evaluation')


@hackathon_bp.route('/spoc/hackathon/<event_id>/ai/next', methods=['POST'])
@login_required
def ai_next(event_id):
    """Score the next few submissions. The page's script calls this in a loop;
    without script, the "Continue" button posts it."""
    event = _managed(event_id)
    result = services_hackathon_eval.run_batch(db, event_id, event)
    if _wants_json():
        return jsonify(result)
    flash(result.get('message') or f"Scored {result['scored']} of {result['total']}.", 'info')
    return _back(event_id, 'evaluation')


@hackathon_bp.route('/spoc/hackathon/<event_id>/ai/<sub_id>/rerun', methods=['POST'])
@login_required
def ai_rerun(event_id, sub_id):
    event = _managed(event_id)
    ok, message = services_hackathon_eval.rerun(db, event_id, event, sub_id)
    flash(message, 'success' if ok else 'warning')
    return _back(event_id, 'ranking')


# ── The ranking and the shortlist (UPG-193) ─────────────────────────────────

@hackathon_bp.route('/spoc/hackathon/<event_id>/review/<reg_id>', methods=['POST'])
@login_required
def review(event_id, reg_id):
    """The SPOC's own score (overrides the AI total in the ranking) and note."""
    event = _managed(event_id)
    ok, message = services_hackathon_eval.set_review(db, event_id, event, reg_id, request.form.get('score', ''),
                                                     request.form.get('note', ''), _me())
    flash(message, 'success' if ok else 'danger')
    return _back(event_id, 'ranking')


@hackathon_bp.route('/spoc/hackathon/<event_id>/shortlist/preview', methods=['POST'])
@login_required
def shortlist_preview(event_id):
    """Who would go to the finale and who wouldn't; nothing changes yet."""
    event = _managed(event_id)
    ev = services_hackathon_eval
    if ev.shortlist(event):
        flash("The finalists are already announced. Undo that shortlist first.", 'warning')
        return _back(event_id, 'ranking')
    rows = ev.ranking(db, event_id, event)
    result = ev.preview(rows, request.form.get('mode', ''), request.form.get('n', 0),
                        request.form.getlist('pick'))
    if not result['ok']:
        flash(result['message'], 'danger')
        return _back(event_id, 'ranking')
    from services_rounds import round_info
    return render_template('hackathon/shortlist.html', event=event, p=result,
                           round=round_info(event)['current'])


@hackathon_bp.route('/spoc/hackathon/<event_id>/shortlist/confirm', methods=['POST'])
@login_required
def shortlist_confirm(event_id):
    event = _managed(event_id)
    ok, message = services_hackathon_eval.confirm(db, event_id, event, request.form.getlist('go'),
                                                  request.form.get('expected_round'), _me())
    if ok:
        _audit('HACKATHON_SHORTLIST', f"{_me()} shortlisted {event_id}: {message}")
    flash(message, 'success' if ok else 'danger')
    return _back(event_id, 'ranking')


@hackathon_bp.route('/spoc/hackathon/<event_id>/shortlist/undo', methods=['POST'])
@login_required
def shortlist_undo(event_id):
    event = _managed(event_id)
    ok, message = services_hackathon_eval.undo(db, event_id, event, _me())
    if ok:
        _audit('HACKATHON_SHORTLIST_UNDONE', f"{_me()} undid the shortlist of {event_id}")
    flash(message, 'success' if ok else 'danger')
    return _back(event_id, 'ranking')


# ── Results (UPG-194) ───────────────────────────────────────────────────────

@hackathon_bp.route('/spoc/hackathon/<event_id>/results/resend', methods=['POST'])
@login_required
def results_resend(event_id):
    """Result emails the daily limit held back, sent now (each lead still gets one)."""
    event = _managed(event_id)
    if not event.get('results_published'):
        flash("Results aren't published yet.", 'warning')
        return _back(event_id, 'ranking')
    sent, pending = services_hackathon_eval.send_result_emails(db, event_id, event)
    flash(f"Result emails sent: {sent}." + (f" {pending} still waiting for the email limit." if pending else ''),
          'success' if not pending else 'warning')
    return _back(event_id, 'ranking')


# ── A submission, for the event's staff and the finale's judges (UPG-194) ───

@hackathon_bp.route('/hackathon/<event_id>/review/<reg_id>')
@login_required
def submission_view(event_id, reg_id):
    """One team's submission. Judges see a team they may score in the current
    round, without the AI score; the event's staff see every team and it."""
    event = _event(event_id)
    staff, reg = _staff(event), _judged_team(event, reg_id)
    if not staff and reg is None:
        abort(403)
    if reg is None:
        doc = db.collection('registrations').document(reg_id).get()
        reg = doc.to_dict() or {} if doc.exists else {}
        if str(reg.get('event_id') or '') not in services_hackathon_ids(event_id):
            abort(404)
    _sub_id, submission = services_hackathon.submission_for(db, reg_id)
    h = services_hackathon
    return render_template('hackathon/review.html', event=event, reg=reg, reg_id=reg_id, submission=submission,
                           fields=h.form(event).get('fields') or [], show=lambda v: h.show(v, event),
                           problem_titles={p['id']: p['title'] for p in h.problems(event)},
                           ai=(submission.get('ai_eval') or {}) if staff else {},
                           criteria=services_hackathon_eval.criteria(event), staff=staff)


def _judged_team(event, reg_id):
    """The registration when this judge may score it now, else None."""
    from services_permission import can
    from services_rounds import can_score
    if not can(session, 'score', event, db=db):
        return None
    doc = db.collection('registrations').document(reg_id).get()
    reg = doc.to_dict() or {} if doc.exists else {}
    if str(reg.get('event_id') or '') not in services_hackathon_ids(event['id']) or not can_score(event, reg):
        return None
    return reg
