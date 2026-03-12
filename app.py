from flask import Flask, render_template, session, redirect
from flask_mail import Mail
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter 
import os
import datetime

app = Flask(__name__)

# --- CRITICAL FIX: HARDCODED SECRET KEY ---
# Do not use os.urandom here, as it clears sessions on server restart
app.secret_key = "saptha_super_secret_key_2026"

# --- 1. EMAIL CONFIGURATION ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'sapthhack@gmail.com' 
app.config['MAIL_PASSWORD'] = 'yqfk tmdn vxof qvxj' 
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_DEFAULT_SENDER'] = ('SapthaEvent Admin', 'sapthhack@gmail.com')

mail = Mail(app)

# --- 2. FIREBASE SETUP ---
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 3. REGISTER BLUEPRINTS ---
from routes_auth import auth_bp
from routes_admin import admin_bp
from routes_coordinator import coord_bp
from routes_participant import participant_bp
from routes_payment import payment_bp
from routes_judge import judge_bp
from routes_profile import profile_bp
from chatbot_routes import chatbot_bp
from routes_feedback import feedback_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(coord_bp)
app.register_blueprint(participant_bp)
app.register_blueprint(payment_bp)
app.register_blueprint(judge_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(chatbot_bp)
app.register_blueprint(feedback_bp)

# --- 4. ROOT ROUTE (HOME SCREEN) ---
@app.route('/')
def home():
    # Fast-lane routing if someone goes to the home page while logged in
    if 'user_id' in session:
        role = session.get('role')
        if role == 'Student': 
            return redirect('/participant/dashboard')
        elif role in ['Admin', 'SuperAdmin', 'Super Admin']: 
            return redirect('/admin/dashboard')
        elif role == 'Coordinator': 
            return redirect('/coordinator/dashboard')
        elif role == 'EventCoordinator': 
            return redirect('/coordinator/scanner')
        elif role == 'Judge': 
            return redirect('/judge/dashboard')
    
    # --- REAL-TIME DATE LOGIC ---
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Fetch Active Events for Public View
    events_ref = db.collection('events').where(filter=FieldFilter('status', '==', 'active')).stream()
    events = []
    for e in events_ref:
        d = e.to_dict()
        d['id'] = e.id
        d['description'] = d.get('description', 'No description available.')
        events.append(d)
        
    return render_template('index.html', events=events, current_date=current_date)

# --- 5. CERTIFICATE VERIFICATION ROUTE ---
@app.route('/verify/<reg_id>')
def verify_certificate(reg_id):
    try:
        reg_doc = db.collection('registrations').document(reg_id).get()
        if not reg_doc.exists: 
            return render_template('public/verify_fail.html', reg_id=reg_id)
        
        data = reg_doc.to_dict()
        if data.get('attendance') != 'Present': 
            return render_template('public/verify_fail.html', reg_id=reg_id, reason="Absent")
            
        event = db.collection('events').document(data['event_id']).get().to_dict()
        return render_template('public/verify_success.html', data=data, event=event)
    except: 
        return "Verification Error", 500

# --- 6. PREVENT BROWSER CACHING (BACK BUTTON GHOST FIX) ---
@app.after_request
def prevent_caching(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)