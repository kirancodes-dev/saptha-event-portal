import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, '.')
from models import db

try:
    users_count = len(list(db.collection('users').stream()))
    events_count = len(list(db.collection('events').stream()))
    regs_count = len(list(db.collection('registrations').stream()))
    print(f"Connection Successful!")
    print(f"Users: {users_count}")
    print(f"Events: {events_count}")
    print(f"Registrations: {regs_count}")
except Exception as e:
    print(f"Error connecting: {e}")
