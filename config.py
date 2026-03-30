import os
import secrets

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
    # hanging forever when Gmail is unreachable, which was causing
    # the "Internal Server Error" on /admin/appoint_spoc and
    # /coordinator/assign_staff.
    #
    # MAIL_PASS must be a 16-char Gmail App Password, NOT your
    # regular Gmail login password. Generate one at:
    #   myaccount.google.com/apppasswords
    # =========================================================
    MAIL_SERVER         = 'smtp.gmail.com'
    MAIL_PORT           = 587
    MAIL_USE_TLS        = True
    MAIL_USE_SSL        = False
    MAIL_TIMEOUT        = 10   # ← THE FIX: 10s timeout, never blocks gunicorn
    MAIL_USERNAME       = os.environ.get('MAIL_USER', 'sapthhack@gmail.com')
    MAIL_PASSWORD       = os.environ.get('MAIL_PASS', 'yqfktmdnvxofqvxj')
    MAIL_DEFAULT_SENDER = (
        'SapthaEvent Team',
        os.environ.get('MAIL_USER', 'sapthhack@gmail.com')
    )

    # =========================================================
    # 4. RATE LIMITING
    # =========================================================
    RATELIMIT_DEFAULT         = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URL     = os.environ.get('REDIS_URL', 'memory://')
    RATELIMIT_HEADERS_ENABLED = True

    # =========================================================
    # 5. SUPER ADMIN
    # =========================================================
    SUPER_ADMIN_EMAIL        = os.environ.get('SUPER_ADMIN_EMAIL', 'admin@snpsu.edu.in')
    SUPER_ADMIN_DEFAULT_PASS = os.environ.get('SUPER_ADMIN_PASS',  'Saptha@Admin2026')
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