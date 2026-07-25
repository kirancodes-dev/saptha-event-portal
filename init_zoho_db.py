"""
init_zoho_db.py — Automated Database Schema Creation & Seeding for Zoho Catalyst
================================================================================
Automatically creates all database tables (users, events, registrations, forms,
scores, audit logs) and seeds the initial SuperAdmin account.
"""

import os
import sys
import logging
from sqlalchemy import create_engine
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
    from sqlalchemy.orm import sessionmaker
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

if __name__ == '__main__':
    db_url_input = sys.argv[1] if len(sys.argv) > 1 else None
    create_all_tables(db_url_input)
