from flask import Flask, session, render_template
from flask_mail import Mail
from config import Config
from models import db
import logging

# --- IMPORT BLUEPRINTS ---
from routes_public import public_bp       # Home & Event Poster
from routes_auth import auth_bp           # Login & Student Sign Up
from routes_participant import participant_bp # Student Dashboard & Reg
from routes_super import super_bp         # Super Admin Dashboard
from routes_spoc import spoc_bp           # Club SPOC Dashboard
from routes_head import head_bp           # Coordinator Dashboard
from routes_judge import judge_bp         # Judge Dashboard
from chatbot_routes import chatbot_bp     # Chatbot API Endpoint

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

    # --- REGISTER BLUEPRINTS ---
    app.register_blueprint(public_bp)      # Routes: / (Home), /event/<id>
    app.register_blueprint(auth_bp)        # Routes: /login, /register
    app.register_blueprint(participant_bp) # Routes: /participant/*
    app.register_blueprint(super_bp)       # Routes: /super_admin/*
    app.register_blueprint(spoc_bp)        # Routes: /spoc/*
    app.register_blueprint(head_bp)        # Routes: /event_head/*
    app.register_blueprint(judge_bp)       # Routes: /judge/*
    app.register_blueprint(chatbot_bp)     # Route: /api/chatbot

    # --- GLOBAL CONTEXT PROCESSOR ---
    # Injects variables into ALL HTML templates automatically
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

# --- ERROR HANDLERS ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # --- SYSTEM INIT ---
    # Auto-create Super Admin if not exists
    try:
        admin_email = 'admin@sapthahack.com'
        if db:
            doc = db.collection('users').document(admin_email).get()
            if not doc.exists:
                logger.info("--- SYSTEM INIT: Creating Default Super Admin ---")
                db.collection('users').document(admin_email).set({
                    'email': admin_email,
                    'password': 'admin', # Change in Production!
                    'role': 'SuperAdmin',
                    'name': 'System Administrator',
                    'created_at': '2026-01-30'
                })
    except Exception as e:
        logger.warning(f"Startup DB Check Failed: {e}")

    app.run(debug=True, port=5000)