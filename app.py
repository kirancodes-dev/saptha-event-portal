import os
import json
import datetime
import logging
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, render_template, session, redirect, request, jsonify, Response
from flask_mail import Mail
from flask_limiter import Limiter
import flask_limiter.util
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_session import Session
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix
from google.cloud.firestore_v1.base_query import FieldFilter
from config import Config
from dotenv import load_dotenv

load_dotenv()

# =========================================================
# LOGGING CONFIGURATION — structured JSON in production
# =========================================================
def _configure_logging():
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    root = logging.getLogger()
    root.setLevel(log_level)
    # Clear pre-existing handlers so reloaders don't double-log
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler()
    if os.environ.get('FLASK_ENV') == 'production':
        try:
            from pythonjsonlogger import jsonlogger
            fmt = jsonlogger.JsonFormatter(
                '%(asctime)s %(levelname)s %(name)s %(message)s %(pathname)s %(lineno)d'
            )
            handler.setFormatter(fmt)
        except Exception:
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    root.addHandler(handler)

_configure_logging()
logger = logging.getLogger(__name__)

# =========================================================
# SENTRY — initialized before app creation so errors during
# boot are captured too
# =========================================================
_SENTRY_DSN = os.environ.get('SENTRY_DSN', '').strip()
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            integrations=[FlaskIntegration()],
            environment=os.environ.get('FLASK_ENV', 'development'),
            traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
            send_default_pii=False,
        )
        logger.info("Sentry: initialized")
    except Exception as exc:
        logger.warning("Sentry: failed to initialize: %s", exc)

# =========================================================
# APP FACTORY
# =========================================================
app = Flask(__name__)
app.config.from_object(Config)

# Trust Railway/Heroku/Nginx proxy headers (X-Forwarded-Proto etc.)
# Required so Talisman's force_https doesn't loop-redirect behind TLS-terminating proxies.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# =========================================================
# EXTENSIONS
# =========================================================
mail = Mail(app)

# ── CSRF ─────────────────────────────────────────────────
csrf = CSRFProtect(app)

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    logger.warning("CSRF validation failed: %s path=%s ip=%s",
                   e.description, request.path, request.remote_addr)
    if request.accept_mimetypes.best == 'application/json' or request.is_json:
        return jsonify({'error': 'csrf_validation_failed', 'detail': e.description}), 400
    return render_template('429.html'), 400

# Expose csrf_token() in Jinja globals (Flask-WTF does this automatically,
# but make it explicit for clarity)
app.jinja_env.globals['csrf_token'] = lambda: (
    __import__('flask_wtf.csrf', fromlist=['generate_csrf']).generate_csrf()
)

# ── Server-side session (Redis in prod, filesystem in dev) ──
if app.config.get('SESSION_TYPE') == 'redis':
    try:
        import redis as _redis
        redis_url = os.environ.get('REDIS_URL') or app.config.get('RATELIMIT_STORAGE_URL')
        if redis_url and redis_url.startswith('redis'):
            app.config['SESSION_REDIS'] = _redis.from_url(redis_url)
            logger.info("Session: using Redis backend")
        else:
            logger.warning("SESSION_TYPE=redis but no REDIS_URL — falling back to filesystem")
            app.config['SESSION_TYPE'] = 'filesystem'
    except Exception as exc:
        logger.warning("Redis session init failed (%s) — using filesystem", exc)
        app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# ── Security headers via Talisman ────────────────────────
_csp = {
    'default-src': ["'self'"],
    'img-src':     ["'self'", 'data:', 'https:'],
    'style-src':   ["'self'", "'unsafe-inline'", 'https://cdnjs.cloudflare.com',
                    'https://fonts.googleapis.com', 'https://cdn.jsdelivr.net'],
    'font-src':    ["'self'", 'https://cdnjs.cloudflare.com',
                    'https://fonts.gstatic.com', 'data:'],
    'script-src':  ["'self'", "'unsafe-inline'", 'https://cdnjs.cloudflare.com',
                    'https://cdn.jsdelivr.net', 'https://www.gstatic.com'],
    'connect-src': ["'self'", 'https://firestore.googleapis.com',
                    'https://identitytoolkit.googleapis.com'],
    'frame-ancestors': ["'self'"],
}
Talisman(
    app,
    force_https=app.config.get('FORCE_HTTPS', False),
    strict_transport_security=app.config.get('FORCE_HTTPS', False),
    strict_transport_security_max_age=31536000,
    content_security_policy=_csp,
    content_security_policy_nonce_in=[],
    session_cookie_secure=app.config.get('SESSION_COOKIE_SECURE', False),
    referrer_policy='strict-origin-when-cross-origin',
    frame_options='SAMEORIGIN',
    x_content_type_options=True,
)

# ── Rate limiter ─────────────────────────────────────────
limiter = Limiter(
    key_func=flask_limiter.util.get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=app.config.get('RATELIMIT_STORAGE_URL', 'memory://'),
    enabled=False
)

# Expose limiter on app so blueprints can attach route-specific limits
app.extensions['limiter'] = limiter

# =========================================================
# FIREBASE  —  reads FIREBASE_CREDENTIALS env var on Railway
#              falls back to local serviceAccountKey.json for dev
# =========================================================
if not firebase_admin._apps:
    firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
    if firebase_creds_json:
        # Production: Use environment variable
        try:
            cred_dict = json.loads(firebase_creds_json)
            if isinstance(cred_dict, str):  # double-encoded guard
                cred_dict = json.loads(cred_dict)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase: Initialized with FIREBASE_CREDENTIALS env var")
        except Exception as exc:
            logger.error("FIREBASE_CREDENTIALS parse error: %s", exc)
            raise
    else:
        # Development: Try local file, skip if not available
        key_path = 'serviceAccountKey.json'
        if os.path.exists(key_path):
            try:
                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase: Initialized with local serviceAccountKey.json")
            except Exception as exc:
                logger.error("Firebase: Failed to initialize with %s: %s", key_path, exc)
                raise
        else:
            if os.environ.get('ENVIRONMENT') == 'production':
                logger.critical("ERROR: FIREBASE_CREDENTIALS env var not set in production!")
                raise EnvironmentError(
                    "FIREBASE_CREDENTIALS environment variable is required in production. "
                    "Set it in Railway Variables with your Firebase service account JSON."
                )
            else:
                logger.warning("Firebase: serviceAccountKey.json not found - running in dev mode without Firebase")
                # For development without Firebase, you can disable it or use mock credentials

# Initialize Firestore database (only if Firebase was initialized)
try:
    db = firestore.client()
    logger.info("Firestore: Connected successfully")
except Exception as exc:
    logger.error("Firestore: Failed to connect: %s", exc)
    db = None  # Use None and handle in routes

# =========================================================
# BLUEPRINTS
# =========================================================
from routes_auth        import auth_bp        # noqa: E402
from routes_api         import api_bp          # noqa: E402
from routes_ai_matching import ai_bp           # noqa: E402
from routes_admin       import admin_bp        # noqa: E402
from routes_coordinator import coord_bp        # noqa: E402
from routes_participant import participant_bp   # noqa: E402
from routes_payment     import payment_bp      # noqa: E402
from routes_judge       import judge_bp        # noqa: E402
from routes_profile     import profile_bp      # noqa: E402
from routes_feedback    import feedback_bp     # noqa: E402
from chatbot_routes     import chatbot_bp      # noqa: E402
from routes_ticket      import ticket_bp       # noqa: E402
from routes_forms       import forms_bp        # noqa: E402
from routes_portfolio   import portfolio_bp    # noqa: E402
from routes_sponsors    import sponsors_bp     # noqa: E402
from routes_teams          import teams_bp           # noqa: E402
from routes_notifications  import notif_bp          # noqa: E402
from routes_push           import push_bp           # noqa: E402
from routes_checkin        import checkin_bp        # noqa: E402
from routes_spoc           import spoc_bp           # noqa: E402
from routes_live           import live_bp           # noqa: E402

app.register_blueprint(auth_bp)
app.register_blueprint(api_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(coord_bp)
app.register_blueprint(participant_bp)
app.register_blueprint(payment_bp)
app.register_blueprint(judge_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(feedback_bp)
app.register_blueprint(chatbot_bp)
app.register_blueprint(ticket_bp)
app.register_blueprint(forms_bp)
app.register_blueprint(portfolio_bp)
app.register_blueprint(sponsors_bp)
app.register_blueprint(teams_bp)
app.register_blueprint(notif_bp)
app.register_blueprint(push_bp)
app.register_blueprint(checkin_bp)
app.register_blueprint(spoc_bp)
app.register_blueprint(live_bp)

# CSRF exemption for JSON-API blueprints hit via fetch()/XHR.
# HTML form-serving blueprints (auth, admin, coordinator, judge, payment,
# participant, profile, feedback) remain CSRF-protected.
for _json_bp in (api_bp, ai_bp, chatbot_bp, forms_bp):
    try:
        csrf.exempt(_json_bp)
    except Exception as exc:
        logger.warning("CSRF exempt failed for %s: %s", _json_bp.name, exc)


# =========================================================
# ROLE → DASHBOARD MAP
# =========================================================
ROLE_REDIRECTS = {
    'Student':          '/participant/dashboard',
    'SuperAdmin':       '/admin/dashboard',
    'Super Admin':      '/admin/dashboard',
    'Admin':            '/admin/dashboard',
    'Coordinator':      '/coordinator/dashboard',
    'ClubSPOC':         '/spoc/dashboard',
    'EventCoordinator': '/coordinator/scanner',
    'Judge':            '/judge/dashboard',
}

# =========================================================
# NOISE SUPPRESSORS
# =========================================================
@app.route('/favicon.ico')
def favicon():
    try:
        from flask import send_from_directory
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'favicon.ico', mimetype='image/vnd.microsoft.icon')
    except Exception:
        return Response(status=204)

@app.route('/cdn-cgi/<path:subpath>')
def cdn_cgi_suppress(subpath):
    return Response(status=204)

# =========================================================
# PWA: service worker served from root scope + offline page
# =========================================================
@app.route('/sw.js')
def service_worker():
    from flask import send_from_directory, make_response
    resp = make_response(send_from_directory(
        os.path.join(app.root_path, 'static'), 'sw.js', mimetype='application/javascript'))
    # Service worker needs to be controlled at the root — never cache it long.
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

@app.route('/manifest.webmanifest')
def pwa_manifest():
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'manifest.webmanifest', mimetype='application/manifest+json')

@app.route('/offline')
def offline_page():
    return render_template('offline.html')

@app.route('/.well-known/<path:subpath>')
def well_known_suppress(subpath):
    return Response(status=204)

# =========================================================
# HEALTH CHECK — For load balancers & monitoring
# =========================================================
@app.route('/health', methods=['GET'])
@limiter.exempt
def health_check():
    """
    Health check endpoint for Railway, Render, and load balancers.
    Returns 200 OK if app and Firebase are healthy.
    """
    try:
        # Quick Firebase connection test
        db.collection('users').limit(1).stream()
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.datetime.now().isoformat(),
            'version': '1.0.0',
            'environment': app.config.get('FLASK_ENV', 'unknown')
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.datetime.now().isoformat()
        }), 503

@app.route('/health/ready', methods=['GET'])
@limiter.exempt
def ready_check():
    """
    Readiness endpoint - checks if app is ready to handle traffic.
    """
    try:
        # Check Firebase
        db.collection('users').limit(1).stream()
        return jsonify({'ready': True}), 200
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return jsonify({'ready': False, 'error': str(e)}), 503

# =========================================================
# HOME
# =========================================================
@app.route('/')
def home():
    if 'user_id' in session:
        role = session.get('role', '')
        dest = ROLE_REDIRECTS.get(role, '/')
        if dest != '/':
            return redirect(dest)

    current_date    = datetime.datetime.now().strftime("%Y-%m-%d")
    events          = []
    calendar_events = []

    try:
        color_map = {
            'Technical':  '#f37021',
            'Cultural':   '#7c3aed',
            'Sports':     '#10b981',
            'Management': '#0891b2',
        }
        for e in (db.collection('events')
                    .where(filter=FieldFilter('status', '==', 'active'))
                    .stream()):
            d       = e.to_dict()
            d['id'] = e.id
            d.setdefault('description',        'An exciting event at Sapthagiri NPS University.')
            d.setdefault('registration_count', 0)
            d.setdefault('entry_fee',          0)
            d.setdefault('category',           'General')
            events.append(d)
            cat = d.get('category', 'General')
            calendar_events.append({
                'title': d.get('title', 'Event'),
                'start': d.get('date', ''),
                'url':   f"/forms/register/{d['id']}",
                'color': color_map.get(cat, '#0d2d62'),
            })
    except Exception as exc:
        app.logger.error("Home page Firebase error: %s", exc)

    return render_template('index.html',
        events=events,
        current_date=current_date,
        calendar_events=json.dumps(calendar_events))


# =========================================================
# EVENT DETAILS
# =========================================================
@app.route('/event/<event_id>')
def event_details(event_id):
    try:
        doc = db.collection('events').document(event_id).get()
        if not doc.exists:
            return render_template('404.html'), 404

        event       = doc.to_dict()
        event['id'] = event_id
        event.setdefault('title',              'Event')
        event.setdefault('description',        '')
        event.setdefault('overview',           '')
        event.setdefault('rules',              '')
        event.setdefault('prizes',             '')
        event.setdefault('date',               'TBD')
        event.setdefault('deadline',           '')
        event.setdefault('venue',              'SNPSU Campus')
        event.setdefault('category',           'General')
        event.setdefault('entry_fee',          0)
        event.setdefault('is_team_event',      False)
        event.setdefault('registration_count', 0)
        event.setdefault('judging_criteria',   [])
        event.setdefault('media_urls',         [])
        event.setdefault('banner_url',         '')
        event.setdefault('status',             'active')
        event.setdefault('organizer',          event.get('created_by', 'SNPSU'))
        event.setdefault('staff',              [])
        event.setdefault('fees',               event.get('entry_fee', 0))
        event.setdefault('fee',                event.get('entry_fee', 0))
        event.setdefault('price',              event.get('entry_fee', 0))
        event.setdefault('organiser',          event.get('organizer', 'SNPSU'))

        is_registered = False
        if session.get('user_id'):
            q = (db.collection('registrations')
                   .where(filter=FieldFilter('event_id',   '==', event_id))
                   .where(filter=FieldFilter('lead_email', '==', session['user_id']))
                   .limit(1).stream())
            is_registered = any(q)

        return render_template('public/event_details.html',
                               event=event, is_registered=is_registered)
    except Exception as exc:
        app.logger.error("Event details error: %s", exc)
        return render_template('500.html'), 500


# =========================================================
# REGISTRATION CONFIRMED PAGE
# =========================================================
@app.route('/registration/confirmed')
def registration_confirmed():
    data = session.pop('reg_confirmed', None)
    if not data:
        return redirect('/participant/dashboard')
    data['user_email'] = session.get('user_id', '')
    return render_template('participant/registration_confirmed.html', **data)


# =========================================================
# CALENDAR JSON FEED
# =========================================================
@app.route('/api/calendar')
def get_calendar_json():
    try:
        color_map = {'Technical':'#f37021','Cultural':'#7c3aed',
                     'Sports':'#10b981','Management':'#0891b2'}
        out = []
        for d in (db.collection('events')
                    .where(filter=FieldFilter('status', '==', 'active'))
                    .stream()):
            ev  = d.to_dict()
            cat = ev.get('category', 'General')
            out.append({'title': ev.get('title',''), 'start': ev.get('date',''),
                        'url':   f"/forms/register/{d.id}",
                        'color': color_map.get(cat, '#0d2d62')})
        return jsonify(out)
    except Exception:
        return jsonify([])


# =========================================================
# PUBLIC EVENTS CALENDAR
# =========================================================
@app.route('/calendar')
def events_calendar():
    color_map = {'Technical':'#f37021','Cultural':'#7c3aed',
                 'Sports':'#10b981','Management':'#0891b2'}
    events, cal_events = [], []
    try:
        for doc in (db.collection('events')
                      .where(filter=FieldFilter('status', '==', 'active'))
                      .stream()):
            d = doc.to_dict()
            d['id'] = doc.id
            cat = d.get('category', 'General')
            events.append(d)
            cal_events.append({
                'title':    d.get('title', 'Event'),
                'start':    d.get('date', ''),
                'url':      f"/forms/register/{doc.id}",
                'color':    color_map.get(cat, '#1a2557'),
                'category': cat,
                'venue':    d.get('venue', 'SNPSU'),
            })
    except Exception as exc:
        app.logger.error("Calendar page error: %s", exc)
    return render_template('public/calendar.html',
                           events=events, calendar_events=cal_events)


# =========================================================
# CERTIFICATE VERIFICATION
# =========================================================
@app.route('/verify', methods=['GET', 'POST'])
def verify_lookup():
    """Public lookup form: paste a certificate ID and redirect to verifier."""
    if request.method == 'POST':
        cert_id = (request.form.get('cert_id') or '').strip()
        if cert_id:
            return redirect(f'/verify/{cert_id}')
    return render_template('public/verify_lookup.html')


@app.route('/verify/<reg_id>')
def verify_certificate(reg_id):
    try:
        reg_doc = db.collection('registrations').document(reg_id).get()
        if not reg_doc.exists:
            return render_template('public/verify_fail.html', reg_id=reg_id)
        data = reg_doc.to_dict()
        if data.get('attendance') != 'Present':
            return render_template('public/verify_fail.html',
                                   reg_id=reg_id, reason='Absent')
        event = db.collection('events').document(data['event_id']).get().to_dict() or {}

        # Resolve student portfolio link (USN) for the cert recipient
        student_usn = None
        lead_email = data.get('lead_email')
        if lead_email:
            user_doc = db.collection('users').document(lead_email).get()
            if user_doc.exists:
                student_usn = (user_doc.to_dict() or {}).get('usn')

        return render_template(
            'public/verify_success.html',
            data=data, event=event, student_usn=student_usn)
    except Exception as exc:
        app.logger.error("Certificate verify error: %s", exc)
        return render_template('500.html'), 500


# =========================================================
# REQUEST LOGGING MIDDLEWARE
# =========================================================
@app.before_request
def log_request():
    """Log all incoming requests"""
    request.start_time = datetime.datetime.now()
    if request.path not in ['/health', '/health/ready', '/favicon.ico']:
        logger.info(f"→ {request.method} {request.path} from {request.remote_addr}")

@app.after_request
def log_response(response):
    """Log response details"""
    if hasattr(request, 'start_time'):
        duration = (datetime.datetime.now() - request.start_time).total_seconds()
        if request.path not in ['/health', '/health/ready', '/favicon.ico']:
            logger.info(f"← {response.status_code} {request.method} {request.path} ({duration:.3f}s)")
    return response
@app.after_request
def apply_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options']        = 'SAMEORIGIN'
    response.headers['Referrer-Policy']        = 'strict-origin-when-cross-origin'
    # Don't cache HTML pages — allow static assets to cache normally
    if 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma']        = 'no-cache'
        response.headers['Expires']       = '0'
    return response


# =========================================================
# ERROR HANDLERS
# =========================================================
@app.errorhandler(404)
def not_found(e):
    logger.warning(f"404 Not Found: {request.path}")
    return render_template('404.html'), 404

@app.errorhandler(429)
def rate_limited(e):
    logger.warning(f"429 Rate Limit: {request.remote_addr} on {request.path}")
    return render_template('429.html'), 429

@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 Server Error: {e}", exc_info=True)
    return render_template('500.html'), 500


# =========================================================
# CELERY — bind Flask app context to the Celery instance
# Scheduling and async work run in celery-worker / celery-beat
# containers, NOT in the web fleet. The web fleet is stateless.
# =========================================================
from celery_app import init_celery  # noqa: E402
init_celery(app)


# =========================================================
# ENTRY POINT  (local dev only)
# =========================================================
if __name__ == '__main__':
    debug_mode = app.config.get('FLASK_ENV', 'development') != 'production'
    app.run(debug=debug_mode, host='0.0.0.0', port=int(os.environ.get('PORT', 5001)), use_reloader=False)  # nosec B104