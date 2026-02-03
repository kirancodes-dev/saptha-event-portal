from flask import Blueprint, request, jsonify
from models import db
import datetime

chatbot_bp = Blueprint('chatbot', __name__)

@chatbot_bp.route('/api/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '').lower()
    response_text = "I didn't understand that. Try asking about 'events', 'dates', or 'clubs'."

    try:
        # 1. GREETINGS
        if any(x in user_msg for x in ['hi', 'hello', 'hey']):
            return jsonify({'reply': "Hello! I am the SapthaEvent Assistant. Ask me about upcoming events or club contacts."})

        # 2. QUERY: "EVENTS" or "HACKATHON"
        if 'event' in user_msg or 'hackathon' in user_msg or 'show' in user_msg:
            # Fetch active events from DB
            events_ref = db.collection('events').where('status', '==', 'active').stream()
            events = [doc.to_dict()['title'] for doc in events_ref]
            
            if events:
                return jsonify({'reply': f"Here are the active events: {', '.join(events)}. Type an event name to know more!"})
            else:
                return jsonify({'reply': "There are no active events scheduled right now."})

        # 3. QUERY: SPECIFIC EVENT DETAILS (Search DB for Title)
        # We check if any active event title is in the user's message
        all_events = db.collection('events').stream()
        for doc in all_events:
            data = doc.to_dict()
            title = data.get('title', '').lower()
            
            if title in user_msg:
                # Found a match! Return details
                reply = f"**{data['title']}** is on {data['date']} at {data['venue']}. <br> Deadline: {data['reg_deadline']}."
                if data.get('group_link'):
                    reply += f" <a href='{data['group_link']}' target='_blank'>Join Group</a>"
                return jsonify({'reply': reply})

        # 4. QUERY: CONTACTS / SPOC
        if 'contact' in user_msg or 'spoc' in user_msg or 'lead' in user_msg:
            return jsonify({'reply': "You can find Club Leads (SPOCs) listed on the specific Event Details page under the 'Contact' tab."})

        # 5. QUERY: REGISTRATION
        if 'register' in user_msg or 'signup' in user_msg:
            return jsonify({'reply': "To register, login as a Student, go to the event page, and click 'Register Now'. If it's a team event, you'll need your teammates' details."})

    except Exception as e:
        print(f"Chat Error: {e}")
        return jsonify({'reply': "Sorry, I'm having trouble connecting to the database."})

    return jsonify({'reply': response_text})