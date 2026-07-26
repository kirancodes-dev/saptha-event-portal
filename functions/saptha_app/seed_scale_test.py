"""
seed_scale_test.py — Bulk seeds 5,000 registrations to Supabase PostgreSQL for scale testing.
"""
import os
import sys
import uuid
import random
import logging
from datetime import datetime, date, timezone
try:
    from dotenv import load_dotenv
except Exception:
    dotenv = None

# Load environment variables
load_dotenv()

# Check database url is present
if not os.environ.get("DATABASE_URL"):
    print("ERROR: DATABASE_URL not set in environment.")
    sys.exit(1)

try:
    from sqlalchemy.orm import Session
except Exception:
    sqlalchemy = None
from db_pg import get_engine, get_session, init_db
from models_pg import (
    Base, User, Event, Registration, TeamMember, UserRole,
    EventCategory, EventStatus, RegistrationStatus, PaymentStatus, AttendanceStatus
)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FIRST_NAMES = ["Aarav", "Aditya", "Akash", "Ananya", "Anjali", "Arjun", "Aryan", "Ashwin", "Deepak", "Divya", "Ganesh", "Gautam", "Karthik", "Kiran", "Madhav", "Neha", "Nikhil", "Pooja", "Pranav", "Priya", "Rahul", "Rohit", "Sanjay", "Suresh", "Swathi", "Tejas", "Varun", "Vijay"]
LAST_NAMES = ["Sharma", "Reddy", "Kumar", "Pillai", "Shetty", "Rao", "Patel", "Singh", "Iyer", "Gowda", "Murthy", "Patil", "Kulkarni", "Bhat"]

def generate_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

def main():
    logger.info("Starting scale test seeding...")

    # Ensure tables exist
    init_db()

    with get_session() as session:
        # 1. Create SPOC user if not exists
        spoc_email = "biradark543@gmail.com"
        spoc = session.query(User).filter_by(email=spoc_email).first()
        if not spoc:
            logger.info("Creating SPOC user %s...", spoc_email)
            spoc = User(
                id=spoc_email,
                email=spoc_email,
                name="Kiran Biradar (SPOC)",
                phone="9876543210",
                role=UserRole.SPOC,
                college="Sapthagiri NPS University",
                department="Computer Science",
                password_hash="pbkdf2:sha256:600000$default_hashed_pass", # test hash
                is_active=True
            )
            session.add(spoc)
            session.commit()
            logger.info("SPOC user created.")
        else:
            logger.info("SPOC user already exists.")

        # 2. Create scale test event on May 29th, 2026
        event_id = uuid.uuid5(uuid.NAMESPACE_DNS, "saptha_scale_test_event_2026")
        event = session.query(Event).filter_by(id=event_id).first()
        if not event:
            logger.info("Creating scale test event...")
            event = Event(
                id=event_id,
                title="Saptha Mega Scale Event 2026",
                description="Scale testing event handling 5,000 mock registrations.",
                category=EventCategory.Technical,
                date=date(2026, 5, 29),
                deadline=date(2026, 5, 27),
                venue="Main Campus Grounds",
                status=EventStatus.active,
                max_teams=6000,
                min_team_size=1,
                max_team_size=3,
                fee=150.0,
                total_rounds=3,
                active_round=1,
                poster_url="https://snpsu.edu.in/wp-content/uploads/2024/05/SNPSU-Campus.jpg",
                rules="- Rule 1: Standard scale tests rules.\n- Rule 2: Complete tasks efficiently.",
                prizes="1st Prize: ₹50,000, 2nd Prize: ₹25,000",
                coordinator_id=spoc_email,
            )
            session.add(event)
            session.commit()
            logger.info("Scale test event created (ID: %s).", event_id)
        else:
            logger.info("Scale test event already exists (ID: %s).", event_id)

        # 3. Bulk insert 5,000 registrations
        logger.info("Checking if registrations already exist for this event...")
        existing_count = session.query(Registration).filter_by(event_id=event_id).count()
        if existing_count >= 5000:
            logger.info("Event already has %d registrations. Skipping seeding.", existing_count)
            return

        needed = 5000 - existing_count
        logger.info("Generating %d registrations and team members...", needed)

        reg_mappings = []
        member_mappings = []

        # Generate data in memory first
        for i in range(1, needed + 1):
            reg_uuid = uuid.uuid4()
            lead_name = generate_name()
            lead_email = f"lead_{existing_count + i}@scaletest.com"
            team_name = f"Scale Team {existing_count + i}"

            # Distribute attendance: 50% Present, 50% Pending
            attendance = AttendanceStatus.Present if i % 2 == 0 else AttendanceStatus.Pending

            reg_mappings.append({
                "id": reg_uuid,
                "event_id": event_id,
                "lead_name": lead_name,
                "lead_email": lead_email,
                "lead_phone": f"90000{i:05d}" if i <= 99999 else "9999999999",
                "team_name": team_name,
                "status": RegistrationStatus.confirmed,
                "payment_status": PaymentStatus.paid,
                "payment_id": f"pay_scale_{existing_count + i}",
                "attendance": attendance,
                "current_round": 1,
                "is_eliminated": False,
                "qr_code_url": f"https://api.qrserver.com/v1/create-qr-code/?data={reg_uuid}",
                "notes": "Automated scale test entry."
            })

            # Add a team member for each to double the DB load (to 10,000 records!)
            member_mappings.append({
                "id": uuid.uuid4(),
                "registration_id": reg_uuid,
                "name": generate_name(),
                "email": f"member_{existing_count + i}@scaletest.com",
                "phone": f"90001{i:05d}" if i <= 99999 else "9999999999",
                "usn": f"1SN26CS{i:04d}" if i <= 9999 else "1SN26CS9999",
                "college": "Sapthagiri NPS University",
                "department": random.choice(["CS", "EC", "ME", "IS"])
            })

        logger.info("Starting bulk insertion of registrations...")
        # Use bulk insert mappings for high performance
        session.bulk_insert_mappings(Registration, reg_mappings)
        logger.info("Bulk inserted %d registrations.", len(reg_mappings))

        logger.info("Starting bulk insertion of team members...")
        session.bulk_insert_mappings(TeamMember, member_mappings)
        logger.info("Bulk inserted %d team members.", len(member_mappings))

        # Update registration count on event
        session.query(Event).filter_by(id=event_id).update({
            "max_teams": 6000 # ensure cap holds
        })
        session.commit()

        logger.info("🎉 SCALE SEEDER FINISHED SUCCESSFULLY!")
        logger.info("Total registrations for event: %d", session.query(Registration).filter_by(event_id=event_id).count())
        logger.info("Total team members for event: %d", session.query(TeamMember).join(Registration).filter(Registration.event_id == event_id).count())

if __name__ == '__main__':
    main()
