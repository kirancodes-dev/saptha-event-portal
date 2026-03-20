from flask import Blueprint, flash, redirect, render_template, request, session
from google.cloud.firestore_v1.base_query import FieldFilter
from models import db
from utils import login_required, role_required, log_action, safe_int

judge_bp    = Blueprint('judge', __name__, url_prefix='/judge')
JUDGE_ROLES = ['Judge', 'SuperAdmin', 'Super Admin']


# =========================================================
# 1. JUDGE DASHBOARD
# =========================================================
@judge_bp.route('/dashboard')
@login_required
@role_required(JUDGE_ROLES)
def dashboard():
    email     = session.get('user_id')
    user_role = session.get('role')
    my_events = []

    for e in db.collection('events').where('status', '==', 'active').stream():
        data  = e.to_dict()
        staff = data.get('staff', [])
        is_assigned = any(
            s.get('email') == email and s.get('role') == 'Judge'
            for s in staff
        )
        if is_assigned or user_role in ('SuperAdmin', 'Super Admin'):
            data['id'] = e.id
            # Show open hall mode badge
            data['open_hall'] = data.get('open_hall_mode', False)
            my_events.append(data)

    return render_template('judge/dashboard.html',
                           events=my_events,
                           user_name=session.get('name'))


# =========================================================
# 2. TEAMS LIST FOR SCORING
# In Open Hall Mode: judge sees ALL present teams (not just assigned)
# In Normal Mode:    judge sees only their assigned teams
# =========================================================
@judge_bp.route('/event/<event_id>')
@login_required
@role_required(JUDGE_ROLES)
def event_teams(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return redirect('/judge/dashboard')

    event         = event_doc.to_dict()
    event['id']   = event_id
    judge_email   = session.get('user_id')
    safe_email_key = judge_email.replace('.', '_')
    open_hall     = event.get('open_hall_mode', False)

    if open_hall:
        # Open Hall Mode — all present teams, any judge can score any team
        regs_query = (db.collection('registrations')
                        .where(filter=FieldFilter('event_id',   '==', event_id))
                        .where(filter=FieldFilter('attendance', '==', 'Present'))
                        .stream())
    else:
        # Normal mode — only teams assigned to this judge
        regs_query = (db.collection('registrations')
                        .where(filter=FieldFilter('event_id',            '==', event_id))
                        .where(filter=FieldFilter('attendance',          '==', 'Present'))
                        .where(filter=FieldFilter('assigned_judge_email','==', judge_email))
                        .stream())

    teams = []
    for r in regs_query:
        d           = r.to_dict()
        d['id']     = r.id
        d['my_score'] = d.get('scores', {}).get(safe_email_key)
        d['scored_by_me'] = safe_email_key in d.get('scores', {})
        teams.append(d)

    # Sort: unscored first, then scored
    teams.sort(key=lambda x: (1 if x['scored_by_me'] else 0, x.get('team_name', '')))

    # Get all judges for this event (for open hall mode info)
    all_judges = [s for s in event.get('staff', []) if s.get('role') == 'Judge']

    return render_template('judge/teams.html',
                           event=event,
                           teams=teams,
                           open_hall=open_hall,
                           all_judges=all_judges,
                           judge_email=judge_email)


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
        open_hall = event_doc.get('open_hall_mode', False)

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
                    'judge_name': session.get('name'),
                    'judge_email': judge_email,
                }
            }
        }, merge=True)

        log_action(db, "SCORE_SUBMITTED",
                   f"Judge {judge_email} scored reg {reg_id} — "
                   f"total {total_score} {'[Open Hall]' if open_hall else ''}")
        flash(f"✅ Score of {total_score} saved!", "success")
        return redirect(f'/judge/event/{event_id}')

    except Exception as exc:
        flash(f"Error submitting score: {exc}", "danger")
        return redirect('/judge/dashboard')


# =========================================================
# 4. SCORE SUMMARY (judge's own scores for an event)
# =========================================================
@judge_bp.route('/my_scores/<event_id>')
@login_required
@role_required(JUDGE_ROLES)
def my_scores(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        return redirect('/judge/dashboard')

    event         = event_doc.to_dict()
    event['id']   = event_id
    judge_email   = session.get('user_id')
    safe_key      = judge_email.replace('.', '_')

    scored = []
    for r in (db.collection('registrations')
                .where(filter=FieldFilter('event_id', '==', event_id)).stream()):
        d = r.to_dict()
        if safe_key in d.get('scores', {}):
            scored.append({
                'team_name': d.get('team_name', 'Individual'),
                'lead_name': d.get('lead_name', ''),
                'score':     d['scores'][safe_key],
            })

    scored.sort(key=lambda x: x['score'].get('total', 0), reverse=True)

    return render_template('judge/my_scores.html',
                           event=event,
                           scored=scored,
                           total=len(scored))