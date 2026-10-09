# SapthaEvent — Agent Handoff & Project Status

**Repository:** `saptha-event-portal`  
**Active Branch:** `production-ready`  
**Date:** 2026-10-10  
**Last Verified Baseline Commit:** `3c65096` (`docs: end-of-Phase 2 re-verification and phase summary`)  

---

## 1. Executive Summary & Purpose

SapthaEvent is the unified event management platform engineered for **Sapthagiri NPS University (SNPSU)**. It provides end-to-end event lifecycle coverage: public catalogue, registration, QR check-in (camera, kiosk, offline sync), team management, multi-round judging, certificates, feedback collection, automated notifications, and accreditation reporting (NAAC Criteria 5.3 / NIRF).

The codebase operates with dual-backend support (PostgreSQL via SQLAlchemy/`db_adapter.py` and Firestore), with PostgreSQL as the production target.

---

## 2. Core Repository Rules & Guidelines (MANDATORY)

Every agent and developer operating on this repository **MUST** adhere to [AGENTS.md](file:///Users/kiranbiradar/Desktop/saptha-event-portal/AGENTS.md) and [docs/FEATURE_REVIEW.md](file:///Users/kiranbiradar/Desktop/saptha-event-portal/docs/FEATURE_REVIEW.md):

1. **Source of Truth:** [docs/FEATURE_REVIEW.md](file:///Users/kiranbiradar/Desktop/saptha-event-portal/docs/FEATURE_REVIEW.md) is the absolute source of truth. Work strictly on the assigned item ID (`UPG-XX` or `BLK-XX`).
2. **Blockers First:** Never start a `UPG` item while any `BLK` item is `TODO` unless explicitly instructed by the project owner.
3. **Acceptance Criteria & Tests:** Build only what the item describes. Every criterion requires a passing automated test. Never delete, skip, or weaken an existing test.
4. **Git Commits & Push:**
   - Work happens on the `production-ready` branch.
   - Commits follow: `<ID>: <summary>` (or `docs: <summary>`).
   - **The agent never pushes to remote git repositories.** Pushing is reserved for the repository owner.
5. **Phase Workflow:** Complete each phase sequentially. Re-verify open items at phase completion and generate a phase summary in `docs/FEATURE_REVIEW.md`.

---

## 3. Current Implementation Status

### Phase Progress

| Phase | Description | Status | Reference |
|---|---|---|---|
| **Phase 0** | Plan synchronization & baseline verification | **DONE** (2026-09-30) | Commit `56a014d` |
| **Phase 1** | Security & architectural blockers (BLK-02..17) | **DONE** (2026-10-01) | Commit `affcab7` |
| **Phase 2** | Event Day experience (UPG-33, 35, 37, 39, 40, 41, 02, 06, 03, 29, 01, 34, 08, 36, 05, 07, 31) | **DONE** (2026-10-08) | Commit `3c65096` |
| **Phase 3** | **Production setup** (UPG-16, 17, 18, 19, 20, 21, 22) | **NEXT UP** | Starting with **UPG-16** |
| **Phase 4** | Frontend modernization & CSP (UPG-23..28) | Planned | Scheduled after Phase 3 |
| **Phase 5** | Clean-up & removal of `functions/saptha_app` (UPG-14, 15, 38) | Planned | Cloud Run consolidation |
| **Phase 6** | Release checks & production validation (UPG-32) | Planned | Final audit |

### Immediate Next Tasks (Phase 3)
1. **UPG-16 (Alembic baseline migrations):** An empty database must initialize cleanly via `alembic upgrade head`. Currently, Alembic migration history has gaps with newly introduced tables (`payment_orders`, `login_attempts`, `flask_sessions`, `coupon_uses`).
2. **UPG-17 / Decision D-5 (Object Storage):** Review Decision D-5 — certificates are drawn on the fly and exports are streamed, so evaluate folding S3 private bucket storage into UPG-21.
3. **UPG-18 (Inline background tasks & outbox):** Transactional outbox for reliable task delivery without Celery hard requirement.
4. **UPG-19 (Pagination):** Paginate `.stream()` calls in `routes_admin.py`.

---

## 4. Work Completed in This Update

### A. Institutional Proposals & Requisition Documents
Created high-impact institutional proposals and requisition assets for **Sapthagiri NPS University (SNPSU) - Department of Computer Science & Engineering (CSE)** and Team InnovEdge:
- [generate_hrd_proposal.py](file:///Users/kiranbiradar/Desktop/saptha-event-portal/generate_hrd_proposal.py): Professional, zero-color monochrome 8-page transmittal letter, server space requisition, and 4-stage administrative approval matrix PDF.
  - Output: `reports/SapthaEvent_HRD_Permission_Proposal.pdf`
- [generate_snpsu_proposal_docx.py](file:///Users/kiranbiradar/Desktop/saptha-event-portal/generate_snpsu_proposal_docx.py): Formatted Microsoft Word proposal document (.docx) with executive summary, problem statements, architecture, privilege matrix, and budget feasibility.
  - Output: `reports/SapthaEvent_SNPSU_CSE_Proposal.docx`
- Static copies mirrored in [static/reports/](file:///Users/kiranbiradar/Desktop/saptha-event-portal/static/reports/) for direct download via the local Flask server (`/static/reports/...`).
- Added `python-docx==1.2.0` to [requirements.txt](file:///Users/kiranbiradar/Desktop/saptha-event-portal/requirements.txt).

### B. Event Seeder for Upcoming 10 Days
- [seed_upcoming_10days_events.py](file:///Users/kiranbiradar/Desktop/saptha-event-portal/seed_upcoming_10days_events.py): Seeds 10 realistic, approved, active upcoming events spanning Oct 9–18, 2026 (CodeStorm, SapthaHack, Esports, RoboWars, Dhvani, SPL Cricket, Nritya, VentureVibe, Annual Gala).
- Fully compliant with **BLK-10** seed safety rules (`from seed_safety import guard; guard()`).

### C. Quality Assurance & Error Fixes
- **Ruff Linting:** Resolved all 14 unused imports, f-string prefixes, and whitespace issues. Verified `ruff check .` passes 100% clean.
- **Repository Hygiene:** Verified [tests/test_repo_hygiene.py](file:///Users/kiranbiradar/Desktop/saptha-event-portal/tests/test_repo_hygiene.py) passes completely (62 passed). No credentials or database files are tracked.
- **BLK-10 AST Compliance:** Verified `seed_upcoming_10days_events.py` executes `guard()` before any non-permitted imports and contains no plaintext passwords.

---

## 5. Development & Testing Commands

### Python Environment
- **Production & CI Target:** Python 3.11 with [requirements-dev.txt](file:///Users/kiranbiradar/Desktop/saptha-event-portal/requirements-dev.txt).
- **Local macOS Note:** The local `.venv` is Python 3.9.6. It runs linting and hygiene tests cleanly, but fails 5 scrypt password tests due to Apple LibreSSL limitations. Always validate full test suites against Python 3.11 (as run in CI).

### Key Commands

```bash
# 1. Lint check (must be 100% clean)
.venv/bin/ruff check .

# 2. Repo hygiene & secrets check
.venv/bin/pytest tests/test_repo_hygiene.py

# 3. Re-generate proposals
.venv/bin/python generate_hrd_proposal.py
.venv/bin/python generate_snpsu_proposal_docx.py

# 4. Seed demo upcoming events
.venv/bin/python seed_upcoming_10days_events.py

# 5. Run Flask server locally
.venv/bin/python app.py
```

---

## 6. Open Decisions for Owner

- **D-4 (UPG-42):** Confirm contact/privacy email address for terms and payment error pages (defaulting to institutional address).
- **D-5 (UPG-17 / UPG-21):** Confirm folding UPG-17 into UPG-21 backup/storage task.
- **UPG-30 (Criterion 4):** Conduct live checkout test under Razorpay test mode.
- **BLK-01 (Criterion 0):** Awaiting GitHub Support deletion of the 47 stale PR refs.
