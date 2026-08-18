#!/usr/bin/env python3
"""
seed_100_days_biradar.py — Generates 100 realistic events spanning the next 100 days
(1 event per day from today through 100 days out), assigned to biradark543@gmail.com.

Covers all categories: Technical, Cultural, Sports, Management, Hackathon, Workshop, Webinar.
Covers all participation types: Solo (Individual), Team (Group), Both.
Covers both Free and Paid events with custom form schemas and HD Unsplash banners.
"""

import os
import sys
import datetime
from datetime import date, timedelta
import random
from werkzeug.security import generate_password_hash

os.environ.setdefault('FIREBASE_KEY_PATH', 'serviceAccountKey.json')

from models import db

# Target SPOC user details
SPOC_EMAIL = 'biradark543@gmail.com'
SPOC_NAME  = 'Kiran Biradar'
SPOC_PHONE = '9876543210'
SPOC_CLUB  = 'Saptha Event Portal HQ'

TEMPLATES = {
    'Technical': [
        ('24hr Hackathon Championship', 'hackathon', 'Team', 2, 5, 'Build an innovative AI or Cloud prototype in 24 hours.', '1. Teams of 2-5 members.\n2. Original code required.\n3. Live demo at finale.'),
        ('Code Sprint Algorithmic Battle', 'coding', 'Solo', 1, 1, 'Fast-paced competitive programming contest on data structures.', '1. Solo participation.\n2. Languages allowed: Python, C++, Java.'),
        ('Robotics Wiremesh Combat', 'robotics', 'Team', 3, 5, 'High-octane custom robot combat inside the wiremesh arena.', '1. Robot weight limit: 15kg.\n2. 3-minute rounds.'),
        ('IoT & Smart Campus Showcase', 'iot', 'Team', 2, 4, 'Design functional IoT hardware prototypes solving campus issues.', '1. Working hardware demo required.\n2. Max 4 members.'),
        ('AI & Deep Learning Model Sprint', 'ai', 'Both', 1, 2, 'Build high-accuracy machine learning models on complex datasets.', '1. Submit Jupyter Notebook.\n2. Evaluated on F1 score and latency.'),
        ('Web Dev Rapid Hack', 'webdev', 'Team', 2, 3, 'Design and deploy a full-stack responsive web application in 6 hours.', '1. Live URL deployment required.\n2. Public GitHub repo.'),
        ('Cyber Security Capture The Flag', 'cybersec', 'Both', 1, 4, 'Jeopardy-style security CTF covering web, crypto, and reverse engineering.', '1. No attacks on scoring platform.\n2. Flag sharing is prohibited.'),
        ('Cloud Native Dev Workshop', 'cloud', 'Solo', 1, 1, 'Hands-on workshop on Kubernetes, Docker, and Microservices.', '1. Bring your own laptop.\n2. Docker Desktop installed.'),
    ],
    'Cultural': [
        ('Rhythm Solo Dance Battle', 'dance', 'Solo', 1, 1, 'Showcase your solo dance moves across Bollywood, Hip-Hop, or Classical.', '1. Time limit: 3 mins.\n2. Audio track submission required.'),
        ('Battle of the Bands Clash', 'music', 'Team', 3, 8, 'Electric live performance battle between college bands.', '1. Max 15 minutes stage time.\n2. Original or cover compositions.'),
        ('Fine Arts Canvas Paint-Off', 'art', 'Solo', 1, 1, 'On-spot themed painting and creative art competition.', '1. Canvas provided.\n2. Bring your own paints/brushes.'),
        ('Short Film 48-Hour Fest', 'film', 'Team', 3, 8, 'Script, shoot, and edit a short film within 48 hours.', '1. Max length: 10 mins.\n2. English subtitles required.'),
        ('Vocal Solo Melody Challenge', 'singing', 'Solo', 1, 1, 'Vocal singing competition across Western and Indian Classical genres.', '1. Karaoke backing track allowed.\n2. Max 4 mins.'),
        ('Rangoli Traditional Design Fest', 'rangoli', 'Team', 2, 4, 'Create intricate, colorful rangoli artwork on campus grounds.', '1. 5x5 ft grid space.\n2. Colors provided.'),
        ('Theatre & Street Play Drama', 'drama', 'Team', 5, 12, 'High-impact short plays on social themes and campus life.', '1. Max 15 mins.\n2. Props allowed.'),
    ],
    'Sports': [
        ('T10 Cricket League Knockout', 'cricket', 'Team', 11, 13, 'Thrilling 10-over tennis ball cricket tournament.', '1. Knockout format.\n2. Standard sports kit required.'),
        ('Badminton Open Championship', 'badminton', 'Both', 1, 2, 'Singles and mixed doubles badminton tournament.', '1. Best of 3 sets to 21 points.\n2. Bring own racquets.'),
        ('Grandmaster Rapid Chess Battle', 'chess', 'Solo', 1, 1, '7-round Swiss-system chess tournament with digital clocks.', '1. FIDE rules apply.\n2. Time control: 15min + 5sec increment.'),
        ('Table Tennis Smash Tournament', 'tabletennis', 'Solo', 1, 1, 'Fast-paced table tennis tournament, best of 5 games.', '1. ITTF rules.\n2. Non-marking shoes mandatory.'),
        ('3x3 Street Basketball League', 'basketball', 'Team', 3, 4, 'High-speed half-court 3-on-3 basketball games.', '1. 10-minute game clock.\n2. FIBA 3x3 rules.'),
        ('Volleyball Inter-Department Cup', 'volleyball', 'Team', 6, 8, 'Six-a-side volleyball tournament on outdoor courts.', '1. Pool + Knockouts.\n2. Standard FIVB rules.'),
    ],
    'Management': [
        ('Startup Pitch & MVP Battle', 'startup', 'Team', 2, 5, 'Pitch your venture or product prototype to venture investors.', '1. 10-slide deck limit.\n2. 5-min pitch + 3-min Q&A.'),
        ('Finance & Stock Market Quiz', 'finance', 'Team', 2, 2, 'Interactive business, stocks, and economics quiz bowl.', '1. Teams of 2.\n2. No mobile phones during rounds.'),
        ('Model United Nations (MUN)', 'debate', 'Solo', 1, 1, 'Diplomatic simulation discussing international affairs.', '1. Formal dress code.\n2. Position papers submitted in advance.'),
        ('Marketing Strategy & Campaign Hack', 'marketing', 'Team', 3, 5, 'Create a full product launch digital marketing strategy in 3 hours.', '1. Pitch presentation to judges.\n2. Strategy budget allocation.'),
    ]
}

BANNERS = {
    'hackathon':   'https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=900&h=400&fit=crop',
    'coding':      'https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=900&h=400&fit=crop',
    'robotics':    'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=900&h=400&fit=crop',
    'iot':         'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=900&h=400&fit=crop',
    'ai':          'https://images.unsplash.com/photo-1677442135703-1787eea5ce01?w=900&h=400&fit=crop',
    'webdev':      'https://images.unsplash.com/photo-1627398242454-45a1465c2479?w=900&h=400&fit=crop',
    'cybersec':    'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=900&h=400&fit=crop',
    'cloud':       'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=900&h=400&fit=crop',
    'dance':       'https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=900&h=400&fit=crop',
    'music':       'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=900&h=400&fit=crop',
    'art':         'https://images.unsplash.com/photo-1541367777708-7905fe3296c0?w=900&h=400&fit=crop',
    'drama':       'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=900&h=400&fit=crop',
    'film':        'https://images.unsplash.com/photo-1485846234645-a62644f84728?w=900&h=400&fit=crop',
    'singing':     'https://images.unsplash.com/photo-1516280440614-37939bbacd81?w=900&h=400&fit=crop',
    'rangoli':     'https://images.unsplash.com/photo-1604599340287-2042e85a3802?w=900&h=400&fit=crop',
    'cricket':     'https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=900&h=400&fit=crop',
    'badminton':   'https://images.unsplash.com/photo-1613918431703-aa50889e3be8?w=900&h=400&fit=crop',
    'chess':       'https://images.unsplash.com/photo-1529699211952-734e80c4d42b?w=900&h=400&fit=crop',
    'tabletennis': 'https://images.unsplash.com/photo-1534158914592-062992fbe900?w=900&h=400&fit=crop',
    'basketball':  'https://images.unsplash.com/photo-1546519638405-a9d1b37a4620?w=900&h=400&fit=crop',
    'volleyball':  'https://images.unsplash.com/photo-1592656094267-764a45160876?w=900&h=400&fit=crop',
    'startup':     'https://images.unsplash.com/photo-1552664730-d307ca884978?w=900&h=400&fit=crop',
    'marketing':   'https://images.unsplash.com/photo-1533750349088-cd871a92f312?w=900&h=400&fit=crop',
    'finance':     'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=900&h=400&fit=crop',
    'debate':      'https://images.unsplash.com/photo-1475721027785-f74eccf877e2?w=900&h=400&fit=crop',
}

VENUES = [
    "Main University Auditorium", "CS Lab 101, Block B", "CS Lab 201, Block B",
    "Robotics Arena, Block C", "Electronics Lab, Block D", "Seminar Hall 1, Block A",
    "Seminar Hall 2, Block A", "Innovation Hub, Block A", "Indoor Sports Complex",
    "University Main Grounds", "Open Air Amphitheatre", "Sports Complex Court 1"
]

def ensure_spoc_user():
    """Ensure biradark543@gmail.com account exists with ClubSPOC role."""
    user_ref = db.collection('users').document(SPOC_EMAIL)
    user_data = {
        'email':                SPOC_EMAIL,
        'name':                 SPOC_NAME,
        'phone':                SPOC_PHONE,
        'role':                 'ClubSPOC',
        'category':             'General',
        'club':                 SPOC_CLUB,
        'password':             generate_password_hash('Saptha@2026', method='pbkdf2:sha256'),
        'created_at':           datetime.datetime.now().strftime('%Y-%m-%d'),
        'needs_password_reset': False,
    }
    user_ref.set(user_data)
    print(f"✅ SPOC user ensured: {SPOC_NAME} ({SPOC_EMAIL})")

def build_form_schema(event_id, title, part_type):
    """Build a rich custom form schema for the event."""
    fields = [
        {'id': 'field_name',  'label': 'Full Name',             'type': 'text',     'required': True},
        {'id': 'field_email', 'label': 'University Email',      'type': 'email',    'required': True},
        {'id': 'field_usn',   'label': 'USN / Registration No', 'type': 'text',     'required': True},
        {'id': 'field_phone', 'label': 'WhatsApp Phone Number', 'type': 'text',     'required': True},
        {'id': 'field_year',  'label': 'Year of Study',        'type': 'select',   'required': True,
         'options': ['1st Year', '2nd Year', '3rd Year', '4th Year']},
        {'id': 'field_dept',  'label': 'Department',           'type': 'select',   'required': True,
         'options': ['Computer Science', 'Information Science', 'Electronics & Comm', 'Mechanical', 'Civil', 'AI & ML', 'Data Science', 'Other']}
    ]

    if part_type in ['Team', 'Both']:
        fields.append({'id': 'field_team', 'label': 'Team Name', 'type': 'text', 'required': False})

    return {
        'event_id':   event_id,
        'title':      title,
        'form_type':  'custom',
        'fields':     fields,
        'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

def seed_100_days():
    if db is None:
        print("❌ Database client is not connected.")
        sys.exit(1)

    print("1. Setting up SPOC account biradark543@gmail.com...")
    ensure_spoc_user()

    print("\n2. Generating 100 events (1 event for each of the next 100 days)...")
    today = date.today()
    categories = list(TEMPLATES.keys())

    created_count = 0
    for day_offset in range(100):
        event_date = today + timedelta(days=day_offset)
        date_str = event_date.strftime('%Y-%m-%d')
        deadline_str = (event_date - timedelta(days=2)).strftime('%Y-%m-%d')

        category = categories[day_offset % len(categories)]
        templates = TEMPLATES[category]
        tpl = templates[(day_offset // len(categories)) % len(templates)]

        base_title, banner_key, part_type, team_min, team_max, desc, rules = tpl
        event_id = f"EVT-100D-{day_offset+1:03d}"

        title = f"Day {day_offset+1}: {base_title}"
        image_url = BANNERS.get(banner_key, BANNERS['hackathon'])

        # Fee structure: 70% Free, 30% Paid (₹50, ₹100, ₹200, ₹500)
        fee = 0
        if day_offset % 3 == 0:
            fee = random.choice([50, 100, 200, 500])

        prizes = {
            '1st': f'₹{random.choice([5, 10, 15, 20])},000',
            '2nd': f'₹{random.choice([3, 5, 8])},000',
            '3rd': f'₹{random.choice([1, 2, 3])},000'
        }

        venue = VENUES[day_offset % len(VENUES)]
        hour = random.choice([9, 10, 11, 14, 15, 16])
        time_str = f"{hour:02d}:00 AM" if hour < 12 else f"{hour-12:02d}:00 PM"

        event_doc = {
            'id':                     event_id,
            'title':                  title,
            'category':               category,
            'spoc_email':             SPOC_EMAIL,
            'created_by':             SPOC_EMAIL,
            'spoc_name':              SPOC_NAME,
            'spoc_phone':             SPOC_PHONE,
            'date':                   date_str,
            'time':                   time_str,
            'venue':                  venue,
            'image':                  image_url,
            'image_url':              image_url,
            'description':            desc,
            'rules':                  rules,
            'status':                 'Published',
            'entry_fee':              fee,
            'prizes':                 prizes,
            'registration_count':     random.randint(5, 45),
            'participation_type':     part_type,
            'team_size':              {'min': team_min, 'max': team_max},
            'limits':                 {'max_participants': 100, 'min_team_size': team_min, 'max_team_size': team_max},
            'registration_deadline':  deadline_str,
            'coordinators': [
                {'name': 'Ananya Sen', 'email': 'ananya@student.snpsu.ac.in', 'phone': '9911223344'},
                {'name': 'Rohit Kumar', 'email': 'rohit@student.snpsu.ac.in', 'phone': '9988776655'}
            ],
            'created_at':             datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # Save event document
        db.collection('events').document(event_id).set(event_doc)

        # Save matching form schema
        schema = build_form_schema(event_id, title, part_type)
        db.collection('event_forms').document(event_id).set(schema)

        created_count += 1
        print(f"  [{created_count}/100] Created event for {date_str} (Day {day_offset+1}): {title} [{category} | Fee: ₹{fee}]")

    print(f"\n🎉 SUCCESS: Created {created_count} events for SPOC {SPOC_EMAIL} spanning next 100 days ({today} to {today + timedelta(days=99)})!")

if __name__ == '__main__':
    seed_100_days()
