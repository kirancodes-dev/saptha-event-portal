try:
    import firebase_admin
except ImportError:
    firebase_admin = None
try:
    from firebase_admin import credentials, firestore
except ImportError:
    credentials = firestore = auth = None

# 1. Connect using your key
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

# 2. Test Write
db = firestore.client()
db.collection('test_setup').add({'message': 'Hello Firebase!', 'timestamp': 2026})

print("✅ Connection Successful! Check your Firestore dashboard.")
