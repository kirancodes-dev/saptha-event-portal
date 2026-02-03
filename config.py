import os
import secrets

class Config:
    # 1. Strong Secret Key (Generates a new one if not found)
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # 2. Database Config
    # (We are using Firestore, so no SQL URI needed here, but kept for structure)
    APP_NAME = "SapthaEvent"
    ORGANIZATION = "Sapthagiri NPS University"
    
    # 3. Security Settings (CRITICAL FOR PHASE 3)
    SESSION_COOKIE_HTTPONLY = True  # Prevents JavaScript from reading cookies (XSS Protection)
    SESSION_COOKIE_SAMESITE = 'Lax' # Prevents CSRF attacks
    PERMANENT_SESSION_LIFETIME = 1800 # Session expires after 30 minutes of inactivity
    
    # 4. Mail Settings (For Future OTPs/Emails)
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USER')
    MAIL_PASSWORD = os.environ.get('MAIL_PASS')