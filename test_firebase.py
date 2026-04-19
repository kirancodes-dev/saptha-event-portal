import firebase_admin
from firebase_admin import credentials, firestore

# 1. Connect using your key
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

# 2. Test Write
db = firestore.client()
db.collection('test_setup').add({'message': 'Hello Firebase!', 'timestamp': 2026})

print("✅ Connection Successful! Check your Firestore dashboard.")