"""
routes_hackathon.py — Hack2skill-Style Hackathon Ideation, Milestone Pipeline & Multi-Criterion Rubric Blueprint
"""
import uuid
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from models import db
from utils import login_required, role_required

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

    # Verify registration
    all_regs = list(db.collection('registrations').stream())
    target_event_ids = {str(event_id), str(to_uuid(event_id))}
    reg_docs = [
        r for r in all_regs
        if (r.to_dict().get('lead_email') == user_email or r.to_dict().get('student_email') == user_email)
        and str(r.to_dict().get('event_id')) in target_event_ids
    ]
    if not reg_docs:
        flash("You must be registered for this hackathon to submit a project.", "warning")
        return redirect(url_for('public.event_details', event_id=event_id))

    reg_doc = reg_docs[0]
    reg_data = reg_doc.to_dict()
    reg_id = reg_doc.id
    team_name = reg_data.get('team_name') or reg_data.get('lead_name') or 'Team'

    # Check for existing submission
    sub_docs = list(db.collection('project_submissions').stream())
    existing = [s for s in sub_docs if str(s.to_dict().get('registration_id')) in {str(reg_id), str(to_uuid(reg_id))}]

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
        return redirect(url_for('public.index'))

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
        return redirect(url_for('public.index'))

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
