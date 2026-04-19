"""
init_superadmin.py — Initialize SuperAdmin on First Deployment
===============================================================

Run this once when deploying to production:
  python init_superadmin.py

It will:
  1. Check if SuperAdmin already exists
  2. If not, create one with default credentials from config
  3. Validate Firebase connection
  4. Print confirmation with login details

Environment Variables (or uses config defaults):
  SUPER_ADMIN_EMAIL = admin@snpsu.edu.in
  SUPER_ADMIN_PASS = Saptha@Admin2026
"""

import os
import sys
import json
import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# FIREBASE INITIALIZATION
# =========================================================
def init_firebase():
    """Initialize Firebase connection"""
    if firebase_admin._apps:
        return firestore.client()
    
    firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
    if firebase_creds_json:
        try:
            cred_dict = json.loads(firebase_creds_json)
            if isinstance(cred_dict, str):
                cred_dict = json.loads(cred_dict)
            cred = credentials.Certificate(cred_dict)
        except Exception as exc:
            print(f"❌ FIREBASE_CREDENTIALS parse error: {exc}")
            sys.exit(1)
    else:
        key_path = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')
        if not os.path.exists(key_path):
            print(f"❌ Neither FIREBASE_CREDENTIALS env var nor {key_path} found!")
            sys.exit(1)
        cred = credentials.Certificate(key_path)
    
    firebase_admin.initialize_app(cred)
    return firestore.client()


# =========================================================
# SUPERADMIN INITIALIZATION
# =========================================================
def init_superadmin():
    """Create SuperAdmin account if it doesn't exist"""
    
    # Get credentials from environment or config defaults
    from config import Config
    
    admin_email = os.environ.get('SUPER_ADMIN_EMAIL', Config.SUPER_ADMIN_EMAIL)
    admin_pass = os.environ.get('SUPER_ADMIN_PASS', Config.SUPER_ADMIN_DEFAULT_PASS)
    
    if not admin_email or not admin_pass:
        print("❌ ERROR: SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASS must be set!")
        sys.exit(1)
    
    # Initialize Firebase
    print("\n📡 Connecting to Firebase...")
    try:
        db = init_firebase()
        print("✅ Firebase connected successfully")
    except Exception as e:
        print(f"❌ Firebase connection failed: {e}")
        sys.exit(1)
    
    # Check if SuperAdmin exists
    print(f"\n🔍 Checking if SuperAdmin exists: {admin_email}")
    try:
        admin_doc = db.collection('users').document(admin_email).get()
        if admin_doc.exists:
            admin_data = admin_doc.to_dict()
            print(f"✅ SuperAdmin already exists:")
            print(f"   Name: {admin_data.get('name', 'N/A')}")
            print(f"   Role: {admin_data.get('role', 'N/A')}")
            print(f"   Created: {admin_data.get('created_at', 'N/A')}")
            return
    except Exception as e:
        print(f"❌ Error checking for SuperAdmin: {e}")
        sys.exit(1)
    
    # Create SuperAdmin account
    print(f"\n🚀 Creating SuperAdmin account...")
    try:
        hashed_pass = generate_password_hash(admin_pass)
        admin_data = {
            'email': admin_email,
            'name': 'System Administrator',
            'role': 'SuperAdmin',
            'category': 'General',
            'phone': 'ADMIN',
            'password': hashed_pass,
            'created_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'needs_password_reset': False,
            'is_active': True,
            'permissions': ['manage_users', 'manage_events', 'view_analytics']
        }
        db.collection('users').document(admin_email).set(admin_data)
        print("✅ SuperAdmin created successfully!")
        print(f"\n{'='*60}")
        print(f"  SUPERADMIN LOGIN CREDENTIALS")
        print(f"{'='*60}")
        print(f"Email:    {admin_email}")
        print(f"Password: {admin_pass}")
        print(f"{'='*60}")
        print(f"\n⚠️  IMPORTANT:")
        print(f"  - Save these credentials securely")
        print(f"  - Change password after first login")
        print(f"  - Store in secure password manager")
        print(f"  - Never commit to version control")
        print(f"\n✅ Initialization complete! System is ready for production.\n")
        
    except Exception as e:
        print(f"❌ Error creating SuperAdmin: {e}")
        sys.exit(1)


# =========================================================
# ENTRY POINT
# =========================================================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("  SapthaEvent - SuperAdmin Initialization")
    print("="*60)
    init_superadmin()
