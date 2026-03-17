"""
models.py — Firebase Firestore client + utility wrapper.

`db` is imported by every route file.
`FirebaseWrapper` lets you access Firestore document fields as attributes,
exactly like an ORM object (e.g. event.title, event.date).
"""
import firebase_admin
from firebase_admin import credentials, firestore
import os


# =========================================================
# FIREBASE INITIALISATION (idempotent)
# =========================================================
if not firebase_admin._apps:
    key_path = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()


# =========================================================
# FIRESTORE DOCUMENT WRAPPER
# =========================================================
class FirebaseWrapper:
    """
    Wraps a Firestore document dict so templates can access fields
    with dot notation: {{ event.title }}  instead of {{ event['title'] }}

    Usage:
        doc  = db.collection('events').document(event_id).get()
        event = FirebaseWrapper(doc.id, doc.to_dict())
        print(event.title, event.date)
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