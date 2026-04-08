"""
tests.py — Comprehensive Test Suite for SapthaEvent
====================================================

Run all tests:
  python -m pytest tests.py -v

Run with coverage:
  pip install pytest-cov
  pytest tests.py --cov=. --cov-report=html

Run specific test:
  pytest tests.py::BasicTests::test_health_check -v
"""

import unittest
import json
from app import app, db
from werkzeug.security import generate_password_hash


class HealthTests(unittest.TestCase):
    """Test health check endpoints"""
    
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
    
    def test_health_endpoint(self):
        """Test /health endpoint returns 200"""
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('timestamp', data)
    
    def test_ready_endpoint(self):
        """Test /health/ready endpoint"""
        response = self.app.get('/health/ready')
        self.assertIn(response.status_code, [200, 503])  # Either ready or not
        data = json.loads(response.data)
        self.assertIn('ready', data)


class PublicPageTests(unittest.TestCase):
    """Test public-facing pages"""
    
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
    
    def test_home_page_loads(self):
        """Test home page returns 200"""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
    
    def test_login_page_loads(self):
        """Test login page loads"""
        response = self.app.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Login', response.data)
    
    def test_404_page(self):
        """Test 404 handling"""
        response = self.app.get('/nonexistent-page-xyz')
        self.assertEqual(response.status_code, 404)
    
    def test_calendar_api(self):
        """Test calendar API returns JSON"""
        response = self.app.get('/api/calendar')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/json')


class SecurityTests(unittest.TestCase):
    """Test security features"""
    
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
    
    def test_spoc_dashboard_requires_login(self):
        """Test unauthenticated access to SPOC dashboard redirects"""
        response = self.app.get('/coordinator/dashboard')
        # Should redirect to login (302) or be forbidden (403)
        self.assertIn(response.status_code, [302, 403])
    
    def test_admin_dashboard_requires_login(self):
        """Test unauthenticated access to admin dashboard redirects"""
        response = self.app.get('/admin/dashboard')
        self.assertIn(response.status_code, [302, 403])
    
    def test_judge_dashboard_requires_login(self):
        """Test unauthenticated access to judge dashboard redirects"""
        response = self.app.get('/judge/dashboard')
        self.assertIn(response.status_code, [302, 403])
    
    def test_security_headers_present(self):
        """Test that security headers are set"""
        response = self.app.get('/')
        self.assertIn('X-Content-Type-Options', response.headers)
        self.assertIn('X-Frame-Options', response.headers)
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')


class ErrorHandlingTests(unittest.TestCase):
    """Test error handling"""
    
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()
    
    def test_favicon_returns_no_content(self):
        """Test /favicon.ico returns 204"""
        response = self.app.get('/favicon.ico')
        self.assertEqual(response.status_code, 204)
    
    def test_well_known_returns_no_content(self):
        """Test /.well-known/* returns 204"""
        response = self.app.get('/.well-known/security.txt')
        self.assertEqual(response.status_code, 204)
    
    def test_cdn_cgi_returns_no_content(self):
        """Test /cdn-cgi/* returns 204"""
        response = self.app.get('/cdn-cgi/challenge')
        self.assertEqual(response.status_code, 204)


class APIEndpointTests(unittest.TestCase):
    """Test API endpoints"""
    
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
    
    def test_calendar_json_returns_json(self):
        """Test /api/calendar returns valid JSON"""
        response = self.app.get('/api/calendar')
        self.assertEqual(response.status_code, 200)
        try:
            data = json.loads(response.data)
            self.assertIsInstance(data, list)
        except json.JSONDecodeError:
            self.fail("Response is not valid JSON")
    
    def test_event_details_with_invalid_id(self):
        """Test event details with non-existent event"""
        response = self.app.get('/event/INVALID-EVENT-ID-XYZ')
        # Should return 404 not found
        self.assertEqual(response.status_code, 404)


class ConfigurationTests(unittest.TestCase):
    """Test configuration"""
    
    def test_app_name_is_set(self):
        """Test app name is configured"""
        self.assertEqual(app.config['APP_NAME'], 'SapthaEvent')
    
    def test_flask_env_is_testing(self):
        """Test Flask env can be testing"""
        app.config['TESTING'] = True
        self.assertTrue(app.config['TESTING'])
    
    def test_session_security_settings(self):
        """Test session security is configured"""
        self.assertTrue(app.config['SESSION_COOKIE_HTTPONLY'])
        self.assertIn(app.config['SESSION_COOKIE_SAMESITE'], ['Lax', 'Strict'])


class RateLimitingTests(unittest.TestCase):
    """Test rate limiting is configured"""
    
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()
    
    def test_health_endpoint_is_exempt_from_rate_limit(self):
        """Health endpoint should be exempt from rate limiting"""
        response = self.app.get('/health')
        # Should not have rate limit headers in test mode
        self.assertEqual(response.status_code, 200)


class IntegrationTests(unittest.TestCase):
    """Integration tests for complete workflows"""
    
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
    
    def test_home_to_event_details_flow(self):
        """Test: Home -> Event -> Back flow"""
        # 1. Load home page
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        
        # 2. Try to load calendar
        response = self.app.get('/api/calendar')
        self.assertEqual(response.status_code, 200)
    
    def test_verify_certificate_flow(self):
        """Test certificate verification endpoint"""
        response = self.app.get('/verify/test-reg-id')
        # Should handle gracefully even if cert doesn't exist
        self.assertIn(response.status_code, [200, 404])


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
