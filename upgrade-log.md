# SapthaEvent — Upgrade Log

This log tracks all upgrade cycles, verified diffs, test runs, and status transitions per the **Self-Upgrade Protocol (v2)**.

---

## Upgrade Cycle 3 — July 21, 2026

### 1. Multi-Worker & Container Restart Persistence Fix
- **Problem Identified**: The initial in-memory dictionary global (`_NATIVE_FIRESTORE_STORE = {}`) was process-isolated, failing under Gunicorn's 4-worker process model and erasing DPDP compliance records (`user_consent` & `deletion_requests`) on container restarts.
- **Architectural Solution Implemented**:
  - Replaced the in-memory dict with a **Durable Multi-Worker Persistent Document Store** in `db_adapter.py`.
  - Storage methods (`_get_native_doc`, `_set_native_doc`, `_delete_native_doc`, `_query_native_docs`) back non-relational collections (`push_subscriptions`, `announcements`, `deletion_requests`, `user_consent`) using:
    1. **Redis Store** (`REDIS_URL` / `RATELIMIT_STORAGE_URL`) shared across all Gunicorn worker processes and Cloud Run instances.
    2. **Durable Database Fallback** (`native_document_store` persistent table) ensuring container restarts preserve all compliance audit logs permanently.

### 2. Verification Protocol (Step 5 Results)
- **Adapter & Compliance Test Suite**: **14/14 Passed** (`tests/test_compliance.py` and `tests/test_db_adapter.py` in 2.54s).
- **Multi-Process & Restart Safety**: Verified durable storage routines read and write to shared Redis / DB persistent backing.

### 3. Open Items & Next Steps
- **Database Consolidation**: Multi-worker persistent storage layer active for Phase 1 collections (`push_subscriptions`, `announcements`, `deletion_requests`, `user_consent`). Next phase will expand to `form_submissions` and `audit_log`.
