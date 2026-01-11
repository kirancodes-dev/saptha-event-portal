from flask import Blueprint, render_template, session, redirect, request, flash
from models import db

judge_bp = Blueprint('judge_bp', __name__, url_prefix='/judge')

# Wrapper for Dot Notation
class FirebaseWrapper:
    def __init__(self, id, data):
        self.id = id
        self._data = data
    def __getattr__(self, name):
        return self._data.get(name)

@judge_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'Judge': return redirect('/login')
    
    judge_email = session['user_id']
    # Find events where 'judge_ids' array contains my email
    query = db.collection('events').where('judge_ids', 'array_contains', judge_email).stream()
    
    my_events = [FirebaseWrapper(doc.id, doc.to_dict()) for doc in query]
    return render_template('dashboard_judge.html', events=my_events)

@judge_bp.route('/evaluate/<event_id>')
def evaluate(event_id):
    if session.get('role') != 'Judge': return redirect('/login')
    
    event_doc = db.collection('events').document(event_id).get()
    event_obj = FirebaseWrapper(event_id, event_doc.to_dict())
    
    # Get Approved Teams
    teams_query = db.collection('teams').where('event_id', '==', event_id).where('approval_status', '==', 'Approved').stream()
    teams = [FirebaseWrapper(doc.id, doc.to_dict()) for doc in teams_query]
    
    # Calculate Leaderboard
    leaderboard = []
    for team in teams:
        scores_ref = db.collection('scores').where('team_id', '==', team.id).stream()
        total = 0
        count = 0
        for s in scores_ref:
            total += s.to_dict().get('total_score', 0)
            count += 1
        
        avg = round(total / count, 1) if count > 0 else 0
        leaderboard.append({'name': team.name, 'score': avg})
    
    leaderboard.sort(key=lambda x: x['score'], reverse=True)
    return render_template('judge_evaluate.html', event=event_obj, teams=teams, leaderboard=leaderboard)

@judge_bp.route('/submit_score', methods=['POST'])
def submit_score():
    try:
        team_id = request.form.get('team_id')
        event_id = request.form.get('event_id')
        judge_id = session['user_id']
        
        c1 = int(request.form.get('c1') or 0)
        c2 = int(request.form.get('c2') or 0)
        c3 = int(request.form.get('c3') or 0)
        c4 = int(request.form.get('c4') or 0)
        total = c1 + c2 + c3 + c4
        
        score_data = {
            'team_id': team_id,
            'event_id': event_id,
            'judge_id': judge_id,
            'criteria_1': c1, 'criteria_2': c2, 'criteria_3': c3, 'criteria_4': c4,
            'total_score': total,
            'feedback': request.form.get('feedback')
        }
        
        # Check if score exists
        query = db.collection('scores').where('team_id', '==', team_id).where('judge_id', '==', judge_id).get()
        
        if len(query) > 0:
            # Update existing
            doc_id = query[0].id
            db.collection('scores').document(doc_id).update(score_data)
            flash("Score Updated", "info")
        else:
            # Create new
            db.collection('scores').add(score_data)
            flash("Score Submitted", "success")
            
    except Exception as e:
        flash(f"Error: {e}", "danger")
        
    return redirect(f'/judge/evaluate/{event_id}')