from flask import Blueprint, render_template, request, redirect, session, flash
from models import db
from utils import login_required, role_required

judge_bp = Blueprint('judge', __name__, url_prefix='/judge')

# --- 1. JUDGE DASHBOARD (SELECT EVENT) ---
@judge_bp.route('/dashboard')
@login_required
@role_required(['Judge', 'SuperAdmin'])
def dashboard():
    email = session.get('user_id')
    events_ref = db.collection('events').where('status', '==', 'active').stream()
    
    my_events = []
    for e in events_ref:
        data = e.to_dict()
        staff = data.get('staff', [])
        # Show event if they are appointed as a Judge, or if they are SuperAdmin
        if any(s.get('email') == email and s.get('role') == 'Judge' for s in staff) or session.get('role') == 'SuperAdmin':
            data['id'] = e.id
            my_events.append(data)
            
    return render_template('judge/dashboard.html', events=my_events, user_name=session.get('name'))

# --- 2. TEAM SCORING LIST (SMART ALLOCATED) ---
@judge_bp.route('/event/<event_id>')
@login_required
@role_required(['Judge', 'SuperAdmin'])
def event_teams(event_id):
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists: return redirect('/judge/dashboard')
    
    event = event_doc.to_dict()
    event['id'] = event_doc.id

    judge_email = session.get('user_id')

    # ONLY fetch teams that are marked "Present" AND assigned specifically to THIS Judge!
    regs_ref = db.collection('registrations')\
        .where('event_id', '==', event_id)\
        .where('attendance', '==', 'Present')\
        .where('assigned_judge_email', '==', judge_email)\
        .stream()
        
    teams = []
    for r in regs_ref:
        d = r.to_dict()
        d['id'] = r.id
        
        # Check if THIS judge has already scored this team
        my_scores = d.get('scores', {}).get(judge_email.replace('.', '_')) # Handle Firebase dot restriction
        d['my_score'] = my_scores
        teams.append(d)
        
    return render_template('judge/teams.html', event=event, teams=teams)

# --- 3. SUBMIT DYNAMIC SCORES ---
@judge_bp.route('/submit_score/<reg_id>', methods=['POST'])
@login_required
@role_required(['Judge', 'SuperAdmin'])
def submit_score(reg_id):
    try:
        reg_ref = db.collection('registrations').document(reg_id)
        reg_data = reg_ref.get().to_dict()
        event_id = reg_data.get('event_id')
        
        event_doc = db.collection('events').document(event_id).get().to_dict()
        criteria = event_doc.get('judging_criteria', ['Overall Score'])

        # Build the score dictionary dynamically based on the form
        score_details = {}
        total_score = 0
        for c in criteria:
            # We use string manipulation to match the form input names safely
            safe_c_name = c.replace(' ', '_').lower()
            val = int(request.form.get(f'score_{safe_c_name}', 0))
            score_details[c] = val
            total_score += val

        judge_email = session.get('user_id')
        safe_email = judge_email.replace('.', '_') # Firebase keys cannot contain periods
        
        # Save score inside the 'scores' map under the Judge's specific email
        # This allows multiple judges to score the same team without overwriting each other!
        reg_ref.set({
            'scores': {
                safe_email: {
                    'details': score_details,
                    'total': total_score,
                    'judge_name': session.get('name')
                }
            }
        }, merge=True)
        
        flash("Score saved successfully!", "success")
        return redirect(f'/judge/event/{event_id}')
        
    except Exception as e:
        flash(f"Error submitting score: {e}", "danger")
        return redirect('/judge/dashboard')