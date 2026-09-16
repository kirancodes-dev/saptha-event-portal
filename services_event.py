"""
services_event.py — Universal Event Engine Service Layer

Handles configuration-driven event lifecycle, slug generation, event retrieval,
event cloning, and workflow state transitions without modifying source code for new event types.
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except ImportError:
    FieldFilter = None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_event_slug(title: str, existing_check_fn=None) -> str:
    """Generate a URL-safe lowercase slug from an event title, ensuring uniqueness."""
    clean = (title or "").strip()
    if not clean:
        base = f"event-{uuid.uuid4().hex[:6]}"
    else:
        base = re.sub(r'[^a-z0-9]+', '-', clean.lower()).strip('-')
        if not base:
            base = f"event-{uuid.uuid4().hex[:6]}"
    
    slug = base
    if existing_check_fn:
        counter = 1
        while existing_check_fn(slug) and counter < 100:
            slug = f"{base}-{counter}"
            counter += 1
    return slug


# Default workflow steps for turnkey event types
DEFAULT_WORKFLOWS: Dict[str, List[Dict[str, Any]]] = {
    "hackathon": [
        {"id": "registration", "label": "Registration", "order": 1, "status": "active"},
        {"id": "team_formation", "label": "Team Formation", "order": 2, "status": "pending"},
        {"id": "submission", "label": "Project Submission", "order": 3, "status": "pending"},
        {"id": "evaluation", "label": "Judge Evaluation", "order": 4, "status": "pending"},
        {"id": "finals", "label": "Final Presentations", "order": 5, "status": "pending"},
        {"id": "results", "label": "Winners & Results", "order": 6, "status": "pending"},
        {"id": "certificates", "label": "Certificates", "order": 7, "status": "pending"},
    ],
    "conference": [
        {"id": "registration", "label": "Ticket Registration", "order": 1, "status": "active"},
        {"id": "payment", "label": "Payment Confirmation", "order": 2, "status": "pending"},
        {"id": "checkin", "label": "Gate Check-in", "order": 3, "status": "pending"},
        {"id": "sessions", "label": "Keynotes & Tracks", "order": 4, "status": "pending"},
        {"id": "feedback", "label": "Attendee Feedback", "order": 5, "status": "pending"},
        {"id": "certificates", "label": "Attendance Certificate", "order": 6, "status": "pending"},
    ],
    "sports": [
        {"id": "registration", "label": "Team Registration", "order": 1, "status": "active"},
        {"id": "roster_verification", "label": "Roster Verification", "order": 2, "status": "pending"},
        {"id": "fixtures", "label": "Match Fixtures", "order": 3, "status": "pending"},
        {"id": "matches", "label": "Live Matches & Scoring", "order": 4, "status": "pending"},
        {"id": "finals", "label": "Championship Finals", "order": 5, "status": "pending"},
        {"id": "results", "label": "Medals & Certificates", "order": 6, "status": "pending"},
    ],
    "workshop": [
        {"id": "registration", "label": "Seat Registration", "order": 1, "status": "active"},
        {"id": "checkin", "label": "Check-in", "order": 2, "status": "pending"},
        {"id": "hands_on", "label": "Hands-On Session", "order": 3, "status": "pending"},
        {"id": "quiz", "label": "Assessment / Quiz", "order": 4, "status": "pending"},
        {"id": "certificates", "label": "Completion Certificate", "order": 5, "status": "pending"},
    ],
    "general": [
        {"id": "registration", "label": "Registration", "order": 1, "status": "active"},
        {"id": "checkin", "label": "Check-in", "order": 2, "status": "pending"},
        {"id": "results", "label": "Results", "order": 3, "status": "pending"},
        {"id": "certificates", "label": "Certificates", "order": 4, "status": "pending"},
    ],
}


class EventService:
    """Service handling configuration-driven universal events."""

    @staticmethod
    def create_event(
        db,
        *,
        title: str,
        description: str = "",
        category: str = "General",
        event_type: str = "general",
        event_mode: str = "offline",
        venue: str = "Main Venue",
        date_str: str = "",
        deadline_str: str = "",
        organization_id: Optional[str] = None,
        slug: Optional[str] = None,
        capacity: int = 200,
        pricing_type: str = "free",
        fee: float = 0.0,
        currency: str = "INR",
        timezone_str: str = "Asia/Kolkata",
        created_by: str = "",
        workflow_config: Optional[List[Dict[str, Any]]] = None,
        evaluation_config: Optional[Dict[str, Any]] = None,
        ticket_tiers: Optional[List[Dict[str, Any]]] = None,
        custom_fields: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create a new universal event with configuration-driven pipeline."""
        event_id = str(uuid.uuid4())
        
        # Determine slug
        def _slug_exists(test_slug: str) -> bool:
            return EventService.get_event_by_slug(db, test_slug) is not None

        final_slug = slug or generate_event_slug(title, _slug_exists)
        
        # Resolve workflow
        wf = workflow_config or DEFAULT_WORKFLOWS.get(event_type.lower(), DEFAULT_WORKFLOWS["general"])
        
        # Default ticket tiers if none provided
        tiers = ticket_tiers or [
            {
                "id": "tier-general",
                "name": "General Admission",
                "price": fee,
                "capacity": capacity,
                "currency": currency,
                "status": "available",
            }
        ]

        event_data: Dict[str, Any] = {
            "id": event_id,
            "organization_id": organization_id,
            "title": title.strip(),
            "slug": final_slug,
            "description": description.strip(),
            "overview": description.strip(),
            "category": category,
            "event_type": event_type.lower(),
            "event_mode": event_mode.lower(),  # offline | online | hybrid
            "timezone": timezone_str,
            "date": date_str or datetime.now().strftime("%Y-%m-%d"),
            "deadline": deadline_str or "",
            "venue": venue.strip(),
            "status": "active",  # active | draft | completed | cancelled
            "capacity": capacity,
            "pricing_type": pricing_type.lower(),
            "fee": float(fee),
            "entry_fee": float(fee),
            "currency": currency,
            "max_teams": capacity,
            "min_team_size": 1,
            "max_team_size": 1,
            "total_rounds": 1,
            "active_round": 1,
            "registration_count": 0,
            "created_by": created_by,
            "created_at": _utcnow_iso(),
            "updated_at": _utcnow_iso(),
            "workflow_config": wf,
            "evaluation_config": evaluation_config or {},
            "ticket_tiers": tiers,
            "notification_rules": [],
        }

        # Persist event
        db.collection("events").document(event_id).set(event_data)

        # If custom form fields provided, persist to event_forms
        if custom_fields is not None:
            form_data = {
                "event_id": event_id,
                "fields": custom_fields,
                "form_title": f"{title} Registration",
                "form_desc": f"Register for {title}",
                "created_at": _utcnow_iso(),
            }
            db.collection("event_forms").document(event_id).set(form_data)

        return event_data

    @staticmethod
    def get_event(db, event_id: str) -> Optional[Dict[str, Any]]:
        """Fetch event by document ID."""
        doc = db.collection("events").document(event_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        data["id"] = doc.id
        return data

    @staticmethod
    def get_event_by_slug(db, slug: str) -> Optional[Dict[str, Any]]:
        """Fetch event by its unique URL slug."""
        cleaned_slug = slug.strip().lower()
        if FieldFilter:
            docs = (
                db.collection("events")
                .where(filter=FieldFilter("slug", "==", cleaned_slug))
                .limit(1)
                .stream()
            )
        else:
            docs = (
                db.collection("events")
                .where("slug", "==", cleaned_slug)
                .limit(1)
                .stream()
            )
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            if data.get("slug", "").strip().lower() == cleaned_slug:
                return data
        return None

    @staticmethod
    def list_events(
        db,
        *,
        organization_id: Optional[str] = None,
        event_type: Optional[str] = None,
        category: Optional[str] = None,
        status: str = "active",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List events with optional multi-tenant and category filters."""
        query = db.collection("events")
        if status:
            if FieldFilter:
                query = query.where(filter=FieldFilter("status", "==", status))
            else:
                query = query.where("status", "==", status)

        if organization_id:
            if FieldFilter:
                query = query.where(filter=FieldFilter("organization_id", "==", organization_id))
            else:
                query = query.where("organization_id", "==", organization_id)

        results = []
        for doc in query.limit(limit).stream():
            d = doc.to_dict()
            d["id"] = doc.id
            if event_type and d.get("event_type") != event_type.lower():
                continue
            if category and d.get("category") != category:
                continue
            results.append(d)
        return results

    @staticmethod
    def clone_event(
        db,
        *,
        source_event_id: str,
        new_title: str,
        new_date: str,
        new_deadline: str = "",
        actor_email: str = "",
        new_organization_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Deep-clone an event configuration WITHOUT copying registrations, payments, or scores.
        Copies forms, workflow structure, ticket tiers, and scoring rubrics.
        """
        source = EventService.get_event(db, source_event_id)
        if not source:
            return None

        # Fetch source form schema
        source_form = None
        form_doc = db.collection("event_forms").document(source_event_id).get()
        if form_doc.exists:
            fd = form_doc.to_dict()
            source_form = fd.get("fields", [])

        # Create cloned event
        cloned = EventService.create_event(
            db,
            title=new_title,
            description=source.get("description", ""),
            category=source.get("category", "General"),
            event_type=source.get("event_type", "general"),
            event_mode=source.get("event_mode", "offline"),
            venue=source.get("venue", "Main Venue"),
            date_str=new_date,
            deadline_str=new_deadline,
            organization_id=new_organization_id or source.get("organization_id"),
            capacity=source.get("capacity", 200),
            pricing_type=source.get("pricing_type", "free"),
            fee=source.get("fee", 0.0),
            currency=source.get("currency", "INR"),
            timezone_str=source.get("timezone", "Asia/Kolkata"),
            created_by=actor_email or source.get("created_by", ""),
            workflow_config=source.get("workflow_config"),
            evaluation_config=source.get("evaluation_config"),
            ticket_tiers=source.get("ticket_tiers"),
            custom_fields=source_form,
        )

        return cloned
