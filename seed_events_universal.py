"""
seed_events_universal.py — Universal Event Operating System Seeder (Phase 12)

Seeds turnkey instances of all 7 pre-built templates:
1. Hackathon ("HackSaptha Global 2026")
2. Academic Conference ("Saptha International AI Conference")
3. Hands-on Workshop ("Full-Stack Generative AI Bootcamp")
4. Executive Seminar ("Future of Quantum Computing Seminar")
5. Sports Tournament ("Saptha Inter-Collegiate Cricket Championship")
6. Cultural Competition ("Nritya & Raaga Cultural Fest 2026")
7. Virtual Webinar ("Cloud Architecture at Scale Webinar")

Demonstrates:
- Automatic custom form schemas & validation
- Multi-tier ticketing configs & dynamic QR tokens
- Pluggable scoring rubrics & tie-breaking criteria
- Automated notification trigger mappings
- Seamless execution across dual database architecture (Firestore + PostgreSQL/SQLite).
"""

import sys
import logging
from datetime import datetime, timezone, timedelta
from services_event import EventService
from services_templates import TemplateService
from models_tenant import create_organization

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def seed_universal_portal(db) -> dict:
    """
    Seed an organization and 7 diverse universal events.
    """
    logger.info("Initializing Universal Event Operating System Data...")

    # 1. Ensure Default Organization exists
    org = create_organization(
        db,
        name="Saptha National Institute of Technology",
        slug="saptha-tech",
        domain="saptha.edu",
        plan="enterprise",
        timezone_str="Asia/Kolkata",
        currency="INR",
        owner_email="dean@saptha.edu",
    )
    org_id = org["id"]
    logger.info("Organization created / verified: %s (%s)", org["name"], org_id)

    # 2. Seed all 7 templates
    template_types = [
        "hackathon",
        "conference",
        "workshop",
        "seminar",
        "sports",
        "cultural",
        "webinar",
    ]

    seeded_events = []
    base_time = datetime.now(timezone.utc) + timedelta(days=14)

    for idx, t_type in enumerate(template_types, start=1):
        preset = TemplateService.get_template(t_type)
        if not preset:
            continue

        title = f"{preset.get('name', 'Universal Event')} 2026"
        event_time = base_time + timedelta(days=idx * 7)

        venue_val = "Campus Convention Center"
        if isinstance(preset.get("venue"), dict):
            venue_val = preset["venue"].get("name", "Campus Convention Center")
        elif isinstance(preset.get("venue"), str):
            venue_val = preset["venue"]

        fee_val = 0.0
        if preset.get("ticket_tiers") and len(preset["ticket_tiers"]) > 0:
            fee_val = float(preset["ticket_tiers"][0].get("price", 0.0) or 0.0)

        event = EventService.create_event(
            db,
            organization_id=org_id,
            title=title,
            description=preset.get("description", "A premier universal event."),
            category=preset.get("category", "Technology"),
            event_type=t_type,
            event_mode="hybrid" if t_type in ("conference", "hackathon") else "offline",
            venue=venue_val,
            date_str=event_time.strftime("%Y-%m-%d"),
            deadline_str=(event_time - timedelta(days=2)).strftime("%Y-%m-%d"),
            capacity=preset.get("capacity", 250),
            pricing_type="paid" if fee_val > 0 else "free",
            fee=fee_val,
            currency="INR",
            created_by="spoc@saptha.edu",
            ticket_tiers=preset.get("ticket_tiers", []),
            custom_fields=preset.get("form_schema", []),
            evaluation_config=preset.get("evaluation_config", {}),
            workflow_config=preset.get("workflow_config", {}).get("stages"),
        )

        # Store additional notification and certificate configs directly
        rules = preset.get("notification_rules", []) or preset.get("notification_triggers", [])
        db.collection("events").document(event["id"]).set({
            "notification_rules": rules,
            "notification_triggers": rules,
            "certificate_config": preset.get("certificate_config", {}),
        }, merge=True)

        event["notification_rules"] = rules
        event["notification_triggers"] = rules
        event["certificate_config"] = preset.get("certificate_config", {})
        seeded_events.append(event)
        logger.info("  [✔] Seeded Event #%d: '%s' (Type: %s, ID: %s)", idx, event["title"], t_type, event["id"])

    logger.info("Universal Seeding Completed: %d events successfully created!", len(seeded_events))
    return {
        "organization": org,
        "events_count": len(seeded_events),
        "events": seeded_events,
    }


if __name__ == "__main__":
    try:
        from app import app
        with app.app_context():
            from models import db
            seed_universal_portal(db)
    except Exception as exc:
        logger.error("Seeder execution error: %s", exc)
        sys.exit(1)
