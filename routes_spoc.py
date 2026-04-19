from flask import Blueprint, render_template, request, redirect, session, flash, Response, url_for
from models import db, FirebaseWrapper
import datetime
import csv
import io
import json
from utils import login_required, role_required

spoc_bp = Blueprint('spoc', __name__, url_prefix='/spoc')

# --- 1. SPOC DASHBOARD ---
@spoc_bp.route('/dashboard')
@login_required
@role_required('ClubSPOC')
def dashboard():
    spoc_id = session.get('user_id')
    query = db.collection('events').where('spoc_id', '==', spoc_id).stream()
    
    events = []
    total_regs = 0

    for doc in query:
        data = doc.to_dict()
        reg_count = len(list(db.collection('registrations').where('event_id', '==', doc.id).stream()))
        total_regs += reg_count
        data['registration_count'] = reg_count 
        events.append(FirebaseWrapper(doc.id, data))

    return render_template('spoc/dashboard.html', 
                          events=events, 
                          stats={'total_events': len(events), 'total_regs': total_regs},
                          category=session.get('category', 'General'))

# --- 2. CREATE EVENT (DYNAMIC BUILDER) ---
@spoc_bp.route('/create_event', methods=['GET', 'POST'])
@login_required
@role_required('ClubSPOC')
def create_event():
    if request.method == 'GET':
        return render_template('spoc/create_event.html') 

    try:
        def get_bool(key): return True if request.form.get(key) == 'on' else False
        def get_int(key, default=0): 
            try: return int(request.form.get(key, default))
            except: return default
        
        # 1. Capture Multiple Coordinators (Comma separated string -> List)
        coord_string = request.form.get('coordinators', '')
        coordinators_list = [email.strip().lower() for email in coord_string.split(',') if email.strip()]

        # 2. Dynamic Form Schema (Strictly defined by SPOC)
        form_schema = {
            'require_lead_whatsapp': get_bool('req_lead_whatsapp'),
            'require_member_usn': get_bool('req_member_usn'),
            'require_member_email': get_bool('req_member_email'),
            'require_member_whatsapp': get_bool('req_member_whatsapp'),
            'submission_type': request.form.get('submission_type', 'none') # 'github', 'drive', 'none'
        }

        # 3. Allowed Years
        allowed_years = []
        if get_bool('year_1'): allowed_years.append(1)
        if get_bool('year_2'): allowed_years.append(2)
        if get_bool('year_3'): allowed_years.append(3)
        if get_bool('year_4'): allowed_years.append(4)

        event_data = {
            'title': request.form.get('title'),
            'category': request.form.get('category'),
            'description': request.form.get('description'),
            'rules': request.form.get('rules'),
            'banner_url': request.form.get('banner_url') or 'https://placehold.co/800x400?text=Event',
            'visibility': request.form.get('visibility'),
            'date': request.form.get('date'),
            'time': request.form.get('time'),
            'reg_deadline': request.form.get('reg_deadline'),
            'venue': request.form.get('venue'),
            'participation_type': request.form.get('participation_type'),
            'is_team_event': request.form.get('participation_type') in ['Team', 'Both'],
            
            # KEY NEW FIELDS
            'coordinators': coordinators_list, # Array of emails
            'form_schema': form_schema,        # The exact form requirements
            
            'limits': {
                'team_min': get_int('team_min', 1),
                'team_max': get_int('team_max', 1),
                'max_participants': get_int('max_participants', 0),
                'allowed_years': allowed_years
            },
            'fees': {'regular': get_int('reg_fee', 0)},
            'prizes': {
                '1st': request.form.get('prize_1'),
                '2nd': request.form.get('prize_2'),
                '3rd': request.form.get('prize_3')
            },
            
            'spoc_id': session['user_id'],
            'organizer': {
                'name': session.get('name'), 
                'email': session.get('user_id'),
                'phone': '9999999999', # Placeholder, ideally fetch from profile
                'group_link': '#'
            },
            'status': 'active',
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'results_published': False
        }

        db.collection('events').add(event_data)
        flash(f"Event '{event_data['title']}' Published with Custom Rules!", "success")
        return redirect('/spoc/dashboard')
        
    except Exception as e:
        print(f"Error: {e}")
        flash(f"Error creating event: {str(e)}", "danger")
        return redirect('/spoc/create_event')

# --- 3. EXPORT CSV ---
@spoc_bp.route('/export_csv/<event_id>')
@login_required
@role_required('ClubSPOC')
def export_csv(event_id):
    try:
        event_doc = db.collection('events').document(event_id).get()
        title = event_doc.to_dict().get('title', 'Event')
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Team/Name', 'Lead Email', 'Members', 'Status', 'Attendance', 'Score', 'Date'])
        regs = db.collection('registrations').where('event_id', '==', event_id).stream()
        for doc in regs:
            r = doc.to_dict()
            member_count = len(r.get('members', []))
            scores = r.get('scores', {})
            final_score = max([v['total'] for v in scores.values()]) if scores else 0
            writer.writerow([r.get('team_name', 'Individual'), r.get('lead_email'), f"{member_count} Members", r.get('status'), r.get('attendance'), final_score, r.get('registered_at')])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename={title}_report.csv"})
    except:
        return redirect('/spoc/dashboard')

# --- 4. RESULTS DASHBOARD ---
@spoc_bp.route('/results/<event_id>')
@login_required
@role_required('ClubSPOC')
def event_results(event_id):
    # 1. Fetch Event
    event_doc = db.collection('events').document(event_id).get()
    event = event_doc.to_dict()
    event['id'] = event_id

    # 2. Fetch Registrations
    regs_ref = db.collection('registrations').where('event_id', '==', event_id).stream()
    
    leaderboard = []
    
    for r in regs_ref:
        data = r.to_dict()
        data['id'] = r.id
        
        # 3. Calculate Scores
        scores_map = data.get('scores', {})
        total_score = sum([s.get('total', 0) for s in scores_map.values()])
        judge_count = len(scores_map)
        
        avg_score = round(total_score / judge_count, 2) if judge_count > 0 else 0
        
        data['final_score'] = avg_score
        data['judge_count'] = judge_count
        
        leaderboard.append(data)

    # 4. Sort by Highest Score
    leaderboard.sort(key=lambda x: x['final_score'], reverse=True)

    return render_template('spoc/results.html', event=event, leaderboard=leaderboard)

# --- 5. PUBLISH RESULTS ---
@spoc_bp.route('/publish_results/<event_id>', methods=['POST'])
@login_required
@role_required('ClubSPOC')
def publish_results(event_id):
    try:
        # Mark event as "Ended" and "Results Published"
        db.collection('events').document(event_id).update({
            'status': 'completed',
            'results_published': True
        })
        flash("Results have been published to the student portal!", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
        
    return redirect(f'/spoc/results/{event_id}')



