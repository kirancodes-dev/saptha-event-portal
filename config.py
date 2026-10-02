import os
import secrets
import logging

logger = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _dev_secret_key():
    """Stable secret key for local development, kept in the gitignored
    instance/ folder so sessions survive restarts and are shared by workers."""
    path = os.path.join(_PROJECT_DIR, 'instance', 'dev_secret_key')
    try:
        with open(path) as fh:
            key = fh.read().strip()
            if key:
                return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as fh:
            fh.write(key)
    except OSError:
        pass
    return key


class Config:
    # =========================================================
    # 1. SECURITY & SESSION
    # =========================================================
    _is_production = os.environ.get('FLASK_ENV') == 'production'
    _env_secret = os.environ.get('SECRET_KEY', '').strip()
    if _is_production:
        if not _env_secret or len(_env_secret) < 32 or _env_secret in ('default_secret_key', 'dev', 'secret', 'changeme', 'your_random_secret_key_here_64_chars_minimum'):
            raise RuntimeError("CRITICAL: In production, SECRET_KEY must be set in the environment and be at least 32 characters long.")

    # Production must set SECRET_KEY (checked above and by validate_production_config).
    # Development uses a stable key from instance/ so all workers share it.
    SECRET_KEY              = _env_secret or ('' if _is_production else _dev_secret_key())
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE   = _is_production
    # Lax, not Strict: Strict drops the cookie when a user arrives from an
    # email link or a payment redirect, so they look logged out (BLK-08)
    SESSION_COOKIE_SAMESITE = 'Lax'
    # 30 days — PWA users stay logged in like a native app
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30
    # 2 hours — when user does NOT check "Keep me logged in"
    SHORT_SESSION_LIFETIME = 60 * 60 * 2

    # Server-side session storage (BLK-08): Redis when REDIS_URL is set,
    # otherwise the app database ('sqlalchemy', session_store.py), so sessions
    # survive restarts and are shared by every instance. 'filesystem' is for
    # local experiments only (per-instance, lost on restart).
    _redis_url = os.environ.get('REDIS_URL', '')
    SESSION_TYPE           = os.environ.get('SESSION_TYPE',
                                 'redis' if _redis_url else 'sqlalchemy')
    # Only used with SESSION_TYPE=filesystem: Flask-Session prunes files past
    # this count (default 500), which logged users out on busy days
    SESSION_FILE_THRESHOLD = int(os.environ.get('SESSION_FILE_THRESHOLD', 50000))
    SESSION_PERMANENT      = True
    SESSION_USE_SIGNER     = True
    SESSION_KEY_PREFIX     = 'saptha_sess:'
    # Writable path in container — /app is root-owned, so write to /tmp.
    # Override with SESSION_FILE_DIR env var if mounting a persistent volume.
    SESSION_FILE_DIR       = os.environ.get('SESSION_FILE_DIR', '/tmp/flask_session')  # nosec B108

    # CSRF protection (Flask-WTF)
    WTF_CSRF_ENABLED       = True
    WTF_CSRF_SECRET_KEY    = os.environ.get('WTF_CSRF_SECRET_KEY') or SECRET_KEY
    WTF_CSRF_TIME_LIMIT    = None  # no expiry — token lives with the session

    # Enforce HTTPS via Talisman when explicitly set, otherwise production-only
    FORCE_HTTPS            = os.environ.get('FORCE_HTTPS', 'true' if _is_production else 'false').lower() == 'true'

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
    MAIL_SERVER         = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT           = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS        = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL        = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_TIMEOUT        = int(os.environ.get('MAIL_TIMEOUT', 10))
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
        os.environ.get('MAIL_SENDER') or MAIL_USERNAME
    )

    # =========================================================
    # 4. RATE LIMITING
    # =========================================================
    RATELIMIT_DEFAULT         = "100000 per day;10000 per hour"
    RATELIMIT_STORAGE_URL     = os.environ.get('REDIS_URL', 'memory://')
    RATELIMIT_HEADERS_ENABLED = True

    # Failed logins and password-reset requests (services_login_throttle,
    # BLK-13): at most LIMIT per IP and per account in any WINDOW seconds.
    # Counters live in Redis when REDIS_URL is set, otherwise in the database,
    # so every instance and worker shares them.
    LOGIN_THROTTLE_IP_LIMIT      = int(os.environ.get('LOGIN_THROTTLE_IP_LIMIT', 5))
    LOGIN_THROTTLE_ACCOUNT_LIMIT = int(os.environ.get('LOGIN_THROTTLE_ACCOUNT_LIMIT', 5))
    LOGIN_THROTTLE_WINDOW        = int(os.environ.get('LOGIN_THROTTLE_WINDOW', 60))
    LOGIN_THROTTLE_STORAGE       = 'redis' if os.environ.get('REDIS_URL') else 'database'

    # =========================================================
    # 5. SUPER ADMIN
    # ─────────────────────────────────────────────────────────
    # No defaults: create the account with `python init_superadmin.py`.
    # If both SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASS are set, the first
    # SuperAdmin login with exactly those credentials also creates it.
    # MASTER_SECRET_KEY is the extra key SuperAdmin logins must supply
    # (required in production; skipped locally when unset).
    # =========================================================
    SUPER_ADMIN_EMAIL        = os.environ.get('SUPER_ADMIN_EMAIL', '').strip().lower()
    SUPER_ADMIN_DEFAULT_PASS = os.environ.get('SUPER_ADMIN_PASS', '')
    MASTER_SECRET_KEY        = os.environ.get('MASTER_SECRET_KEY', '')

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
        'https://saptha-event-portal-production.up.railway.app/static/snpsu-logo.png'
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

    # =========================================================
    # 11. OBSERVABILITY — Sentry error tracking
    # =========================================================
    SENTRY_DSN       = os.environ.get('SENTRY_DSN', '')
    SENTRY_ENV       = os.environ.get('FLASK_ENV', 'development')
    SENTRY_SAMPLE    = float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.1'))

    # =========================================================
    # 12. CELERY — Async task queue (optional)
    # =========================================================
    # If CELERY_BROKER_URL is unset, tasks fall back to synchronous execution.
    CELERY_BROKER_URL     = os.environ.get('CELERY_BROKER_URL', '')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND',
                                            os.environ.get('CELERY_BROKER_URL', ''))

    # =========================================================
    # 13. JWT AUTHENTICATION (API layer)
    # =========================================================
    JWT_SECRET_KEY            = os.environ.get('JWT_SECRET_KEY', '') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES  = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 900))    # 15 min
    JWT_REFRESH_TOKEN_EXPIRES = int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES', 604800))  # 7 days

    # =========================================================
    # 14. OAUTH 2.0 / SSO
    # =========================================================
    OAUTH_GOOGLE_CLIENT_ID     = os.environ.get('OAUTH_GOOGLE_CLIENT_ID', '')
    OAUTH_GOOGLE_CLIENT_SECRET = os.environ.get('OAUTH_GOOGLE_CLIENT_SECRET', '')
    OAUTH_MICROSOFT_CLIENT_ID     = os.environ.get('OAUTH_MICROSOFT_CLIENT_ID', '')
    OAUTH_MICROSOFT_CLIENT_SECRET = os.environ.get('OAUTH_MICROSOFT_CLIENT_SECRET', '')

    # =========================================================
    # 15. POSTGRESQL (for SQL-backed features / migration target)
    # =========================================================
    DATABASE_URL = os.environ.get('DATABASE_URL', '')

    # =========================================================
    # 16. MULTI-TENANCY
    # =========================================================
    MULTI_TENANT_ENABLED = os.environ.get('MULTI_TENANT_ENABLED', 'false').lower() == 'true'
    DEFAULT_ORG_SLUG     = os.environ.get('DEFAULT_ORG_SLUG', 'snpsu')

    # =========================================================
    # 17. SUPABASE API
    # =========================================================
    SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')




# Values that must never be used in production (old published defaults)
_KNOWN_WEAK_SECRETS = {'SAPTHA@2026', 'Saptha@Admin2026', 'Admin@12345',
                       'your_random_secret_key_here_64_chars_minimum'}


def validate_production_config(config):
    """Refuse to start in production with missing or placeholder secrets."""
    if config.get('FLASK_ENV') != 'production':
        return
    problems = []
    secret = config.get('SECRET_KEY') or ''
    if len(secret) < 32 or secret in _KNOWN_WEAK_SECRETS:
        problems.append('SECRET_KEY must be set to a random value of at least 32 characters')
    master = config.get('MASTER_SECRET_KEY') or ''
    if len(master) < 12 or master in _KNOWN_WEAK_SECRETS:
        problems.append('MASTER_SECRET_KEY must be set (12+ characters, not a published default)')
    if config.get('SUPER_ADMIN_DEFAULT_PASS') in _KNOWN_WEAK_SECRETS:
        problems.append('SUPER_ADMIN_PASS is a published default password')
    if problems:
        raise RuntimeError('Refusing to start in production: ' + '; '.join(problems))
