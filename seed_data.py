import datetime
from werkzeug.security import generate_password_hash
from models import db # Imports your Firebase connection

def generate_test_data():
    print("🚀 Starting Data Seeder...")

    # 1. CREATE THE EVENT
    event_id = "EVT-TEST-1000"
    event_data = {
        'title': 'Mega Tech Hackathon 2026 (TEST)',
        'date': 'Oct 15, 2026, 10:00 AM',
        'deadline': 'Oct 12, 2026, 11:59 PM',
        'venue': 'Main Campus',
        'description': 'A massive test event injected directly into the database.',
        'overview': 'Testing Smart Allocations and Granular Scanners with 100 students.',
        'rules': '- Rule 1: Code hard.\n- Rule 2: No copying.',
        'prizes': '1st Prize: ₹50000',
        'category': 'Tech',
        'media_urls': ['https://images.unsplash.com/photo-1504384308090-c894fdcc538d'],
        'banner_url': 'https://images.unsplash.com/photo-1504384308090-c894fdcc538d',
        'entry_fee': 500,
        'is_team_event': True,
        'judging_criteria': ['Innovation', 'Code Quality', 'UI/UX', 'Pitch'],
        'status': 'active',
        'registration_count': 25, # 25 Teams
        'staff': [], 
        'created_by': 'System Seeder',
        'created_by_email': 'tech@snpsu.edu.in', # Change this if your SPOC email is different!
        'created_at': datetime.datetime.now().strftime("%Y-%m-%d")
    }
    
    # 2. CREATE 5 JUDGES
    judges = []
    for i in range(1, 6):
        judge_email = f"judge{i}@test.com"
        judge_name = f"Test Judge {i}"
        judges.append({'name': judge_name, 'email': judge_email, 'role': 'Judge'})
        
        # Save judge to users collection
        db.collection('users').document(judge_email).set({
            'name': judge_name,
            'email': judge_email,
            'role': 'Judge',
            'password': generate_password_hash('password123'),
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d"),
            'needs_password_reset': False
        })
        print(f"✅ Created Judge: {judge_email} (Password: password123)")

    event_data['staff'] = judges
    db.collection('events').document(event_id).set(event_data)
    print(f"✅ Created Event: {event_data['title']}")

    # 3. CREATE 25 TEAMS (100 STUDENTS TOTAL)
    print("⏳ Generating 25 Teams (100 Students)...")
    for i in range(1, 26):
        reg_id = f"REG-TEST-{1000 + i}"
        team_name = f"Quantum Coders {i}"
        
        lead_usn = f"1SP26CS{i:03d}"
        
        members = []
        for j in range(1, 4): # Add 3 members to the lead
            members.append({
                'name': f"Member {j} (Team {i})",
                'usn': f"1SP26CS{i}{j}",
                'email': f"member{j}_team{i}@test.com",
                'phone': "9876543210",
                'attendance': 'Pending'
            })
            
        reg_data = {
            'reg_id': reg_id,
            'event_id': event_id,
            'event_title': event_data['title'],
            'lead_name': f"Lead Student {i}",
            'lead_email': f"lead{i}@test.com",
            'lead_usn': lead_usn,
            'phone': "9998887776",
            'team_name': team_name,
            'members': members,
            'status': 'Confirmed',
            'payment_status': 'Paid',
            'amount_paid': 500,
            'payment_mode': 'UPI',
            'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'attendance': 'Pending',
            'assigned_room': None,
            'assigned_judge_email': None
        }
        db.collection('registrations').document(reg_id).set(reg_data)
        
    print("✅ Successfully generated 25 Teams (100 total students)!")
    print("🎉 ALL TEST DATA LOADED! Go to your SPOC/Admin Dashboard to view it.")

if __name__ == '__main__':
    generate_test_data()