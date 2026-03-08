import os
import secrets

class Config:
    # --- 1. Security & Session ---
    # Generates a new secret key if one isn't set (Keeps sessions secure)
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    SESSION_COOKIE_HTTPONLY = True   # Prevents JavaScript access to cookies (XSS Protection)
    SESSION_COOKIE_SAMESITE = 'Lax'  # Prevents CSRF attacks
    PERMANENT_SESSION_LIFETIME = 1800 # Session expires after 30 mins
    
    # --- 2. Application Info ---
    APP_NAME = "SapthaEvent"
    ORGANIZATION = "Sapthagiri NPS University"
    
    # --- 3. Email Configuration (Gmail SMTP) ---
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    
    # IMPORTANT: Replace these with your actual Gmail and App Password for testing.
    # If using environment variables, ensure they are set in your OS/Terminal.
    MAIL_USERNAME = os.environ.get('MAIL_USER') or 'your-email@gmail.com' 
    MAIL_PASSWORD = os.environ.get('MAIL_PASS') or 'your-app-password'
    
    # Auto-sets the sender to be your email
    MAIL_DEFAULT_SENDER = ('SapthaEvent Team', MAIL_USERNAME)