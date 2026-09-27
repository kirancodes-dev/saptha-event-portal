"""
tests/test_venues_and_calendar_e2e.py — End-to-End Tests for Venues, Calendar, Conflicts, Discovery & My Events
=============================================================================================================
Verifies all 6 pillars of the campus event tracking system:
1. Venues & Seeding: Campus -> Building -> Room Admin CRUD + seeding default venues.
2. Conflict Detection & Timezones: Overlapping confirmed bookings block, touching slots allowed,
   cancelled bookings do not block, Asia/Kolkata -> UTC conversion.
3. WorkflowEngine Guard: Overlapping room booking blocks event publishing and names clashing event.
4. University Calendar: month/week/list views, department-only visibility scoping, filters,
   single .ics export, and personal .ics feed.
5. Public Discovery: Search + filters (dept, type, mode, fee) respecting visibility scoping.
6. My Events for Students: Upcoming, Registered, Waitlisted, Attended, Certificates, Cancelled tabs.
7. Change Notifications: Venue/time changes and event cancellations notify registered attendees exactly once.

All tests go through the Flask test client.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
import pytest

from services_venue import (
    parse_to_utc,
    format_kolkata,
    slots_overlap,
    check_room_conflict,
    create_or_update_venue_booking,
    seed_default_venues,
)
from services_workflow import WorkflowEngine, WorkflowError


# ═══════════════════════════════════════════════════════════════════════════
# 1. VENUES SEED & ADMIN CRUD
# ═══════════════════════════════════════════════════════════════════════════

class TestVenuesAndAdminCRUD:
    """Test venue hierarchy management and admin CRUD through Flask test client."""

    def test_admin_venues_seed_endpoint(self, admin_client, mock_db):
        """Admin can seed default venues and operation is idempotent."""
        resp = admin_client.post("/admin/venues/seed", follow_redirects=True)
        assert resp.status_code == 200

        # Verify campus, buildings, and rooms created in mock_db
        campus_doc = mock_db.collection("campuses").document("campus-main").get()
        assert campus_doc.exists
        assert campus_doc.to_dict()["name"] == "Main Campus"

        rooms = list(mock_db.collection("rooms").stream())
        assert len(rooms) >= 6
        room_names = [r.to_dict().get("name") for r in rooms]
        assert "Main Auditorium" in room_names
        assert "Seminar Hall 1" in room_names

        # Calling seed again is idempotent (doesn't duplicate)
        resp2 = admin_client.post("/admin/venues/seed", follow_redirects=True)
        assert resp2.status_code == 200
        rooms_after = list(mock_db.collection("rooms").stream())
        assert len(rooms_after) == len(rooms)

    def test_admin_venues_listing_page_and_json(self, admin_client, mock_db):
        """Venues dashboard returns HTML and JSON listings."""
        seed_default_venues(mock_db)

        # HTML page view
        resp_html = admin_client.get("/admin/venues")
        assert resp_html.status_code == 200
        assert b"Campus Venues &amp; Room Bookings" in resp_html.data or b"Campus Venues & Room Bookings" in resp_html.data
        assert b"Main Auditorium" in resp_html.data

        # JSON view
        resp_json = admin_client.get("/admin/venues?format=json")
        assert resp_json.status_code == 200
        data = resp_json.get_json()
        assert "campuses" in data
        assert "rooms" in data
        assert len(data["rooms"]) >= 6

    def test_admin_venue_hierarchy_crud_operations(self, admin_client, mock_db):
        """Admin can create campus, building, room, edit room, and delete room."""
        # 1. Create Campus
        resp_c = admin_client.post(
            "/admin/venues/campus/create",
            data={"name": "North Campus", "address": "Yelahanka, Bangalore"},
            follow_redirects=True,
        )
        assert resp_c.status_code == 200
        campuses = list(mock_db.collection("campuses").stream())
        north_campus = [c for c in campuses if c.to_dict().get("name") == "North Campus"]
        assert len(north_campus) == 1
        campus_id = north_campus[0].id

        # 2. Create Building
        resp_b = admin_client.post(
            "/admin/venues/building/create",
            data={"campus_id": campus_id, "name": "Innovation Hub", "code": "IHUB"},
            follow_redirects=True,
        )
        assert resp_b.status_code == 200
        buildings = list(mock_db.collection("buildings").stream())
        ihub_bldg = [b for b in buildings if b.to_dict().get("code") == "IHUB"]
        assert len(ihub_bldg) == 1
        bldg_id = ihub_bldg[0].id

        # 3. Create Room
        resp_r = admin_client.post(
            "/admin/venues/room/create",
            data={
                "building_id": bldg_id,
                "name": "Robotics Arena",
                "room_number": "105",
                "capacity": "120",
                "type": "lab",
                "facilities": "wifi, projector, 3d_printers, power_strips",
            },
            follow_redirects=True,
        )
        assert resp_r.status_code == 200
        rooms = list(mock_db.collection("rooms").stream())
        arena = [r for r in rooms if r.to_dict().get("name") == "Robotics Arena"]
        assert len(arena) == 1
        room_id = arena[0].id
        arena_data = arena[0].to_dict()
        assert arena_data["capacity"] == 120
        assert "3d_printers" in arena_data.get("facilities_json", [])

        # 4. Edit Room
        resp_edit = admin_client.post(
            f"/admin/venues/room/{room_id}/edit",
            data={
                "building_id": bldg_id,
                "name": "Robotics & AI Arena",
                "room_number": "105",
                "capacity": "150",
                "type": "lab",
                "facilities": "wifi, projector, 3d_printers, gpu_cluster",
            },
            follow_redirects=True,
        )
        assert resp_edit.status_code == 200
        updated_room = mock_db.collection("rooms").document(room_id).get().to_dict()
        assert updated_room["name"] == "Robotics & AI Arena"
        assert updated_room["capacity"] == 150
        assert "gpu_cluster" in updated_room.get("facilities_json", [])

        # 5. Delete Room
        resp_del = admin_client.post(f"/admin/venues/room/{room_id}/delete", follow_redirects=True)
        assert resp_del.status_code == 200
        deleted_room = mock_db.collection("rooms").document(room_id).get()
        assert not deleted_room.exists

    def test_admin_venues_permission_guard(self, client, auth_client):
        """Unauthorized or non-admin users cannot access venues admin endpoints."""
        # Anonymous user
        resp_anon = client.get("/admin/venues")
        assert resp_anon.status_code in (302, 401, 403)

        # Regular student user
        resp_student = auth_client.get("/admin/venues")
        assert resp_student.status_code in (302, 403)


# ═══════════════════════════════════════════════════════════════════════════
# 2. CONFLICT DETECTION & TIMEZONES
# ═══════════════════════════════════════════════════════════════════════════

class TestConflictDetectionAndTimezones:
    """Test room booking conflict detection edge cases and Asia/Kolkata timezone handling."""

    def test_timezone_parsing_and_utc_storage(self):
        """Naive strings assumed Asia/Kolkata (+05:30) and converted to UTC."""
        ist_naive = "2026-10-15 10:00:00"
        utc_dt = parse_to_utc(ist_naive)
        assert utc_dt.tzinfo == timezone.utc
        # 10:00 IST is 04:30 UTC
        assert utc_dt.hour == 4
        assert utc_dt.minute == 30

        # format_kolkata converts back to IST display
        ist_str = format_kolkata(utc_dt)
        assert "10:00 AM" in ist_str or "10:00" in ist_str

    def test_slots_overlap_edge_cases(self):
        """Touching slots do NOT overlap; strictly overlapping intervals do."""
        t10_00 = parse_to_utc("2026-10-15 10:00:00")
        t12_00 = parse_to_utc("2026-10-15 12:00:00")
        t14_00 = parse_to_utc("2026-10-15 14:00:00")
        t11_00 = parse_to_utc("2026-10-15 11:00:00")
        t13_00 = parse_to_utc("2026-10-15 13:00:00")

        # Overlapping: 10-12 and 11-13
        assert slots_overlap(t10_00, t12_00, t11_00, t13_00) is True

        # Touching slots: 10-12 and 12-14 (Allowed, no clash!)
        assert slots_overlap(t10_00, t12_00, t12_00, t14_00) is False

        # Completely disjoint: 10-11 and 13-14
        assert slots_overlap(t10_00, t11_00, t13_00, t14_00) is False

    def test_check_room_conflict_scenarios(self, mock_db):
        """Confirmed bookings clash; touching slots and cancelled bookings do NOT clash."""
        room_id = "room-test-audit"
        mock_db.collection("rooms").document(room_id).set({
            "id": room_id,
            "name": "Audit Room A",
            "capacity": 200,
        })

        # Event 1 booking: 10:00 to 12:00 IST
        mock_db.collection("venue_bookings").document("book_01").set({
            "id": "book_01",
            "room_id": room_id,
            "event_id": "evt_conf_01",
            "start_time": "2026-10-15T04:30:00+00:00",  # 10:00 IST
            "end_time": "2026-10-15T06:30:00+00:00",    # 12:00 IST
            "status": "confirmed",
        })
        mock_db.collection("events").document("evt_conf_01").set({
            "id": "evt_conf_01",
            "title": "Quantum Computing Workshop",
            "status": "published",
        })

        # 1. Overlap (11:00 to 13:00 IST) -> CLASH!
        has_clash, clash = check_room_conflict(
            mock_db,
            room_id=room_id,
            start_time="2026-10-15 11:00:00",
            end_time="2026-10-15 13:00:00",
            exclude_event_id="evt_new_02",
        )
        assert has_clash is True
        assert "Quantum Computing Workshop" in clash["message"]

        # 2. Touching slot (12:00 to 14:00 IST) -> NO CLASH!
        has_clash, clash = check_room_conflict(
            mock_db,
            room_id=room_id,
            start_time="2026-10-15 12:00:00",
            end_time="2026-10-15 14:00:00",
            exclude_event_id="evt_new_03",
        )
        assert has_clash is False
        assert clash is None

        # 3. Different room (10:00 to 12:00 IST on room-diff) -> NO CLASH!
        has_clash, clash = check_room_conflict(
            mock_db,
            room_id="room-diff",
            start_time="2026-10-15 10:00:00",
            end_time="2026-10-15 12:00:00",
        )
        assert has_clash is False

        # 4. Cancelled booking does not block
        mock_db.collection("venue_bookings").document("book_01").update({"status": "cancelled"})
        has_clash, clash = check_room_conflict(
            mock_db,
            room_id=room_id,
            start_time="2026-10-15 11:00:00",
            end_time="2026-10-15 13:00:00",
        )
        assert has_clash is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. WORKFLOW ENGINE PUBLISH GUARD (BLOCKED ON CLASH)
# ═══════════════════════════════════════════════════════════════════════════

class TestWorkflowEnginePublishGuard:
    """Verify that room clashes block publishing via WorkflowEngine and Flask admin approval."""

    def test_publish_blocked_on_clash_via_flask_client(self, admin_client, mock_db):
        """Admin approve route fails when event has an overlapping room booking."""
        room_id = "room-sem-hall"
        mock_db.collection("rooms").document(room_id).set({
            "id": room_id,
            "name": "Seminar Hall 1",
            "capacity": 100,
        })

        # Event 1 already confirmed/published in room-sem-hall from 14:00 to 16:00 IST
        mock_db.collection("events").document("evt_live_10").set({
            "id": "evt_live_10",
            "title": "AI Ethics Seminar",
            "room_id": room_id,
            "status": "published",
            "organization_id": "default",
        })
        mock_db.collection("venue_bookings").document("book_live_10").set({
            "id": "book_live_10",
            "room_id": room_id,
            "event_id": "evt_live_10",
            "start_time": "2026-11-05T08:30:00+00:00",  # 14:00 IST
            "end_time": "2026-11-05T10:30:00+00:00",    # 16:00 IST
            "status": "confirmed",
        })

        # Event 2 in pending_approval with overlapping time 15:00 to 17:00 IST
        mock_db.collection("events").document("evt_clash_20").set({
            "id": "evt_clash_20",
            "title": "Cloud Computing Masterclass",
            "room_id": room_id,
            "start_datetime": "2026-11-05 15:00:00",
            "end_datetime": "2026-11-05 17:00:00",
            "status": "pending_approval",
            "organization_id": "default",
        })
        mock_db.collection("venue_bookings").document("book_clash_20").set({
            "id": "book_clash_20",
            "room_id": room_id,
            "event_id": "evt_clash_20",
            "start_time": "2026-11-05T09:30:00+00:00",  # 15:00 IST
            "end_time": "2026-11-05T11:30:00+00:00",    # 17:00 IST
            "status": "hold",
        })

        # Admin tries to approve and publish evt_clash_20 -> SHOULD BE BLOCKED
        resp = admin_client.post("/admin/events/approve/evt_clash_20", follow_redirects=True)
        assert resp.status_code == 200
        # Check that approval error was flashed naming the clashing event
        assert (b"Cannot publish event due to room booking conflict" in resp.data or
                b"AI Ethics Seminar" in resp.data or
                b"Approval error" in resp.data)

        # Event 2 status must remain pending_approval (NOT published)
        ev2_after = mock_db.collection("events").document("evt_clash_20").get().to_dict()
        assert ev2_after["status"] == "pending_approval"

        # Now cancel Event 1's booking
        mock_db.collection("venue_bookings").document("book_live_10").update({"status": "cancelled"})

        # Try approving again -> SHOULD NOW SUCCEED
        resp2 = admin_client.post("/admin/events/approve/evt_clash_20", follow_redirects=True)
        assert resp2.status_code == 200
        assert b"approved and published" in resp2.data

        # Event 2 status is now published
        ev2_published = mock_db.collection("events").document("evt_clash_20").get().to_dict()
        assert ev2_published["status"] == "published"


# ═══════════════════════════════════════════════════════════════════════════
# 4. UNIVERSITY CALENDAR & VISIBILITY SCOPING
# ═══════════════════════════════════════════════════════════════════════════

class TestUniversityCalendarAndVisibility:
    """Test calendar views, department visibility scoping, filters, and .ics feeds."""

    @pytest.fixture(autouse=True)
    def setup_calendar_data(self, mock_db):
        """Seed org units and events for calendar tests."""
        mock_db.collection("org_units").document("cse").set({
            "id": "cse", "name": "Computer Science", "slug": "cse"
        })
        mock_db.collection("org_units").document("ece").set({
            "id": "ece", "name": "Electronics", "slug": "ece"
        })

        # 1. Public Event
        mock_db.collection("events").document("ev_pub").set({
            "id": "ev_pub",
            "slug": "campus-hackathon-2026",
            "title": "Campus Hackathon 2026",
            "status": "published",
            "visibility": "public",
            "event_type": "hackathon",
            "mode": "offline",
            "fee": 0,
            "start_datetime": "2026-11-10T09:00:00+05:30",
            "end_datetime": "2026-11-10T17:00:00+05:30",
            "date": "2026-11-10",
            "venue": "Main Auditorium",
        })

        # 2. CSE Department-Only Event
        mock_db.collection("events").document("ev_cse").set({
            "id": "ev_cse",
            "slug": "cse-algo-symposium",
            "title": "CSE Algorithm Symposium",
            "status": "published",
            "visibility": "department",
            "org_unit_id": "cse",
            "event_type": "symposium",
            "mode": "offline",
            "fee": 50,
            "start_datetime": "2026-11-12T10:00:00+05:30",
            "end_datetime": "2026-11-12T13:00:00+05:30",
            "date": "2026-11-12",
            "venue": "CSE Seminar Hall",
        })

        # 3. ECE Department-Only Event
        mock_db.collection("events").document("ev_ece").set({
            "id": "ev_ece",
            "slug": "ece-robotics-expo",
            "title": "ECE Robotics Expo",
            "status": "published",
            "visibility": "department",
            "org_unit_id": "ece",
            "event_type": "expo",
            "mode": "online",
            "fee": 0,
            "start_datetime": "2026-11-15T14:00:00+05:30",
            "end_datetime": "2026-11-15T16:00:00+05:30",
            "date": "2026-11-15",
            "venue": "Online Webex",
        })

    def test_calendar_hides_department_events_from_unauthorized_viewers(self, client, mock_db):
        """Logged-out public visitors only see public events; department events are hidden."""
        resp = client.get("/api/calendar")
        assert resp.status_code == 200
        items = resp.get_json()
        ids = [item["id"] for item in items]
        assert "ev_pub" in ids
        assert "ev_cse" not in ids
        assert "ev_ece" not in ids

    def test_calendar_shows_matching_department_events_to_department_student(self, client, mock_db):
        """CSE student sees Public and CSE events, but ECE events are hidden."""
        mock_db.collection("users").document("cse_student@test.edu").set({
            "email": "cse_student@test.edu",
            "role": "Student",
            "department": "cse",
            "org_unit_id": "cse",
            "is_active": True,
        })
        with client.session_transaction() as sess:
            sess["user_id"] = "cse_student@test.edu"
            sess["role"] = "Student"
            sess["org_unit_id"] = "cse"
            sess["department"] = "cse"

        resp = client.get("/api/calendar")
        assert resp.status_code == 200
        items = resp.get_json()
        ids = [item["id"] for item in items]
        assert "ev_pub" in ids
        assert "ev_cse" in ids
        assert "ev_ece" not in ids

    def test_admin_sees_all_calendar_events(self, admin_client):
        """SuperAdmin sees events from all departments."""
        resp = admin_client.get("/api/calendar")
        assert resp.status_code == 200
        items = resp.get_json()
        ids = [item["id"] for item in items]
        assert "ev_pub" in ids
        assert "ev_cse" in ids
        assert "ev_ece" in ids

    def test_calendar_filters(self, admin_client):
        """Calendar filters for event_type, mode, fee, and dept."""
        # Filter by mode=online
        resp_online = admin_client.get("/api/calendar?mode=online")
        items_online = resp_online.get_json()
        assert len(items_online) == 1
        assert items_online[0]["id"] == "ev_ece"

        # Filter by fee=free
        resp_free = admin_client.get("/api/calendar?fee=free")
        free_ids = [item["id"] for item in resp_free.get_json()]
        assert "ev_pub" in free_ids
        assert "ev_ece" in free_ids
        assert "ev_cse" not in free_ids

        # Filter by dept=cse
        resp_dept = admin_client.get("/api/calendar?dept=cse")
        dept_ids = [item["id"] for item in resp_dept.get_json()]
        assert "ev_cse" in dept_ids
        assert "ev_ece" not in dept_ids

    def test_calendar_page_and_export_ics(self, client, auth_client, mock_db):
        """Calendar page renders full calendar and ICS exports function correctly."""
        # 1. UI Calendar page
        resp_page = client.get("/calendar")
        assert resp_page.status_code == 200
        assert b"dayGridMonth" in resp_page.data or b"fullcalendar" in resp_page.data or b"calendar" in resp_page.data

        # 2. Single Event .ics Download
        resp_ics = client.get("/events/campus-hackathon-2026/calendar.ics")
        assert resp_ics.status_code == 200
        assert resp_ics.content_type.startswith("text/calendar")
        ics_text = resp_ics.data.decode("utf-8")
        assert "BEGIN:VCALENDAR" in ics_text
        assert "SUMMARY:Campus Hackathon 2026" in ics_text
        assert "LOCATION:Main Auditorium" in ics_text
        assert "END:VCALENDAR" in ics_text

        # 3. Personal Calendar .ics Feed for logged-in user
        mock_db.collection("registrations").document("reg_personal").set({
            "id": "reg_personal",
            "event_id": "ev_pub",
            "lead_email": "student@test.edu",
            "status": "confirmed",
        })
        resp_feed = auth_client.get("/calendar/feed.ics")
        assert resp_feed.status_code == 200
        assert resp_feed.content_type.startswith("text/calendar")
        feed_text = resp_feed.data.decode("utf-8")
        assert "BEGIN:VCALENDAR" in feed_text
        assert "Campus Hackathon 2026" in feed_text


# ═══════════════════════════════════════════════════════════════════════════
# 5. PUBLIC DISCOVERY SEARCH & FILTERS
# ═══════════════════════════════════════════════════════════════════════════

class TestPublicDiscovery:
    """Test search and filter functionality on public listing route."""

    @pytest.fixture(autouse=True)
    def seed_events(self, mock_db):
        mock_db.collection("events").document("ev_disc_1").set({
            "id": "ev_disc_1",
            "title": "Python for Data Science",
            "description": "Learn pandas and numpy",
            "status": "active",
            "visibility": "public",
            "event_type": "workshop",
            "mode": "online",
            "fee": 0,
            "date": "2026-11-20",
        })
        mock_db.collection("events").document("ev_disc_2").set({
            "id": "ev_disc_2",
            "title": "Flutter Mobile Bootcamp",
            "description": "Cross platform app development",
            "status": "active",
            "visibility": "public",
            "event_type": "bootcamp",
            "mode": "offline",
            "fee": 200,
            "date": "2026-11-25",
        })

    def test_search_and_filters_on_public_home(self, client):
        """Public homepage filters by query keyword, type, mode, and fee."""
        # Search query
        resp_q = client.get("/?q=Python&format=json")
        assert resp_q.status_code == 200
        data_q = resp_q.get_json()
        assert len(data_q["events"]) == 1
        assert data_q["events"][0]["id"] == "ev_disc_1"

        # Mode filter: offline
        resp_mode = client.get("/?mode=offline&format=json")
        assert resp_mode.status_code == 200
        data_mode = resp_mode.get_json()
        assert any(e["id"] == "ev_disc_2" for e in data_mode["events"])
        assert not any(e["id"] == "ev_disc_1" for e in data_mode["events"])

        # Fee filter: free
        resp_free = client.get("/?fee=free&format=json")
        assert resp_free.status_code == 200
        data_free = resp_free.get_json()
        assert any(e["id"] == "ev_disc_1" for e in data_free["events"])
        assert not any(e["id"] == "ev_disc_2" for e in data_free["events"])


# ═══════════════════════════════════════════════════════════════════════════
# 6. MY EVENTS FOR STUDENTS (TABS)
# ═══════════════════════════════════════════════════════════════════════════

class TestMyEventsTabs:
    """Test student My Events tabs: Upcoming, Registered, Waitlisted, Attended, Certificates, Cancelled."""

    @pytest.fixture(autouse=True)
    def seed_student_records(self, mock_db):
        student_email = "student@test.edu"
        now_dt = datetime.now(timezone.utc)
        future_dt = (now_dt + timedelta(days=10)).strftime("%Y-%m-%d")
        past_dt = (now_dt - timedelta(days=10)).strftime("%Y-%m-%d")

        # 1. Upcoming Event & Registration
        mock_db.collection("events").document("ev_up").set({
            "id": "ev_up", "title": "Upcoming AI Summit", "date": future_dt, "status": "published"
        })
        mock_db.collection("registrations").document("reg_up").set({
            "id": "reg_up", "event_id": "ev_up", "lead_email": student_email, "status": "confirmed"
        })

        # 2. Waitlisted Event & Registration
        mock_db.collection("events").document("ev_wait").set({
            "id": "ev_wait", "title": "Overbooked Cloud Workshop", "date": future_dt, "status": "published"
        })
        mock_db.collection("registrations").document("reg_wait").set({
            "id": "reg_wait", "event_id": "ev_wait", "lead_email": student_email, "status": "waitlist"
        })

        # 3. Attended Event & Registration (has checkin record)
        mock_db.collection("events").document("ev_att").set({
            "id": "ev_att", "title": "Cybersecurity Conclave", "date": past_dt, "status": "completed"
        })
        mock_db.collection("registrations").document("reg_att").set({
            "id": "reg_att", "event_id": "ev_att", "lead_email": student_email, "status": "confirmed", "checked_in": True
        })
        mock_db.collection("checkins").document("chk_att").set({
            "id": "chk_att", "event_id": "ev_att", "registration_id": "reg_att", "attendee_email": student_email
        })

        # 4. Certificates Record
        mock_db.collection("certificates").document("cert_01").set({
            "id": "cert_01",
            "event_id": "ev_att",
            "event_title": "Cybersecurity Conclave",
            "recipient_email": student_email,
            "recipient_name": "Test Student",
            "certificate_url": "https://example.com/certs/cert_01.pdf",
            "issued_at": past_dt,
        })

        # 5. Cancelled Registration
        mock_db.collection("events").document("ev_canc").set({
            "id": "ev_canc", "title": "Robo Wars", "date": future_dt, "status": "published"
        })
        mock_db.collection("registrations").document("reg_canc").set({
            "id": "reg_canc", "event_id": "ev_canc", "lead_email": student_email, "status": "cancelled"
        })

    def test_my_events_api_categorizes_into_correct_tabs(self, auth_client):
        """GET /participant/api/my_events returns registrations accurately grouped in 6 tabs."""
        resp = auth_client.get("/participant/api/my_events")
        assert resp.status_code == 200
        data = resp.get_json()

        assert "upcoming" in data
        assert "registered" in data
        assert "waitlisted" in data
        assert "attended" in data
        assert "certificates" in data
        assert "cancelled" in data

        # Upcoming tab has ev_up
        up_event_ids = [item.get("event_id") for item in data["upcoming"]]
        assert "ev_up" in up_event_ids

        # Waitlisted tab has ev_wait
        wait_event_ids = [item.get("event_id") for item in data["waitlisted"]]
        assert "ev_wait" in wait_event_ids

        # Attended tab has ev_att
        att_event_ids = [item.get("event_id") for item in data["attended"]]
        assert "ev_att" in att_event_ids

        # Certificates tab has cert_01
        cert_ids = [item.get("id") for item in data["certificates"]]
        assert "cert_01" in cert_ids

        # Cancelled tab has ev_canc
        canc_event_ids = [item.get("event_id") for item in data["cancelled"]]
        assert "ev_canc" in canc_event_ids

    def test_my_events_html_page_renders_all_tabs(self, auth_client):
        """GET /participant/my_events renders the 6 tab navigation bar."""
        resp = auth_client.get("/participant/my_events")
        assert resp.status_code == 200
        assert b"Upcoming" in resp.data
        assert b"Registered" in resp.data
        assert b"Waitlisted" in resp.data
        assert b"Attended" in resp.data
        assert b"Certificates" in resp.data
        assert b"Cancelled" in resp.data


# ═══════════════════════════════════════════════════════════════════════════
# 7. CHANGE NOTIFICATIONS (EXACTLY ONCE PER PARTICIPANT)
# ═══════════════════════════════════════════════════════════════════════════

class TestChangeNotifications:
    """Test that event changes and cancellations notify participants exactly once."""

    def test_venue_and_time_change_notifies_attendees_exactly_once(self, client, mock_db):
        """Updating event room/venue and date via SPOC triggers notification exactly once per attendee."""
        event_id = "ev_notif_test"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Full Stack Dev Meetup",
            "date": "2026-12-01",
            "venue": "Old Room 101",
            "room_id": "room-101",
            "spoc_id": "spoc@test.edu",
            "spoc_email": "spoc@test.edu",
            "status": "published",
        })

        # Add 2 distinct participants + 1 duplicate registration for participant 1
        mock_db.collection("registrations").document("reg_p1").set({
            "id": "reg_p1", "event_id": event_id, "lead_email": "alice@student.edu", "lead_name": "Alice", "status": "confirmed"
        })
        mock_db.collection("registrations").document("reg_p1_dup").set({
            "id": "reg_p1_dup", "event_id": event_id, "lead_email": "alice@student.edu", "lead_name": "Alice", "status": "confirmed"
        })
        mock_db.collection("registrations").document("reg_p2").set({
            "id": "reg_p2", "event_id": event_id, "lead_email": "bob@student.edu", "lead_name": "Bob", "status": "confirmed"
        })

        # Log in as SPOC
        with client.session_transaction() as sess:
            sess["user_id"] = "spoc@test.edu"
            sess["role"] = "ClubSPOC"
            sess["name"] = "Test SPOC"

        # Update event via SPOC edit endpoint
        resp = client.post(
            f"/spoc/edit_event/{event_id}",
            data={
                "title": "Full Stack Dev Meetup",
                "venue": "Main Auditorium",
                "date": "2026-12-05",
                "time": "14:00",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        # Check notifications generated in mock_db (routes_notifications_v2 stores in notifications_v2)
        notifs = list(mock_db.collection("notifications_v2").stream()) + list(mock_db.collection("notifications").stream())
        alice_notifs = [n for n in notifs if n.to_dict().get("user_email") == "alice@student.edu"]
        bob_notifs = [n for n in notifs if n.to_dict().get("user_email") == "bob@student.edu"]

        # Exactly once per participant
        assert len(alice_notifs) == 1
        assert len(bob_notifs) == 1
        assert "Main Auditorium" in alice_notifs[0].to_dict().get("message", "")

    def test_event_cancellation_notifies_attendees_exactly_once(self, mock_db):
        """Cancelling an event sends cancellation notifications exactly once per participant."""
        event_id = "ev_cancel_test"
        mock_db.collection("events").document(event_id).set({
            "id": event_id,
            "title": "Annual Sports Fest",
            "date": "2026-12-15",
            "venue": "Campus Grounds",
            "status": "published",
        })

        mock_db.collection("registrations").document("reg_c1").set({
            "id": "reg_c1", "event_id": event_id, "lead_email": "charlie@student.edu", "lead_name": "Charlie", "status": "confirmed"
        })
        mock_db.collection("registrations").document("reg_c1_dup").set({
            "id": "reg_c1_dup", "event_id": event_id, "lead_email": "charlie@student.edu", "lead_name": "Charlie", "status": "confirmed"
        })

        # Cancel event via WorkflowEngine
        WorkflowEngine.transition_event(
            mock_db,
            event_id=event_id,
            target_state="cancelled",
            actor_id="admin@saptha.org",
            force=True,
        )

        notifs = list(mock_db.collection("notifications_v2").stream()) + list(mock_db.collection("notifications").stream())
        charlie_notifs = [n for n in notifs if n.to_dict().get("user_email") == "charlie@student.edu"]
        assert len(charlie_notifs) == 1
        assert "cancelled" in charlie_notifs[0].to_dict().get("message", "").lower()
