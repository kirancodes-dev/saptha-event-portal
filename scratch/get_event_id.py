import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, '.')
from models import db
from google.cloud.firestore_v1.base_query import FieldFilter

docs = list(db.collection('events').where(filter=FieldFilter('title', '==', 'Classical Dance Recital')).stream())
for d in docs:
    print(f"Classical Dance Recital ID: {d.id}")
