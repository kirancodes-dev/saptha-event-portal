from flask import Blueprint, request, jsonify
from google import genai
from models import db
from google.cloud.firestore_v1.base_query import FieldFilter
import datetime

chatbot_bp = Blueprint('chatbot', __name__, url_prefix='/chatbot')

# =====================================================================
# 🔑 GEMINI SDK INTEGRATION
# =====================================================================
GEMINI_API_KEY = "AIzaSyDPyxj9yfqXtjyX5WJkHUird0cgxp3O5O4"

# Clean initialization using the new SDK
client = genai.Client(api_key=GEMINI_API_KEY)

@chatbot_bp.route('/ask', methods=['POST'])
def ask():
    try:
        data = request.get_json()
        user_message = data.get('message')

        if not user_message:
            return jsonify({'reply': "I didn't quite catch that. Could you ask again?"})

        # --- GET TODAY'S REAL-TIME DATE ---
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")

        # Fetch Active Events from Firebase
        events_ref = db.collection('events').where(filter=FieldFilter('status', '==', 'active')).stream()
        
        context = f"Today's Date is {current_date}.\n\nCurrent Active Events Open for Registration:\n"
        has_events = False
        
        for e in events_ref:
            evt = e.to_dict()
            event_date = evt.get('date', '')
            
            # Real-time AI filter: Only feed the event to the AI if it hasn't passed
            if event_date >= current_date:
                has_events = True
                context += f"- Event: {evt.get('title')}\n"
                context += f"  Date: {event_date}\n"
                context += f"  Venue: {evt.get('venue')}\n"
                context += f"  Fee: ₹{evt.get('entry_fee', 0)}\n"
                context += f"  Details: {evt.get('overview', 'No details provided.')}\n\n"

        if not has_events:
            context += "There are currently NO upcoming events scheduled. All previous events have closed."

        system_prompt = f"""
        You are 'Sparky', the official AI Helpdesk Assistant for the Sapthagiri NPS University Event Portal.
        Your job is to help students with questions about upcoming events, hackathons, and registrations.
        Be enthusiastic, highly concise (keep answers to 2-3 short sentences), and polite.
        Use emojis occasionally.
        
        Here is the LIVE data from the university database right now:
        {context}
        
        Answer the user's question based strictly on the live data provided above. 
        If they ask about an event that has already passed, politely inform them that registration is closed.
        If they ask something not in the data, tell them politely that you don't have that information.
        
        User's message: {user_message}
        """

        # Call the newest supported model
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=system_prompt
        )

        return jsonify({'reply': response.text})

    except Exception as e:
        print(f"Gemini Error: {e}")
        return jsonify({'reply': "Oops! My AI brain is currently rebooting or the API key limit was reached. Please try again in a moment! 🤖⚡"})