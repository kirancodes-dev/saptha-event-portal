"""
wipe_firestore.py — Bulk delete all Firestore data except super admin users.

Preserves:
  - users/admin@snpsu.edu.in        (role=SuperAdmin)
  - users/superadmin@snpsu.edu.in   (role=SuperAdmin)
  - users/wCUdejsxWlYpnXt7N3hdDXaKods2 (role=Super Admin, email=admin@portal.com)

Deletes entirely:
  audit_log, event_forms, events, form_submissions, registrations, test_setup

Run from project root:  python scripts/wipe_firestore.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import firebase_admin
from firebase_admin import credentials, firestore

# ── Init Firebase ────────────────────────────────────────────────────────────
KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'serviceAccountKey.json')
if not os.path.exists(KEY_FILE):
    print(f"ERROR: serviceAccountKey.json not found at {KEY_FILE}")
    sys.exit(1)

if not firebase_admin._apps:
    cred = credentials.Certificate(KEY_FILE)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ── Config ───────────────────────────────────────────────────────────────────
SUPER_ADMIN_IDS = {
    'admin@snpsu.edu.in',
    'superadmin@snpsu.edu.in',
    'wCUdejsxWlYpnXt7N3hdDXaKods2',
}

WIPE_COLLECTIONS = [
    'audit_log',
    'event_forms',
    'events',
    'form_submissions',
    'registrations',
    'test_setup',
]

BATCH_SIZE = 400  # Firestore max batch write is 500


def delete_collection(col_name: str) -> int:
    """Delete all documents in a collection in batches. Returns count deleted."""
    total = 0
    while True:
        docs = list(db.collection(col_name).limit(BATCH_SIZE).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()
        total += len(docs)
        print(f"  {col_name}: deleted {total} docs so far...")
    return total


def wipe_users_except_admins() -> int:
    """Delete all user docs except the 3 super admin IDs. Returns count deleted."""
    total = 0
    last_doc = None
    while True:
        query = db.collection('users').limit(BATCH_SIZE)
        if last_doc:
            query = query.start_after(last_doc)
        docs = list(query.stream())
        if not docs:
            break

        to_delete = [d for d in docs if d.id not in SUPER_ADMIN_IDS]
        if to_delete:
            batch = db.batch()
            for doc in to_delete:
                batch.delete(doc.reference)
            batch.commit()
            total += len(to_delete)
            print(f"  users: deleted {total} docs so far (skipping super admins)...")

        last_doc = docs[-1]
        if len(docs) < BATCH_SIZE:
            break

    return total


# ── Run ──────────────────────────────────────────────────────────────────────
print("=" * 60)
print("FIRESTORE BULK DELETE")
print("Preserving super admins:", SUPER_ADMIN_IDS)
print("=" * 60)

grand_total = 0

for col in WIPE_COLLECTIONS:
    print(f"\nDeleting collection: {col}")
    count = delete_collection(col)
    print(f"  DONE: {count} documents deleted from '{col}'")
    grand_total += count

print(f"\nDeleting non-admin users from: users")
count = wipe_users_except_admins()
print(f"  DONE: {count} user documents deleted")
grand_total += count

print("\n" + "=" * 60)
print(f"COMPLETE — Total documents deleted: {grand_total}")
print("Super admin accounts preserved:")
for uid in SUPER_ADMIN_IDS:
    doc = db.collection('users').document(uid).get()
    status = "EXISTS" if doc.exists else "NOT FOUND"
    print(f"  {uid} → {status}")
print("=" * 60)
