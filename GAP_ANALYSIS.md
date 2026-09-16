# SapthaEvent: Gap Analysis & Modernization Matrix

> **Scope:** Transition from College-Centric Fest Portal → Universal, Multi-Tenant Event Operating System  
> **Status:** Phase 1 Engineering Deliverable  

---

## 1. High-Level Architectural Gaps

| Capability Area | Current State (College Fest Model) | Target State (Universal Event OS) | Impact / Risk |
|---|---|---|---|
| **Event Paradigm** | Fixed college event types (`Technical`, `Cultural`, `Sports`, `Management`). | Universal Event Engine supporting any event (Conferences, Hackathons, Seminars, Tournaments, Concerts, Corporate). | **High**: Inability to host external organizations or non-college events without code changes. |
| **Workflow Engine** | Hardcoded round progression (`total_rounds`, `current_round`, `is_eliminated`). | Configurable DAG/State Machine per event (e.g., Reg → Team → Submissions → Evaluation → Final → Certificate). | **High**: Seminars and workshops are forced into a round-based tournament model. |
| **Multi-Tenancy** | Partial Firestore organization helper (`models_tenant.py`) not mapped into PostgreSQL adapter `db_adapter.py`. | Strict tenant isolation where every query, asset, and user belongs to an `organization_id`. | **Critical**: Data leakage and silently dropped queries on PostgreSQL for multi-tenant collections. |
| **Ticketing Engine** | Direct 1-to-1 registration QR without ticket tiers. Single ticket per registration. | Multi-tier ticketing (VIP, General, Speaker, Sponsor, Student) with gate, zone, and seat allocation. | **High**: Cannot run commercial or tiered conferences. |
| **Check-in & Scanning** | Camera scan requires active network connection. Self-checkin allows any user entering email to mark Present. | Offline-capable mobile scanner with encrypted QR tokens, replay prevention, and local IndexedDB queue. | **High**: Venues with poor cellular reception experience check-in failure; self check-in spoofing. |
| **Session & Venue Mgmt** | Single venue string (`venue: "Auditorium"`). No track or session concept. | Hierarchical Venue & Session tree (Venue → Hall → Room → Stage → Track → Session → Speaker). | **Medium**: Cannot manage multi-track conferences or workshop rooms. |
| **Security & Credentials** | `README.md` exposes demo credentials (`student@demo.com` / `Demo1234`). | Automated credential rotation, removal of hardcoded passwords, object-level ACL verification. | **Critical**: Immediate attack vector in public repositories. |
| **Mobile Experience** | Responsive CSS with desktop-oriented tables and desktop navigation. | Native-like mobile-first PWA with bottom navigation bar, quick scan view, and mobile wallet. | **Medium**: Friction for mobile coordinators and attendees on 375px/390px viewports. |

---

## 2. Deep-Dive Gap Analysis by Subsystem

### 2.1 Event Model & Configuration
- **Current Model (`models_pg.py` / `models.py`):**
  - Columns: `title`, `description`, `category` (Enum: Technical, Cultural, Sports, Management), `date`, `deadline`, `venue`, `fee`, `min_team_size`, `max_team_size`, `total_rounds`.
- **Gaps:**
  - No `organization_id` foreign key on the `Event` model in `models_pg.py`.
  - No `slug` for clean public URLs (currently uses UUID or raw string).
  - No event mode (`offline`, `online`, `hybrid`).
  - No meeting URL / stream link for virtual events.
  - No timezone awareness (hardcoded to `Asia/Kolkata`).
  - No status lifecycle: currently only `active`, `inactive`, `completed`, `cancelled`, `archived` (missing `draft`, `registration_open`, `registration_closed`, `ongoing`).
  - No event template reference or cloning mechanism.

### 2.2 Dynamic Forms & Custom Fields
- **Current Model:**
  - `event_forms` table with `fields_json` and `form_submissions` with `answers_json`.
- **Gaps:**
  - Validation rules are basic (required, min/max length). Missing regex validation, file-type constraints, and conditional visibility (e.g. show field B only if field A is "Yes").
  - Form builder UI is tied to SPOC dashboard rather than a reusable standalone component.
  - Form answers are not cleanly indexed for multi-field CSV/Excel export without full JSON deserialization.

### 2.3 Ticketing & Check-in Engine
- **Current State:**
  - `routes_ticket.py` renders `/ticket/<reg_id>`.
  - Check-in simply sets `attendance = 'Present'` on `Registration`.
  - Self-check-in at `/checkin/<event_id>/submit` accepts a raw email address without authentication or token validation, allowing anyone to mark arbitrary attendees present.
- **Gaps:**
  - **No QR Replay Protection:** QR code contains the plain registration ID or student email. A screenshot can be shared and scanned multiple times unless scanned synchronously.
  - **No Offline Support:** If WiFi or 5G drops at the venue entrance, the coordinator scanner fails with network errors.
  - **No Multi-Gate / Seating Support:** Tickets lack seat, row, gate, or badge category information.

### 2.4 Evaluation & Scoring Engine
- **Current State:**
  - `Score` model has `criteria` JSON and `total` float. Handled primarily for hackathons and technical events.
- **Gaps:**
  - Hardcoded to score numbers (0-100).
  - Does not support alternative evaluation paradigms:
    - Pass / Fail (e.g. audition or preliminary screening)
    - Star Rating (1-5 stars)
    - Public Voting / Audience Choice
    - Time-based (e.g., coding speed, athletic race times)
    - Formula-based aggregated scoring (e.g. drop highest and lowest judge score).
  - Tie-breaking rules are manual rather than automated.

### 2.5 Multi-Tenancy & Database Adapter
- **Current State:**
  - `models_tenant.py` was created for Firestore, but `db_adapter.py` has:
    ```python
    PURE_FIRESTORE_COLLECTIONS = {'push_subscriptions', 'announcements', 'deletion_requests', 'user_consent', 'waitlists'}
    ```
  - `organizations` is **omitted** from both `COLLECTION_MAP` and `PURE_FIRESTORE_COLLECTIONS`.
  - Result: Calling `db.collection('organizations')` under PostgreSQL returns empty streams and ignores writes!
- **Gaps:**
  - Multi-tenancy is not enforced at the database query layer.
  - Most routes query `db.collection('events')` without scoping to `g.tenant_id`.

### 2.6 Security & Hardening
- **Identified Vulnerabilities:**
  1. **Exposed Credentials in Documentation:** `README.md` displays default passwords `Demo1234` for 5 accounts.
  2. **Unauthenticated Self Check-in:** `/checkin/<event_id>/submit` allows unauthenticated POST with an email to mark attendance.
  3. **IDOR Risks:** Several endpoints access `/ticket/<reg_id>` or `/participant/registration/<reg_id>` without verifying that `session['user_id']` matches `registration.lead_email` or has coordinator permissions.
  4. **CSRF Exemptions:** Broad CSRF exemptions applied to entire blueprints in `app.py` line 391.
  5. **HMAC Key Warning:** JWT authentication unit tests use short secrets (< 32 bytes), producing cryptographic warnings.

---

## 3. Comprehensive Item Classification Matrix

Every component and module is classified into one of five categories:
- **KEEP**: Preserve working code with minimal/no modifications.
- **REFACTOR**: Update to support universal configuration, multi-tenancy, or security.
- **REPLACE**: Supersede with an upgraded, modern engine.
- **NEW**: Implement new capability required for the Universal Event OS.
- **REMOVE**: Deprecate legacy, dead, or insecure code.

| Component / File | Current Classification | Action Plan |
|---|---|---|
| `app.py` | **REFACTOR** | Modularize middleware, mount Event Engine, enforce tenant context, secure CSRF exemptions. |
| `models.py` | **KEEP** | Core FirebaseWrapper and database resolver. |
| `models_pg.py` | **REFACTOR** | Add `organization_id`, `event_mode`, `slug`, `timezone`, `ticket_tiers`, `sessions`, `venues`. |
| `models_tenant.py` | **REFACTOR** | Unify with `models_pg.py` and register in `db_adapter.py`. |
| `db_adapter.py` | **REFACTOR** | Register `organizations`, `tickets`, `sessions`, `venues` in collections and schema alignment. |
| `repositories.py` | **REFACTOR** | Introduce clean Repository pattern (`EventRepository`, `RegistrationRepository`, `TenantRepository`). |
| `routes_auth.py` | **REFACTOR** | Multi-tenant auth scoping, sanitize default seeds, enforce rate-limiting. |
| `auth_oauth.py` / `auth_2fa.py` | **KEEP** | Excellent security foundation; maintain 100% test compatibility. |
| `auth_jwt.py` | **REFACTOR** | Ensure minimum 256-bit secret keys and tenant claim inclusion. |
| `routes_admin.py` | **REFACTOR** | Upgrade to multi-tenant Organization & Platform SuperAdmin management. |
| `routes_coordinator.py` | **REFACTOR** | Decouple from college SPOC terminology; support universal coordinator roles. |
| `routes_spoc.py` | **REFACTOR** | Refactor massive file (2,144 lines) into modular services for event operations. |
| `routes_participant.py` | **REFACTOR** | Transform into Universal Participant Portal (`My Events`, `My Tickets`, `My Sessions`). |
| `routes_forms.py` | **REFACTOR** | Enhance dynamic form engine with regex, conditional logic, and file uploads. |
| `routes_ticket.py` | **REPLACE** | Replace with new **Ticketing Engine** supporting multi-tier tickets, gates, and seats. |
| `routes_checkin.py` | **REPLACE** | Replace with **Secure Check-in Engine** (authenticated/signed tokens, anti-replay, duplicate detection). |
| `static/js/scanner.js` | **NEW** | **Offline-First Check-in Scanner** with local IndexedDB queue and background sync. |
| `routes_judge.py` | **REFACTOR** | Upgrade to **Universal Evaluation Engine** (scores, pass/fail, rating, voting, speed). |
| `routes_live.py` | **KEEP** | Maintain high-performance SSE live leaderboard. |
| `utils_certificate.py` | **KEEP / REFACTOR** | Maintain ReportLab templates; add configurable text placement and multi-category templates. |
| `routes_verification.py` | **KEEP** | Secure cryptographic certificate verification endpoint. |
| `routes_payment.py` / `routes_payment_stripe.py` | **REFACTOR** | Unify behind abstract `PaymentProvider` interface (Razorpay, Stripe, Mock). |
| `routes_coupons.py` / `routes_dynamic_pricing.py` | **KEEP** | Maintain existing discount and pricing logic. |
| `utils_email.py` / `utils_whatsapp.py` / `routes_push.py` | **REFACTOR** | Unify into an **Event-Driven Notification Engine** (`WHEN event THEN notify`). |
| `routes_marketing.py` / `routes_public.py` | **REFACTOR** | Implement dynamic SEO-optimized `/events/<slug>` public event pages. |
| `Event Template Engine` | **NEW** | Pre-built templates (Hackathon, Conference, Workshop, Seminar, Sports, Cultural, Webinar). |
| `Event Workflow Engine` | **NEW** | Configurable workflow transitions and state validation per event. |
| `Seating & Session Engine` | **NEW** | Multi-room, track, session, and seating management. |
| `Event AI Copilot` | **NEW** | Propose structure, forms, schedules, and rubrics with human approval workflow. |
| `Mobile Bottom Nav System` | **NEW** | Mobile-first bottom navigation bar and touch-first participant wallet. |
| `README.md` Demo Passwords | **REMOVE** | Purge plaintext credentials and replace with secure initialization instructions. |
| `saptha_fallback.db` / test logs | **KEEP** | Local development and testing artifacts. |
