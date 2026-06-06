import os
import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db
from werkzeug.security import generate_password_hash

if not db:
    print("Database client is None!")
    sys.exit(1)

# Ensure admin@snpsu.edu.in exists and has password Saptha@Admin2026
db.collection('users').document('admin@snpsu.edu.in').set({
    'email': 'admin@snpsu.edu.in',
    'name': 'System Super Admin',
    'role': 'SuperAdmin',
    'category': 'All',
    'password': generate_password_hash('Saptha@Admin2026', method='pbkdf2:sha256'),
    'created_at': '2026-06-03',
    'needs_password_reset': False
}, merge=True)

print("Admin password set to Saptha@Admin2026")
