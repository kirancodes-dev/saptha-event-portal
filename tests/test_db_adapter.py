"""
tests/test_db_adapter.py — Unit tests for the SQL Firestore Compatibility Adapter
"""
import uuid
import json
import pytest
from datetime import datetime, date, timezone

try:
    from sqlalchemy import create_engine
except Exception:
    sqlalchemy = None
try:
    from sqlalchemy.orm import sessionmaker
except Exception:
    sqlalchemy = None

from models_pg import (
    Base, User, Event, Registration, TeamMember, Score, EventForm,
    FormSubmission, AuditLog, PushSubscription, UserRole, EventCategory,
    EventStatus, RegistrationStatus, PaymentStatus, AttendanceStatus
)
import db_pg
from db_adapter import SQLFirestoreAdapter, SQLBatch


@pytest.fixture(scope="function", autouse=True)
def setup_test_db(monkeypatch):
    """Set up an in-memory SQLite database patched into db_pg for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    
    # Monkeypatch db_pg engine and session local
    monkeypatch.setattr(db_pg, "_engine", engine)
    monkeypatch.setattr(db_pg, "_SessionLocal", SessionLocal)
    
    yield engine
    
    Base.metadata.drop_all(engine)


def test_user_crud():
    adapter = SQLFirestoreAdapter()
    users_ref = adapter.collection("users")
    
    user_id = "test_user@snpsu.edu.in"
    user_data = {
        "name": "Kiran Tester",
        "role": "SuperAdmin",
        "password": "hashed_password_123",
        "phone": "9876543210",
        "college": "NPSU",
        "department": "CSE",
        "is_active": True,
        "created_at": "2026-05-23T12:00:00Z"
    }
    
    # Test Create (set)
    users_ref.document(user_id).set(user_data)
    
    # Test Read (get)
    doc = users_ref.document(user_id).get()
    assert doc.exists
    assert doc.id == user_id
    
    data = doc.to_dict()
    assert data["name"] == "Kiran Tester"
    assert data["role"] == "SuperAdmin"
    assert data["password"] == "hashed_password_123"
    assert data["phone"] == "9876543210"
    assert data["college"] == "NPSU"
    assert data["department"] == "CSE"
    assert data["is_active"] is True
    
    # Test Update
    users_ref.document(user_id).update({
        "name": "Kiran Updated",
        "role": "Coordinator"
    })
    
    doc = users_ref.document(user_id).get()
    assert doc.get("name") == "Kiran Updated"
    assert doc.get("role") == "Coordinator"
    
    # Test Delete
    users_ref.document(user_id).delete()
    doc = users_ref.document(user_id).get()
    assert not doc.exists


def test_event_crud():
    adapter = SQLFirestoreAdapter()
    events_ref = adapter.collection("events")
    
    event_id = str(uuid.uuid4())
    event_data = {
        "title": "Saptha Hack 2026",
        "description": "The ultimate coding challenge",
        "category": "Tech",
        "date": "2026-05-29",
        "deadline": "2026-05-28",
        "venue": "B-Block Lab",
        "status": "active",
        "max_participants": 120,
        "team_min": 2,
        "team_max": 4,
        "entry_fee": 300.0,
        "total_rounds": 3,
        "active_round": 1,
        "banner_url": "https://example.com/banner.png",
        "rules": "Bring your own laptop",
        "prizes": "1st: 10K, 2nd: 5K",
        "coordinator_id": "spoc_tester@snpsu.edu.in",
        "open_hall_mode": True,
        "scoring_locked": False,
        "judging_criteria": [
            {"name": "Innovation", "weight": 40},
            {"name": "Execution", "weight": 60}
        ],
        "staff": ["judge_a@snpsu.edu.in", "judge_b@snpsu.edu.in"]
    }
    
    # Test Create (set)
    events_ref.document(event_id).set(event_data)
    
    # Test Read (get)
    doc = events_ref.document(event_id).get()
    assert doc.exists
    assert doc.id == event_id
    
    data = doc.to_dict()
    assert data["title"] == "Saptha Hack 2026"
    assert data["category"] == "Technical"  # Mapped to enum string
    assert data["max_participants"] == 120   # Mapped to max_teams
    assert data["team_min"] == 2
    assert data["team_max"] == 4
    assert data["entry_fee"] == 300.0
    assert data["banner_url"] == "https://example.com/banner.png"
    assert data["open_hall_mode"] is True
    assert data["scoring_locked"] is False
    assert data["judging_criteria"] == [
        {"name": "Innovation", "weight": 40},
        {"name": "Execution", "weight": 60}
    ]
    assert data["staff"] == ["judge_a@snpsu.edu.in", "judge_b@snpsu.edu.in"]
    
    # Test Update
    events_ref.document(event_id).update({
        "scoring_locked": True,
        "max_participants": 150
    })
    
    doc = events_ref.document(event_id).get()
    assert doc.get("scoring_locked") is True
    assert doc.get("max_participants") == 150


def test_registration_crud_and_nested_relations():
    adapter = SQLFirestoreAdapter()
    
    # First create parent event
    event_id = str(uuid.uuid4())
    adapter.collection("events").document(event_id).set({
        "title": "SQL Test Event",
        "category": "Tech",
        "date": "2026-05-29",
        "venue": "Online"
    })
    
    reg_id = str(uuid.uuid4())
    reg_data = {
        "event_id": event_id,
        "leadName": "John Doe",
        "leadEmail": "john.doe@test.com",
        "leadPhone": "9999999999",
        "teamName": "Dream Team",
        "status": "Approved",
        "paymentStatus": "Paid",
        "paymentId": "ch_12345",
        "attendance": "Present",
        "currentRound": 1,
        "isEliminated": False,
        "qrCodeUrl": "https://example.com/qr",
        "notes": "Fastest solver",
        "assigned_judge_email": "judge_one@test.com",
        "amount_paid": 100.0,
        "payment_mode": "UPI",
        "assigned_room": "Room 101",
        "registered_at": "2026-05-23T12:00:00Z",
        "members": [
            {"name": "Member One", "email": "m1@test.com", "phone": "123", "usn": "1SN01", "college": "SNPSU", "dept": "CSE"},
            {"name": "Member Two", "email": "m2@test.com", "phone": "456", "usn": "1SN02", "college": "SNPSU", "dept": "ISE"}
        ],
        "scores": {
            "judge_1": {
                "judge_name": "Judge One",
                "total": 18.0,
                "criteria": {"creativity": 9, "impact": 9},
                "feedback": "Outstanding idea",
                "timestamp": "2026-05-23T14:30:00Z"
            }
        }
    }
    
    # Test Create (set)
    adapter.collection("registrations").document(reg_id).set(reg_data)
    
    # Let's inspect the created registration
    doc = adapter.collection("registrations").document(reg_id).get()
    assert doc.exists
    data = doc.to_dict()
    assert data["leadName"] == "John Doe"
    assert data["status"] == "confirmed"
    assert data["paymentStatus"] == "paid"
    
    # Check members and scores (this verifies the new insert path)
    assert len(data["members"]) == 2
    assert data["members"][0]["name"] == "Member One"
    assert data["members"][0]["dept"] == "CSE"
    assert data["members"][1]["email"] == "m2@test.com"
    
    assert "judge_1" in data["scores"]
    assert data["scores"]["judge_1"]["judge_name"] == "Judge One"
    assert data["scores"]["judge_1"]["total"] == 18.0
    assert data["scores"]["judge_1"]["criteria"] == {"creativity": 9, "impact": 9}


def test_query_where_filtering_sorting_and_limiting():
    adapter = SQLFirestoreAdapter()
    users_ref = adapter.collection("users")
    
    # Seed users
    users_ref.document("usr_001").set({"name": "Alpha", "role": "Participant", "phone": "100", "is_active": True})
    users_ref.document("usr_002").set({"name": "Beta", "role": "Participant", "phone": "200", "is_active": True})
    users_ref.document("usr_003").set({"name": "Gamma", "role": "Coordinator", "phone": "300", "is_active": True})
    users_ref.document("usr_004").set({"name": "Delta", "role": "Participant", "phone": "400", "is_active": False})
    
    # Test simple equality filter
    res = list(users_ref.where("role", "==", "Participant").stream())
    assert len(res) == 3
    names = {r.to_dict()["name"] for r in res}
    assert names == {"Alpha", "Beta", "Delta"}
    
    # Test numeric-string comparison filters
    res_gt = list(users_ref.where("phone", ">", "150").stream())
    assert len(res_gt) == 3
    
    # Test multiple where filters
    res_multi = list(users_ref.where("role", "==", "Participant").where("is_active", "==", True).stream())
    assert len(res_multi) == 2
    names_multi = {r.to_dict()["name"] for r in res_multi}
    assert names_multi == {"Alpha", "Beta"}
    
    # Test IN operator
    res_in = list(users_ref.where("phone", "in", ["100", "300", "500"]).stream())
    assert len(res_in) == 2
    names_in = {r.to_dict()["name"] for r in res_in}
    assert names_in == {"Alpha", "Gamma"}
    
    # Test Sorting (order_by) DESC
    res_desc = list(users_ref.order_by("phone", "DESCENDING").stream())
    assert [r.id for r in res_desc] == ["usr_004", "usr_003", "usr_002", "usr_001"]
    
    # Test Sorting (order_by) ASC
    res_asc = list(users_ref.order_by("phone", "ASC").stream())
    assert [r.id for r in res_asc] == ["usr_001", "usr_002", "usr_003", "usr_004"]
    
    # Test Limiting
    res_limit = list(users_ref.order_by("phone", "DESCENDING").limit(2).stream())
    assert len(res_limit) == 2
    assert res_limit[0].id == "usr_004"
    assert res_limit[1].id == "usr_003"


def test_write_batch():
    adapter = SQLFirestoreAdapter()
    users_ref = adapter.collection("users")
    
    users_ref.document("usr_batch_1").set({"name": "User 1", "role": "Participant"})
    
    batch = adapter.batch()
    # Batch Update
    batch.update(users_ref.document("usr_batch_1"), {"name": "User 1 Updated"})
    # Batch Set
    batch.set(users_ref.document("usr_batch_2"), {"name": "User 2", "role": "Coordinator"})
    # Batch Delete
    users_ref.document("usr_batch_3").set({"name": "User 3", "role": "Participant"})
    batch.delete(users_ref.document("usr_batch_3"))
    
    # Commit batch
    batch.commit()
    
    # Verify results
    doc1 = users_ref.document("usr_batch_1").get()
    assert doc1.get("name") == "User 1 Updated"
    
    doc2 = users_ref.document("usr_batch_2").get()
    assert doc2.get("name") == "User 2"
    assert doc2.get("role") == "Coordinator"
    
    doc3 = users_ref.document("usr_batch_3").get()
    assert not doc3.exists


def test_pure_firestore_native_collections():
    """Test native Firestore dictionary storage for non-relational collections."""
    adapter = SQLFirestoreAdapter()
    
    # 1. Test announcements native CRUD
    ann_ref = adapter.collection("announcements")
    ann_id = "ann_101"
    ann_ref.document(ann_id).set({
        "title": "Welcome to Hackathon 2026",
        "message": "Submissions open now",
        "pinned": True
    })
    doc = ann_ref.document(ann_id).get()
    assert doc.exists
    assert doc.get("title") == "Welcome to Hackathon 2026"
    
    # Test stream filtering
    results = list(ann_ref.where("pinned", "==", True).stream())
    assert len(results) == 1
    assert results[0].id == ann_id
    
    # Test deletion
    ann_ref.document(ann_id).delete()
    assert not ann_ref.document(ann_id).get().exists

    # 2. Test push_subscriptions native CRUD
    push_ref = adapter.collection("push_subscriptions")
    sub_id = "user_sub_01"
    push_ref.document(sub_id).set({
        "endpoint": "https://fcm.googleapis.com/fcm/send/test_endpoint",
        "user_email": "student@snpsu.edu.in"
    })
    sub_doc = push_ref.document(sub_id).get()
    assert sub_doc.exists
    assert sub_doc.get("endpoint") == "https://fcm.googleapis.com/fcm/send/test_endpoint"
