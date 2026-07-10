import os
import sys
sys.path.insert(0, '/Users/kiranbiradar/Desktop/saptha-event-portal')

from app import app
from unittest.mock import patch, MagicMock

# Configure test mode
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

client = app.test_client()

@patch('routes_spoc.db')
def test_render(mock_db):
    # Mock firebase calls
    mock_event = MagicMock()
    mock_event.id = 'evt_test_1'
    mock_event.to_dict.return_value = {
        'title': 'Test Event',
        'category': 'Technical',
        'spoc_id': 'biradark543@gmail.com',
        'date': '2026-06-15',
        'venue': 'Main Auditorium',
        'registration_count': 10,
        'attendance_count': 5,
        'limits': {'max_participants': 100},
        'fees': {'regular': 100},
        'staff': []
    }
    
    mock_query = MagicMock()
    mock_query.stream.return_value = [mock_event]
    
    # Setup chain of mocks
    mock_col = MagicMock()
    mock_col.where.return_value.stream = mock_query.stream
    mock_col.stream = mock_query.stream
    mock_db.collection.return_value = mock_col
    
    # Mock registration stream for default fallback
    mock_db.collection.return_value.where.return_value.stream.return_value = []

    with client.session_transaction() as sess:
        sess['user_id'] = 'biradark543@gmail.com'
        sess['role'] = 'ClubSPOC'
        sess['name'] = 'Kiran Biradar'
        sess['category'] = 'Technical'

    resp = client.get('/spoc/dashboard')
    print("Response Status Code:", resp.status_code)
    if resp.status_code != 200:
        print("Error details:")
        print(resp.data.decode('utf-8', errors='ignore')[:2000])
    assert resp.status_code == 200
    print("✅ SPOC Dashboard template rendered successfully!")

if __name__ == '__main__':
    test_render()
