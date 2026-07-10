import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, '.')
from models import db

collections = [
    'events', 'registrations', 'announcements', 'event_forms',
    'teams', 'certificates', 'notifications', 'feedback', 'audit_log', 'users'
]

for col in collections:
    try:
        cnt = len(list(db.collection(col).stream()))
        print(f"Collection '{col}': {cnt} documents")
    except Exception as e:
        print(f"Error on '{col}': {e}")
