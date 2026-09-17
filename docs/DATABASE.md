# SapthaEvent Dual-Database Layer

## 1. Overview
SapthaEvent incorporates a high-performance **Dual-Database Abstraction Architecture** (`db_adapter.py`, `models.py`, `db_pg.py`). This guarantees full operational parity whether running against **Google Cloud Firestore** (document-oriented, serverless real-time sync) or **PostgreSQL / SQLite** (relational, ACID-compliant).

---

## 2. Abstraction Interface: `SQLFirestoreAdapter`

The `SQLFirestoreAdapter` wraps SQLAlchemy sessions to mirror Firestore's fluent collection-document API:

```
                          ┌───────────────────────────┐
                          │   Application Services    │
                          │(Event, Ticket, Eval, etc.)│
                          └─────────────┬─────────────┘
                                        │
                         db.collection('events').document(id)...
                                        │
                          ┌─────────────▼─────────────┐
                          │   Universal Database      │
                          │        Adapter            │
                          └──────┬─────────────┬──────┘
                                 │             │
                    Firestore SDK│             │SQLAlchemy ORM
                                 │             │
                    ┌────────────▼──┐       ┌──▼────────────┐
                    │Cloud Firestore│       │PostgreSQL/    │
                    │   (NoSQL)     │       │SQLite (SQL)   │
                    └───────────────┘       └───────────────┘
```

### Supported Fluent Operations
- `db.collection(name).document(id).get()`
- `db.collection(name).document(id).set(data, merge=True)`
- `db.collection(name).document(id).update(fields)`
- `db.collection(name).document(id).delete()`
- `db.collection(name).where(filter=FieldFilter(field, op, val)).stream()`
- `db.collection(name).order_by(field, direction).limit(n).stream()`
- `db.batch()` (Atomic multi-document transactions)

---

## 3. Relational Schema Mapping

| Firestore Collection | PostgreSQL Table | Primary Key | Key Foreign Keys |
|----------------------|------------------|-------------|------------------|
| `events` | `events` | `id` (VARCHAR 36) | `organization_id` → `organizations.id` |
| `registrations` | `registrations` | `id` (VARCHAR 36) | `event_id` → `events.id`, `user_id` → `users.id` |
| `organizations` | `organizations` | `id` (VARCHAR 36) | None |
| `users` | `users` | `id` (VARCHAR 36) | `organization_id` → `organizations.id` |
| `teams` | `teams` | `id` (VARCHAR 36) | `event_id` → `events.id`, `lead_id` → `users.id` |
| `project_submissions` | `project_submissions` | `id` (VARCHAR 36) | `event_id` → `events.id`, `team_id` → `teams.id` |
| `evaluations` | `evaluations` | `id` (VARCHAR 36) | `event_id` → `events.id`, `judge_id` → `users.id` |
| `certificates` | `certificates` | `id` (VARCHAR 36) | `event_id` → `events.id`, `user_id` → `users.id` |
| `tickets` | `tickets` | `id` (VARCHAR 36) | `event_id` → `events.id`, `registration_id` → `registrations.id` |
| `audit_log` | `audit_logs` | `id` (VARCHAR 36) | `event_id` → `events.id` |

---

## 4. Dual-Write Parity & Fallback Logic
When configured with primary PostgreSQL and secondary Firestore, changes are propagated with fallback safety:
1. Primary write commits to the active relational database within an ACID transaction.
2. Async or inline secondary sync replicates state to Cloud Firestore collections for real-time mobile push listeners.
3. If Cloud SQL encounters network partition or connectivity issues, the application automatically falls back to local SQLite (`saptha_fallback.db`) with zero downtime.

---

## 5. Migrations & Seeders
- `setup_db.py`: Initializes tables and baseline roles.
- `init_superadmin.py`: Provisions the initial root administrator account.
- `seed_data.py` & `seed_demo.py`: Populates sample organizations, multi-category events, and demo evaluation rubrics.
