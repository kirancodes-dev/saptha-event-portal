import os
import sys
import secrets
import logging

logger = logging.getLogger(__name__)

class Config:
    # =========================================================
    # 1. SECURITY & SESSION
    # =========================================================
    SECRET_KEY              = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE   = os.environ.get('FLASK_ENV') == 'production'
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600

    # =========================================================
    # 2. APPLICATION INFO
    # =========================================================
    APP_NAME     = "SapthaEvent"
    ORGANIZATION = "Sapthagiri NPS University"
    FLASK_ENV    = os.environ.get('FLASK_ENV', 'development')

    # =========================================================
    # 3. EMAIL — Gmail SMTP
    # ─────────────────────────────────────────────────────────
    # CRITICAL: MAIL_TIMEOUT = 10 prevents gunicorn worker from
    # hanging forever when Gmail is unreachable.
    #
    # MAIL_PASS must be a 16-char Gmail App Password, NOT your
    # regular Gmail login password. Generate one at:
    #   myaccount.google.com/apppasswords
    #
    # ⚠️  PRODUCTION: These MUST be set via environment variables!
    # =========================================================
    MAIL_SERVER         = 'smtp.gmail.com'
    MAIL_PORT           = 587
    MAIL_USE_TLS        = True
    MAIL_USE_SSL        = False
    MAIL_TIMEOUT        = os.environ.get('MAIL_TIMEOUT', 10)
    _mail_user_raw      = os.environ.get('MAIL_USER')
    _mail_pass_raw      = os.environ.get('MAIL_PASS')
    
    # Validation: warn if production but no email configured
    if os.environ.get('FLASK_ENV') == 'production':
        if not _mail_user_raw or not _mail_pass_raw:
            logger.warning("⚠️  PRODUCTION MODE: MAIL_USER and MAIL_PASS must be set!")
    
    # Use defaults only for development
    MAIL_USERNAME = _mail_user_raw or 'sapthhack@gmail.com'
    MAIL_PASSWORD = _mail_pass_raw or 'SET_THIS_IN_ENV'
    MAIL_DEFAULT_SENDER = (
        'SapthaEvent Team',
        MAIL_USERNAME
    )

    # =========================================================
    # 4. RATE LIMITING
    # =========================================================
    RATELIMIT_DEFAULT         = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URL     = os.environ.get('REDIS_URL', 'memory://')
    RATELIMIT_HEADERS_ENABLED = True

    # =========================================================
    # 5. SUPER ADMIN
    # ─────────────────────────────────────────────────────────
    # ⚠️  PRODUCTION: These MUST be set via environment variables!
    # Use init_superadmin.py to initialize on first deployment
    # =========================================================
    _super_admin_email = os.environ.get('SUPER_ADMIN_EMAIL')
    _super_admin_pass = os.environ.get('SUPER_ADMIN_PASS')
    
    if os.environ.get('FLASK_ENV') == 'production':
        if not _super_admin_email or not _super_admin_pass:
            logger.warning("⚠️  PRODUCTION: SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASS must be set!")
    
    SUPER_ADMIN_EMAIL        = _super_admin_email or 'admin@snpsu.edu.in'
    SUPER_ADMIN_DEFAULT_PASS = _super_admin_pass or 'SET_THIS_IN_ENV'
    MASTER_SECRET_KEY        = os.environ.get('MASTER_SECRET_KEY', 'SAPTHA@2026')

    # =========================================================
    # 6. GEMINI AI
    # =========================================================
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

    # =========================================================
    # 7. TWILIO WHATSAPP
    # ─────────────────────────────────────────────────────────
    # Set these 3 in Railway Variables:
    #   TWILIO_ACCOUNT_SID   = ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    #   TWILIO_AUTH_TOKEN    = your_auth_token_here
    #   TWILIO_WHATSAPP_FROM = whatsapp:+14155238886
    #
    # App works without these — WhatsApp sends are silently skipped.
    # =========================================================
    TWILIO_ACCOUNT_SID   = os.environ.get('TWILIO_ACCOUNT_SID',   '')
    TWILIO_AUTH_TOKEN    = os.environ.get('TWILIO_AUTH_TOKEN',    '')
    TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM', '')

    # =========================================================
    # 8. APP BASE URL
    # ─────────────────────────────────────────────────────────
    # Set BASE_URL in Railway Variables:
    #   BASE_URL = https://saptha-event-portal-production.up.railway.app
    # =========================================================
    BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')

    # =========================================================
    # 9. COLLEGE LOGO
    # ─────────────────────────────────────────────────────────
    # Used in PDF certificates and email templates.
    # Defaults to official SNPSU logo. Override in Railway:
    #   COLLEGE_LOGO_URL = https://your-custom-logo.png
    # =========================================================
    COLLEGE_LOGO_URL = os.environ.get(
        'COLLEGE_LOGO_URL',
        'https://snpsu.edu.in/wp-content/uploads/2024/03/Untitled-2-1-1536x527.png'
    )

    # =========================================================
    # 10. FIREBASE
    # ─────────────────────────────────────────────────────────
    # Set in Railway Variables:
    #   FIREBASE_CREDENTIALS = { ...full serviceAccountKey.json content... }
    # Falls back to serviceAccountKey.json for local development.
    # =========================================================
    FIREBASE_CREDENTIALS = os.environ.get('FIREBASE_CREDENTIALS', '')
    FIREBASE_KEY_PATH    = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')