# SapthaEvent: Comprehensive Engineering Audit & Current Architecture

> **Audit Date:** September 2026  
> **Repository:** `kirancodes-dev/saptha-event-portal`  
> **Active Branch / Working Directory:** `/Users/kiranbiradar/Desktop/saptha-event-portal`  
> **Auditor:** Staff-Level Principal Systems Architect (Phase 1 Engineering Audit)

---

## 1. Executive Summary

SapthaEvent is an established, feature-rich web platform initially designed for college campus technical, cultural, and sports fests at Sapthagiri NPS University (SNPSU). The codebase contains **40+ route modules**, over **14,000 lines of Python backend logic**, a **dual-database abstraction layer** (Firestore and PostgreSQL via SQLAlchemy), background job processing via Celery & Redis, QR check-in & ticketing, dynamic form builder, judge scoring & live leaderboards, ReportLab PDF certificate generation, multiple notification providers (Email, WhatsApp, Web Push), and basic PWA service-worker lifecycle handling.

**Current Test Suite Status:**
- Total tests executed: **161**
- Tests passing: **161 (100% pass rate)**
- Failures: **0**
- Warnings: **242** (primarily deprecated session filesystem options, Python 3.9 deprecation warnings, in-memory rate-limiter notifications, and HMAC key lengths in unit tests).
- Execution runtime: **~70.7 seconds**.

While functional and extensive, the system is conceptually hardwired around college campus workflows (`Student`, `ClubSPOC`, `USN`, academic semesters, predefined categories `Technical`, `Cultural`, `Sports`, `Management`). To become a **Universal Event Operating System**, the platform must undergo an architectural transition from an event-specific application to a configuration-driven, multi-tenant Event Engine.

---

## 2. Core Architecture Breakdown

### 2.1 Backend Architecture
- **Framework:** Flask (modular monolithic application using Flask Blueprints).
- **WSGI & Server:** ProxyFix middleware for TLS termination behind Cloud Run, Render, or Railway reverse proxies.
- **Application Factory:** Single `app` instance created in `app.py` (959 lines) with global extension bindings (`Mail`, `CSRFProtect`, `Session`, `Talisman`, `Limiter`).
- **Asynchronous Task Queue:** Celery (`celery_app.py`, `tasks/`) backed by Redis for heavy operations (bulk email blasts, reminder scheduling, payment webhooks, daily rollups).

### 2.2 Database Architecture & Dual-Engine Abstraction
The system supports two database backends controlled via `DATABASE_TYPE` (`postgres` vs `firebase`):
1. **Google Cloud Firestore (Native NoSQL):**
   - Document-store accessed via `google-cloud-firestore` SDK.
   - Collections: `users`, `events`, `registrations`, `event_forms`, `form_submissions`, `audit_log`, `announcements`, `push_subscriptions`, `organizations`, `waitlists`.
2. **PostgreSQL / SQLite via `SQLFirestoreAdapter` (`db_adapter.py`):**
   - Implements a transparent adapter mimicking Firestore's `.collection().document().get() / .set() / .stream() / .where()`.
   - Maps core collections to relational tables in `models_pg.py`:
     - `users` → `User` (PK: `id` VARCHAR)
     - `events` → `Event` (PK: `id` UUID)
     - `registrations` → `Registration` (PK: `id` UUID) + nested `TeamMember` & `Score` tables
     - `event_forms` → `EventForm` (PK: `event_id` UUID)
     - `form_submissions` → `FormSubmission` (PK: `id` UUID)
     - `audit_log` → `AuditLog` (PK: `id` UUID)
     - `push_subscriptions` → `PushSubscription`
     - `announcements` → `Announcement`
     - `project_submissions` → `ProjectSubmission`
   - **Fallback Storage:** For collections not present in `COLLECTION_MAP`, `db_adapter.py` provides a `native_document_store` table storing JSON blobs with upsert semantics.

### 2.3 Authentication, Authorization & Identity
- **Session Management:** Flask-Session backed by Redis in production with fallback to filesystem.
- **Password Hashing:** Werkzeug `pbkdf2:sha256` patched to support environments without native `scrypt`.
- **RBAC Roles:** `SuperAdmin` / `Super Admin`, `Admin`, `Coordinator` / `EventCoordinator`, `SPOC` / `ClubSPOC`, `Judge`, `Student` / `Participant`.
- **Advanced Auth Modules:**
  - `auth_oauth.py`: Google OAuth 2.0 integration via `google-auth` / OAuthlib.
  - `auth_2fa.py`: TOTP two-factor authentication with QR provisioning and backup recovery codes.
  - `auth_jwt.py`: JWT generation and verification for REST API endpoints (`/api/v1/*`).
- **Access Control:** Decorators `login_required` and `role_required(...)` in `utils.py`.

### 2.4 Registration & Form Engine
- **Dynamic Forms (`routes_forms.py`):**
  - Admins / SPOCs configure custom fields per event stored in `event_forms/<event_id>` as JSON.
  - Field types supported: `text`, `email`, `phone`, `number`, `dropdown`, `radio`, `checkbox`, `file`.
  - Public registration at `/forms/register/<event_id>` renders form dynamically.
  - Submissions validated server-side, saved to `registrations` and `form_submissions`.
- **Team Management (`routes_teams.py`):**
  - Handles lead participant + team members (`min_team_size` to `max_team_size`).
  - Stores team members in nested list (Firestore) or `team_members` table (PostgreSQL).

### 2.5 QR, Ticketing & Check-in System
- **QR Generation (`utils_qr.py`):** Uses Python `qrcode` + PIL to generate high-res PNG base64 strings or direct image streams.
- **Ticketing (`routes_ticket.py`):** Renders interactive tickets (`/ticket/<reg_id>`) with QR code, participant name, event title, venue, and status.
- **Check-in Modes (`routes_checkin.py` & `routes_coordinator.py`):**
  - **Coordinator Scan Mode:** Camera-based scanner at `/coordinator/scan` or `/spoc/scan` scanning registration tokens.
  - **Self Check-in Mode:** Venue QR code at `/checkin/<event_id>` where participants enter their registered email to mark attendance.

### 2.6 Evaluation, Scoring & Leaderboard
- **Judge Scoring (`routes_judge.py`):**
  - Judges log in and view assigned events/participants.
  - Multi-criteria rubric (e.g., Innovation, Presentation, Technical Feasibility) with weights.
  - Round progression (`current_round`, `is_eliminated`, `total_rounds`).
  - Score locking prevents tampering once finalized.
- **Live Leaderboard (`routes_live.py`):**
  - Server-Sent Events (SSE) stream at `/live/stream/<event_id>` broadcasting real-time rankings and score updates to auditorium displays.

### 2.7 Certification System (`utils_certificate.py`, `routes_verification.py`)
- **Engine:** ReportLab PDF generation with 5 pre-built design themes (Classic Navy, Tech Blue, Cultural Gold, Sports Green, Management Purple) + custom image overlay mode.
- **Verification:** Each certificate includes a unique verification ID and cryptographic verification URL (`/verify/<cert_id>`) with QR code.
- **Delivery:** Direct PDF download and automated email delivery.

### 2.8 Payment Gateway Integrations
- **Razorpay (`routes_payment.py`):**
  - Order creation via Razorpay API.
  - Client-side checkout modal.
  - Server-side signature verification using HMAC-SHA256 (`razorpay_signature`).
- **Stripe (`routes_payment_stripe.py`):**
  - Stripe Checkout Session creation.
  - Webhook endpoint `/stripe/webhook` verifying Stripe webhook signatures.
- **Coupons & Dynamic Pricing (`routes_coupons.py`, `routes_dynamic_pricing.py`):** Discount codes, percentage vs flat deductions, early-bird limits.

### 2.9 Communication & Notifications
- **Email (`utils_email.py`):** SMTP / Flask-Mail with responsive HTML templates for registrations, tickets, credentials, reminders, and certificates.
- **WhatsApp (`utils_whatsapp.py`):** UltraMsg API integration for ticket delivery, room assignments, and elimination alerts.
- **Web Push (`routes_push.py`):** W3C Push API with pywebpush (VAPID keys) and service worker integration.

### 2.10 AI Capabilities
- **AI Matching (`routes_ai_matching.py`):** Team recommendation and candidate matchmaking using embeddings.
- **AI Features (`routes_ai_features.py`):** Google Gemini integration (`google-genai` / `google.generativeai`) for generating post-event executive summaries, business intelligence reports, and attendee sentiment analysis.
- **Chatbot (`chatbot_routes.py`):** FAQ and event assistance chatbot.

### 2.11 Multi-Tenancy & White-Labeling (`models_tenant.py`, `middleware_tenant.py`)
- Preliminary organization model with slug/domain lookup (`models_tenant.py`).
- Host-header and subdomain detection middleware (`middleware_tenant.py`) attaching `g.tenant` to Flask context.
- Custom branding fields (primary color, logo, plan limits).

### 2.12 Mobile UX & PWA
- Service worker (`static/sw.js`) served from root `/sw.js` with `Service-Worker-Allowed: /`.
- Web App Manifest (`/manifest.webmanifest`).
- Offline fallback page (`/offline`).
- Mobile CSS breakpoints and basic touch layout.

---

## 3. Inventory of Routes and Blueprints

The system registers **35+ Blueprints** in `app.py`:

| Blueprint | Route Prefix | Primary Purpose |
|---|---|---|
| `auth_bp` | `/` | Login, logout, register, reset password |
| `oauth_bp` | `/auth/google` | Google OAuth2 single sign-on |
| `twofa_bp` | `/2fa` | TOTP 2FA enrollment, challenge, recovery |
| `admin_bp` | `/admin` | Institution-wide admin dashboard, user management, audit logs |
| `coord_bp` | `/coordinator` | Event management, coordinator dashboard, attendee scanning |
| `spoc_bp` | `/spoc` | Club SPOC operations, event creation wizard, broadcast blasts |
| `participant_bp` | `/participant` | Student dashboard, enrolled events, team invites, certificates |
| `forms_bp` | `/forms` | Form builder, public registration page, submission processing |
| `ticket_bp` | `/ticket` | Mobile ticket view, downloadable PDF/image ticket, QR endpoint |
| `checkin_bp` | `/checkin` | Public self check-in landing page and processing |
| `judge_bp` | `/judge` | Evaluation portal, rubric scoring, round advancements |
| `live_bp` | `/live` | Live leaderboard display and SSE real-time stream |
| `payment_bp` | `/payment` | Razorpay payment orders and callback verification |
| `stripe_bp` | `/payment/stripe` | Stripe checkout sessions and webhooks |
| `coupons_bp` | `/coupons` | Promo code validation and discount calculation |
| `dynamic_pricing_bp`| `/pricing` | Tiered pricing rules (early bird, VIP) |
| `verification_bp` | `/verify` | Public certificate authentication and QR verification |
| `teams_bp` | `/teams` | Team creation, member invitations, join requests |
| `profile_bp` | `/profile` | User profile updates, notification preferences |
| `feedback_bp` | `/feedback` | Post-event attendee feedback forms and aggregation |
| `notif_bp` / `notif_v2_bp` | `/notifications` | In-app notification center and broadcast dispatcher |
| `push_bp` | `/push` | Web Push subscription registration and test dispatch |
| `ai_bp` | `/ai` | AI team matchmaking |
| `ai_features_bp` | `/ai/features` | Gemini event summaries and analytics reports |
| `chatbot_routes` | `/chatbot` | Event portal FAQ AI assistant |
| `api_bp` / `api_v1_bp`| `/api`, `/api/v1` | REST API for mobile app / third-party integrations |
| `compliance_bp` | `/compliance` | GDPR/DPDP data export and account deletion requests |
| `waitlist_bp` | `/waitlist` | Event waitlist management and auto-promotion |
| `analytics_bp` | `/analytics` | Registration and financial analytics |
| `marketing_bp` | `/marketing` | Public landing pages, SEO banners, promotional campaigns |
| `i18n_bp` | `/i18n` | Multi-language localization switching |
| `developer_bp` | `/developer` | API keys, webhooks, and developer docs |
| `gamification_bp` | `/gamification` | Participant XP, badges, and campus leaderboards |
| `exams_bp` | `/exams` | Online quiz / exam runner for technical rounds |
| `hackathon_bp` | `/hackathon` | Milestone tracking, GitHub submission, project judging |

---

## 4. Current Test Suite Analysis

Executing `uv run pytest` yields:
```
================= 161 passed, 242 warnings in 70.69s (0:01:10) =================
```
**Breakdown by test module:**
- `tests/test_auth.py`: Login, registration, password hashing, session expiration.
- `tests/test_jwt_auth.py`: JWT token issue, signature verification, expiry.
- `tests/test_security.py`: Input sanitization, XSS mitigation, audit logging, masking.
- `tests/test_forms.py`: Form builder schema validation, submission constraints.
- `tests/test_ticket.py`: Ticket generation, QR token resolution.
- `tests/test_checkin.py`: Coordinator and self-checkin flows.
- `tests/test_payment.py`: Payment order creation, webhook verification.
- `tests/test_judge.py`: Score calculations, criteria weights, locking.
- `tests/test_certificate.py`: PDF rendering, verification hash checking.
- `tests/test_tenant.py`: Organization CRUD, slug lookups, plan constraints.
- `tests/test_waitlist.py`: Queue ordering, waitlist promotion.
- `tests/test_compliance.py`: Data subject access requests (DSAR), deletion.
- `tests/test_tasks.py`: Celery async tasks and background email dispatches.
- `tests/test_spoc_features.py`: SPOC workflows, blast previews, round management.

**Key Observation:** All 161 tests pass cleanly, meaning existing functionality is robust and well-verified. Any refactoring must preserve 100% of these test invariants.
