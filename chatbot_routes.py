from flask import Blueprint, request, jsonify
from models import db, Team, EventSettings, Judge

chat_bp = Blueprint('chat_bp', __name__)

@chat_bp.route('/bot/chat', methods=['POST'])
def chat_response():
    try:
        data = request.get_json()
        user_msg = data.get('message', '').lower()
        
        reply = ""

        # --- QUERY 1: EVENT DETAILS ---
        if "date" in user_msg or "when" in user_msg:
            event = EventSettings.query.first()
            if event and event.date:
                reply = f"The event is scheduled for {event.date}."
            else:
                reply = "The event date has not been announced yet."

        # --- QUERY 2: LIVE WINNER ---
        elif "winning" in user_msg or "leader" in user_msg or "top" in user_msg:
            # Get the team with the highest score
            top_team = Team.query.order_by(Team.score.desc()).first()
            if top_team and top_team.score > 0:
                reply = f"Currently, the leader is '{top_team.team_name}' with {top_team.score} points!"
            else:
                reply = "Scores haven't been updated yet. Check back soon!"

        # --- QUERY 3: TEAM COUNT ---
        elif "how many teams" in user_msg or "count" in user_msg:
            count = Team.query.count()
            reply = f"There are currently {count} teams registered for the event."

        # --- QUERY 4: REGISTRATION ---
        elif "register" in user_msg or "sign up" in user_msg:
            reply = "You can register by clicking the 'Participant' button on the home page."

        # --- QUERY 5: JUDGES ---
        elif "judge" in user_msg or "jury" in user_msg:
            count = Judge.query.count()
            reply = f"We have {count} expert judges evaluating the projects."

        # --- DEFAULT FALLBACK ---
        else:
            reply = "I can help with Event Dates, Registration info, or tell you who is currently winning!"

        return jsonify({"reply": reply})

    except Exception as e:
        print(f"Bot Error: {e}")
        return jsonify({"reply": "I'm having trouble connecting to the server database right now."})