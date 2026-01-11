from flask import Flask, render_template, session
from flask_mail import Mail
from models import db, SuperAdmin, Event, Participant
from config import Config

# --- BLUEPRINT IMPORTS ---
from routes_auth import auth_bp
from routes_super import super_bp
from routes_spoc import spoc_bp
from routes_head import head_bp
from routes_participant import participant_bp
from routes_judge import judge_bp 

mail = Mail()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # --- EMAIL CONFIGURATION ---
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'sapthhack@gmail.com'  
    app.config['MAIL_PASSWORD'] = 'oivm qpty tpfs ktjk'  
    # UPDATED SENDER NAME:
    app.config['MAIL_DEFAULT_SENDER'] = ('SapthaEvent Portal', 'sapthhack@gmail.com')
    
    # Initialize Extensions
    db.init_app(app)
    mail.init_app(app)
    app.extensions['mail'] = mail

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(super_bp)
    app.register_blueprint(spoc_bp)
    app.register_blueprint(head_bp)
    app.register_blueprint(participant_bp)
    app.register_blueprint(judge_bp)

    return app

app = create_app()

# --- HOME ROUTE ---
@app.route('/')
def home():
    try:
        # Fetch featured (latest 3 published) and upcoming events
        featured_events = Event.query.filter_by(is_published=True).order_by(Event.date).limit(3).all()
        upcoming = Event.query.filter_by(is_published=True).order_by(Event.date).all()
    except Exception as e:
        print(f"Database Error: {e}")
        featured_events = []
        upcoming = []
    return render_template('home.html', featured=featured_events, upcoming=upcoming)

# --- EVENT DETAILS ROUTE ---
@app.route('/event/<int:event_id>')
def event_details(event_id):
    event = Event.query.get_or_404(event_id)
    
    is_registered = False
    # Check registration status if user is a participant
    if session.get('role') == 'Participant' and session.get('user_id'):
        user = Participant.query.get(session['user_id'])
        if user and event in user.events_attended:
            is_registered = True

    return render_template('event_details.html', event=event, is_registered=is_registered)

if __name__ == '__main__':
    with app.app_context():
        # Auto-create tables
        db.create_all()
        
        # Create Super Admin if not exists
        if not SuperAdmin.query.first():
            print("\n--- CREATING SUPER ADMIN ---")
            # You can keep the admin email as is for login consistency
            admin = SuperAdmin(email='admin@sapthahack.com', password='admin', secret_key='SuperSecret123')
            db.session.add(admin)
            db.session.commit()
            print("Super Admin Created: admin@sapthahack.com / admin")
            
    app.run(debug=True, port=5000)