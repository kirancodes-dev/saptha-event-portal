import datetime
import logging
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

        FAQ_CONTEXT = """
CAMPUS LOGISTICS & FAQ:
1. Q: Where is Zone A / Main Auditorium?
   A: Main Auditorium (Zone A) is located in the Administration Block on the Ground Floor.
2. Q: Where is Zone B / Seminar Hall?
   A: Seminar Hall (Zone B) is in the Library Block, 1st Floor.
3. Q: Where is Zone C / CS Labs?
   A: CS Labs (Zone C) is in the Computer Science Block, 3rd Floor.
4. Q: Where is Zone D / Sports Stadium?
   A: Sports Stadium (Zone D) is located in the Sports Arena, East Campus.
5. Q: Is parking available on campus?
   A: Yes, student and visitor parking is available at the North Gate Parking lot. Inner campus parking is prohibited.
6. Q: Where can we get food/refreshments?
   A: The main Student Food Court is situated near the Basketball court. Snack kiosks are also open near the CS Block.
7. Q: Who to contact for help/emergencies?
   A: Visit the main registration desk at the main arch entrance, or email help@sapthagiri.edu.
8. Q: What is required for check-in?
   A: Carry your college student ID card and your digital ticket QR code.
9. Q: How to download certificates?
   A: If you were marked 'Present' at the event, go to your dashboard, scroll to 'Completed Events', and click 'Download Certificate'.
"""

        system_prompt = (
            "You are 'Sparky', the official AI assistant for the Sapthagiri NPS University "
            "Event Portal. Help students with event questions. Be concise (2–3 sentences), "
            "enthusiastic, and accurate. Use occasional emojis.\n\n"
            f"LIVE DATABASE CONTEXT:\n{context}\n\n"
            f"CAMPUS LOGISTICS & FAQ:\n{FAQ_CONTEXT}\n\n"
            f"PERSONALIZED STUDENT CONTEXT:\n{user_context}\n\n"
            "If the student asks about their own registration status, ticket details, room assignments, "
            "assigned judges, or attendance status, refer directly to the PERSONALIZED STUDENT CONTEXT.\n"
            "If the student asks about campus directions, food, parking, help desks, or certificates, "
            "refer to the CAMPUS LOGISTICS & FAQ.\n"
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
            return jsonify({
                'reply': f"Hello! Sparky (Zoho Zia AI) here! 🤖\n\nRegarding '{user_message}': Please check your student dashboard for live updates or contact support@snpsu.edu.in."
            })

    except Exception as exc:
        logger.error("Chatbot error: %s", exc)
        return jsonify({
            'reply': "Oops! My Zoho Zia AI brain is rebooting. Please try again in a moment! 🤖⚡"
        })

