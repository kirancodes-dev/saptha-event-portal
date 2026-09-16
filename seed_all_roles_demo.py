"""
seed_all_roles_demo.py
======================
Seeds 1 verified demo account for each role:
- SuperAdmin
- Admin
- ClubSPOC (Manager)
- EventCoordinator (Scanner)
- Judge (Evaluator)
- Student (Participant)

Also creates a complete flagship event ("HackSaptha 2026: Universal AI & Innovation Hackathon")
with all lifecycle details:
- Registration schemas & form fields
- Ticket tiers
- Assigned SPOC, Coordinator, and Judge
- Active student registration & ticket
- Judge scoring submission
"""

import sys
import datetime
from werkzeug.security import generate_password_hash
from app import app
import models

def seed():
    print("=" * 65)
    print("  Seeding Demo Accounts & Full Lifecycle Event Details")
    print("=" * 65)

    with app.app_context():
        db = models.db

        # 1. User Accounts definition
        DEMO_USERS = [
            {
                "email": "admin@snpsu.edu.in",
                "name": "Prof. Vikram Malhotra (Super Admin)",
                "role": "SuperAdmin",
                "category": "All",
                "phone": "+91 98765 00001",
                "department": "Executive Dean Office",
                "password_raw": "Saptha@Admin2026",
                "needs_password_reset": False,
                "is_active": True,
            },
            {
                "email": "spoc@snpsu.edu.in",
                "name": "Dr. Priya Sharma (Tech Club SPOC)",
                "role": "ClubSPOC",
                "category": "Technical",
                "phone": "+91 98765 00002",
                "department": "Computer Science & Engineering",
                "password_raw": "Spoc@2026",
                "needs_password_reset": False,
                "is_active": True,
            },
            {
                "email": "coord1@snpsu.edu.in",
                "name": "Suresh Babu (Lead Coordinator)",
                "role": "EventCoordinator",
                "category": "Technical",
                "phone": "+91 98765 00003",
                "department": "Information Science",
                "password_raw": "Coord@2026",
                "needs_password_reset": False,
                "is_active": True,
            },
            {
                "email": "judge1@snpsu.edu.in",
                "name": "Dr. Arun Menon (Senior Judge)",
                "role": "Judge",
                "category": "Technical",
                "phone": "+91 98765 00004",
                "department": "Artificial Intelligence Lab",
                "password_raw": "Judge@2026",
                "needs_password_reset": False,
                "is_active": True,
            },
            {
                "email": "student001@snpsu.edu.in",
                "name": "Aarav Sharma (Student Participant)",
                "role": "Student",
                "category": "General",
                "phone": "+91 98765 00005",
                "usn": "1SNPSU22CS001",
                "department": "Computer Science",
                "semester": "6th Semester",
                "password_raw": "Student@2026",
                "needs_password_reset": False,
                "is_active": True,
            },
            # Also provide simple alternative email aliases for convenience
            {
                "email": "spoc@demo.com",
                "name": "Demo Club SPOC",
                "role": "ClubSPOC",
                "category": "Technical",
                "phone": "+91 98765 00002",
                "password_raw": "Spoc@2026",
                "needs_password_reset": False,
                "is_active": True,
            },
            {
                "email": "coordinator@demo.com",
                "name": "Demo Coordinator",
                "role": "EventCoordinator",
                "category": "Technical",
                "phone": "+91 98765 00003",
                "password_raw": "Coord@2026",
                "needs_password_reset": False,
                "is_active": True,
            },
            {
                "email": "judge@demo.com",
                "name": "Demo Judge",
                "role": "Judge",
                "category": "Technical",
                "phone": "+91 98765 00004",
                "password_raw": "Judge@2026",
                "needs_password_reset": False,
                "is_active": True,
            },
            {
                "email": "student@demo.com",
                "name": "Demo Student",
                "role": "Student",
                "category": "General",
                "phone": "+91 98765 00005",
                "usn": "1SNPSU22CS999",
                "password_raw": "Student@2026",
                "needs_password_reset": False,
                "is_active": True,
            }
        ]

        print("\n[1/3] Upserting Demo Accounts into Database...")
        for u in DEMO_USERS:
            doc_data = {
                "email": u["email"],
                "name": u["name"],
                "role": u["role"],
                "category": u.get("category", "General"),
                "phone": u.get("phone", ""),
                "department": u.get("department", ""),
                "usn": u.get("usn", ""),
                "password": generate_password_hash(u["password_raw"], method="pbkdf2:sha256"),
                "needs_password_reset": False,
                "is_active": True,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            db.collection("users").document(u["email"]).set(doc_data)
            print(f"  ✔ [{u['role']:<16}] {u['email']:<26} (Pass: {u['password_raw']})")

        # 2. Flagship Event Creation with All Details
        print("\n[2/3] Creating Complete Universal Flagship Event...")
        event_id = "hacksaptha-2026-flagship"
        today = datetime.datetime.now(datetime.timezone.utc)
        start_date = (today + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        deadline_date = (today + datetime.timedelta(days=5)).strftime("%Y-%m-%d")

        event_payload = {
            "id": event_id,
            "event_id": event_id,
            "title": "HackSaptha 2026: Universal AI & Innovation Hackathon",
            "event_name": "HackSaptha 2026: Universal AI & Innovation Hackathon",
            "description": (
                "A 36-hour national level flagship hackathon bringing together students, developers, "
                "and creators to build production-ready AI solutions across HealthTech, FinTech, and Smart Cities."
            ),
            "category": "Technical",
            "event_type": "hackathon",
            "event_mode": "hybrid",
            "venue": "Dr. A.P.J. Abdul Kalam Convention Center, SNPSU Campus",
            "location": "Bengaluru, Karnataka",
            "date": f"{start_date} — 09:00 AM IST",
            "date_iso": start_date,
            "registration_deadline": deadline_date,
            "deadline": deadline_date,
            "capacity": 300,
            "is_team": True,
            "team_min": 2,
            "team_max": 4,
            "fee": 150.0,
            "pricing_type": "paid",
            "currency": "INR",
            "status": "active",
            "approval_status": "approved",
            "banner_url": "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1600&q=80",
            "spoc_id": "spoc@snpsu.edu.in",
            "created_by": "Dr. Priya Sharma",
            "created_by_email": "spoc@snpsu.edu.in",
            "coordinators": ["coord1@snpsu.edu.in", "coordinator@demo.com"],
            "judges": ["judge1@snpsu.edu.in", "judge@demo.com"],
            # Ticket Tiers
            "ticket_tiers": [
                {
                    "id": "tier-standard",
                    "name": "Standard Participant Pass",
                    "price": 150.0,
                    "currency": "INR",
                    "capacity": 200,
                    "description": "Full 36-hr venue access, meals, mentor lounge, and swag kit"
                },
                {
                    "id": "tier-vip",
                    "name": "VIP Team Pass",
                    "price": 500.0,
                    "currency": "INR",
                    "capacity": 50,
                    "description": "Fast-track mentoring, private breakout room, and cloud credits"
                }
            ],
            # Pluggable Scoring Rubric
            "scoring_rubrics": [
                {"id": "innovation", "name": "Innovation & Originality", "max_score": 25, "weight": 0.25},
                {"id": "tech_depth", "name": "Technical Execution & Architecture", "max_score": 35, "weight": 0.35},
                {"id": "ui_ux", "name": "UI/UX & User Experience", "max_score": 20, "weight": 0.20},
                {"id": "presentation", "name": "Pitch & Working Demo", "max_score": 20, "weight": 0.20}
            ],
            # Rounds and Schedule
            "rounds": [
                {"round_number": 1, "name": "Ideation & Problem Pitch", "time": "Day 1, 11:00 AM"},
                {"round_number": 2, "name": "Architecture & Prototype Review", "time": "Day 1, 09:00 PM"},
                {"round_number": 3, "name": "Final Demo & Stage Presentation", "time": "Day 2, 03:00 PM"}
            ],
            # Custom Form Schema
            "custom_form": [
                {"id": "github_repo", "label": "GitHub Repository URL", "type": "url", "required": True},
                {"id": "tech_stack", "label": "Primary Tech Stack", "type": "text", "required": True},
                {"id": "tshirt_size", "label": "T-Shirt Size", "type": "select", "options": ["S", "M", "L", "XL", "XXL"], "required": True}
            ],
            "created_at": today.isoformat()
        }

        db.collection("events").document(event_id).set(event_payload)
        print(f"  ✔ Event Created: {event_payload['title']} (ID: {event_id})")

        # 3. Seed Participant Registration & Ticket & Evaluation
        print("\n[3/3] Creating Sample Student Registration, Ticket & Judge Evaluation...")
        reg_id = "reg-hacksaptha-student001"
        reg_payload = {
            "id": reg_id,
            "event_id": event_id,
            "event_title": event_payload["title"],
            "student_email": "student001@snpsu.edu.in",
            "student_name": "Aarav Sharma",
            "usn": "1SNPSU22CS001",
            "phone": "+91 98765 00005",
            "team_name": "QuantumCoders",
            "is_team": True,
            "team_members": [
                {"name": "Aarav Sharma", "email": "student001@snpsu.edu.in", "usn": "1SNPSU22CS001", "role": "Lead"},
                {"name": "Ananya Rao", "email": "student002@snpsu.edu.in", "usn": "1SNPSU22CS002", "role": "Fullstack"}
            ],
            "tier_id": "tier-standard",
            "amount_paid": 150.0,
            "payment_status": "completed",
            "status": "confirmed",
            "attended": False,
            "qr_code_token": f"TKT-{event_id}-AARAV-2026",
            "custom_responses": {
                "github_repo": "https://github.com/quantumcoders/ai-hackathon",
                "tech_stack": "Next.js, Python Flask, PyTorch",
                "tshirt_size": "L"
            },
            "registered_at": today.isoformat()
        }
        db.collection("registrations").document(reg_id).set(reg_payload)
        print(f"  ✔ Registration Created: {reg_id} for student001@snpsu.edu.in")

        # Sample Judge Score
        score_id = f"score-{event_id}-judge1-quantumcoders"
        score_payload = {
            "id": score_id,
            "event_id": event_id,
            "judge_email": "judge1@snpsu.edu.in",
            "team_name": "QuantumCoders",
            "scores": {
                "innovation": 24,
                "tech_depth": 33,
                "ui_ux": 18,
                "presentation": 19
            },
            "total_score": 94,
            "comments": "Excellent AI integration and crisp architecture. Clean UX demo.",
            "submitted_at": today.isoformat()
        }
        db.collection("scores").document(score_id).set(score_payload)
        print(f"  ✔ Judge Evaluation Created: {score_id} (Score: 94/100)")

    print("\n" + "=" * 65)
    print("  ALL DEMO ACCOUNTS & LIFECYCLE EVENT DETAILS SEEDED!")
    print("=" * 65)

if __name__ == "__main__":
    seed()
