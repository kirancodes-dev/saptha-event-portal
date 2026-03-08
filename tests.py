import unittest
from app import app

class BasicTests(unittest.TestCase):

    # 1. Setup the test client
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()

    # 2. Test: Does the Home Page load?
    def test_home_page(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)

    # 3. Test: Does the Login Page load?
    def test_login_page(self):
        response = self.app.get('/login')
        self.assertEqual(response.status_code, 200)
        # Check if the text "Login" exists on the page
        self.assertIn(b'Login', response.data)

    # 4. Test: Security Check
    # Trying to access SPOC dashboard without login should redirect (302)
    def test_spoc_access_denied(self):
        response = self.app.get('/spoc/dashboard')
        self.assertEqual(response.status_code, 302) 

if __name__ == "__main__":
    unittest.main()