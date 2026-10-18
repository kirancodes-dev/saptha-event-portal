import datetime
import logging
import os
import re
from flask import Blueprint, current_app, jsonify, request
try:
    from google import genai
except ImportError:
    genai = None
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None
from models import db
from extensions import limiter

logger     = logging.getLogger(__name__)
chatbot_bp = Blueprint('chatbot', __name__, url_prefix='/chatbot')

# Until the owner confirms the campus facts, the assistant doesn't state any
# (UPG-108): questions clearly about the campus get this answer straight away.
CHECK_WITH_OFFICE = "Please check with the college office."
_CAMPUS_QUESTION = re.compile(
    r"\b(parking|park my|canteen|cafeteria|food court|mess|hostel|toilets?|washrooms?|restrooms?|wi-?fi|"
    r"help ?desk|campus map|directions?|how (do i|to) (get|reach)|which (block|building|floor)|"
    r"where is (the )?(zone|block|building|library|office|auditorium|seminar hall|lab|gate|stadium)|"
    r"zone [a-d]\b|north gate|main gate|bus|transport|id card)", re.I)

_client = None  # initialised lazily so we always read the live config value


def _get_client():
    global _client
    if _client is None:
        # =====================================================
        # PASTE YOUR GEMINI API KEY IN .env as:
        #   GEMINI_API_KEY=your_key_here
        #
        # Get it free from: https://aistudio.google.com/app/apikey
        # Then add GEMINI_API_KEY to Railway Variables too.
        # =====================================================
        api_key = current_app.config.get('GEMINI_API_KEY', '')
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. "
                "Add it to your .env file and Railway Variables."
            )
        _client = genai.Client(api_key=api_key)
    return _client


@chatbot_bp.route('/ask', methods=['POST'])
@limiter.limit("20 per minute")   # protect Gemini API quota
def ask():
    try:
        from flask import session
        data         = request.get_json() or {}
        user_message = data.get('message', '').strip()[:500]   # cap message length
        if not user_message:
            return jsonify({'reply': "I didn't catch that — please ask again!"})
        # Campus questions get the college office, never an unconfirmed fact (UPG-108)
        if _CAMPUS_QUESTION.search(user_message):
            return jsonify({'reply': CHECK_WITH_OFFICE})

        current_date = datetime.datetime.now().strftime("%Y-%m-%d")

        # Build live event context from Firestore
        events_ref = (
            db.collection('events')
              .where(filter=FieldFilter('status', '==', 'active'))
              .stream()
        )
        context    = f"Today's date: {current_date}\n\nActive events open for registration:\n"
        has_events = False

        for e in events_ref:
            evt        = e.to_dict()
            event_date = evt.get('date', '')
            if event_date < current_date:
                continue
            has_events = True

            # Format judges/staff
            staff_list = evt.get('staff', [])
            judges     = [s.get('name') for s in staff_list if s.get('role') == 'Judge']
            judges_str = ", ".join(judges) if judges else "None assigned yet"

            # Format rooms
            rooms_list = evt.get('rooms', [])
            rooms      = [f"{r.get('name')} (capacity {r.get('capacity')})" for r in rooms_list]
            rooms_str  = ", ".join(rooms) if rooms else "None configured yet"

            # Format agenda
            agenda_list = evt.get('agenda', [])
            agenda_str  = ""
            if agenda_list:
                agenda_items = [f"  * {item.get('time')}: {item.get('title')} - {item.get('desc', '')}" for item in agenda_list]
                agenda_str   = "\nSchedule/Agenda:\n" + "\n".join(agenda_items)

            context += (
                f"\n• {evt.get('title')} (ID: {e.id})\n"
                f"  Date: {event_date} | Venue: {evt.get('venue')} | Fee: ₹{evt.get('entry_fee', 0)}\n"
                f"  Details: {evt.get('overview', 'No details provided.')}\n"
                f"  Judges: {judges_str}\n"
                f"  Rooms: {rooms_str}\n"
                f"  {agenda_str}\n"
            )

        if not has_events:
            context += "No upcoming events are currently scheduled.\n"

        # Build student's personalized context
        user_email = session.get('user_id')
        user_context = ""
        if user_email:
            user_context = f"Logged-in Student Email: {user_email}\n"
            try:
                regs = list(
                    db.collection('registrations')
                      .where(filter=FieldFilter('lead_email', '==', user_email))
                      .stream()
                )
                if regs:
                    user_context += "Student's Registrations & Assignments:\n"
                    for r in regs:
                        r_data = r.to_dict()
                        user_context += (
                            f"- Registered Event: {r_data.get('event_title')}\n"
                            f"  Ticket ID: {r_data.get('reg_id')}\n"
                            f"  Assigned Room: {r_data.get('assigned_room') or 'Not assigned yet'}\n"
                            f"  Assigned Judge: {r_data.get('assigned_judge_name') or 'Not assigned yet'}\n"
                            f"  Attendance Status: {r_data.get('attendance') or 'Absent'}\n"
                        )
            except Exception as e:
                logger.warning("Failed to fetch student registrations for chatbot: %s", e)

        # Campus facts (zones, parking, food, help desks, ID rules) are not stated
        # until the owner confirms them (UPG-108): the assistant refers students
        # to the college office instead. Only how the portal itself works is here.
        FAQ_CONTEXT = """
PORTAL FAQ:
1. Q: What do I need for check-in?
   A: Your digital ticket QR code, from your dashboard.
2. Q: How do I download a certificate?
   A: If you were marked 'Present' at the event, open your dashboard and find it under past events.
"""

        system_prompt = (
            "You are 'Sparky', the official AI assistant for the Sapthagiri NPS University "
            "Event Portal. Help students with event questions. Be concise (2–3 sentences), "
            "enthusiastic, and accurate. Use occasional emojis.\n\n"
            f"LIVE DATABASE CONTEXT:\n{context}\n\n"
            f"{FAQ_CONTEXT}\n"
            f"PERSONALIZED STUDENT CONTEXT:\n{user_context}\n\n"
            "If the student asks about their own registration status, ticket details, room assignments, "
            "assigned judges, or attendance status, refer directly to the PERSONALIZED STUDENT CONTEXT.\n"
            "If the student asks about check-in or certificates, refer to the PORTAL FAQ.\n"
            f"If the student asks about the campus itself (directions, buildings, parking, food, hostels, help desks, contacts, rules), you have no confirmed information: reply exactly \"{CHECK_WITH_OFFICE}\"\n"
            "If an event has passed, say registration is closed. "
            "If the question is not about the listed events, logistics, or user data, say you don't have that info.\n\n"
            f"Student's question: {user_message}"
        )

        # Try Zoho Zia AI first
        try:
            from zoho_zia import ask_zia_chatbot
            reply_text = ask_zia_chatbot(user_message, system_prompt)
            if reply_text:
                return jsonify({'reply': reply_text})
        except Exception as z_err:
            logger.warning("Zoho Zia primary call skipped: %s. Falling back to Gemini Client.", z_err)

        # Gemini Client fallback
        try:
            response = _get_client().models.generate_content(
                model='gemini-2.5-flash',
                contents=system_prompt
            )
            return jsonify({'reply': response.text})
        except Exception as g_err:
            logger.warning("Gemini API fallback error: %s", g_err)
            # No AI answered: say so, and point to the configured support address (UPG-65)
            support = (os.environ.get('SUPPORT_EMAIL') or '').strip()
            return jsonify({
                'reply': "I couldn't answer that just now. Please check your student dashboard for the latest "
                         "updates" + (f" or write to {support}." if support else ".")
            })

    except Exception as exc:
        logger.error("Chatbot error: %s", exc)
        return jsonify({
            'reply': "I couldn't answer that just now. Please try again in a moment."
        })

