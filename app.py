import os
import json
import datetime
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
    default_limits=["200 per day", "50 per hour"],
    storage_uri=app.config['RATELIMIT_STORAGE_URL']
)

# =========================================================
# FIREBASE
# =========================================================
if not firebase_admin._apps:
    key_path = os.environ.get('FIREBASE_KEY_PATH', 'serviceAccountKey.json')
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# =========================================================
# BLUEPRINTS
# =========================================================
from routes_auth        import auth_bp
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
# FAVICON
# =========================================================
@app.route('/favicon.ico')
def favicon():
    try:
        from flask import send_from_directory
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon'
        )
    except Exception:
        return Response(status=204)

# Suppress Cloudflare email-decode script 404 noise in dev logs
@app.route('/cdn-cgi/<path:subpath>')
def cdn_cgi_suppress(subpath):
    return Response(status=204)

# =========================================================
# HOME
# =========================================================
@app.route('/')
def home():
    # Logged-in users go straight to their dashboard
    if 'user_id' in session:
        role = session.get('role', '')
        dest = ROLE_REDIRECTS.get(role, '/')
        if dest != '/':
            return redirect(dest)

    current_date    = datetime.datetime.now().strftime("%Y-%m-%d")
    events          = []
    calendar_events = []

    try:
        events_ref = (
            db.collection('events')
              .where(filter=FieldFilter('status', '==', 'active'))
              .stream()
        )
        color_map = {
            'Technical':  '#f37021',
            'Cultural':   '#7c3aed',
            'Sports':     '#10b981',
            'Management': '#0891b2',
        }
        for e in events_ref:
            d       = e.to_dict()
            d['id'] = e.id
            d.setdefault('description', 'An exciting event at Sapthagiri NPS University.')
            d.setdefault('registration_count', 0)
            d.setdefault('entry_fee', 0)
            d.setdefault('category', 'General')
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

    return render_template(
        'index.html',
        events=events,
        current_date=current_date,
        calendar_events=json.dumps(calendar_events),
    )


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

        # Provide safe defaults for every field the template might access
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

        is_registered = False
        if session.get('user_id'):
            q = (db.collection('registrations')
                   .where(filter=FieldFilter('event_id',   '==', event_id))
                   .where(filter=FieldFilter('lead_email', '==', session['user_id']))
                   .limit(1).stream())
            is_registered = any(q)

        return render_template('public/event_details.html',
                               event=event,
                               is_registered=is_registered)
    except Exception as exc:
        app.logger.error("Event details error: %s", exc)
        return render_template('500.html'), 500


# =========================================================
# FULLCALENDAR JSON FEED
# =========================================================
@app.route('/api/events')
def get_events_json():
    try:
        color_map = {
            'Technical':  '#f37021',
            'Cultural':   '#7c3aed',
            'Sports':     '#10b981',
            'Management': '#0891b2',
        }
        out = []
        for d in (db.collection('events')
                    .where(filter=FieldFilter('status', '==', 'active'))
                    .stream()):
            ev  = d.to_dict()
            cat = ev.get('category', 'General')
            out.append({
                'title': ev.get('title', ''),
                'start': ev.get('date', ''),
                'url':   f"/forms/register/{d.id}",
                'color': color_map.get(cat, '#0d2d62'),
            })
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
# SECURITY HEADERS
# =========================================================
@app.after_request
def apply_security_headers(response):
    response.headers['Cache-Control']          = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma']                 = 'no-cache'
    response.headers['Expires']                = '0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options']        = 'SAMEORIGIN'
    response.headers['Referrer-Policy']        = 'strict-origin-when-cross-origin'
    return response


# =========================================================
# ERROR HANDLERS
# =========================================================
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(429)
def rate_limited(e):
    return render_template('429.html'), 429

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


# =========================================================
# ENTRY POINT
# =========================================================
if __name__ == '__main__':
    debug_mode = app.config.get('FLASK_ENV', 'development') != 'production'
    # Start the 24-hour reminder scheduler (background thread, no UI)
    init_scheduler(app)
    app.run(debug=debug_mode, host='0.0.0.0', port=5000, use_reloader=False)