"""
tests/test_seminar_e2e.py — End-to-end tests for the Universal Event Engine via Flask test client.

Focuses on the non-competition "seminar" lifecycle and guards:
  1. SPOC creates event from "seminar" template (seeds workflow_config, evaluation_config, form).
  2. Sequential state progression via WorkflowEngine guards (cannot skip states).
  3. Cannot register until event state is registration_open.
  4. Capacity limits and waitlisting: when event reaches capacity, next registration goes to waitlist.
  5. Promotion upon cancellation: when a confirmed attendee cancels, waitlisted user is promoted and ticket is issued.
  6. Registering does NOT imply attendance: registration and ticket records are separate, attendance is 'Pending'.
  7. Door check-in: staff scans ticket QR token -> marks attendance 'Present', updates ticket to checked_in.
  8. Certificate guards:
     - Certificate NOT issued before event completion (blocked when event is in progress/registration_open).
     - Certificate NOT issued to no-shows (even after event completes).
     - Feedback gate: attendee must provide feedback before viewing/downloading certificate.
     - Attended user who provides feedback receives certificate successfully.
"""

import json
import pytest
from routes_ticket import generate_ticket_token


def _setup_users(mock_db):
    """Seed test users for SPOC and participants."""
    mock_db.collection("users").document("spoc@saptha.edu").set({
        "name": "Dr. Seminar SPOC",
        "email": "spoc@saptha.edu",
        "role": "ClubSPOC",
        "category": "General",
        "is_active": True,
    })
    mock_db.collection("users").document("alice@saptha.edu").set({
        "name": "Alice Cooper",
        "email": "alice@saptha.edu",
        "role": "Student",
        "category": "General",
        "is_active": True,
    })
    mock_db.collection("users").document("bob@saptha.edu").set({
        "name": "Bob Marley",
        "email": "bob@saptha.edu",
        "role": "Student",
        "category": "General",
        "is_active": True,
    })
    mock_db.collection("users").document("charlie@saptha.edu").set({
        "name": "Charlie Chaplin",
        "email": "charlie@saptha.edu",
        "role": "Student",
        "category": "General",
        "is_active": True,
    })


def test_seminar_full_lifecycle_and_certificate_guards(client, mock_db):
    """
    Full lifecycle test:
    Create Seminar -> Publish -> Open Registration -> Register -> Separate Ticket & Registration
    -> Guard: No cert before completion -> Check In at Door -> Complete Event
    -> Guard: No cert for no-show -> Guard: Feedback required -> Submit Feedback -> Cert Granted!
    """
    _setup_users(mock_db)

    # 1. SPOC logs in and creates a Seminar event
    with client.session_transaction() as sess:
        sess["user_id"] = "spoc@saptha.edu"
        sess["role"] = "ClubSPOC"
        sess["name"] = "Dr. Seminar SPOC"

    create_data = {
        "title": "Universal AI Architecture Seminar",
        "category": "Technical",
        "description": "Comprehensive seminar on universal event architecture",
        "rules": "Be on time and respectful.",
        "date": "2026-11-20",
        "time": "10:00",
        "reg_deadline": "2026-11-19",
        "venue": "Auditorium Hall B",
        "template_id": "seminar",
        "max_participants": "10",
        "reg_fee": "0",
        "coordinators": "spoc@saptha.edu",
    }
    resp = client.post("/spoc/create_event", data=create_data, follow_redirects=False)
    assert resp.status_code in (301, 302)

    # Find the created event
    events = list(mock_db.collection("events").stream())
    event_doc = next((e for e in events if e.to_dict().get("title") == "Universal AI Architecture Seminar"), None)
    assert event_doc is not None, "Seminar event was not created in DB"
    event_id = event_doc.id
    event_data = event_doc.to_dict()

    # Validate Seminar seeding properties
    assert event_data.get("status") == "draft"
    assert event_data.get("event_type") == "seminar"
    assert event_data.get("is_team_event") is False
    assert event_data.get("capacity") == 10
    assert "workflow_config" in event_data
    workflow_rules = event_data["workflow_config"].get("rules", {})
    assert workflow_rules.get("require_feedback_for_certificate") is True

    # Verify template form was seeded
    form_doc = mock_db.collection("event_forms").document(event_id).get()
    assert form_doc.exists
    assert len(form_doc.to_dict().get("fields", [])) > 0

    # 2. Cannot skip states: try going directly from draft to completed
    skip_resp = client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "completed"}, follow_redirects=True)
    ev_check = mock_db.collection("events").document(event_id).get().to_dict()
    assert ev_check.get("status") == "draft", "State skipping guard failed; event should remain in draft"

    # Try registering while in draft (should be blocked)
    with client.session_transaction() as sess:
        sess.clear()

    reg_attempt = client.post(f"/forms/submit/{event_id}", data={
        "full_name": "Alice Cooper",
        "email": "alice@saptha.edu",
        "phone": "9999999999",
        "usn": "1SP21CS001",
        "college_or_company": "Saptha Institute",
    }, follow_redirects=True)
    assert b"Registration Closed" in reg_attempt.data or b"Registration is closed" in reg_attempt.data

    # 3. SPOC advances draft -> published
    with client.session_transaction() as sess:
        sess["user_id"] = "spoc@saptha.edu"
        sess["role"] = "ClubSPOC"
        sess["name"] = "Dr. Seminar SPOC"

    pub_resp = client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "published"}, follow_redirects=True)
    assert mock_db.collection("events").document(event_id).get().to_dict()["status"] == "published"

    # Cannot register while in published
    with client.session_transaction() as sess:
        sess.clear()

    reg_attempt = client.post(f"/forms/submit/{event_id}", data={
        "full_name": "Alice Cooper",
        "email": "alice@saptha.edu",
        "phone": "9999999999",
        "usn": "1SP21CS001",
        "college_or_company": "Saptha Institute",
    }, follow_redirects=True)
    assert b"Registration Closed" in reg_attempt.data or b"Registration is closed" in reg_attempt.data

    # 4. SPOC advances published -> registration_open
    with client.session_transaction() as sess:
        sess["user_id"] = "spoc@saptha.edu"
        sess["role"] = "ClubSPOC"
        sess["name"] = "Dr. Seminar SPOC"

    open_resp = client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "registration_open"}, follow_redirects=True)
    assert mock_db.collection("events").document(event_id).get().to_dict()["status"] == "registration_open"

    # 5. Alice registers (Attendee)
    alice_reg_resp = client.post(f"/forms/submit/{event_id}", data={
        "full_name": "Alice Cooper",
        "email": "alice@saptha.edu",
        "phone": "9999999999",
        "usn": "1SP21CS001",
        "college_or_company": "Saptha Institute",
        "ticket_tier": "Standard",
    }, follow_redirects=True)
    assert alice_reg_resp.status_code == 200

    alice_regs = list(mock_db.collection("registrations").where("event_id", "==", event_id).where("lead_email", "==", "alice@saptha.edu").stream())
    assert len(alice_regs) == 1
    alice_reg = alice_regs[0].to_dict()
    alice_reg_id = alice_regs[0].id
    assert alice_reg["status"] == "Confirmed"

    # Registering must NOT imply attendance!
    assert alice_reg.get("attendance") == "Pending"
    assert alice_reg.get("ticket_id") is not None

    # Separate ticket record exists
    ticket_doc = mock_db.collection("tickets").document(alice_reg["ticket_id"]).get()
    assert ticket_doc.exists
    ticket_data = ticket_doc.to_dict()
    assert ticket_data.get("status") == "active"
    assert ticket_data.get("checked_in") is False

    # 6. Charlie registers (No-show participant)
    charlie_reg_resp = client.post(f"/forms/submit/{event_id}", data={
        "full_name": "Charlie Chaplin",
        "email": "charlie@saptha.edu",
        "phone": "8888888888",
        "usn": "1SP21CS002",
        "college_or_company": "Saptha Institute",
        "ticket_tier": "Standard",
    }, follow_redirects=True)
    assert charlie_reg_resp.status_code == 200
    charlie_regs = list(mock_db.collection("registrations").where("event_id", "==", event_id).where("lead_email", "==", "charlie@saptha.edu").stream())
    charlie_reg_id = charlie_regs[0].id
    assert charlie_regs[0].to_dict().get("attendance") == "Pending"

    # 7. Certificate Guard: Certificate NOT issued before event completion
    with client.session_transaction() as sess:
        sess["user_id"] = "alice@saptha.edu"
        sess["role"] = "Student"
        sess["name"] = "Alice Cooper"

    cert_early = client.get(f"/participant/certificate/{alice_reg_id}", follow_redirects=True)
    assert b"Certificates are only" in cert_early.data
    assert b"completed" in cert_early.data

    # 8. Staff door check-in: Alice presents ticket token
    # Switch session to SPOC (staff)
    with client.session_transaction() as sess:
        sess["user_id"] = "spoc@saptha.edu"
        sess["role"] = "ClubSPOC"
        sess["name"] = "Dr. Seminar SPOC"

    alice_token = generate_ticket_token(alice_reg_id, event_id, "Alice Cooper")
    # GET verify validates read-only
    get_verify = client.get(f"/ticket/verify/{alice_token}")
    assert get_verify.status_code == 200
    assert b"Ticket Valid" in get_verify.data or b"Ticket is valid" in get_verify.data

    # Attendance still Pending before POST
    assert mock_db.collection("registrations").document(alice_reg_id).get().to_dict().get("attendance") == "Pending"

    # POST verify marks attendance
    post_verify = client.post(f"/ticket/verify/{alice_token}")
    assert post_verify.status_code == 200
    assert b"Entry Granted" in post_verify.data or b"Entry granted" in post_verify.data

    # Verify separate records updated
    updated_alice_reg = mock_db.collection("registrations").document(alice_reg_id).get().to_dict()
    assert updated_alice_reg.get("attendance") == "Present"
    assert updated_alice_reg.get("checkin_time") is not None

    updated_ticket = mock_db.collection("tickets").document(alice_reg["ticket_id"]).get().to_dict()
    assert updated_ticket.get("checked_in") is True
    assert updated_ticket.get("status") == "checked_in"

    # Charlie never checked in (remains Pending)
    assert mock_db.collection("registrations").document(charlie_reg_id).get().to_dict().get("attendance") == "Pending"

    # 9. SPOC advances event to completed (registration_open -> registration_closed -> in_progress -> completed)
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "registration_closed"})
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "in_progress"})
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "completed"})
    assert mock_db.collection("events").document(event_id).get().to_dict()["status"] == "completed"

    # 10. Certificate Guard: No-show (Charlie) denied certificate even after event is completed
    with client.session_transaction() as sess:
        sess["user_id"] = "charlie@saptha.edu"
        sess["role"] = "Student"
        sess["name"] = "Charlie Chaplin"

    charlie_cert = client.get(f"/participant/certificate/{charlie_reg_id}", follow_redirects=True)
    assert b"Certificates are only issued to students who attended" in charlie_cert.data

    # 11. Certificate Guard: Attended participant (Alice) prompted for feedback first
    with client.session_transaction() as sess:
        sess["user_id"] = "alice@saptha.edu"
        sess["role"] = "Student"
        sess["name"] = "Alice Cooper"

    alice_cert_before_fb = client.get(f"/participant/certificate/{alice_reg_id}", follow_redirects=False)
    # Redirects to feedback page
    assert alice_cert_before_fb.status_code in (301, 302)
    assert f"/participant/feedback/{alice_reg_id}" in alice_cert_before_fb.headers.get("Location", "")

    # 12. Alice submits feedback
    fb_resp = client.post(f"/participant/feedback/{alice_reg_id}", data={
        "rating": "5",
        "comments": "Brilliant architecture seminar, learned so much!",
        "tags": ["Well organised", "Inspiring"],
    }, follow_redirects=True)
    assert fb_resp.status_code == 200

    # Verify feedback was stored
    alice_reg_after_fb = mock_db.collection("registrations").document(alice_reg_id).get().to_dict()
    assert alice_reg_after_fb.get("feedback") is not None
    assert alice_reg_after_fb["feedback"]["rating"] == 5

    # 13. Alice requests certificate after feedback -> Successfully issued!
    final_cert_resp = client.get(f"/participant/certificate/{alice_reg_id}")
    assert final_cert_resp.status_code == 200
    assert b"Certificate of Participation" in final_cert_resp.data or b"CERTIFICATE" in final_cert_resp.data
    assert b"Alice Cooper" in final_cert_resp.data
    assert b"Universal AI Architecture Seminar" in final_cert_resp.data


def test_capacity_waitlist_and_promotion_guard(client, mock_db):
    """
    Capacity & waitlist lifecycle:
    1. Seminar created with capacity = 1.
    2. Event opened for registration.
    3. Alice registers -> Confirmed, ticket issued.
    4. Bob registers -> Event full, placed on waitlist (position 1, no ticket).
    5. Alice cancels registration -> Bob is promoted from waitlist to Confirmed, ticket issued.
    """
    _setup_users(mock_db)

    # SPOC creates seminar with capacity = 1
    with client.session_transaction() as sess:
        sess["user_id"] = "spoc@saptha.edu"
        sess["role"] = "ClubSPOC"
        sess["name"] = "Dr. Seminar SPOC"

    client.post("/spoc/create_event", data={
        "title": "Intimate Workshop on Quantum AI",
        "category": "Technical",
        "description": "Limited seats masterclass",
        "rules": "Laptops required",
        "date": "2026-11-25",
        "time": "14:00",
        "reg_deadline": "2026-11-24",
        "venue": "Lab 3",
        "template_id": "workshop",
        "max_participants": "1",
        "reg_fee": "0",
        "coordinators": "spoc@saptha.edu",
    })

    events = list(mock_db.collection("events").stream())
    event_doc = next((e for e in events if e.to_dict().get("title") == "Intimate Workshop on Quantum AI"), None)
    event_id = event_doc.id

    # SPOC transitions: draft -> published -> registration_open
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "published"})
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "registration_open"})

    # Alice registers -> Confirmed
    client.post(f"/forms/submit/{event_id}", data={
        "full_name": "Alice Cooper",
        "email": "alice@saptha.edu",
        "phone": "9999999999",
        "usn": "1SP21CS001",
        "experience_level": "Intermediate (1-2 years)",
        "laptop_os": "macOS",
    })

    alice_regs = list(mock_db.collection("registrations").where("event_id", "==", event_id).where("lead_email", "==", "alice@saptha.edu").stream())
    assert len(alice_regs) == 1
    alice_reg_id = alice_regs[0].id
    assert alice_regs[0].to_dict().get("status") == "Confirmed"
    assert alice_regs[0].to_dict().get("ticket_id") is not None

    # Bob registers -> Capacity is 1 and registration_count is 1 -> Bob goes to waitlist
    bob_resp = client.post(f"/forms/submit/{event_id}", data={
        "full_name": "Bob Marley",
        "email": "bob@saptha.edu",
        "phone": "7777777777",
        "usn": "1SP21CS003",
        "experience_level": "Complete Beginner",
        "laptop_os": "macOS",
    }, follow_redirects=True)
    assert b"waitlist" in bob_resp.data or b"joined the waitlist" in bob_resp.data

    # Bob has NO confirmed registration yet
    bob_regs = list(mock_db.collection("registrations").where("event_id", "==", event_id).where("lead_email", "==", "bob@saptha.edu").stream())
    assert len(bob_regs) == 0

    # Bob IS in waitlists collection
    waitlist_entries = list(mock_db.collection("waitlists").where("event_id", "==", event_id).where("email", "==", "bob@saptha.edu").stream())
    assert len(waitlist_entries) == 1
    assert waitlist_entries[0].to_dict().get("status") == "waiting"
    assert waitlist_entries[0].to_dict().get("position") == 1

    # Alice cancels registration
    with client.session_transaction() as sess:
        sess["user_id"] = "alice@saptha.edu"
        sess["role"] = "Student"
        sess["name"] = "Alice Cooper"

    cancel_resp = client.post(f"/participant/cancel/{alice_reg_id}", follow_redirects=True)
    assert cancel_resp.status_code == 200

    # Alice is marked cancelled
    assert mock_db.collection("registrations").document(alice_reg_id).get().to_dict().get("status") == "Cancelled"

    # Bob has now been promoted from the waitlist
    promoted_entries = list(mock_db.collection("waitlists").where("event_id", "==", event_id).where("email", "==", "bob@saptha.edu").stream())
    assert promoted_entries[0].to_dict().get("status") == "promoted"

    # Bob now has a Confirmed registration and a Ticket
    bob_promoted_regs = list(mock_db.collection("registrations").where("event_id", "==", event_id).where("lead_email", "==", "bob@saptha.edu").stream())
    assert len(bob_promoted_regs) == 1
    bob_reg = bob_promoted_regs[0].to_dict()
    assert bob_reg.get("status") == "Confirmed"
    assert bob_reg.get("ticket_id") is not None

    # Ticket is active
    bob_ticket = mock_db.collection("tickets").document(bob_reg["ticket_id"]).get().to_dict()
    assert bob_ticket.get("status") == "active"
    assert bob_ticket.get("checked_in") is False


def test_workflow_state_transition_guards(client, mock_db):
    """
    Test that invalid state transitions are guarded and rejected:
    draft cannot jump to completed or in_progress.
    """
    _setup_users(mock_db)

    with client.session_transaction() as sess:
        sess["user_id"] = "spoc@saptha.edu"
        sess["role"] = "ClubSPOC"
        sess["name"] = "Dr. Seminar SPOC"

    client.post("/spoc/create_event", data={
        "title": "Strict State Seminar",
        "category": "Technical",
        "description": "Testing state machine transitions",
        "rules": "No state skipping",
        "date": "2026-11-30",
        "time": "11:00",
        "reg_deadline": "2026-11-29",
        "venue": "Hall C",
        "template_id": "seminar",
        "max_participants": "50",
        "reg_fee": "0",
        "coordinators": "spoc@saptha.edu",
    })

    events = list(mock_db.collection("events").stream())
    event_doc = next((e for e in events if e.to_dict().get("title") == "Strict State Seminar"), None)
    event_id = event_doc.id

    assert event_doc.to_dict()["status"] == "draft"

    # Invalid: draft -> in_progress
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "in_progress"})
    assert mock_db.collection("events").document(event_id).get().to_dict()["status"] == "draft"

    # Invalid: draft -> completed
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "completed"})
    assert mock_db.collection("events").document(event_id).get().to_dict()["status"] == "draft"

    # Invalid: draft -> registration_closed
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "registration_closed"})
    assert mock_db.collection("events").document(event_id).get().to_dict()["status"] == "draft"

    # Valid: draft -> published
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "published"})
    assert mock_db.collection("events").document(event_id).get().to_dict()["status"] == "published"

    # Invalid: published -> completed
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "completed"})
    assert mock_db.collection("events").document(event_id).get().to_dict()["status"] == "published"

    # Valid: published -> registration_open
    client.post(f"/spoc/event/{event_id}/transition", data={"target_state": "registration_open"})
    assert mock_db.collection("events").document(event_id).get().to_dict()["status"] == "registration_open"
