from flask import Blueprint, render_template, session, redirect, request, flash
from models import db, Participant, Event, Team, Announcement
from datetime import datetime

participant_bp = Blueprint('participant_bp', __name__, url_prefix='/participant')

@participant_bp.route('/dashboard')
def dashboard():
    if session.get('role') != 'Participant': return redirect('/login')
    
    user_id = session.get('user_id')
    participant = Participant.query.get(user_id)
    
    if not participant:
        session.clear()
        return redirect('/login')

    # --- 1. BUILD SMART EVENT DATA (Status, Team, Submissions) ---
    my_events_data = []
    registered_events = participant.events_attended
    
    now = datetime.now()
    
    for event in registered_events:
        # Find User's Team for this event
        my_team = Team.query.filter_by(event_id=event.id).filter(Team.members.any(id=user_id)).first()
        
        # Determine Status
        status = "Registered"
        status_class = "primary"
        
        if my_team and my_team.project_link:
            status = "Submitted"
            status_class = "success"
        elif event.date < now:
            status = "Completed"
            status_class = "dark"
        elif event.date.date() == now.date():
            status = "Ongoing"
            status_class = "danger fw-bold blink"
        
        my_events_data.append({
            'event': event,
            'team': my_team,
            'status': status,
            'status_class': status_class,
            'has_submission': bool(my_team and my_team.project_link)
        })

    # --- 2. FETCH ANNOUNCEMENTS ---
    my_event_ids = [e.id for e in registered_events]
    notifications = Announcement.query.filter(Announcement.event_id.in_(my_event_ids))\
                                      .order_by(Announcement.timestamp.desc()).limit(5).all()

    # --- 3. UPCOMING EVENTS ---
    all_events = Event.query.filter_by(is_published=True).all()
    upcoming_events = [e for e in all_events if e not in registered_events and e.date > now]

    return render_template('dashboard_participant.html', 
                           participant=participant, 
                           my_events_data=my_events_data, 
                           notifications=notifications,
                           upcoming_events=upcoming_events)

# --- ROBUST REGISTRATION LOGIC ---
@participant_bp.route('/register_event', methods=['POST'])
def register_event():
    if session.get('role') != 'Participant': return redirect('/login')
    
    try:
        user_id = session.get('user_id')
        event_id = request.form.get('event_id')
        participant = Participant.query.get(user_id)
        event = Event.query.get(event_id)

        # Check existing registration
        if event in participant.events_attended:
            flash("You are already registered for this event.", "info")
            return redirect('/participant/dashboard')

        # Handle Team Creation
        if event.event_type == 'Team':
            team_name = request.form.get('team_name')
            
            new_team = Team(
                name=team_name, 
                code=f"T-{event.id}-{user_id}-{str(hash(team_name))[-4:]}",
                event_id=event.id
            )
            new_team.members.append(participant)
            
            # Add Teammates
            member_emails = request.form.getlist('member_emails')
            for email in member_emails:
                if email and email.strip():
                    email = email.strip()
                    mem = Participant.query.filter_by(email=email).first()
                    
                    if mem:
                        # Prevent duplicate errors
                        if mem.id == participant.id: continue # Don't add self
                        if mem not in new_team.members:
                            new_team.members.append(mem)
                        if event not in mem.events_attended:
                            mem.events_attended.append(event)
            
            db.session.add(new_team)

        # Register Self
        if event not in participant.events_attended:
            participant.events_attended.append(event)
        
        db.session.commit()
        flash("Successfully registered!", "success")
        
    except Exception as e:
        db.session.rollback()
        if "UNIQUE constraint" in str(e):
            flash("Registration failed: A team member is already registered.", "warning")
        else:
            flash(f"Error: {str(e)}", "danger")

    return redirect('/participant/dashboard')

# --- SUBMISSION LOGIC ---
@participant_bp.route('/submit_project', methods=['POST'])
def submit_project():
    if session.get('role') != 'Participant': return redirect('/login')
    
    team_id = request.form.get('team_id')
    link = request.form.get('project_link')
    
    team = Team.query.get(team_id)
    if team:
        team.project_link = link
        db.session.commit()
        flash("Project submitted successfully!", "success")
    
    return redirect('/participant/dashboard')