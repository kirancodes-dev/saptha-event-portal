import firebase_admin
from firebase_admin import credentials, firestore

# 1. Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def delete_collection(coll_ref, batch_size):
    docs = coll_ref.limit(batch_size).stream()
    deleted = 0

    for doc in docs:
        print(f'Deleting doc {doc.id}...')
        doc.reference.delete()
        deleted = deleted + 1

    if deleted >= batch_size:
        return delete_collection(coll_ref, batch_size)

# --- EXECUTE DELETION ---
print("⚠️  WARNING: Deleting ALL Event and Registration Data...")

# 1. Delete Registrations
print("\n🗑️  Deleting Registrations...")
delete_collection(db.collection('registrations'), 10)

# 2. Delete Events
print("\n🗑️  Deleting Events...")
delete_collection(db.collection('events'), 10)

print("\n✅ All sample data has been successfully wiped.")