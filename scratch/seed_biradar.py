import sys
import os
sys.path.insert(0, '/Users/kiranbiradar/Desktop/saptha-event-portal')

import datetime
from werkzeug.security import generate_password_hash

# Ensure we use Firestore database type
os.environ['DATABASE_TYPE'] = 'firestore'

# Import models to connect to Firestore
from models import db

def seed_biradar_data():
    print("🚀 Seeding SPOC account biradark543@gmail.com and test events...")

    if not db:
        print("❌ Error: Firebase db connection not available. Please check environment/credentials.")
        return

    spoc_email = "biradark543@gmail.com"
    
    # 1. Create/Update SPOC account in users collection
    spoc_data = {
        'email': spoc_email,
        'name': 'Kiran Biradar (Club SPOC)',
        'role': 'ClubSPOC',
        'password': generate_password_hash('password123', method='pbkdf2:sha256'),
        'created_at': datetime.datetime.now().strftime("%Y-%m-%d"),
        'needs_password_reset': False,
        'is_active': True
    }
    db.collection('users').document(spoc_email).set(spoc_data)
    print(f"✅ SPOC Account seeded: {spoc_email} (Password: password123, Role: ClubSPOC)")

    # 2. Add 2 mock Judges to users collection
    judge_alpha = "judge_alpha@test.edu"
    judge_beta = "judge_beta@test.edu"
    
    db.collection('users').document(judge_alpha).set({
        'email': judge_alpha,
        'name': 'Dr. Alpha (Strict)',
        'role': 'Judge',
        'password': generate_password_hash('password123', method='pbkdf2:sha256'),
        'is_active': True
    })
    db.collection('users').document(judge_beta).set({
        'email': judge_beta,
        'name': 'Dr. Beta (Lenient)',
        'role': 'Judge',
        'password': generate_password_hash('password123', method='pbkdf2:sha256'),
        'is_active': True
    })
    print("✅ Seeded Mock Judges: Dr. Alpha & Dr. Beta")

    # 3. Create Events under biradark543@gmail.com
    events = [
        {
            'id': 'evt_biradar_001',
            'title': 'National AI Showdown 2026',
            'category': 'Technical',
            'date': '2026-06-15',
            'deadline': '2026-06-12',
            'venue': 'CS Lab 3, Campus Arena',
            'description': 'An elite coding challenge to design state-of-the-art AI systems.',
            'overview': 'Develop next-gen generative models under strict rules.',
            'rules': '- Work in teams of 2-4.\n- Code must be open source.',
            'prizes': 'Winner: ₹1,00,000 | Runner-up: ₹50,000',
            'entry_fee': 150,
            'is_team_event': True,
            'limits': {'max_participants': 50, 'team_min': 2, 'team_max': 4},
            'status': 'active',
            'registration_count': 2,
            'spoc_id': spoc_email,
            'created_by': 'Kiran Biradar',
            'created_by_email': spoc_email,
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
        },
        {
            'id': 'evt_biradar_002',
            'title': 'Inter-University Cultural Fest',
            'category': 'Cultural',
            'date': '2026-06-22',
            'deadline': '2026-06-20',
            'venue': 'Main Auditorium',
            'description': 'A celebratory night showing off classical dance, music, and theatre.',
            'overview': 'Showcase your talents and represent your college.',
            'rules': '- Performance limit is 8 minutes.\n- Bring soundtracks on USB.',
            'prizes': 'Winner Trophy + ₹20,000',
            'entry_fee': 0,
            'is_team_event': False,
            'limits': {'max_participants': 200, 'team_min': 1, 'team_max': 1},
            'status': 'active',
            'registration_count': 1,
            'spoc_id': spoc_email,
            'created_by': 'Kiran Biradar',
            'created_by_email': spoc_email,
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
        },
        {
            'id': 'evt_biradar_003',
            'title': 'Annual Sports Meet - Track & Field',
            'category': 'Sports',
            'date': '2026-07-02',
            'deadline': '2026-06-30',
            'venue': 'Stadium Ground',
            'description': '100m, 400m, and relay events for universities in Karnataka.',
            'overview': 'Athletic tournaments organized for university state leagues.',
            'rules': '- Standard IAAF track rules apply.\n- Proper spikes required.',
            'prizes': 'Medals + Certificates',
            'entry_fee': 50,
            'is_team_event': False,
            'limits': {'max_participants': 100, 'team_min': 1, 'team_max': 1},
            'status': 'active',
            'registration_count': 1,
            'spoc_id': spoc_email,
            'created_by': 'Kiran Biradar',
            'created_by_email': spoc_email,
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
        }
    ]

    for event_data in events:
        db.collection('events').document(event_data['id']).set(event_data)
        print(f"✅ Seeded Event: {event_data['title']} (ID: {event_data['id']})")

    # 4. Create Registrations for these events
    registrations = [
        {
            'reg_id': 'reg_biradar_001',
            'event_id': 'evt_biradar_001',
            'event_title': 'National AI Showdown 2026',
            'lead_name': 'Suhas Kamath',
            'lead_email': 'suhas@student.edu',
            'lead_usn': '1SP26CS088',
            'phone': '9876543210',
            'team_name': 'Matrix Coders',
            'status': 'Confirmed',
            'payment_status': 'Paid',
            'amount_paid': 150,
            'payment_mode': 'UPI',
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'attendance': 'Present',
            'scores': {
                judge_alpha: {'total': 5.0},  # Strict average
                judge_beta: {'total': 9.0}   # Lenient average
            }
        },
        {
            'reg_id': 'reg_biradar_002',
            'event_id': 'evt_biradar_001',
            'event_title': 'National AI Showdown 2026',
            'lead_name': 'Anjali Sharma',
            'lead_email': 'anjali@student.edu',
            'lead_usn': '1SP26CS012',
            'phone': '9988776655',
            'team_name': 'Deep Learners',
            'status': 'Confirmed',
            'payment_status': 'Paid',
            'amount_paid': 150,
            'payment_mode': 'UPI',
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'attendance': 'Present',
            'scores': {
                judge_alpha: {'total': 6.0},
                judge_beta: {'total': 8.5}
            }
        },
        {
            'reg_id': 'reg_biradar_003',
            'event_id': 'evt_biradar_002',
            'event_title': 'Inter-University Cultural Fest',
            'lead_name': 'Rohit Raj',
            'lead_email': 'rohit@student.edu',
            'lead_usn': '1SP26CS050',
            'phone': '9000111222',
            'status': 'Confirmed',
            'payment_status': 'Free',
            'amount_paid': 0,
            'payment_mode': 'Free',
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'attendance': 'Pending'
        },
        {
            'reg_id': 'reg_biradar_004',
            'event_id': 'evt_biradar_003',
            'event_title': 'Annual Sports Meet - Track & Field',
            'lead_name': 'Vikas Gowda',
            'lead_email': 'vikas@student.edu',
            'lead_usn': '1SP26CS122',
            'phone': '9123456789',
            'status': 'Confirmed',
            'payment_status': 'Paid',
            'amount_paid': 50,
            'payment_mode': 'UPI',
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'attendance': 'Present'
        }
    ]

    for reg_data in registrations:
        db.collection('registrations').document(reg_data['reg_id']).set(reg_data)
        print(f"✅ Seeded Registration: {reg_data['lead_name']} (ID: {reg_data['reg_id']})")

    # 5. Create some mock feedback reviews for sentiment analysis
    feedbacks = [
        {
            'feedback_id': 'fb_biradar_001',
            'event_id': 'evt_biradar_001',
            'rating': 5,
            'comments': 'Absolutely phenomenal! Event structure and rules were outstanding.'
        },
        {
            'feedback_id': 'fb_biradar_002',
            'event_id': 'evt_biradar_001',
            'rating': 4,
            'comments': 'Great coding tasks, though lab seating was slightly packed.'
        },
        {
            'feedback_id': 'fb_biradar_003',
            'event_id': 'evt_biradar_001',
            'rating': 2,
            'comments': 'Too little time given for presentation, grading strictness was questionable.'
        }
    ]

    for fb in feedbacks:
        db.collection('feedback').document(fb['feedback_id']).set(fb)
        print(f"✅ Seeded Feedback: (ID: {fb['feedback_id']})")

    print("\n🎉 ALL SEEDING FOR biradark543@gmail.com SUCCESSFUL!")

if __name__ == '__main__':
    seed_biradar_data()
