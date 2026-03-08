from flask import Blueprint, render_template, jsonify, session
from models import db, FirebaseWrapper 

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def home():
    """Landing Page: Slider + Calendar + Event List"""
    featured_events = []
    upcoming = []
    
    try:
        if db:
            # Query: Active events only
            events_ref = db.collection('events').where('status', '==', 'active').stream()
            
            all_events = []
            for doc in events_ref:
                data = doc.to_dict()
                event_obj = FirebaseWrapper(doc.id, data) 
                all_events.append(event_obj)
            
            # Sort by date
            all_events.sort(key=lambda x: x.date if hasattr(x, 'date') else '9999-99-99')

            # Filter Featured vs Regular
            featured_events = [e for e in all_events if getattr(e, 'is_featured', False)][:3]
            upcoming = all_events
            
    except Exception as e:
        print(f"Home Page Error: {e}")
    
    return render_template('public/home.html', featured_events=featured_events, events=upcoming)

@public_bp.route('/event/<event_id>')
def event_details(event_id):
    """The 'Event Poster' Page: Rules, Description, Register Button"""
    try:
        doc_ref = db.collection('events').document(event_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return "Event not found", 404
        
        event = FirebaseWrapper(event_id, doc.to_dict())
        
        # Check if User is Already Registered
        is_registered = False
        if session.get('user_id'):
            user_email = session.get('user_id')
            # Check 'registrations' collection for this user + event
            reg_query = db.collection('registrations')\
                          .where('event_id', '==', event_id)\
                          .where('lead_email', '==', user_email)\
                          .limit(1).stream()
            
            if any(reg_query):
                is_registered = True

        return render_template('public/event_details.html', event=event, is_registered=is_registered)

    except Exception as e:
        print(f"Event Details Error: {e}")
        return "System Error", 500

@public_bp.route('/api/events')
def get_events_json():
    """API for FullCalendar"""
    try:
        if not db: return jsonify([])
        events_ref = db.collection('events').where('status', '==', 'active').stream()
        events_list = []
        for doc in events_ref:
            data = doc.to_dict()
            events_list.append({
                'title': data.get('title'),
                'start': data.get('date'), 
                'url': f"/event/{doc.id}", 
                'className': 'fc-event-custom'
            })
        return jsonify(events_list)
    except Exception:
        return jsonify([])