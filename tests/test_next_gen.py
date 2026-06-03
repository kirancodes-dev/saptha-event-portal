"""
tests/test_next_gen.py — Integration and functional tests for the next-gen upgrades (Phases 6–10)
"""

import json
from unittest.mock import patch


# Helper to setup a logged-in SPOC session
def login_as_spoc(client, mock_db):
    mock_db.collection("users").document("spoc@test.edu").set({
        "name": "Test SPOC",
        "email": "spoc@test.edu",
        "role": "ClubSPOC",
        "is_active": True,
    })
    with client.session_transaction() as sess:
        sess["user_id"] = "spoc@test.edu"
        sess["role"] = "ClubSPOC"
        sess["name"] = "Test SPOC"
    return client


# Helper to setup a logged-in Student session
def login_as_student(client, mock_db):
    mock_db.collection("users").document("student@test.edu").set({
        "name": "Test Student",
        "email": "student@test.edu",
        "role": "Student",
        "is_active": True,
    })
    with client.session_transaction() as sess:
        sess["user_id"] = "student@test.edu"
        sess["role"] = "Student"
        sess["name"] = "Test Student"
    return client


# ═══════════════════════════════════════════════════════════════════════════
# TESTS FOR UPGRADE 1: CRYPTOGRAPHIC VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def test_verify_certificate_invalid_hash_returns_404(client, mock_db):
    print("URL MAP IS:")
    for rule in client.application.url_map.iter_rules():
        print(rule.endpoint, "->", rule.rule)
    resp = client.get('/verify/invalidhash12345')
    print("RESPONSE BODY IS:", resp.data)
    assert resp.status_code == 404
    assert b"Verification Failed" in resp.data


def test_verify_certificate_valid_hash_returns_200(client, mock_db):
    mock_db.collection("verified_certificates").document("validhash123").set({
        "hash": "validhash123",
        "student_name": "Kiran Biradar",
        "event_title": "AI Showdown 2026",
        "cert_type": "winner",
        "rank": 1,
        "college_name": "Sapthagiri University",
        "issued_at": "2026-06-02T19:21:25",
    })
    resp = client.get('/verify/validhash123')
    assert resp.status_code == 200
    assert b"Certificate Verified" in resp.data
    assert b"Kiran Biradar" in resp.data
    assert b"AI Showdown 2026" in resp.data


# ═══════════════════════════════════════════════════════════════════════════
# TESTS FOR UPGRADE 2: CAMPUS WAYFINDER MAPS
# ═══════════════════════════════════════════════════════════════════════════

def test_wayfinder_page_returns_200(client):
    resp = client.get('/platform/wayfinder')
    assert resp.status_code == 200
    assert b"SapthaEvent Wayfinder" in resp.data
    assert b"Campus Wayfinder" in resp.data


# ═══════════════════════════════════════════════════════════════════════════
# TESTS FOR UPGRADE 3: LIVE STREAM AND REELS SHOWCASES
# ═══════════════════════════════════════════════════════════════════════════

def test_live_streams_page_returns_200(client):
    resp = client.get('/live/streams')
    assert resp.status_code == 200
    assert b"SapthaEvent LiveStream" in resp.data


def test_live_reels_page_returns_200(client):
    resp = client.get('/live/reels')
    assert resp.status_code == 200
    assert b"Watch Highlight Reels" in resp.data or b"SapthaEvent Highlight Reels" in resp.data


# ═══════════════════════════════════════════════════════════════════════════
# TESTS FOR UPGRADE 4: TEAMMATE MATCHMAKER CHATS
# ═══════════════════════════════════════════════════════════════════════════

def test_matchmaker_page_requires_auth(client):
    resp = client.get('/participant/matchmaker/')
    assert resp.status_code in (302, 401)  # Redirects to login or errors


def test_matchmaker_endpoint_calculates_jaccard_matches(client, mock_db):
    auth_c = login_as_student(client, mock_db)
    payload = {
        "skills": ["Python", "Flask"],
        "interests": ["AI Hackathon"]
    }
    resp = auth_c.post(
        '/participant/matchmaker/api/match',
        data=json.dumps(payload),
        content_type='application/json'
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert len(data['matches']) > 0
    # The first mock partner should have high score due to overlapping skills/interests
    assert data['matches'][0]['match_score'] > 30


def test_matchmaker_message_exchange_simulates_realtime_replies(client, mock_db):
    auth_c = login_as_student(client, mock_db)
    payload = {
        "peer_id": "st_002",
        "message": "Hey! Want to join forces for the web dev fest?"
    }
    resp = auth_c.post(
        '/participant/matchmaker/api/message',
        data=json.dumps(payload),
        content_type='application/json'
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert 'reply' in data
    assert data['sender'] == 'Sneha Kulkarni'


# ═══════════════════════════════════════════════════════════════════════════
# TESTS FOR UPGRADE 5: JUDGE SCORE NORMALIZATION AUDITS
# ═══════════════════════════════════════════════════════════════════════════

def test_judging_audit_page_resolves_and_renders_bias(client, mock_db):
    spoc_c = login_as_spoc(client, mock_db)
    mock_db.collection("events").document("evt_test_001").set({
        "title": "RoboWars 2026",
        "spoc_id": "spoc@test.edu"
    })
    # Add mock registration with judge scores to calculate variance
    mock_db.collection("registrations").document("reg_test_001").set({
        "event_id": "evt_test_001",
        "lead_name": "Aarav",
        "scores": {
            "judge_strict@test.edu": {"total": 5.0},
            "judge_lenient@test.edu": {"total": 9.0}
        }
    })
    
    resp = spoc_c.get('/spoc/judging/audit/evt_test_001')
    assert resp.status_code == 200
    assert b"Strictness Status" in resp.data
    assert b"judge_strict@test.edu" in resp.data
    assert b"judge_lenient@test.edu" in resp.data


# ═══════════════════════════════════════════════════════════════════════════
# TESTS FOR UPGRADE 6: AI SCHEDULE CLASH OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════

def test_schedule_optimizer_detects_clashes(client, mock_db):
    spoc_c = login_as_spoc(client, mock_db)
    mock_db.collection("events").document("evt_test_001").set({
        "title": "RoboWars 2026",
        "spoc_id": "spoc@test.edu",
        "date": "2026-06-15"
    })
    
    resp = spoc_c.get('/spoc/schedule/optimize/evt_test_001')
    assert resp.status_code == 200
    assert b"Schedule &amp; Timetable Optimizer" in resp.data or b"Schedule & Timetable Optimizer" in resp.data
    assert b"Optimized Agenda Timeline" in resp.data


# ═══════════════════════════════════════════════════════════════════════════
# TESTS FOR UPGRADE 7: NFC SCANNER SIMULATION
# ═══════════════════════════════════════════════════════════════════════════

def test_nfc_verify_view_renders_dropdown_list(client, mock_db):
    spoc_c = login_as_spoc(client, mock_db)
    mock_db.collection("events").document("evt_test_001").set({
        "title": "RoboWars 2026",
        "spoc_id": "spoc@test.edu"
    })
    mock_db.collection("registrations").document("reg_test_001").set({
        "event_id": "evt_test_001",
        "lead_name": "Aarav Mehta",
        "lead_email": "aarav@test.edu",
        "attendance": "Pending"
    })
    
    resp = spoc_c.get('/spoc/ticket/nfc-verify/evt_test_001')
    assert resp.status_code == 200
    assert b"RFID Scan Terminal" in resp.data
    assert b"Aarav Mehta" in resp.data


# ═══════════════════════════════════════════════════════════════════════════
# TESTS FOR UPGRADE 8: SURGE pricing and checkout
# ═══════════════════════════════════════════════════════════════════════════

def test_dynamic_pricing_endpoint_applies_surge(client, mock_db):
    mock_db.collection("events").document("evt_test_001").set({
        "title": "Sports Stadium Arena",
        "entry_fee": 100,
        "registration_count": 80,
        "limits": {"max_participants": 100} # 80% filled -> 1.5x surge price
    })
    
    resp = client.get('/api/pricing/evt_test_001')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert data['base_price'] == 100.0
    assert data['surge_price'] == 150.0
    assert data['multiplier'] == 1.5
    assert "High Demand Surge" in data['reason']


def test_checkout_applies_surge_pricing_to_order_amount(client, mock_db):
    mock_db.collection("events").document("evt_test_001").set({
        "title": "Sports Stadium Arena",
        "entry_fee": 100,
        "registration_count": 80,
        "limits": {"max_participants": 100}
    })
    with client.session_transaction() as sess:
        sess['pending_reg_data'] = {'lead_email': 'test@student.edu', 'lead_name': 'Test Student'}
        
    resp = client.post(
        '/payment/create_order',
        data=json.dumps({"event_id": "evt_test_001"}),
        content_type='application/json'
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['simulate'] is True
    assert data['amount'] == 150.0 # verified surge price correctly propagated
    assert data['multiplier'] == 1.5


# ═══════════════════════════════════════════════════════════════════════════
# TESTS FOR UPGRADE 9: STUDENT AFFILIATES AND REFERRALS
# ═══════════════════════════════════════════════════════════════════════════

def test_referrals_endpoint_returns_stats(client, mock_db):
    auth_c = login_as_student(client, mock_db)
    resp = auth_c.get('/participant/referrals/api/stats')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert 'referral_code' in data
    assert 'referral_link' in data
    assert data['count'] >= 0


def test_referrals_claim_rewards(client, mock_db):
    auth_c = login_as_student(client, mock_db)
    resp = auth_c.post('/participant/referrals/api/claim')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['success'] is True
    assert "Payout request submitted" in data['message']
