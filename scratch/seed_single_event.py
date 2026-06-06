"""
seed_single_event.py — Seeds a single active event for testing.
Wipes existing events, registrations, and mock users,
then creates a clean environment under biradark543@gmail.com SPOC.
"""
import os
import sys
import datetime
from dotenv import load_dotenv

# Workaround for macOS Python 3.9 lacking scrypt
import werkzeug.security as _wsec
if not hasattr(_wsec, '_is_patched'):
    _original_generate_password_hash = _wsec.generate_password_hash
    def _safe_generate_password_hash(password, method='pbkdf2:sha256', salt_length=16):
        return _original_generate_password_hash(password, method=method, salt_length=salt_length)
    _wsec.generate_password_hash = _safe_generate_password_hash
    _wsec._is_patched = True

from werkzeug.security import generate_password_hash

# Load environment variables
load_dotenv()

# Initialize Firebase client
import firebase_admin
from firebase_admin import credentials, firestore

def init_firebase():
    if not firebase_admin._apps:
        key_path = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')
        if os.path.exists(key_path):
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred)
        else:
            print("ERROR: serviceAccountKey.json not found. Set FIREBASE_KEY_PATH or place it in CWD.")
            sys.exit(1)
    return firestore.client()

def main():
    print("🚀 Initializing Firebase...")
    db = init_firebase()

    print("🧹 Cleaning existing collections...")
    # Delete registrations
    regs = db.collection('registrations').stream()
    for r in regs:
        db.collection('registrations').document(r.id).delete()
    print("  Deleted all registrations.")

    # Delete events
    events = db.collection('events').stream()
    for e in events:
        db.collection('events').document(e.id).delete()
    print("  Deleted all events.")

    # Delete all users
    users = db.collection('users').stream()
    for u in users:
        db.collection('users').document(u.id).delete()
    print("  Deleted all users.")

    password_hash = generate_password_hash("Password@123")

    # Re-create accounts
    users_to_create = [
        {
            'email': 'admin@snpsu.edu.in',
            'name': 'System Administrator',
            'role': 'SuperAdmin',
            'category': 'All',
            'phone': '9876500000',
            'password': password_hash,
            'needs_password_reset': False,
            'is_active': True,
            'created_at': datetime.date.today().strftime('%Y-%m-%d')
        },
        {
            'email': 'biradark543@gmail.com',
            'name': 'Kiran Biradar (SPOC)',
            'role': 'ClubSPOC',
            'category': 'Technical',
            'phone': '9876500001',
            'password': password_hash,
            'needs_password_reset': False,
            'is_active': True,
            'created_at': datetime.date.today().strftime('%Y-%m-%d')
        },
        {
            'email': 'coordinator@example.com',
            'name': 'Event Coordinator',
            'role': 'EventCoordinator',
            'category': 'Technical',
            'phone': '9876500002',
            'password': password_hash,
            'needs_password_reset': False,
            'is_active': True,
            'created_at': datetime.date.today().strftime('%Y-%m-%d')
        },
        {
            'email': 'judge@example.com',
            'name': 'Event Judge',
            'role': 'Judge',
            'category': 'Technical',
            'phone': '9876500003',
            'password': password_hash,
            'needs_password_reset': False,
            'is_active': True,
            'created_at': datetime.date.today().strftime('%Y-%m-%d')
        },
        {
            'email': 'student@example.com',
            'name': 'Student One',
            'role': 'Student',
            'category': 'General',
            'phone': '9876500004',
            'usn': '1SNPSU22CS001',
            'password': password_hash,
            'needs_password_reset': False,
            'is_active': True,
            'created_at': datetime.date.today().strftime('%Y-%m-%d')
        }
    ]

    for u in users_to_create:
        db.collection('users').document(u['email']).set(u)
        print(f"  Created user: {u['email']} [{u['role']}] with Password@123")

    # Create Event
    event_id = "EVT-TEST-SINGLE"
    
    # Event dates
    today = datetime.date.today()
    evt_date = (today + datetime.timedelta(days=5)).strftime('%Y-%m-%d')
    deadline_date = (today + datetime.timedelta(days=3)).strftime('%Y-%m-%d')

    event_data = {
        'title': 'Saptha Mega Hackathon 2026',
        'category': 'Technical',
        'date': evt_date,
        'date_display': f"{(today + datetime.timedelta(days=5)).strftime('%B %d, %Y')} — 10:00 AM",
        'deadline': deadline_date,
        'venue': 'Main Auditorium, Block A',
        'description': 'The ultimate coding showdown at Sapthagiri NPS University.',
        'overview': 'Saptha Mega Hackathon 2026 brings together the brightest minds to solve real-world problems. Test your skills, collaborate, and win prizes.',
        'rules': '- Teams can have up to 4 members.\n- Plagiarism leads to immediate disqualification.\n- Submissions must be uploaded before the deadline.\n- Judge decisions are final.',
        'prizes': '1st Place: Rs. 25,000 + Trophy + Certificate\n2nd Place: Rs. 15,000 + Certificate\n3rd Place: Rs. 5,000 + Certificate',
        'judging_criteria': ['Innovation', 'Technical Complexity', 'User Experience', 'Presentation'],
        'entry_fee': 0,
        'is_team_event': True,
        'open_hall_mode': True,
        'cert_template': 2,
        'status': 'active',
        'active_round': 1,
        'registration_count': 5,
        'banner_url': '/static/img/event_slide1.png',
        'media_urls': [
            '/static/img/event_slide1.png',
            '/static/img/event_slide2.png',
            '/static/img/event_slide3.png',
            '/static/img/event_slide4.png'
        ],
        'staff': [
            {'name': 'Event Coordinator', 'email': 'coordinator@example.com', 'role': 'EventCoordinator'},
            {'name': 'Event Judge', 'email': 'judge@example.com', 'role': 'Judge'}
        ],
        'spoc_id': 'biradark543@gmail.com',
        'created_by': 'Kiran Biradar (SPOC)',
        'created_by_email': 'biradark543@gmail.com',
        'created_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    }

    db.collection('events').document(event_id).set(event_data)
    print(f"  Created Single Test Event: {event_data['title']}")

    # Seed 5 Registrations
    registrations_to_seed = [
        {
            'reg_id': 'REG-001',
            'event_id': event_id,
            'event_title': event_data['title'],
            'lead_name': 'Student One',
            'lead_email': 'student@example.com',
            'lead_usn': '1SNPSU22CS001',
            'phone': '9876500004',
            'team_name': 'Cyber Warriors',
            'members': [
                {'name': 'Alice member', 'usn': '1SNPSU22CS011', 'email': 'alice.m@example.com', 'phone': '9876500011', 'attendance': 'Pending'},
                {'name': 'Bob member', 'usn': '1SNPSU22CS012', 'email': 'bob.m@example.com', 'phone': '9876500012', 'attendance': 'Pending'}
            ],
            'status': 'Confirmed',
            'payment_status': 'Paid',
            'amount_paid': 0,
            'payment_mode': 'UPI',
            'registered_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'attendance': 'Present',
            'checkin_time': '09:15:00',
            'assigned_room': 'Lab 301',
            'assigned_judge_email': 'judge@example.com',
            'current_round': 1,
            'is_eliminated': False,
            'scores': {}
        },
        {
            'reg_id': 'REG-002',
            'event_id': event_id,
            'event_title': event_data['title'],
            'lead_name': 'Emma Watson',
            'lead_email': 'emma@example.com',
            'lead_usn': '1SNPSU22CS002',
            'phone': '9876500005',
            'team_name': 'Neural Nets',
            'members': [
                {'name': 'Harry member', 'usn': '1SNPSU22CS013', 'email': 'harry.m@example.com', 'phone': '9876500013', 'attendance': 'Pending'}
            ],
            'status': 'Confirmed',
            'payment_status': 'Paid',
            'amount_paid': 0,
            'payment_mode': 'UPI',
            'registered_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'attendance': 'Present',
            'checkin_time': '09:20:00',
            'assigned_room': 'Lab 301',
            'assigned_judge_email': 'judge@example.com',
            'current_round': 1,
            'is_eliminated': False,
            'scores': {}
        },
        {
            'reg_id': 'REG-003',
            'event_id': event_id,
            'event_title': event_data['title'],
            'lead_name': 'John Doe',
            'lead_email': 'john@example.com',
            'lead_usn': '1SNPSU22CS003',
            'phone': '9876500006',
            'team_name': 'Code Wizards',
            'members': [],
            'status': 'Confirmed',
            'payment_status': 'Paid',
            'amount_paid': 0,
            'payment_mode': 'UPI',
            'registered_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'attendance': 'Present',
            'checkin_time': '09:25:00',
            'assigned_room': 'Lab 302',
            'assigned_judge_email': 'judge@example.com',
            'current_round': 1,
            'is_eliminated': False,
            'scores': {}
        },
        {
            'reg_id': 'REG-004',
            'event_id': event_id,
            'event_title': event_data['title'],
            'lead_name': 'Sophia Loren',
            'lead_email': 'sophia@example.com',
            'lead_usn': '1SNPSU22CS004',
            'phone': '9876500007',
            'team_name': 'Data Divas',
            'members': [],
            'status': 'Confirmed',
            'payment_status': 'Paid',
            'amount_paid': 0,
            'payment_mode': 'UPI',
            'registered_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'attendance': 'Pending',
            'assigned_room': None,
            'assigned_judge_email': None,
            'current_round': 1,
            'is_eliminated': False,
            'scores': {}
        },
        {
            'reg_id': 'REG-005',
            'event_id': event_id,
            'event_title': event_data['title'],
            'lead_name': 'Oliver Twist',
            'lead_email': 'oliver@example.com',
            'lead_usn': '1SNPSU22CS005',
            'phone': '9876500008',
            'team_name': 'Web Wranglers',
            'members': [],
            'status': 'Confirmed',
            'payment_status': 'Paid',
            'amount_paid': 0,
            'payment_mode': 'UPI',
            'registered_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'attendance': 'Pending',
            'assigned_room': None,
            'assigned_judge_email': None,
            'current_round': 1,
            'is_eliminated': False,
            'scores': {}
        }
    ]

    for r in registrations_to_seed:
        db.collection('registrations').document(r['reg_id']).set(r)
        print(f"  Created registration: {r['reg_id']} for team '{r['team_name']}' ({r['attendance']})")

    print("\n🎉 Seeding completed successfully! Single event system ready for testing.")
    print("   Logins: SuperAdmin (admin@snpsu.edu.in), SPOC (biradark543@gmail.com), Coordinator (coordinator@example.com), Judge (judge@example.com), Student (student@example.com)")
    print("   Password for all: Password@123")

if __name__ == '__main__':
    main()
