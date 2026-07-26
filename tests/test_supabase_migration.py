"""
tests/test_supabase_migration.py — Tests for migrate_to_supabase.py
"""
import uuid
import json
import unittest
from datetime import datetime, date, timezone
from unittest.mock import MagicMock

try:
    from sqlalchemy import create_engine
except Exception:
    sqlalchemy = None
try:
    from sqlalchemy.orm import sessionmaker
except Exception:
    sqlalchemy = None

# Import Models and Base
from models_pg import (
    Base, User, Event, Registration, TeamMember, Score, EventForm,
    FormSubmission, AuditLog, PushSubscription, UserRole, EventCategory,
    EventStatus, RegistrationStatus, PaymentStatus, AttendanceStatus
)

# Import functions under test
from migrate_to_supabase import (
    to_uuid, parse_date, parse_datetime,
    map_user_role, map_event_category, map_event_status,
    map_registration_status, map_payment_status, map_attendance_status,
    migrate_users, migrate_events, migrate_registrations_and_relations,
    migrate_event_forms, migrate_form_submissions, migrate_audit_log,
    migrate_push_subscriptions
)


class MockDocumentSnapshot:
    """Mock Firestore Document Snapshot."""
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return self._data.copy()


class MockCollectionReference:
    """Mock Firestore Collection Reference."""
    def __init__(self, docs_list):
        self.docs = docs_list

    def stream(self):
        return iter(self.docs)


class MockFirestoreClient:
    """Mock Firestore Client."""
    def __init__(self):
        self.collections = {}

    def set_collection(self, name, doc_data_dict):
        docs = [MockDocumentSnapshot(k, v) for k, v in doc_data_dict.items()]
        self.collections[name] = MockCollectionReference(docs)

    def collection(self, name):
        return self.collections.get(name, MockCollectionReference([]))


class TestSupabaseMigration(unittest.TestCase):
    """Test Suite for Supabase/Postgres Database Migration Helper Methods."""

    def setUp(self):
        # Create an in-memory SQLite database for testing SQL models/schema
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.session = self.SessionLocal()

        # Mock Firestore db client
        self.db = MockFirestoreClient()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_to_uuid_deterministic(self):
        """Test deterministic UUID generation from Firestore document IDs."""
        id1 = "evt_001"
        id2 = "evt_001"
        id3 = "evt_002"

        uuid1 = to_uuid(id1)
        uuid2 = to_uuid(id2)
        uuid3 = to_uuid(id3)

        self.assertIsInstance(uuid1, uuid.UUID)
        self.assertEqual(uuid1, uuid2)
        self.assertNotEqual(uuid1, uuid3)

        # Test if it's already a valid UUID string
        valid_uuid_str = str(uuid.uuid4())
        parsed_uuid = to_uuid(valid_uuid_str)
        self.assertEqual(parsed_uuid, uuid.UUID(valid_uuid_str))

    def test_parse_date(self):
        """Test robust date parsing helper."""
        self.assertEqual(parse_date("2026-03-15"), date(2026, 3, 15))
        # fallback behavior
        today = date.today()
        self.assertEqual(parse_date(None), today)
        self.assertEqual(parse_date("invalid-date-string"), today)

    def test_parse_datetime(self):
        """Test robust datetime parsing helper."""
        parsed = parse_datetime("2026-03-15T12:00:00Z")
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 3)
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)

    def test_map_user_role(self):
        """Test role mappings from string to UserRole enum."""
        self.assertEqual(map_user_role("SuperAdmin"), UserRole.SuperAdmin)
        self.assertEqual(map_user_role("ClubSPOC"), UserRole.SPOC)
        self.assertEqual(map_user_role("EventCoordinator"), UserRole.Coordinator)
        self.assertEqual(map_user_role("Judge"), UserRole.Judge)
        self.assertEqual(map_user_role("Student"), UserRole.Participant)
        self.assertEqual(map_user_role("unknown"), UserRole.Participant)

    def test_map_event_category(self):
        """Test category mappings from string to EventCategory enum."""
        self.assertEqual(map_event_category("Tech"), EventCategory.Technical)
        self.assertEqual(map_event_category("Technical"), EventCategory.Technical)
        self.assertEqual(map_event_category("Cultural"), EventCategory.Cultural)
        self.assertEqual(map_event_category("Sports"), EventCategory.Sports)
        self.assertEqual(map_event_category("Management"), EventCategory.Management)

    def test_migrate_users(self):
        """Test user collection migration to Postgres/SQL database."""
        users_data = {
            "admin@sapthahack.com": {
                "name": "System Admin",
                "role": "SuperAdmin",
                "password": "hashed_password_xyz",
                "phone": "9988776655",
                "college": "SNPSU",
                "department": "CSE",
                "created_at": "2026-01-01T10:00:00Z"
            },
            "student@snpsu.edu.in": {
                "name": "Rahul Student",
                "role": "Student",
                "password": "hashed_password_abc",
                "phone": "9900112233",
                "college": "SNPSU",
                "department": "ISE",
                "created_at": "2026-02-15T15:30:00Z"
            }
        }
        self.db.set_collection("users", users_data)

        # Migrate
        migrate_users(self.db, self.session)

        # Assertions
        db_users = self.session.query(User).all()
        self.assertEqual(len(db_users), 2)

        admin = self.session.query(User).filter_by(email="admin@sapthahack.com").first()
        self.assertIsNotNone(admin)
        self.assertEqual(admin.name, "System Admin")
        self.assertEqual(admin.role, UserRole.SuperAdmin)
        self.assertEqual(admin.password_hash, "hashed_password_xyz")

        student = self.session.query(User).filter_by(email="student@snpsu.edu.in").first()
        self.assertIsNotNone(student)
        self.assertEqual(student.role, UserRole.Participant)
        self.assertEqual(student.department, "ISE")

    def test_migrate_events(self):
        """Test event collection migration to Postgres/SQL database."""
        events_data = {
            "evt_001": {
                "title": "AI Hackathon 2026",
                "overview": "Testing Smart Allocations.",
                "category": "Tech",
                "date": "2026-03-15",
                "deadline": "2026-03-10",
                "venue": "Auditorium A",
                "status": "active",
                "entry_fee": 150.0,
                "created_by_email": "spoc@snpsu.edu.in"
            }
        }
        self.db.set_collection("events", events_data)

        # Migrate
        migrate_events(self.db, self.session)

        # Assertions
        db_events = self.session.query(Event).all()
        self.assertEqual(len(db_events), 1)

        event = self.session.query(Event).filter_by(title="AI Hackathon 2026").first()
        self.assertIsNotNone(event)
        self.assertEqual(event.id, to_uuid("evt_001"))
        self.assertEqual(event.category, EventCategory.Technical)
        self.assertEqual(event.fee, 150.0)
        self.assertEqual(event.coordinator_id, "spoc@snpsu.edu.in")

    def test_migrate_registrations_relations_and_scores(self):
        """Test registrations, nested members, and nested judge scores migration."""
        # Setup parents first (requires events table records to satisfy Foreign Keys)
        evt_uuid = to_uuid("evt_001")
        test_event = Event(
            id=evt_uuid,
            title="AI Hackathon 2026",
            category=EventCategory.Technical,
            date=date(2026, 3, 15),
            venue="Auditorium A"
        )
        self.session.add(test_event)
        self.session.commit()

        regs_data = {
            "reg_001": {
                "event_id": "evt_001",
                "lead_name": "Rahul Student",
                "lead_email": "student@snpsu.edu.in",
                "lead_phone": "9900112233",
                "team_name": "Code Warriors",
                "status": "Approved",
                "payment_status": "Paid",
                "payment_id": "pay_tx_999",
                "attendance": "Present",
                "current_round": 1,
                "members": [
                    {"name": "Teammate A", "email": "team_a@snpsu.edu.in", "usn": "1SNCS001"},
                    {"name": "Teammate B", "email": "team_b@snpsu.edu.in", "usn": "1SNCS002"}
                ],
                "scores": {
                    "judge1@snpsu.edu.in": {
                        "judge_name": "Prof. Arun",
                        "total": 24,
                        "criteria": {"innovation": 8, "presentation": 8, "tech": 8},
                        "timestamp": "2026-03-15T12:00:00Z"
                    }
                }
            }
        }
        self.db.set_collection("registrations", regs_data)

        # Migrate
        migrate_registrations_and_relations(self.db, self.session)

        # Check Registration
        db_regs = self.session.query(Registration).all()
        self.assertEqual(len(db_regs), 1)
        reg = db_regs[0]
        self.assertEqual(reg.id, to_uuid("reg_001"))
        self.assertEqual(reg.team_name, "Code Warriors")
        self.assertEqual(reg.status, RegistrationStatus.confirmed)
        self.assertEqual(reg.payment_status, PaymentStatus.paid)

        # Check Nested Members
        db_members = self.session.query(TeamMember).all()
        self.assertEqual(len(db_members), 2)
        member1 = self.session.query(TeamMember).filter_by(name="Teammate A").first()
        self.assertIsNotNone(member1)
        self.assertEqual(member1.registration_id, reg.id)
        self.assertEqual(member1.usn, "1SNCS001")

        # Check Nested Scores
        db_scores = self.session.query(Score).all()
        self.assertEqual(len(db_scores), 1)
        score = db_scores[0]
        self.assertEqual(score.registration_id, reg.id)
        self.assertEqual(score.judge_id, "judge1@snpsu.edu.in")
        self.assertEqual(score.total, 24.0)
        criteria = json.loads(score.criteria)
        self.assertEqual(criteria.get("innovation"), 8)
