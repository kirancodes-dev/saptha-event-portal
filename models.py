import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

# 1. Initialize Firebase
if not firebase_admin._apps:
    # OPTION A: Look for the file (Local Development)
    if os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
    
    # OPTION B: Look for Environment Variable (Render / Production)
    # We will create this variable in Render later
    elif os.environ.get('FIREBASE_CREDENTIALS'):
        # Convert the string back to a dictionary
        creds_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(creds_dict)
    
    else:
        raise Exception("Firebase Key not found! Add serviceAccountKey.json or set FIREBASE_CREDENTIALS env var.")

    firebase_admin.initialize_app(cred)

# 2. Create the Database Client
db = firestore.client()