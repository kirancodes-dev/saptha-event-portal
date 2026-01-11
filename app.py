from flask import Flask, render_template, session, abort
from flask_mail import Mail
from config import Config

# --- IMPORT DATABASE CONNECTION ---
# We import 'db' from the new models.py we just created
from models import db 

# --- BLUEPRINT IMPORTS ---
# NOTE: You must eventually update the code inside these files 
# to use Firebase logic (db.collection) instead of SQL logic!
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
    app.config['MAIL_DEFAULT_SENDER'] = ('SapthaEvent Portal', 'sapthhack@gmail.com')
    
    # Initialize Mail Extension
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

# --- HOME ROUTE (FIREBASE VERSION) ---
@app.route('/')
def home():
    featured_events = []
    upcoming = []
    try:
        events_ref = db.collection('events')
        
        # Fetch Events where is_published == True
        # Note: Firestore queries require an index for complex sorting. 
        # For now, we fetch and sort in Python if data is small, or use simple .stream()
        query = events_ref.where('is_published', '==', True).stream()
        
        # Convert Firestore documents to a list of dictionaries
        all_events = []
        for doc in query:
            event_data = doc.to_dict()
            event_data['id'] = doc.id  # IMPORTANT: Attach the ID to the data
            all_events.append(event_data)

        # Sort by date manually (string sort)
        all_events.sort(key=lambda x: x.get('date', ''))

        # Split into featured (first 3) and upcoming (rest)
        featured_events = all_events[:3]
        upcoming = all_events # Or all_events[3:] if you want to exclude featured

    except Exception as e:
        print(f"Firebase Error: {e}")
    
    return render_template('home.html', featured=featured_events, upcoming=upcoming)

# --- EVENT DETAILS ROUTE (FIREBASE VERSION) ---
@app.route('/event/<event_id>') # Changed from int:event_id to event_id (String)
def event_details(event_id):
    try:
        # 1. Fetch Event Document
        event_ref = db.collection('events').document(event_id)
        event_doc = event_ref.get()

        if not event_doc.exists:
            abort(404) # Event not found

        event = event_doc.to_dict()
        event['id'] = event_doc.id

        # 2. Check Registration Status
        is_registered = False
        if session.get('role') == 'Participant' and session.get('user_id'):
            user_email = session['user_id']
            
            # Check the sub-collection 'participants' inside the event 
            # OR check an array inside the user document. 
            # Here we assume there is a 'participants' sub-collection in the event.
            participant_doc = event_ref.collection('participants').document(user_email).get()
            
            if participant_doc.exists:
                is_registered = True

        return render_template('event_details.html', event=event, is_registered=is_registered)

    except Exception as e:
        print(f"Error fetching details: {e}")
        abort(404)

if __name__ == '__main__':
    # --- AUTO-CREATE SUPER ADMIN (FIREBASE) ---
    try:
        admin_email = 'admin@sapthahack.com'
        users_ref = db.collection('users')
        doc = users_ref.document(admin_email).get()

        if not doc.exists:
            print("\n--- CREATING SUPER ADMIN (FIREBASE) ---")
            admin_data = {
                'email': admin_email,
                'password': 'admin', # Remember to hash this in production!
                'role': 'SuperAdmin',
                'name': 'System Administrator'
            }
            users_ref.document(admin_email).set(admin_data)
            print("Super Admin Created in Firestore!")
    except Exception as e:
        print(f"Startup Error: {e}")

    app.run(debug=True, port=5000)