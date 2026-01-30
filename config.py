import os
import secrets

class Config:
    """
    Base Configuration for SapthaEvent Enterprise.
    Securely manages environment variables and core settings.
    """
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SESSION_COOKIE_NAME = 'saptha_enterprise_session'
    
    # Database (Firebase)
    FIREBASE_CREDENTIALS = os.environ.get('FIREBASE_CREDENTIALS')
    
    # Mail Settings (SMTP)
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'sapthhack@gmail.com'
    MAIL_PASSWORD = 'bbcw iimk ghvu pvof' 
    MAIL_DEFAULT_SENDER = ('SapthaEvent Admin', 'sapthhack@gmail.com')
    
    # App Meta
    APP_NAME = "SapthaEvent Enterprise"
    ORGANIZATION = "Sapthagiri College of Engineering"