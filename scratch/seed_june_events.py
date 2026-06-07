import os
import sys
import datetime
from werkzeug.security import generate_password_hash

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set default firebase credentials path if not set
os.environ.setdefault('FIREBASE_KEY_PATH', 'serviceAccountKey.json')

from models import db
from seed_events import build_form_schema

# ── 4 SPOC ACCOUNTS (including Rohan Mehta for Management) ──
SPOCS = {
    'Technical': {
        'email':         'priya.nair@snpsu.ac.in',
        'name':          'Priya Nair',
        'phone':         '+91 98765 43210',
        'club':          'Innovation & Technology Club (ITC)',
        'password':      'SPOC@Priya2026',
        'role':          'ClubSPOC',
        'category':      'Technical',
        'whatsapp_group': 'https://chat.whatsapp.com/snpsu-itc-2026',
    },
    'Cultural': {
        'email':         'arjun.sharma@snpsu.ac.in',
        'name':          'Arjun Sharma',
        'phone':         '+91 91234 56789',
        'club':          'Arts & Culture Society (ACS)',
        'password':      'SPOC@Arjun2026',
        'role':          'ClubSPOC',
        'category':      'Cultural',
        'whatsapp_group': 'https://chat.whatsapp.com/snpsu-acs-2026',
    },
    'Sports': {
        'email':         'kavya.reddy@snpsu.ac.in',
        'name':          'Kavya Reddy',
        'phone':         '+91 87654 32109',
        'club':          'Student Activity Council (SAC)',
        'password':      'SPOC@Kavya2026',
        'role':          'ClubSPOC',
        'category':      'Sports',
        'whatsapp_group': 'https://chat.whatsapp.com/snpsu-sac-2026',
    },
    'Management': {
        'email':         'rohan.mehta@snpsu.ac.in',
        'name':          'Rohan Mehta',
        'phone':         '+91 99999 88888',
        'club':          'Management Association (MA)',
        'password':      'SPOC@Rohan2026',
        'role':          'ClubSPOC',
        'category':      'Management',
        'whatsapp_group': 'https://chat.whatsapp.com/snpsu-ma-2026',
    }
}

# ── Dynamic Event templates ──
TEMPLATES = {
    'Technical': [
        ('Algorithm Hack', 'webdev', '09:00 AM', 'CS Lab 201, Block B', 'Solo', 'Challenge your algorithmic thinking and solve complex structures in a time-bound coding run.', '1. Bring own laptop.\n2. Individual work only.\n3. Python/C++/Java allowed.'),
        ('AI Build Sprint', 'ai', '10:00 AM', 'Data Science Lab, Block B', 'Team', 'Build and deploy an AI model targeting computer vision or natural language processing in 6 hours.', '1. Teams of 2-4.\n2. Use of pre-trained models allowed with attribution.'),
        ('Robotics Design Contest', 'robotics', '11:00 AM', 'Mechanical Arena, Block C', 'Team', 'Design a remote-controlled robot to navigate an obstacle course.', '1. Teams of 3-5.\n2. Bots must fit size constraints (30x30x30 cm).'),
        ('Cyber Capture Flag', 'cybersec', '02:00 PM', 'Networking Lab, Block A', 'Both', 'Solve forensics, web exploitation, and cryptography challenges to capture flags.', '1. Team/Solo entries.\n2. Do not attack server infrastructure.')
    ],
    'Cultural': [
        ('Starlight Dance Off', 'dance', '03:00 PM', 'Main Auditorium', 'Solo', 'Solo dance battle showing classical or contemporary routines in front of a live panel.', '1. Duration: 3 min.\n2. Tracks submitted 1 day prior.'),
        ('Acoustic Jam Night', 'music', '05:30 PM', 'Open Air Theatre', 'Team', 'Live acoustic music showcase featuring cover songs or original compositions.', '1. Bands of 3-8.\n2. Acoustic instruments only.'),
        ('Expressive Drama Showcase', 'drama', '04:00 PM', 'Main Auditorium', 'Team', 'Short plays and theatre acts on socially relevant modern themes.', '1. Teams of 5-10.\n2. Max duration: 15 minutes.'),
        ('Canvas & Expression Art Walk', 'art', '10:30 AM', 'Art Studio, Block E', 'Solo', 'On-spot painting competition with standard medium canvas sheets.', '1. Sheets provided.\n2. Bring own brushes and paints.')
    ],
    'Sports': [
        ('T10 Departmental Smash', 'cricket', '07:30 AM', 'SNPSU Cricket Ground', 'Team', 'Knockout T10 cricket match between departmental teams.', '1. Departmental squads of 11-13.\n2. Helmets and pads mandatory.'),
        ('Badminton Power Cup', 'badminton', '08:30 AM', 'Indoor Sports Hall', 'Both', 'Singles and mixed-doubles fast-paced badminton tournament.', '1. Bring own rackets.\n2. Shuttles provided.'),
        ('Rapid Chess Arena', 'chess', '10:00 AM', 'Seminar Hall 3, Block D', 'Solo', 'Swiss-system rapid chess championship under standard FIDE rules.', '1. Standard rapid time control.\n2. Arbiters decision final.'),
        ('Table Tennis Showdown', 'tabletennis', '09:30 AM', 'Indoor Sports Hall', 'Solo', 'Knockout table tennis tournament with standard ITTF rules.', '1. Best of 5 sets.\n2. Bring own bats.')
    ],
    'Management': [
        ('B-Plan Elevator Pitch', 'startup', '10:00 AM', 'Seminar Hall 1, Block A', 'Team', 'Pitch your business idea to seasoned investors and startup founders.', '1. Pitch deck max 10 slides.\n2. 5 min pitch + 5 min Q&A.'),
        ('Ad-Vantage Marketing Run', 'marketing', '11:30 AM', 'Seminar Hall 2, Block A', 'Team', 'Create and present a marketing strategy for a newly launched product.', '1. Fictional budget limits.\n2. Teams of 3-5.'),
        ('Debate Parliament Championship', 'debate', '02:30 PM', 'Seminar Hall 1, Block A', 'Solo', 'Standard parliamentary style debate competition on current global affairs.', '1. Individual debate slots.\n2. Formal college attire.'),
        ('Finance Asset Quiz', 'finance', '03:30 PM', 'Seminar Hall 3, Block D', 'Team', 'Multi-round quiz covering stock markets, corporate finance, and assets.', '1. Teams of 2.\n2. No phone usage permitted.')
    ]
}

def seed_june_data():
    print("Connecting to Firestore...")
    if db is None:
        print("❌ Database connection failed!")
        return

    # 1. Create/Verify SPOC Users
    print("1. Creating SPOC users...")
    for cat, spoc in SPOCS.items():
        user_ref = db.collection('users').document(spoc['email'])
        if not user_ref.get().exists:
            user_ref.set({
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
            print(f"  ✅ Created SPOC: {spoc['name']} ({spoc['email']})")
        else:
            print(f"  ℹ  SPOC {spoc['email']} already exists.")

    # 2. Seed Daily Events from June 7, 2026 to June 30, 2026
    start_date = datetime.date(2026, 6, 7)
    end_date = datetime.date(2026, 6, 30)
    delta = datetime.timedelta(days=1)

    curr = start_date
    event_count = 0
    form_count = 0

    print(f"2. Seeding daily events from {start_date} to {end_date}...")
    while curr <= end_date:
        date_str = curr.strftime('%Y-%m-%d')
        print(f"  📅 Seeding events for {date_str}...")

        # For each day, create one event in each sector
        for sector, templates in TEMPLATES.items():
            # Choose a template based on the day number to rotate them
            template_idx = curr.day % len(templates)
            title_prefix, banner_key, time_str, venue, part_type, desc, rules = templates[template_idx]

            # Generate distinct title
            day_suffix = curr.strftime('%b %d')
            event_title = f"{title_prefix} ({day_suffix})"

            # Build Event data
            spoc = SPOCS[sector]
            reg_deadline = (curr - datetime.timedelta(days=2)).strftime('%Y-%m-%d')

            event_data = {
                'title':              event_title,
                'category':           sector,
                'description':        desc,
                'rules':              rules,
                'banner_url':         f"https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=900&h=400&fit=crop", # standard fallback
                'visibility':         'Public',
                'date':               date_str,
                'time':               time_str,
                'reg_deadline':       reg_deadline,
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
                    'team_min':         2 if part_type == 'Team' else 1,
                    'team_max':         4 if part_type == 'Team' else 1,
                    'max_participants':  100,
                    'allowed_years':     [1, 2, 3, 4],
                },
                'fees':               {'regular': 0},
                'prizes':             {'1st': '₹5,000', '2nd': '₹3,000', '3rd': '₹1,500'},
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
                'entry_fee':           0,
                'created_at':          datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            # Write event to Firestore
            _, ref = db.collection('events').add(event_data)
            event_id = ref.id
            event_count += 1

            # Build and save form schema
            schema = build_form_schema(
                event_id, event_title, spoc['email'],
                part_type, event_data['limits']['team_min'], event_data['limits']['team_max']
            )
            db.collection('event_forms').document(event_id).set(schema)
            form_count += 1

        curr += delta

    print("══════════════════════════════════════════════════════")
    print(f"  SUCCESS! Seeded {event_count} events and {form_count} event_forms.")
    print("══════════════════════════════════════════════════════")

if __name__ == '__main__':
    seed_june_data()
