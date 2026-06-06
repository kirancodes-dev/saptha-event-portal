import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db

print("DATABASE_TYPE:", os.environ.get('DATABASE_TYPE'))
print("FIREBASE_KEY_PATH:", os.environ.get('FIREBASE_KEY_PATH'))

if not db:
    print("Database client is None!")
    sys.exit(1)

print("\n--- EVENTS ---")
events = list(db.collection('events').stream())
print(f"Total events found: {len(events)}")
for e in events:
    d = e.to_dict()
    print(f"ID: {e.id} | Title: {d.get('title')} | Date: {d.get('date')} | Status: {d.get('status')}")

print("\n--- REGISTRATIONS ---")
regs = list(db.collection('registrations').stream())
print(f"Total registrations found: {len(regs)}")
for r in regs:
    d = r.to_dict()
    print(f"ID: {r.id} | EventID: {d.get('event_id')} | EventTitle (cached): {d.get('event_title')} | Lead: {d.get('lead_email')}")
