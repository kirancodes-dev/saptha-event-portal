"""
migrate_to_supabase.py — Migration script from Firebase Firestore to Supabase (PostgreSQL)

This script reads data from Firestore and inserts it into PostgreSQL tables
defined by models_pg.py using SQLAlchemy.

Usage:
  # Set DATABASE_URL and Firebase credentials, then run:
  python migrate_to_supabase.py
"""
import os
import sys
import json
import uuid
import logging
from datetime import datetime, date, timezone
from dateutil import parser as date_parser
try:
    from dotenv import load_dotenv
except Exception:
    dotenv = None

# Load environment variables from .env
load_dotenv()

try:
    import firebase_admin
except ImportError:
    firebase_admin = None
try:
    from firebase_admin import credentials, firestore
except ImportError:
    credentials = firestore = auth = None
try:
    from sqlalchemy.orm import Session
except Exception:
    sqlalchemy = None

# Import SQLAlchemy DB helpers and Models
from db_pg import get_engine, init_db, get_session
from models_pg import (
    Base, User, Event, Registration, TeamMember, Score, EventForm,
    FormSubmission, AuditLog, PushSubscription, UserRole, EventCategory,
    EventStatus, RegistrationStatus, PaymentStatus, AttendanceStatus
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ── Utility: ID mapping ──────────────────────────────────────────────────────
def to_uuid(doc_id):
    """Generate a deterministic UUID from any Firestore document ID.

    If the document ID is already a valid UUID, returns it as-is.
    """
    if not doc_id:
        return None
    try:
        return uuid.UUID(doc_id)
    except ValueError:
        # Generate deterministic UUID using DNS namespace
        return uuid.uuid5(uuid.NAMESPACE_DNS, doc_id)


def safe_str(val) -> str:
    """Safely convert any type to string.

    Handles None (returns empty string) and JSON-serializable complex objects
    (lists, dicts) by serializing them to a JSON string.
    """
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return str(val)


# ── Utility: Date & Datetime Parsers ─────────────────────────────────────────
def parse_date(val) -> date:
    """Parse date fields safely from Firestore to python date object."""
    if not val:
        return date.today()
    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()
    try:
        # Check if Firestore Timestamp
        if hasattr(val, 'date'):
            return val.date()
        # Parse ISO or natural language strings
        dt = date_parser.parse(str(val))
        return dt.date()
    except Exception as e:
        logger.warning("Failed to parse date %s, using today: %s", val, e)
        return date.today()


def parse_datetime(val) -> datetime:
    """Parse datetime fields safely from Firestore to timezone-aware UTC datetime."""
    if not val:
        return datetime.now(timezone.utc)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val
    try:
        if hasattr(val, 'to_dict'): # Firestore Timestamp fallback
            return val
        dt = date_parser.parse(str(val))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        logger.warning("Failed to parse datetime %s: %s", val, e)
        return datetime.now(timezone.utc)


# ── Mappings ─────────────────────────────────────────────────────────────────
def map_user_role(role_str) -> UserRole:
    role_map = {
        "superadmin": UserRole.SuperAdmin,
        "admin": UserRole.SuperAdmin,
        "coordinator": UserRole.Coordinator,
        "eventcoordinator": UserRole.Coordinator,
        "clubspoc": UserRole.SPOC,
        "spoc": UserRole.SPOC,
        "judge": UserRole.Judge,
        "student": UserRole.Participant,
        "participant": UserRole.Participant,
    }
    cleaned = str(role_str).strip().lower()
    return role_map.get(cleaned, UserRole.Participant)


def map_event_category(cat_str) -> EventCategory:
    cat_map = {
        "technical": EventCategory.Technical,
        "tech": EventCategory.Technical,
        "cultural": EventCategory.Cultural,
        "sports": EventCategory.Sports,
        "management": EventCategory.Management,
    }
    cleaned = str(cat_str).strip().lower()
    return cat_map.get(cleaned, EventCategory.Technical)


def map_event_status(status_str) -> EventStatus:
    status_map = {
        "active": EventStatus.active,
        "inactive": EventStatus.inactive,
        "completed": EventStatus.completed,
        "cancelled": EventStatus.cancelled,
    }
    cleaned = str(status_str).strip().lower()
    return status_map.get(cleaned, EventStatus.active)


def map_registration_status(status_str) -> RegistrationStatus:
    status_map = {
        "confirmed": RegistrationStatus.confirmed,
        "approved": RegistrationStatus.confirmed,
        "pending": RegistrationStatus.pending,
        "cancelled": RegistrationStatus.cancelled,
        "waitlisted": RegistrationStatus.waitlisted,
    }
    cleaned = str(status_str).strip().lower()
    return status_map.get(cleaned, RegistrationStatus.confirmed)


def map_payment_status(status_str) -> PaymentStatus:
    status_map = {
        "paid": PaymentStatus.paid,
        "unpaid": PaymentStatus.unpaid,
        "waived": PaymentStatus.waived,
        "refunded": PaymentStatus.refunded,
    }
    cleaned = str(status_str).strip().lower()
    return status_map.get(cleaned, PaymentStatus.unpaid)


def map_attendance_status(status_str) -> AttendanceStatus:
    status_map = {
        "present": AttendanceStatus.Present,
        "absent": AttendanceStatus.Absent,
        "pending": AttendanceStatus.Pending,
    }
    cleaned = str(status_str).strip().lower()
    return status_map.get(cleaned, AttendanceStatus.Pending)


# ── Database Initialization ──────────────────────────────────────────────────
def initialize_firebase():
    """Connect to Google Cloud Firestore."""
    if not firebase_admin._apps:
        creds_json = os.environ.get('FIREBASE_CREDENTIALS')
        if creds_json:
            cred = credentials.Certificate(json.loads(creds_json))
            firebase_admin.initialize_app(cred)
        else:
            key_path = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred)
            else:
                logger.error("Neither FIREBASE_CREDENTIALS nor local serviceAccountKey.json found.")
                sys.exit(1)
    return firestore.client()


# ── Collection Migrators ──────────────────────────────────────────────────────
def migrate_users(db, session: Session):
    logger.info("Migrating collection: 'users'...")
    count = 0
    docs = db.collection('users').stream()
    for doc in docs:
        data = doc.to_dict()
        email = doc.id.strip().lower()
        if not email:
            continue

        # Check if user already exists in SQL DB
        existing = session.query(User).filter_by(email=email).first()
        if existing:
            continue

        user = User(
            id=email,  # set primary key directly to email (matching Firestore doc ID pattern)
            email=email,
            name=safe_str(data.get('name', 'Unknown User')),
            phone=safe_str(data.get('phone', '')),
            role=map_user_role(data.get('role', 'Participant')),
            college=safe_str(data.get('college', '')),
            department=safe_str(data.get('department', '')),
            password_hash=safe_str(data.get('password') or data.get('passwordHash') or ''),
            is_active=data.get('is_active', data.get('isActive', True)),
            created_at=parse_datetime(data.get('created_at', data.get('createdAt'))),
        )
        session.add(user)
        count += 1
    session.commit()
    logger.info("Successfully migrated %d users.", count)


def migrate_events(db, session: Session):
    logger.info("Migrating collection: 'events'...")
    count = 0
    docs = db.collection('events').stream()
    for doc in docs:
        data = doc.to_dict()
        event_id = to_uuid(doc.id)

        # Check if event already exists
        existing = session.query(Event).filter_by(id=event_id).first()
        if existing:
            continue

        # Determine coordinator email if staff list contains one
        coord_email = None
        staff = data.get('staff', [])
        for member in staff:
            if isinstance(member, dict) and member.get('role') in ('EventCoordinator', 'Coordinator'):
                coord_email = member.get('email')
                break
        if not coord_email:
            coord_email = data.get('created_by_email') or data.get('spoc_id')

        event = Event(
            id=event_id,
            title=safe_str(data.get('title', 'Untitled Event')),
            description=safe_str(data.get('description') or data.get('overview') or ''),
            category=map_event_category(data.get('category', 'Technical')),
            date=parse_date(data.get('date')),
            deadline=parse_date(data.get('deadline')) if data.get('deadline') else None,
            venue=safe_str(data.get('venue', 'Unknown Venue')),
            status=map_event_status(data.get('status', 'active')),
            max_teams=data.get('max_teams', data.get('max_participants')),
            min_team_size=data.get('min_team_size', data.get('team_min', 1)),
            max_team_size=data.get('max_team_size', data.get('team_max', 1)),
            fee=float(data.get('fee', data.get('entry_fee', 0.0))),
            total_rounds=data.get('total_rounds', data.get('totalRounds', 1)),
            active_round=data.get('active_round', data.get('activeRound', 1)),
            poster_url=safe_str(data.get('poster_url') or data.get('banner_url') or ''),
            rules=safe_str(data.get('rules') or ''),
            prizes=safe_str(data.get('prizes') or ''),
            coordinator_id=coord_email,
            created_at=parse_datetime(data.get('created_at', data.get('createdAt'))),
        )
        session.add(event)
        count += 1
    session.commit()
    logger.info("Successfully migrated %d events.", count)


def migrate_registrations_and_relations(db, session: Session):
    logger.info("Migrating collection: 'registrations'...")
    count_regs = 0
    count_members = 0
    count_scores = 0

    docs = db.collection('registrations').stream()
    for doc in docs:
        data = doc.to_dict()
        reg_id = to_uuid(doc.id)

        # Check if registration already exists
        existing = session.query(Registration).filter_by(id=reg_id).first()
        if existing:
            continue

        event_id_str = data.get('event_id')
        if not event_id_str:
            continue
        event_id = to_uuid(event_id_str)

        # Make sure event exists in Postgres (prevent foreign key violation)
        event_exists = session.query(Event).filter_by(id=event_id).first()
        if not event_exists:
            logger.warning("Event ID %s not found in events table. Skipping registration %s.", event_id, doc.id)
            continue

        # Create registration
        reg = Registration(
            id=reg_id,
            event_id=event_id,
            lead_name=safe_str(data.get('lead_name') or data.get('leadName', 'Unknown Lead')),
            lead_email=safe_str(data.get('lead_email') or data.get('leadEmail', 'unknown@test.com')),
            lead_phone=safe_str(data.get('lead_phone') or data.get('leadPhone') or data.get('phone', '0000000000')),
            team_name=safe_str(data.get('team_name') or data.get('teamName') or ''),
            status=map_registration_status(data.get('status', 'Confirmed')),
            payment_status=map_payment_status(data.get('payment_status') or data.get('paymentStatus', 'unpaid')),
            payment_id=safe_str(data.get('payment_id') or data.get('paymentId') or ''),
            attendance=map_attendance_status(data.get('attendance', 'Pending')),
            current_round=data.get('current_round', data.get('currentRound', 1)),
            is_eliminated=data.get('is_eliminated', data.get('isEliminated', False)),
            qr_code_url=safe_str(data.get('qr_code_url') or data.get('qrCodeUrl') or ''),
            notes=safe_str(data.get('notes') or ''),
            created_at=parse_datetime(data.get('registered_at') or data.get('createdAt')),
        )
        session.add(reg)
        count_regs += 1

        # Migrate team members (nested list)
        members = data.get('members', [])
        for idx, m in enumerate(members):
            if not isinstance(m, dict):
                continue
            member_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc.id}_member_{idx}")
            existing_m = session.query(TeamMember).filter_by(id=member_id).first()
            if existing_m:
                continue

            member = TeamMember(
                id=member_id,
                registration_id=reg_id,
                name=safe_str(m.get('name', 'Unknown Member')),
                email=safe_str(m.get('email', '')),
                phone=safe_str(m.get('phone', '')),
                usn=safe_str(m.get('usn', '')),
                college=safe_str(m.get('college', '')),
                department=safe_str(m.get('dept') or m.get('department') or ''),
            )
            session.add(member)
            count_members += 1

        # Migrate scores (nested dict)
        scores = data.get('scores', {})
        if isinstance(scores, dict):
            for judge_id, score_data in scores.items():
                if not isinstance(score_data, dict):
                    continue
                # composite primary key check
                existing_s = session.query(Score).filter_by(registration_id=reg_id, judge_id=judge_id).first()
                if existing_s:
                    continue

                criteria_data = score_data.get('criteria', {})
                score = Score(
                    registration_id=reg_id,
                    judge_id=judge_id,
                    judge_name=safe_str(score_data.get('judge_name', '')),
                    round=score_data.get('round', reg.current_round),
                    total=float(score_data.get('total', 0.0)),
                    criteria=json.dumps(criteria_data),
                    feedback=safe_str(score_data.get('feedback', '')),
                    scored_at=parse_datetime(score_data.get('timestamp') or score_data.get('scoredAt')),
                )
                session.add(score)
                count_scores += 1

    session.commit()
    logger.info("Successfully migrated %d registrations, %d team members, %d scores.", count_regs, count_members, count_scores)


def migrate_event_forms(db, session: Session):
    logger.info("Migrating collection: 'event_forms'...")
    count = 0
    docs = db.collection('event_forms').stream()
    for doc in docs:
        data = doc.to_dict()
        event_id = to_uuid(doc.id)

        # Check if form exists
        existing = session.query(EventForm).filter_by(event_id=event_id).first()
        if existing:
            continue

        # Check if event exists
        event_exists = session.query(Event).filter_by(id=event_id).first()
        if not event_exists:
            continue

        form = EventForm(
            event_id=event_id,
            fields_json=json.dumps(data.get('fields', data)),
            created_at=parse_datetime(data.get('created_at', data.get('createdAt'))),
        )
        session.add(form)
        count += 1
    session.commit()
    logger.info("Successfully migrated %d event forms.", count)


def migrate_form_submissions(db, session: Session):
    logger.info("Migrating collection: 'form_submissions'...")
    count = 0
    docs = db.collection('form_submissions').stream()
    for doc in docs:
        data = doc.to_dict()
        sub_id = to_uuid(doc.id)

        # Check if submission already exists
        existing = session.query(FormSubmission).filter_by(id=sub_id).first()
        if existing:
            continue

        event_id = to_uuid(data.get('event_id'))
        reg_id = to_uuid(data.get('registration_id'))

        # Make sure parents exist
        event_exists = session.query(Event).filter_by(id=event_id).first()
        reg_exists = session.query(Registration).filter_by(id=reg_id).first()
        if not event_exists or not reg_exists:
            continue

        sub = FormSubmission(
            id=sub_id,
            event_id=event_id,
            registration_id=reg_id,
            answers_json=json.dumps(data.get('answers', data)),
            submitted_at=parse_datetime(data.get('submitted_at', data.get('submittedAt'))),
        )
        session.add(sub)
        count += 1
    session.commit()
    logger.info("Successfully migrated %d form submissions.", count)


def migrate_audit_log(db, session: Session):
    logger.info("Migrating collection: 'audit_log'...")
    count = 0
    docs = db.collection('audit_log').stream()
    for doc in docs:
        data = doc.to_dict()
        log_id = to_uuid(doc.id)

        # Check if audit entry already exists
        existing = session.query(AuditLog).filter_by(id=log_id).first()
        if existing:
            continue

        entry = AuditLog(
            id=log_id,
            actor_email=safe_str(data.get('actor_email', 'system')),
            action=safe_str(data.get('action', 'unknown')),
            target_id=safe_str(data.get('target_id') or data.get('targetId') or ''),
            detail=safe_str(data.get('detail') or data.get('details') or ''),
            created_at=parse_datetime(data.get('created_at', data.get('createdAt'))),
        )
        session.add(entry)
        count += 1
    session.commit()
    logger.info("Successfully migrated %d audit logs.", count)


def migrate_push_subscriptions(db, session: Session):
    logger.info("Migrating collection: 'push_subscriptions'...")
    count = 0
    docs = db.collection('push_subscriptions').stream()
    for doc in docs:
        data = doc.to_dict()
        sub_id = to_uuid(doc.id)

        # Check if subscription already exists
        existing = session.query(PushSubscription).filter_by(id=sub_id).first()
        if existing:
            continue

        sub = PushSubscription(
            id=sub_id,
            user_email=safe_str(data.get('user_email', data.get('email', 'unknown'))),
            endpoint=safe_str(data.get('endpoint', '')),
            p256dh=safe_str(data.get('p256dh', '')),
            auth_key=safe_str(data.get('auth_key') or data.get('auth') or ''),
            created_at=parse_datetime(data.get('created_at', data.get('createdAt'))),
        )
        session.add(sub)
        count += 1
    session.commit()
    logger.info("Successfully migrated %d push subscriptions.", count)


# ── Run Migration ─────────────────────────────────────────────────────────────
def run_migration():
    logger.info("Starting database migration process...")

    # Initialize SQL database tables
    try:
        init_db()
        logger.info("PostgreSQL Database tables verified/created successfully.")
    except Exception as e:
        logger.error("Failed to initialize PostgreSQL tables: %s", e)
        sys.exit(1)

    # Initialize Firestore client
    try:
        db = initialize_firebase()
        logger.info("Connected to Google Cloud Firestore.")
    except Exception as e:
        logger.error("Failed to initialize Firebase client: %s", e)
        sys.exit(1)

    # Run migration step-by-step
    with get_session() as session:
        migrate_users(db, session)
        migrate_events(db, session)
        migrate_registrations_and_relations(db, session)
        migrate_event_forms(db, session)
        migrate_form_submissions(db, session)
        migrate_audit_log(db, session)
        migrate_push_subscriptions(db, session)

    logger.info("🎉 MIGRATION PROCESS COMPLETED SUCCESSFULLY!")


if __name__ == '__main__':
    run_migration()
