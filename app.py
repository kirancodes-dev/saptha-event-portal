from flask import Flask, render_template, session, redirect, url_for
from flask_mail import Mail
from config import Config
from models import db, FirebaseWrapper
import logging

# --- IMPORT BLUEPRINTS ---
# Ensure these files (routes_*.py) exist in your folder from the previous step
from routes_auth import auth_bp
from routes_super import super_bp
from routes_spoc import spoc_bp
from routes_head import head_bp
from routes_participant import participant_bp
from routes_judge import judge_bp 

# Initialize Extensions
mail = Mail()
# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize Mail
    mail.init_app(app)
    app.extensions['mail'] = mail

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(super_bp)
    app.register_blueprint(spoc_bp)
    app.register_blueprint(head_bp)
    app.register_blueprint(participant_bp)
    app.register_blueprint(judge_bp)

    # --- GLOBAL CONTEXT PROCESSOR ---
    # This injects variables into ALL HTML templates automatically
    @app.context_processor
    def inject_globals():
        return dict(
            app_name=Config.APP_NAME,
            organization=Config.ORGANIZATION,
            current_user_name=session.get('name', 'User'),
            current_user_role=session.get('role', 'Guest')
        )

    return app

app = create_app()

# --- GLOBAL ROUTES ---

@app.route('/')
def home():
    """Landing Page Logic"""
    featured_events = []
    upcoming = []
    
    try:
        if db:
            events_ref = db.collection('events')
            # Query: Published events only
            query = events_ref.where('is_published', '==', True).stream()
            
            # Convert to Wrappers
            all_events = [FirebaseWrapper(doc.id, doc.to_dict()) for doc in query]
            
            # Python-side sorting (since Firestore compound queries require indexes)
            # Sorting by 'date' string (YYYY-MM-DD)
            all_events.sort(key=lambda x: x.date)

            # Slice lists for UI sections
            featured_events = all_events[:3] # Top 3 soonest
            upcoming = all_events            # All events list
            
    except Exception as e:
        logger.error(f"Home Page Error: {e}")
        # Fail gracefully (empty lists)
    
    return render_template('home.html', featured=featured_events, upcoming=upcoming)

@app.route('/event/<event_id>')
def event_details(event_id):
    """Public Event Details Page"""
    try:
        if not db: raise Exception("DB Not Connected")

        # Fetch Event
        doc_ref = db.collection('events').document(event_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return render_template('404.html'), 404
        
        event = FirebaseWrapper(event_id, doc.to_dict())
        
        # Check Registration Status for Participants
        is_registered = False
        if session.get('role') == 'Participant':
            user_email = session.get('user_id')
            
            # Check Teams collection for this event + this user
            # "member_emails" is an array field in the team document
            teams_q = db.collection('teams')\
                        .where('event_id', '==', event_id)\
                        .where('member_emails', 'array_contains', user_email)\
                        .get()
            
            if len(teams_q) > 0:
                is_registered = True

        return render_template('event_details.html', event=event, is_registered=is_registered)

    except Exception as e:
        logger.error(f"Event Details Error: {e}")
        return f"System Error: {e}", 500

# --- ERROR HANDLERS ---
@app.errorhandler(404)
def page_not_found(e):
    # You can create a simple 404.html template if you wish
    return "<h1>404 - Page Not Found</h1><p>The requested page could not be found.</p><a href='/'>Go Home</a>", 404

if __name__ == '__main__':
    # Auto-create Admin on startup (Safety Check)
    try:
        admin_email = 'admin@sapthahack.com'
        if db:
            doc = db.collection('users').document(admin_email).get()
            if not doc.exists:
                print("--- SYSTEM INIT: Creating Super Admin ---")
                db.collection('users').document(admin_email).set({
                    'email': admin_email,
                    'password': 'admin', # Dev password
                    'role': 'SuperAdmin',
                    'name': 'System Administrator'
                })
    except Exception as e:
        print(f"Startup Init Warning: {e}")

    app.run(debug=True, port=5000)