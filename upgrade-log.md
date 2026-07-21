# SapthaEvent — Upgrade Log

This log tracks all upgrade cycles, verified diffs, test runs, and status transitions per the **Self-Upgrade Protocol (v2)**.

---

## Upgrade Cycle 4 — July 21, 2026

### 1. Error Propagation & Fail-Safe Compliance Fix
- **Problem Identified**: `_set_native_doc` and `_delete_native_doc` swallowed SQL transaction exceptions, returning `None`. Route handlers (`routes_compliance.py`) returned a false-positive HTTP 200 OK success response to users even if a database write failed.
- **Architectural Solution Implemented**:
  1. **Exception Propagation in Storage**: `_set_native_doc` and `_delete_native_doc` in `db_adapter.py` now log errors AND raise `RuntimeError`, preventing silent write failure.
  2. **Fail-Safe Compliance Route Handlers**: Updated `update_consent()` and `request_deletion()` in `routes_compliance.py` to catch storage exceptions and return explicit **HTTP 500 Internal Server Error** JSON responses (`{"error": "Failed to persist..."}`).
  3. **Live Database Environment Resolution**: Confirmed `db_pg.py` resolves `get_session()` to real PostgreSQL (`postgresql+pg8000://`) via PgBouncer transaction pooling in Cloud Run production when `DATABASE_URL` or `CLOUD_SQL_INSTANCE` is configured, with `sqlite:///saptha_fallback.db` for local dev.

### 2. Verification Protocol (Step 5 Results)
- **Error Handling Tests**: Added `test_deletion_request_write_failure_returns_500` and `test_update_consent_write_failure_returns_500` in `tests/test_compliance.py`.
- **Test Suite Pass Rate**: **16/16 Passed** (`tests/test_compliance.py` & `tests/test_db_adapter.py` in 1.55s).

### 3. Open Items
- **Database Consolidation**: Multi-worker persistent storage layer and error propagation verified for Phase 1 compliance collections. Phase 2 will expand to `form_submissions` and `audit_log`.
