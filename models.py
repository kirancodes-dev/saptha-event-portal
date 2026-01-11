from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# --- ASSOCIATION TABLES ---
# Links Participants <-> Events (Many-to-Many)
registrations = db.Table('registrations',
    db.Column('participant_id', db.Integer, db.ForeignKey('participant.id'), primary_key=True),
    db.Column('event_id', db.Integer, db.ForeignKey('event.id'), primary_key=True)
)

# Links Participants <-> Teams (Many-to-Many)
team_membership = db.Table('team_membership',
    db.Column('participant_id', db.Integer, db.ForeignKey('participant.id'), primary_key=True),
    db.Column('team_id', db.Integer, db.ForeignKey('team.id'), primary_key=True)
)

# --- CORE EVENT MODEL ---
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # 1. Basic Metadata
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False) # 'Tech', 'Sports', 'Cultural'
    event_mode = db.Column(db.String(20), default='Offline')
    event_level = db.Column(db.String(20), default='College')
    
    date = db.Column(db.DateTime, nullable=False)
    venue = db.Column(db.String(100))
    time_slot = db.Column(db.String(50))
    reg_deadline = db.Column(db.DateTime)
    
    # 2. Participation Config
    event_type = db.Column(db.String(20), default='Team')
    max_participants = db.Column(db.Integer, default=100)
    team_min = db.Column(db.Integer, default=1)
    team_max = db.Column(db.Integer, default=1)
    allow_inter_college = db.Column(db.Boolean, default=False)
    
    # 3. Tech Specifics
    tech_problem_type = db.Column(db.String(20), default='Predefined') 
    problem_stmt_link = db.Column(db.String(500)) 
    tech_domain = db.Column(db.String(200))
    tech_stack_allowed = db.Column(db.String(200))
    submission_format = db.Column(db.String(50)) 
    rounds_config = db.Column(db.Text) 

    # 4. Evaluation Criteria (Weights)
    eval_innovation = db.Column(db.Integer, default=25)
    eval_tech_complexity = db.Column(db.Integer, default=25)
    eval_feasibility = db.Column(db.Integer, default=20)
    eval_presentation = db.Column(db.Integer, default=15)
    eval_impact = db.Column(db.Integer, default=15)

    # 5. Content
    overview = db.Column(db.Text)
    rules = db.Column(db.Text)
    prizes = db.Column(db.Text)
    image_url = db.Column(db.String(500))
    resource_link = db.Column(db.String(500))
    
    # Status
    is_published = db.Column(db.Boolean, default=False)

    # 6. Relations
    spoc_id = db.Column(db.Integer, db.ForeignKey('club_spoc.id'))
    coord_student_id = db.Column(db.Integer, db.ForeignKey('coordinator.id'))
    coord_staff_id = db.Column(db.Integer, db.ForeignKey('coordinator.id'))
    
    # Backrefs
    teams_rel = db.relationship('Team', backref='event_ref', lazy=True)
    judges = db.relationship('Judge', backref='event', cascade="all, delete")
    announcements = db.relationship('Announcement', backref='event', cascade="all, delete")
    problems = db.relationship('ProblemStatement', backref='event', cascade="all, delete")
    scores = db.relationship('Score', backref='event', cascade="all, delete")

# --- USER ROLES ---
class SuperAdmin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    secret_key = db.Column(db.String(100))

class ClubSPOC(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    category = db.Column(db.String(50)) 

class Coordinator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    role_type = db.Column(db.String(20)) # 'Student' or 'Staff'

class Judge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    expertise = db.Column(db.String(100))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))

class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(15))
    usn = db.Column(db.String(20))
    college = db.Column(db.String(100))
    department = db.Column(db.String(50))
    year = db.Column(db.String(20))
    
    events_attended = db.relationship('Event', secondary=registrations, backref='participants')

# --- OPERATIONAL TABLES ---
class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    project_link = db.Column(db.String(500)) 
    
    # Status Tracking
    approval_status = db.Column(db.String(20), default='Pending') # Pending, Approved, Rejected
    attendance_status = db.Column(db.String(20), default='Absent') # Absent, Present
    
    members = db.relationship('Participant', secondary=team_membership, backref='teams')
    scores = db.relationship('Score', backref='team', cascade="all, delete")

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    judge_id = db.Column(db.Integer, db.ForeignKey('judge.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    
    # Scoring Breakdown
    criteria_1 = db.Column(db.Integer, default=0) # e.g. Innovation
    criteria_2 = db.Column(db.Integer, default=0) # e.g. Tech Stack
    criteria_3 = db.Column(db.Integer, default=0) # e.g. Presentation
    criteria_4 = db.Column(db.Integer, default=0) # e.g. Feasibility
    total_score = db.Column(db.Integer, default=0)
    
    feedback = db.Column(db.Text)

class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='Info') 
    timestamp = db.Column(db.DateTime, default=datetime.now)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))

class ProblemStatement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(10))
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))

# --- PLACEHOLDERS FOR FUTURE MODULES ---
class Fixture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_a = db.Column(db.String(100))
    team_b = db.Column(db.String(100))
    round_name = db.Column(db.String(50))
    match_time = db.Column(db.String(50))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))

class Performance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100))
    activity = db.Column(db.String(100))
    duration = db.Column(db.String(20))
    slot_time = db.Column(db.String(20))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))