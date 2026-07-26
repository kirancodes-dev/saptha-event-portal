"""
seed_100_events.py
Wipes existing events and registrations, and generates 100 realistic, unique events
spread across the next 30 days. Generates matching custom form schemas.
"""

import os
import sys
import datetime
from datetime import date, timedelta
import random
from werkzeug.security import generate_password_hash

os.environ.setdefault('FIREBASE_KEY_PATH', 'serviceAccountKey.json')

from models import db
from seed_events import SPOCS, build_form_schema

# Category-specific event templates to construct varied, unique events
TEMPLATES = {
    'Technical': [
        ('Hackathon', 'hackathon', 'Team', 2, 5, 'Build a complete prototype in 24 hours on a surprise theme.', '1. Teams of 2-5 members.\n2. Original code only.'),
        ('Code Sprint', 'coding', 'Solo', 1, 1, 'Fast-paced algorithmic programming contest.', '1. Individual participation.\n2. No external libraries/help.'),
        ('Robowars Combat', 'robotics', 'Team', 3, 5, 'Custom robot combat in the special wire-mesh arena.', '1. Match duration: 3 mins.\n2. Safety rules apply.'),
        ('IoT Showcase', 'iot', 'Team', 2, 4, 'Design smart devices solving local/campus problems.', '1. Live demo required.\n2. Hardware must be functional.'),
        ('AI Model Sprint', 'ai', 'Both', 1, 2, 'Build a predictive AI model for a complex dataset.', '1. Submit Jupyter Notebook.\n2. Models are graded on accuracy.'),
        ('Web Dev Hack', 'webdev', 'Team', 2, 3, 'Create and deploy a responsive web app from scratch in 6 hours.', '1. Deploy live on Vercel/Netlify.\n2. Code must be in GitHub.'),
        ('Data Science Olympiad', 'datascience', 'Solo', 1, 1, 'Advanced data analysis, wrangling and visualization battle.', '1. Individual entry.\n2. Use Python or R.'),
        ('Cyber CTF Challenge', 'cybersec', 'Both', 1, 4, 'Jeopardy-style capture the flag security event.', '1. No DDoS attacks on infrastructure.\n2. Flag sharing is banned.'),
    ],
    'Cultural': [
        ('Rhythm Solo Dance', 'dance', 'Solo', 1, 1, 'Expressive dance competition across classical and Western styles.', '1. Max 3 minutes.\n2. Submission of audio required.'),
        ('Battle of Bands', 'music', 'Team', 3, 8, 'A clash of college bands performing original and cover tracks.', '1. Own instruments.\n2. Time limit: 15 mins.'),
        ('Fine Arts Paint off', 'art', 'Solo', 1, 1, 'Theme-based canvas painting on-spot competition.', '1. Bring own brushes/paints.\n2. Canvas provided.'),
        ('One-Act Drama Fest', 'drama', 'Team', 5, 12, 'Powerful short theatre plays on social themes.', '1. Original scripts only.\n2. Max 15 minutes.'),
        ('Campus Photography Hunt', 'photography', 'Solo', 1, 1, 'Capture the essence of the campus in a photography walk.', '1. Standard edits only.\n2. Submit 3 JPEG photos.'),
        ('Short Film Screening', 'film', 'Team', 3, 8, 'Write, direct, shoot, and edit a short film in 48 hours.', '1. Max length: 10 mins.\n2. Subtitles required.'),
        ('Vocal Solo Singing', 'singing', 'Solo', 1, 1, 'Showcase your vocal talent across Indian and Western music.', '1. Karaoke tracks allowed.\n2. Max 4 minutes.'),
        ('Rangoli Art Competition', 'rangoli', 'Team', 2, 4, 'Create stunning designs using traditional rangoli colors.', '1. No pre-drawn outlines.\n2. Size: 5x5 ft area.'),
    ],
    'Sports': [
        ('T10 Cricket League', 'cricket', 'Team', 11, 13, 'Exciting 10-over cricket knockout tournament.', '1. Tennis ball match.\n2. Proper gear mandatory.'),
        ('Badminton Smash Cup', 'badminton', 'Both', 1, 2, 'Knockout badminton matches in singles and mixed doubles.', '1. Standard BWF rules.\n2. Bring own rackets.'),
        ('Chess Masters Arena', 'chess', 'Solo', 1, 1, 'Swiss-system rapid chess tournament (7 rounds).', '1. FIDE rules apply.\n2. Strict time control: 15+5.'),
        ('Table Tennis Showdown', 'tabletennis', 'Solo', 1, 1, 'Lightning-fast table tennis matches, best of 5 sets.', '1. Own paddles allowed.\n2. Standard ITTF rules.'),
        ('3x3 Basketball Blitz', 'basketball', 'Team', 3, 4, 'Fast half-court basketball tournament.', '1. Team of 3+1 sub.\n2. FIBA 3x3 rules.'),
        ('Volleyball Division Cup', 'volleyball', 'Team', 6, 8, 'Six-a-side volleyball tournament.', '1. Pool + Knockouts.\n2. FIVB rules.'),
    ],
    'Management': [
        ('Startup Pitch Battle', 'startup', 'Team', 2, 5, 'Pitch your venture/MVP ideas to a panel of startup mentors.', '1. Slide deck max 10 slides.\n2. MVP demo preferred.'),
        ('Finance Quiz Bowl', 'finance', 'Team', 2, 2, 'Exciting finance, business and economy quiz.', '1. Team of 2.\n2. No electronic devices.'),
        ('Model UN Assembly', 'debate', 'Solo', 1, 1, 'Diplomatic simulation representing international issues.', '1. Position papers required.\n2. Dress formally.'),
        ('Marketing Maestro Hack', 'marketing', 'Team', 3, 5, 'Create a full launch marketing campaign in 3 hours.', '1. Slide deck presentation.\n2. Fictional budget allocation.'),
    ]
}

BANNERS = {
    'hackathon':   'https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=900&h=400&fit=crop',
    'coding':      'https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=900&h=400&fit=crop',
    'robotics':    'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=900&h=400&fit=crop',
    'iot':         'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=900&h=400&fit=crop',
    'ai':          'https://images.unsplash.com/photo-1677442135703-1787eea5ce01?w=900&h=400&fit=crop',
    'webdev':      'https://images.unsplash.com/photo-1627398242454-45a1465c2479?w=900&h=400&fit=crop',
    'datascience': 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=900&h=400&fit=crop',
    'cybersec':    'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=900&h=400&fit=crop',
    'appdev':      'https://images.unsplash.com/photo-1512941937669-90a1b58e7e9c?w=900&h=400&fit=crop',
    'cloud':       'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=900&h=400&fit=crop',
    'opensource':  'https://images.unsplash.com/photo-1556075798-4825dfaaf498?w=900&h=400&fit=crop',
    'algorithm':   'https://images.unsplash.com/photo-1509228468518-180dd4864904?w=900&h=400&fit=crop',
    'dance':       'https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=900&h=400&fit=crop',
    'music':       'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=900&h=400&fit=crop',
    'art':         'https://images.unsplash.com/photo-1541367777708-7905fe3296c0?w=900&h=400&fit=crop',
    'drama':       'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=900&h=400&fit=crop',
    'photography': 'https://images.unsplash.com/photo-1452587925148-ce544e77e70d?w=900&h=400&fit=crop',
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
    "Main Auditorium", "CS Lab 101, Block B", "CS Lab 201, Block B", 
    "Mechanical Lab Arena, Block C", "Electronics Lab, Block D", 
    "Seminar Hall 1, Block A", "Seminar Hall 2, Block A", "Seminar Hall 3, Block D", 
    "Innovation Hub, Block A", "Indoor Sports Hall", "College Grounds", 
    "Open Air Theatre", "Sports Complex Court 1", "Sports Complex Court 2"
]

COORDINATORS_POOL = [
    {"name": "Ananya Sen", "email": "ananya.sen@student.snpsu.ac.in", "phone": "9911223344"},
    {"name": "Rohit Kumar", "email": "rohit.k@student.snpsu.ac.in", "phone": "9988776655"},
    {"name": "Vikram Seth", "email": "vikram.s@student.snpsu.ac.in", "phone": "9944556677"},
    {"name": "Pooja Hegde", "email": "pooja.h@student.snpsu.ac.in", "phone": "9922334455"},
]

def create_spocs_local():
    created = 0
    for key, spoc in SPOCS.items():
        ref = db.collection('users').document(spoc['email'])
        if ref.get().exists:
            print(f"  ⚠  SPOC already exists: {spoc['email']} — skipping.")
            continue
        ref.set({
            'email':                spoc['email'],
            'name':                 spoc['name'],
            'phone':                spoc['phone'],
            'role':                 spoc['role'],
            'category':             spoc['category'],
            'club':                 spoc['club'],
            'password':             generate_password_hash(spoc['password'], method='pbkdf2:sha256'),
            'created_at':           datetime.datetime.now().strftime('%Y-%m-%d'),
            'needs_password_reset': False,
        })
        print(f"  ✅ SPOC created: {spoc['name']} ({spoc['email']})")
        created += 1
    return created

def main():
    if db is None:
        print("❌ Firestore not connected.")
        sys.exit(1)

    print("1. Creating SPOC Accounts...")
    create_spocs_local()

    print("\n2. Generating 100 events distributed over next 30 days...")
    
    categories = list(TEMPLATES.keys())
    today = date.today()
    
    # Track statistics
    counts = {'Technical': 0, 'Cultural': 0, 'Sports': 0, 'Management': 0}
    
    events_to_create = []
    
    for i in range(1, 101):
        # Evenly spread over 30 days: day offset goes from 1 to 30
        day_offset = ((i - 1) % 30) + 1
        event_date = today + timedelta(days=day_offset)
        date_str = event_date.strftime('%Y-%m-%d')
        
        # Deadlines are set 3 days before the event
        deadline_date = event_date - timedelta(days=3)
        deadline_str = deadline_date.strftime('%Y-%m-%d')
        
        # Cycle through categories
        category = categories[(i - 1) % len(categories)]
        counts[category] += 1
        
        # Pick template
        templates = TEMPLATES[category]
        tpl = templates[(counts[category] - 1) % len(templates)]
        base_title, banner_key, part_type, team_min, team_max, desc, rules = tpl
        
        # Make the title unique
        title = f"{base_title} - Division {counts[category]}"
        
        # SPOC assignments
        if category == 'Technical':
            spoc_key = 'itc'
        elif category == 'Cultural':
            spoc_key = 'acs'
        elif category == 'Sports':
            spoc_key = 'sac'
        else:
            spoc_key = 'acs' if i % 2 == 0 else 'sac'
            
        spoc = SPOCS[spoc_key]
        
        # Determine registration fee (80% free, 20% paid)
        fee = 0
        if i % 5 == 0:
            fee = random.choice([50, 100, 150, 200])
            
        # Determine prizes
        prizes = {
            '1st': f'₹{random.choice([5, 8, 10, 15])},000',
            '2nd': f'₹{random.choice([3, 4, 5])},000',
            '3rd': f'₹{random.choice([1, 2])},000'
        }
        
        # Venue
        venue = VENUES[(i - 1) % len(VENUES)]
        
        # Hour/Time selection
        hour = random.choice([9, 10, 11, 14, 15, 16])
        time_str = f"{hour:02d}:00 AM" if hour < 12 else f"{hour-12:02d}:00 PM"
        
        # Coordinators (randomly assign 1-2 student coordinators)
        coors = random.sample(COORDINATORS_POOL, k=random.choice([1, 2]))
        
        event_dict = {
            'title':              title,
            'category':           category,
            'description':        desc,
            'rules':              rules,
            'banner_url':         BANNERS.get(banner_key, BANNERS['coding']),
            'visibility':         'Public',
            'date':               date_str,
            'time':               time_str,
            'reg_deadline':       deadline_str,
            'venue':              venue,
            'participation_type': part_type,
            'is_team_event':      part_type in ['Team', 'Both'],
            'coordinators':       coors,
            'form_schema': {
                'require_lead_whatsapp':   True,
                'require_member_usn':      True,
                'require_member_email':    True,
                'require_member_whatsapp': True,
                'submission_type':         'none',
            },
            'limits': {
                'team_min':         team_min,
                'team_max':         team_max,
                'max_participants':  random.choice([60, 100, 120, 200]),
                'allowed_years':     [1, 2, 3, 4],
            },
            'fees':               {'regular': fee},
            'prizes':             prizes,
            'spoc_id':            spoc['email'],
            'organizer': {
                'name':       spoc['name'],
                'email':      spoc['email'],
                'phone':      spoc['phone'],
                'group_link': spoc['whatsapp_group'],
            },
            'status':             'active',
            'registration_count':  0,
            'results_published':   False,
            'has_custom_form':     True,
            'entry_fee':           fee,
            'created_at':          datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            # Temp fields to build custom schema
            '_part_type':          part_type,
            '_team_min':           team_min,
            '_team_max':           team_max,
            '_spoc_email':         spoc['email']
        }
        events_to_create.append(event_dict)

    # Insert events and registration forms
    print(f"Inserting {len(events_to_create)} events into database...")
    for idx, ev in enumerate(events_to_create, 1):
        # Extract temp schema fields
        part_type = ev.pop('_part_type')
        team_min = ev.pop('_team_min')
        team_max = ev.pop('_team_max')
        spoc_email = ev.pop('_spoc_email')
        
        _, ref = db.collection('events').add(ev)
        event_id = ref.id
        
        # Build custom schema and save
        schema = build_form_schema(event_id, ev['title'], spoc_email, part_type, team_min, team_max)
        db.collection('event_forms').document(event_id).set(schema)
        
        if idx % 10 == 0:
            print(f"  Inserted {idx}/100 events...")

    print("\n✅ Successfully loaded 100 events spread across next 30 days.")
    print("Category breakdown:")
    for cat, count in counts.items():
        print(f"  {cat}: {count} events")

if __name__ == '__main__':
    main()
