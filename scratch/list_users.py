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

print("\n--- USERS ---")
users = list(db.collection('users').stream())
print(f"Total users found: {len(users)}")
for u in users:
    d = u.to_dict()
    print(f"Email/ID: {u.id} | Name: {d.get('name')} | Role: {d.get('role')} | Pwd: {d.get('password')[:15]}...")
