"""
test_scoped_roles_e2e.py — Comprehensive End-to-End Scoped RBAC & OrgUnit Tests
================================================================================
Verifies:
  1. A CSE admin cannot view, edit, export, or check in for an ECE event (4 distinct tests).
  2. A UniversityAdmin sees everything across all units.
  3. An EventCoordinator can only act on assigned events.
  4. Role migration correctly maps existing demo users ('SuperAdmin' -> UniversityAdmin,
     ClubSPOC -> UnitAdmin, Coordinator/Judge -> event-scoped) and backfills events.
  5. Unpublished events awaiting approval (draft, pending_approval) aren't publicly visible.
  6. Unit approval guard: unit-created events require pending_approval and admin approval.
  7. Admin page allows managing departments/clubs and assigning/revoking scoped roles.

All tests go through the Flask test client.
"""
from services_permission import migrate_roles_and_units, can


def _setup_test_hierarchy_and_events(mock_db):
    """Seed OrgUnits and sample CSE & ECE events."""
    # OrgUnits
    mock_db.collection("org_units").document("central").set({
        "id": "central", "organization_id": "default", "type": "central",
        "name": "Central Administration", "slug": "central", "parent_id": None
    })
    mock_db.collection("org_units").document("cse").set({
        "id": "cse", "organization_id": "default", "type": "department",
        "name": "Computer Science & Engineering", "slug": "cse", "parent_id": "central"
    })
    mock_db.collection("org_units").document("ece").set({
        "id": "ece", "organization_id": "default", "type": "department",
        "name": "Electronics & Communication Engineering", "slug": "ece", "parent_id": "central"
    })

    # CSE Event
    mock_db.collection("events").document("cse_evt_01").set({
        "id": "cse_evt_01",
        "title": "CSE Hackathon 2026",
        "organization_id": "default",
        "org_unit_id": "cse",
        "category": "Technical",
        "status": "active",
        "date": "2026-12-20",
        "spoc_id": "cse_admin@test.edu",
        "spoc_email": "cse_admin@test.edu",
        "created_by_email": "cse_admin@test.edu",
        "coordinators": ["coord_cse@test.edu"],
        "staff": [{"email": "coord_cse@test.edu", "role": "EventCoordinator"}],
    })

    # ECE Event
    mock_db.collection("events").document("ece_evt_01").set({
        "id": "ece_evt_01",
        "title": "ECE Robotics Workshop",
        "organization_id": "default",
        "org_unit_id": "ece",
        "category": "Technical",
        "status": "active",
        "date": "2026-12-25",
        "spoc_id": "ece_admin@test.edu",
        "spoc_email": "ece_admin@test.edu",
        "created_by_email": "ece_admin@test.edu",
        "coordinators": ["coord_ece@test.edu"],
        "staff": [{"email": "coord_ece@test.edu", "role": "EventCoordinator"}],
    })

    # Registrations for each event
    mock_db.collection("registrations").document("reg_cse_01").set({
        "id": "reg_cse_01",
        "event_id": "cse_evt_01",
        "lead_name": "Aarav Sharma",
        "lead_email": "aarav@student.edu",
        "attendance": "Pending",
        "payment_status": "Free",
        "registered_at": "2026-06-01",
    })
    mock_db.collection("registrations").document("reg_ece_01").set({
        "id": "reg_ece_01",
        "event_id": "ece_evt_01",
        "lead_name": "Diya Patel",
        "lead_email": "diya@student.edu",
        "attendance": "Pending",
        "payment_status": "Free",
        "registered_at": "2026-06-01",
    })

    # Users
    mock_db.collection("users").document("cse_admin@test.edu").set({
        "email": "cse_admin@test.edu",
        "name": "Prof. CSE Admin",
        "role": "UnitAdmin",
        "department": "cse",
        "org_unit_id": "cse",
    })
    mock_db.collection("users").document("ece_admin@test.edu").set({
        "email": "ece_admin@test.edu",
        "name": "Prof. ECE Admin",
        "role": "UnitAdmin",
        "department": "ece",
        "org_unit_id": "ece",
    })
    mock_db.collection("users").document("univ_admin@test.edu").set({
        "email": "univ_admin@test.edu",
        "name": "Vice Chancellor",
        "role": "UniversityAdmin",
    })

    # Role Assignments
    mock_db.collection("role_assignments").document("ra_cse_admin").set({
        "id": "ra_cse_admin",
        "user_id": "cse_admin@test.edu",
        "role": "UnitAdmin",
        "scope_type": "unit",
        "scope_id": "cse",
    })
    mock_db.collection("role_assignments").document("ra_ece_admin").set({
        "id": "ra_ece_admin",
        "user_id": "ece_admin@test.edu",
        "role": "UnitAdmin",
        "scope_type": "unit",
        "scope_id": "ece",
    })
    mock_db.collection("role_assignments").document("ra_univ_admin").set({
        "id": "ra_univ_admin",
        "user_id": "univ_admin@test.edu",
        "role": "UniversityAdmin",
        "scope_type": "university",
        "scope_id": "default",
    })


# ═══════════════════════════════════════════════════════════════════════════
# 1. CSE ADMIN CANNOT VIEW, EDIT, EXPORT, OR CHECK IN FOR ECE EVENT
# ═══════════════════════════════════════════════════════════════════════════

def test_cse_admin_cannot_view_ece_event(client, mock_db):
    """CSE admin only sees CSE events on SPOC dashboard and cannot view ECE results."""
    _setup_test_hierarchy_and_events(mock_db)

    with client.session_transaction() as sess:
        sess["user_id"] = "cse_admin@test.edu"
        sess["role"] = "UnitAdmin"
        sess["name"] = "Prof. CSE Admin"
        sess["org_unit_id"] = "cse"

    # Dashboard lists only CSE events
    resp = client.get("/spoc/dashboard")
    assert resp.status_code == 200
    assert b"CSE Hackathon 2026" in resp.data
    assert b"ECE Robotics Workshop" not in resp.data

    # Direct results page for ECE event is forbidden
    resp_results = client.get("/spoc/results/ece_evt_01")
    assert resp_results.status_code == 403


def test_cse_admin_cannot_edit_ece_event(client, mock_db):
    """CSE admin gets 403 when attempting to GET or POST edit for an ECE event."""
    _setup_test_hierarchy_and_events(mock_db)

    with client.session_transaction() as sess:
        sess["user_id"] = "cse_admin@test.edu"
        sess["role"] = "UnitAdmin"
        sess["name"] = "Prof. CSE Admin"
        sess["org_unit_id"] = "cse"

    # GET edit page for ECE event
    resp_get = client.get("/spoc/edit_event/ece_evt_01")
    assert resp_get.status_code == 403

    # POST update to ECE event
    resp_post = client.post("/spoc/edit_event/ece_evt_01", data={"title": "Hacked ECE Event"})
    assert resp_post.status_code == 403

    # Verify event was NOT modified
    doc = mock_db.collection("events").document("ece_evt_01").get()
    assert doc.to_dict()["title"] == "ECE Robotics Workshop"


def test_cse_admin_cannot_export_ece_event(client, mock_db):
    """CSE admin gets 403 when trying to export CSV or registrations for an ECE event."""
    _setup_test_hierarchy_and_events(mock_db)

    with client.session_transaction() as sess:
        sess["user_id"] = "cse_admin@test.edu"
        sess["role"] = "UnitAdmin"
        sess["name"] = "Prof. CSE Admin"
        sess["org_unit_id"] = "cse"

    # SPOC CSV export
    resp_spoc_csv = client.get("/spoc/export_csv/ece_evt_01")
    assert resp_spoc_csv.status_code == 403

    # Coordinator registrations export
    resp_coord_csv = client.get("/coordinator/export_registrations/ece_evt_01")
    assert resp_coord_csv.status_code == 403


def test_cse_admin_cannot_check_in_for_ece_event(client, mock_db):
    """CSE admin cannot access scan page, invoke check-in API, or use kiosk for an ECE event."""
    _setup_test_hierarchy_and_events(mock_db)

    with client.session_transaction() as sess:
        sess["user_id"] = "cse_admin@test.edu"
        sess["role"] = "UnitAdmin"
        sess["name"] = "Prof. CSE Admin"
        sess["org_unit_id"] = "cse"

    # Scan page returns 403 Forbidden
    resp_scan = client.get("/spoc/scan/ece_evt_01")
    assert resp_scan.status_code == 403

    # SPOC checkin API returns 403
    resp_api = client.post("/spoc/api/checkin/ece_evt_01/reg_ece_01")
    assert resp_api.status_code == 403

    # Kiosk confirm checkin returns 403 Forbidden
    resp_kiosk = client.post("/checkin/kiosk/confirm/reg_ece_01")
    assert resp_kiosk.status_code == 403
    data = resp_kiosk.get_json()
    assert data["success"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. UNIVERSITY ADMIN SEES EVERYTHING
# ═══════════════════════════════════════════════════════════════════════════

def test_university_admin_sees_everything(client, mock_db):
    """UniversityAdmin has campus-wide access to all units, events, exports, and admin views."""
    _setup_test_hierarchy_and_events(mock_db)

    with client.session_transaction() as sess:
        sess["user_id"] = "univ_admin@test.edu"
        sess["role"] = "UniversityAdmin"
        sess["name"] = "Vice Chancellor"

    # Dashboard shows both CSE and ECE events
    resp_spoc = client.get("/spoc/dashboard")
    assert resp_spoc.status_code == 200
    assert b"CSE Hackathon 2026" in resp_spoc.data
    assert b"ECE Robotics Workshop" in resp_spoc.data

    # Export for any event succeeds (200 OK + CSV content)
    resp_csv = client.get("/spoc/export_csv/ece_evt_01")
    assert resp_csv.status_code == 200
    assert b"Lead Email" in resp_csv.data

    # Coordinator export succeeds
    resp_coord = client.get("/coordinator/export_registrations/cse_evt_01")
    assert resp_coord.status_code == 200

    # Admin org_units management page loads
    resp_org = client.get("/admin/org_units")
    assert resp_org.status_code == 200
    assert b"Configured OrgUnits" in resp_org.data


# ═══════════════════════════════════════════════════════════════════════════
# 3. EVENT COORDINATOR CAN ONLY ACT ON ASSIGNED EVENTS
# ═══════════════════════════════════════════════════════════════════════════

def test_event_coordinator_scoped_to_assigned_events(client, mock_db):
    """EventCoordinator only sees and acts on their assigned event, not unassigned events."""
    _setup_test_hierarchy_and_events(mock_db)

    # Assign coord_user only to cse_evt_01
    mock_db.collection("role_assignments").document("ra_coord_cse").set({
        "id": "ra_coord_cse",
        "user_id": "coord_cse@test.edu",
        "role": "EventCoordinator",
        "scope_type": "event",
        "scope_id": "cse_evt_01",
    })

    with client.session_transaction() as sess:
        sess["user_id"] = "coord_cse@test.edu"
        sess["role"] = "EventCoordinator"
        sess["name"] = "CSE Coordinator"

    # Coordinator dashboard: shows cse_evt_01, hides ece_evt_01
    resp_dash = client.get("/coordinator/dashboard")
    assert resp_dash.status_code == 200
    assert b"CSE Hackathon 2026" in resp_dash.data
    assert b"ECE Robotics Workshop" not in resp_dash.data

    # View registrations: allowed on assigned event
    resp_reg_cse = client.get("/coordinator/registrations/cse_evt_01")
    assert resp_reg_cse.status_code == 200
    assert b"Aarav Sharma" in resp_reg_cse.data

    # View registrations: forbidden on unassigned ECE event
    resp_reg_ece = client.get("/coordinator/registrations/ece_evt_01")
    assert resp_reg_ece.status_code == 403

    # Export registrations: allowed on assigned event
    resp_exp_cse = client.get("/coordinator/export_registrations/cse_evt_01")
    assert resp_exp_cse.status_code == 200

    # Export registrations: forbidden on unassigned event
    resp_exp_ece = client.get("/coordinator/export_registrations/ece_evt_01")
    assert resp_exp_ece.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 4. ROLE MIGRATION MAPS EXISTING DEMO USERS CORRECTLY
# ═══════════════════════════════════════════════════════════════════════════

def test_role_migration_maps_demo_users_and_backfills(mock_db):
    """Test migrate_roles_and_units helper: maps legacy roles and backfills events."""
    # Seed legacy users
    mock_db.collection("users").document("admin_old@test.edu").set({
        "email": "admin_old@test.edu",
        "role": "SuperAdmin",
        "name": "Legacy Super Admin",
    })
    mock_db.collection("users").document("spoc_cs@test.edu").set({
        "email": "spoc_cs@test.edu",
        "role": "ClubSPOC",
        "department": "Computer Science & Engineering",
        "name": "CS SPOC",
    })
    mock_db.collection("users").document("spoc_ec@test.edu").set({
        "email": "spoc_ec@test.edu",
        "role": "ClubSPOC",
        "department": "Electronics and Communication",
        "name": "EC SPOC",
    })
    mock_db.collection("users").document("coord_demo@test.edu").set({
        "email": "coord_demo@test.edu",
        "role": "Coordinator",
        "name": "Demo Coordinator",
    })
    mock_db.collection("users").document("judge_demo@test.edu").set({
        "email": "judge_demo@test.edu",
        "role": "Judge",
        "name": "Demo Judge",
    })
    mock_db.collection("users").document("unmapped@test.edu").set({
        "email": "unmapped@test.edu",
        "role": "ClubSPOC",
        "department": "",
        "category": "General",
        "club": "",
        "name": "Unknown SPOC",
    })

    # Legacy event without org_unit_id, with staff
    mock_db.collection("events").document("legacy_evt_001").set({
        "title": "Old University Fest",
        "staff": [
            {"email": "coord_demo@test.edu", "role": "Coordinator"},
            {"email": "judge_demo@test.edu", "role": "Judge"},
        ],
        "coordinators": ["coord_demo@test.edu"],
    })

    result = migrate_roles_and_units(mock_db)

    # 1. 'SuperAdmin' -> UniversityAdmin
    u_admin = mock_db.collection("users").document("admin_old@test.edu").get().to_dict()
    assert u_admin["role"] == "UniversityAdmin"
    ra_admin = mock_db.collection("role_assignments").document("ra_admin_old@test.edu_univ").get().to_dict()
    assert ra_admin["role"] == "UniversityAdmin"
    assert ra_admin["scope_type"] == "university"

    # 2. ClubSPOC -> UnitAdmin of their unit
    u_cs = mock_db.collection("users").document("spoc_cs@test.edu").get().to_dict()
    assert u_cs["role"] == "UnitAdmin"
    ra_cs = mock_db.collection("role_assignments").document("ra_spoc_cs@test.edu_cse").get().to_dict()
    assert ra_cs["scope_id"] == "cse"

    u_ec = mock_db.collection("users").document("spoc_ec@test.edu").get().to_dict()
    assert u_ec["role"] == "UnitAdmin"
    ra_ec = mock_db.collection("role_assignments").document("ra_spoc_ec@test.edu_ece").get().to_dict()
    assert ra_ec["scope_id"] == "ece"

    # 3. Coordinator / Judge -> event-scoped role assignments
    ra_coord = mock_db.collection("role_assignments").document("ra_coord_demo@test.edu_legacy_evt_001").get().to_dict()
    assert ra_coord["role"] == "EventCoordinator"
    assert ra_coord["scope_type"] == "event"
    assert ra_coord["scope_id"] == "legacy_evt_001"

    ra_judge = mock_db.collection("role_assignments").document("ra_judge_demo@test.edu_legacy_evt_001").get().to_dict()
    assert ra_judge["role"] == "Judge"
    assert ra_judge["scope_type"] == "event"
    assert ra_judge["scope_id"] == "legacy_evt_001"

    # 4. Backfill existing event to 'central'
    e_legacy = mock_db.collection("events").document("legacy_evt_001").get().to_dict()
    assert e_legacy["org_unit_id"] == "central"

    # 5. Unmapped users identified
    assert any(u["email"] == "unmapped@test.edu" for u in result["unmapped_users"])


# ═══════════════════════════════════════════════════════════════════════════
# 5. UNPUBLISHED EVENTS AWAITING APPROVAL AREN'T PUBLICLY VISIBLE
# ═══════════════════════════════════════════════════════════════════════════

def test_unpublished_events_awaiting_approval_not_publicly_visible(client, mock_db):
    """Events in draft or pending_approval state return 404 to public visitors."""
    _setup_test_hierarchy_and_events(mock_db)

    # Draft event
    mock_db.collection("events").document("draft_evt").set({
        "id": "draft_evt",
        "title": "Secret Draft Seminar",
        "status": "draft",
        "org_unit_id": "cse",
    })

    # Pending approval event
    mock_db.collection("events").document("pending_evt").set({
        "id": "pending_evt",
        "title": "Awaiting Approval Symposium",
        "status": "pending_approval",
        "org_unit_id": "ece",
    })

    # Public unauthenticated visitor cannot view details (404)
    resp_draft = client.get("/event/draft_evt")
    assert resp_draft.status_code == 404

    resp_pending = client.get("/event/pending_evt")
    assert resp_pending.status_code == 404

    # Public unauthenticated visitor cannot register (closed)
    resp_reg_pending = client.get("/forms/register/pending_evt")
    assert resp_reg_pending.status_code == 200
    assert b"Registration Closed" in resp_reg_pending.data or b"registration_closed" in resp_reg_pending.data


# ═══════════════════════════════════════════════════════════════════════════
# 6. APPROVAL WORKFLOW FOR UNIT-CREATED EVENTS
# ═══════════════════════════════════════════════════════════════════════════

def test_unit_created_event_workflow_guard_and_approval(client, mock_db):
    """Unit-created event cannot jump directly from draft to published; requires approval."""
    _setup_test_hierarchy_and_events(mock_db)

    mock_db.collection("events").document("cse_new_evt").set({
        "id": "cse_new_evt",
        "title": "CSE Advanced Web Summit",
        "status": "draft",
        "org_unit_id": "cse",
        "spoc_id": "cse_admin@test.edu",
    })

    # 1. CSE admin tries to transition directly from draft -> published: blocked by guard
    with client.session_transaction() as sess:
        sess["user_id"] = "cse_admin@test.edu"
        sess["role"] = "UnitAdmin"
        sess["org_unit_id"] = "cse"

    resp_direct_pub = client.post("/spoc/transition_event/cse_new_evt", data={"target_state": "published"}, follow_redirects=True)
    assert resp_direct_pub.status_code == 200
    # Status remains draft
    ev_doc = mock_db.collection("events").document("cse_new_evt").get().to_dict()
    assert ev_doc["status"] == "draft"

    # 2. CSE admin transitions draft -> pending_approval: succeeds
    resp_submit = client.post("/spoc/transition_event/cse_new_evt", data={"target_state": "pending_approval"}, follow_redirects=True)
    assert resp_submit.status_code == 200
    ev_doc = mock_db.collection("events").document("cse_new_evt").get().to_dict()
    assert ev_doc["status"] == "pending_approval"

    # 3. UniversityAdmin approves the event via admin endpoint
    with client.session_transaction() as sess:
        sess["user_id"] = "univ_admin@test.edu"
        sess["role"] = "UniversityAdmin"

    resp_approve = client.post("/admin/events/approve/cse_new_evt", follow_redirects=True)
    assert resp_approve.status_code == 200
    ev_doc = mock_db.collection("events").document("cse_new_evt").get().to_dict()
    assert ev_doc["status"] == "published"


# ═══════════════════════════════════════════════════════════════════════════
# 7. ADMIN PAGE TO MANAGE ORGUNITS AND ASSIGN PEOPLE TO ROLES
# ═══════════════════════════════════════════════════════════════════════════

def test_admin_org_units_and_role_assignment(client, mock_db):
    """Admin can create new OrgUnits and assign/revoke scoped roles."""
    _setup_test_hierarchy_and_events(mock_db)

    with client.session_transaction() as sess:
        sess["user_id"] = "univ_admin@test.edu"
        sess["role"] = "UniversityAdmin"

    # 1. Admin creates a new club OrgUnit
    resp_create_unit = client.post("/admin/org_units/create", data={
        "name": "Robotics Society",
        "type": "club",
        "slug": "robotics-society",
        "parent_id": "central",
    }, follow_redirects=True)
    assert resp_create_unit.status_code == 200
    assert b"Robotics Society" in resp_create_unit.data

    unit_doc = mock_db.collection("org_units").document("robotics-society").get()
    assert unit_doc.exists
    assert unit_doc.to_dict()["name"] == "Robotics Society"

    # 2. Admin assigns a user to UnitAdmin of the new club
    resp_assign = client.post("/admin/roles/assign", data={
        "user_id": "robotics_head@test.edu",
        "role": "UnitAdmin",
        "scope_type": "unit",
        "scope_id": "robotics-society",
    }, follow_redirects=True)
    assert resp_assign.status_code == 200

    # Verify assignment can()
    user_check = {"user_id": "robotics_head@test.edu", "role": "UnitAdmin", "org_unit_id": "robotics-society"}
    assert can(user_check, "create_event", "robotics-society", db=mock_db) is True
    assert can(user_check, "create_event", "cse", db=mock_db) is False

    # 3. Admin revokes role assignment
    ra_id = "ra_robotics_head_test_edu_unit_robotics-society"
    resp_revoke = client.post(f"/admin/roles/revoke/{ra_id}", follow_redirects=True)
    assert resp_revoke.status_code == 200
    ra_doc = mock_db.collection("role_assignments").document(ra_id).get()
    assert not ra_doc.exists
