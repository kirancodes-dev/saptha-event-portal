"""
init_zoho_db.py — Automated Database Schema Creation & Seeding for Zoho Catalyst
================================================================================
Automatically creates all database tables (users, events, registrations, forms,
scores, audit logs) and seeds the initial SuperAdmin account.
"""

import os
import sys
import logging
try:
    from sqlalchemy import create_engine
except Exception:
    sqlalchemy = None
from models_pg import Base, User
from werkzeug.security import generate_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_all_tables(db_url: str = None):
    url = db_url or os.environ.get('DATABASE_URL')
    if not url:
        logger.error("DATABASE_URL is not set. Pass db_url or set DATABASE_URL environment variable.")
        sys.exit(1)

    logger.info("Connecting to database: %s", url.split('@')[-1] if '@' in url else url)
    engine = create_engine(url, pool_pre_ping=True)

    logger.info("Creating all database tables automatically...")
    Base.metadata.create_all(bind=engine)
    logger.info("✅ All database tables created successfully!")

    # Seed initial SuperAdmin user
    try:
        from sqlalchemy.orm import sessionmaker
    except Exception:
        sqlalchemy = None
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        admin_email = os.environ.get('SUPER_ADMIN_EMAIL', 'admin@snpsu.edu.in')
        existing = session.query(User).filter_by(email=admin_email).first()
        if not existing:
            admin_user = User(
                email=admin_email,
                name="System SuperAdmin",
                role="SuperAdmin",
                password=generate_password_hash(os.environ.get('SUPER_ADMIN_PASS', 'Saptha@Admin2026')),
                usn="ADMIN001"
            )
            session.add(admin_user)
            session.commit()
            logger.info("✅ Initial SuperAdmin user seeded: %s", admin_email)
        else:
            logger.info("SuperAdmin user already exists: %s", admin_email)

        # Seed sample matchmaker participant users if none present
        participant_count = session.query(User).filter_by(role="Participant").count()
        if participant_count == 0:
            sample_participants = [
                {
                    "email": "aarav.m@snpsu.edu.in",
                    "name": "Aarav Mehta",
                    "role": "Participant",
                    "usn": "1SP21CS001",
                    "department": "Computer Science",
                    "skills": "Python, Flask, Machine Learning, SQL",
                    "interests": "AI Hackathon, Data Science Showdown",
                    "bio": "Passionate ML developer looking for front-end designer partner."
                },
                {
                    "email": "sneha.k@snpsu.edu.in",
                    "name": "Sneha Kulkarni",
                    "role": "Participant",
                    "usn": "1SP21CS042",
                    "department": "Information Science",
                    "skills": "Figma, UI/UX Design, React, Tailwind",
                    "interests": "Designathon, Web Development",
                    "bio": "UI/UX designer. Seeking Python developers."
                }
            ]
            for sp in sample_participants:
                user = User(
                    email=sp["email"],
                    name=sp["name"],
                    role=sp["role"],
                    usn=sp["usn"],
                    department=sp["department"],
                    skills=sp["skills"],
                    interests=sp["interests"],
                    bio=sp["bio"],
                    password=generate_password_hash("Student@2026")
                )
                session.add(user)
            session.commit()
            logger.info("✅ Sample matchmaker participants seeded successfully!")

if __name__ == '__main__':
    db_url_input = sys.argv[1] if len(sys.argv) > 1 else None
    create_all_tables(db_url_input)
