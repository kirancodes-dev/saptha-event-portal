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
from google.cloud.firestore_v1.base_query import FieldFilter
from config import Config
from dotenv import load_dotenv
from scheduler import init_scheduler

load_dotenv()

# =========================================================
# LOGGING CONFIGURATION
# =========================================================
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================================================
# APP FACTORY
# =========================================================
app = Flask(__name__)
app.config.from_object(Config)

# =========================================================
# EXTENSIONS
# =========================================================
mail = Mail(app)

limiter = Limiter(
    key_func=flask_limiter.util.get_remote_address,
    app=app,
    default_limits=app.config.get('RATELIMIT_DEFAULT', '5000 per day;500 per hour').split(';'),
    storage_uri=app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
)

# =========================================================
# FIREBASE  —  reads FIREBASE_CREDENTIALS env var on Railway
#              falls back to local serviceAccountKey.json for dev
# =========================================================
if not firebase_admin._apps:
    firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
    if firebase_creds_json:
        try:
            cred_dict = json.loads(firebase_creds_json)
            if isinstance(cred_dict, str):          # double-encoded guard
                cred_dict = json.loads(cred_dict)
            cred = credentials.Certificate(cred_dict)
        except Exception as exc:
            app.logger.error("FIREBASE_CREDENTIALS parse error: %s", exc)
            raise
    else:
        key_path = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')
        cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# =========================================================
# BLUEPRINTS
# =========================================================
from routes_auth        import auth_bp
from routes_api         import api_bp  # Ensure routes_api.py exists in the same directory
from routes_ai_matching import ai_bp
from routes_admin       import admin_bp
from routes_coordinator import coord_bp
from routes_participant import participant_bp
from routes_payment     import payment_bp
from routes_judge       import judge_bp
from routes_profile     import profile_bp
from routes_feedback    import feedback_bp
from chatbot_routes     import chatbot_bp
from routes_ticket      import ticket_bp
from routes_forms       import forms_bp

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

# =========================================================
# ROLE → DASHBOARD MAP
# =========================================================
ROLE_REDIRECTS = {
    'Student':          '/participant/dashboard',
    'SuperAdmin':       '/admin/dashboard',
    'Super Admin':      '/admin/dashboard',
    'Admin':            '/admin/dashboard',
    'Coordinator':      '/coordinator/dashboard',
    'ClubSPOC':         '/coordinator/dashboard',
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
# CERTIFICATE VERIFICATION
# =========================================================
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
        event = db.collection('events').document(data['event_id']).get().to_dict()
        return render_template('public/verify_success.html', data=data, event=event)
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
# PRODUCTION — Gunicorn entry point (Railway / Docker)
# Gunicorn imports this module, not __main__, so the scheduler
# must start here too, not just inside  if __name__ == '__main__'
# =========================================================
if os.environ.get('FLASK_ENV') == 'production':
    init_scheduler(app)


# =========================================================
# ENTRY POINT  (local dev only)
# =========================================================
if __name__ == '__main__':
    debug_mode = app.config.get('FLASK_ENV', 'development') != 'production'
    init_scheduler(app)
    app.run(debug=debug_mode, host='0.0.0.0', port=5000, use_reloader=False)