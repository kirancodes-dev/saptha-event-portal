import datetime
import logging

from flask import Blueprint, current_app, jsonify, request
from google import genai
from google.cloud.firestore_v1.base_query import FieldFilter

from models import db

logger     = logging.getLogger(__name__)
chatbot_bp = Blueprint('chatbot', __name__, url_prefix='/chatbot')

_client = None   # initialised lazily so we always read the live config value


def _get_client():
    global _client
    if _client is None:
        api_key = current_app.config.get('GEMINI_API_KEY', '')
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set in config / environment.")
        _client = genai.Client(api_key=api_key)
    return _client


@chatbot_bp.route('/ask', methods=['POST'])
def ask():
    try:
        data         = request.get_json() or {}
        user_message = data.get('message', '').strip()

        if not user_message:
            return jsonify({'reply': "I didn't catch that — please ask again!"})

        current_date = datetime.datetime.now().strftime("%Y-%m-%d")

        # Build live event context
        events_ref = db.collection('events') \
                       .where(filter=FieldFilter('status', '==', 'active')) \
                       .stream()
        context   = f"Today's date: {current_date}\n\nActive events open for registration:\n"
        has_events = False

        for e in events_ref:
            evt        = e.to_dict()
            event_date = evt.get('date', '')
            if event_date < current_date:
                continue
            has_events = True
            context += (
                f"\n• {evt.get('title')}\n"
                f"  Date: {event_date} | Venue: {evt.get('venue')} "
                f"| Fee: ₹{evt.get('entry_fee', 0)}\n"
                f"  Details: {evt.get('overview', 'No details provided.')}\n"
            )

        if not has_events:
            context += "No upcoming events are currently scheduled.\n"

        system_prompt = (
            "You are 'Sparky', the official AI assistant for the Sapthagiri NPS University "
            "Event Portal. Help students with event questions. Be concise (2–3 sentences), "
            "enthusiastic, and accurate. Use occasional emojis.\n\n"
            f"LIVE DATABASE:\n{context}\n\n"
            "If an event has passed, say registration is closed. "
            "If the question is not about the listed events, say you don't have that info.\n\n"
            f"Student's question: {user_message}"
        )

        response = _get_client().models.generate_content(
            model='gemini-2.5-flash',
            contents=system_prompt
        )
        return jsonify({'reply': response.text})

    except Exception as exc:
        logger.error("Chatbot error: %s", exc)
        return jsonify({
            'reply': "Oops! My AI brain is rebooting. Please try again in a moment! 🤖⚡"
        })