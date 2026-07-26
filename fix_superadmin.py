"""
Run this ONCE locally to create/reset the SuperAdmin account in Firestore.

Usage:
    python fix_superadmin.py

It will print the email and new password to the terminal.
Delete this file after you've logged in successfully.
"""
import os
import datetime
try:
    from dotenv import load_dotenv
except Exception:
    dotenv = None
load_dotenv()

from werkzeug.security import generate_password_hash
from models import db  # reuses your existing Firestore connection

EMAIL    = os.environ.get('SUPER_ADMIN_EMAIL', '').strip()
NEW_PASS = 'Admin@12345'   # change this after first login

if not EMAIL:
    print("ERROR: SUPER_ADMIN_EMAIL not set in .env")
    exit(1)

db.collection('users').document(EMAIL).set({
    'email':               EMAIL,
    'name':                'System Super Admin',
    'role':                'SuperAdmin',
    'category':            'All',
    'password':            generate_password_hash(NEW_PASS, method='pbkdf2:sha256'),
    'created_at':          datetime.datetime.now().strftime("%Y-%m-%d"),
    'needs_password_reset': False,
}, merge=True)

print(f"""
SuperAdmin reset complete.
--------------------------
Email    : {EMAIL}
Password : {NEW_PASS}
Role     : Super Admin  (select this in the dropdown)
Master Key: check MASTER_SECRET_KEY in your .env or Railway Variables

Login at: https://saptha-event-portal-production.up.railway.app/login
Change the password immediately after login.
""")
