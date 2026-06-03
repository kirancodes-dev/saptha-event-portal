import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def mock_celery_tasks():
    with patch('tasks.email_tasks.send_ticket_email_task.delay') as mock_email, \
         patch('tasks.notification_tasks.send_payment_receipt_whatsapp_task.delay') as mock_receipt, \
         patch('tasks.notification_tasks.send_ticket_whatsapp_task.delay') as mock_ticket:
        yield (mock_email, mock_receipt, mock_ticket)


def test_stripe_create_session_simulation_fallback(client, mock_db, sample_event):
    """Test that Stripe create_session falls back to simulation mode when API key is missing."""
    with client.session_transaction() as sess:
        sess['pending_reg_data'] = {
            'lead_email': 'student@test.edu',
            'lead_name': 'Test Student',
            'reg_id': 'REG-12345',
            'amount_paid': 100
        }
    
    resp = client.post('/payment/stripe/create_session', 
                       data=json.dumps({'event_id': sample_event}),
                       content_type='application/json')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data.get('simulate') is True
    assert data.get('event_id') == sample_event
    assert data.get('amount') == 100


def test_stripe_success_redirection_and_registration(client, mock_db, sample_event):
    """Test Stripe success route processes registration and redirects to digital ticket."""
    with client.session_transaction() as sess:
        sess['pending_reg_data'] = {
            'event_id': sample_event,
            'lead_email': 'student@test.edu',
            'lead_name': 'Test Student',
            'lead_phone': '+919999999999',
            'reg_id': 'REG-98765',
            'amount_paid': 100
        }
    
    resp = client.get('/payment/stripe/success?session_id=cs_test_123')
    assert resp.status_code == 302
    assert '/ticket/REG-98765' in resp.location
    
    # Check registration created in mock Firestore
    reg_doc = mock_db.collection('registrations').document('REG-98765').get()
    assert reg_doc.exists
    assert reg_doc.to_dict().get('payment_status') == 'Paid (Stripe)'
    assert reg_doc.to_dict().get('status') == 'Confirmed'


def test_ai_generate_event_details(admin_client, mock_db):
    """Test AI route that generates event details structure."""
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.return_value = MagicMock(
        text='{"description": "AI-generated description", "rules": ["Rule 1", "Rule 2"], "judging_criteria": ["Crit 1"]}'
    )
    
    with patch('routes_ai_features._gemini_client', return_value=mock_gemini):
        resp = admin_client.post('/ai/generate_event_details',
                                 data=json.dumps({'title': 'RoboWars', 'category': 'Technical'}),
                                 content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get('status') == 'success'
        assert data['data']['description'] == 'AI-generated description'
        assert len(data['data']['rules']) == 2


def test_ai_chatbot_advanced(client, mock_db):
    """Test advanced context-aware AI chatbot concierge."""
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.return_value = MagicMock(
        text='Here is the event details you requested.'
    )
    
    with patch('routes_ai_features._gemini_client', return_value=mock_gemini):
        resp = client.post('/ai/chatbot_advanced',
                           data=json.dumps({'message': 'Tell me about Technical events'}),
                           content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get('status') == 'success'
        assert 'reply' in data


def test_onboarding_self_service_signup(client, mock_db):
    """Test university onboarding signup creates org tenant and SuperAdmin account."""
    resp = client.post('/onboarding/signup', data={
        'org_name': 'Sapthagiri NPS University',
        'org_domain': 'snpsu.edu',
        'admin_name': 'Kiran Biradar',
        'email': 'kiran@snpsu.edu',
        'password': 'SuperSecretPassword123'
    })
    assert resp.status_code == 302
    assert '/onboarding/wizard' in resp.location
    
    # Assert database state
    org_doc = mock_db.collection('organizations').document('sapthagiri-nps-university').get()
    assert org_doc.exists
    assert org_doc.to_dict().get('domain') == 'snpsu.edu'
    
    user_doc = mock_db.collection('users').document('kiran@snpsu.edu').get()
    assert user_doc.exists
    assert user_doc.to_dict().get('role') == 'SuperAdmin'
    assert user_doc.to_dict().get('org_id') == 'sapthagiri-nps-university'


def test_onboarding_wizard_save(client, mock_db):
    """Test onboarding wizard configures organization settings."""
    mock_db.collection('organizations').document('test-org').set({
        'name': 'Test Org',
        'slug': 'test-org',
        'plan': 'free'
    })
    
    with client.session_transaction() as sess:
        sess['user_id'] = 'kiran@snpsu.edu'
        sess['role'] = 'SuperAdmin'
        sess['org_id'] = 'test-org'
        
    resp = client.post('/onboarding/wizard',
                       data=json.dumps({
                           'primary_color': '#ff0000',
                           'logo_url': 'https://example.com/logo.png',
                           'departments': ['CSE', 'ECE']
                       }),
                       content_type='application/json')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data.get('status') == 'success'
    assert '/coordinator/dashboard' in data.get('redirect')
    
    # Confirm configuration written to DB
    org = mock_db.collection('organizations').document('test-org').get().to_dict()
    assert org.get('logo_url') == 'https://example.com/logo.png'
    assert org.get('settings', {}).get('primary_color') == '#ff0000'
    assert 'CSE' in org.get('settings', {}).get('departments', [])


def test_gamification_leaderboards(auth_client, mock_db):
    """Test leaderboard route yields successful HTML render and correct JSON API metrics."""
    # Set up some dummy students with different XP and departments
    mock_db.collection('users').document('stud1@test.edu').set({
        'name': 'Student One',
        'role': 'Student',
        'xp': 150,
        'department': 'CSE',
        'college': 'SNPSU'
    })
    mock_db.collection('users').document('stud2@test.edu').set({
        'name': 'Student Two',
        'role': 'Student',
        'xp': 350,
        'department': 'ECE',
        'college': 'SNPSU'
    })
    mock_db.collection('users').document('stud3@test.edu').set({
        'name': 'Student Three',
        'role': 'Student',
        'xp': 50,
        'department': 'CSE',
        'college': 'SNPSU'
    })
    
    # 1. Test HTML view
    resp = auth_client.get('/gamification/leaderboard')
    assert resp.status_code == 200
    assert b'Hall of Fame' in resp.data
    assert b'Student One' in resp.data
    assert b'Student Two' in resp.data
    
    # 2. Test JSON API view
    api_resp = auth_client.get('/gamification/api/leaderboard')
    assert api_resp.status_code == 200
    api_data = json.loads(api_resp.data)
    assert api_data.get('status') == 'success'
    
    # Check student rankings sorted descending by XP
    students = api_data.get('students', [])
    assert len(students) >= 4
    assert students[0]['name'] == 'Student Two'   # 350 XP
    assert students[1]['name'] == 'Student One'   # 150 XP
    assert students[2]['name'] == 'Test Student'  # 100 XP
    assert students[3]['name'] == 'Student Three' # 50 XP
    
    # Check department stats (CSE total: 200 XP, ECE total: 350 XP)
    depts = api_data.get('departments', [])
    assert depts[0]['name'] == 'ECE'
    assert depts[0]['total_xp'] == 350
    assert depts[1]['name'] == 'CSE'
    assert depts[1]['total_xp'] == 200


def test_xp_triggers_registration_and_checkin(client, mock_db, sample_event):
    """Test user registration awards +50 XP and ticket scanner check-in awards +150 XP."""
    # Register a new student
    mock_db.collection('users').document('stud_xp@test.edu').set({
        'name': 'XP Student',
        'role': 'Student',
        'xp': 0,
        'department': 'CSE'
    })
    
    # 1. Trigger registration (simulated payment)
    with client.session_transaction() as sess:
        sess['pending_reg_data'] = {
            'event_id': sample_event,
            'lead_email': 'stud_xp@test.edu',
            'lead_name': 'XP Student',
            'reg_id': 'REG-XP-111',
            'amount_paid': 100
        }
    
    client.post('/payment/process', data={'event_id': sample_event, 'amount': 100})
    
    # Check XP is +50
    user = mock_db.collection('users').document('stud_xp@test.edu').get().to_dict()
    assert user.get('xp') == 50
    
    # 2. Trigger check-in via verify endpoint
    # Pre-authorize payment status
    mock_db.collection('registrations').document('REG-XP-111').update({'payment_status': 'Paid'})
    
    # Scan/Verify ticket (which marks Present)
    client.get('/ticket/verify/REG-XP-111')
    
    # Check XP is 50 + 150 = 200
    user_after = mock_db.collection('users').document('stud_xp@test.edu').get().to_dict()
    assert user_after.get('xp') == 200


def test_sla_uptime_page(client, mock_db):
    """Test public SLA Status uptime page renders successfully."""
    resp = client.get('/compliance/sla')
    assert resp.status_code == 200
    assert b'All Systems Operational' in resp.data
    assert b'Stripe Gateway' in resp.data
    assert b'SLA Commitment' in resp.data


def test_seo_json_ld_event_metadata(client, mock_db, sample_event):
    """Test event details page includes JSON-LD structured schema metadata."""
    resp = client.get(f'/event/{sample_event}')
    assert resp.status_code == 200
    assert b'application/ld+json' in resp.data
    assert b'https://schema.org' in resp.data
    assert b'OfflineEventAttendanceMode' in resp.data
    assert b'Tech Hackathon 2026' in resp.data
