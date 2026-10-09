#!/usr/bin/env python3
"""
seed_upcoming_10days_events.py
==============================
Seeds 10 realistic, fully-configured events for Sapthagiri NPS University
spanning the next 10 days (from tomorrow Oct 9, 2026 to Oct 18, 2026).

Each event is verified to be:
- status: 'active'
- approval_status: 'approved'
- visibility: 'Public'
- deadline / reg_deadline: comfortably in the future (open registration!)
- capacity > registration_count (no waitlist, direct registration!)
- Complete event_forms schema attached
- Working Register buttons on homepage, event detail, and calendar!
"""

# BLK-10: seed safety guard
from seed_safety import guard
guard()

import datetime

from app import app
import models

def seed():
    print("=" * 70)
    print("  Seeding 10 Upcoming Active Events for the Next 10 Days")
    print("=" * 70)

    base_date = datetime.date(2026, 10, 8)  # Today
    deadline_date = str(base_date + datetime.timedelta(days=17))  # 2026-10-25

    EVENTS = [
        {
            "id": "codestorm-2026-rapid-algo",
            "title": "CodeStorm 2026: Rapid Algorithmic Challenge",
            "category": "Technical",
            "event_type": "competition",
            "event_mode": "offline",
            "day_offset": 1,
            "time_str": "10:00 AM — 01:00 PM IST",
            "venue": "Turing Advanced Computing Lab (Lab 3), CSE Block",
            "description": (
                "An intense, high-speed competitive programming tournament. Participants tackle "
                "algorithmic puzzles, dynamic programming challenges, and graph theory problems "
                "under tight time constraints. Bring your laptop and your sharpest logic!"
            ),
            "fee": 0.0,
            "pricing_type": "free",
            "is_team": False,
            "team_min": 1,
            "team_max": 1,
            "capacity": 120,
            "registration_count": 28,
            "banner_url": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?auto=format&fit=crop&w=1200&q=80",
            "department": "Computer Science & Engineering",
            "rules": (
                "1. Individual participation only.\n"
                "2. Permitted languages: C++, Python, Java, Rust.\n"
                "3. Plagiarism detection tools will be strictly enforced.\n"
                "4. Top 3 coders win cash prizes and technical certificates."
            ),
            "custom_fields": [
                {"id": "preferred_language", "type": "select", "label": "Primary Programming Language", "options": ["Python", "C++", "Java", "Other"], "required": True},
                {"id": "codechef_or_cf_handle", "type": "text", "label": "Codeforces / LeetCode Handle", "placeholder": "Optional handle", "required": False},
            ]
        },
        {
            "id": "sapthahack-2026-ai-sprint",
            "title": "SapthaHack 2026: 36-Hr Universal AI Hackathon",
            "category": "Technical",
            "event_type": "hackathon",
            "event_mode": "hybrid",
            "day_offset": 2,
            "time_str": "09:00 AM (36 Hours Continuous)",
            "venue": "Dr. A.P.J. Abdul Kalam Convention Center, SNPSU Campus",
            "description": (
                "The university's flagship national hackathon. Build functional, production-ready AI solutions "
                "across Healthcare, FinTech, and Smart Campus infrastructure. Mentorship from industry veterans, "
                "high-speed cloud credits, midnight pizzas, and an INR 1,00,000 prize pool!"
            ),
            "fee": 0.0,
            "pricing_type": "free",
            "is_team": True,
            "team_min": 2,
            "team_max": 4,
            "capacity": 300,
            "registration_count": 84,
            "banner_url": "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1200&q=80",
            "department": "Information Science & Engineering",
            "rules": (
                "1. Teams must consist of 2 to 4 members.\n"
                "2. All projects must be started from scratch during the hackathon.\n"
                "3. Working GitHub repository and live presentation required for judging.\n"
                "4. Mentors available 24/7 in Discord and offline lounge."
            ),
            "custom_fields": [
                {"id": "hackathon_track", "type": "select", "label": "Chosen Hackathon Track", "options": ["GenAI & LLMs", "Smart Campus IoT", "Healthcare Diagnostics", "FinTech & Web3"], "required": True},
                {"id": "github_org_url", "type": "text", "label": "Team GitHub / Portfolio URL", "placeholder": "https://github.com/...", "required": False},
            ]
        },
        {
            "id": "esports-championship-2026",
            "title": "Saptha Esports Arena: Valorant & BGMI Showdown",
            "category": "Sports",
            "event_type": "competition",
            "event_mode": "offline",
            "day_offset": 3,
            "time_str": "11:00 AM — 06:00 PM IST",
            "venue": "Indoor Sports Complex & Student Lounge, 2nd Floor",
            "description": (
                "The ultimate collegiate gaming tournament. Squad up with your classmates and battle for "
                "the varsity gaming cup in Valorant (PC 5v5) and BGMI (Mobile Squads). Cast live on giant LED "
                "screens with campus shoutcasters!"
            ),
            "fee": 100.0,
            "pricing_type": "paid",
            "is_team": True,
            "team_min": 4,
            "team_max": 5,
            "capacity": 160,
            "registration_count": 32,
            "banner_url": "https://images.unsplash.com/photo-1542751371-adc38448a05e?auto=format&fit=crop&w=1200&q=80",
            "department": "Student Welfare Board",
            "rules": (
                "1. Players must bring their own gaming peripherals or mobile devices.\n"
                "2. Standard tournament competitive map pools and ban rules apply.\n"
                "3. Toxic behavior or emulator usage in mobile titles results in immediate DQ."
            ),
            "custom_fields": [
                {"id": "game_title", "type": "select", "label": "Tournament Title", "options": ["Valorant (5v5 PC)", "BGMI (4-Man Squad)"], "required": True},
                {"id": "in_game_lead_id", "type": "text", "label": "Captain In-Game Tag / Riot ID", "placeholder": "e.g. Phoenix#IND", "required": True},
            ]
        },
        {
            "id": "genai-llm-masterclass",
            "title": "Hands-on Workshop: Building Agentic AI with Gemini & Python",
            "category": "Technical",
            "event_type": "workshop",
            "event_mode": "offline",
            "day_offset": 4,
            "time_str": "02:00 PM — 05:30 PM IST",
            "venue": "Aryabhata Seminar Hall, Mechanical & CSE Block",
            "description": (
                "A practical, code-along workshop on developing multi-agent autonomous AI systems, RAG pipelines, "
                "and tool-calling workflows using Python and Gemini 2.5. Every attendee walks away with a deployed "
                "AI application on Google Cloud."
            ),
            "fee": 0.0,
            "pricing_type": "free",
            "is_team": False,
            "team_min": 1,
            "team_max": 1,
            "capacity": 150,
            "registration_count": 95,
            "banner_url": "https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&w=1200&q=80",
            "department": "Computer Science & Engineering",
            "rules": (
                "1. Open to 2nd, 3rd, and 4th year students across all branches.\n"
                "2. Laptop with Python 3.10+ pre-installed required.\n"
                "3. Free API keys and compute vouchers will be provided to participants."
            ),
            "custom_fields": [
                {"id": "python_proficiency", "type": "select", "label": "Python Experience Level", "options": ["Beginner", "Intermediate", "Advanced"], "required": True},
            ]
        },
        {
            "id": "robowars-drone-grand-prix",
            "title": "RoboWars & Drone Obstacle Grand Prix 2026",
            "category": "Technical",
            "event_type": "competition",
            "event_mode": "offline",
            "day_offset": 5,
            "time_str": "10:30 AM — 04:30 PM IST",
            "venue": "Robotics Enclosure & Mechanical Quadrangle",
            "description": (
                "Steel, sparks, and speed! Witness custom-engineered combat robots battle inside a reinforced bulletproof "
                "arena, followed by high-speed FPV drone racing through intricate campus obstacle courses."
            ),
            "fee": 150.0,
            "pricing_type": "paid",
            "is_team": True,
            "team_min": 2,
            "team_max": 4,
            "capacity": 80,
            "registration_count": 18,
            "banner_url": "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1200&q=80",
            "department": "Mechanical & Mechatronics Engineering",
            "rules": (
                "1. Robots must pass safety inspection and fail-safe switch checks.\n"
                "2. 15kg and 30kg combat categories with strict pneumatic limits.\n"
                "3. Drone racers must operate on designated 5.8 GHz video frequencies."
            ),
            "custom_fields": [
                {"id": "robot_weight_class", "type": "select", "label": "Combat Category / Drone Class", "options": ["15kg Featherweight", "30kg Middleweight", "FPV Drone Racing"], "required": True},
                {"id": "bot_name", "type": "text", "label": "Robot / Drone Team Name", "placeholder": "e.g. IronClad", "required": True},
            ]
        },
        {
            "id": "dhvani-2026-battle-of-bands",
            "title": "Dhvani 2026: Inter-Department Battle of the Bands",
            "category": "Cultural",
            "event_type": "cultural",
            "event_mode": "offline",
            "day_offset": 6,
            "time_str": "05:00 PM — 09:30 PM IST",
            "venue": "Open-Air Amphitheatre, Central Quadrangle",
            "description": (
                "The most electrifying musical night of the semester! College bands and acoustic ensembles face off "
                "performing original tracks and high-energy covers across Rock, Fusion, Indie, and Carnatic Progressive."
            ),
            "fee": 0.0,
            "pricing_type": "free",
            "is_team": True,
            "team_min": 3,
            "team_max": 8,
            "capacity": 500,
            "registration_count": 42,
            "banner_url": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=1200&q=80",
            "department": "Cultural Committee & Student Council",
            "rules": (
                "1. Performance slot: 15 minutes setup + playing time.\n"
                "2. Drum kit and sound amplification provided by the university.\n"
                "3. Bands must bring their own guitars, keys, and specialized gear."
            ),
            "custom_fields": [
                {"id": "band_genre", "type": "text", "label": "Musical Genre / Style", "placeholder": "e.g. Indie Rock / Fusion", "required": True},
                {"id": "equipment_needs", "type": "text", "label": "Special Sound Requirements", "placeholder": "e.g. 2 vocal mics, 2 guitar lines", "required": False},
            ]
        },
        {
            "id": "saptha-premier-league-t20",
            "title": "Saptha Premier League: Inter-Collegiate T20 & Football",
            "category": "Sports",
            "event_type": "sports",
            "event_mode": "offline",
            "day_offset": 7,
            "time_str": "08:30 AM — 05:00 PM IST",
            "venue": "University Main Athletic & Cricket Grounds",
            "description": (
                "Annual inter-departmental athletic showdown. Compete in high-stakes 10-over floodlit cricket matches "
                "and 7-a-side football knockouts. Professional referees, live commentary, and championship trophies!"
            ),
            "fee": 0.0,
            "pricing_type": "free",
            "is_team": True,
            "team_min": 7,
            "team_max": 15,
            "capacity": 250,
            "registration_count": 60,
            "banner_url": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?auto=format&fit=crop&w=1200&q=80",
            "department": "Department of Physical Education & Sports",
            "rules": (
                "1. Players must wear official departmental sports kits and safety gear.\n"
                "2. Standard ICC and FIFA tournament rules apply with tournament modifications.\n"
                "3. Valid university ID card mandatory at registration desk."
            ),
            "custom_fields": [
                {"id": "sport_selection", "type": "select", "label": "Tournament Sport", "options": ["T20 Cricket", "7-a-side Football"], "required": True},
            ]
        },
        {
            "id": "nritya-dance-fest-2026",
            "title": "Nritya 2026: Classical & Contemporary Dance Fest",
            "category": "Cultural",
            "event_type": "cultural",
            "event_mode": "offline",
            "day_offset": 8,
            "time_str": "03:00 PM — 07:00 PM IST",
            "venue": "Main University Auditorium, Administrative Block",
            "description": (
                "A celebration of rhythm, grace, and storytelling. Showcasing solo and group choreography in "
                "Bharatanatyam, Kathak, Western Hip-Hop, Contemporary, and Bollywood Fusion."
            ),
            "fee": 0.0,
            "pricing_type": "free",
            "is_team": False,
            "team_min": 1,
            "team_max": 6,
            "capacity": 400,
            "registration_count": 55,
            "banner_url": "https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?auto=format&fit=crop&w=1200&q=80",
            "department": "Fine Arts & Cultural Affairs",
            "rules": (
                "1. Solo performances: 4 minutes max. Group routines: 8 minutes max.\n"
                "2. High-quality soundtrack MP3 must be submitted to the audio desk 2 hours prior.\n"
                "3. Judged on synchronization, expression, rhythm, and costume."
            ),
            "custom_fields": [
                {"id": "dance_style", "type": "select", "label": "Dance Form", "options": ["Classical Solo", "Western / Hip-Hop", "Folk / Group Fusion", "Contemporary"], "required": True},
            ]
        },
        {
            "id": "venturevibe-startup-pitch",
            "title": "VentureVibe: Student Startup Pitch & Angel Summit",
            "category": "Management",
            "event_type": "competition",
            "event_mode": "offline",
            "day_offset": 9,
            "time_str": "10:00 AM — 03:00 PM IST",
            "venue": "MBA Executive Boardroom & Seminar Hall",
            "description": (
                "Have a groundbreaking startup idea? Pitch directly to venture capitalists, angel investors, and "
                "startup incubation directors. Top pitches receive seed incubation grants, mentorship, and co-working credits."
            ),
            "fee": 0.0,
            "pricing_type": "free",
            "is_team": True,
            "team_min": 1,
            "team_max": 4,
            "capacity": 100,
            "registration_count": 22,
            "banner_url": "https://images.unsplash.com/photo-1475721027785-f74eccf877e2?auto=format&fit=crop&w=1200&q=80",
            "department": "Department of Management Studies (MBA) & E-Cell",
            "rules": (
                "1. Pitch duration: 7 minutes pitch + 3 minutes Q&A with jury.\n"
                "2. Pitch decks must be in PDF format submitted 24 hours prior.\n"
                "3. Evaluation rubrics: Problem validation, Market size, Unit economics, Defensibility."
            ),
            "custom_fields": [
                {"id": "startup_name", "type": "text", "label": "Venture / Project Name", "placeholder": "e.g. EcoPack Innovations", "required": True},
                {"id": "industry_sector", "type": "select", "label": "Industry Domain", "options": ["EdTech", "FinTech", "CleanTech / Sustainability", "HealthTech", "SaaS / B2B"], "required": True},
            ]
        },
        {
            "id": "saptha-gala-night-2026",
            "title": "Saptha Annual Gala & DJ Star Night 2026",
            "category": "Cultural",
            "event_type": "cultural",
            "event_mode": "offline",
            "day_offset": 10,
            "time_str": "06:00 PM — 10:30 PM IST",
            "venue": "University Main Grounds & Festival Stage",
            "description": (
                "The grand university finale festival! Featuring celebrity DJ sets, visual laser shows, food trucks, "
                "annual student awards ceremony, and an unforgettable evening with your campus community."
            ),
            "fee": 0.0,
            "pricing_type": "free",
            "is_team": False,
            "team_min": 1,
            "team_max": 1,
            "capacity": 1000,
            "registration_count": 210,
            "banner_url": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?auto=format&fit=crop&w=1200&q=80",
            "department": "University Student Council",
            "rules": (
                "1. Entry strictly permitted with valid SapthaEvent QR ticket pass.\n"
                "2. Physical SNPSU Student ID card required at all entry gates.\n"
                "3. Gates close strictly at 07:30 PM."
            ),
            "custom_fields": [
                {"id": "dietary_preference", "type": "select", "label": "Food Truck Coupon Preference", "options": ["Vegetarian", "Non-Vegetarian"], "required": False},
            ]
        }
    ]

    with app.app_context():
        db = models.db

        for ev in EVENTS:
            ev_date = base_date + datetime.timedelta(days=ev["day_offset"])
            date_iso = ev_date.strftime("%Y-%m-%d")

            event_payload = {
                "id": ev["id"],
                "event_id": ev["id"],
                "title": ev["title"],
                "event_name": ev["title"],
                "description": ev["description"],
                "category": ev["category"],
                "event_type": ev["event_type"],
                "event_mode": ev["event_mode"],
                "venue": ev["venue"],
                "location": "Bengaluru, Karnataka",
                "date": date_iso,
                "date_iso": date_iso,
                "deadline": deadline_date,
                "reg_deadline": deadline_date,
                "registration_deadline": deadline_date,
                "time": ev["time_str"],
                "capacity": ev["capacity"],
                "registration_count": ev["registration_count"],
                "fee": ev["fee"],
                "entry_fee": ev["fee"],
                "pricing_type": ev["pricing_type"],
                "currency": "INR",
                "is_team": ev["is_team"],
                "is_team_event": ev["is_team"],
                "min_team_size": ev["team_min"],
                "max_team_size": ev["team_max"],
                "status": "active",
                "approval_status": "approved",
                "visibility": "Public",
                "banner_url": ev["banner_url"],
                "poster_url": ev["banner_url"],
                "department": ev["department"],
                "rules": ev["rules"],
                "spoc_id": "admin@snpsu.edu.in",
                "created_by": "Sapthagiri NPS University",
                "created_by_email": "admin@snpsu.edu.in",
                "created_at": base_date.strftime("%Y-%m-%dT10:00:00Z"),
                "updated_at": base_date.strftime("%Y-%m-%dT10:00:00Z"),
            }

            # Upsert event into 'events' collection
            db.collection("events").document(ev["id"]).set(event_payload)

            # Create tailored form schema in 'event_forms'
            standard_fields = [
                {"id": "full_name", "type": "text", "label": "Full Name", "placeholder": "Enter your full name", "required": True, "options": [], "help_text": ""},
                {"id": "email", "type": "email", "label": "Email Address", "placeholder": "you@snpsu.edu.in", "required": True, "options": [], "help_text": ""},
                {"id": "phone", "type": "tel", "label": "Mobile Number", "placeholder": "10-digit mobile number", "required": True, "options": [], "help_text": ""},
                {"id": "usn", "type": "text", "label": "USN / Roll Number", "placeholder": "e.g. 1SN22CS045", "required": True, "options": [], "help_text": ""},
                {"id": "department", "type": "select", "label": "Department", "options": ["Computer Science & Engg", "Information Science", "Electronics & Comm", "Mechanical Engg", "MBA", "Basic Sciences", "Other"], "required": True, "help_text": ""},
                {"id": "year", "type": "select", "label": "Year of Study", "options": ["1st Year", "2nd Year", "3rd Year", "4th Year", "Postgraduate"], "required": True, "help_text": ""},
            ]

            custom = ev.get("custom_fields", [])
            for c in custom:
                c.setdefault("options", [])
                c.setdefault("help_text", "")
                c.setdefault("placeholder", "")

            form_payload = {
                "event_id": ev["id"],
                "form_title": f"{ev['title']} — Registration Form",
                "form_desc": f"Official registration for {ev['title']} hosted at {ev['venue']}.",
                "fields": standard_fields + custom,
                "updated_at": base_date.strftime("%Y-%m-%dT10:00:00Z"),
            }
            db.collection("event_forms").document(ev["id"]).set(form_payload)

            print(f"  ✔ [Day {ev['day_offset']:>2} | {date_iso}] {ev['title'][:42]:<42} ({ev['category']:<10} | {ev['pricing_type'].upper()})")

    print("\nAll 10 events successfully seeded into active database!")

if __name__ == "__main__":
    seed()
