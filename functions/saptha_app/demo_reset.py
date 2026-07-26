"""
demo_reset.py
=============
1. WIPES all collections (events, registrations, announcements, teams,
   certificates, notifications, feedback, audit_log, event_forms)
   and all non-SuperAdmin users.
2. SEEDS fresh demo data for every portal EXCEPT admin:
     • 3 Club SPOCs  (Cultural, Sports, Technical)
     • 5 Judges
     • 3 Event Coordinators
     • 20 Students
     • 35 Events  (10 Cultural + 10 Sports + 10 Technical + 5 Management)

SuperAdmin accounts are NEVER touched.

Run:  python demo_reset.py
"""

import sys
import datetime
sys.path.insert(0, '.')

try:
    from dotenv import load_dotenv
except Exception:
    dotenv = None
load_dotenv()

from models import db
from werkzeug.security import generate_password_hash

TODAY     = datetime.date.today()
T         = lambda days: str(TODAY + datetime.timedelta(days=days))
NOW_STR   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
TODAY_STR = str(TODAY)

TOMORROW = T(1)    # July 6
PLUS3    = T(8)    # July 13
PLUS4    = T(15)   # July 20
PLUS7    = T(25)   # July 30
PLUS10   = T(40)   # August 14
PLUS14   = T(55)   # August 29

DL0  = T(-2)       # Reg closed
DL2  = T(5)        # Reg closes July 10
DL3  = T(12)       # Reg closes July 17
DL6  = T(22)       # Reg closes July 27
DL9  = T(37)       # Reg closes August 11
DL13 = T(52)       # Reg closes August 26


# =========================================================
# USERS
# =========================================================
SPOCS = [
    {'email': 'cultural.spoc@snpsu.edu.in', 'name': 'Meera Sharma',
     'password': 'Cultural@2026', 'role': 'ClubSPOC',
     'category': 'Cultural', 'club': 'Cultural Arts Club'},
    {'email': 'sports.spoc@snpsu.edu.in',   'name': 'Arjun Reddy',
     'password': 'Sports@2026',   'role': 'ClubSPOC',
     'category': 'Sports',   'club': 'Sports Association'},
    {'email': 'tech.spoc@snpsu.edu.in',     'name': 'Priya Nair',
     'password': 'Tech@2026',     'role': 'ClubSPOC',
     'category': 'Technical', 'club': 'Technical Developers Club'},
    {'email': 'mgmt.spoc@snpsu.edu.in',     'name': 'Rohan Shetty',
     'password': 'Mgmt@2026',     'role': 'ClubSPOC',
     'category': 'Management', 'club': 'Management & Entrepreneurship Club'},
]

JUDGES = [
    {'email': 'judge1@snpsu.edu.in', 'name': 'Prof. Arun Menon',   'role': 'Judge', 'category': 'Technical',  'password': 'Judge@1111'},
    {'email': 'judge2@snpsu.edu.in', 'name': 'Dr. Kavitha Rao',    'role': 'Judge', 'category': 'Cultural',   'password': 'Judge@2222'},
    {'email': 'judge3@snpsu.edu.in', 'name': 'Prof. Vinod Shetty', 'role': 'Judge', 'category': 'Sports',     'password': 'Judge@3333'},
    {'email': 'judge4@snpsu.edu.in', 'name': 'Dr. Suma Bhat',      'role': 'Judge', 'category': 'Management', 'password': 'Judge@4444'},
    {'email': 'judge5@snpsu.edu.in', 'name': 'Prof. Rajan Pillai', 'role': 'Judge', 'category': 'Technical',  'password': 'Judge@5555'},
]

COORDINATORS = [
    {'email': 'coord1@snpsu.edu.in', 'name': 'Suresh Babu',   'role': 'EventCoordinator', 'category': 'General', 'password': 'Coord@1111'},
    {'email': 'coord2@snpsu.edu.in', 'name': 'Meena Pillai',  'role': 'EventCoordinator', 'category': 'General', 'password': 'Coord@2222'},
    {'email': 'coord3@snpsu.edu.in', 'name': 'Ramesh Shenoy', 'role': 'EventCoordinator', 'category': 'General', 'password': 'Coord@3333'},
]

STUDENT_NAMES = [
    "Aarav Sharma", "Ananya Rao", "Arjun Pillai", "Divya Nair",
    "Karthik Shetty", "Lavanya Iyer", "Meera Reddy", "Nikhil Kumar",
    "Priya Menon", "Rahul Hegde", "Sahana Kamath", "Sneha Bhat",
    "Tejas Naidu", "Vaishnavi Joshi", "Varun Gowda", "Yamini Murthy",
    "Rohit Patil", "Sanjana Kulkarni", "Mihir Das", "Riya Banerjee",
]

STUDENTS = [
    {'email': f'student{i:03d}@snpsu.edu.in', 'name': n,
     'usn': f'1SNPSU22CS{i:03d}', 'phone': f'98765{i:05d}',
     'password': 'Student@1234', 'role': 'Student'}
    for i, n in enumerate(STUDENT_NAMES, start=1)
]


# =========================================================
# EVENT BUILDER
# =========================================================
def img(seed, w=800, h=400):
    return f'https://picsum.photos/seed/{seed}/{w}/{h}'


def make_event(title, category, spoc, date_str, deadline_str,
               time_str, venue, description, rules, prizes,
               reg_fee=0, is_team=False,
               team_min=1, team_max=1, max_p=200,
               banner_seed='event', extra_seed='campus'):
    spoc_email = spoc['email']
    spoc_name  = spoc['name']
    return {
        'title':            title,
        'category':         category,
        'description':      description,
        'rules':            rules,
        'banner_url':       img(banner_seed),
        'media_urls':       [img(banner_seed), img(extra_seed)],
        'visibility':       'Public',
        'date':             date_str,
        'time':             time_str,
        'reg_deadline':     deadline_str,
        'venue':            venue,
        'participation_type': 'Team' if is_team else 'Individual',
        'is_team_event':    is_team,
        'open_hall_mode':   not is_team,
        'coordinators':     [c['email'] for c in COORDINATORS],
        'form_schema': {
            'require_lead_whatsapp':   False,
            'require_member_usn':      is_team,
            'require_member_email':    False,
            'require_member_whatsapp': False,
            'submission_type':         'none',
        },
        'limits': {
            'team_min':        team_min,
            'team_max':        team_max,
            'max_participants': max_p,
            'allowed_years':   [1, 2, 3, 4],
        },
        'fees':   {'regular': reg_fee},
        'prizes': prizes,
        'spoc_id': spoc_email,
        'organizer': {
            'name':       spoc_name,
            'email':      spoc_email,
            'phone':      '9876543210',
            'group_link': '#',
        },
        'staff': (
            [{'name': j['name'], 'email': j['email'], 'role': 'Judge'}
             for j in JUDGES]
            + [{'name': c['name'], 'email': c['email'], 'role': 'EventCoordinator'}
               for c in COORDINATORS]
        ),
        'status':             'active',
        'active_round':       1,
        'registration_count': 0,
        'has_custom_form':    False,
        'results_published':  False,
        'created_at':         NOW_STR,
    }


# =========================================================
# EVENT DEFINITIONS
# =========================================================
def build_events():
    CUL = next(s for s in SPOCS if s['category'] == 'Cultural')
    SPT = next(s for s in SPOCS if s['category'] == 'Sports')
    TEC = next(s for s in SPOCS if s['category'] == 'Technical')
    MGT = next(s for s in SPOCS if s['category'] == 'Management')

    events = []

    # ── CULTURAL (10) ──────────────────────────────────────
    events += [
        make_event('Solo Singing Championship', 'Cultural', CUL,
            TOMORROW, DL0, '10:00', 'Main Auditorium',
            'Showcase your vocal talent in this solo singing contest open to all years. Classical, semi-classical, film, and indie genres all welcome.',
            '1. Performance max 5 min.\n2. Own instrument or karaoke allowed.\n3. No explicit content.\n4. Decision of judges is final.',
            {'1st': '₹5,000 Cash + Trophy', '2nd': '₹3,000 Cash', '3rd': '₹2,000 Cash'},
            banner_seed='singing', extra_seed='music-stage'),

        make_event('Street Play Festival', 'Cultural', CUL,
            TOMORROW, DL0, '11:00', 'Open Air Theatre',
            'High-energy street play (Nukkad Natak) competition addressing social issues. Teams of 8–15 members perform for 10–15 minutes.',
            '1. Team size: 8–15 members.\n2. Duration: 10–15 minutes.\n3. Props allowed, no live fire.\n4. Theme must be socially relevant.',
            {'1st': '₹8,000 + Rolling Trophy', '2nd': '₹5,000', '3rd': '₹3,000'},
            is_team=True, team_min=8, team_max=15, max_p=120,
            banner_seed='street-play', extra_seed='theatre'),

        make_event('Photography Showdown', 'Cultural', CUL,
            TOMORROW, DL0, '09:00', 'Block B Corridor & Campus',
            'Capture the soul of the campus in this 3-hour on-spot photography hunt. Theme announced at the start.',
            '1. Only mobile/DSLR cameras.\n2. No heavy post-processing.\n3. Submit 3 best shots in JPEG.\n4. Plagiarism = disqualification.',
            {'1st': 'Professional Camera Kit', '2nd': '₹3,000', '3rd': '₹1,500'},
            banner_seed='photography', extra_seed='camera-lens'),

        make_event('Group Dance Championship', 'Cultural', CUL,
            PLUS3, DL2, '14:00', 'Main Auditorium',
            'Battle it out on stage with your crew. All styles — classical, folk, hip-hop, fusion — accepted.',
            '1. Team size: 5–20 members.\n2. Performance: 5–10 min.\n3. Music submitted 2 days prior.\n4. No offensive gestures.',
            {'1st': '₹12,000 + Revolving Shield', '2nd': '₹7,000', '3rd': '₹4,000'},
            is_team=True, team_min=5, team_max=20, max_p=200,
            banner_seed='dance-group', extra_seed='dance-stage'),

        make_event('Poetry Slam & Spoken Word', 'Cultural', CUL,
            PLUS3, DL2, '16:00', 'Seminar Hall 2',
            'Raw, unfiltered expression. Write, perform, and move the audience through the power of words.',
            '1. Original compositions only.\n2. Performance: 3–5 min.\n3. No offensive language.\n4. Audience scoring included.',
            {'1st': '₹4,000', '2nd': '₹2,500', '3rd': '₹1,500'},
            banner_seed='poetry', extra_seed='microphone'),

        make_event('Fine Arts Exhibition', 'Cultural', CUL,
            PLUS3, DL2, '10:00', 'Art Block Gallery',
            'Present your artwork — painting, sculpture, digital art, or installations — in an open gallery format.',
            '1. Artwork must be original.\n2. Canvas size max 3×3 ft.\n3. Artist present for Q&A.',
            {'1st': '₹5,000 + Certificate', '2nd': '₹3,000', '3rd': '₹2,000'},
            banner_seed='fine-arts', extra_seed='painting'),

        make_event('Fashion Show Extravaganza', 'Cultural', CUL,
            PLUS4, DL3, '18:00', 'Main Auditorium',
            'The most glamorous event of the year! Walk the ramp with sustainable fashion or traditional attire.',
            '1. Team of 2–6 members.\n2. Theme: Sustainable Chic.\n3. Original outfits only.\n4. 8-minute runway slot.',
            {'1st': '₹15,000 + Crown', '2nd': '₹10,000', '3rd': '₹6,000'},
            reg_fee=300, is_team=True, team_min=2, team_max=6, max_p=80,
            banner_seed='fashion-show', extra_seed='runway'),

        make_event('Classical Dance Recital', 'Cultural', CUL,
            PLUS4, DL3, '11:00', 'Seminar Hall 1',
            'Solo or duet classical dance recital — Bharatanatyam, Kathak, Odissi, Kuchipudi, and more.',
            '1. Solo or duet only.\n2. Duration: 5–8 min.\n3. Costume as per classical form.',
            {'1st': '₹6,000', '2nd': '₹4,000', '3rd': '₹2,000'},
            banner_seed='classical-dance', extra_seed='bharatanatyam'),

        make_event('Open Mic Night', 'Cultural', CUL,
            PLUS4, DL3, '19:00', 'Open Air Theatre',
            'Comedy, storytelling, stand-up, poetry, or music — the mic is yours for 5 minutes.',
            '1. Max 5 minutes per slot.\n2. No offensive/hate content.\n3. First come, first served.',
            {'1st': 'Audience Pick — Goodies!', '2nd': '', '3rd': ''},
            banner_seed='open-mic', extra_seed='stage-lights'),

        make_event('Drama Fest — One-Act Play', 'Cultural', CUL,
            PLUS4, DL3, '15:00', 'Main Auditorium',
            'Write, direct, and perform an original one-act play. Teams of 5–12 compete for the Curtain Call Trophy.',
            '1. Team: 5–12 members.\n2. Duration: 15–25 min.\n3. Script submitted 3 days before.',
            {'1st': '₹10,000 + Trophy', '2nd': '₹6,000', '3rd': '₹3,000'},
            is_team=True, team_min=5, team_max=12, max_p=100,
            banner_seed='drama-theatre', extra_seed='play-stage'),
    ]

    # ── SPORTS (10) ────────────────────────────────────────
    events += [
        make_event('3x3 Basketball Blitz', 'Sports', SPT,
            TOMORROW, DL0, '08:00', 'Sports Complex — Basketball Court',
            'Fast-paced 3-on-3 basketball tournament. Half-court, 10-minute timed games.',
            '1. Teams of 3 + 1 substitute.\n2. FIBA 3x3 rules.\n3. Proper sports shoes mandatory.',
            {'1st': '₹6,000 + Medals', '2nd': '₹4,000', '3rd': '₹2,000'},
            is_team=True, team_min=3, team_max=4, max_p=120,
            banner_seed='basketball', extra_seed='basketball-court'),

        make_event('Badminton Open Championship', 'Sports', SPT,
            TOMORROW, DL0, '09:00', 'Indoor Sports Hall',
            'Singles and doubles badminton knockout. Separate categories for men and women.',
            '1. Own rackets; shuttles provided.\n2. Best of 3 games, 21 points.\n3. Proper sports attire required.',
            {'1st': '₹5,000', '2nd': '₹3,000', '3rd': '₹1,500'},
            banner_seed='badminton', extra_seed='indoor-sports'),

        make_event('Table Tennis Lightning', 'Sports', SPT,
            TOMORROW, DL0, '10:00', 'Indoor Sports Hall — TT Zone',
            'Singles table tennis speed tournament with 5-minute match slots.',
            '1. ITTF rules.\n2. Own paddle allowed; balls provided.\n3. 11-point games, best of 5.',
            {'1st': '₹3,000', '2nd': '₹2,000', '3rd': '₹1,000'},
            banner_seed='table-tennis', extra_seed='ping-pong'),

        make_event('Cricket T10 Smash', 'Sports', SPT,
            PLUS3, DL2, '07:30', 'College Ground',
            'T10 format cricket tournament. Teams of 11 + 4 substitutes. Full day knockout.',
            '1. T10 rules — 10 overs per side.\n2. Tennis ball; team provides own bat.\n3. Player ID mandatory.',
            {'1st': '₹20,000 + Trophy', '2nd': '₹12,000', '3rd': '₹6,000'},
            reg_fee=200, is_team=True, team_min=11, team_max=15, max_p=200,
            banner_seed='cricket', extra_seed='cricket-ground'),

        make_event('Volleyball Tournament', 'Sports', SPT,
            PLUS3, DL2, '09:00', 'Volleyball Courts',
            '6-a-side volleyball league with pool stage and knockouts. Men and women divisions.',
            '1. Team of 6 + 2 substitutes.\n2. 25-point rally scoring.\n3. Best of 3 sets.',
            {'1st': '₹8,000', '2nd': '₹5,000', '3rd': '₹2,500'},
            is_team=True, team_min=6, team_max=8, max_p=150,
            banner_seed='volleyball', extra_seed='volleyball-team'),

        make_event('Chess Masters Cup', 'Sports', SPT,
            PLUS3, DL2, '11:00', 'Seminar Hall 3',
            'Swiss-system chess tournament over 7 rounds. Clock: 15+10.',
            '1. FIDE rules.\n2. Phones off during game.\n3. Touch piece = move piece.',
            {'1st': '₹4,000', '2nd': '₹2,500', '3rd': '₹1,500'},
            banner_seed='chess', extra_seed='chess-board'),

        make_event('Football 5-A-Side Cup', 'Sports', SPT,
            PLUS4, DL3, '07:00', 'Football Ground',
            '5-a-side football knockout. 15-minute halves. Fast, technical, exciting.',
            '1. Team of 5 + 2 subs.\n2. No sliding tackles.\n3. Futsal-style rules.',
            {'1st': '₹10,000', '2nd': '₹6,000', '3rd': '₹3,000'},
            is_team=True, team_min=5, team_max=7, max_p=140,
            banner_seed='football', extra_seed='soccer-field'),

        make_event('Athletics Track & Field', 'Sports', SPT,
            PLUS4, DL3, '06:30', 'Athletics Track',
            '100 m, 200 m, 400 m, 4×100 m relay, long jump, shot put, and high jump.',
            '1. Proper track shoes or bare feet only.\n2. Two false starts = disqualification.',
            {'1st': 'Gold Medal + ₹2,000', '2nd': 'Silver + ₹1,500', '3rd': 'Bronze + ₹1,000'},
            banner_seed='athletics-track', extra_seed='running'),

        make_event('Kabaddi League', 'Sports', SPT,
            PLUS7, DL6, '09:00', 'Kabaddi Ground',
            'Traditional Indian Kabaddi with standard mat rules. 40-minute matches.',
            '1. Standard Kabaddi Federation rules.\n2. Team: 7 on mat + 5 off.\n3. Raider must chant "kabaddi".',
            {'1st': '₹7,000', '2nd': '₹4,000', '3rd': '₹2,000'},
            is_team=True, team_min=7, team_max=12, max_p=120,
            banner_seed='kabaddi', extra_seed='sports-team'),

        make_event('Swimming Gala', 'Sports', SPT,
            PLUS7, DL6, '08:00', 'SNPSU Swimming Pool',
            'Freestyle, backstroke, breaststroke, and 4×50 m medley relay.',
            '1. FINA rules.\n2. Swimwear and cap mandatory.\n3. No dive starts in backstroke.',
            {'1st': '₹3,000 per event', '2nd': '₹2,000', '3rd': '₹1,000'},
            banner_seed='swimming', extra_seed='pool'),
    ]

    # ── TECHNICAL (10) ─────────────────────────────────────
    events += [
        make_event('Hackathon 2026 — Build the Future', 'Technical', TEC,
            TOMORROW, DL0, '08:00', 'CS Block — Labs 1–5',
            '24-hour hackathon. Build real solutions in AI, healthcare, sustainability, or smart cities.',
            '1. Teams of 3–5.\n2. Code written during hackathon.\n3. GitHub repo pushed by deadline.\n4. 5-min demo + Q&A.',
            {'1st': '₹30,000 + AWS Credits', '2nd': '₹15,000', '3rd': '₹8,000'},
            reg_fee=500, is_team=True, team_min=3, team_max=5, max_p=200,
            banner_seed='hackathon', extra_seed='coding-laptops'),

        make_event('Code Sprint — 2 Hour Challenge', 'Technical', TEC,
            TOMORROW, DL0, '14:00', 'CS Lab — Room 202',
            'Competitive programming: 6 algorithmic problems across easy, medium, and hard tiers.',
            '1. Individual only.\n2. No internet access.\n3. Penalty +5 min per wrong submission.',
            {'1st': '₹5,000', '2nd': '₹3,000', '3rd': '₹2,000'},
            banner_seed='competitive-programming', extra_seed='algorithm'),

        make_event('Cybersecurity CTF', 'Technical', TEC,
            TOMORROW, DL0, '10:00', 'Networking Lab + Online',
            '30+ CTF challenges in web exploitation, cryptography, reverse engineering, forensics.',
            '1. Teams of 2–3.\n2. Only attack designated challenge servers.\n3. Flag sharing = ban.',
            {'1st': '₹8,000 + CTF Merch', '2nd': '₹5,000', '3rd': '₹2,500'},
            is_team=True, team_min=2, team_max=3, max_p=150,
            banner_seed='cybersecurity', extra_seed='hacking-code'),

        make_event('AI Model Challenge', 'Technical', TEC,
            PLUS3, DL2, '10:00', 'Data Science Lab',
            'Build the best ML/DL model for a given dataset announced on event day. Kaggle-style leaderboard.',
            '1. Teams of 1–3.\n2. Dataset revealed at 10:00 AM; submission closes at 4:00 PM.\n3. Accuracy + interpretability judged.',
            {'1st': '₹10,000', '2nd': '₹6,000', '3rd': '₹3,000'},
            is_team=True, team_min=1, team_max=3, max_p=90,
            banner_seed='machine-learning', extra_seed='neural-network'),

        make_event('Robotics Combat Arena', 'Technical', TEC,
            PLUS3, DL2, '09:00', 'Mechanical Engineering Workshop',
            'Design, build, and battle your autonomous or RC robot in a sumo-style arena.',
            '1. Bot weight ≤ 3 kg.\n2. No open flame or liquid.\n3. 3-minute match.\n4. Bring spare parts.',
            {'1st': '₹12,000 + Champion Belt', '2nd': '₹7,000', '3rd': '₹4,000'},
            is_team=True, team_min=2, team_max=5, max_p=80,
            banner_seed='robotics', extra_seed='robot-arena'),

        make_event('Web Dev Showdown', 'Technical', TEC,
            PLUS3, DL2, '11:00', 'CS Lab — Room 301',
            'Design and build a functional web app in 4 hours on a surprise problem statement.',
            '1. Teams of 1–2.\n2. Any framework/language.\n3. Deploy to Vercel/Netlify.\n4. Copied templates = disqualification.',
            {'1st': '₹6,000', '2nd': '₹4,000', '3rd': '₹2,000'},
            is_team=True, team_min=1, team_max=2, max_p=80,
            banner_seed='web-development', extra_seed='ui-design'),

        make_event('Data Science Olympiad', 'Technical', TEC,
            PLUS7, DL6, '10:00', 'Data Science Lab',
            'Multi-round data science: EDA, feature engineering, visualisation, and storytelling with real-world data.',
            '1. Individual.\n2. Tools: Python / R / Tableau.\n3. 3-hour analysis window.\n4. 5-minute pitch.',
            {'1st': '₹8,000', '2nd': '₹5,000', '3rd': '₹2,500'},
            banner_seed='data-science', extra_seed='data-visualization'),

        make_event('IoT Innovation Challenge', 'Technical', TEC,
            PLUS7, DL6, '09:00', 'Electronics Lab',
            'Build a working IoT prototype using Arduino / Raspberry Pi / ESP32 solving a real problem.',
            '1. Teams of 2–4.\n2. Hardware kits on loan.\n3. 6-hour build window.\n4. Working prototype required.',
            {'1st': '₹10,000 + Hardware Kit', '2nd': '₹6,000', '3rd': '₹3,000'},
            is_team=True, team_min=2, team_max=4, max_p=80,
            banner_seed='iot-electronics', extra_seed='arduino'),

        make_event('Mobile App Sprint', 'Technical', TEC,
            PLUS10, DL9, '10:00', 'CS Lab — Room 105',
            'Design and ship a mobile app (Android / Flutter / React Native) in a 5-hour sprint.',
            '1. Teams of 2–3.\n2. Core logic written during sprint.\n3. APK / TestFlight submitted.',
            {'1st': '₹7,000', '2nd': '₹4,500', '3rd': '₹2,500'},
            is_team=True, team_min=2, team_max=3, max_p=90,
            banner_seed='mobile-app', extra_seed='smartphone-code'),

        make_event('Open Source Contribution Sprint', 'Technical', TEC,
            PLUS10, DL9, '11:00', 'CS Block — Open Lab',
            'Find a good-first-issue on a real open source repo and get it merged.',
            '1. Individual.\n2. Choose from pre-approved GitHub repos.\n3. Submit merged PR URL by 5:00 PM.',
            {'1st': '₹5,000 + FOSS T-shirt', '2nd': '₹3,000', '3rd': '₹1,500'},
            banner_seed='open-source', extra_seed='github-code'),
    ]

    # ── MANAGEMENT (5) ─────────────────────────────────────
    events += [
        make_event('B-Plan Pitch Fest', 'Management', MGT,
            PLUS4, DL3, '10:00', 'Conference Hall',
            'Present your business plan to a panel of industry mentors. Seed funding advice included.',
            '1. Teams of 2–4.\n2. Pitch: 8 min + 5 min Q&A.\n3. Deck submitted 1 day before.\n4. No NDAs honoured.',
            {'1st': '₹15,000 + Mentorship Session', '2nd': '₹8,000', '3rd': '₹4,000'},
            is_team=True, team_min=2, team_max=4, max_p=80,
            banner_seed='business-plan', extra_seed='startup'),

        make_event('Case Study Crunch', 'Management', MGT,
            PLUS4, DL3, '14:00', 'Seminar Hall C',
            'McKinsey-style case study competition. Teams receive a real business problem and have 2 hours to analyse and present.',
            '1. Teams of 3.\n2. Case study revealed at 2:00 PM.\n3. 10-min presentation + 5 min Q&A.\n4. Calculators allowed.',
            {'1st': '₹10,000', '2nd': '₹6,000', '3rd': '₹3,000'},
            is_team=True, team_min=3, team_max=3, max_p=60,
            banner_seed='case-study', extra_seed='boardroom'),

        make_event('Marketing Mania', 'Management', MGT,
            PLUS7, DL6, '11:00', 'Seminar Hall B',
            'Design a go-to-market strategy for a mystery product announced on the day.',
            '1. Individual or pairs.\n2. 3 hours to build campaign.\n3. Present to judges in 7 minutes.\n4. Budget constraints apply.',
            {'1st': '₹6,000', '2nd': '₹4,000', '3rd': '₹2,000'},
            banner_seed='marketing', extra_seed='advertising'),

        make_event('HR Simulation & Negotiation', 'Management', MGT,
            PLUS10, DL9, '10:00', 'Conference Room 2',
            'Role-play HR scenarios — performance reviews, conflict resolution, salary negotiations.',
            '1. Individual.\n2. Scenarios assigned randomly.\n3. Assessed on empathy, structure, and outcome.\n4. 15-min session per participant.',
            {'1st': '₹5,000', '2nd': '₹3,000', '3rd': '₹1,500'},
            banner_seed='hr-management', extra_seed='office'),

        make_event('Supply Chain Simulation', 'Management', MGT,
            PLUS14, DL13, '10:00', 'Business Lab',
            'Beer Game-style supply chain simulation. Teams manage inventory, demand, and supplier relations.',
            '1. Teams of 4.\n2. 6 rounds of simulation.\n3. Lowest total cost wins.\n4. No communication between supply chain tiers.',
            {'1st': '₹8,000', '2nd': '₹5,000', '3rd': '₹2,500'},
            is_team=True, team_min=4, team_max=4, max_p=80,
            banner_seed='supply-chain', extra_seed='logistics'),
    ]

    return events


# =========================================================
# WIPE
# =========================================================
WIPE_COLLECTIONS = [
    'events', 'registrations', 'announcements', 'event_forms',
    'teams', 'certificates', 'notifications', 'feedback', 'audit_log',
]


def wipe():
    print('\n[WIPE] Clearing collections...')

    for col in WIPE_COLLECTIONS:
        count = 0
        for doc in db.collection(col).stream():
            db.collection(col).document(doc.id).delete()
            count += 1
        print(f'  deleted {count:>4}  docs  from  {col}')

    # Users: keep SuperAdmin accounts
    kept = deleted = 0
    for doc in db.collection('users').stream():
        role = doc.to_dict().get('role', '')
        if role in ('SuperAdmin', 'Super Admin'):
            kept += 1
            print(f'  kept SuperAdmin: {doc.id}')
        else:
            db.collection('users').document(doc.id).delete()
            deleted += 1
    print(f'  deleted {deleted:>4}  users  (kept {kept} SuperAdmin accounts)')


# =========================================================
# SEED
# =========================================================
def seed_registrations(db, event_id, ev):
    import random
    import time
    
    is_team = ev.get('is_team_event', False)
    limits = ev.get('limits', {})
    team_min = limits.get('team_min', 1)
    team_max = limits.get('team_max', 1)
    fee = ev.get('fees', {}).get('regular', 0)
    event_title = ev['title']
    event_date_str = ev['date']
    
    # Select a random subset of our 20 students to participate (at least team_min, up to team_max * 2)
    min_reg_size = team_min if is_team else 1
    max_reg_size = max(min_reg_size, min(team_max * 3, 20))
    num_students_to_register = random.randint(min_reg_size, max_reg_size)
    
    shuffled_students = list(STUDENTS)
    random.shuffle(shuffled_students)
    event_students = shuffled_students[:num_students_to_register]
    
    registrations = []
    
    if not is_team:
        # Solo event
        for student in event_students:
            registrations.append({
                'lead_name': student['name'],
                'lead_email': student['email'],
                'lead_usn': student['usn'],
                'lead_phone': student['phone'],
                'team_name': 'Individual',
                'members': [],
                'member_count': 1
            })
    else:
        # Team event
        idx = 0
        team_idx = 1
        while idx < len(event_students):
            remaining = len(event_students) - idx
            if remaining < team_min:
                # If remaining students are too few to form a new team, add them to the last team
                if registrations:
                    for m in event_students[idx:]:
                        registrations[-1]['members'].append({
                            'role': 'Member',
                            'name': m['name'],
                            'email': m['email'],
                            'phone': m['phone'],
                            'usn': m['usn']
                        })
                    registrations[-1]['member_count'] = len(registrations[-1]['members'])
                break
            
            team_size = random.randint(team_min, min(team_max, remaining))
            # If the left-over students cannot form another team, consume them all in this team
            if 0 < remaining - team_size < team_min:
                team_size = remaining
                
            team_members = event_students[idx : idx + team_size]
            idx += team_size
            
            lead = team_members[0]
            extra_members = []
            for m in team_members[1:]:
                extra_members.append({
                    'role': 'Member',
                    'name': m['name'],
                    'email': m['email'],
                    'phone': m['phone'],
                    'usn': m['usn']
                })
            
            registrations.append({
                'lead_name': lead['name'],
                'lead_email': lead['email'],
                'lead_usn': lead['usn'],
                'lead_phone': lead['phone'],
                'team_name': f'Team {team_idx} - {event_title[:12]}',
                'members': [{
                    'role': 'Lead',
                    'name': lead['name'],
                    'email': lead['email'],
                    'phone': lead['phone'],
                    'usn': lead['usn']
                }] + extra_members,
                'member_count': len(team_members)
            })
            team_idx += 1
            
    count = 0
    now = datetime.datetime.now()
    
    # Determine if event is in the past / currently happening
    event_date = datetime.datetime.strptime(event_date_str, '%Y-%m-%d').date()
    is_past_or_current = event_date <= TODAY + datetime.timedelta(days=3)
    
    reg_docs = []
    
    for r in registrations:
        reg_id = f"REG-{event_id[:5].upper()}-{random.randint(1000, 9999)}-{int(time.time()*1000)%1000}"
        time.sleep(0.001)
        
        payment_status = 'Paid' if fee > 0 else 'Free'
        amount_paid = fee if fee > 0 else 0
        
        if is_past_or_current:
            attendance = 'Present' if random.random() < 0.85 else 'Absent'
        else:
            attendance = 'Pending'
            
        reg_doc = {
            'reg_id':          reg_id,
            'event_id':        event_id,
            'event_title':     event_title,
            'lead_name':       r['lead_name'],
            'lead_email':      r['lead_email'],
            'lead_usn':        r['lead_usn'],
            'lead_phone':      r['lead_phone'],
            'team_name':       r['team_name'],
            'members':         r['members'],
            'member_count':    r['member_count'],
            'status':          'Confirmed',
            'payment_status':  payment_status,
            'amount_paid':     amount_paid,
            'registered_at':   (now - datetime.timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%d %H:%M:%S"),
            'attendance':      attendance,
            'checkin_time':    '09:30:00' if attendance == 'Present' else '',
            'is_eliminated':   False,
            'current_round':   1,
            'scores':          {},
            'final_score':     None,
            'final_rank':      None
        }
        
        # Add mock scores for present teams in completed/current events
        if attendance == 'Present' and is_past_or_current:
            num_judges = random.randint(2, 3)
            selected_judges = random.sample(JUDGES, num_judges)
            criteria = ['Innovation', 'Technical Complexity', 'Impact', 'Presentation']
            
            scores_map = {}
            for j in selected_judges:
                score_details = {}
                total_score = 0
                for c in criteria:
                    val = random.randint(65, 98)
                    score_details[c] = val
                    total_score += val
                avg_score = round(total_score / len(criteria), 1)
                scores_map[j['email']] = {
                    'details': score_details,
                    'total': avg_score,
                    'raw_total': total_score,
                    'judge_name': j['name'],
                    'submitted_at': now.strftime("%Y-%m-%d %H:%M:%S")
                }
            reg_doc['scores'] = scores_map
            
            if scores_map:
                reg_doc['final_score'] = round(sum(s['total'] for s in scores_map.values()) / len(scores_map), 1)
        
        db.collection('registrations').document(reg_id).set(reg_doc)
        reg_docs.append(reg_doc)
        count += 1
        
    db.collection('events').document(event_id).update({
        'registration_count': count
    })
    
    # Rank and publish results for key past events
    if is_past_or_current and len(reg_docs) > 1 and event_title in ('Solo Singing Championship', 'Code Sprint — 2 Hour Challenge'):
        present_regs = [r for r in reg_docs if r['attendance'] == 'Present' and r.get('final_score') is not None]
        present_regs.sort(key=lambda x: x['final_score'], reverse=True)
        for rank, r in enumerate(present_regs, start=1):
            db.collection('registrations').document(r['reg_id']).update({
                'final_rank': rank
            })
        db.collection('events').document(event_id).update({
            'results_published': True
        })
        print(f"    [RESULTS PUBLISHED] ranked {len(present_regs)} teams for {event_title}")

def seed():
    print('\n[SEED] Creating users...')

    all_users = SPOCS + JUDGES + COORDINATORS

    for u in all_users:
        db.collection('users').document(u['email']).set({
            'email':    u['email'],
            'name':     u['name'],
            'password': generate_password_hash(u['password'], method='pbkdf2:sha256'),
            'role':     u['role'],
            'category': u.get('category', 'General'),
            'club':     u.get('club', ''),
            'phone':    u.get('phone', ''),
            'is_active': True,
            'created_at': NOW_STR,
        })
        print(f'  {u["role"]:<20} {u["email"]:<40} pw: {u["password"]}')

    for s in STUDENTS:
        db.collection('users').document(s['email']).set({
            'email':    s['email'],
            'name':     s['name'],
            'password': generate_password_hash(s['password'], method='pbkdf2:sha256'),
            'role':     'Student',
            'category': 'General',
            'usn':      s['usn'],
            'phone':    s['phone'],
            'is_active': True,
            'created_at': NOW_STR,
        })
    print(f'  {"Student":<20} student001–{len(STUDENTS):03d}@snpsu.edu.in        pw: Student@1234')

    print('\n[SEED] Creating events and registrations...')
    events = build_events()
    for ev in events:
        _, ref = db.collection('events').add(ev)
        print(f'  [{ev["category"]:<10}] {ev["title"][:45]:<45} date={ev["date"]}  fee=₹{ev["fees"]["regular"]}')
        seed_registrations(db, ref.id, ev)

    return events


# =========================================================
# SUMMARY
# =========================================================
def print_summary(events):
    line = '─' * 64
    print(f'\n{"═"*64}')
    print('  DEMO RESET COMPLETE — Login Credentials')
    print(f'{"═"*64}')

    print('\n  CLUB SPOCs')
    print(line)
    for s in SPOCS:
        print(f'  {s["category"]:<12} {s["email"]:<38} {s["password"]}')

    print('\n  JUDGES')
    print(line)
    for j in JUDGES:
        print(f'  {j["name"]:<24} {j["email"]:<38} {j["password"]}')

    print('\n  COORDINATORS')
    print(line)
    for c in COORDINATORS:
        print(f'  {c["name"]:<24} {c["email"]:<38} {c["password"]}')

    print('\n  STUDENTS  (all share password: Student@1234)')
    print(line)
    print(f'  student001@snpsu.edu.in  …  student{len(STUDENTS):03d}@snpsu.edu.in')

    print(f'\n  EVENTS CREATED: {len(events)}')
    print(line)
    cats = {}
    for ev in events:
        cats[ev['category']] = cats.get(ev['category'], 0) + 1
    for cat, cnt in sorted(cats.items()):
        print(f'  {cat:<14} {cnt} events')

    print(f'{"═"*64}\n')


# =========================================================
# MAIN
# =========================================================
if __name__ == '__main__':
    if not db:
        print('ERROR: Firebase not initialised. Check serviceAccountKey.json or FIREBASE_KEY_PATH.')
        sys.exit(1)

    print('SapthaEvent — Demo Reset')
    print('This will WIPE all data (except SuperAdmin) and re-seed.')
    
    if len(sys.argv) > 1 and sys.argv[1] == '--yes':
        confirm = 'YES'
    else:
        confirm = input('Type YES to continue: ').strip()
        
    if confirm != 'YES':
        print('Aborted.')
        sys.exit(0)

    wipe()
    events = seed()
    print_summary(events)
