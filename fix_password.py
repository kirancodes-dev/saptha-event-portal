import firebase_admin
from firebase_admin import credentials, firestore
from werkzeug.security import generate_password_hash

# 1. Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 2. Settings
target_email = "admin@sapthahack.com"  # <--- YOUR ADMIN EMAIL
new_password = "admin"                 # <--- YOUR DESIRED PASSWORD

# 3. Generate Hash
hashed_pw = generate_password_hash(new_password)

# 4. Update Database
user_ref = db.collection('users').document(target_email)
doc = user_ref.get()

if doc.exists:
    user_ref.update({
        'password': hashed_pw,  # Updates with the HASHED version
        'role': 'Admin'         # Ensures role is correct too
    })
    print(f"✅ Success! Password for {target_email} has been reset.")
    print(f"👉 You can now login with: {new_password}")
else:
    print(f"❌ Error: User {target_email} not found in database.")