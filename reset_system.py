
# BLK-10: refuse production-looking databases before anything connects
from seed_safety import guard  # noqa: E402
guard()

import os
from app import app, db
from models import Participant

test_password = os.environ.get('TEST_STUDENT_PASSWORD', 'test_password_placeholder')

with app.app_context():
    # 1. Create a Test Student
    print("Creating Test Student...")

    # Check if student already exists to avoid duplicate error
    if not Participant.query.filter_by(email='student@test.com').first():
        student = Participant(
            name="Test Student",
            email="student@test.com",
            password=test_password
        )
        db.session.add(student)
        db.session.commit()
        print("✅ Student Created!")
        print("   Email: student@test.com")
    else:
        print("⚠️ Student 'student@test.com' already exists.")

    print("\nSystem ready for login testing.")
