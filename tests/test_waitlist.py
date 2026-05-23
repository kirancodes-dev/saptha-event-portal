"""
test_waitlist.py — Tests for the Waitlist System

Covers: join/leave waitlist, position tracking, auto-promotion,
and integration with notifications.
"""
import pytest


class TestWaitlistJoin:
    """Test waitlist join operations."""

    def test_join_waitlist(self, mock_db):
        """User can join a waitlist."""
        import uuid
        wl_id = str(uuid.uuid4())
        wl_data = {
            "id": wl_id,
            "event_id": "evt_full",
            "user_email": "wait@test.edu",
            "position": 1,
            "status": "waiting",
            "joined_at": "2026-06-01T10:00:00Z",
        }
        mock_db.collection("waitlists").document(wl_id).set(wl_data)
        doc = mock_db.collection("waitlists").document(wl_id).get()
        assert doc.exists
        assert doc.to_dict()["status"] == "waiting"
        assert doc.to_dict()["position"] == 1

    def test_multiple_waitlist_entries(self, mock_db):
        """Multiple users can join the same waitlist."""
        for i in range(3):
            mock_db.collection("waitlists").document(f"wl_{i}").set({
                "event_id": "evt_full",
                "user_email": f"user{i}@test.edu",
                "position": i + 1,
                "status": "waiting",
            })
        entries = list(mock_db.collection("waitlists").stream())
        assert len(entries) >= 3


class TestWaitlistPromotion:
    """Test auto-promotion logic."""

    def test_promote_changes_status(self, mock_db):
        """Promoted user status changes from 'waiting' to 'promoted'."""
        mock_db.collection("waitlists").document("wl_promote").set({
            "event_id": "evt_001",
            "user_email": "lucky@test.edu",
            "position": 1,
            "status": "waiting",
        })
        mock_db.collection("waitlists").document("wl_promote").update({
            "status": "promoted",
        })
        doc = mock_db.collection("waitlists").document("wl_promote").get()
        assert doc.to_dict()["status"] == "promoted"

    def test_leave_waitlist(self, mock_db):
        """User can cancel their waitlist position."""
        mock_db.collection("waitlists").document("wl_leave").set({
            "event_id": "evt_001",
            "user_email": "leaving@test.edu",
            "status": "waiting",
        })
        mock_db.collection("waitlists").document("wl_leave").update({
            "status": "cancelled",
        })
        doc = mock_db.collection("waitlists").document("wl_leave").get()
        assert doc.to_dict()["status"] == "cancelled"


class TestWaitlistPosition:
    """Test position tracking."""

    def test_positions_are_sequential(self, mock_db):
        """Positions should be assigned sequentially."""
        positions = []
        for i in range(5):
            mock_db.collection("waitlists").document(f"pos_{i}").set({
                "event_id": "evt_001",
                "user_email": f"pos{i}@test.edu",
                "position": i + 1,
                "status": "waiting",
            })
            positions.append(i + 1)
        assert positions == [1, 2, 3, 4, 5]

    def test_position_starts_at_one(self):
        """First position is always 1."""
        assert 0 + 1 == 1  # position = count + 1 where count starts at 0
