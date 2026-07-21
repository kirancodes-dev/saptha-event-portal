# Gap Analysis: Path to Market-Ready Product (MVP+)

The Saptha Event Portal has a strong functional foundation. To transition from a working project to a market-ready product, technical, architectural, and legal compliance gaps are tracked below.

## 1. Technical & Architectural Gaps 🛠️
- **Database Consolidation (OPEN / IN PROGRESS):** The `SQLFirestoreAdapter` in `db_adapter.py` acts as a temporary compatibility bridge translating dictionary operations to PostgreSQL/SQLAlchemy ORM models with SQLite fallback. Full decommission of the adapter bridge in favor of direct SQLAlchemy ORM sessions across all routes is currently open.
- **CI/CD Automation:** Implement a full deployment pipeline (e.g., GitHub Actions) including:
    - Automated linting and formatting.
    - Automated unit and integration tests.
    - Staging vs. Production environment separation.
- **API Specification:** No formal API documentation exists. A Swagger/OpenAPI specification is required for any external integrations or mobile app developers.
- **Scaling Strategy:** While Celery is used, a formal load-testing report and auto-scaling configuration for web servers are missing.

## 2. User Experience (UX) & Interface Gaps 🎨
- **Design System:** Jinja2 base templates upgraded to modern dark/neon theme system (`base_classic.html`) with glassmorphism and aurora overlay elements.
- **Accessibility (a11y):** ARIA labels and keyboard navigation audit for institutional software compliance.
- **Onboarding Flow:** Interactive onboarding wizard (`/onboarding/wizard`) available for SPOCs and self-service organizations.
- **Mobile Polish:** PWA support with mobile navigation drawer and responsive dashboard widgets.

## 3. Product Feature Gaps 🚀
- **Calendar Integrations:** Ability to sync registered events with Google Calendar, Apple Calendar, and Outlook.
- **Advanced Analytics:** Real-time interactive leaderboards and SPOC live control room feeds for active assessments and hackathons.
- **Payment Flexibility:** Support for Stripe Gateway (`routes_payment_stripe.py`) and Razorpay webhooks.
- **Communication Center:** In-app notifications (`routes_notifications_v2.py`) and browser push notifications (`routes_push.py`).

## 4. Business & Compliance Gaps ⚖️
- **[RESOLVED] Legal Framework:** Added dedicated Terms of Service (`/terms`) and Privacy Policy (`/privacy`) pages, linked cleanly across all site navigation and footers (`base_classic.html`, `index.html`, `landing.html`).
- **[RESOLVED] Data Compliance:** Implemented full Indian DPDP Act 2023 & GDPR Article 17 / Article 20 compliance suite (`/compliance/settings`, `/compliance/export-data`, `/compliance/delete-request`, `/compliance/consent`).
- **SLA & Support:** Public SLA status dashboard (`/compliance/sla`).
- **Monetization Engine:** Organization multi-tenancy and tier subscription billing (`middleware_tenant.py`).

---

### Summary Priority Matrix
| Priority | Gap | Status | Impact | Effort |
| :--- | :--- | :--- | :--- | :--- |
| 🔴 **Critical** | Database Consolidation | Open / In Progress | High (Stability) | Medium |
| ✅ **Resolved** | Legal/Privacy Compliance (DPDP & GDPR) | Completed | High (Risk) | Low |
| 🟡 **High** | Design System/UX Polish | In Progress | High (Perception) | High |
| 🟡 **High** | CI/CD Pipeline | Planned | Medium (Quality) | Medium |
| 🟢 **Medium** | Calendar Integrations | Planned | Medium (Value) | Medium |
| 🟢 **Medium** | API Documentation | Planned | Low (Scale) | Medium |
