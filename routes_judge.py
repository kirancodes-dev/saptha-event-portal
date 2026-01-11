from flask import Blueprint, render_template, session, redirect, request, flash
from models import db, Event, Team, Judge, Score

judge_bp = Blueprint('judge_bp', __name__, url_prefix='/judge')

@judge_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'Judge': return redirect('/login')
    
    judge_id = session.get('user_id')
    # Fetch events assigned to this judge
    my_events = Event.query.filter(Event.judges.any(id=judge_id)).all()
    
    return render_template('dashboard_judge.html', events=my_events)

@judge_bp.route('/evaluate/<int:event_id>')
def evaluate(event_id):
    if session.get('role') != 'Judge': return redirect('/login')
    
    event = Event.query.get_or_404(event_id)
    # Get all approved teams for this event
    teams = Team.query.filter_by(event_id=event_id, approval_status='Approved').all()
    
    # Calculate Leaderboard
    leaderboard = []
    for team in teams:
        # Get all scores for this team
        scores = Score.query.filter_by(team_id=team.id).all()
        avg_score = sum([s.total_score for s in scores]) / len(scores) if scores else 0
        leaderboard.append({'name': team.name, 'score': round(avg_score, 1)})
    
    # Sort leaderboard
    leaderboard.sort(key=lambda x: x['score'], reverse=True)

    return render_template('judge_evaluate.html', event=event, teams=teams, leaderboard=leaderboard)

@judge_bp.route('/submit_score', methods=['POST'])
def submit_score():
    if session.get('role') != 'Judge': return redirect('/login')
    
    try:
        team_id = request.form.get('team_id')
        event_id = request.form.get('event_id')
        
        c1 = int(request.form.get('c1') or 0)
        c2 = int(request.form.get('c2') or 0)
        c3 = int(request.form.get('c3') or 0)
        c4 = int(request.form.get('c4') or 0)
        
        total = c1 + c2 + c3 + c4
        
        # Check if score exists for this judge & team, update it
        existing_score = Score.query.filter_by(team_id=team_id, judge_id=session['user_id']).first()
        
        if existing_score:
            existing_score.criteria_1 = c1
            existing_score.criteria_2 = c2
            existing_score.criteria_3 = c3
            existing_score.criteria_4 = c4
            existing_score.total_score = total
            existing_score.feedback = request.form.get('feedback')
            flash("Score updated!", "info")
        else:
            new_score = Score(
                team_id=team_id,
                judge_id=session['user_id'],
                event_id=event_id,
                criteria_1=c1, criteria_2=c2, criteria_3=c3, criteria_4=c4,
                total_score=total,
                feedback=request.form.get('feedback')
            )
            db.session.add(new_score)
            flash("Score submitted!", "success")
            
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting score: {str(e)}", "danger")
        
    return redirect(f'/judge/evaluate/{event_id}')