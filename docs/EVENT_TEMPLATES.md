# SapthaEvent Turnkey Templates Catalog

## 1. Overview
SapthaEvent ships with **14 pre-engineered turnkey templates** covering the full spectrum of academic, industry, athletic, and artistic events. Each template encapsulates domain-specific form fields, workflow stages, judging rubrics, and ticketing defaults so an event can launch in under 60 seconds without manual configuration.

---

## 2. Complete Turnkey Catalog

| # | Template ID | Display Name | Category | Default Mode | Key Features |
|---|-------------|--------------|----------|--------------|--------------|
| 1 | `hackathon` | Hackathon Competition | Technical | Hybrid | Team formation, GitHub submission, multi-criteria rubric, pitch finals |
| 2 | `conference` | Academic / Industry Conference | Academic | Hybrid | Multi-tier passes, call for papers, session tracks, attendance certificate |
| 3 | `workshop` | Technical / Hands-On Workshop | Technical | Offline | Prerequisite checks, lab capacity, quiz/assessment, completion badge |
| 4 | `sports` | Sports Tournament | Sports | Offline | Fixture generator, knockout/round-robin brackets, match scoring, podium |
| 5 | `cultural` | Cultural / Arts Competition | Cultural | Offline | Audition rounds, stage performance slots, artistic rubric, tie-breaking |
| 6 | `webinar` | Virtual Webinar / Masterclass | Academic | Online | Stream URL binding, Q&A queue, digital attendee pass, auto-recording link |
| 7 | `seminar` | Guest Lecture & Seminar | Academic | Hybrid | Speaker spotlight, interactive Q&A, attendance certificate |
| 8 | `meetup` | Community / Alumni Meetup | Networking | Offline | Lightning talks, speed networking sessions, open mic registration |
| 9 | `esports` | Gaming & Esports Championship | Technical | Hybrid | Gamer tags, match lobbies, discord sync, bracket progression |
| 10 | `quiz` | Trivia & Academic Quiz Bowl | Academic | Hybrid | Rapid buzzer scoring, elimination rounds, instant digital leaderboard |
| 11 | `college_fest` | Multi-Event College Festival | Mega-Event | Hybrid | Umbrella pass, inter-college tally, multi-venue scheduler |
| 12 | `exhibition` | Project & Startup Exhibition | Showcase | Offline | Booth allocation, QR-based visitor polling, investor demo slots |
| 13 | `panel` | Executive Panel Discussion | Professional | Hybrid | Moderator queue, audience sli.do integration, VIP networking tier |
| 14 | `recruitment` | Campus Placement & Career Fair | Corporate | Offline | Resume upload, company slot reservations, interviewer scorecards |

---

## 3. Template Configuration Schema (Example: Hackathon)

```json
{
  "id": "hackathon",
  "name": "Hackathon Competition",
  "category": "Technical",
  "default_mode": "hybrid",
  "default_capacity": 250,
  "description": "Multi-day rapid innovation marathon with team formation, milestone sprints, and judging.",
  "form_fields": [
    {
      "id": "github_url",
      "label": "GitHub Profile / Organization",
      "type": "url",
      "required": true
    },
    {
      "id": "track",
      "label": "Preferred Problem Statement Track",
      "type": "dropdown",
      "required": true,
      "options": ["AI / GenAI", "Web3 & Fintech", "HealthTech & Biotech", "Open Innovation"]
    },
    {
      "id": "tshirt_size",
      "label": "Swag T-Shirt Size",
      "type": "dropdown",
      "required": false,
      "options": ["S", "M", "L", "XL", "XXL"]
    }
  ],
  "rubric": [
    {
      "name": "Innovation & Novelty",
      "weight": 30,
      "description": "Originality of concept and uniqueness of technological approach."
    },
    {
      "name": "Technical Execution & Architecture",
      "weight": 35,
      "description": "Code quality, depth of stack utilization, completeness of demo."
    },
    {
      "name": "UI / UX Polish",
      "weight": 15,
      "description": "User experience intuition, accessibility, and visual polish."
    },
    {
      "name": "Pitch & Demonstration",
      "weight": 20,
      "description": "Clarity of live presentation, business viability, and Q&A defense."
    }
  ],
  "workflow_steps": [
    {"id": "registration", "label": "Registration & Team Formation", "order": 1, "status": "active"},
    {"id": "submission", "label": "Code & Project Submission", "order": 2, "status": "pending"},
    {"id": "evaluation", "label": "Preliminary Judging", "order": 3, "status": "pending"},
    {"id": "finals", "label": "Top 10 Stage Pitches", "order": 4, "status": "pending"},
    {"id": "results", "label": "Podium Winners & Results", "order": 5, "status": "pending"},
    {"id": "certificates", "label": "Cryptographic Certificates", "order": 6, "status": "pending"}
  ],
  "ticket_tiers": [
    {"id": "hacker-pass", "name": "Hacker Pass (Team of 4)", "price": 0.0, "capacity": 200, "status": "available"},
    {"id": "mentor-pass", "name": "Mentor / Industry Guest", "price": 0.0, "capacity": 50, "status": "available"}
  ]
}
```

---

## 4. Programmatic Instantiation

Developers can instantiate any template via API or service:
```python
from services_templates import TemplateService

# 1-click instantiation with overrides
new_event = TemplateService.instantiate_template(
    db,
    template_id="sports",
    title="Inter-University Badminton Championship 2026",
    venue="Indoor Sports Complex Court A-D",
    date_str="2026-10-15",
    overrides={
        "capacity": 64,
        "fee": 300.0,
        "pricing_type": "paid"
    },
    created_by="sports-director-id"
)
```
