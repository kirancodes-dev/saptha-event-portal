"""
test_event_engine.py — Comprehensive Tests for Universal Event Engine (Phase 2)

Covers:
- Slug generation and collision resolution
- Universal EventService (creation, retrieval by slug and id, listing)
- Event cloning (deep config clone without copying attendees/payments)
- Dual-engine persistence for Organization and Ticket entities
- Public /events/<slug> routing
"""
import pytest
from services_event import EventService, generate_event_slug


class TestSlugGeneration:
    def test_basic_slug(self):
        slug = generate_event_slug("Global Tech Summit 2026")
        assert slug == "global-tech-summit-2026"

    def test_special_characters_sanitized(self):
        slug = generate_event_slug("AI & ML Hackathon #1 (Bengaluru!)")
        assert slug == "ai-ml-hackathon-1-bengaluru"

    def test_empty_string_fallback(self):
        slug = generate_event_slug("")
        assert slug.startswith("event-")

    def test_uniqueness_resolution(self):
        existing = {"hackathon-2026", "hackathon-2026-1"}
        slug = generate_event_slug("Hackathon 2026", lambda s: s in existing)
        assert slug == "hackathon-2026-2"


class TestEventServiceOperations:
    def test_create_universal_event(self, mock_db):
        event = EventService.create_event(
            mock_db,
            title="International Robotics Expo",
            description="Exhibition of cutting edge robotics.",
            category="Exhibition",
            event_type="conference",
            event_mode="hybrid",
            venue="Hall 3, Convention Center",
            date_str="2026-11-20",
            capacity=500,
            pricing_type="paid",
            fee=499.0,
            currency="INR",
            custom_fields=[
                {"id": "dietary", "label": "Dietary Preference", "type": "dropdown", "required": False}
            ]
        )

        assert event["id"] is not None
        assert event["title"] == "International Robotics Expo"
        assert event["slug"] == "international-robotics-expo"
        assert event["event_type"] == "conference"
        assert event["event_mode"] == "hybrid"
        assert event["capacity"] == 500
        assert event["fee"] == 499.0
        assert len(event["workflow_config"]) > 0
        assert len(event["ticket_tiers"]) > 0

    def test_get_event_by_slug(self, mock_db):
        created = EventService.create_event(
            mock_db,
            title="Design Thinking Workshop",
            event_type="workshop",
            event_mode="offline",
        )
        fetched = EventService.get_event_by_slug(mock_db, "design-thinking-workshop")
        assert fetched is not None
        assert fetched["id"] == created["id"]
        assert fetched["title"] == "Design Thinking Workshop"

    def test_get_nonexistent_slug_returns_none(self, mock_db):
        fetched = EventService.get_event_by_slug(mock_db, "nonexistent-event-slug")
        assert fetched is None

    def test_event_cloning(self, mock_db):
        # Create original event
        original = EventService.create_event(
            mock_db,
            title="Annual Coding Fest 2026",
            description="Annual coding championship.",
            category="Technical",
            event_type="hackathon",
            date_str="2026-10-01",
            capacity=300,
            custom_fields=[{"id": "github", "label": "GitHub Profile", "type": "text"}]
        )

        # Clone event for 2027
        cloned = EventService.clone_event(
            mock_db,
            source_event_id=original["id"],
            new_title="Annual Coding Fest 2027",
            new_date="2027-10-01",
            actor_email="admin@sapthaevent.com",
        )

        assert cloned is not None
        assert cloned["id"] != original["id"]
        assert cloned["title"] == "Annual Coding Fest 2027"
        assert cloned["date"] == "2027-10-01"
        assert cloned["event_type"] == "hackathon"
        assert cloned["capacity"] == 300
        assert cloned["registration_count"] == 0  # Does NOT copy attendees


class TestPublicSlugRoute:
    def test_slug_route_renders_event(self, client, mock_db):
        event = EventService.create_event(
            mock_db,
            title="FinTech Innovation Summit",
            event_type="conference",
            event_mode="hybrid",
        )
        resp = client.get(f"/events/{event['slug']}")
        # Should resolve and render the event page (200 OK)
        assert resp.status_code == 200
        assert b"FinTech Innovation Summit" in resp.data

    def test_nonexistent_slug_returns_404(self, client, mock_db):
        resp = client.get("/events/completely-fake-event-slug")
        assert resp.status_code == 404


class TestDBAdapterParity:
    def test_sql_adapter_organization_crud(self):
        from db_adapter import SQLFirestoreAdapter
        adapter = SQLFirestoreAdapter()
        
        org_id = "test-org-123"
        org_data = {
            "name": "MIT Institute",
            "slug": "mit-inst",
            "domain": "mit.edu",
            "plan": "pro",
            "primary_color": "#1a2557",
            "accent_color": "#f37021",
            "is_active": True,
            "settings": {"max_events": 50},
        }
        
        # Write organization
        adapter.collection("organizations").document(org_id).set(org_data)
        
        # Read back
        doc = adapter.collection("organizations").document(org_id).get()
        assert doc.exists is True
        fetched = doc.to_dict()
        assert fetched["name"] == "MIT Institute"
        assert fetched["slug"] == "mit-inst"
        assert fetched["plan"] == "pro"

    def test_sql_adapter_unmapped_collection_fallback(self):
        from db_adapter import SQLFirestoreAdapter
        adapter = SQLFirestoreAdapter()
        
        # Custom collection not in predefined models
        coll_name = "test_custom_metadata"
        doc_id = "meta-abc"
        data = {"key": "api_quota", "value": 10000}
        
        # Write to fallback
        adapter.collection(coll_name).document(doc_id).set(data)
        
        # Read back
        doc = adapter.collection(coll_name).document(doc_id).get()
        assert doc.exists is True
        assert doc.to_dict()["value"] == 10000

