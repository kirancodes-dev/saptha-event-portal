from flask import Blueprint, flash, redirect, render_template, request, session
from models import db
from utils import login_required, role_required, log_action, safe_int

judge_bp = Blueprint('judge', __name__, url_prefix='/judge')

JUDGE_ROLES = ['Judge', 'SuperAdmin', 'Super Admin']


# =========================================================
# 1. JUDGE DASHBOARD
# =========================================================
@judge_bp.route('/dashboard')
@login_required
@role_required(JUDGE_ROLES)
def dashboard():
    email      = session.get('user_id')
    user_role  = session.get('role')
    my_events  = []

    for e in db.collection('events').where('status', '==', 'active').stream():
        data  = e.to_dict()
        staff = data.get('staff', [])
        is_assigned = any(
            s.get('email') == email and s.get('role') == 'Judge'
            for s in staff
        )
        if is_assigned or user_role in ('SuperAdmin', 'Super Admin'):
            data['id'] = e.id
            my_events.append(data)

    return render_template('judge/dashboard.html',
                            events=my_events,
                            user_name=session.get('name'))


# =========================================================
# 2. TEAMS LIST FOR SCORING
# =========================================================
@judge_bp.route('/event/<event_id>')
@login_required
@role_required(JUDGE_ROLES)
def event_teams(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return redirect('/judge/dashboard')

    event          = event_doc.to_dict()
    event['id']    = event_id
    judge_email    = session.get('user_id')
    safe_email_key = judge_email.replace('.', '_')

    regs = (db.collection('registrations')
              .where('event_id', '==', event_id)
              .where('attendance', '==', 'Present')
              .where('assigned_judge_email', '==', judge_email)
              .stream())

    teams = []
    for r in regs:
        d        = r.to_dict()
        d['id']  = r.id
        d['my_score'] = d.get('scores', {}).get(safe_email_key)
        teams.append(d)

    return render_template('judge/teams.html', event=event, teams=teams)


# =========================================================
# 3. SUBMIT SCORE
# =========================================================
@judge_bp.route('/submit_score/<reg_id>', methods=['POST'])
@login_required
@role_required(JUDGE_ROLES)
def submit_score(reg_id):
    try:
        reg_ref  = db.collection('registrations').document(reg_id)
        reg_data = reg_ref.get().to_dict()

        if not reg_data:
            flash("Registration not found.", "danger")
            return redirect('/judge/dashboard')

        event_id  = reg_data.get('event_id')
        event_doc = db.collection('events').document(event_id).get().to_dict()
        criteria  = event_doc.get('judging_criteria', ['Overall Score'])

        score_details = {}
        total_score   = 0
        for c in criteria:
            key = f"score_{c.replace(' ', '_').lower()}"
            val = safe_int(request.form.get(key, 0))
            score_details[c] = val
            total_score      += val

        judge_email    = session.get('user_id')
        safe_email_key = judge_email.replace('.', '_')

        reg_ref.set({
            'scores': {
                safe_email_key: {
                    'details':    score_details,
                    'total':      total_score,
                    'judge_name': session.get('name')
                }
            }
        }, merge=True)

        log_action(db, "SCORE_SUBMITTED",
                   f"Judge {judge_email} scored reg {reg_id} — total {total_score}")
        flash(f"✅ Score of {total_score} saved!", "success")
        return redirect(f'/judge/event/{event_id}')

    except Exception as exc:
        flash(f"Error submitting score: {exc}", "danger")
        return redirect('/judge/dashboard')