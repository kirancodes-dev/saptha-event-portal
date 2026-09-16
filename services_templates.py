"""
services_templates.py — Pre-Built Turnkey Event Templates for SapthaEvent Universal OS

Provides 7 ready-to-use event templates covering all major event paradigms:
1. Hackathon & Code Challenge
2. Professional Academic / Industry Conference
3. Hands-On Workshop / Training
4. Academic / Industry Seminar or Keynote
5. Sports Tournament
6. Cultural / Talent Competition
7. Online Webinar / Virtual Meetup

Each template configures:
- Event metadata defaults (type, category, mode, timezone, capacity, pricing)
- Workflow DAG stages and progression rules
- Dynamic registration form fields
- Pluggable evaluation rubrics
- Multi-tier ticketing defaults
- Event-driven notification automation triggers
- Certificate styling & issuance configurations
"""

import copy
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from services_event import EventService


TEMPLATES_CATALOG: Dict[str, Dict[str, Any]] = {
    "hackathon": {
        "id": "hackathon",
        "name": "Hackathon & Code Sprint",
        "category": "Technology",
        "event_type": "hackathon",
        "event_mode": "hybrid",
        "description": "Collaborative competitive programming, rapid prototyping, and innovation sprint with multiple judging rounds.",
        "pricing_type": "free",
        "fee": 0.0,
        "currency": "INR",
        "capacity": 300,
        "workflow_config": {
            "stages": [
                "draft",
                "published",
                "registration_open",
                "team_formation",
                "submission_open",
                "judging_round_1",
                "pitch_finals",
                "completed",
                "certified",
            ],
            "initial_stage": "draft",
            "participant_stages": [
                "applied",
                "confirmed",
                "waitlisted",
                "checked_in",
                "submitted",
                "round_1_reviewed",
                "shortlisted",
                "pitching",
                "winner",
                "runner_up",
                "completed",
                "certified",
            ],
            "rules": {
                "require_submission_for_judging": True,
                "allow_team_registration": True,
                "min_team_size": 2,
                "max_team_size": 4,
            },
        },
        "form_config": [
            {
                "field_name": "team_name",
                "label": "Team / Squad Name",
                "type": "text",
                "required": True,
                "placeholder": "e.g. ByteCraft",
            },
            {
                "field_name": "github_url",
                "label": "GitHub Profile / Repository URL",
                "type": "url",
                "required": True,
                "placeholder": "https://github.com/...",
            },
            {
                "field_name": "tech_stack",
                "label": "Primary Tech Stack",
                "type": "select",
                "required": True,
                "options": ["AI/ML & Python", "Full-Stack Web (React/Node)", "Mobile (Flutter/React Native)", "Cloud & DevOps", "Blockchain & Web3"],
            },
            {
                "field_name": "project_pitch",
                "label": "Brief Project Idea / Pitch",
                "type": "textarea",
                "required": False,
                "placeholder": "Summarize what you plan to build...",
            },
            {
                "field_name": "tshirt_size",
                "label": "T-Shirt Size",
                "type": "select",
                "required": True,
                "options": ["S", "M", "L", "XL", "XXL"],
            },
            {
                "field_name": "dietary_preference",
                "label": "Meal Preference",
                "type": "select",
                "required": True,
                "options": ["Vegetarian", "Non-Vegetarian", "Jain", "Vegan"],
            },
        ],
        "evaluation_config": {
            "type": "rubric",
            "scoring_scale": 10,
            "criteria": [
                {"key": "innovation", "name": "Innovation & Originality", "max_score": 10, "weight": 30},
                {"key": "execution", "name": "Technical Execution & Architecture", "max_score": 10, "weight": 30},
                {"key": "ui_ux", "name": "Design Polish & User Experience", "max_score": 10, "weight": 20},
                {"key": "pitch", "name": "Presentation, Clarity & Viability", "max_score": 10, "weight": 20},
            ],
            "rounds": ["Round 1: Code Review", "Round 2: Live Pitch & Demo"],
        },
        "ticket_tiers": [
            {"tier_id": "hacker_pass", "name": "Hacker Pass", "price": 0.0, "capacity": 200, "badge_type": "HACKER", "perks": "Full hackathon access, food, swag"},
            {"tier_id": "mentor_pass", "name": "Mentor / Industry Guide", "price": 0.0, "capacity": 20, "badge_type": "MENTOR", "perks": "Mentor lounge, VIP networking"},
            {"tier_id": "judge_pass", "name": "Judge / Evaluator Pass", "price": 0.0, "capacity": 10, "badge_type": "JUDGE", "perks": "Scoring portal, VIP lounge"},
            {"tier_id": "sponsor_pass", "name": "Sponsor & Recruiter", "price": 0.0, "capacity": 15, "badge_type": "SPONSOR", "perks": "Talent booth access, resume book"},
        ],
        "notification_rules": [
            {"trigger": "on_registered", "channel": "email", "template": "Welcome to {event_title}! Your registration is received."},
            {"trigger": "on_checked_in", "channel": "whatsapp", "template": "Welcome to {event_title}! You are checked in at badge desk."},
            {"trigger": "on_shortlisted", "channel": "email", "template": "Congratulations! Your team has advanced to the Pitch Finals of {event_title}!"},
        ],
        "certificate_config": {
            "template_id": "tech_modern_gold",
            "title": "Certificate of Achievement",
            "badge_icon": "trophy",
            "include_qr_verification": True,
        },
    },
    "conference": {
        "id": "conference",
        "name": "Academic & Industry Conference",
        "category": "Academic",
        "event_type": "conference",
        "event_mode": "in-person",
        "description": "Multi-track professional gathering with keynotes, technical tracks, panel discussions, and paper presentations.",
        "pricing_type": "paid",
        "fee": 1500.0,
        "currency": "INR",
        "capacity": 500,
        "workflow_config": {
            "stages": [
                "draft",
                "published",
                "registration_open",
                "registration_closed",
                "in_progress",
                "completed",
                "certified",
            ],
            "initial_stage": "draft",
            "participant_stages": [
                "applied",
                "pending_payment",
                "confirmed",
                "checked_in",
                "attended",
                "completed",
                "certified",
            ],
            "rules": {
                "require_payment_for_confirmation": True,
                "multi_track_selection": True,
            },
        },
        "form_config": [
            {
                "field_name": "full_name",
                "label": "Full Name (for Badge & Certificate)",
                "type": "text",
                "required": True,
            },
            {
                "field_name": "designation",
                "label": "Current Role / Designation",
                "type": "text",
                "required": True,
                "placeholder": "e.g. Senior Researcher / Staff Engineer",
            },
            {
                "field_name": "organization",
                "label": "Organization / University Affiliation",
                "type": "text",
                "required": True,
            },
            {
                "field_name": "track_interest",
                "label": "Primary Track of Interest",
                "type": "select",
                "required": True,
                "options": ["Track A: AI Systems & LLMs", "Track B: Distributed Cloud & Security", "Track C: Human-Computer Interaction", "Track D: Quantum Computing"],
            },
            {
                "field_name": "dietary_requirements",
                "label": "Dietary Preference",
                "type": "select",
                "required": False,
                "options": ["Standard / Non-Veg", "Vegetarian", "Vegan", "Gluten-Free"],
            },
        ],
        "evaluation_config": {
            "type": "peer_review",
            "scoring_scale": 5,
            "criteria": [
                {"key": "novelty", "name": "Novelty & Contribution", "max_score": 5, "weight": 40},
                {"key": "methodology", "name": "Methodological Rigor", "max_score": 5, "weight": 35},
                {"key": "presentation", "name": "Clarity & Visual Presentation", "max_score": 5, "weight": 25},
            ],
        },
        "ticket_tiers": [
            {"tier_id": "student_pass", "name": "Student Delegate", "price": 500.0, "capacity": 150, "badge_type": "STUDENT", "perks": "All technical sessions & digital proceedings"},
            {"tier_id": "standard_pass", "name": "Professional Delegate", "price": 1500.0, "capacity": 250, "badge_type": "DELEGATE", "perks": "All tracks, networking lunch, conference kit"},
            {"tier_id": "vip_pass", "name": "VIP All-Access", "price": 3500.0, "capacity": 50, "badge_type": "VIP", "perks": "Keynote reserved seating, VIP dinner, speaker meet-and-greet"},
            {"tier_id": "speaker_pass", "name": "Keynote / Speaker Pass", "price": 0.0, "capacity": 30, "badge_type": "SPEAKER", "perks": "Speaker lounge, VIP dinner, honorary plaque"},
        ],
        "notification_rules": [
            {"trigger": "on_registered", "channel": "email", "template": "Registration confirmed for {event_title}. Please present your QR pass upon arrival."},
            {"trigger": "session_reminder", "channel": "push", "template": "Keynote starts in 15 minutes in Main Auditorium."},
        ],
        "certificate_config": {
            "template_id": "academic_classic",
            "title": "Certificate of Participation",
            "badge_icon": "seal",
            "include_qr_verification": True,
        },
    },
    "workshop": {
        "id": "workshop",
        "name": "Hands-On Technical Workshop",
        "category": "Workshop",
        "event_type": "workshop",
        "event_mode": "hybrid",
        "description": "Interactive, instructor-led training session with live coding, lab assignments, and direct mentoring.",
        "pricing_type": "paid",
        "fee": 499.0,
        "currency": "INR",
        "capacity": 60,
        "workflow_config": {
            "stages": [
                "draft",
                "published",
                "registration_open",
                "registration_closed",
                "in_progress",
                "completed",
                "certified",
            ],
            "initial_stage": "draft",
            "participant_stages": [
                "applied",
                "pending_payment",
                "confirmed",
                "checked_in",
                "assignment_submitted",
                "completed",
                "certified",
            ],
            "rules": {
                "require_assignment_for_certificate": True,
                "strict_capacity_limit": True,
            },
        },
        "form_config": [
            {
                "field_name": "experience_level",
                "label": "Prior Experience with Subject",
                "type": "select",
                "required": True,
                "options": ["Complete Beginner", "Intermediate (1-2 years)", "Advanced Practitioner"],
            },
            {
                "field_name": "laptop_os",
                "label": "Operating System of Your Workshop Laptop",
                "type": "select",
                "required": True,
                "options": ["macOS", "Linux (Ubuntu/Fedora/Debian)", "Windows 11 with WSL2", "Other"],
            },
            {
                "field_name": "github_or_portfolio",
                "label": "GitHub or LinkedIn Profile",
                "type": "url",
                "required": False,
            },
        ],
        "evaluation_config": {
            "type": "pass_fail",
            "scoring_scale": 100,
            "criteria": [
                {"key": "lab_completion", "name": "Lab Milestone Completion", "max_score": 100, "weight": 100}
            ],
            "pass_score": 70,
        },
        "ticket_tiers": [
            {"tier_id": "general_seat", "name": "Hands-On Workshop Seat", "price": 499.0, "capacity": 60, "badge_type": "ATTENDEE", "perks": "Cloud sandbox access, lab guidebook, verified certificate"}
        ],
        "notification_rules": [
            {"trigger": "on_registered", "channel": "email", "template": "Seat reserved for {event_title}! Check the lab setup instructions before day 1."},
        ],
        "certificate_config": {
            "template_id": "skill_credential",
            "title": "Certificate of Course Completion",
            "badge_icon": "code",
            "include_qr_verification": True,
        },
    },
    "seminar": {
        "id": "seminar",
        "name": "Academic & Executive Seminar",
        "category": "Seminar",
        "event_type": "seminar",
        "event_mode": "in-person",
        "description": "In-depth lecture or symposium featuring distinguished subject-matter experts and thought leaders.",
        "pricing_type": "free",
        "fee": 0.0,
        "currency": "INR",
        "capacity": 200,
        "workflow_config": {
            "stages": [
                "draft",
                "published",
                "registration_open",
                "registration_closed",
                "in_progress",
                "completed",
                "certified",
            ],
            "initial_stage": "draft",
            "participant_stages": [
                "applied",
                "confirmed",
                "checked_in",
                "attended",
                "feedback_submitted",
                "completed",
                "certified",
            ],
            "rules": {
                "require_feedback_for_certificate": True,
            },
        },
        "form_config": [
            {
                "field_name": "college_or_company",
                "label": "Institution / Organization",
                "type": "text",
                "required": True,
            },
            {
                "field_name": "speaker_question",
                "label": "Questions for the Keynote Speaker",
                "type": "textarea",
                "required": False,
                "placeholder": "What would you like the speaker to address?",
            },
        ],
        "evaluation_config": {
            "type": "attendance_based",
            "criteria": [
                {"key": "attendance", "name": "Verified Session Attendance", "max_score": 100, "weight": 100}
            ],
        },
        "ticket_tiers": [
            {"tier_id": "seminar_entry", "name": "General Admission", "price": 0.0, "capacity": 200, "badge_type": "ATTENDEE", "perks": "Symposium entry, Q&A participation, attendance certificate"}
        ],
        "notification_rules": [
            {"trigger": "on_registered", "channel": "email", "template": "Registration confirmed for the seminar: {event_title}."},
        ],
        "certificate_config": {
            "template_id": "symposium_standard",
            "title": "Certificate of Attendance",
            "badge_icon": "book-open",
            "include_qr_verification": True,
        },
    },
    "sports": {
        "id": "sports",
        "name": "Sports Tournament & League",
        "category": "Sports",
        "event_type": "sports",
        "event_mode": "in-person",
        "description": "Multi-team competitive sports tournament with fixture brackets, live match score updates, and leaderboard point tables.",
        "pricing_type": "paid",
        "fee": 1000.0,
        "currency": "INR",
        "capacity": 32,
        "workflow_config": {
            "stages": [
                "draft",
                "published",
                "registration_open",
                "roster_verification",
                "bracket_fixtures_live",
                "knockout_rounds",
                "finals",
                "completed",
                "certified",
            ],
            "initial_stage": "draft",
            "participant_stages": [
                "applied",
                "pending_payment",
                "confirmed",
                "roster_verified",
                "checked_in",
                "round_of_16",
                "quarter_finals",
                "semi_finals",
                "finals",
                "winner",
                "runner_up",
                "completed",
                "certified",
            ],
            "rules": {
                "require_roster_verification": True,
                "bracket_type": "single_elimination",
            },
        },
        "form_config": [
            {
                "field_name": "team_name",
                "label": "Official Team Name",
                "type": "text",
                "required": True,
            },
            {
                "field_name": "captain_contact",
                "label": "Captain Phone / WhatsApp Number",
                "type": "tel",
                "required": True,
            },
            {
                "field_name": "squad_size",
                "label": "Number of Players in Squad",
                "type": "number",
                "required": True,
                "placeholder": "e.g. 11 or 7",
            },
            {
                "field_name": "player_roster_names",
                "label": "Player Roster Names & Jersey Numbers",
                "type": "textarea",
                "required": True,
                "placeholder": "1. Name (Captain)\n2. Name (Vice Captain)...",
            },
            {
                "field_name": "emergency_contact",
                "label": "Emergency Medical Contact Name & Number",
                "type": "text",
                "required": True,
            },
        ],
        "evaluation_config": {
            "type": "match_points",
            "criteria": [
                {"key": "match_score", "name": "Points / Goals Scored", "max_score": 100, "weight": 50},
                {"key": "fair_play", "name": "Fair Play & Conduct Score", "max_score": 10, "weight": 20},
                {"key": "mvp_rating", "name": "MVP Performance Metric", "max_score": 10, "weight": 30},
            ],
        },
        "ticket_tiers": [
            {"tier_id": "team_entry", "name": "Team Squad Registration", "price": 1000.0, "capacity": 32, "badge_type": "TEAM", "perks": "Full squad tournament entry, jersey badges, tournament referee fees"},
            {"tier_id": "spectator_pass", "name": "Spectator Gallery Pass", "price": 50.0, "capacity": 500, "badge_type": "SPECTATOR", "perks": "Stadium spectator access"}
        ],
        "notification_rules": [
            {"trigger": "on_registered", "channel": "whatsapp", "template": "Squad registered for {event_title}! Fixtures will be generated shortly."},
            {"trigger": "fixture_announced", "channel": "whatsapp", "template": "Match alert: Your match is scheduled on Court 1 at {match_time}."},
        ],
        "certificate_config": {
            "template_id": "sports_athletics_bold",
            "title": "Certificate of Athletic Merit",
            "badge_icon": "medal",
            "include_qr_verification": True,
        },
    },
    "cultural": {
        "id": "cultural",
        "name": "Cultural & Performing Arts Competition",
        "category": "Cultural",
        "event_type": "cultural",
        "event_mode": "in-person",
        "description": "Music, dance, dramatic arts, visual arts, and literary competitions with multi-judge performance scoring.",
        "pricing_type": "paid",
        "fee": 250.0,
        "currency": "INR",
        "capacity": 100,
        "workflow_config": {
            "stages": [
                "draft",
                "published",
                "registration_open",
                "audition_prelims",
                "stage_performance",
                "judge_deliberation",
                "completed",
                "certified",
            ],
            "initial_stage": "draft",
            "participant_stages": [
                "applied",
                "pending_payment",
                "confirmed",
                "prelim_shortlisted",
                "checked_in",
                "performance_evaluated",
                "winner",
                "runner_up",
                "completed",
                "certified",
            ],
            "rules": {
                "max_performance_duration_mins": 8,
                "multi_judge_consensus": True,
            },
        },
        "form_config": [
            {
                "field_name": "performance_title",
                "label": "Performance / Piece Title",
                "type": "text",
                "required": True,
            },
            {
                "field_name": "art_subgenre",
                "label": "Sub-Genre / Style",
                "type": "select",
                "required": True,
                "options": ["Classical Music / Vocal", "Contemporary / Hip-Hop Dance", "Classical Dance (Bharatanatyam/Kathak)", "Battle of Bands", "Stand-Up Comedy", "Short Play / Monologue"],
            },
            {
                "field_name": "audio_track_link",
                "label": "Backing Track Audio (Google Drive / SoundCloud Link)",
                "type": "url",
                "required": False,
                "placeholder": "https://...",
            },
            {
                "field_name": "tech_requirements",
                "label": "Stage / Mic / Prop Requirements",
                "type": "textarea",
                "required": False,
                "placeholder": "e.g. 2 Cordless Mics, Acoustic Guitar DI Box, Stage Fog",
            },
        ],
        "evaluation_config": {
            "type": "rubric",
            "scoring_scale": 10,
            "criteria": [
                {"key": "technique", "name": "Artistic Technique & Mastery", "max_score": 10, "weight": 30},
                {"key": "rhythm_tempo", "name": "Rhythm, Pitch & Synchronization", "max_score": 10, "weight": 25},
                {"key": "stage_presence", "name": "Stage Presence, Costume & Expression", "max_score": 10, "weight": 25},
                {"key": "originality", "name": "Originality & Audience Impact", "max_score": 10, "weight": 20},
            ],
        },
        "ticket_tiers": [
            {"tier_id": "performer_solo", "name": "Solo Performer Pass", "price": 250.0, "capacity": 50, "badge_type": "ARTIST", "perks": "Green room access, stage sound check, certificate"},
            {"tier_id": "performer_group", "name": "Group Performance Pass", "price": 750.0, "capacity": 25, "badge_type": "TROUPE", "perks": "Group green room access, full sound check"},
            {"tier_id": "audience_seat", "name": "Audience Gallery Seat", "price": 100.0, "capacity": 300, "badge_type": "AUDIENCE", "perks": "Audience seating, voting rights"}
        ],
        "notification_rules": [
            {"trigger": "on_registered", "channel": "email", "template": "Registration confirmed for {event_title}! Please upload your final backing track 24h prior."},
        ],
        "certificate_config": {
            "template_id": "cultural_ornate_purple",
            "title": "Certificate of Excellence",
            "badge_icon": "sparkles",
            "include_qr_verification": True,
        },
    },
    "webinar": {
        "id": "webinar",
        "name": "Global Online Webinar & Virtual Meetup",
        "category": "Virtual",
        "event_type": "webinar",
        "event_mode": "online",
        "description": "Worldwide virtual broadcast with interactive Q&A, chat, screen sharing, and automatic session recording access.",
        "pricing_type": "free",
        "fee": 0.0,
        "currency": "USD",
        "capacity": 1000,
        "workflow_config": {
            "stages": [
                "draft",
                "published",
                "registration_open",
                "live_broadcasting",
                "recording_processing",
                "completed",
                "certified",
            ],
            "initial_stage": "draft",
            "participant_stages": [
                "applied",
                "confirmed",
                "link_delivered",
                "joined_live",
                "completed",
                "certified",
            ],
            "rules": {
                "auto_generate_join_link": True,
                "allow_on_demand_recording": True,
            },
        },
        "form_config": [
            {
                "field_name": "job_title",
                "label": "Job Title / Role",
                "type": "text",
                "required": False,
            },
            {
                "field_name": "country",
                "label": "Country / Region",
                "type": "text",
                "required": True,
                "placeholder": "e.g. India, United States, Germany",
            },
        ],
        "evaluation_config": {
            "type": "digital_attendance",
            "criteria": [
                {"key": "watch_duration", "name": "Live Streaming Minutes Attended", "max_score": 60, "weight": 100}
            ],
        },
        "ticket_tiers": [
            {"tier_id": "virtual_free_pass", "name": "Virtual Free Pass", "price": 0.0, "capacity": 1000, "badge_type": "VIRTUAL", "perks": "Live stream access, live Q&A, on-demand video access"}
        ],
        "notification_rules": [
            {"trigger": "on_registered", "channel": "email", "template": "You are registered! Your private join link is included in this email."},
            {"trigger": "1_hour_before", "channel": "email", "template": "Starting in 1 hour: {event_title}! Join link: {stream_url}"},
        ],
        "certificate_config": {
            "template_id": "virtual_modern_blue",
            "title": "Certificate of Attendance",
            "badge_icon": "globe",
            "include_qr_verification": True,
        },
    },
}


class TemplateService:
    """
    Catalog and instantiation engine for pre-built universal event templates.
    """

    @staticmethod
    def list_templates() -> List[Dict[str, Any]]:
        """Return metadata summary for all available pre-built templates."""
        summaries = []
        for t_id, t in TEMPLATES_CATALOG.items():
            summaries.append({
                "id": t["id"],
                "name": t["name"],
                "category": t["category"],
                "event_type": t["event_type"],
                "event_mode": t["event_mode"],
                "description": t["description"],
                "pricing_type": t["pricing_type"],
                "fee": t["fee"],
                "currency": t["currency"],
                "capacity": t["capacity"],
                "form_field_count": len(t.get("form_config", [])),
                "ticket_tier_count": len(t.get("ticket_tiers", [])),
                "evaluation_type": t.get("evaluation_config", {}).get("type", "general"),
            })
        return summaries

    @staticmethod
    def get_template(template_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full template specification by ID."""
        cleaned_id = template_id.strip().lower()
        template = TEMPLATES_CATALOG.get(cleaned_id)
        if not template:
            return None
        return copy.deepcopy(template)

    @staticmethod
    def instantiate_event(
        db,
        *,
        template_id: str,
        title: str,
        date_str: str,
        deadline_str: str = "",
        venue: str = "",
        organization_id: Optional[str] = None,
        created_by: str = "",
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a live Event record and corresponding Form Schema based on a template.
        Supports granular parameter overrides.
        """
        template = TemplateService.get_template(template_id)
        if not template:
            raise ValueError(f"Unknown event template: '{template_id}'. Available: {list(TEMPLATES_CATALOG.keys())}")

        overrides = overrides or {}

        # Merge defaults with overrides
        merged_title = title or overrides.get("title") or template["name"]
        merged_desc = overrides.get("description", template["description"])
        merged_category = overrides.get("category", template["category"])
        merged_event_type = overrides.get("event_type", template["event_type"])
        merged_event_mode = overrides.get("event_mode", template["event_mode"])
        merged_venue = venue or overrides.get("venue") or ("Online / Virtual" if merged_event_mode == "online" else "Main Campus / Arena")
        merged_capacity = overrides.get("capacity", template["capacity"])
        merged_pricing_type = overrides.get("pricing_type", template["pricing_type"])
        merged_fee = overrides.get("fee", template["fee"])
        merged_currency = overrides.get("currency", template["currency"])
        merged_workflow = overrides.get("workflow_config", template["workflow_config"])
        merged_eval = overrides.get("evaluation_config", template["evaluation_config"])
        merged_tickets = overrides.get("ticket_tiers", template["ticket_tiers"])
        merged_notifications = overrides.get("notification_rules", template.get("notification_rules", []))
        merged_form_fields = overrides.get("form_config", template["form_config"])

        # Create event via EventService
        event = EventService.create_event(
            db,
            title=merged_title,
            description=merged_desc,
            category=merged_category,
            event_type=merged_event_type,
            event_mode=merged_event_mode,
            venue=merged_venue,
            date_str=date_str,
            deadline_str=deadline_str,
            organization_id=organization_id,
            capacity=merged_capacity,
            pricing_type=merged_pricing_type,
            fee=merged_fee,
            currency=merged_currency,
            created_by=created_by,
            workflow_config=merged_workflow,
            evaluation_config=merged_eval,
            ticket_tiers=merged_tickets,
            custom_fields=merged_form_fields,
        )

        # Attach template metadata
        event["template_id"] = template_id
        event["notification_rules"] = merged_notifications
        event["certificate_config"] = template.get("certificate_config", {})
        db.collection("events").document(event["id"]).set(event, merge=True)

        return event
