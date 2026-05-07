"""
seed_live_demo.py
=================
Seeds ONE demo event for tomorrow's live presentation.

Timeline:
  09:00–10:00  Students register on-spot  (Coordinator → /coordinator/on_spot)
  10:00–11:00  SPOC verifies setup        (SPOC → /spoc/dashboard)
  12:00        Event starts               ← the event date/time
  12:00–12:30  Coordinator scans QR codes (Coordinator → /coordinator/scanner)
  12:30–14:00  Judges score participants  (Judge → /judge/dashboard)
  14:00–14:30  SPOC publishes results     (SPOC → /spoc/event/<id>/results)
  14:30–15:00  Certificates auto-generated & sent

What this script creates:
  • 1 SPOC   (demo.spoc@snpsu.edu.in   / Demo@Spoc123)
  • 2 Judges (demo.judge1/2@snpsu.edu.in / Demo@Judge1 / Demo@Judge2)
  • 2 Coordinators (demo.coord1/2@snpsu.edu.in / Demo@Coord1 / Demo@Coord2)
  • 1 Event  "Project Showcase 2026"  tomorrow 12:00 PM, venue = CS Block Lab 1
  • 0 Registrations — students register LIVE at 9–10 AM tomorrow

Run:  python seed_live_demo.py
"""

import sys
import datetime
import os
sys.path.insert(0, '.')

from werkzeug.security import generate_password_hash

# ── Firebase init (reuse models.py pattern) ───────────────────────────────────
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    key_path = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')
    if not os.path.exists(key_path):
        print("ERROR: serviceAccountKey.json not found. Set FIREBASE_KEY_PATH or place it in cwd.")
        sys.exit(1)
    firebase_admin.initialize_app(credentials.Certificate(key_path))

db = firestore.client()

# ── Dates ─────────────────────────────────────────────────────────────────────
TODAY    = datetime.date.today()
TOMORROW = str(TODAY + datetime.timedelta(days=1))   # "2026-05-07"
NOW_STR  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ── Demo users ────────────────────────────────────────────────────────────────
DEMO_SPOC = {
    'email':    'demo.spoc@snpsu.edu.in',
    'name':     'Demo SPOC',
    'password': 'Demo@Spoc123',
    'role':     'ClubSPOC',
    'category': 'Technical',
    'club':     'Technical Developers Club',
}

DEMO_JUDGES = [
    {'email': 'demo.judge1@snpsu.edu.in', 'name': 'Demo Judge 1',
     'password': 'Demo@Judge1', 'role': 'Judge', 'category': 'Technical'},
    {'email': 'demo.judge2@snpsu.edu.in', 'name': 'Demo Judge 2',
     'password': 'Demo@Judge2', 'role': 'Judge', 'category': 'Technical'},
]

DEMO_COORDINATORS = [
    {'email': 'demo.coord1@snpsu.edu.in', 'name': 'Demo Coordinator 1',
     'password': 'Demo@Coord1', 'role': 'EventCoordinator', 'category': 'General'},
    {'email': 'demo.coord2@snpsu.edu.in', 'name': 'Demo Coordinator 2',
     'password': 'Demo@Coord2', 'role': 'EventCoordinator', 'category': 'General'},
]

# ── Demo event ────────────────────────────────────────────────────────────────
def build_event():
    return {
        'title':              'Project Showcase 2026',
        'category':           'Technical',
        'description': (
            'Live on-spot project showcase. Students present their mini-projects '
            'to a panel of judges. Registration is open at the venue from 9:00 AM. '
            'Judging begins at 12:00 PM sharp.'
        ),
        'rules': (
            '1. Individual participation only.\n'
            '2. Each student gets 5 minutes to present + 2 minutes Q&A.\n'
            '3. Judging criteria: Idea (25), Implementation (25), Presentation (25), Innovation (25).\n'
            '4. Students must be present by 11:45 AM for QR check-in.'
        ),
        'banner_url':         'https://picsum.photos/seed/project-showcase/800/400',
        'media_urls':         ['https://picsum.photos/seed/project-showcase/800/400'],
        'visibility':         'Public',
        'date':               TOMORROW,
        'time':               '12:00',
        'reg_deadline':       TOMORROW,       # open until tomorrow (day of event)
        'venue':              'CS Block — Lab 1',
        'participation_type': 'Individual',
        'is_team_event':      False,
        'open_hall_mode':     True,           # walk-in QR scan marks attendance
        'coordinators':       [c['email'] for c in DEMO_COORDINATORS],
        'form_schema': {
            'require_lead_whatsapp':   False,
            'require_member_usn':      False,
            'require_member_email':    False,
            'require_member_whatsapp': False,
            'submission_type':         'none',
        },
        'limits': {
            'team_min':         1,
            'team_max':         1,
            'max_participants': 100,
            'allowed_years':    [1, 2, 3, 4],
        },
        'fees':   {'regular': 0},
        'prizes': {
            '1st': '₹3,000 Cash + Certificate',
            '2nd': '₹2,000 Cash + Certificate',
            '3rd': '₹1,000 Cash + Certificate',
        },
        'spoc_id':  DEMO_SPOC['email'],
        'organizer': {
            'name':       DEMO_SPOC['name'],
            'email':      DEMO_SPOC['email'],
            'phone':      '9000000001',
            'group_link': '#',
        },
        'staff': (
            [{'name': j['name'], 'email': j['email'], 'role': 'Judge'}
             for j in DEMO_JUDGES]
            + [{'name': c['name'], 'email': c['email'], 'role': 'EventCoordinator'}
               for c in DEMO_COORDINATORS]
        ),
        # Judging criteria (must match key read by routes_judge.py)
        'judging_criteria': ['Idea', 'Implementation', 'Presentation', 'Innovation'],
        'status':             'active',
        'active_round':       1,
        'registration_count': 0,
        'has_custom_form':    False,
        'results_published':  False,
        'created_at':         NOW_STR,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────
def upsert_user(u):
    doc = {
        'email':      u['email'],
        'name':       u['name'],
        'password':   generate_password_hash(u['password']),
        'role':       u['role'],
        'category':   u.get('category', 'General'),
        'club':       u.get('club', ''),
        'phone':      u.get('phone', ''),
        'is_active':  True,
        'created_at': NOW_STR,
    }
    db.collection('users').document(u['email']).set(doc)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print('\nSapthaEvent — Live Demo Seeder')
    print('This will CREATE demo users + 1 event (does NOT wipe anything).')
    confirm = input('Type YES to continue: ').strip()
    if confirm != 'YES':
        print('Aborted.')
        sys.exit(0)

    # 1. Users
    print('\n[1/2] Creating demo users...')
    for u in [DEMO_SPOC] + DEMO_JUDGES + DEMO_COORDINATORS:
        upsert_user(u)
        print(f'  {u["role"]:<20} {u["email"]:<40} pw: {u["password"]}')

    # 2. Event
    print('\n[2/2] Creating demo event...')
    event_data = build_event()
    _, ref = db.collection('events').add(event_data)
    event_id = ref.id
    print(f'  Created event ID: {event_id}')
    print(f'  Title: {event_data["title"]}')
    print(f'  Date:  {TOMORROW}  12:00–15:00  |  Venue: {event_data["venue"]}')

    # Save event ID to file for quick reference
    with open('demo_event_id.txt', 'w') as f:
        f.write(event_id)

    # 3. Summary / credential card
    W = 66
    print(f'\n{"═"*W}')
    print(f'  DEMO READY — Tomorrow {TOMORROW}')
    print(f'{"═"*W}')

    print('\n  STEP-BY-STEP DEMO SCRIPT')
    print(f'  {"─"*60}')
    print('  09:00–10:00  REGISTRATION (on-spot at venue)')
    print('               Coordinator logs in → /coordinator/on_spot')
    print('               Enter student Name / Email / USN → Submit')
    print('               Student gets a ticket email with QR code')
    print()
    print('  10:00–11:30  SPOC SETUP (already done by this script)')
    print('               SPOC logs in → /spoc/dashboard')
    print('               Verify judges & coordinators are listed on event')
    print()
    print('  11:45–12:00  QR CHECK-IN')
    print('               Coordinator → /coordinator/scanner')
    print('               Select event "Project Showcase 2026"')
    print('               Scan each student\'s QR code → marks them Present')
    print()
    print('  12:00–14:00  JUDGING (judges score on their phones/laptops)')
    print('               Judge logs in → /judge/dashboard')
    print('               See list of Present students → Score each one')
    print('               Criteria: Idea / Implementation / Presentation / Innovation')
    print()
    print('  14:00        PUBLISH RESULTS')
    print(f'               SPOC → /spoc/event/{event_id}/results')
    print('               Click "Publish Results" → leaderboard goes live')
    print('               Certificates auto-generated for top participants')
    print()
    print(f'  {"─"*60}')
    print('  LOGIN CREDENTIALS')
    print(f'  {"─"*60}')
    print(f'  SPOC          {DEMO_SPOC["email"]:<35} {DEMO_SPOC["password"]}')
    for j in DEMO_JUDGES:
        print(f'  Judge         {j["email"]:<35} {j["password"]}')
    for c in DEMO_COORDINATORS:
        print(f'  Coordinator   {c["email"]:<35} {c["password"]}')
    print()
    print(f'  EVENT ID (for direct URLs): {event_id}')
    print('  Also saved to: demo_event_id.txt')
    print(f'{"═"*W}\n')


if __name__ == '__main__':
    main()
