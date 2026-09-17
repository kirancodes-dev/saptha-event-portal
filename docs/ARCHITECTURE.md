# SapthaEvent System Architecture

## Executive Overview
SapthaEvent is an enterprise-grade, multi-tenant Event Operating System engineered to host, manage, evaluate, and certify any event type purely through declarative configuration.

```
                               ┌─────────────────────────────────────────┐
                               │   Client Layer (Web, PWA, iOS, Android) │
                               └────────────────────┬────────────────────┘
                                                    │ HTTPS / WSS
                               ┌────────────────────▼────────────────────┐
                               │     Reverse Proxy & Edge Security       │
                               │  (TLS Termination, Talisman CSP, WAF)   │
                               └────────────────────┬────────────────────┘
                                                    │
                 ┌──────────────────────────────────┴──────────────────────────────────┐
                 │                   SapthaEvent Application Server                    │
                 │                 (Flask + Gunicorn / Async Workers)                  │
                 └───────┬──────────────────────────┬──────────────────────────┬───────┘
                         │                          │                          │
           ┌─────────────▼────────────┐ ┌───────────▼──────────┐ ┌─────────────▼───────────┐
           │   Event Core Engine      │ │ Workflow Engine (DAG)│ │ Evaluation & Certificates │
           │  • Universal Model       │ │ • Linear & Non-linear│ │ • Multi-Judge Rubrics    │
           │  • 14 Turnkey Templates  │ │ • State Transitions  │ │ • Deterministic Ties     │
           │  • Dynamic Slug Routing  │ │ • Immutable Audit    │ │ • SHA-256 Verifier       │
           └──────────────────────────┘ └──────────────────────┘ └─────────────────────────┘
                         │                          │                          │
           ┌─────────────▼────────────┐ ┌───────────▼──────────┐ ┌─────────────▼───────────┐
           │   Zero-Trust Security    │ │ AI Event Copilot (HITL)│ │ Turnkey Ticketing & HUD │
           │  • JWT + Role Hierarchy  │ │ • Gemini 2.5 Flash   │ │ • HMAC Anti-Replay Tokens│
           │  • Anti-Brute-Force Lock │ │ • Structured Output  │ │ • Offline Vault & Sync   │
           │  • Multi-Tenant Isolation│ │ • Human-Approval Gate│ │ • Camera-Stream HUD      │
           └──────────────────────────┘ └──────────────────────┘ └─────────────────────────┘
                                                    │
                               ┌────────────────────▼────────────────────┐
                               │     Universal Database Adapter Layer    │
                               │   (Dual-Write & Fallback Abstraction)   │
                               └────────────┬──────────────────┬─────────┘
                                            │                  │
                         ┌──────────────────▼───────┐ ┌────────▼──────────────────┐
                         │ Cloud Firestore (NoSQL)  │ │ PostgreSQL / SQLite (SQL)│
                         │ Realtime Document Sync   │ │ Relational ACID Integrity│
                         └──────────────────────────┘ └──────────────────────────┘
```

---

## 1. Architectural Principles
1. **Zero Custom Code per Event**: All event variations (Hackathons, Medical Conferences, Esports, Arts Festivals, Sports Tournaments) run on the same shared engine. All behavioral differences are governed by JSON configuration schemas.
2. **Dual-Database Parity**: Full abstraction (`SQLFirestoreAdapter` and native Firestore SDK) ensures zero lock-in. Applications can switch seamlessly between Google Cloud Firestore and standard PostgreSQL without altering higher-level services.
3. **Defense-in-Depth & Zero-Trust**: Strict role-based access control (SuperAdmin, Admin, SPOC, Judge, Coordinator, Participant), ephemeral JWT tokens, HMAC-SHA256 signed QR tickets with timestamp anti-replay verification, and cryptographic certificate verification.
4. **Human-in-the-Loop (HITL) AI**: Generative AI tools assist organizers in scaffolding events in seconds, but proposals remain in `PENDING_REVIEW` until an authorized administrator verifies and approves the schema into production.
5. **Mobile-First & Offline Resilience**: Progressive Web App (PWA) with service workers combined with Capacitor native mobile wrappers enable offline ticket verification with local SQLite/IndexedDB reconciliation queues.

---

## 2. Core Subsystems

### 2.1 Universal Event Core (`services_event.py`)
- Manages universal event entity lifecycles: `draft` → `published` → `active` → `paused` → `completed` → `archived`.
- Automated slug generation ensures clean, SEO-optimized URLs with conflict resolution.
- Deep cloning capability duplicates previous events with dates shifted, resetting participant pools while preserving rubrics, workflows, and ticketing structures.

### 2.2 Turnkey Templates Catalog (`services_templates.py`)
- Provides 14 production-ready event templates.
- Each template bundles predefined custom form fields, evaluation rubrics, stage workflows, and admission tiers.
- Allows 1-click instantiation or fully custom parameter overrides.

### 2.3 Workflow State Engine (`services_workflow.py`)
- Executes directed acyclic graph (DAG) transitions across stages.
- Enforces strict transition validation rules (e.g., registration must complete before project submissions or judge evaluation).
- Emits immutable audit trail records with actor ID, source IP, previous status, next status, and timestamp.

### 2.4 Ticketing & Physical Verification (`services_ticket.py`)
- Produces tamper-evident digital passes with HMAC-SHA256 signatures over `event_id`, `registration_id`, `tier_id`, and issuance timestamp.
- Offline check-in vault queues scans on local devices and syncs deterministically with optimistic concurrency controls.

### 2.5 Evaluation & Merit Engine (`services_evaluation.py`)
- Multi-criteria weighted rubrics with normalized score aggregation.
- Real-time leaderboard compilation with configurable deterministic tie-breaking rules.
- Instant publication toggles to control student visibility.

### 2.6 Cryptographic Credentialing (`services_certificate.py`)
- Automates certificate issuance for winners, participants, coordinators, and merit holders.
- Encodes a verification SHA-256 hash enabling public third-party verification without login.

### 2.7 AI Copilot (`services_copilot.py`)
- Natural language to production event schema compiler using Google Gemini 2.5 Flash.
- Two-stage proposal lifecycle prevents unreviewed AI hallucinations from reaching live attendees.
