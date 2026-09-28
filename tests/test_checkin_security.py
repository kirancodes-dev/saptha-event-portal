"""
tests/test_checkin_security.py — Security integration tests for Check-in & Ticket systems

Covers:
  1. Anonymous kiosk search & confirm rejected (requires staff role).
  2. Kiosk search never returns emails or phone numbers, and never returns other events' registrations.
  3. A participant cannot confirm someone else's attendance.
  4. Raw registration IDs in /ticket/verify and /ticket/api/verify are rejected.
  5. GET /ticket/verify never marks attendance (public read-only validation).
  6. Forged or tampered ticket tokens are rejected.
  7. Self check-in without a valid signed venue code is rejected.
  8. Application refuses to start in production without a valid, strong SECRET_KEY.
"""
import importlib
import pytest

from routes_ticket import generate_ticket_token
from routes_checkin import _get_venue_serializer


def test_anonymous_kiosk_search_and_confirm_rejected(client, mock_db):
    """Anonymous kiosk search/confirm must be rejected; Students must also be rejected."""
    # 1. Anonymous search
    resp = client.post('/checkin/kiosk/search', json={'query': 'test', 'event_id': 'evt_1'})
    assert resp.status_code in (302, 401, 403)

    # 2. Anonymous confirm
    resp = client.post('/checkin/kiosk/confirm/REG-123')
    assert resp.status_code in (302, 401, 403)

    # 3. Logged-in non-staff participant (Student role)
    with client.session_transaction() as sess:
        sess['user_id'] = 'student@test.edu'
        sess['role'] = 'Student'

    resp = client.post('/checkin/kiosk/search', json={'query': 'test', 'event_id': 'evt_1'})
    assert resp.status_code in (302, 401, 403)

    resp = client.post('/checkin/kiosk/confirm/REG-123')
    assert resp.status_code in (302, 401, 403)


def test_kiosk_search_never_returns_emails_and_scoped_to_event(client, mock_db):
    """Kiosk search must require event_id, query only that event, and omit emails and phone numbers."""
    # Setup two events
    mock_db.collection('events').document('evt_A').set({
        'title': 'Hackathon A',
        'status': 'active',
        'created_by': 'spoc@test.edu'
    })
    mock_db.collection('events').document('evt_B').set({
        'title': 'Hackathon B',
        'status': 'active',
        'created_by': 'spoc@test.edu'
    })

    # Registration in Event A (with sensitive emails & phones)
    mock_db.collection('registrations').document('REG-A1').set({
        'event_id': 'evt_A',
        'lead_name': 'Alice Smith',
        'lead_email': 'alice_secret@test.edu',
        'team_name': 'Alpha Squad',
        'attendance': 'Pending',
        'members': [{
            'name': 'Bob TeamMember',
            'email': 'bob_secret@test.edu',
            'phone': '9876543210'
        }]
    })

    # Registration in Event B with similar name
    mock_db.collection('registrations').document('REG-B1').set({
        'event_id': 'evt_B',
        'lead_name': 'Alice Wonder',
        'lead_email': 'alice_other@test.edu',
        'team_name': 'Beta Squad',
        'attendance': 'Pending'
    })

    # Log in as SPOC for evt_A
    with client.session_transaction() as sess:
        sess['user_id'] = 'spoc@test.edu'
        sess['role'] = 'ClubSPOC'
        sess['category'] = 'General'

    # Search Event A for "Alice"
    resp = client.post('/checkin/kiosk/search', json={'query': 'Alice', 'event_id': 'evt_A'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    results = data['results']

    # Must contain REG-A1
    reg_ids = [r['reg_id'] for r in results]
    assert 'REG-A1' in reg_ids
    # Must NOT contain registrations from Event B
    assert 'REG-B1' not in reg_ids

    # Verify returned fields do NOT include personal emails or phones
    for r in results:
        assert 'lead_email' not in r
        assert 'members' not in r
        assert 'email' not in r
        assert 'phone' not in r
        assert set(r.keys()).issubset({'reg_id', 'lead_name', 'team_name', 'attendance', 'event_title'})

    # Full payload text scan: ensure emails/phones are nowhere in response body
    raw_response = resp.data.decode('utf-8')
    assert 'alice_secret@test.edu' not in raw_response
    assert 'bob_secret@test.edu' not in raw_response
    assert '9876543210' not in raw_response
    assert 'alice_other@test.edu' not in raw_response


def test_participant_cannot_confirm_someone_else(client, mock_db):
    """A participant must not be able to confirm someone else's registration or ticket."""
    mock_db.collection('events').document('evt_test').set({
        'title': 'Test Event',
        'status': 'active',
        'created_by': 'admin@test.edu'
    })
    mock_db.collection('registrations').document('REG-VICTIM').set({
        'event_id': 'evt_test',
        'lead_name': 'Victim User',
        'lead_email': 'victim@test.edu',
        'attendance': 'Pending',
        'payment_status': 'Paid'
    })

    # Log in as an attacker student
    with client.session_transaction() as sess:
        sess['user_id'] = 'attacker@test.edu'
        sess['role'] = 'Student'

    # 1. Attacker tries kiosk confirm
    resp = client.post('/checkin/kiosk/confirm/REG-VICTIM')
    assert resp.status_code in (302, 401, 403)

    # 2. Attacker tries POST /ticket/verify
    token = generate_ticket_token('REG-VICTIM', 'evt_test', 'Victim User')
    resp = client.post(f'/ticket/verify/{token}')
    assert resp.status_code in (302, 401, 403)

    # 3. Attacker tries POST /ticket/api/verify
    resp = client.post(f'/ticket/api/verify/{token}')
    assert resp.status_code in (302, 401, 403)

    # Ensure attendance was not modified
    reg = mock_db.collection('registrations').document('REG-VICTIM').get().to_dict()
    assert reg.get('attendance') == 'Pending'


def test_raw_reg_id_verify_rejected(client, mock_db):
    """Passing a raw registration ID instead of a cryptographically signed token must be rejected."""
    mock_db.collection('registrations').document('REG-RAW-123').set({
        'lead_name': 'Raw Student',
        'lead_email': 'raw@test.edu',
        'attendance': 'Pending',
        'payment_status': 'Paid',
        'event_id': 'evt_1'
    })

    # GET /ticket/verify/<raw_id> -> 400
    resp = client.get('/ticket/verify/REG-RAW-123')
    assert resp.status_code == 400

    # POST /ticket/verify/<raw_id> -> 400
    resp = client.post('/ticket/verify/REG-RAW-123')
    assert resp.status_code == 400

    # GET /ticket/api/verify/<raw_id> -> 400
    resp = client.get('/ticket/api/verify/REG-RAW-123')
    assert resp.status_code == 400

    # POST /ticket/api/verify/<raw_id> -> 400
    resp = client.post('/ticket/api/verify/REG-RAW-123')
    assert resp.status_code == 400


def test_get_verify_never_marks_attendance(client, mock_db):
    """GET /ticket/verify and GET /ticket/api/verify must never change attendance state."""
    mock_db.collection('events').document('evt_safe').set({
        'title': 'Safe Event',
        'status': 'active'
    })
    mock_db.collection('registrations').document('REG-SAFE-1').set({
        'event_id': 'evt_safe',
        'lead_name': 'Jane Doe',
        'lead_email': 'jane@test.edu',
        'attendance': 'Pending',
        'payment_status': 'Paid'
    })

    token = generate_ticket_token('REG-SAFE-1', 'evt_safe', 'Jane Doe')

    # Anonymous GET verify
    resp = client.get(f'/ticket/verify/{token}')
    assert resp.status_code == 200
    reg = mock_db.collection('registrations').document('REG-SAFE-1').get().to_dict()
    assert reg.get('attendance') == 'Pending'

    # Staff GET verify
    with client.session_transaction() as sess:
        sess['user_id'] = 'coord@test.edu'
        sess['role'] = 'Coordinator'
        sess['category'] = 'All'

    resp = client.get(f'/ticket/verify/{token}')
    assert resp.status_code == 200
    reg = mock_db.collection('registrations').document('REG-SAFE-1').get().to_dict()
    assert reg.get('attendance') == 'Pending'

    # Staff GET api/verify
    resp = client.get(f'/ticket/api/verify/{token}')
    assert resp.status_code == 200
    reg = mock_db.collection('registrations').document('REG-SAFE-1').get().to_dict()
    assert reg.get('attendance') == 'Pending'

    # Only POST by authorized staff marks attendance
    resp = client.post(f'/ticket/verify/{token}')
    assert resp.status_code == 200
    reg_after = mock_db.collection('registrations').document('REG-SAFE-1').get().to_dict()
    assert reg_after.get('attendance') == 'Present'


def test_forged_or_tampered_token_rejected(client, mock_db):
    """Forged or tampered tokens must fail verification."""
    token = generate_ticket_token('REG-TEST', 'evt_1', 'John Doe')
    tampered = token[:-4] + "WXYZ"

    # HTML verification
    resp = client.get(f'/ticket/verify/{tampered}')
    assert resp.status_code == 400

    resp = client.post(f'/ticket/verify/{tampered}')
    assert resp.status_code == 400

    # JSON API verification
    resp = client.get(f'/ticket/api/verify/{tampered}')
    assert resp.status_code == 400

    # Bogus string
    resp = client.get('/ticket/api/verify/completely-bogus-token-string')
    assert resp.status_code == 400


def test_self_checkin_without_valid_venue_code_rejected(client, mock_db):
    """Self check-in must require a logged-in owner and a valid, short-lived signed venue code."""
    mock_db.collection('events').document('evt_self').set({
        'title': 'Self Checkin Event',
        'status': 'active',
        'allow_self_checkin': True
    })
    mock_db.collection('events').document('evt_other').set({
        'title': 'Other Event',
        'status': 'active',
        'allow_self_checkin': True
    })
    mock_db.collection('registrations').document('REG-SELF-99').set({
        'event_id': 'evt_self',
        'lead_name': 'Self Student',
        'lead_email': 'self_student@test.edu',
        'attendance': 'Pending',
        'payment_status': 'Paid'
    })

    # Log in as the registration owner
    with client.session_transaction() as sess:
        sess['user_id'] = 'self_student@test.edu'
        sess['role'] = 'Student'

    # Case 1: Missing code
    resp = client.post('/checkin/evt_self/submit', data={})
    assert resp.status_code == 302
    reg = mock_db.collection('registrations').document('REG-SELF-99').get().to_dict()
    assert reg.get('attendance') == 'Pending'

    # Case 2: Tampered code
    resp = client.post('/checkin/evt_self/submit', data={'code': 'tampered_venue_code_abc'})
    assert resp.status_code == 302
    reg = mock_db.collection('registrations').document('REG-SELF-99').get().to_dict()
    assert reg.get('attendance') == 'Pending'

    # Case 3: Signed code for a DIFFERENT event
    serializer = _get_venue_serializer()
    wrong_event_code = serializer.dumps({'event_id': 'evt_other'})
    resp = client.post('/checkin/evt_self/submit', data={'code': wrong_event_code})
    assert resp.status_code == 302
    reg = mock_db.collection('registrations').document('REG-SELF-99').get().to_dict()
    assert reg.get('attendance') == 'Pending'

    # Case 4: Correct signed code for this event
    valid_code = serializer.dumps({'event_id': 'evt_self'})
    resp = client.post('/checkin/evt_self/submit', data={'code': valid_code})
    assert resp.status_code == 200
    reg = mock_db.collection('registrations').document('REG-SELF-99').get().to_dict()
    assert reg.get('attendance') == 'Present'


def test_app_refuses_to_boot_in_production_without_secret_key(monkeypatch):
    """In production, missing or weak SECRET_KEY must prevent application boot."""
    import config

    # 1. Missing / Empty SECRET_KEY
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="CRITICAL: In production, SECRET_KEY must be set"):
        importlib.reload(config)

    # 2. Known default / weak SECRET_KEY
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "default_secret_key")
    with pytest.raises(RuntimeError, match="CRITICAL: In production, SECRET_KEY must be set"):
        importlib.reload(config)

    # 3. Too short SECRET_KEY (< 32 characters)
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "short_secret_key_123")
    with pytest.raises(RuntimeError, match="CRITICAL: In production, SECRET_KEY must be set"):
        importlib.reload(config)

    # Reset environment cleanly
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest-12345")
    importlib.reload(config)
