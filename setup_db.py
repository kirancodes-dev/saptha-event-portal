import firebase_admin
from firebase_admin import credentials, firestore
import datetime

# 1. Initialize Firestore
# We check if it's already initialized to avoid errors if you run this twice
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()
print("--- CONNECTED TO FIRESTORE ---")

# --- DATA GENERATORS ---

def create_users():
    print("Creating Users...")
    users = [
        {
            'email': 'admin@sapthahack.com',
            'data': {'name': 'System Admin', 'role': 'SuperAdmin', 'password': 'admin', 'created_at': datetime.datetime.now()}
        },
        {
            'email': 'spoc@snpsu.edu.in',
            'data': {'name': 'Dr. Rajesh (SPOC)', 'role': 'ClubSPOC', 'club_name': 'AI & Robotics', 'category': 'Tech', 'password': 'password123', 'created_at': datetime.datetime.now()}
        },
        {
            'email': 'student@snpsu.edu.in',
            'data': {'name': 'Rahul Student', 'role': 'Student', 'usn': '1SN23CS001', 'password': 'password123', 'created_at': datetime.datetime.now()}
        },
        {
            'email': 'judge@snpsu.edu.in',
            'data': {'name': 'Dr. Expert (Judge)', 'role': 'Judge', 'expertise': 'AI/ML', 'password': 'password123', 'created_at': datetime.datetime.now()}
        },
        {
            'email': 'coord@snpsu.edu.in',
            'data': {'name': 'Priya Coord', 'role': 'Coordinator', 'role_type': 'Student', 'password': 'password123', 'created_at': datetime.datetime.now()}
        }
    ]

    for u in users:
        # We use .set() with merge=True so we don't overwrite existing data if it exists
        db.collection('users').document(u['email']).set(u['data'], merge=True)
    print(f"✅ Created {len(users)} Sample Users.")

def create_event():
    print("Creating Sample Event...")
    
    # We need the SPOC's ID and Judge's ID we just created
    spoc_id = 'spoc@snpsu.edu.in'
    judge_id = 'judge@snpsu.edu.in'
    coord_id = 'coord@snpsu.edu.in'

    event_data = {
        'title': 'AI Hackathon 2026',
        'description': 'A 24-hour hackathon to solve real-world problems using Artificial Intelligence.',
        'date': '2026-03-15',
        'time': '09:00',
        'venue': 'Auditorium, Block A',
        'category': 'Tech',
        'status': 'active',
        'spoc_id': spoc_id,
        'created_by': spoc_id,
        
        # Rules
        'is_team_event': True,
        'team_min': 2,
        'team_max': 4,
        'max_participants': 100,
        'reg_deadline': '2026-03-10',
        'is_published': True,
        
        # Resources
        'banner_url': 'https://snpsu.edu.in/wp-content/uploads/2024/05/SNPSU-Campus.jpg',
        'prizes': '1st Place: ₹10,000, 2nd Place: ₹5,000',
        'group_link': 'https://chat.whatsapp.com/sample',
        'problem_statements': ['Healthcare AI', 'Smart Campus', 'FinTech'],
        
        # Assignments
        'coord_student_id': coord_id,
        'coord_staff_id': None,
        'judge_ids': [judge_id]
    }

    # Add event (auto-ID)
    # We store the reference to use it in the registration below
    _, ref = db.collection('events').add(event_data)
    print(f"✅ Created Event: {event_data['title']} (ID: {ref.id})")
    return ref.id, event_data

def create_registration(event_id, event_title):
    print("Creating Sample Registration...")
    
    reg_data = {
        'event_id': event_id,
        'event_title': event_title,
        'lead_email': 'student@snpsu.edu.in',
        'team_name': 'Code Warriors',
        'problem_statement': 'Smart Campus',
        'status': 'Approved',
        'attendance': 'Present', # Marked as present so Judge can see them
        'registered_at': datetime.datetime.now(),
        'members': [
            {'name': 'Rahul Student', 'role': 'Team Lead', 'usn': '1SN23CS001'},
            {'name': 'Teammate 1', 'role': 'Member', 'usn': '1SN23CS002'}
        ],
        # Sample Score (as if Judge already graded them)
        'scores': {
            'judge@snpsu.edu.in': {
                'judge_name': 'Dr. Expert',
                'criteria': {'innovation': 8, 'feasibility': 7, 'tech_stack': 9},
                'total': 24,
                'timestamp': '2026-03-15 10:00:00'
            }
        }
    }
    
    db.collection('registrations').add(reg_data)
    print("✅ Created Sample Registration for 'Code Warriors'")

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    try:
        create_users()
        evt_id, evt_data = create_event()
        create_registration(evt_id, evt_data['title'])
        print("\n🎉 DATABASE INITIALIZED SUCCESSFULLY!")
        print("You can now login with:")
        print(" - SPOC: spoc@snpsu.edu.in / password123")
        print(" - Judge: judge@snpsu.edu.in / password123")
        print(" - Student: student@snpsu.edu.in / password123")
    except Exception as e:
        print(f"❌ Error: {e}")