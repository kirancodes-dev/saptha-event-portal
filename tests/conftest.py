"""
conftest.py — Shared pytest fixtures for SapthaEvent test suite

Provides mock Firestore, Flask test client, and common test data.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure tests run with non-production development settings and no HTTPS redirects
os.environ.setdefault("FLASK_ENV", "development")
os.environ["FORCE_HTTPS"] = "false"

# Tests never use a developer's real outbound credentials or services (BLK-05).
# app.py calls load_dotenv(), which never overrides a variable that's already
# set, so blanking these before any app import keeps .env's values out.
OUTBOUND_CREDENTIALS = (
    'MAIL_USER', 'MAIL_PASS', 'MAIL_PASSWORD', 'BREVO_API_KEY', 'RESEND_API_KEY',
    'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_FROM',
    'GEMINI_API_KEY', 'GOOGLE_API_KEY',
    'RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET', 'STRIPE_SECRET_KEY',
    'VAPID_PRIVATE_KEY', 'VAPID_PUBLIC_KEY',
    'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_STORAGE_BUCKET_NAME', 'GCS_BUCKET_NAME',
    'STORAGE_TYPE', 'SUPABASE_URL', 'SUPABASE_KEY', 'SENTRY_DSN',
    'OAUTH_GOOGLE_CLIENT_ID', 'OAUTH_GOOGLE_CLIENT_SECRET',
    'OAUTH_MICROSOFT_CLIENT_ID', 'OAUTH_MICROSOFT_CLIENT_SECRET',
    'ZOHO_AUTH_TOKEN', 'CATALYST_AUTH_TOKEN',
    'CLOUD_SQL_INSTANCE', 'DB_PASS', 'FIREBASE_CREDENTIALS', 'GOOGLE_APPLICATION_CREDENTIALS',
)
for _name in OUTBOUND_CREDENTIALS:
    os.environ[_name] = ''
# Background tasks run inline, never on a real broker (CI and a developer's
# .env may point CELERY_BROKER_URL at Redis, where nothing would run them).
os.environ['CELERY_BROKER_URL'] = 'memory://'
os.environ['CELERY_RESULT_BACKEND'] = 'cache+memory://'

# Point the SQL layer at a throwaway database before any app module is
# imported, so tests never touch a developer's local data. Set
# TEST_DATABASE_URL (e.g. an empty PostgreSQL database) to test against it.
import tempfile  # noqa: E402
_TEST_DB_DIR = tempfile.mkdtemp(prefix='saptha-test-')
os.environ['DATABASE_URL'] = (os.environ.get('TEST_DATABASE_URL')
                              or f"sqlite:///{os.path.join(_TEST_DB_DIR, 'test.db')}")
os.environ.setdefault('DATABASE_TYPE', 'postgres')
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-pytest-only-0123456789')


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
            target = self._store[self._collection][self.id]
            for k, v in data.items():
                if hasattr(v, "value") and "Increment" in type(v).__name__:
                    base = target.get(k, 0)
                    try:
                        base = int(base)
                    except (ValueError, TypeError):
                        base = 0
                    target[k] = base + v.value
                else:
                    target[k] = v

    def delete(self):
        if self._collection in self._store:
            self._store[self._collection].pop(self.id, None)

    def collection(self, name):
        sub_key = f"{self._collection}/{self.id}/{name}"
        return MockCollectionReference(sub_key, self._store)


def _matches_filter(doc_data, *args, **kwargs):
    field, op, val = None, None, None
    if args and len(args) >= 3:
        field, op, val = args[0], args[1], args[2]
    elif "filter" in kwargs and kwargs["filter"] is not None:
        filt = kwargs["filter"]
        field = getattr(filt, "field_path", None) or getattr(filt, "field", None)
        op = getattr(filt, "op_string", None) or getattr(filt, "operator", None) or "=="
        val = getattr(filt, "value", None)
    elif "field" in kwargs:
        field = kwargs.get("field")
        op = kwargs.get("op", "==")
        val = kwargs.get("value")

    if not field:
        return True

    doc_val = doc_data.get(field)
    if op in ("==", "="):
        return doc_val == val
    elif op == "!=":
        return doc_val != val
    elif op == "in":
        return doc_val in val if isinstance(val, (list, tuple, set)) else False
    elif op == ">":
        return doc_val is not None and val is not None and doc_val > val
    elif op == ">=":
        return doc_val is not None and val is not None and doc_val >= val
    elif op == "<":
        return doc_val is not None and val is not None and doc_val < val
    elif op == "<=":
        return doc_val is not None and val is not None and doc_val <= val
    return True


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
        filtered = [d for d in self._docs if _matches_filter(d.to_dict(), *args, **kwargs)]
        return MockQuery(filtered)


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
        docs = []
        for doc_id, data in self._store.get(self._name, {}).items():
            if _matches_filter(data, *args, **kwargs):
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

@pytest.fixture(autouse=True)
def _fresh_login_throttle():
    """Every test client logs in from 127.0.0.1, so one test's failed logins
    would throttle the next test's (BLK-13). Start each test with no counters."""
    throttle = sys.modules.get('services_login_throttle')
    app_module = sys.modules.get('app')
    if throttle is not None and app_module is not None:
        with app_module.app.app_context():
            throttle.reset_all()
    yield


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
        "FORCE_HTTPS": "false",
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


# ═══════════════════════════════════════════════════════════════════════════
# REAL DATABASE LAYER — the SQL adapter the app uses (no mock db)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def real_app(monkeypatch):
    import app as app_module
    import models
    import routes_forms

    # Other tests' fixtures swap in a mock db; use the real SQL adapter here
    monkeypatch.setattr(app_module, 'db', models.db)
    for name in ('routes_exams', 'routes_hackathon'):
        module = __import__(name)
        monkeypatch.setattr(module, 'db', models.db)

    # No outbound email/WhatsApp from tests (every email goes through _send)
    import utils_email
    monkeypatch.setattr(utils_email, '_send', lambda *a, **k: True)
    monkeypatch.setattr(routes_forms, 'send_registration_confirmed_email', lambda *a, **k: None)
    monkeypatch.setattr(routes_forms, 'send_ticket_whatsapp', lambda *a, **k: None, raising=False)

    flask_app = app_module.app
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    monkeypatch.setitem(flask_app.config, 'SERVER_NAME', None)
    from extensions import limiter
    monkeypatch.setattr(limiter, 'enabled', False, raising=False)
    return flask_app, models.db

