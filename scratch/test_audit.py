import sys
sys.path.insert(0, '/Users/kiranbiradar/Desktop/saptha-event-portal')
from tests.conftest import MockFirestore
from app import app
import app as app_module

# Mock DB
mock_db = MockFirestore()
app_module.db = mock_db

# Mock data
mock_db.collection("events").document("evt_test_001").set({
    "title": "RoboWars 2026",
    "spoc_id": "spoc@test.edu"
})
mock_db.collection("registrations").document("reg_test_001").set({
    "event_id": "evt_test_001",
    "lead_name": "Aarav",
    "scores": {
        "judge_strict@test.edu": {"total": 5.0},
        "judge_lenient@test.edu": {"total": 9.0}
    }
})

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess["user_id"] = "spoc@test.edu"
        sess["role"] = "ClubSPOC"
        sess["name"] = "Test SPOC"
    resp = client.get('/spoc/judging/audit/evt_test_001')
    print("STATUS:", resp.status_code)
    print("DATA SIZE:", len(resp.data))
    with open("scratch_audit_out.html", "wb") as f:
        f.write(resp.data)
