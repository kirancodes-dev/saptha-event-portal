"""
tests/conftest.py — Shared pytest fixtures
==========================================
Mocks Firebase/Firestore so tests run without a real GCP project.
All fixtures are function-scoped unless noted.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

# ── Environment stubs (must be set before importing app) ──
os.environ.setdefault('FLASK_ENV',          'testing')
os.environ.setdefault('SECRET_KEY',         'test-secret-key')
os.environ.setdefault('SESSION_TYPE',       'filesystem')
os.environ.setdefault('FIREBASE_CREDENTIALS', '')
os.environ.setdefault('SUPER_ADMIN_EMAIL',  'admin@test.local')
os.environ.setdefault('SUPER_ADMIN_PASS',   'test-pass')
os.environ.setdefault('MASTER_SECRET_KEY',  'test-master-key')
os.environ.setdefault('NO_SCHEDULER',       'true')
os.environ.setdefault('CELERY_BROKER_URL',  'memory://')
os.environ.setdefault('CELERY_RESULT_BACKEND', 'cache+memory://')
os.environ.setdefault('RATELIMIT_STORAGE_URL', 'memory://')


@pytest.fixture(scope='session')
def mock_firebase():
    """Patch firebase_admin so the app boots without real credentials."""
    with patch('firebase_admin.initialize_app'), \
         patch('firebase_admin._apps', {'[DEFAULT]': MagicMock()}), \
         patch('firebase_admin.credentials.Certificate', return_value=MagicMock()):
        yield


@pytest.fixture(scope='session')
def mock_db():
    """Return a MagicMock Firestore client wired into models.db."""
    db_mock = MagicMock()
    # Default: collection().limit().stream() returns empty list
    db_mock.collection.return_value.limit.return_value.stream.return_value = iter([])
    db_mock.collection.return_value.where.return_value.stream.return_value = iter([])
    db_mock.collection.return_value.document.return_value.get.return_value.exists = False
    return db_mock


@pytest.fixture(scope='session')
def app(mock_firebase, mock_db):
    """Create the Flask app with all Firebase calls mocked."""
    with patch('firebase_admin.firestore.client', return_value=mock_db), \
         patch('models.db', mock_db):
        from app import app as flask_app
        flask_app.config.update({
            'TESTING':              True,
            'WTF_CSRF_ENABLED':     False,
            'SESSION_TYPE':         'filesystem',
            'RATELIMIT_ENABLED':    False,
        })
        yield flask_app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def auth_headers():
    """Helper: returns a dict you can pass as headers for JSON API calls."""
    return {'Content-Type': 'application/json', 'Accept': 'application/json'}


@pytest.fixture
def student_session(client):
    """Log in as a student by directly setting session variables."""
    with client.session_transaction() as sess:
        sess['user_id'] = 'student@test.local'
        sess['name']    = 'Test Student'
        sess['role']    = 'Student'
    return client


@pytest.fixture
def admin_session(client):
    """Log in as an admin."""
    with client.session_transaction() as sess:
        sess['user_id'] = 'admin@test.local'
        sess['name']    = 'Test Admin'
        sess['role']    = 'SuperAdmin'
    return client
