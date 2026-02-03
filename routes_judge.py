from flask import Blueprint, render_template, request, redirect, session, flash, url_for
from models import db, FirebaseWrapper
import datetime

judge_bp = Blueprint('judge', __name__, url_prefix='/judge')

# --- 1. DASHBOARD (List Assigned Events) ---
@judge_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'Judge': 
        return redirect('/login')
    
    user_email = session.get('user_id')
    
    # Find events where this user's email is in the 'judge_ids' array
    # Note: Firestore 'array-contains' query
    events_ref = db.collection('events')
    query = events_ref.where('judge_ids', 'array_contains', user_email).stream()
    
    my_events = []
    for doc in query:
        data = doc.to_dict()
        my_events.append(FirebaseWrapper(doc.id, data))
        
    return render_template('judge/dashboard.html', events=my_events)

# --- 2. EVENT VIEW (List Teams) ---
@judge_bp.route('/event/<event_id>')
def view_event(event_id):
    if session.get('role') != 'Judge': return redirect('/login')
    
    # Get Event Details
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists: return redirect('/judge/dashboard')
    event_data = FirebaseWrapper(event_id, event_doc.to_dict())
    
    # Get Teams (Registrations)
    # We only show teams that have marked attendance as 'Present' (Optional logic)
    # For now, show all.
    teams_ref = db.collection('registrations').where('event_id', '==', event_id).stream()
    
    teams = []
    for t in teams_ref:
        data = t.to_dict()
        # Check if this judge has already scored this team
        # We look for a sub-collection or a 'scores' field. 
        # Simple approach: Check a 'scores' map inside the registration doc
        # Structure: registration.scores = { 'judge_email': 45, ... }
        
        has_scored = False
        score_val = 0
        if 'scores' in data and session['user_id'] in data['scores']:
            has_scored = True
            score_val = data['scores'][session['user_id']]['total']
            
        data['has_scored'] = has_scored
        data['my_score'] = score_val
        teams.append(FirebaseWrapper(t.id, data))
        
    return render_template('judge/event_view.html', event=event_data, teams=teams)

# --- 3. SCORE TEAM (Form) ---
@judge_bp.route('/score/<event_id>/<reg_id>', methods=['GET', 'POST'])
def score_team(event_id, reg_id):
    if session.get('role') != 'Judge': return redirect('/login')
    
    reg_ref = db.collection('registrations').document(reg_id)
    reg_doc = reg_ref.get()
    
    if request.method == 'POST':
        try:
            # Capture Scores
            criteria = {
                'innovation': int(request.form.get('innovation')),
                'feasibility': int(request.form.get('feasibility')),
                'tech_stack': int(request.form.get('tech_stack')),
                'presentation': int(request.form.get('presentation')),
                'impact': int(request.form.get('impact'))
            }
            total = sum(criteria.values())
            
            # Save Score Object
            score_entry = {
                'judge_name': session.get('name'),
                'judge_email': session.get('user_id'),
                'criteria': criteria,
                'total': total,
                'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Update Firestore using Dot Notation for specific judge key
            # This prevents overwriting other judges' scores
            judge_key = session.get('user_id').replace('.', '_') # Firestore keys can't have dots
            
            # Note: In a real app, use a subcollection 'judging' for scalability.
            # Here we use a map field 'scores' for simplicity.
            # We must fetch, update dict, and set back to avoid "dot in key" issues if using direct update.
            
            reg_data = reg_doc.to_dict()
            current_scores = reg_data.get('scores', {})
            current_scores[session.get('user_id')] = score_entry
            
            reg_ref.update({'scores': current_scores})
            
            flash("Score submitted successfully!", "success")
            return redirect(url_for('judge.view_event', event_id=event_id))
            
        except Exception as e:
            flash(f"Error submitting score: {e}", "danger")

    return render_template('judge/score_sheet.html', team=reg_doc.to_dict(), event_id=event_id, reg_id=reg_id)