import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FirebaseWrapper:
    """
    Enterprise Data Wrapper.
    Converts Firestore documents into Object-like entities for safe Jinja rendering.
    """
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data if data else {}
    
    def __getattr__(self, name):
        # Graceful fallback for missing keys
        val = self._data.get(name)
        return val if val is not None else ''
        
    def __getitem__(self, name):
        return self._data.get(name, '')
    
    def to_dict(self):
        return self._data

# Initialize Firebase Connection
if not firebase_admin._apps:
    try:
        cred = None
        # Priority 1: Local File
        if os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
            logger.info("Loaded credentials from file.")
        
        # Priority 2: Env Variable (Cloud)
        elif os.environ.get('FIREBASE_CREDENTIALS'):
            cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
            cred = credentials.Certificate(cred_dict)
            logger.info("Loaded credentials from ENV.")
        
        if cred:
            firebase_admin.initialize_app(cred)
        else:
            logger.warning("No Firebase credentials found.")
            
    except Exception as e:
        logger.error(f"Firebase Init Error: {e}")

db = firestore.client() if firebase_admin._apps else None