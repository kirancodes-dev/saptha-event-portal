"""
seed_events.py
==============
Creates 1 ClubSPOC user + 30 seeded events in Firestore.
Run:  python3 seed_events.py
"""

import datetime
import sys
import os
os.environ.setdefault('FIREBASE_KEY_PATH', 'serviceAccountKey.json')

from models import db
from werkzeug.security import generate_password_hash

# ──────────────────────────────────────────────
# SPOC DETAILS
# ──────────────────────────────────────────────
SPOC = {
    'email':    'priya.nair@snpsu.ac.in',
    'name':     'Priya Nair',
    'phone':    '+91 98765 43210',
    'club':     'SNPSU Innovation & Technology Club (ITC)',
    'password': 'SPOC@Priya2026',
    'role':     'ClubSPOC',
    'category': 'Technical',
    'whatsapp_group': 'https://chat.whatsapp.com/snpsu-itc-2026',
}

# ──────────────────────────────────────────────
# BANNER IMAGES — Unsplash CDN (topic-matched)
# ──────────────────────────────────────────────
BANNERS = {
    'hackathon':     'https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=900&h=400&fit=crop',
    'coding':        'https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=900&h=400&fit=crop',
    'robotics':      'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=900&h=400&fit=crop',
    'iot':           'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=900&h=400&fit=crop',
    'ai':            'https://images.unsplash.com/photo-1677442135703-1787eea5ce01?w=900&h=400&fit=crop',
    'webdev':        'https://images.unsplash.com/photo-1627398242454-45a1465c2479?w=900&h=400&fit=crop',
    'datascience':   'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=900&h=400&fit=crop',
    'cybersec':      'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=900&h=400&fit=crop',
    'appdev':        'https://images.unsplash.com/photo-1512941937669-90a1b58e7e9c?w=900&h=400&fit=crop',
    'cloud':         'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=900&h=400&fit=crop',
    'opensource':    'https://images.unsplash.com/photo-1556075798-4825dfaaf498?w=900&h=400&fit=crop',
    'algorithm':     'https://images.unsplash.com/photo-1509228468518-180dd4864904?w=900&h=400&fit=crop',
    'dance':         'https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=900&h=400&fit=crop',
    'music':         'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=900&h=400&fit=crop',
    'art':           'https://images.unsplash.com/photo-1541367777708-7905fe3296c0?w=900&h=400&fit=crop',
    'drama':         'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=900&h=400&fit=crop',
    'photography':   'https://images.unsplash.com/photo-1452587925148-ce544e77e70d?w=900&h=400&fit=crop',
    'film':          'https://images.unsplash.com/photo-1485846234645-a62644f84728?w=900&h=400&fit=crop',
    'singing':       'https://images.unsplash.com/photo-1516280440614-37939bbacd81?w=900&h=400&fit=crop',
    'rangoli':       'https://images.unsplash.com/photo-1604599340287-2042e85a3802?w=900&h=400&fit=crop',
    'cricket':       'https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=900&h=400&fit=crop',
    'badminton':     'https://images.unsplash.com/photo-1613918431703-aa50889e3be8?w=900&h=400&fit=crop',
    'chess':         'https://images.unsplash.com/photo-1529699211952-734e80c4d42b?w=900&h=400&fit=crop',
    'tabletennis':   'https://images.unsplash.com/photo-1534158914592-062992fbe900?w=900&h=400&fit=crop',
    'basketball':    'https://images.unsplash.com/photo-1546519638405-a9d1b37a4620?w=900&h=400&fit=crop',
    'volleyball':    'https://images.unsplash.com/photo-1592656094267-764a45160876?w=900&h=400&fit=crop',
    'startup':       'https://images.unsplash.com/photo-1552664730-d307ca884978?w=900&h=400&fit=crop',
    'marketing':     'https://images.unsplash.com/photo-1533750349088-cd871a92f312?w=900&h=400&fit=crop',
    'finance':       'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=900&h=400&fit=crop',
    'debate':        'https://images.unsplash.com/photo-1475721027785-f74eccf877e2?w=900&h=400&fit=crop',
}


def event(title, category, banner_key, date, time, venue,
          description, rules, part_type,
          team_min=1, team_max=1, max_p=200,
          fee=0, prize1='₹5,000', prize2='₹3,000', prize3='₹1,500',
          years=None, reg_days_before=7):
    if years is None:
        years = [1, 2, 3, 4]
    event_date = datetime.datetime.strptime(date, '%Y-%m-%d')
    deadline   = (event_date - datetime.timedelta(days=reg_days_before)).strftime('%Y-%m-%d')
    return {
        'title':              title,
        'category':           category,
        'description':        description,
        'rules':              rules,
        'banner_url':         BANNERS[banner_key],
        'visibility':         'Public',
        'date':               date,
        'time':               time,
        'reg_deadline':       deadline,
        'venue':              venue,
        'participation_type': part_type,
        'is_team_event':      part_type in ['Team', 'Both'],
        'coordinators':       [],
        'form_schema': {
            'require_lead_whatsapp':   True,
            'require_member_usn':      True,
            'require_member_email':    True,
            'require_member_whatsapp': True,
            'submission_type':         'none',
        },
        'limits': {
            'team_min':        team_min,
            'team_max':        team_max,
            'max_participants': max_p,
            'allowed_years':   years,
        },
        'fees':   {'regular': fee},
        'prizes': {'1st': prize1, '2nd': prize2, '3rd': prize3},
        'spoc_id': SPOC['email'],
        'organizer': {
            'name':        SPOC['name'],
            'email':       SPOC['email'],
            'phone':       SPOC['phone'],
            'group_link':  SPOC['whatsapp_group'],
        },
        'status':           'active',
        'registration_count': 0,
        'results_published':  False,
        'entry_fee':          fee,   # flat alias used by participant dashboard
        'created_at':         datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


EVENTS = [
    # ── TECHNICAL (12) ────────────────────────────────────────
    event(
        'HackathonX 2026',
        'Technical', 'hackathon',
        '2026-05-10', '09:00 AM', 'Innovation Hub, Block A',
        '24-hour hackathon where teams build innovative solutions to real-world problems. '
        'Themes include Smart Cities, HealthTech, EdTech, and FinTech. '
        'Mentors from industry and academia guide teams throughout the event.',
        '1. Teams of 2–5 members.\n2. All code must be written during the event.\n'
        '3. Use of open-source libraries is allowed.\n4. Projects judged on innovation, '
        'completeness, and presentation.\n5. No plagiarism — teams may be disqualified.',
        'Team', 2, 5, 300,
        fee=150, prize1='₹15,000', prize2='₹10,000', prize3='₹5,000',
    ),
    event(
        'Code Sprint Championship',
        'Technical', 'coding',
        '2026-05-22', '10:00 AM', 'CS Lab 201, Block B',
        'Competitive programming contest across three rounds — Screening, Semi-Final, and Grand Finale. '
        'Problems range from easy to expert-level across algorithms, data structures, and math.',
        '1. Individual participation only.\n2. Allowed languages: C, C++, Python, Java.\n'
        '3. No internet access during contest.\n4. External editors/IDEs are not permitted.\n'
        '5. Judges\' decision is final.',
        'Solo', 1, 1, 150,
        fee=50, prize1='₹8,000', prize2='₹5,000', prize3='₹2,500',
    ),
    event(
        'Robo Wars 2026',
        'Technical', 'robotics',
        '2026-06-05', '10:00 AM', 'Mechanical Lab Arena, Block C',
        'Build a remote-controlled combat robot and battle it out in our arena. '
        'Robots will be inspected before battles. Weight classes: Light (up to 5 kg) and Heavy (up to 15 kg).',
        '1. Teams of 3–5.\n2. Robot weight ≤ 15 kg.\n3. No liquid weapons.\n'
        '4. Safety kill switch mandatory.\n5. Damage to arena results in disqualification.',
        'Team', 3, 5, 80,
        fee=300, prize1='₹20,000', prize2='₹12,000', prize3='₹6,000',
    ),
    event(
        'IoT Innovation Challenge',
        'Technical', 'iot',
        '2026-06-20', '09:30 AM', 'Electronics Lab, Block D',
        'Design and prototype an Internet of Things solution that addresses a campus or community problem. '
        'Hardware kits (Arduino/Raspberry Pi) will be provided. Present a working demo to the jury.',
        '1. Teams of 2–4.\n2. Hardware kit provided — additional components allowed at own cost.\n'
        '3. Solution must be functional and demonstrated live.\n4. Open-source code must be shared on GitHub.',
        'Team', 2, 4, 100,
        fee=100, prize1='₹10,000', prize2='₹6,000', prize3='₹3,000',
    ),
    event(
        'AI & ML Showdown',
        'Technical', 'ai',
        '2026-07-04', '09:00 AM', 'Data Science Lab, Block B',
        'Build and present an AI/ML model that solves a given dataset challenge. '
        'Participants will receive the dataset 48 hours before the event. '
        'Judged on accuracy, creativity of approach, and presentation clarity.',
        '1. Solo or pair (max 2).\n2. Python with sklearn/TensorFlow/PyTorch only.\n'
        '3. Pre-trained models allowed if credited.\n4. Notebooks submitted via Google Drive link.',
        'Both', 1, 2, 120,
        fee=75, prize1='₹12,000', prize2='₹7,000', prize3='₹3,500',
    ),
    event(
        'Web Dev Showdown',
        'Technical', 'webdev',
        '2026-07-18', '10:00 AM', 'Computer Lab 101, Block B',
        'Build a full-stack web application in 6 hours on a given theme. '
        'Deploy it live before the deadline. Teams present a 5-minute demo.',
        '1. Teams of 2–3.\n2. Frameworks allowed: React, Vue, Django, Flask, Node.\n'
        '3. No pre-built templates — must be coded from scratch.\n4. App must be live on any free hosting.',
        'Team', 2, 3, 100,
        fee=75, prize1='₹8,000', prize2='₹5,000', prize3='₹2,000',
    ),
    event(
        'Data Science Olympiad',
        'Technical', 'datascience',
        '2026-08-08', '09:30 AM', 'Data Science Lab, Block B',
        'Three-stage competition: Data Wrangling, Visualization Challenge, and Predictive Modelling. '
        'Real-world datasets from industry partners. Top scorers across stages win.',
        '1. Individual only.\n2. Python/R allowed.\n3. Internet allowed for documentation only.\n'
        '4. Submissions via Kaggle-style notebook upload.',
        'Solo', 1, 1, 100,
        fee=50, prize1='₹7,000', prize2='₹4,000', prize3='₹2,000',
    ),
    event(
        'CyberShield CTF',
        'Technical', 'cybersec',
        '2026-08-22', '11:00 AM', 'Networking Lab, Block A',
        'Capture The Flag competition across Web, Forensics, Cryptography, Reverse Engineering, '
        'and Pwn categories. Beginner to advanced difficulty levels. '
        'Prizes for each category winner plus an overall leaderboard.',
        '1. Teams of 1–4.\n2. Attacking shared infrastructure is strictly prohibited.\n'
        '3. Flag sharing between teams leads to disqualification.\n4. Hint system available (penalises score).',
        'Both', 1, 4, 200,
        fee=100, prize1='₹10,000', prize2='₹6,000', prize3='₹3,000',
    ),
    event(
        'App Dev Challenge',
        'Technical', 'appdev',
        '2026-09-05', '10:00 AM', 'Innovation Hub, Block A',
        'Design and develop a mobile application (Android/iOS/PWA) in 8 hours. '
        'Theme announced on the day. Apps judged on UX, functionality, and innovation.',
        '1. Teams of 2–4.\n2. Flutter, React Native, or native Android/iOS allowed.\n'
        '3. App must be installable/demonstrable on a physical device.\n4. Firebase backend recommended.',
        'Team', 2, 4, 80,
        fee=100, prize1='₹9,000', prize2='₹5,500', prize3='₹2,500',
    ),
    event(
        'Cloud Computing Bootcamp & Contest',
        'Technical', 'cloud',
        '2026-09-19', '09:00 AM', 'Server Room Lab, Block A',
        'Morning: 3-hour hands-on workshop on AWS/GCP fundamentals (free for all). '
        'Afternoon: Speed challenge on cloud deployment tasks. '
        'Top 3 fastest correct deployments win. AWS Educate credits provided.',
        '1. Individual only.\n2. Participants must bring laptops.\n'
        '3. Free-tier cloud accounts (provided in advance) must be used.\n'
        '4. Workshop attendance mandatory to participate in contest.',
        'Solo', 1, 1, 150,
        fee=0, prize1='₹5,000 + AWS credits', prize2='₹3,000 + AWS credits', prize3='₹1,500 + AWS credits',
    ),
    event(
        'Open Source Sprint',
        'Technical', 'opensource',
        '2026-10-03', '10:00 AM', 'Computer Lab 202, Block B',
        'Contribute to curated open-source repositories in a 6-hour sprint. '
        'Points awarded for merged pull requests, bug fixes, and documentation. '
        'All skill levels welcome — beginner-friendly issues labelled.',
        '1. Individual only.\n2. Contributions must be merged by event end.\n'
        '3. Only labelled issues count.\n4. AI-generated code without understanding is disqualified.',
        'Solo', 1, 1, 200,
        fee=0, prize1='₹4,000 + certificate', prize2='₹2,500 + certificate', prize3='₹1,000 + certificate',
    ),
    event(
        'Algorithm Arena',
        'Technical', 'algorithm',
        '2026-10-17', '10:00 AM', 'CS Lab 101, Block B',
        'Head-to-head algorithm battles. Two contestants face the same problem with a time limit. '
        'First correct solution advances. Single-elimination tournament format.',
        '1. Individual only.\n2. Languages: C++, Python, or Java.\n'
        '3. 20-minute time limit per round.\n4. Only one attempt to submit per round.',
        'Solo', 1, 1, 64,
        fee=50, prize1='₹6,000', prize2='₹3,500', prize3='₹1,500',
    ),

    # ── CULTURAL (8) ──────────────────────────────────────────
    event(
        'Rhythm Rush — Solo Dance',
        'Cultural', 'dance',
        '2026-05-30', '02:00 PM', 'Main Auditorium',
        'Showcase your dance talent in any style — Classical, Contemporary, Hip-Hop, or Freestyle. '
        '3-minute solo performance. Judged on technique, expression, and stage presence.',
        '1. Solo performance — 3 minutes max.\n2. Music track must be submitted 2 days before.\n'
        '3. Costumes must be decent and college-appropriate.\n4. Props allowed if safe.',
        'Solo', 1, 1, 60,
        fee=50, prize1='₹5,000 + Trophy', prize2='₹3,000 + Trophy', prize3='₹1,500 + Trophy',
    ),
    event(
        'Battle of Bands',
        'Cultural', 'music',
        '2026-06-14', '05:00 PM', 'Open Air Theatre',
        'Inter-college band competition. Perform two songs — one original composition and one cover. '
        '20 minutes per band including setup. Judged on musical quality, originality, and crowd energy.',
        '1. Bands of 3–8 members.\n2. Instruments must be brought by teams (basic PA provided).\n'
        '3. Explicit lyrics not allowed.\n4. College ID mandatory for all members.',
        'Team', 3, 8, 120,
        fee=200, prize1='₹25,000', prize2='₹15,000', prize3='₹8,000',
    ),
    event(
        'Canvas & Colors — Painting',
        'Cultural', 'art',
        '2026-07-11', '10:00 AM', 'Art Studio, Block E',
        'On-spot painting competition. Theme revealed 15 minutes before start. '
        '3-hour session. All mediums welcome — watercolour, acrylic, oil pastel.',
        '1. Individual only.\n2. Canvas (A2) provided.\n3. Bring your own paints and brushes.\n'
        '4. Theme-based interpretation — must relate to announced theme.',
        'Solo', 1, 1, 80,
        fee=50, prize1='₹4,000', prize2='₹2,500', prize3='₹1,000',
    ),
    event(
        'Drama Quest — Theatre Competition',
        'Cultural', 'drama',
        '2026-07-25', '03:00 PM', 'Main Auditorium',
        'Short play competition on socially relevant themes. '
        '10–15 minute performances. Props and costumes can be brought or arranged on campus.',
        '1. Teams of 5–12.\n2. Themes: Environment, Gender Equality, Mental Health, or Technology.\n'
        '3. Scripts must be original.\n4. Performances in English, Hindi, or Kannada.',
        'Team', 5, 12, 150,
        fee=100, prize1='₹12,000', prize2='₹7,000', prize3='₹3,500',
    ),
    event(
        'Click & Capture — Photography',
        'Cultural', 'photography',
        '2026-08-15', '08:00 AM', 'SNPSU Campus (Outdoor)',
        'Campus photography walk followed by a judging session. '
        'Theme: "Everyday Life on Campus." Participants click photos on campus grounds '
        'and submit their best 3 shots by 12 PM.',
        '1. Individual only.\n2. DSLR, mirrorless, or smartphone allowed.\n'
        '3. Heavy post-processing (compositing) not allowed — basic edits only.\n'
        '4. Submit 3 JPEG files via Google Drive link by noon.',
        'Solo', 1, 1, 100,
        fee=0, prize1='₹4,500 + framed print', prize2='₹2,500 + framed print', prize3='₹1,000 + framed print',
    ),
    event(
        'Short Film Fiesta',
        'Cultural', 'film',
        '2026-09-12', '10:00 AM', 'Media Lab & Auditorium, Block F',
        '48-hour short film challenge. Theme given on Friday evening; films screened Sunday. '
        'Films must be original, shot within 48 hours, and 5–10 minutes long.',
        '1. Teams of 3–8 (director, camera, actors, editor).\n'
        '2. All footage must be shot after theme announcement.\n'
        '3. Submit MP4 file (1080p minimum) via Google Drive.\n'
        '4. Subtitles required if dialogue is not in English.',
        'Team', 3, 8, 80,
        fee=150, prize1='₹15,000', prize2='₹9,000', prize3='₹4,500',
    ),
    event(
        'Singing Idol — Vocal Contest',
        'Cultural', 'singing',
        '2026-10-09', '04:00 PM', 'Main Auditorium',
        'Solo vocal competition across three rounds: Screening (recorded), '
        'Semi-Final (live), and Grand Finale (live with live band accompaniment). '
        'Any language, any genre.',
        '1. Solo only.\n2. Karaoke/background track allowed (no live band at preliminary).\n'
        '3. 4-minute time limit per performance.\n4. Own mic not allowed; venue mic mandatory.',
        'Solo', 1, 1, 80,
        fee=50, prize1='₹8,000 + Trophy', prize2='₹5,000 + Trophy', prize3='₹2,000 + Trophy',
    ),
    event(
        'Rangoli Royale',
        'Cultural', 'rangoli',
        '2026-10-31', '09:00 AM', 'College Corridor, Block A',
        'Traditional and contemporary Rangoli competition. Theme: "Festivals of India." '
        '3-hour creation session. Judged on creativity, symmetry, and use of colour.',
        '1. Teams of 2–4.\n2. Colours provided; additional materials at own cost.\n'
        '3. Pre-drawn outlines not allowed.\n4. Area: 5×5 feet per team.',
        'Team', 2, 4, 60,
        fee=50, prize1='₹3,000', prize2='₹2,000', prize3='₹1,000',
    ),

    # ── SPORTS (6) ────────────────────────────────────────────
    event(
        'Cricket Carnival',
        'Sports', 'cricket',
        '2026-06-07', '07:00 AM', 'SNPSU Cricket Ground',
        'Inter-department T10 cricket tournament. Knockout format. '
        'Up to 12 departments can register. Matches played in morning slots.',
        '1. Teams of 11 + 2 substitutes.\n2. T10 format — 10 overs per side.\n'
        '3. Valid college ID mandatory for all players.\n4. Umpires\' decision is final.\n'
        '5. Helmets and pads mandatory for batsmen.',
        'Team', 11, 13, 150,
        fee=500, prize1='₹20,000 + Trophy', prize2='₹12,000 + Trophy', prize3='₹0',
    ),
    event(
        'Badminton Blast',
        'Sports', 'badminton',
        '2026-07-02', '08:00 AM', 'Indoor Sports Hall',
        'Singles and doubles badminton tournament. '
        'Two categories: Men\'s Singles and Mixed Doubles. Knockout rounds.',
        '1. Open to all SNPSU students.\n2. Players must bring own rackets.\n'
        '3. Shuttle provided by organisers.\n4. BWF rules apply.',
        'Both', 1, 2, 100,
        fee=100, prize1='₹4,000 per category', prize2='₹2,000 per category', prize3='₹0',
    ),
    event(
        'Chess Masters Championship',
        'Sports', 'chess',
        '2026-08-01', '10:00 AM', 'Seminar Hall 3, Block D',
        'Swiss-system chess tournament (7 rounds). Time control: 15+5 (rapid). '
        'Top 3 players from each round advance. FIDE rules apply.',
        '1. Individual only.\n2. Electronic devices must be off during games.\n'
        '3. Draws by agreement allowed after move 30 only.\n4. Arbiter\'s decision is final.',
        'Solo', 1, 1, 64,
        fee=50, prize1='₹5,000 + Chess set', prize2='₹3,000', prize3='₹1,500',
    ),
    event(
        'Table Tennis Tussle',
        'Sports', 'tabletennis',
        '2026-08-28', '09:00 AM', 'Indoor Sports Hall',
        'Singles table tennis tournament. Knockout format with round-robin group stage. '
        'Best of 5 sets per match. ITTF rules apply.',
        '1. Individual only.\n2. Own bats allowed (no illegal rubbers).\n'
        '3. SNPSU-branded balls used.\n4. Referee\'s call is final.',
        'Solo', 1, 1, 64,
        fee=50, prize1='₹3,500', prize2='₹2,000', prize3='₹1,000',
    ),
    event(
        'Basketball Bonanza 3×3',
        'Sports', 'basketball',
        '2026-09-26', '08:00 AM', 'Basketball Court, SNPSU',
        '3-on-3 basketball tournament (FIBA 3×3 rules). '
        'Separate brackets for men and women. '
        'Round-robin pool stage followed by knockout semis and finals.',
        '1. Teams of 3 + 1 substitute.\n2. FIBA 3×3 rules apply (10-minute games).\n'
        '3. Basketball shoes mandatory.\n4. No jewellery during play.',
        'Team', 3, 4, 120,
        fee=200, prize1='₹8,000 per bracket', prize2='₹4,500 per bracket', prize3='₹0',
    ),
    event(
        'Volleyball Vibe',
        'Sports', 'volleyball',
        '2026-10-24', '08:30 AM', 'Volleyball Court, SNPSU',
        'Inter-department volleyball tournament. 6-a-side, knockout format. '
        'Up to 10 department teams. Best of 3 sets per match.',
        '1. Teams of 6 + 2 substitutes.\n2. Standard volleyball rules (FIVB).\n'
        '3. Knee pads recommended.\n4. Only registered players allowed on court.',
        'Team', 6, 8, 100,
        fee=300, prize1='₹10,000 + Trophy', prize2='₹6,000', prize3='₹0',
    ),

    # ── MANAGEMENT (4) ────────────────────────────────────────
    event(
        'Startup Pitch Battle',
        'Management', 'startup',
        '2026-05-16', '10:00 AM', 'Seminar Hall 1, Block A',
        'Present your startup idea to a panel of investors and industry mentors. '
        '5 minutes pitch + 5 minutes Q&A. Ideas judged on problem-market fit, '
        'feasibility, scalability, and presentation.',
        '1. Teams of 2–5.\n2. Pitch deck (max 10 slides) submitted 2 days before.\n'
        '3. Working prototype/MVP is a bonus but not mandatory.\n'
        '4. Ideas must be original — no existing company pitches.',
        'Team', 2, 5, 120,
        fee=100, prize1='₹20,000 + Incubation opportunity', prize2='₹10,000', prize3='₹5,000',
    ),
    event(
        'Marketing Maestros',
        'Management', 'marketing',
        '2026-07-30', '10:00 AM', 'Seminar Hall 2, Block A',
        'Teams are given a fictional product and must create a complete marketing campaign: '
        'market research, branding, digital strategy, and budget allocation. '
        'Present campaign in 10 minutes to a jury of marketing professionals.',
        '1. Teams of 3–5.\n2. Product brief revealed 2 hours before presentations.\n'
        '3. PowerPoint/Canva presentation only.\n4. Budget: fictional ₹10 lakh.',
        'Team', 3, 5, 80,
        fee=75, prize1='₹8,000', prize2='₹5,000', prize3='₹2,500',
    ),
    event(
        'Finance Quiz Bowl',
        'Management', 'finance',
        '2026-09-05', '02:00 PM', 'Seminar Hall 3, Block D',
        'Three-round finance and business quiz: Written Round, Rapid Fire, and Audio-Visual. '
        'Topics: Stock markets, Corporate finance, Banking, Global economy, and Case studies.',
        '1. Teams of 2.\n2. Phones not allowed during the quiz.\n'
        '3. Quizmaster\'s decision is final.\n4. Negative marking in written round.',
        'Team', 2, 2, 100,
        fee=50, prize1='₹6,000', prize2='₹3,500', prize3='₹1,500',
    ),
    event(
        'Model UN — Campus Debate',
        'Management', 'debate',
        '2026-10-10', '09:00 AM', 'Seminar Hall 1 & 2, Block A',
        'One-day Model United Nations simulation with 4 committees: '
        'UNSC, UNGA, WHO, and ECOSOC. Delegates represent assigned countries. '
        'Awards: Best Delegate, Outstanding Delegate, Honourable Mention per committee.',
        '1. Individual delegates — register with country/committee preference.\n'
        '2. Position paper submitted 1 week before.\n3. Formal attire mandatory.\n'
        '4. Rules of procedure strictly followed.\n5. Chairing decisions are final.',
        'Solo', 1, 1, 120,
        fee=150, prize1='Best Delegate certificate + ₹2,000', prize2='Outstanding Delegate + ₹1,000', prize3='Honourable Mention + certificate',
    ),
]


def create_spoc():
    ref = db.collection('users').document(SPOC['email'])
    if ref.get().exists:
        print(f"  SPOC already exists: {SPOC['email']} — skipping user creation.")
        return
    ref.set({
        'email':                SPOC['email'],
        'name':                 SPOC['name'],
        'phone':                SPOC['phone'],
        'role':                 SPOC['role'],
        'category':             SPOC['category'],
        'club':                 SPOC['club'],
        'password':             generate_password_hash(SPOC['password']),
        'created_at':           datetime.datetime.now().strftime('%Y-%m-%d'),
        'needs_password_reset': False,
    })
    print(f"  ✅ SPOC user created: {SPOC['email']}")


def seed_events():
    created = 0
    for ev in EVENTS:
        _, ref = db.collection('events').add(ev)
        print(f"  ✅ [{ev['category']:12s}] {ev['title']}  →  {ref.id}")
        created += 1
    return created


if __name__ == '__main__':
    if db is None:
        print("❌ Firestore not connected. Check serviceAccountKey.json.")
        sys.exit(1)

    print("\n══════════════════════════════════════════════")
    print("  SNPSU Event Portal — Seed Script")
    print("══════════════════════════════════════════════\n")

    print("1/2  Creating Club SPOC account …")
    create_spoc()

    print(f"\n2/2  Seeding {len(EVENTS)} events …")
    n = seed_events()

    print(f"\n══════════════════════════════════════════════")
    print(f"  Done! {n} events seeded.")
    print(f"\n  ┌─ SPOC Login Details ──────────────────────")
    print(f"  │  Name     : {SPOC['name']}")
    print(f"  │  Email    : {SPOC['email']}")
    print(f"  │  Password : {SPOC['password']}")
    print(f"  │  Role     : ClubSPOC  (category: Technical)")
    print(f"  │  Club     : {SPOC['club']}")
    print(f"  │  Phone    : {SPOC['phone']}")
    print(f"  └───────────────────────────────────────────")
    print()
