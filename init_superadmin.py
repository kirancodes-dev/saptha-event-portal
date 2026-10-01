"""
init_superadmin.py — Create (or reset) the SuperAdmin account.

Usage:
    SUPER_ADMIN_EMAIL=you@college.edu SUPER_ADMIN_PASS='a strong password' \
        python init_superadmin.py            # create if missing
    python init_superadmin.py --reset        # also overwrite the password

The values can also come from .env. Uses the same database as the app
(DATABASE_URL, or the local SQLite file in development).
"""

# BLK-10: refuse production-looking databases before anything connects
from seed_safety import guard  # noqa: E402
guard()

import datetime
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from werkzeug.security import generate_password_hash

from utils import validate_password_strength


def main(argv):
    email = os.environ.get('SUPER_ADMIN_EMAIL', '').strip().lower()
    password = os.environ.get('SUPER_ADMIN_PASS', '')
    reset = '--reset' in argv

    if not email or not password:
        print("SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASS must be set (environment or .env).")
        return 1
    ok, message = validate_password_strength(password)
    if not ok:
        print(f"SUPER_ADMIN_PASS is too weak: {message}")
        return 1

    from models import db
    if db is None:
        print("Database is not available — check DATABASE_URL.")
        return 1

    ref = db.collection('users').document(email)
    if ref.get().exists and not reset:
        print(f"SuperAdmin {email} already exists. Use --reset to overwrite the password.")
        return 0

    ref.set({
        'email': email,
        'name': 'System Administrator',
        'role': 'SuperAdmin',
        'category': 'All',
        'password': generate_password_hash(password, method='pbkdf2:sha256'),
        'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'needs_password_reset': False,
        'is_active': True,
    }, merge=True)
    print(f"SuperAdmin {'reset' if reset else 'created'}: {email}")
    print("Log in with role 'Super Admin' (plus MASTER_SECRET_KEY if it is set).")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
