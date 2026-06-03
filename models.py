"""
models.py — Firebase Firestore client + utility wrapper.

`db` is imported by every route file.
`FirebaseWrapper` lets you access Firestore document fields as attributes,
exactly like an ORM object (e.g. event.title, event.date).
"""
import warnings
# Suppress deprecation warnings from Firestore SDK for using positional arguments in .where()
warnings.filterwarnings(
    "ignore",
    message="Detected filter using positional arguments.*",
    category=UserWarning,
    module="google.cloud.firestore"
)

import firebase_admin
from firebase_admin import credentials, firestore
from typing import Any, cast
import os


# =========================================================
# DATABASE RESOLUTION (Firestore vs. Supabase SQL)
# =========================================================
DATABASE_TYPE = os.environ.get('DATABASE_TYPE', 'firestore').lower()

db: Any = None

if DATABASE_TYPE in ('postgres', 'postgresql', 'supabase'):
    try:
        from db_adapter import SQLFirestoreAdapter
        db = SQLFirestoreAdapter()
    except Exception as exc:
        # Fallback to printing error
        import logging
        logging.getLogger(__name__).error("Failed to initialize SQL Firestore Adapter: %s", exc)
else:
    # Initialize standard Firebase Firestore
    if not firebase_admin._apps:
        key_path = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')
        if os.path.exists(key_path):
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred)
    try:
        db = cast(Any, firestore.client())
    except Exception:
        pass


# =========================================================
# FIRESTORE DOCUMENT WRAPPER
# =========================================================
class FirebaseWrapper:
    """
    Wraps a Firestore document dict so templates can access fields
    with dot notation (event.title) instead of dict notation (event['title']).

    Pass the document id and its to_dict() result to the constructor.
    Every field becomes an attribute; use .get(key, default) for safe access.
    """

    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data or {}
        # Expose every key as an attribute
        for key, value in self._data.items():
            if not key.startswith('_') and not hasattr(self, key):
                setattr(self, key, value)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def to_dict(self) -> dict:
        return self._data

    def __repr__(self):
        return f"<FirebaseWrapper id={self.id}>"
