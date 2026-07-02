"""
tests/test_spoc_features.py — Unit tests for SPOC check-in and certificate settings
"""

import json
import datetime
from unittest.mock import patch, MagicMock


def test_spoc_scan_page_loads(client, mock_db):
    mock_event = MagicMock()
    mock_event.exists = True
    mock_event.to_dict.return_value = {
        'title': 'Test Hackathon',
        'spoc_id': 'spoc@test.com',
        'date': datetime.date.today().isoformat()
    }
    
    mock_reg1 = MagicMock()
    mock_reg1.id = 'reg-1'
    mock_reg1.to_dict.return_value = {
        'lead_name': 'Alice',
        'lead_email': 'alice@test.com',
        'team_name': 'Team A',
        'attendance': 'Absent',
        'checkin_time': ''
    }
    
    with patch.object(mock_db, 'collection') as mock_collection:
        mock_events = MagicMock()
        mock_events.document.return_value.get.return_value = mock_event
        
        mock_regs = MagicMock()
        mock_regs.where.return_value.stream.return_value = [mock_reg1]
        
        def mock_collection_side_effect(name):
            if name == 'events':
                return mock_events
            elif name == 'registrations':
                return mock_regs
            return MagicMock()
            
        mock_collection.side_effect = mock_collection_side_effect
        
        with client.session_transaction() as sess:
            sess['user_id'] = 'spoc@test.com'
            sess['role'] = 'ClubSPOC'
            sess['name'] = 'Test SPOC'
            
        resp = client.get('/spoc/scan/evt-1')
        assert resp.status_code == 200
        assert b'QR Scanner & Check-in' in resp.data
        assert b'Manual List' in resp.data


def test_spoc_checkin_api_succeeds(client, mock_db):
    mock_event = MagicMock()
    mock_event.exists = True
    mock_event.to_dict.return_value = {
        'title': 'Test Hackathon',
        'spoc_id': 'spoc@test.com',
        'date': datetime.date.today().isoformat()
    }
    
    mock_reg = MagicMock()
    mock_reg.exists = True
    mock_reg.to_dict.return_value = {
        'event_id': 'evt-1',
        'lead_name': 'Alice',
        'lead_email': 'alice@test.com',
        'attendance': 'Absent'
    }
    
    with patch.object(mock_db, 'collection') as mock_collection:
        mock_events = MagicMock()
        mock_events.document.return_value.get.return_value = mock_event
        
        mock_regs = MagicMock()
        mock_regs.document.return_value.get.return_value = mock_reg
        mock_regs.document.return_value.update = MagicMock()
        
        def mock_collection_side_effect(name):
            if name == 'events':
                return mock_events
            elif name == 'registrations':
                return mock_regs
            return MagicMock()
            
        mock_collection.side_effect = mock_collection_side_effect
        
        with client.session_transaction() as sess:
            sess['user_id'] = 'spoc@test.com'
            sess['role'] = 'ClubSPOC'
            
        resp = client.post('/spoc/api/checkin/evt-1/reg-1')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['status'] == 'success'
        assert data['name'] == 'Alice'


def test_spoc_end_event_saves_cert_config(client, mock_db):
    mock_event = MagicMock()
    mock_event.exists = True
    mock_event.to_dict.return_value = {
        'title': 'Test Hackathon',
        'spoc_id': 'spoc@test.com'
    }
    
    with patch.object(mock_db, 'collection') as mock_collection:
        mock_events = MagicMock()
        mock_events.document.return_value.get.return_value = mock_event
        mock_events.document.return_value.update = MagicMock()
        
        mock_regs = MagicMock()
        mock_regs.where.return_value.stream.return_value = []
        
        def mock_collection_side_effect(name):
            if name == 'events':
                return mock_events
            elif name == 'registrations':
                return mock_regs
            return MagicMock()
            
        mock_collection.side_effect = mock_collection_side_effect
        
        with client.session_transaction() as sess:
            sess['user_id'] = 'spoc@test.com'
            sess['role'] = 'ClubSPOC'
            sess['email'] = 'spoc@test.com'
            
        resp = client.post('/spoc/end_event/evt-1', data={
            'template_id': '3',
            'issued_by': 'President John'
        })
        assert resp.status_code == 302
        
        # Extract the mock call to document.update
        update_calls = mock_events.document.return_value.update.call_args_list
        assert len(update_calls) > 0
        updated_fields = update_calls[0][0][0]
        assert updated_fields['status'] == 'completed'
        assert updated_fields['cert_template_id'] == 3
        assert updated_fields['cert_issued_by'] == 'President John'


def test_spoc_marketing_event_writer_fallback(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 'spoc@test.com'
        sess['role'] = 'ClubSPOC'
        
    resp = client.post('/spoc/marketing/event_writer', 
                       data=json.dumps({'title': 'New coding event'}),
                       content_type='application/json')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert 'description' in data
    assert 'rules' in data
    assert 'New coding event' in data['description']


def test_spoc_edit_event_updates_rules(client, mock_db):
    mock_event = MagicMock()
    mock_event.exists = True
    mock_event.to_dict.return_value = {
        'title': 'Old Title',
        'description': 'Old Description',
        'rules': 'Old Rules',
        'spoc_id': 'spoc@test.com'
    }

    with patch.object(mock_db, 'collection') as mock_collection:
        mock_events = MagicMock()
        mock_events.document.return_value.get.return_value = mock_event
        mock_events.document.return_value.update = MagicMock()

        def mock_collection_side_effect(name):
            if name == 'events':
                return mock_events
            return MagicMock()

        mock_collection.side_effect = mock_collection_side_effect

        with client.session_transaction() as sess:
            sess['user_id'] = 'spoc@test.com'
            sess['role'] = 'ClubSPOC'

        # Edit the event by updating description, title and rules
        resp = client.post('/spoc/edit_event/evt-1', data={
            'title': 'New Title',
            'description': 'New Description',
            'rules': 'New Rules list here'
        })
        assert resp.status_code == 302
        assert resp.location.endswith('/spoc/dashboard#event-evt-1')

        # Check document.update call arguments
        update_calls = mock_events.document.return_value.update.call_args_list
        assert len(update_calls) > 0
        updated_fields = update_calls[0][0][0]
        assert updated_fields['title'] == 'New Title'
        assert updated_fields['description'] == 'New Description'
        assert updated_fields['rules'] == 'New Rules list here'


