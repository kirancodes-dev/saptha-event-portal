"""
conftest.py — Shared pytest fixtures for SapthaEvent test suite

Provides mock Firestore, Flask test client, and common test data.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from collections import defaultdict

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════
# MOCK FIRESTORE
# ═══════════════════════════════════════════════════════════════════════════

class MockDocumentSnapshot:
    """Simulates a Firestore document snapshot."""
    def __init__(self, doc_id, data, exists=True):
        self.id = doc_id
        self._data = data
        self.exists = exists
        self.reference = MagicMock()
        self.reference.id = doc_id

    def to_dict(self):
        return self._data.copy() if self._data else {}


class MockDocumentReference:
    """Simulates a Firestore document reference."""
    def __init__(self, collection, doc_id, store):
        self._collection = collection
        self.id = doc_id
        self._store = store

    def get(self):
        data = self._store.get(self._collection, {}).get(self.id)
        if data is not None:
            return MockDocumentSnapshot(self.id, data, exists=True)
        return MockDocumentSnapshot(self.id, None, exists=False)

    def set(self, data, merge=False):
        if self._collection not in self._store:
            self._store[self._collection] = {}
        if merge and self.id in self._store[self._collection]:
            self._store[self._collection][self.id].update(data)
        else:
            self._store[self._collection][self.id] = data.copy()

    def update(self, data):
        if self._collection in self._store and self.id in self._store[self._collection]:
            self._store[self._collection][self.id].update(data)

    def delete(self):
        if self._collection in self._store:
            self._store[self._collection].pop(self.id, None)

    def collection(self, name):
        sub_key = f"{self._collection}/{self.id}/{name}"
        return MockCollectionReference(sub_key, self._store)


class MockQuery:
    """Simulates Firestore query results."""
    def __init__(self, docs):
        self._docs = list(docs)

    def stream(self):
        return iter(self._docs)

    def limit(self, n):
        return MockQuery(self._docs[:n])

    def order_by(self, field, direction=None):
        return self

    def where(self, *args, **kwargs):
        return self


class MockCollectionReference:
    """Simulates a Firestore collection reference."""
    def __init__(self, name, store):
        self._name = name
        self._store = store

    def document(self, doc_id):
        return MockDocumentReference(self._name, doc_id, self._store)

    def add(self, data):
        import uuid
        doc_id = str(uuid.uuid4())[:8]
        if self._name not in self._store:
            self._store[self._name] = {}
        self._store[self._name][doc_id] = data.copy()
        ref = MockDocumentReference(self._name, doc_id, self._store)
        return (None, ref)

    def where(self, *args, **kwargs):
        field = kwargs.get("field")
        docs = []
        for doc_id, data in self._store.get(self._name, {}).items():
            docs.append(MockDocumentSnapshot(doc_id, data))
        return MockQuery(docs)

    def order_by(self, field, direction=None):
        docs = []
        for doc_id, data in self._store.get(self._name, {}).items():
            docs.append(MockDocumentSnapshot(doc_id, data))
        return MockQuery(docs)

    def stream(self):
        docs = []
        for doc_id, data in self._store.get(self._name, {}).items():
            docs.append(MockDocumentSnapshot(doc_id, data))
        return iter(docs)

    def limit(self, n):
        return self


class MockFirestore:
    """In-memory mock of the Firestore client."""
    def __init__(self):
        self._store = {}

    def collection(self, name):
        return MockCollectionReference(name, self._store)

    def batch(self):
        return MockBatch(self._store)

    def _clear(self):
        self._store.clear()


class MockBatch:
    def __init__(self, store):
        self._ops = []
        self._store = store

    def set(self, ref, data):
        self._ops.append(("set", ref, data))

    def update(self, ref, data):
        self._ops.append(("update", ref, data))

    def commit(self):
        for op, ref, data in self._ops:
            if op == "set":
                ref.set(data)
            elif op == "update":
                ref.update(data)
        self._ops.clear()


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_db():
    """Provide a fresh in-memory Firestore mock."""
    return MockFirestore()


@pytest.fixture
def app(mock_db):
    """Create a Flask test application with mocked Firestore."""
    # Patch firebase before importing app
    with patch.dict(os.environ, {
        "FLASK_ENV": "development",
        "SECRET_KEY": "test-secret-key-for-pytest-12345",
        "JWT_SECRET_KEY": "test-jwt-secret-12345",
        "SUPER_ADMIN_EMAIL": "admin@test.edu",
        "SUPER_ADMIN_PASS": "TestAdmin123",
        "MASTER_SECRET_KEY": "test-master-key",
        "BASE_URL": "http://localhost:5001",
    }):
        with patch("firebase_admin._apps", {"[DEFAULT]": MagicMock()}):
            with patch("firebase_admin.credentials.Certificate"):
                with patch("firebase_admin.initialize_app"):
                    with patch("google.cloud.firestore_v1.client.Client", return_value=mock_db):
                        # Import app with mocked Firebase
                        import importlib
                        import app as app_module
                        importlib.reload(app_module)
                        app_module.db = mock_db
                        try:
                            import routes_exams
                            routes_exams.db = mock_db
                            import routes_hackathon
                            routes_hackathon.db = mock_db
                        except Exception:
                            pass

                        flask_app = app_module.app
                        flask_app.config["TESTING"] = True
                        flask_app.config["WTF_CSRF_ENABLED"] = False
                        flask_app.config["SERVER_NAME"] = "localhost:5001"

                        # Register new blueprints if not already
                        try:
                            from routes_api_v1 import api_v1_bp
                            if "api_v1" not in [bp.name for bp in flask_app.iter_blueprints()]:
                                flask_app.register_blueprint(api_v1_bp)
                                from flask_wtf.csrf import CSRFProtect
                                csrf = flask_app.extensions.get("csrf")
                                if csrf:
                                    csrf.exempt(api_v1_bp)
                        except Exception:
                            pass

                        yield flask_app


@pytest.fixture
def client(app):
    """Flask test client."""
    with app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(client, mock_db):
    """Authenticated test client with a test user in session."""
    from werkzeug.security import generate_password_hash
    mock_db.collection("users").document("student@test.edu").set({
        "name": "Test Student",
        "email": "student@test.edu",
        "role": "Student",
        "password_hash": generate_password_hash("TestPass123", method="pbkdf2:sha256"),
        "xp": 100,
        "badges": ["Participant"],
        "is_active": True,
    })

    with client.session_transaction() as sess:
        sess["user_id"] = "student@test.edu"
        sess["role"] = "Student"
        sess["name"] = "Test Student"

    return client


@pytest.fixture
def admin_client(client, mock_db):
    """Authenticated admin test client."""
    from werkzeug.security import generate_password_hash
    mock_db.collection("users").document("admin@test.edu").set({
        "name": "Test Admin",
        "email": "admin@test.edu",
        "role": "SuperAdmin",
        "password_hash": generate_password_hash("AdminPass123", method="pbkdf2:sha256"),
        "is_active": True,
    })

    with client.session_transaction() as sess:
        sess["user_id"] = "admin@test.edu"
        sess["role"] = "SuperAdmin"
        sess["name"] = "Test Admin"

    return client


@pytest.fixture
def sample_event(mock_db):
    """Create a sample event in the mock DB."""
    event_data = {
        "title": "Tech Hackathon 2026",
        "description": "48-hour coding challenge",
        "category": "Technical",
        "date": "2026-06-15",
        "deadline": "2026-06-10",
        "venue": "Main Auditorium",
        "status": "active",
        "entry_fee": 100,
        "fee": 100,
        "is_team_event": True,
        "min_team_size": 2,
        "max_team_size": 4,
        "registration_count": 5,
        "rules": "Standard hackathon rules",
        "prizes": "1st: ₹10,000",
        "created_by": "spoc@test.edu",
    }
    mock_db.collection("events").document("evt_test_001").set(event_data)
    return "evt_test_001"


@pytest.fixture
def jwt_token(app):
    """Generate a valid JWT token for API testing."""
    with app.app_context():
        from auth_jwt import create_access_token
        return create_access_token("student@test.edu", "Student")


@pytest.fixture
def admin_jwt_token(app):
    """Generate a valid admin JWT token."""
    with app.app_context():
        from auth_jwt import create_access_token
        return create_access_token("admin@test.edu", "SuperAdmin")
