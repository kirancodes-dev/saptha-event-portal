from app import app, db
from models import Participant, Event

with app.app_context():
    # 1. Create a Test Student
    print("Creating Test Student...")
    
    # Check if student already exists to avoid duplicate error
    if not Participant.query.filter_by(email='student@test.com').first():
        student = Participant(
            name="Test Student",
            email="student@test.com",
            password="password123"  # <--- THIS IS YOUR PASSWORD
        )
        db.session.add(student)
        db.session.commit()
        print("✅ Student Created!")
        print("   Email: student@test.com")
        print("   Pass:  password123")
    else:
        print("⚠️ Student 'student@test.com' already exists.")

    print("\nSystem ready for login testing.")