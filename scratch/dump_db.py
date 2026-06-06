import os
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

print("==================================================")
print("Firestore Database Inspector")
print(f"Project ID: {cred.project_id}")
print("==================================================")

collections = ['users', 'events', 'registrations', 'waitlists', 'announcements']

for coll_name in collections:
    docs = list(db.collection(coll_name).stream())
    print(f"Collection: {coll_name:<15} | Document Count: {len(docs)}")
    if docs:
        print("  Sample Document IDs:")
        for doc in docs[:3]:
            print(f"    - {doc.id}")
print("==================================================")
