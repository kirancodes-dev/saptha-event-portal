# Gap Analysis: Path to Market-Ready Product (MVP+)

The Saptha Event Portal has a strong functional foundation. To transition from a working project to a market-ready product, technical, architectural, and legal compliance gaps are tracked below.

## 1. Technical & Architectural Gaps 🛠️
- **[PHASE 1 COMPLETE] Database Consolidation (Pure Firestore Native):** Confirmed decision to standardize on Google Cloud Firestore as the single source of truth. Phase 1 delivers durable multi-worker persistent document store for compliance collections (`user_consent`, `deletion_requests`, `push_subscriptions`, `announcements`) with atomic upsert (Postgres `ON CONFLICT` / SQLite `INSERT OR REPLACE`), error propagation to route handlers, and `updated_at` audit timestamps. Phase 2 will expand to `form_submissions` and `audit_log`.
- **[RESOLVED] CI/CD Automation:** Full GitHub Actions pipeline live in `.github/workflows/ci.yml`:
    - **Lint**: ruff (E/W/F rules)
    - **Test**: pytest with coverage + Codecov upload, Redis service container
    - **Docker Build**: BuildKit with GHA cache (main/master only)
    - **Security Scan**: bandit static analysis
- **API Specification:** No formal API documentation exists. A Swagger/OpenAPI specification is required for any external integrations or mobile app developers.
- **Scaling Strategy:** While Celery is used, a formal load-testing report and auto-scaling configuration for web servers are missing.

## 2. User Experience (UX) & Interface Gaps 🎨
- **Design System:** Jinja2 base templates upgraded to modern dark/neon theme system (`base_classic.html`) with glassmorphism and aurora overlay elements.
- **Accessibility (a11y):** ARIA labels present in core templates. Full keyboard navigation audit pending for institutional software compliance.
- **Onboarding Flow:** Interactive onboarding wizard (`/onboarding/wizard`) available for SPOCs and self-service organizations.
- **Mobile Polish:** PWA support with mobile navigation drawer and responsive dashboard widgets.

## 3. Product Feature Gaps 🚀
- **Calendar Integrations:** Ability to sync registered events with Google Calendar, Apple Calendar, and Outlook.
- **Advanced Analytics:** Real-time interactive leaderboards and SPOC live control room feeds for active assessments and hackathons.
- **Payment Flexibility:** Support for Stripe Gateway (`routes_payment_stripe.py`) and Razorpay webhooks.
- **Communication Center:** In-app notifications (`routes_notifications_v2.py`) and browser push notifications (`routes_push.py`).

## 4. Business & Compliance Gaps ⚖️
- **[RESOLVED] Legal Framework:** Added dedicated Terms of Service (`/terms`) and Privacy Policy (`/privacy`) pages, linked cleanly across all site navigation and footers (`base_classic.html`, `index.html`, `landing.html`).
- **[RESOLVED] Data Compliance:** Implemented full Indian DPDP Act 2023 & GDPR Article 17 / Article 20 compliance suite (`/compliance/settings`, `/compliance/export-data`, `/compliance/delete-request`, `/compliance/consent`). Write failures return HTTP 500 (not false-positive 200).
- **SLA & Support:** Public SLA status dashboard (`/compliance/sla`).
- **Monetization Engine:** Organization multi-tenancy and tier subscription billing (`middleware_tenant.py`).

---

### Summary Priority Matrix
| Priority | Gap | Status | Impact | Effort |
| :--- | :--- | :--- | :--- | :--- |
| ✅ **Resolved** | Database Consolidation (Phase 1) | Phase 1 Complete | High (Cleanliness) | Low |
| ✅ **Resolved** | Legal/Privacy Compliance (DPDP & GDPR) | Completed | High (Risk) | Low |
| ✅ **Resolved** | CI/CD Pipeline | Live (ci.yml) | Medium (Quality) | Done |
| 🟡 **High** | Design System/UX Polish | In Progress | High (Perception) | High |
| 🟡 **High** | Accessibility (a11y) Audit | Partial | Medium (Compliance) | Medium |
| 🟢 **Medium** | Calendar Integrations | Planned | Medium (Value) | Medium |
| 🟢 **Medium** | API Documentation (OpenAPI) | Planned | Low (Scale) | Medium |
