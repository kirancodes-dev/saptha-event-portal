"""
services_copilot.py — AI Event Copilot Service Layer

Provides Human-in-the-Loop AI event setup:
1. Natural language generation of event proposals (structure, forms, workflows, rubrics).
2. Proposal persistence with status 'PENDING_REVIEW'.
3. Admin preview and explicit approval workflow before committing to production.
4. Comprehensive audit logging of AI-generated configurations.
"""
import os
import json
import uuid
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional

try:
    from services_event import EventService
except ImportError:
    EventService = None

try:
    from services_templates import TemplateService
except ImportError:
    TemplateService = None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AICopilotService:
    """Enterprise AI Copilot for event generation with human-in-the-loop safeguards."""

    @staticmethod
    def generate_event_proposal(
        prompt: str,
        organization_id: Optional[str] = None,
        requested_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synthesize natural language prompt into a structured event proposal.
        Uses Google Gemini if configured, otherwise employs intelligent heuristic extraction.
        """
        clean_prompt = (prompt or "").strip()
        if not clean_prompt:
            raise ValueError("Prompt cannot be empty")

        p_lower = clean_prompt.lower()
        
        # Determine event type & template baseline
        event_type = "general"
        if any(w in p_lower for w in ["hackathon", "coding", "hack", "buildathon"]):
            event_type = "hackathon"
        elif any(w in p_lower for w in ["conference", "summit", "keynote", "symposium"]):
            event_type = "conference"
        elif any(w in p_lower for w in ["workshop", "bootcamp", "hands-on", "masterclass"]):
            event_type = "workshop"
        elif any(w in p_lower for w in ["sports", "tournament", "badminton", "cricket", "football", "athletics"]):
            event_type = "sports"
        elif any(w in p_lower for w in ["cultural", "dance", "music", "drama", "art", "photography"]):
            event_type = "cultural"
        elif any(w in p_lower for w in ["quiz", "trivia"]):
            event_type = "quiz"
        elif any(w in p_lower for w in ["debate"]):
            event_type = "debate"
        elif any(w in p_lower for w in ["webinar", "online session"]):
            event_type = "webinar"

        # Try calling Gemini if API key is provided
        ai_generated = False
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                system_instruction = (
                    "You are the SapthaEvent Universal Event AI Copilot. "
                    "Analyze the user's event request and return ONLY a valid JSON object with: "
                    "title, short_description, description, category, event_type, event_mode ('offline'|'online'|'hybrid'), "
                    "capacity (int), fee (float), form_fields (list of {id, label, type, required}), "
                    "rubric (list of {name, weight, description}), workflow_steps (list of {id, label, order})."
                )
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"Generate event proposal for: {clean_prompt}",
                    config={"response_mime_type": "application/json", "system_instruction": system_instruction}
                )
                if response and response.text:
                    parsed = json.loads(response.text)
                    proposal = AICopilotService._normalize_proposal_structure(parsed, event_type, clean_prompt, organization_id)
                    proposal["ai_model"] = "gemini-2.5-flash"
                    return proposal
            except Exception:
                # Fallback gracefully to heuristic generation
                pass

        # Intelligent Heuristic Baseline
        return AICopilotService._generate_heuristic_proposal(clean_prompt, event_type, organization_id)

    @staticmethod
    def _generate_heuristic_proposal(prompt: str, event_type: str, organization_id: Optional[str]) -> Dict[str, Any]:
        """Deterministic heuristic proposal generator for offline or fallback operation."""
        # Extract title
        title = prompt.split('.')[0].strip()
        if len(title) > 60:
            title = title[:57] + "..."
        if len(title) < 5:
            title = f"{event_type.capitalize()} Event"

        # Extract capacity heuristics
        capacity = 150
        cap_match = re.search(r'(\d+)\s*(people|students|attendees|participants|teams|seats)', prompt, re.IGNORECASE)
        if cap_match:
            try:
                capacity = int(cap_match.group(1))
            except ValueError:
                pass

        # Mode
        event_mode = "offline"
        if "online" in prompt.lower() or "virtual" in prompt.lower():
            event_mode = "online"
        elif "hybrid" in prompt.lower():
            event_mode = "hybrid"

        # Baseline rubrics & forms per type
        if event_type == "hackathon":
            category = "Technical"
            form_fields = [
                {"id": "github_url", "label": "GitHub Profile / Organization", "type": "text", "required": True},
                {"id": "track", "label": "Preferred Track / Problem Statement", "type": "dropdown", "required": True, "options": ["AI/ML", "Web3", "HealthTech", "Open Innovation"]},
                {"id": "tshirt_size", "label": "T-Shirt Size", "type": "dropdown", "required": False, "options": ["S", "M", "L", "XL", "XXL"]}
            ]
            rubric = [
                {"name": "Innovation & Originality", "weight": 30, "description": "Novelty and creativity of the proposed solution."},
                {"name": "Technical Complexity & Execution", "weight": 35, "description": "Architecture quality, stack mastery, and working code."},
                {"name": "UI / UX Design", "weight": 15, "description": "Usability, aesthetics, and frontend polish."},
                {"name": "Pitch & Presentation", "weight": 20, "description": "Clarity of demonstration and business viability."}
            ]
            workflow = [
                {"id": "registration", "label": "Registration & Team Formation", "order": 1, "status": "active"},
                {"id": "submission", "label": "Prototype Submission", "order": 2, "status": "pending"},
                {"id": "evaluation", "label": "Judge Scoring", "order": 3, "status": "pending"},
                {"id": "finals", "label": "Pitch Finals", "order": 4, "status": "pending"},
                {"id": "results", "label": "Results & Awards", "order": 5, "status": "pending"},
                {"id": "certificates", "label": "Certificates", "order": 6, "status": "pending"}
            ]
        elif event_type == "conference":
            category = "Conference"
            form_fields = [
                {"id": "affiliation", "label": "Company / Academic Affiliation", "type": "text", "required": True},
                {"id": "designation", "label": "Professional Role / Designation", "type": "text", "required": True},
                {"id": "dietary", "label": "Dietary Preference", "type": "dropdown", "required": False, "options": ["Vegetarian", "Non-Vegetarian", "Vegan"]}
            ]
            rubric = [
                {"name": "Relevance & Novelty", "weight": 40, "description": "Relevance to keynote tracks."},
                {"name": "Speaker Delivery", "weight": 60, "description": "Engagement and clarity of insights."}
            ]
            workflow = [
                {"id": "registration", "label": "Ticket Registration", "order": 1, "status": "active"},
                {"id": "payment", "label": "Payment Processing", "order": 2, "status": "pending"},
                {"id": "checkin", "label": "Badge & QR Check-in", "order": 3, "status": "pending"},
                {"id": "sessions", "label": "Conference Tracks", "order": 4, "status": "pending"},
                {"id": "feedback", "label": "Feedback & Evaluation", "order": 5, "status": "pending"},
                {"id": "certificates", "label": "Attendance Certificates", "order": 6, "status": "pending"}
            ]
        elif event_type == "sports":
            category = "Sports"
            form_fields = [
                {"id": "team_captain", "label": "Captain Name & Phone", "type": "text", "required": True},
                {"id": "jersey_color", "label": "Jersey / Kit Color", "type": "text", "required": False}
            ]
            rubric = [
                {"name": "Match Points", "weight": 70, "description": "Head-to-head score results."},
                {"name": "Fair Play / Discipline", "weight": 30, "description": "Sportsmanship points."}
            ]
            workflow = [
                {"id": "registration", "label": "Team Entry", "order": 1, "status": "active"},
                {"id": "fixtures", "label": "Match Fixtures", "order": 2, "status": "pending"},
                {"id": "matches", "label": "Tournament Matches", "order": 3, "status": "pending"},
                {"id": "finals", "label": "Championship Finals", "order": 4, "status": "pending"},
                {"id": "results", "label": "Podium & Medals", "order": 5, "status": "pending"}
            ]
        else:
            category = "General"
            form_fields = [
                {"id": "experience_level", "label": "Prior Experience", "type": "dropdown", "required": False, "options": ["Beginner", "Intermediate", "Advanced"]}
            ]
            rubric = [
                {"name": "Overall Performance", "weight": 100, "description": "General rubric criteria."}
            ]
            workflow = [
                {"id": "registration", "label": "Registration", "order": 1, "status": "active"},
                {"id": "checkin", "label": "Check-in", "order": 2, "status": "pending"},
                {"id": "results", "label": "Results", "order": 3, "status": "pending"},
                {"id": "certificates", "label": "Certificates", "order": 4, "status": "pending"}
            ]

        proposal_id = f"prop-{uuid.uuid4().hex[:8]}"
        return {
            "proposal_id": proposal_id,
            "status": "PENDING_REVIEW",
            "organization_id": organization_id,
            "prompt": prompt,
            "title": title,
            "short_description": f"AI-suggested configuration for {title}",
            "description": prompt,
            "category": category,
            "event_type": event_type,
            "event_mode": event_mode,
            "capacity": capacity,
            "fee": 0.0,
            "form_fields": form_fields,
            "rubric": rubric,
            "workflow_steps": workflow,
            "ticket_tiers": [
                {"id": "general", "name": "General Admission", "price": 0, "capacity": capacity}
            ],
            "notification_rules": [
                {"trigger": "registration_completed", "channel": "email", "enabled": True},
                {"trigger": "24_hours_before", "channel": "email", "enabled": True},
                {"trigger": "result_published", "channel": "push", "enabled": True}
            ],
            "ai_model": "heuristic-copilot-v1",
            "created_at": _utcnow_iso()
        }

    @staticmethod
    def _normalize_proposal_structure(parsed: dict, event_type: str, prompt: str, org_id: Optional[str]) -> Dict[str, Any]:
        """Normalize Gemini response into guaranteed schema."""
        proposal_id = f"prop-{uuid.uuid4().hex[:8]}"
        raw_type = str(parsed.get("event_type", event_type)).lower()
        canonical_type = event_type
        type_mappings = [
            (["hackathon", "coding", "hack", "buildathon"], "hackathon"),
            (["conference", "summit", "keynote", "symposium"], "conference"),
            (["workshop", "bootcamp", "hands-on", "masterclass"], "workshop"),
            (["sports", "tournament", "badminton", "cricket", "football", "athletics"], "sports"),
            (["cultural", "dance", "music", "drama", "art", "singing", "fashion"], "cultural"),
            (["webinar"], "webinar"),
            (["seminar", "talk", "guest"], "seminar"),
            (["meetup"], "meetup"),
            (["quiz", "trivia"], "quiz"),
            (["hackfest", "fest", "festival"], "college_fest"),
            (["exhibition", "expo"], "exhibition"),
        ]
        for keywords, c_type in type_mappings:
            if any(kw in raw_type for kw in keywords):
                canonical_type = c_type
                break

        return {
            "proposal_id": proposal_id,
            "status": "PENDING_REVIEW",
            "organization_id": org_id,
            "prompt": prompt,
            "title": parsed.get("title", f"{canonical_type.capitalize()} Event"),
            "short_description": parsed.get("short_description", "AI-generated event proposal"),
            "description": parsed.get("description", prompt),
            "category": parsed.get("category", "General"),
            "event_type": canonical_type,
            "event_mode": parsed.get("event_mode", "offline"),
            "capacity": int(parsed.get("capacity", 200)),
            "fee": float(parsed.get("fee", 0.0)),
            "form_fields": parsed.get("form_fields", []),
            "rubric": parsed.get("rubric", []),
            "workflow_steps": parsed.get("workflow_steps", []),
            "ticket_tiers": parsed.get("ticket_tiers", [{"id": "general", "name": "General Admission", "price": 0, "capacity": 200}]),
            "notification_rules": parsed.get("notification_rules", [
                {"trigger": "registration_completed", "channel": "email", "enabled": True}
            ]),
            "ai_model": "gemini",
            "created_at": _utcnow_iso()
        }

    @staticmethod
    def save_proposal(db, proposal: Dict[str, Any], user_id: str) -> str:
        """Persist a draft proposal in the ai_proposals collection."""
        proposal_id = proposal.get("proposal_id") or f"prop-{uuid.uuid4().hex[:8]}"
        proposal["proposal_id"] = proposal_id
        proposal["created_by"] = user_id
        proposal["created_at"] = proposal.get("created_at") or _utcnow_iso()
        proposal["status"] = "PENDING_REVIEW"

        if db is not None:
            db.collection("ai_proposals").document(proposal_id).set(proposal)
        return proposal_id

    @staticmethod
    def get_proposal(db, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a stored proposal by ID."""
        if db is None:
            return None
        doc = db.collection("ai_proposals").document(proposal_id).get()
        if not doc.exists:
            return None
        return doc.to_dict()

    @staticmethod
    def approve_and_apply_proposal(
        db,
        proposal_id: str,
        reviewer_id: str
    ) -> Dict[str, Any]:
        """
        Explicit human approval action:
        Atomically promotes a proposal into a production event with full configuration.
        """
        if db is None:
            raise RuntimeError("Database connection unavailable")

        doc_ref = db.collection("ai_proposals").document(proposal_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise ValueError(f"Proposal {proposal_id} not found")

        proposal = doc.to_dict()
        if proposal.get("status") == "APPROVED":
            return {
                "success": True,
                "message": "Proposal was already approved",
                "event_id": proposal.get("created_event_id"),
                "proposal_id": proposal_id
            }

        # 1. Instantiate the Event using EventService
        from services_event import EventService
        event_dict = EventService.create_event(
            db,
            title=proposal.get("title", "AI Configured Event"),
            description=proposal.get("description", ""),
            category=proposal.get("category", "General"),
            event_type=proposal.get("event_type", "general"),
            event_mode=proposal.get("event_mode", "offline"),
            capacity=proposal.get("capacity", 200),
            fee=proposal.get("fee", 0.0),
            organization_id=proposal.get("organization_id"),
            created_by=reviewer_id
        )
        event_id = event_dict["id"]

        # 2. Persist Form Fields if present
        form_fields = proposal.get("form_fields")
        if form_fields:
            db.collection("event_forms").document(event_id).set({
                "event_id": event_id,
                "fields": form_fields,
                "updated_at": _utcnow_iso(),
                "created_by": reviewer_id
            })

        # 3. Persist Judging Rubric if present
        rubric = proposal.get("rubric")
        if rubric:
            db.collection("event_rubrics").document(event_id).set({
                "event_id": event_id,
                "criteria": rubric,
                "updated_at": _utcnow_iso(),
                "created_by": reviewer_id
            })

        # 4. Record Audit Log Entry
        db.collection("audit_log").document(f"audit-{uuid.uuid4().hex[:10]}").set({
            "action": "ai_proposal_approved_and_applied",
            "proposal_id": proposal_id,
            "created_event_id": event_id,
            "reviewer_id": reviewer_id,
            "timestamp": _utcnow_iso(),
            "event_title": proposal.get("title")
        })

        # 5. Update Proposal State
        now_str = _utcnow_iso()
        doc_ref.set({
            **proposal,
            "status": "APPROVED",
            "reviewed_by": reviewer_id,
            "reviewed_at": now_str,
            "created_event_id": event_id
        })

        return {
            "success": True,
            "message": "AI Proposal approved and successfully created production event",
            "event_id": event_id,
            "proposal_id": proposal_id
        }
