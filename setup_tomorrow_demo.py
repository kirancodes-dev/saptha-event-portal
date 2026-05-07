"""
setup_tomorrow_demo.py
======================
Does TWO things:

  1. CLEAN USERS  — deletes every user EXCEPT SuperAdmin accounts
                    and biradark543@gmail.com.
                    Events are NOT touched.

  2. CREATE EVENTS — adds 2 Technical events for tomorrow owned by
                     biradark543@gmail.com so they appear on your SPOC
                     dashboard immediately:
       • "Code Innovation Challenge 2026"  — FREE entry (individual)
       • "Tech Hackathon Sprint 2026"      — ₹150 entry (team)

     Staff (judges & coordinators) are left EMPTY — assign them yourself
     via the SPOC dashboard after logging in.

Run:  python setup_tomorrow_demo.py
"""

import sys
import datetime
import os
sys.path.insert(0, '.')

import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    key_path = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')
    if not os.path.exists(key_path):
        print("ERROR: serviceAccountKey.json not found.")
        sys.exit(1)
    firebase_admin.initialize_app(credentials.Certificate(key_path))

db = firestore.client()

# ── Constants ─────────────────────────────────────────────────────────────────
SPOC_EMAIL = 'biradark543@gmail.com'
SPOC_NAME  = 'Kiran Biradar'
TOMORROW   = str(datetime.date.today() + datetime.timedelta(days=1))
NOW_STR    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

KEEP_ROLES  = {'SuperAdmin', 'Super Admin'}
KEEP_EMAILS = {SPOC_EMAIL}

# ── Events ────────────────────────────────────────────────────────────────────
FREE_EVENT = {
    'title':       'Code Innovation Challenge 2026',
    'category':    'Technical',
    'description': (
        'A fast-paced individual coding event where participants solve real-world '
        'software problems using any programming language of their choice. '
        'Problems range from algorithmic puzzles to mini-product features. '
        'Open to all years — bring your laptop and your best ideas!'
    ),
    'rules': (
        '1. Individual participation only — no teams allowed.\n'
        '2. Internet access is NOT permitted during the challenge.\n'
        '3. Participants must bring their own laptop with any IDE pre-installed.\n'
        '4. Three problem statements will be revealed at 12:00 PM sharp.\n'
        '5. Submission deadline is 2:30 PM — late submissions will not be evaluated.\n'
        '6. Code must be original; plagiarism results in immediate disqualification.\n'
        '7. Judging criteria: Code Quality (25) · Correctness (25) · Efficiency (25) · Presentation (25).\n'
        '8. Decision of judges is final and binding.'
    ),
    'banner_url':  'https://picsum.photos/seed/code-innovation/800/400',
    'media_urls':  [
        'https://picsum.photos/seed/code-innovation/800/400',
        'https://picsum.photos/seed/coding-laptops/800/400',
        'https://picsum.photos/seed/algorithm/800/400',
    ],
    'visibility':         'Public',
    'date':               TOMORROW,
    'time':               '12:00',
    'reg_deadline':       TOMORROW,
    'venue':              'CS Block — Computer Lab 1 & 2',
    'participation_type': 'Individual',
    'is_team_event':      False,
    'open_hall_mode':     True,
    'coordinators':       [],
    'staff':              [],
    'form_schema': {
        'require_lead_whatsapp':   False,
        'require_member_usn':      False,
        'require_member_email':    False,
        'require_member_whatsapp': False,
        'submission_type':         'none',
    },
    'judging_criteria': ['Code Quality', 'Correctness', 'Efficiency', 'Presentation'],
    'limits': {
        'team_min':         1,
        'team_max':         1,
        'max_participants': 80,
        'allowed_years':    [1, 2, 3, 4],
    },
    'fees':   {'regular': 0},
    'prizes': {
        '1st': '₹5,000 Cash + Trophy + Certificate of Excellence',
        '2nd': '₹3,000 Cash + Certificate',
        '3rd': '₹1,500 Cash + Certificate',
    },
    'spoc_id':  SPOC_EMAIL,
    'organizer': {
        'name':       SPOC_NAME,
        'email':      SPOC_EMAIL,
        'phone':      '9000000001',
        'group_link': '#',
    },
    'status':             'active',
    'active_round':       1,
    'registration_count': 0,
    'has_custom_form':    False,
    'results_published':  False,
    'created_at':         NOW_STR,
}

PAID_EVENT = {
    'title':       'Tech Hackathon Sprint 2026',
    'category':    'Technical',
    'description': (
        'A high-energy 3-hour team hackathon where participants design and build a '
        'working prototype for a problem statement announced on the day. '
        'Teams will pitch their solution to a panel of expert judges at the end. '
        'Domains: Smart Campus · HealthTech · FinTech · Sustainability.'
    ),
    'rules': (
        '1. Teams of 2–4 members; solo entries are not accepted.\n'
        '2. Problem statement is revealed at 12:00 PM — development window closes at 2:45 PM.\n'
        '3. Each team gets a 5-minute pitch + 2-minute Q&A with judges at 3:00 PM.\n'
        '4. Any programming language, framework, or platform is allowed.\n'
        '5. AI tools (Copilot, ChatGPT) are permitted but must be disclosed.\n'
        "6. The prototype must run live on the team's own hardware or cloud.\n"
        '7. Judging criteria: Innovation (30) · Feasibility (25) · Technical Depth (25) · Pitch (20).\n'
        '8. Registration fee ₹150 per team — paid at the venue before 11:45 AM.\n'
        '9. Decisions of the judging panel are final.'
    ),
    'banner_url':  'https://picsum.photos/seed/hackathon-sprint/800/400',
    'media_urls':  [
        'https://picsum.photos/seed/hackathon-sprint/800/400',
        'https://picsum.photos/seed/startup/800/400',
        'https://picsum.photos/seed/neural-network/800/400',
    ],
    'visibility':         'Public',
    'date':               TOMORROW,
    'time':               '12:00',
    'reg_deadline':       TOMORROW,
    'venue':              'CS Block — Smart Classroom & Lab 3',
    'participation_type': 'Team',
    'is_team_event':      True,
    'open_hall_mode':     False,
    'coordinators':       [],
    'staff':              [],
    'form_schema': {
        'require_lead_whatsapp':   False,
        'require_member_usn':      True,
        'require_member_email':    True,
        'require_member_whatsapp': False,
        'submission_type':         'none',
    },
    'judging_criteria': ['Innovation', 'Feasibility', 'Technical Depth', 'Pitch'],
    'limits': {
        'team_min':         2,
        'team_max':         4,
        'max_participants': 120,
        'allowed_years':    [1, 2, 3, 4],
    },
    'fees':   {'regular': 150},
    'prizes': {
        '1st': '₹12,000 Cash + Champion Trophy + Certificates for all members',
        '2nd': '₹7,000 Cash + Certificates for all members',
        '3rd': '₹3,000 Cash + Certificates for all members',
    },
    'spoc_id':  SPOC_EMAIL,
    'organizer': {
        'name':       SPOC_NAME,
        'email':      SPOC_EMAIL,
        'phone':      '9000000001',
        'group_link': '#',
    },
    'status':             'active',
    'active_round':       1,
    'registration_count': 0,
    'has_custom_form':    False,
    'results_published':  False,
    'created_at':         NOW_STR,
}


# ── Step 1: Clean users ────────────────────────────────────────────────────────
def clean_users():
    print('\n[1/2] Cleaning users...')
    kept = deleted = 0
    for doc in db.collection('users').stream():
        d     = doc.to_dict()
        role  = d.get('role', '')
        email = d.get('email', doc.id)
        if role in KEEP_ROLES or email in KEEP_EMAILS:
            kept += 1
            print(f'  KEEP  {role:<20} {email}')
        else:
            doc.reference.delete()
            deleted += 1
    print(f'  → Deleted {deleted} user(s), kept {kept}.')


# ── Step 2: Create events ──────────────────────────────────────────────────────
def create_events():
    print('\n[2/2] Creating events...')
    ids = []
    for ev in [FREE_EVENT, PAID_EVENT]:
        _, ref = db.collection('events').add(ev)
        ids.append(ref.id)
        fee = 'FREE' if ev['fees']['regular'] == 0 else f'₹{ev["fees"]["regular"]}'
        print(f'  [{fee:<6}] {ev["title"]}  →  ID: {ref.id}')
    return ids


# ── Summary ────────────────────────────────────────────────────────────────────
def print_summary(event_ids):
    free_id, paid_id = event_ids
    W = 68
    print(f'\n{"═"*W}')
    print(f'  DONE — {TOMORROW}')
    print(f'{"═"*W}')

    print('\n  LOGIN AS SPOC')
    print(f'  {"─"*60}')
    print(f'  {SPOC_EMAIL}  →  /spoc/dashboard')
    print('  Both events will appear there. Assign judges & coordinators')
    print('  from the dashboard using "Add Judge" / "Assign Coordinator".')

    print('\n  EVENTS')
    print(f'  {"─"*60}')
    print('  [FREE]  Code Innovation Challenge 2026  (Individual)')
    print(f'          ID      : {free_id}')
    print(f'          Results : /spoc/results/{free_id}')
    print()
    print('  [PAID]  Tech Hackathon Sprint 2026  ₹150  (Team 2–4)')
    print(f'          ID      : {paid_id}')
    print(f'          Results : /spoc/results/{paid_id}')
    print(f'{"═"*W}\n')


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print('SapthaEvent — Tomorrow Demo Setup')
    print(f'  Keeps : SuperAdmin accounts + {SPOC_EMAIL}')
    print('  Keeps : ALL existing events (untouched)')
    print(f'  Adds  : 2 Technical events for {TOMORROW} under {SPOC_EMAIL}')
    confirm = input('\nType YES to continue: ').strip()
    if confirm != 'YES':
        print('Aborted.')
        sys.exit(0)

    clean_users()
    event_ids = create_events()
    print_summary(event_ids)
