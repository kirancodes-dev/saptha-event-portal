# SapthaEvent — Upgrade Log

This log tracks all upgrade cycles, verified diffs, test runs, and status transitions per the **Self-Upgrade Protocol (v2)**.

---

## Upgrade Cycle — July 21, 2026

### 1. State Snapshot & Architectural Decision
- **Commit SHA**: `98ffd8e`
- **Database Architecture Decision**: **OPTION B (Pure Firestore Native) CONFIRMED**
  - **Rationale**: Firestore is the active production DB on Cloud Run, natively powering real-time SSE leaderboards and proctoring streams without observed consistency or latency issues. Option B avoids touching query logic across 40+ route files, eliminates dual-path adapter complexity, and matches live infrastructure.
- **Confirmed Resolved Items**:
  - `Legal & Privacy Compliance Suite (DPDP Act 2023 & GDPR)`: ✅ **RESOLVED** — Verified via routes `/terms`, `/privacy`, `/compliance/settings`, `/compliance/export-data`, `/compliance/delete-request`, and navigation links across all Jinja2 templates.

### 2. Verification Protocol (Step 5 Results)
- **Compliance Suite Runtime Test**: Passed (8/8 tests in `tests/test_compliance.py`).
- **Full Test Suite**: Passed (154/154 tests).
- **Navigation & Template Audit**:
  - `templates/base_classic.html` ➔ Added Privacy & DPDP nav links.
  - `templates/index.html` ➔ Updated footer links.
  - `templates/index_classic.html` ➔ Updated footer links.
  - `templates/marketing/landing.html` ➔ Updated footer links.

### 3. Next Action / Priority
- **Database Consolidation**: Streamline `db_adapter.py` for pure Firestore NoSQL execution and deprecate dual-path SQL abstraction code.
