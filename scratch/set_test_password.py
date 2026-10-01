
# BLK-10: refuse production-looking databases before anything connects
import os as _os, sys as _sys  # noqa: E401,E402
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from seed_safety import guard  # noqa: E402
guard()

import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db
from werkzeug.security import generate_password_hash

if not db:
    print("Database client is None!")
    sys.exit(1)

# Ensure testuser@example.com exists and has password Student@1234
db.collection('users').document('testuser@example.com').set({
    'email': 'testuser@example.com',
    'name': 'Test User',
    'role': 'Student',
    'category': 'General',
    'password': generate_password_hash('Student@1234', method='pbkdf2:sha256'),
    'created_at': '2026-06-03'
}, merge=True)

print("Test user testuser@example.com password set to Student@1234")
