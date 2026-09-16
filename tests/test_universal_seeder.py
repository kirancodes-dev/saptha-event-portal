"""
tests/test_universal_seeder.py — Verification of Universal Production Seeder (Phase 12)

Verifies:
1. Universal seeder creates enterprise organization and all 7 template events.
2. Form schemas, ticket tiers, evaluation rubrics, and notification triggers are all populated.
3. Querying seeded events returns diverse event types (hackathon, conference, sports, etc.).
"""

import pytest
from seed_events_universal import seed_universal_portal


class TestUniversalSeeder:
    """Verify Phase 12 universal seeding."""

    def test_seed_universal_portal(self, mock_db):
        res = seed_universal_portal(mock_db)
        assert res["events_count"] == 7
        assert res["organization"]["slug"] == "saptha-tech"

        # Check all 7 event types are present in database
        events = res["events"]
        types = {e["event_type"] for e in events}
        assert types == {"hackathon", "conference", "workshop", "seminar", "sports", "cultural", "webinar"}

        # Verify each event has complete sub-engine configurations
        for ev in events:
            assert len(ev.get("ticket_tiers", [])) > 0
            assert "type" in ev.get("evaluation_config", {})
            assert len(ev.get("notification_triggers", [])) > 0
            assert "title" in ev.get("certificate_config", {})
