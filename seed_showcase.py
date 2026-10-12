"""
seed_showcase.py — a clean, realistic SapthaEvent for demonstrations (UPG-88).

Empties every table (the schema and its migration record stay), then builds the
portal through the app's own routes, so every record is exactly what real use
produces: the SPOC wizard and publishing, the registration form, staff
appointment, judges' scores, results publishing, certificates and feedback.

What it creates:
  * 1 Super Admin, 3 Club SPOCs (Technical & Careers, Cultural, Sports),
    3 event coordinators, 4 judges, 1 volunteer and 60 students
  * the main campus with 4 buildings and 13 rooms
  * 40 upcoming events: two a day for the next 20 days, every kind of event
  * 8 events from the last two weeks, finished: attendance, judges' scores,
    published results, certificates and feedback
  * in-app announcements

Email, WhatsApp, push and AI calls are switched off for the run, and every
account uses the reserved domain @snpsu.test, which never delivers mail, so the
demo can't write to a real person. Passwords come from seed_safety (one per
role; SEED_<ROLE>_PASSWORD or random) and are printed once at the end.

    python seed_showcase.py [--summary demo_summary.json]

Refuses production-looking databases (seed_safety.guard, BLK-10).
"""
# BLK-10: refuse production-looking databases before anything connects
from seed_safety import guard, seed_password  # noqa: E402
guard()

import argparse  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402

# Nothing leaves the machine while seeding: no mail, WhatsApp, push or AI
for _key in ('MAIL_USER', 'MAIL_PASS', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_FROM',
             'VAPID_PRIVATE_KEY', 'GEMINI_API_KEY', 'CELERY_BROKER_URL'):
    os.environ[_key] = ''

from werkzeug.security import generate_password_hash  # noqa: E402

from app import app  # noqa: E402
import models  # noqa: E402
import utils_email  # noqa: E402
import utils_whatsapp  # noqa: E402

utils_email._send = lambda *a, **k: True
utils_whatsapp._send = lambda *a, **k: True
app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, GEMINI_API_KEY='')
from extensions import limiter  # noqa: E402
limiter.enabled = False

db = models.db
random.seed(2026)
TODAY = datetime.date.today()
DOMAIN = 'snpsu.test'          # reserved: mail to it is never delivered (RFC 2606)


# ── Clean slate ────────────────────────────────────────────────────────────

def wipe():
    """Delete every row of every table except the migration record."""
    from sqlalchemy import inspect, text
    from db_pg import get_engine
    engine = get_engine()
    tables = [t for t in inspect(engine).get_table_names() if t != 'alembic_version']
    with engine.begin() as conn:
        if engine.dialect.name == 'sqlite':
            conn.execute(text('PRAGMA foreign_keys=OFF'))
            for t in tables:
                conn.execute(text(f'DELETE FROM "{t}"'))
            conn.execute(text('PRAGMA foreign_keys=ON'))
        else:
            conn.execute(text('TRUNCATE ' + ', '.join(f'"{t}"' for t in tables) + ' CASCADE'))
    return len(tables)


# ── People ─────────────────────────────────────────────────────────────────

PASSWORDS = {}


def password(role):
    PASSWORDS[role] = seed_password(role)
    return PASSWORDS[role]


def person(email, name, role, **extra):
    doc = {'email': email, 'name': name, 'role': role, 'is_active': True, 'needs_password_reset': False,
           'password': generate_password_hash(password(role)), 'email_verified': True,
           'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    doc.update(extra)
    db.collection('users').document(email).set(doc)
    return {'email': email, 'name': name, 'role': role, **extra}


ADMIN = dict(email=f'admin@{DOMAIN}', name='Dr. Sunil Kumar', designation='Dean, Student Affairs')
SPOCS = {
    'T': dict(email=f'tech.spoc@{DOMAIN}', name='Dr. Ananya Rao', category='Technical',
              department='Computer Science & Engineering', club='Technical Club & Career Cell'),
    'C': dict(email=f'cultural.spoc@{DOMAIN}', name='Prof. Meera Iyer', category='Cultural',
              department='Humanities & Arts', club='Cultural Committee'),
    'S': dict(email=f'sports.spoc@{DOMAIN}', name='Mr. Rahul Gowda', category='Sports',
              department='Physical Education', club='Sports & Wellness Council'),
}
COORDS = {
    'T': dict(email=f'coord.tech@{DOMAIN}', name='Suresh Babu'),
    'C': dict(email=f'coord.cultural@{DOMAIN}', name='Lakshmi Prasad'),
    'S': dict(email=f'coord.sports@{DOMAIN}', name='Kiran Shetty'),
}
JUDGES = [
    dict(email=f'judge.arun@{DOMAIN}', name='Dr. Arun Menon', department='Computer Science & Engineering'),
    dict(email=f'judge.kavitha@{DOMAIN}', name='Prof. Kavitha Nair', department='Performing Arts'),
    dict(email=f'judge.ramesh@{DOMAIN}', name='Dr. Ramesh Hegde', department='Management Studies'),
    dict(email=f'judge.deepa@{DOMAIN}', name='Prof. Deepa Kulkarni', department='Electronics & Communication'),
]
VOLUNTEER = dict(email=f'volunteer@{DOMAIN}', name='Nikhil Raj')

FIRST = ['Aarav', 'Diya', 'Ishaan', 'Meera', 'Kabir', 'Ananya', 'Rohan', 'Sneha', 'Vikram', 'Priya', 'Arjun',
         'Kavya', 'Nikhil', 'Pooja', 'Rahul', 'Tanvi', 'Siddharth', 'Riya', 'Aditya', 'Neha', 'Varun', 'Shreya',
         'Karthik', 'Divya', 'Manoj', 'Bhavana', 'Harsha', 'Nandini', 'Pranav', 'Sahana']
LAST = ['Sharma', 'Rao', 'Iyer', 'Patil', 'Gowda', 'Reddy', 'Nair', 'Kulkarni', 'Hegde', 'Menon', 'Shetty',
        'Bhat', 'Naidu', 'Prasad', 'Joshi']
DEPTS = [('CS', 'Computer Science & Engineering'), ('IS', 'Information Science & Engineering'),
         ('AI', 'Artificial Intelligence & Machine Learning'), ('EC', 'Electronics & Communication'),
         ('ME', 'Mechanical Engineering'), ('CV', 'Civil Engineering'), ('BA', 'BBA'), ('MB', 'MBA'),
         ('BC', 'BCA')]


def make_students(n=60):
    out, used = [], set()
    for i in range(n):
        while True:
            first, last = random.choice(FIRST), random.choice(LAST)
            if (first, last) not in used:
                used.add((first, last))
                break
        code, dept = DEPTS[i % len(DEPTS)]
        degree, length = {'BA': ('BBA', 3), 'MB': ('MBA', 2), 'BC': ('BCA', 3)}.get(code, (f'B.Tech - {dept}', 4))
        year = 1 + i % min(length, 4)
        joined = TODAY.year - (year - 1) if TODAY.month >= 8 else TODAY.year - year
        usn = f"1SN{joined % 100:02d}{code}{100 + i:03d}"
        email = f"{first.lower()}.{last.lower()}@{DOMAIN}"
        out.append(person(email, f'{first} {last}', 'Student', usn=usn, department=dept, year=year,
                          degree=degree, batch=f'{joined}–{joined + length}', college='Sapthagiri NPS University',
                          phone=f'+91 9{random.randint(100000000, 999999999)}', participant_type='student',
                          category='General'))
    return out


# ── Logging in through the real login form ─────────────────────────────────

def login(email, role):
    client = app.test_client()
    data = {'role': role, 'email': email, 'password': PASSWORDS[role]}
    if role == 'SuperAdmin':
        data['secret_key'] = app.config.get('MASTER_SECRET_KEY', '')
    resp = client.post('/login', data=data)
    if resp.status_code != 302 or resp.headers.get('Location', '').endswith('/login'):
        sys.exit(f'Login failed for {email} ({role}); stopping.')
    return client


# ── Venues ─────────────────────────────────────────────────────────────────

BUILDINGS = [
    ('CSE & Mechanical Block', 'CME', [('CSE Lab 1', 'CL1', 60, 'lab'), ('CSE Lab 2', 'CL2', 60, 'lab'),
                                       ('Esports Arena (CSE Lab 3)', 'CL3', 40, 'lab'),
                                       ('Aryabhata Seminar Hall', 'ASH', 150, 'seminar_hall'),
                                       ('Robotics Lab', 'RBL', 40, 'lab')]),
    ('Main Academic Block', 'MAB', [('Main Auditorium', 'AUD', 800, 'auditorium'),
                                    ('Seminar Hall 2', 'SH2', 120, 'seminar_hall'),
                                    ('Innovation Centre', 'INC', 200, 'hall'),
                                    ('Exhibition Foyer', 'EXF', 300, 'hall')]),
    ('Sports Complex', 'SPC', [('Indoor Sports Complex', 'ISC', 300, 'sports'),
                               ('Main Ground', 'MGR', 2000, 'ground')]),
    ('Management Block', 'MGT', [('MBA Seminar Hall', 'MSH', 120, 'seminar_hall'),
                                 ('Open Air Theatre', 'OAT', 1000, 'outdoor')]),
]


def make_venues(admin):
    admin.post('/admin/venues/campus/create', data={
        'name': 'SNPSU Main Campus', 'slug': 'main-campus',
        'address': '#14/5, Chikkasandra, Hesarghatta Main Road, Bengaluru 560057'})
    rooms = {}
    for bname, code, room_list in BUILDINGS:
        admin.post('/admin/venues/building/create', data={'campus_id': 'main-campus', 'name': bname, 'code': code})
        bid = 'bldg_' + re.sub(r'[^a-z0-9]+', '-', bname.lower()).strip('-')
        for rname, number, cap, kind in room_list:
            admin.post('/admin/venues/room/create', data={
                'building_id': bid, 'name': rname, 'room_number': number, 'capacity': cap, 'type': kind,
                'facilities': 'Projector, Wi-Fi' if kind in ('lab', 'seminar_hall', 'hall') else ''})
            rooms[rname] = 'room_' + re.sub(r'[^a-z0-9]+', '-', rname.lower()).strip('-')
    return rooms


# ── Events ─────────────────────────────────────────────────────────────────
# (day offset, slot, SPOC, type, title, settings). Slots: A morning, B afternoon.

CRIT = {
    'tech': [('Innovation', 30), ('Technical depth', 30), ('Execution', 20), ('Presentation', 20)],
    'perf': [('Technique', 40), ('Creativity', 30), ('Stage presence', 30)],
    'talk': [('Content', 40), ('Delivery', 30), ('Rebuttal', 30)],
    'biz': [('Problem understanding', 30), ('Solution', 40), ('Pitch', 30)],
    'quiz': [('Score', 100)],
}

UPCOMING = [
    (1, 'A', 'T', 'workshop', 'Hands-on Workshop: Building AI Agents with Python',
     dict(room='CSE Lab 1', fee=0, cap=60, details={'trainer': 'Dr. Ananya Rao', 'prerequisites': 'Basic Python',
                                                     'bring': 'Laptop with Python 3.11'})),
    (1, 'B', 'S', 'sports_tournament', 'Inter-Department Badminton Championship',
     dict(room='Indoor Sports Complex', fee=100, team=(2, 2), details={'sport': 'Badminton', 'format': 'Knockout',
                                                                        'gender': 'Mixed'})),
    (2, 'A', 'T', 'seminar', 'Seminar: Careers in Cloud Computing',
     dict(room='Aryabhata Seminar Hall', category='Technical',
          details={'speaker': 'Ms. Shruti Desai', 'speaker_designation': 'Cloud Solutions Architect'})),
    (2, 'B', 'C', 'cultural_competition', 'Swara 2026: Solo Singing Competition',
     dict(room='Main Auditorium', fee=50, crit='perf', participation='Individual',
          details={'discipline': 'Music', 'performance_size': 'Solo', 'time_limit_minutes': '5'})),
    (3, 'A', 'T', 'coding_contest', 'CodeSprint: Three-Hour Coding Contest',
     dict(room='CSE Lab 2', crit='tech', details={'platform': 'HackerRank', 'duration_hours': '3',
                                                    'languages': 'C++, Java, Python'})),
    (3, 'B', 'C', 'debate', 'Inter-Department Debate: AI in Education',
     dict(room='Seminar Hall 2', crit='talk', details={'style': 'Debate', 'language': 'English'})),
    (4, 'A', 'S', 'athletics', 'Annual Athletics Meet: Track Events',
     dict(room='Main Ground', time=('07:00', '11:00'), details={'disciplines': '100 m, 400 m, 4 x 100 m relay',
                                                                 'gender': 'Open'})),
    (4, 'B', 'T', 'case_competition', 'Case Study Challenge: Startup Strategy',
     dict(room='MBA Seminar Hall', fee=100, crit='biz', category='Management', details={'kind': 'Case study'})),
    (5, 'A', 'T', 'hackathon', 'HackSaptha 2026: 24-Hour Hackathon',
     dict(room='Innovation Centre', fee=300, crit='tech', time=('09:00', '09:00'), days=1, team=(2, 4),
          prizes=('₹25,000', '₹15,000', '₹10,000'),
          details={'duration_hours': '24', 'themes': 'Smart campus, Health tech, Sustainability'})),
    (5, 'B', 'C', 'cultural_show', 'Nritya Sandhya: Classical Dance Evening',
     dict(room='Main Auditorium', time=('17:30', '20:00'), details={'performers': 'Students of the Dance Club'})),
    (6, 'A', 'S', 'sports_tournament', 'Inter-Department Football League',
     dict(room='Main Ground', fee=300, team=(7, 11), time=('07:30', '12:00'),
          details={'sport': 'Football', 'format': 'League then knockout', 'gender': 'Men'})),
    (6, 'B', 'S', 'esports', 'Valorant Campus Cup',
     dict(room='Esports Arena (CSE Lab 3)', fee=250, team=(5, 5),
          details={'game': 'Valorant', 'platform': 'PC', 'format': 'Knockout'})),
    (7, 'A', 'T', 'guest_lecture', 'Guest Lecture: Cybersecurity in Practice',
     dict(room='Aryabhata Seminar Hall', category='Technical',
          details={'speaker': 'Mr. Abhishek Varma', 'speaker_designation': 'Security Lead, FinTech industry'})),
    (7, 'B', 'C', 'cultural_competition', 'Rangotsava: Rangoli and Art Competition',
     dict(room='Exhibition Foyer', crit='perf', participation='Individual',
          details={'discipline': 'Art & painting', 'performance_size': 'Solo'})),
    (8, 'A', 'T', 'workshop', 'Workshop: Full-Stack Web Development with Flask',
     dict(room='CSE Lab 1', fee=200, cap=60, details={'trainer': 'Prof. Vinay Kumar',
                                                       'prerequisites': 'HTML and Python basics'})),
    (8, 'B', 'S', 'sports_tournament', 'Table Tennis Open',
     dict(room='Indoor Sports Complex', participation='Individual', team=(1, 1),
          details={'sport': 'Table tennis', 'format': 'Knockout', 'gender': 'Open'})),
    (9, 'A', 'T', 'quiz', 'TechQuiz 2026: Science and Technology Quiz',
     dict(room='Seminar Hall 2', crit='quiz', team=(2, 3), details={'quiz_format': 'Written prelims + stage finals',
                                                                     'topic': 'Science, technology and innovation'})),
    (9, 'B', 'C', 'cultural_competition', 'Battle of the Bands',
     dict(room='Open Air Theatre', fee=300, crit='perf', team=(3, 6), time=('16:00', '20:00'),
          details={'discipline': 'Music', 'performance_size': 'Group', 'time_limit_minutes': '15'})),
    (10, 'A', 'T', 'placement_drive', 'Campus Placement Drive: Nimbus Technologies',
     dict(room='Innovation Centre', category='Management', placement_company='Nimbus Technologies Pvt. Ltd.')),
    (10, 'B', 'T', 'paper_presentation', 'National Paper Presentation: Emerging Technologies',
     dict(room='Seminar Hall 2', fee=150, crit='tech', team=(1, 2),
          details={'domains': 'AI, IoT, Renewable energy, Biomedical'})),
    (11, 'A', 'S', 'sports_tournament', 'Inter-Department Cricket Tournament (T10)',
     dict(room='Main Ground', fee=500, team=(11, 15), time=('07:00', '13:00'),
          details={'sport': 'Cricket', 'format': 'Knockout', 'gender': 'Men'})),
    (11, 'B', 'C', 'cultural_competition', 'Nukkad Natak: Street Play Competition',
     dict(room='Open Air Theatre', crit='perf', team=(6, 12),
          details={'discipline': 'Drama / theatre', 'performance_size': 'Group', 'language': 'Kannada / English'})),
    (12, 'A', 'T', 'webinar', 'Webinar: Research Writing and Publishing',
     dict(mode='online', online='https://meet.snpsu.test/research-writing', category='Technical',
          details={'speaker': 'Dr. Latha Krishnan', 'speaker_designation': 'Research Dean'})),
    (12, 'B', 'T', 'club_activity', 'Robotics Club: Line-Follower Build Session',
     dict(room='Robotics Lab', cap=40, details={'club': 'Robotics Club'})),
    (13, 'A', 'S', 'sports_tournament', "Women's Throwball Championship",
     dict(room='Main Ground', team=(7, 12), time=('07:30', '11:30'),
          details={'sport': 'Throwball', 'format': 'League', 'gender': 'Women'})),
    (13, 'B', 'C', 'cultural_competition', 'Campus Through the Lens: Photography Contest',
     dict(room='Exhibition Foyer', crit='perf', participation='Individual',
          details={'discipline': 'Photography', 'performance_size': 'Solo'})),
    (14, 'A', 'T', 'project_expo', 'Final-Year Project Expo 2026',
     dict(room='Exhibition Foyer', crit='tech', team=(1, 4), details={'domains': 'All engineering branches'})),
    (14, 'B', 'T', 'seminar', 'Seminar: Entrepreneurship and Startups',
     dict(room='MBA Seminar Hall', category='Management',
          details={'speaker': 'Ms. Pallavi Rao', 'speaker_designation': 'Founder, campus-born startup'})),
    (15, 'A', 'S', 'esports', 'BGMI Mobile Showdown',
     dict(room='Esports Arena (CSE Lab 3)', fee=200, team=(4, 4),
          details={'game': 'BGMI', 'platform': 'Mobile', 'format': 'League then knockout'})),
    (15, 'B', 'C', 'cultural_competition', 'Step Up: Group Dance Championship',
     dict(room='Main Auditorium', fee=200, crit='perf', team=(4, 10), time=('15:00', '19:00'),
          details={'discipline': 'Dance', 'performance_size': 'Group', 'time_limit_minutes': '8'})),
    (16, 'A', 'C', 'social_drive', 'Blood Donation Camp',
     dict(room='Innovation Centre', category='Social', details={'cause': 'Blood donation',
                                                                'partner': 'Sapthagiri Hospital blood bank'})),
    (16, 'B', 'T', 'workshop', 'Workshop: Data Analytics with Power BI',
     dict(room='CSE Lab 2', fee=150, category='Management', cap=60,
          details={'trainer': 'Dr. Ramesh Hegde', 'bring': 'Laptop'})),
    (17, 'A', 'S', 'athletics', 'Field Events: Long Jump, Shot Put and Javelin',
     dict(room='Main Ground', time=('07:00', '11:00'), details={'disciplines': 'Long jump, Shot put, Javelin',
                                                                 'gender': 'Open'})),
    (17, 'B', 'C', 'debate', 'Elocution Contest: Voices of Change',
     dict(room='Seminar Hall 2', crit='talk', details={'style': 'Elocution', 'language': 'Kannada / English'})),
    (18, 'A', 'T', 'case_competition', 'IdeaThon: Pitch Your Product',
     dict(room='MBA Seminar Hall', fee=100, crit='biz', category='Management', team=(2, 4),
          prizes=('₹10,000', '₹6,000', '₹4,000'), details={'kind': 'Business plan'})),
    (18, 'B', 'S', 'sports_tournament', 'Chess Rapid Open',
     dict(room='Aryabhata Seminar Hall', fee=50, participation='Individual', team=(1, 1),
          details={'sport': 'Chess', 'format': 'League', 'gender': 'Open'})),
    (19, 'A', 'T', 'career_fair', 'Career Fair 2026: Internships and Jobs',
     dict(room='Innovation Centre', category='Management',
          details={'companies': 'IT services, product startups and core engineering firms'})),
    (19, 'B', 'C', 'cultural_competition', 'Threads of Tradition: Fashion Show',
     dict(room='Main Auditorium', fee=300, crit='perf', team=(6, 12), time=('16:00', '20:00'),
          details={'discipline': 'Fashion show', 'performance_size': 'Group'})),
    (20, 'A', 'S', 'sports_tournament', 'Volleyball Championship',
     dict(room='Indoor Sports Complex', team=(6, 10), details={'sport': 'Volleyball', 'format': 'Knockout',
                                                               'gender': 'Men'})),
    (20, 'B', 'C', 'cultural_show', 'Saptha Utsav: Closing Cultural Night',
     dict(room='Main Auditorium', time=('18:00', '21:30'), details={'performers': 'Music, dance and theatre clubs'})),
]

PAST = [
    (-14, 'A', 'T', 'hackathon', 'CodeStorm Mini Hackathon',
     dict(room='Innovation Centre', crit='tech', team=(2, 4), time=('09:00', '18:00'), fee=100,
          prizes=('₹10,000', '₹6,000', '₹4,000'), details={'duration_hours': '8', 'themes': 'Campus problems'})),
    (-12, 'B', 'C', 'cultural_competition', 'Natya Taranga: Solo Dance Competition',
     dict(room='Main Auditorium', crit='perf', participation='Individual',
          details={'discipline': 'Dance', 'performance_size': 'Solo'})),
    (-10, 'A', 'S', 'sports_tournament', 'Inter-Department Kabaddi Cup',
     dict(room='Main Ground', team=(7, 10), time=('07:30', '12:00'),
          details={'sport': 'Kabaddi', 'format': 'Knockout', 'gender': 'Men'})),
    (-9, 'A', 'T', 'workshop', 'Workshop: Git and GitHub for Beginners',
     dict(room='CSE Lab 1', cap=60, details={'trainer': 'Prof. Vinay Kumar'})),
    (-7, 'B', 'T', 'quiz', 'Brainwave: General Quiz',
     dict(room='Seminar Hall 2', crit='quiz', team=(2, 3), details={'quiz_format': 'Buzzer rounds only'})),
    (-5, 'A', 'T', 'seminar', 'Seminar: Generative AI for Engineers',
     dict(room='Aryabhata Seminar Hall', category='Technical',
          details={'speaker': 'Dr. Arun Menon', 'speaker_designation': 'Professor, CSE'})),
    (-3, 'B', 'C', 'debate', 'Debate: Social Media and Democracy',
     dict(room='Seminar Hall 2', crit='talk', details={'style': 'Debate', 'language': 'English'})),
    (-2, 'A', 'S', 'athletics', 'Campus Cross-Country Run',
     dict(room='Main Ground', time=('06:30', '09:00'), details={'disciplines': '5 km cross-country',
                                                                 'gender': 'Open'})),
]

DESCRIPTIONS = {
    'workshop': 'A hands-on session where you build as you learn. Seats are limited to the lab size, so register early.',
    'seminar': 'An open seminar with time for questions at the end. All students and faculty are welcome.',
    'guest_lecture': 'A guest lecture by an industry practitioner, followed by an open discussion.',
    'webinar': 'An online session; the meeting link is shared with everyone who registers.',
    'hackathon': 'Form a team, pick a theme and build a working prototype. Mentors are on hand throughout.',
    'coding_contest': 'Solve algorithmic problems against the clock. Ranked by problems solved, then time taken.',
    'quiz': 'Teams answer rounds on science, technology and general knowledge; the top teams reach the stage final.',
    'paper_presentation': 'Present a technical paper to a jury of faculty. Abstracts are reviewed before the day.',
    'project_expo': 'Final-year teams show their projects to visitors, faculty and industry guests.',
    'case_competition': 'Teams analyse a business problem and pitch their solution to a panel of judges.',
    'debate': 'Speakers argue for and against the motion; judges score content, delivery and rebuttal.',
    'cultural_competition': 'Show your talent on stage. Judges score technique, creativity and stage presence.',
    'cultural_show': 'An evening of performances by the university\'s students. Entry is free for all.',
    'sports_tournament': 'Department teams compete for the championship trophy. Fixtures are shared after registration.',
    'athletics': 'Open to all students; heats in the morning and finals before noon.',
    'esports': 'A campus esports tournament played on university machines under referee supervision.',
    'placement_drive': 'A recruitment drive for final-year students: pre-placement talk, test and interviews.',
    'career_fair': 'Meet employers offering internships and jobs. Bring copies of your resume.',
    'social_drive': 'A community drive organised with our partners. Volunteers and donors are welcome.',
    'club_activity': 'A club session open to members and newcomers alike.',
}

SLOTS = {'A': ('09:30', '12:30'), 'B': ('14:00', '17:00')}


def event_form(day, slot, kind, title, opts, rooms):
    date = TODAY + datetime.timedelta(days=day)
    start, end = opts.get('time') or SLOTS[slot]
    end_date = date + datetime.timedelta(days=opts.get('days', 0))
    deadline = max(date - datetime.timedelta(days=1), TODAY) if day > 0 else date - datetime.timedelta(days=1)
    team = opts.get('team')
    # Left out, the event type's own participation and team size apply
    participation = opts.get('participation') or (('Team' if team[1] > 1 else 'Individual') if team else '')
    form = {
        'event_type': kind, 'title': title, 'description': DESCRIPTIONS[kind],
        'rules': 'Carry your college ID card. Report 30 minutes before the start. The organisers\' decision is final.',
        'date': date.isoformat(), 'end_date': end_date.isoformat(), 'time': start, 'end_time': end,
        'reg_deadline': deadline.isoformat(), 'visibility': 'Public',
        'max_participants': str(opts.get('cap', 0)),
        'reg_fee': str(opts.get('fee', 0)), 'contact_phone': '+91 80 2837 2800',
        'allowed_participants': ['student'],
    }
    if participation:
        form['participation_type'] = participation
    if opts.get('category'):
        form['category'] = opts['category']
    if team:
        form['team_min'], form['team_max'] = str(team[0]), str(team[1])
    if opts.get('mode') == 'online':
        form['event_mode'] = 'online'
        form['online_link'] = opts['online']
    else:
        form['room_id'] = rooms[opts['room']]
        form['venue'] = opts['room']
    for name, value in (opts.get('details') or {}).items():
        form[f'detail_{kind}__{name}'] = value
    if opts.get('placement_company'):
        form['placement_company'] = opts['placement_company']
    if opts.get('crit'):
        form['judging_criteria_json'] = json.dumps([{'name': n, 'max_score': m} for n, m in CRIT[opts['crit']]])
        prizes = opts.get('prizes') or ('Trophy and certificate', 'Medal and certificate', 'Certificate of merit')
        form.update(prize_1=prizes[0], prize_2=prizes[1], prize_3=prizes[2])
    return form


def create_event(client, form):
    data = {k: v for k, v in form.items() if k != 'allowed_participants'}
    resp = client.post('/spoc/create_event', data=dict(data, allowed_participants=form['allowed_participants']))
    m = re.search(r'/spoc/event/([^/]+)/review', resp.headers.get('Location', ''))
    if not m:
        sys.exit(f"Couldn't create '{form['title']}' ({resp.status_code}): "
                 + re.sub(r'<[^>]+>', ' ', resp.get_data(as_text=True))[:600])
    return m.group(1)


# ── Registrations ──────────────────────────────────────────────────────────

def answers_for(event_id, ev, lead):
    """Plausible answers to the event's own questions (the preset's form, or
    the SPOC's), so every registration passes the form's checks."""
    from routes_forms import registration_schema
    out = {}
    for f in registration_schema(event_id, dict(ev, id=event_id)).get('fields', []):
        fid, kind = f.get('id', ''), f.get('type', 'text')
        if kind in ('heading', 'paragraph', 'divider') or fid.startswith('member_') or fid in (
                'full_name', 'email', 'phone', 'usn', 'participant_type'):
            continue
        if fid == 'team_name' or 'team' in (f.get('label') or '').lower() and 'name' in (f.get('label') or '').lower():
            # Individual sports ask which team the athlete represents: their department
            out[fid] = lead.get('department', 'Computer Science & Engineering')
            continue
        if not f.get('required') and random.random() < 0.4:
            continue
        options = [o.get('value', o.get('label')) if isinstance(o, dict) else o for o in (f.get('options') or [])]
        label = (f.get('label') or fid).lower()
        if kind in ('select', 'radio') and options:
            out[fid] = random.choice(options)
        elif kind == 'checkbox_group' and options:
            out[fid] = options[:1]
        elif kind == 'checkbox':
            out[fid] = 'yes'
        elif kind == 'email':
            out[fid] = lead['email']
        elif kind == 'tel':
            out[fid] = lead['phone']
        elif kind == 'url':
            out[fid] = f"https://github.com/{lead['email'].split('@')[0].replace('.', '-')}"
        elif kind == 'number':
            out[fid] = str(f.get('min') or 1)
        elif kind == 'date':
            out[fid] = ev.get('date') or TODAY.isoformat()
        elif kind == 'textarea':
            out[fid] = 'Looking forward to taking part and learning from the session.'
        elif 'department' in label or 'branch' in label:
            out[fid] = lead.get('department', 'Computer Science & Engineering')
        elif 'year' in label or 'semester' in label:
            out[fid] = str(lead.get('year', 2))
        elif 'college' in label or 'institution' in label:
            out[fid] = 'Sapthagiri NPS University'
        else:
            out[fid] = 'Yes'
    return out


def register_live(student_clients, students, event_id, ev, n_slots, fee):
    """Register through the real form, so each registration gets its ticket
    and QR code. A paid event sends the registrant to the payment gateway,
    which a demo can't use, so the fee is set aside while they register and
    each registration is then recorded as paid by UPI."""
    import uuid
    event_key = str(uuid.UUID(event_id))
    if fee:
        db.collection('events').document(event_key).update({'fees': {'regular': 0.0}, 'entry_fee': 0,
                                                             'pricing_type': 'free'})
    lo, hi = (ev.get('limits') or {}).get('team_min', 1), (ev.get('limits') or {}).get('team_max', 1)
    team = ev.get('is_team_event') and hi > 1
    pool = students[:]
    random.shuffle(pool)
    made = 0
    for i in range(n_slots):
        if not pool:
            break
        lead = pool.pop()
        # Teams near the smallest allowed size, so the 60 students make several teams
        size = random.randint(max(lo, 1), min(hi, max(lo, 1) + 1)) if team else 1
        if team and len(pool) < size - 1:
            break
        members = [pool.pop() for _ in range(size - 1) if pool]
        form = {'privacy_consent': 'yes', 'full_name': lead['name'], 'email': lead['email'],
                'phone': lead['phone'], 'usn': lead['usn'], 'participant_type': 'student'}
        form.update(answers_for(event_id, ev, lead))   # a team event's own team name follows
        if team:
            form['team_name'] = random.choice(['Byte', 'Code', 'Phoenix', 'Titan', 'Nova', 'Spark', 'Falcon',
                                               'Vortex', 'Eagle', 'Orbit', 'Pixel', 'Rhythm']) + f' {i + 1}'
            for j, m in enumerate(members, 1):
                form.update({f'member_{j}_name': m['name'], f'member_{j}_email': m['email'],
                             f'member_{j}_usn': m['usn']})
        resp = student_clients[lead['email']].post(f'/forms/submit/{event_id}', data=form)
        where = resp.headers.get('Location', '')
        if f'/forms/register/{event_id}' in where or resp.status_code >= 400:
            with student_clients[lead['email']].session_transaction() as sess:
                flashes = [m for _, m in sess.get('_flashes', [])]
            print(f"   ! not registered for {ev.get('title')}: {flashes[-1:] or resp.status_code}")
            continue
        made += 1
    if fee:
        db.collection('events').document(event_key).update({'fees': {'regular': float(fee)}, 'entry_fee': fee,
                                                             'pricing_type': 'paid'})
        for doc in db.collection('registrations').where('event_id', '==', event_key).stream():
            db.collection('registrations').document(doc.id).update({
                'status': 'confirmed', 'payment_status': 'paid', 'amount_paid': float(fee),
                'payment_mode': 'UPI', 'payment_id': f"pay_demo_{str(doc.id).replace('-', '')[:14]}"})
    return made


def register_past(students, event_id, ev, n_slots, fee, date):
    """Past events can't take new registrations, so these are written as the
    form writes them, with the attendance taken at the gate."""
    lo, hi = (ev.get('limits') or {}).get('team_min', 1), (ev.get('limits') or {}).get('team_max', 1)
    team = ev.get('is_team_event') and hi > 1
    pool = students[:]
    random.shuffle(pool)
    ids = []
    for i in range(n_slots):
        if not pool:
            break
        lead = pool.pop()
        size = random.randint(max(lo, 1), hi) if team else 1
        members = [pool.pop() for _ in range(size - 1) if pool]
        present = random.random() < 0.82
        when = datetime.datetime.combine(date - datetime.timedelta(days=random.randint(2, 12)),
                                         datetime.time(random.choice([10, 11, 13, 16, 19, 20, 21]), random.randint(0, 59)))
        doc = {
            'event_id': event_id, 'lead_name': lead['name'], 'lead_email': lead['email'],
            'lead_phone': lead['phone'], 'usn': lead['usn'], 'participant_type': 'student',
            'team_name': (f"Team {lead['name'].split()[0]}" if team else ''),
            'members': [{'role': 'Member', 'name': m['name'], 'email': m['email'], 'usn': m['usn'],
                         'attendance': 'Present' if present else 'Absent'} for m in members],
            'status': 'confirmed', 'attendance': 'Present' if present else 'Absent',
            'checkin_time': f"{date.isoformat()} 09:{random.randint(5, 55):02d}" if present else None,
            'payment_status': 'paid' if fee else 'Free', 'amount_paid': float(fee) if fee else 0.0,
            'payment_mode': 'UPI' if fee else '', 'registered_at': when.strftime('%Y-%m-%d %H:%M:%S'),
            'current_round': 1, 'is_eliminated': False,
        }
        _, ref = db.collection('registrations').add(doc)
        ids.append((ref.id, doc, lead))
    return ids


def score(regs, ev, judges):
    criteria = ev.get('judging_criteria') or [{'name': 'Overall', 'max_score': 100}]
    for rid, doc, _ in regs:
        if doc['attendance'] != 'Present':
            continue
        skill = random.uniform(0.55, 0.95)
        entries = {}
        for j in judges:
            details = {c['name']: round(c['max_score'] * min(1.0, max(0.3, random.gauss(skill, 0.07))), 1)
                       for c in criteria}
            entries[j['email']] = {'total': round(sum(details.values()), 2), 'details': details,
                                   'judge_name': j['name'], 'judge_email': j['email'], 'round': 1,
                                   'scored_at': datetime.datetime.now().isoformat(timespec='seconds')}
        db.collection('registrations').document(rid).update({'scores': entries})


FEEDBACK = [
    (5, 'Very well organised and the sessions were practical.', ['Well organised', 'Learned a lot']),
    (5, 'Great speakers and good use of time.', ['Great speakers']),
    (4, 'Enjoyed it. The venue was a little crowded.', ['Learned a lot']),
    (4, 'Good event; would like more hands-on time.', ['Well organised']),
    (3, 'Content was good but it started late.', []),
]


# ── Run ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Seed a clean demo of SapthaEvent.')
    parser.add_argument('--summary', help='write the accounts and events created to this JSON file')
    args = parser.parse_args()

    with app.app_context():
        print(f'Emptying {wipe()} tables…')
        # The university's organisation and its central unit, which every event belongs to
        db._ensure_root_units()

        print('People…')
        admin_u = person(ADMIN['email'], ADMIN['name'], 'SuperAdmin', category='All', designation=ADMIN['designation'],
                         department='Office of Student Affairs', phone='+91 80 2837 2800')
        spocs = {k: person(v['email'], v['name'], 'ClubSPOC', category=v['category'], department=v['department'],
                           club=v['club'], phone='+91 80 2837 2800') for k, v in SPOCS.items()}
        coords = {k: person(v['email'], v['name'], 'EventCoordinator', category=SPOCS[k]['category'],
                            department=SPOCS[k]['department']) for k, v in COORDS.items()}
        judges = [person(j['email'], j['name'], 'Judge', category='All', department=j['department']) for j in JUDGES]
        volunteer = person(VOLUNTEER['email'], VOLUNTEER['name'], 'Volunteer', category='All')
        students = make_students()

        admin = login(ADMIN['email'], 'SuperAdmin')
        spoc_clients = {k: login(v['email'], 'ClubSPOC') for k, v in SPOCS.items()}

        print('Venues…')
        rooms = make_venues(admin)

        print('Events…')
        created = []
        for day, slot, owner, kind, title, opts in UPCOMING + PAST:
            client = spoc_clients[owner]
            eid = create_event(client, event_form(day, slot, kind, title, opts, rooms))
            if day > 0:
                client.post(f'/spoc/event/{eid}/publish')
            created.append(dict(id=eid, day=day, slot=slot, owner=owner, kind=kind, title=title, opts=opts))
            # Staff: the SPOC's coordinator; two judges for judged events
            client.post(f'/coordinator/assign_staff/{eid}', data={'name': COORDS[owner]['name'],
                                                                 'email': COORDS[owner]['email'],
                                                                 'role': 'EventCoordinator'})
            if opts.get('crit'):
                for j in random.sample(JUDGES, 2):
                    client.post(f'/coordinator/assign_staff/{eid}', data={'name': j['name'], 'email': j['email'],
                                                                         'role': 'Judge'})

        print('Registrations…')
        student_clients = {s['email']: login(s['email'], 'Student') for s in students}
        for ev in created:
            doc = db.collection('events').document(ev['id']).get().to_dict() or {}
            team = doc.get('is_team_event') and (doc.get('limits') or {}).get('team_max', 1) > 1
            fee = ev['opts'].get('fee', 0)
            if ev['day'] > 0:
                n = random.randint(3, 6) if team else random.randint(10, 26)
                n = max(3 if team else 5, int(n * max(0.5, 1 - ev['day'] / 30)))   # nearer events: more sign-ups
                ev['registrations'] = register_live(student_clients, students, ev['id'], doc, n, fee)
            else:
                date = TODAY + datetime.timedelta(days=ev['day'])
                n = random.randint(5, 8) if team else random.randint(22, 40)
                regs = register_past(students, ev['id'], doc, n, fee, date)
                ev['registrations'] = len(regs)
                staff_judges = [s for s in (doc.get('staff') or []) if s.get('role') == 'Judge']
                if ev['opts'].get('crit') and staff_judges:
                    score(regs, doc, staff_judges)
                ev['past_regs'] = regs

        print('Finished events: results, certificates and feedback…')
        for ev in [e for e in created if e['day'] < 0]:
            client = spoc_clients[ev['owner']]
            if ev['opts'].get('crit'):
                admin.post(f"/coordinator/publish_results/{ev['id']}")
                db.collection('events').document(ev['id']).update({'results_published': True})
            else:
                db.collection('events').document(ev['id']).update({'status': 'completed'})
            client.post(f"/spoc/bulk_certs/{ev['id']}")
            if ev['kind'] in ('workshop', 'seminar', 'hackathon', 'cultural_competition'):
                for rid, doc, lead in ev['past_regs']:
                    if doc['attendance'] == 'Present' and random.random() < 0.8:
                        rating, comment, tags = random.choice(FEEDBACK)
                        student_clients[lead['email']].post(f'/participant/feedback/{rid}',
                                                            data={'rating': str(rating), 'comments': comment,
                                                                  'tags': tags})

        print('Announcements…')
        for subject, message in (
                ('Welcome to SapthaEvent', 'Every university event is now on SapthaEvent: register online and '
                                           'carry your QR ticket. Results and certificates appear here too.'),
                ('HackSaptha 2026 registrations are open', 'Form a team of 2 to 4 and register before the '
                                                           'deadline. Mentors from industry will be on campus.')):
            admin.post('/admin/send_email', data={'audience': 'role_filter', 'role_filter': 'Student',
                                                  'subject': subject, 'message': message, 'channel': 'app'})

        # One spelling for every status (the form writes 'Confirmed', the workflow 'confirmed')
        for doc in db.collection('registrations').stream():
            r = doc.to_dict() or {}
            if r.get('status') and r['status'] != r['status'].lower():
                db.collection('registrations').document(doc.id).update({'status': r['status'].lower()})

        # Nothing queued to send later, and nobody left logged in from the run
        for coll in ('outbox', 'login_attempts', 'flask_sessions'):
            try:
                from sqlalchemy import text
                from db_pg import get_engine
                with get_engine().begin() as conn:
                    conn.execute(text(f'DELETE FROM "{coll}"'))
            except Exception:
                pass

        totals = {'users': sum(1 for _ in db.collection('users').stream()),
                  'events': sum(1 for _ in db.collection('events').stream()),
                  'registrations': sum(1 for _ in db.collection('registrations').stream())}
        print(f"Done: {totals['users']} accounts, {totals['events']} events, "
              f"{totals['registrations']} registrations.")

        if args.summary:
            events_out = []
            for ev in created:
                d = db.collection('events').document(ev['id']).get().to_dict() or {}
                events_out.append({
                    'id': ev['id'], 'title': d.get('title'), 'type': d.get('event_type'),
                    'category': d.get('category'), 'date': d.get('date'), 'end_date': d.get('end_date'),
                    'time': d.get('time'), 'end_time': d.get('end_time'), 'venue': d.get('venue'),
                    'status': d.get('status'), 'fee': (d.get('fees') or {}).get('regular', 0),
                    'team': d.get('is_team_event'), 'team_min': (d.get('limits') or {}).get('team_min'),
                    'team_max': (d.get('limits') or {}).get('team_max'), 'owner': SPOCS[ev['owner']]['name'],
                    'registrations': ev.get('registrations', 0), 'winners': d.get('winners') or [],
                })
            accounts = ([dict(admin_u, password=PASSWORDS['SuperAdmin'])]
                        + [dict(s, password=PASSWORDS['ClubSPOC']) for s in spocs.values()]
                        + [dict(c, password=PASSWORDS['EventCoordinator']) for c in coords.values()]
                        + [dict(j, password=PASSWORDS['Judge']) for j in judges]
                        + [dict(volunteer, password=PASSWORDS['Volunteer'])]
                        + [dict(s, password=PASSWORDS['Student']) for s in students])
            with open(args.summary, 'w') as fh:
                json.dump({'generated': datetime.datetime.now().isoformat(timespec='seconds'),
                           'today': TODAY.isoformat(), 'totals': totals, 'accounts': accounts,
                           'rooms': list(rooms), 'events': events_out}, fh, indent=1, default=str)
            print(f'Summary written to {args.summary}')


if __name__ == '__main__':
    main()
