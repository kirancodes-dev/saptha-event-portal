import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db

if not db:
    print("Database client is None!")
    sys.exit(1)

EVENT_ID = "enR13zOrEtEld7uYBiHz"
STUDENT_EMAIL = "testuser@example.com"
REG_ID = "REG-test-mismatch-123"

# 1. Get current event details
event_doc = db.collection('events').document(EVENT_ID).get()
if not event_doc.exists:
    print(f"Event {EVENT_ID} not found!")
    sys.exit(1)
event_data = event_doc.to_dict()
old_title = event_data.get('title')
print(f"Current event title: {old_title}")

# 2. Create registration with cached title
db.collection('registrations').document(REG_ID).set({
    'reg_id': REG_ID,
    'event_id': EVENT_ID,
    'event_title': old_title,
    'lead_email': STUDENT_EMAIL,
    'lead_name': 'Test User',
    'status': 'Confirmed',
    'payment_status': 'Free',
    'attendance': 'Pending',
    'registered_at': '2026-06-03 12:00:00'
})
print("Created registration with cached title.")

# 3. Simulate SPOC updating the event title in events collection
new_title = f"{old_title} - UPDATED NAME"
db.collection('events').document(EVENT_ID).update({
    'title': new_title
})
print(f"Updated event title in events collection to: {new_title}")

# 4. Check what Home Page displays
# Home page fetches event directly:
event_doc_after = db.collection('events').document(EVENT_ID).get().to_dict()
print(f"\n[Home Page] will display event title: {event_doc_after.get('title')}")

# 5. Check what Participant Dashboard (/participant/dashboard) displays
# Participant Dashboard fetches registration and event document:
reg_doc = db.collection('registrations').document(REG_ID).get().to_dict()
event_doc_enrich = db.collection('events').document(reg_doc.get('event_id')).get().to_dict()
dashboard_title = event_doc_enrich.get('title', reg_doc.get('event_title', ''))
print(f"[Participant Dashboard] will display event title: {dashboard_title}")

# 6. Check what Profile Page (/profile/) displays
# Profile page fetches registrations directly:
profile_reg = db.collection('registrations').document(REG_ID).get().to_dict()
profile_title = profile_reg.get('event_title')
print(f"[Profile Page / My Registrations] will display event title: {profile_title}")

# 7. Clean up changes to avoid polluting database (revert event title)
db.collection('events').document(EVENT_ID).update({
    'title': old_title
})
db.collection('registrations').document(REG_ID).delete()
print("\nCleaned up changes.")
