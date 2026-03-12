import firebase_admin
from firebase_admin import credentials, firestore
from werkzeug.security import generate_password_hash

# 1. Connect to Firebase
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
except ValueError:
    pass

db = firestore.client()

print("🔨 Smashing the old admin account and rebuilding it...")

try:
    # 2. Forcefully overwrite the database document
    email = "admin@snpsu.edu.in"
    password = "Saptha@Admin2026"
    
    db.collection('users').document(email).set({
        'email': email,
        'name': 'System Super Admin',
        'role': 'SuperAdmin',
        'category': 'All',
        'password': generate_password_hash(password),
        'created_at': '2026-03-08'
    })

    print("✅ Success! The Admin account is perfectly configured.")
    print("Go login with:")
    print("Role: Super Admin")
    print(f"Email: {email}")
    print(f"Password: {password}")
    print("Secret Key: SAPTHA@2026")

except Exception as e:
    print(f"Error: {e}")