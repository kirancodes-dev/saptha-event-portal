# Database Evolution & Data Architecture Plan

> **Scope:** Multi-Tenant Schema Evolution, Clean Repository Layer & Dual-Engine Parity  
> **Status:** Phase 1 Deliverable — Data Architecture Blueprint  

---

## 1. Dual-Database Paradigm (Firestore + PostgreSQL)

SapthaEvent operates in hybrid cloud environments:
1. **Google Cloud Firestore:** Primary serverless NoSQL document store used when deployed with Firebase.
2. **PostgreSQL / Supabase (with SQLite fallback):** Relational SQL storage used via `SQLFirestoreAdapter` (`db_adapter.py`) and SQLAlchemy models (`models_pg.py`).

### Architectural Rule: Clean Layering
Business logic and route blueprints must **never directly issue raw SQL or bind to low-level engine idiosyncrasies**. All access flows through standard domain repositories:

```
┌─────────────────────────────────────────────────────────────┐
│                 FLASK ROUTE CONTROLLER                      │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Calls Business Service)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                          │
│   (EventService, RegistrationService, TicketingService)     │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Invokes Domain Repository)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    REPOSITORY LAYER                         │
│  (EventRepository, TenantRepository, RegistrationRepo)      │
└──────────────────────────────┬──────────────────────────────┘
                               │ (Enforces Tenant Isolation)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              DB ADAPTER / ORM CLIENT (`db`)                 │
│        Firestore SDK   ◄── OR ──►   SQLAlchemy ORM          │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. PostgreSQL Schema Evolution (`models_pg.py`)

To support multi-tenancy and the Universal Event Engine, the relational schema evolves with the following additions while maintaining 100% backward compatibility for existing columns:

### 2.1 Table: `organizations` (New Core Entity)
```python
class Organization(Base):
    __tablename__ = "organizations"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name         = Column(String(255), nullable=False)
    slug         = Column(String(100), nullable=False, unique=True, index=True)
    domain       = Column(String(255), index=True)  # e.g., 'stanford.edu' or 'acme.corp'
    plan         = Column(String(50), nullable=False, default="free")  # free, pro, enterprise
    logo_url     = Column(String(500))
    favicon_url  = Column(String(500))
    primary_color = Column(String(20), default="#1a2557")
    accent_color  = Column(String(20), default="#f37021")
    custom_domain = Column(String(255), unique=True)
    api_key      = Column(String(128), unique=True, index=True)
    is_active    = Column(Boolean, nullable=False, default=True)
    settings_json = Column(Text)  # JSON config for features, email templates, limits
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at   = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    events       = relationship("Event", back_populates="organization", cascade="all, delete-orphan")
```

### 2.2 Updating `events` Table
Add the following columns to `Event` in `models_pg.py`:
- `organization_id` (UUID, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True for legacy events, indexed).
- `slug` (String(300), index=True).
- `event_type` (String(100), default="competition").
- `event_mode` (String(50), default="offline").
- `timezone` (String(100), default="Asia/Kolkata").
- `start_datetime` (DateTime(timezone=True)).
- `end_datetime` (DateTime(timezone=True)).
- `capacity` (Integer, default=200).
- `pricing_type` (String(50), default="free").
- `currency` (String(10), default="INR").
- `workflow_config_json` (Text).
- `evaluation_config_json` (Text).
- `ticket_tiers_json` (Text).
- `notification_rules_json` (Text).

### 2.3 Table: `tickets` (New Dedicated Entity)
Decouples tickets from simple registration records:
```python
class Ticket(Base):
    __tablename__ = "tickets"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id         = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    registration_id  = Column(UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_email       = Column(String(255), nullable=False, index=True)
    ticket_type      = Column(String(100), nullable=False, default="General")  # VIP, Speaker, Judge, General
    ticket_code      = Column(String(100), nullable=False, unique=True, index=True)
    qr_token_hash    = Column(String(255), nullable=False)
    gate_assignment  = Column(String(100))
    seat_assignment  = Column(String(100))
    status           = Column(String(50), nullable=False, default="active")  # active, checked_in, cancelled, expired
    checked_in_at    = Column(DateTime(timezone=True))
    created_at       = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
```

### 2.4 Table: `event_sessions` (New Entity for Conferences & Tracks)
```python
class EventSession(Base):
    __tablename__ = "event_sessions"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id      = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    track_name    = Column(String(100), default="Main Track")
    title         = Column(String(300), nullable=False)
    speaker_name  = Column(String(200))
    speaker_bio   = Column(Text)
    room_number   = Column(String(100))
    start_time    = Column(DateTime(timezone=True), nullable=False)
    end_time      = Column(DateTime(timezone=True), nullable=False)
    capacity      = Column(Integer, default=100)
    created_at    = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
```

---

## 3. Resolving the `db_adapter.py` Silent Drop Issue

### Root Cause Analysis
During Phase 1 codebase inspection, we identified that `db_adapter.py` maintains:
```python
COLLECTION_MAP = {
    'users': User,
    'events': Event,
    'registrations': Registration,
    'event_forms': EventForm,
    'form_submissions': FormSubmission,
    'audit_log': AuditLog,
    'push_subscriptions': PushSubscription,
    'announcements': Announcement,
    'project_submissions': ProjectSubmission
}
PURE_FIRESTORE_COLLECTIONS = {'push_subscriptions', 'announcements', 'deletion_requests', 'user_consent', 'waitlists'}
```
When code queries or writes to a collection outside these sets (such as `organizations`, `tickets`, `coupons`, `feedback`, `event_sessions`):
- `stream()` executes: `if not self.collection.model: return iter([])` (Returns empty results).
- `set()` executes: `if not self.model_class: return` (Silently drops the write).

### The Fix Plan:
1. Register `Organization` into `COLLECTION_MAP['organizations']`.
2. Register `Ticket` into `COLLECTION_MAP['tickets']`.
3. Register `EventSession` into `COLLECTION_MAP['event_sessions']`.
4. Make `native_document_store` the automatic fallback for **any unmapped collection** rather than silently dropping queries and writes.
5. In `verify_and_align_schema()`, automatically execute `CREATE TABLE IF NOT EXISTS` or `ALTER TABLE ADD COLUMN` for PostgreSQL and SQLite.

---

## 4. Strict Tenant Isolation Strategy

To prevent multi-tenant data leaks and IDOR:
1. **Context Attachment:** `middleware_tenant.py` resolves the organization from:
   - Subdomain (e.g., `mit.sapthaevent.com` → slug `mit`).
   - Custom domain (`events.university.edu` → custom domain lookup).
   - Session variable `session['org_id']`.
   - Falls back to default root platform organization.
2. **Context Injection:** Sets `g.tenant_id = org['id']`.
3. **Repository-Level Filtering:** Repositories automatically append `filter_by(organization_id=g.tenant_id)` unless the user is a verified global `SuperAdmin`.
4. **Cross-Tenant IDOR Prevention:** Any route accepting an `event_id` or `registration_id` checks:
   ```python
   if event.organization_id != g.tenant_id and not is_global_superadmin():
       abort(403)
   ```
