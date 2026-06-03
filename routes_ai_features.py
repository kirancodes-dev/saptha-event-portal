# routes_ai_features.py — Auto-Generation and Chatbot 2.0 blueprint
# Python 3.9 compatible

import json
import logging
from flask import Blueprint, request, jsonify, current_app, session
from google import genai
def _db():
    from app import db
    return db
from utils import login_required, role_required, log_action

logger = logging.getLogger(__name__)
ai_features_bp = Blueprint('ai_features', __name__, url_prefix='/ai')

COORD_ROLES = ['ClubSPOC', 'Coordinator', 'SuperAdmin', 'Super Admin']

def _gemini_client():
    api_key = current_app.config.get('GEMINI_API_KEY', '')
    if not api_key:
        # Check environment as backup
        import os
        api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY not configured.')
    return genai.Client(api_key=api_key)


@ai_features_bp.route('/generate_event_details', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def generate_event_details():
    """POST /ai/generate_event_details — Auto-generates rules, descriptions, and criteria."""
    data = request.json or {}
    title = data.get('title', '').strip()
    category = data.get('category', '').strip()

    if not title or not category:
        return jsonify({'error': 'Title and Category are required'}), 400

    prompt = f"""You are the lead designer for college fest activities at Sapthagiri NPS University.
Design a premium event with:
Title: {title}
Category: {category}

Generate and return a JSON structure with these exact keys:
{{
  "description": "<detailed paragraph describing the theme, excitement, and purpose of this event>",
  "rules": [
    "<rule 1>",
    "<rule 2>",
    "<rule 3>",
    "<rule 4>"
  ],
  "judging_criteria": [
    "<criterion 1>",
    "<criterion 2>",
    "<criterion 3>"
  ]
}}

Return ONLY the raw JSON string — no markdown tags, no backticks."""

    try:
        client = _gemini_client()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        raw_text = response.text.strip()
        if raw_text.startswith('```'):
            raw_text = raw_text.split('\n', 1)[1] if '\n' in raw_text else raw_text[3:]
            raw_text = raw_text.rsplit('```', 1)[0].strip()

        result = json.loads(raw_text)
        return jsonify({'status': 'success', 'data': result})
    except Exception as e:
        logger.error("AI details generation failed: %s", e)
        return jsonify({'error': str(e)}), 500


@ai_features_bp.route('/chatbot_advanced', methods=['POST'])
def chatbot_advanced():
    """POST /ai/chatbot_advanced — Dynamic context-aware chatbot query endpoint."""
    data = request.json or {}
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'error': 'Message is required'}), 400

    try:
        # Load all events from Firestore to construct fresh local context
        events_ref = _db().collection('events').stream()
        events_list = []
        for e in events_ref:
            d = e.to_dict()
            events_list.append({
                'id': e.id,
                'title': d.get('title', 'Unknown'),
                'category': d.get('category', 'General'),
                'date': d.get('date', 'TBD'),
                'venue': d.get('venue', 'TBD'),
                'entry_fee': d.get('entry_fee', 0),
                'status': d.get('status', 'active')
            })

        # Inject context into Gemini instruction
        context_str = json.dumps(events_list, indent=2)
        
        prompt = f"""You are the official campus event concierge assistant at Sapthagiri NPS University.
Below is the database of all registered events in our university portal:
{context_str}

Use this database to answer the student's question accurately.
Provide links to register using '/payment/checkout/<event_id>' if they want to join a paid event, or just explain the registration steps.
Keep the response warm, clean, and professional.

Student's question: {message}"""

        client = _gemini_client()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        return jsonify({
            'status': 'success',
            'reply': response.text.strip()
        })
    except Exception as e:
        logger.error("Chatbot advanced response failed: %s", e)
        return jsonify({'error': str(e)}), 500
