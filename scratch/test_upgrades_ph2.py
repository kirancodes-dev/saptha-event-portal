import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from app import app
from models import DATABASE_TYPE

class TestUpgradesPhase2(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

    def test_database_default(self):
        print(f"Active default database: {DATABASE_TYPE}")
        self.assertIn(DATABASE_TYPE, ('postgres', 'postgresql', 'supabase'))

    def test_kiosk_search_empty(self):
        # Test empty kiosk search
        response = self.client.post('/checkin/kiosk/search', json={'query': ''})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 0)

    def test_kiosk_search_nonexistent(self):
        response = self.client.post('/checkin/kiosk/search', json={'query': 'nonexistent_test_query_email_or_id'})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['results']), 0)

    def test_matchmaker_jaccard_fallback(self):
        # We temporarily unset GEMINI_API_KEY to force the Jaccard fallback path
        old_key = self.app.config.get('GEMINI_API_KEY')
        self.app.config['GEMINI_API_KEY'] = ''
        
        # We need a logged in session. Let's force a user_id in the session
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'test_student@sapthagiri.edu'
            sess['role'] = 'Student'
            
        response = self.client.post('/participant/matchmaker/api/match', json={
            'skills': ['Python', 'Figma'],
            'interests': ['AI Hackathon']
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertGreater(len(data['matches']), 0)
        # Verify that match insight is populated by fallback
        first_match = data['matches'][0]
        self.assertIn('match_reason', first_match)
        self.assertIn('match_score', first_match)
        print(f"Fallback first match: {first_match['name']} - Score: {first_match['match_score']}% - Reason: {first_match['match_reason']}")
        
        # Restore key
        if old_key:
            self.app.config['GEMINI_API_KEY'] = old_key

if __name__ == '__main__':
    unittest.main()
