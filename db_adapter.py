"""
db_adapter.py — Transparent SQL Firestore Compatibility Adapter for SapthaEvent

Mimics Google Cloud Firestore client APIs but routes them to Supabase (PostgreSQL)
using SQLAlchemy and the models in models_pg.py.
"""
import os
import json
import uuid
import logging
from datetime import datetime, date, timezone
from dateutil import parser as date_parser

try:
    from sqlalchemy import text
except Exception:
    sqlalchemy = None
from db_pg import get_engine, get_session
from models_pg import (
    Base, User, Event, Registration, TeamMember, Score, EventForm,
    FormSubmission, AuditLog, PushSubscription, Announcement, ProjectSubmission,
    Organization, Ticket, EventSession, OrgUnit, RoleAssignment,
    Campus, Building, Room, VenueBooking,
    UserRole, EventCategory, EventStatus, RegistrationStatus, PaymentStatus, AttendanceStatus
)

logger = logging.getLogger(__name__)

# Collection name to SQLAlchemy Model class mapping
COLLECTION_MAP = {
    'users': User,
    'events': Event,
    'registrations': Registration,
    'event_forms': EventForm,
    'form_submissions': FormSubmission,
    'audit_log': AuditLog,
    'push_subscriptions': PushSubscription,
    'announcements': Announcement,
    'project_submissions': ProjectSubmission,
    'organizations': Organization,
    'tickets': Ticket,
    'event_sessions': EventSession,
    'org_units': OrgUnit,
    'role_assignments': RoleAssignment,
    'campuses': Campus,
    'buildings': Building,
    'rooms': Room,
    'venue_bookings': VenueBooking,
}

STRING_PK_COLLECTIONS = (
    'users', 'organizations', 'tickets', 'event_sessions', 'org_units',
    'role_assignments', 'campuses', 'buildings', 'rooms', 'venue_bookings'
)

# Field name translation map: Firestore -> SQLAlchemy/Postgres
FIELD_MAP = {
    'max_participants': 'max_teams',
    'team_min': 'min_team_size',
    'team_max': 'max_team_size',
    'entry_fee': 'fee',
    'banner_url': 'poster_url',
    'registered_at': 'created_at',
    'createdAt': 'created_at',
    'updatedAt': 'updated_at',
    'isEliminated': 'is_eliminated',
    'currentRound': 'current_round',
    'paymentStatus': 'payment_status',
    'paymentId': 'payment_id',
    'leadName': 'lead_name',
    'leadEmail': 'lead_email',
    'leadPhone': 'lead_phone',
    'teamName': 'team_name',
    'fieldsJson': 'fields_json',
    'fields': 'fields_json',
    'answersJson': 'answers_json',
    'answers': 'answers_json',
    'actorEmail': 'actor_email',
    'targetId': 'target_id',
    'student_email': 'lead_email',
    'reg_id': 'registration_id',
    'regId': 'registration_id',
    'organization_id': 'organization_id',
    'organizationId': 'organization_id',
    'org_id': 'organization_id',
    'org_unit_id': 'org_unit_id',
    'orgUnitId': 'org_unit_id',
    'user_id': 'user_id',
    'userId': 'user_id',
    'scope_type': 'scope_type',
    'scopeType': 'scope_type',
    'scope_id': 'scope_id',
    'scopeId': 'scope_id',
    'event_type': 'event_type',
    'eventType': 'event_type',
    'event_mode': 'event_mode',
    'eventMode': 'event_mode',
    'mode': 'event_mode',
    'visibility': 'visibility',
    'start_datetime': 'start_datetime',
    'startDatetime': 'start_datetime',
    'end_datetime': 'end_datetime',
    'endDatetime': 'end_datetime',
    'pricing_type': 'pricing_type',
    'pricingType': 'pricing_type',
    'workflow_config': 'workflow_config_json',
    'workflow_config_json': 'workflow_config_json',
    'workflowConfigJson': 'workflow_config_json',
    'evaluation_config': 'evaluation_config_json',
    'evaluation_config_json': 'evaluation_config_json',
    'evaluationConfigJson': 'evaluation_config_json',
    'ticket_tiers': 'ticket_tiers_json',
    'ticket_tiers_json': 'ticket_tiers_json',
    'ticketTiersJson': 'ticket_tiers_json',
    'notification_rules': 'notification_rules_json',
    'notification_rules_json': 'notification_rules_json',
    'notificationRulesJson': 'notification_rules_json',
    'certificate_config': 'certificate_config_json',
    'certificate_config_json': 'certificate_config_json',
    'certificateConfigJson': 'certificate_config_json',
    'feedback': 'feedback_json',
    'feedback_json': 'feedback_json',
    'checkin_time': 'checkin_time',
    'ticket_id': 'ticket_id',
    'capacity': 'capacity',
    'room_id': 'room_id',
    'roomId': 'room_id',
    'campus_id': 'campus_id',
    'campusId': 'campus_id',
    'building_id': 'building_id',
    'buildingId': 'building_id',
    'room_number': 'room_number',
    'roomNumber': 'room_number',
    'facilities_json': 'facilities_json',
    'facilitiesJson': 'facilities_json',
    'facilities': 'facilities_json',
    'session_id': 'session_id',
    'sessionId': 'session_id',
    'start_time': 'start_time',
    'startTime': 'start_time',
    'end_time': 'end_time',
    'endTime': 'end_time',
}


# Document value aliases -> SQL enum members (lower-cased keys)
ROLE_ALIASES = {
    "superadmin": UserRole.SuperAdmin,
    "admin": UserRole.SuperAdmin,
    "coordinator": UserRole.Coordinator,
    "eventcoordinator": UserRole.Coordinator,
    "clubspoc": UserRole.SPOC,
    "spoc": UserRole.SPOC,
    "judge": UserRole.Judge,
    "student": UserRole.Participant,
    "participant": UserRole.Participant,
}

CATEGORY_ALIASES = {
    "technical": EventCategory.Technical,
    "tech": EventCategory.Technical,
    "cultural": EventCategory.Cultural,
    "sports": EventCategory.Sports,
    "management": EventCategory.Management,
}

# Every EventStatus value maps to itself, so workflow states (draft, pending_approval,
# published, registration_open, ...) are never collapsed to 'active'.
EVENT_STATUS_ALIASES = {s.value: s for s in EventStatus}

REG_STATUS_ALIASES = {
    **{s.value: s for s in RegistrationStatus},
    "approved": RegistrationStatus.confirmed,
    "pending payment": RegistrationStatus.pending_payment,
}

PAYMENT_STATUS_ALIASES = {
    "paid": PaymentStatus.paid,
    "unpaid": PaymentStatus.unpaid,
    "waived": PaymentStatus.waived,
    "refunded": PaymentStatus.refunded,
}

ATTENDANCE_ALIASES = {
    "present": AttendanceStatus.Present,
    "absent": AttendanceStatus.Absent,
    "pending": AttendanceStatus.Pending,
}

ENUM_ALIASES = {
    UserRole: ROLE_ALIASES,
    EventCategory: CATEGORY_ALIASES,
    EventStatus: EVENT_STATUS_ALIASES,
    RegistrationStatus: REG_STATUS_ALIASES,
    PaymentStatus: PAYMENT_STATUS_ALIASES,
    AttendanceStatus: ATTENDANCE_ALIASES,
}


# ── Alignment Helper ────────────────────────────────────────────────────────
def verify_and_align_schema():
    """Verify and add missing columns to live Supabase Postgres tables if not present."""
    engine = get_engine()

    cols_events = [
        ('open_hall_mode', 'BOOLEAN DEFAULT FALSE'),
        ('scoring_locked', 'BOOLEAN DEFAULT FALSE'),
        ('judging_criteria_json', 'TEXT'),
        ('staff_json', 'TEXT'),
        ('organizationId', 'VARCHAR(128)'),
        ('orgUnitId', 'VARCHAR(128)'),
        ('roomId', 'VARCHAR(128)'),
        ('slug', 'VARCHAR(300)'),
        ('eventType', "VARCHAR(100) DEFAULT 'competition'"),
        ('eventMode', "VARCHAR(50) DEFAULT 'offline'"),
        ('timezone', "VARCHAR(100) DEFAULT 'Asia/Kolkata'"),
        ('startDatetime', 'TIMESTAMP WITH TIME ZONE'),
        ('endDatetime', 'TIMESTAMP WITH TIME ZONE'),
        ('capacity', 'INTEGER DEFAULT 200'),
        ('pricingType', "VARCHAR(50) DEFAULT 'free'"),
        ('currency', "VARCHAR(10) DEFAULT 'INR'"),
        ('workflowConfigJson', 'TEXT'),
        ('evaluationConfigJson', 'TEXT'),
        ('ticketTiersJson', 'TEXT'),
        ('notificationRulesJson', 'TEXT'),
        ('certificateConfigJson', 'TEXT'),
        ('visibility', "VARCHAR(50) DEFAULT 'Public'"),
    ]
    cols_payment_orders = [  # UPG-30
        ('regDataJson', 'TEXT'),
        ('failureReason', 'TEXT'),
        ('refundId', 'VARCHAR(128)'),
        ('refundedAt', 'TIMESTAMP WITH TIME ZONE'),
        ('refundedBy', 'VARCHAR(255)'),
    ]
    cols_registrations = [
        ('assigned_judge_email', 'VARCHAR(255)'),
        ('amount_paid', 'DOUBLE PRECISION'),
        ('payment_mode', 'VARCHAR(100)'),
        ('assigned_room', 'VARCHAR(100)'),
        ('checkin_time', 'VARCHAR(100)'),
        ('ticket_id', 'VARCHAR(128)'),
        ('feedback_json', 'TEXT'),
    ]

    if not engine:
        return

    # Ensure any newly introduced tables (org_units, role_assignments, campuses, buildings, rooms, venue_bookings) exist
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                OrgUnit.__table__, RoleAssignment.__table__,
                Campus.__table__, Building.__table__, Room.__table__, VenueBooking.__table__
            ],
            checkfirst=True
        )
    except Exception as e:
        logger.debug("Table creation check note: %s", e)

    is_sqlite = engine.url.drivername.startswith('sqlite')
    if is_sqlite:
        try:
            with engine.connect() as conn:
                for col, col_type in cols_events:
                    try:
                        conn.execute(text(f"ALTER TABLE events ADD COLUMN {col} {col_type}"))
                    except Exception:
                        pass
                for col, col_type in cols_registrations:
                    try:
                        conn.execute(text(f"ALTER TABLE registrations ADD COLUMN {col} {col_type}"))
                    except Exception:
                        pass
                for col, col_type in cols_payment_orders:
                    try:
                        conn.execute(text(f'ALTER TABLE payment_orders ADD COLUMN "{col}" {col_type}'))
                    except Exception:
                        pass
                conn.commit()
        except Exception as e:
            logger.debug("SQLite schema alignment note: %s", e)
        return

    try:
        with engine.connect() as conn:
            # Postgres Enum alignment
            for st in ['draft', 'pending_approval', 'published', 'registration_open', 'registration_closed', 'in_progress', 'certified']:
                try:
                    conn.execute(text(f"ALTER TYPE eventstatus ADD VALUE IF NOT EXISTS '{st}'"))
                except Exception:
                    pass
            try:
                conn.execute(text("ALTER TYPE registrationstatus ADD VALUE IF NOT EXISTS 'checked_in'"))
            except Exception:
                pass

            # Events alignment
            for col, col_type in cols_events:
                res = conn.execute(text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :table AND column_name = :col"
                ), {"table": "events", "col": col}).fetchone()
                if not res:
                    logger.info("Aligning Schema: Adding column '%s' to 'events'...", col)
                    # Quoted: camelCase column names must keep their case in Postgres
                    conn.execute(text(f'ALTER TABLE events ADD COLUMN "{col}" {col_type}'))

            # Registrations alignment
            for col, col_type in cols_registrations:
                res = conn.execute(text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :table AND column_name = :col"
                ), {"table": "registrations", "col": col}).fetchone()
                if not res:
                    logger.info("Aligning Schema: Adding column '%s' to 'registrations'...", col)
                    conn.execute(text(f'ALTER TABLE registrations ADD COLUMN "{col}" {col_type}'))

            # Payment orders alignment (UPG-30)
            for col, col_type in cols_payment_orders:
                conn.execute(text(f'ALTER TABLE IF EXISTS payment_orders ADD COLUMN IF NOT EXISTS "{col}" {col_type}'))
            conn.commit()
    except Exception as e:
        logger.error("Failed to run schema alignment checks: %s", e)


# ── Helper: ID Translation ──────────────────────────────────────────────────
def to_uuid(doc_id):
    if not doc_id:
        return None
    if isinstance(doc_id, uuid.UUID):
        return doc_id
    try:
        return uuid.UUID(str(doc_id))
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_DNS, str(doc_id))


import decimal

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, uuid.UUID):
            return str(o)
        if hasattr(o, 'value') and o.__class__.__module__ != 'builtins':
            return o.value  # enums
        if isinstance(o, (set, tuple)):
            return list(o)
        return str(o)


# ── Firestore write transforms (Increment, ArrayUnion, DELETE_FIELD, ...) ───
_DELETE = object()


def _transform_kind(val):
    """Identify a Firestore write sentinel/transform without importing the SDK."""
    name = type(val).__name__
    if name in ('Increment', 'ArrayUnion', 'ArrayRemove', 'Maximum', 'Minimum'):
        return name
    if name == 'Sentinel':
        desc = str(getattr(val, 'description', '')).lower()
        if 'delete' in desc:
            return 'DELETE_FIELD'
        if 'timestamp' in desc:
            return 'SERVER_TIMESTAMP'
    return None


def _has_transforms(data):
    return any(_transform_kind(v) for v in data.values())


def _resolve_transforms(data, current):
    """Apply write transforms against the current document state.

    Deleted fields are returned with the `_DELETE` marker.
    """
    resolved = {}
    for key, val in data.items():
        kind = _transform_kind(val)
        cur = current.get(key)
        if kind is None:
            resolved[key] = val
        elif kind in ('Increment', 'Maximum', 'Minimum'):
            base = cur if isinstance(cur, (int, float)) and not isinstance(cur, bool) else 0
            if kind == 'Increment':
                resolved[key] = base + val.value
            elif kind == 'Maximum':
                resolved[key] = max(base, val.value)
            else:
                resolved[key] = min(base, val.value)
        elif kind == 'ArrayUnion':
            items = list(cur) if isinstance(cur, list) else []
            for item in val.values:
                if item not in items:
                    items.append(item)
            resolved[key] = items
        elif kind == 'ArrayRemove':
            items = list(cur) if isinstance(cur, list) else []
            resolved[key] = [i for i in items if i not in val.values]
        elif kind == 'SERVER_TIMESTAMP':
            resolved[key] = datetime.now(timezone.utc)
        elif kind == 'DELETE_FIELD':
            resolved[key] = _DELETE
    return resolved


def _with_column_aliases(collection_name, data):
    """Copy nested/alternate Firestore fields onto the keys the SQL columns use."""
    d = dict(data)
    if collection_name == 'events':
        if d.get('spoc_id') and not d.get('coordinator_id'):
            d['coordinator_id'] = d['spoc_id']
        if d.get('reg_deadline') and not d.get('deadline'):
            d['deadline'] = d['reg_deadline']
        fees = d.get('fees')
        if isinstance(fees, dict) and 'fee' not in d and 'entry_fee' not in d:
            try:
                d['fee'] = float(fees.get('regular') or 0)
            except (TypeError, ValueError):
                pass
        limits = d.get('limits')
        if isinstance(limits, dict):
            for key in ('max_participants', 'team_min', 'team_max'):
                if limits.get(key) is not None and key not in d:
                    d[key] = limits[key]
    return d


def _submission_document(text):
    """A form submission's stored JSON as a document. Rows written before
    UPG-45 hold only the answers, so those become {'answers': …}."""
    try:
        doc = json.loads(text) if text else {}
    except (TypeError, ValueError):
        return {}
    if not isinstance(doc, dict):
        return {}
    return doc if isinstance(doc.get('answers'), dict) else {'answers': doc}


def _normalize_out(val):
    """Normalise a column value to the plain form documents expose."""
    if hasattr(val, 'value') and val.__class__.__module__ != 'builtins':
        val = val.value
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, decimal.Decimal):
        return float(val)
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            val = val.astimezone(timezone.utc).replace(tzinfo=None)
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    return val


def _py_match(doc_val, op, val):
    """Evaluate one Firestore filter against a plain document value."""
    try:
        if op == '==':
            return doc_val == val
        if op == '!=':
            return doc_val is not None and doc_val != val
        if op in ('<', '<=', '>', '>='):
            if doc_val is None or val is None:
                return False
            if op == '<':
                return doc_val < val
            if op == '<=':
                return doc_val <= val
            if op == '>':
                return doc_val > val
            return doc_val >= val
        if op == 'in':
            return doc_val in (val or [])
        if op in ('not-in', 'not_in'):
            return doc_val is not None and doc_val not in (val or [])
        if op in ('array_contains', 'array-contains'):
            return isinstance(doc_val, list) and val in doc_val
        if op in ('array_contains_any', 'array-contains-any'):
            return isinstance(doc_val, list) and any(v in doc_val for v in (val or []))
    except TypeError:
        return False
    logger.warning("Unsupported query operator %r — no documents matched", op)
    return False


def _sort_key(val):
    # None sorts first, then numbers, then strings; anything else by its str()
    if val is None:
        return (0, 0, 0)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return (1, 0, val)
    if isinstance(val, str):
        return (1, 1, val)
    return (1, 2, str(val))

def safe_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return json.dumps(val, cls=CustomJSONEncoder)
    if isinstance(val, decimal.Decimal):
        return str(float(val))
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    return str(val)


# ── Native Firestore Store (Multi-Worker Durable Document Store) ────────────
PURE_FIRESTORE_COLLECTIONS = {'push_subscriptions', 'announcements', 'deletion_requests', 'user_consent', 'waitlists'}

def _ensure_native_table(session):
    """Ensure persistent native document table exists with audit timestamp."""
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS native_document_store (
            collection_name VARCHAR(64),
            doc_id VARCHAR(128),
            data_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (collection_name, doc_id)
        )
    """))

def _db_dialect_name():
    """Return the SQLAlchemy dialect name of the active engine ('postgresql' or 'sqlite')."""
    try:
        engine = get_engine()
        return engine.dialect.name if engine else 'sqlite'
    except Exception:
        return 'sqlite'

def _get_native_doc(collection_name, doc_id):
    """Retrieve document from shared multi-worker persistent store."""
    try:
        redis_url = os.environ.get('REDIS_URL') or os.environ.get('RATELIMIT_STORAGE_URL')
        if redis_url and redis_url.startswith('redis'):
            import redis
            r = redis.Redis.from_url(redis_url, decode_responses=True)
            raw = r.get(f"doc:{collection_name}:{doc_id}")
            if raw and isinstance(raw, (str, bytes, bytearray)):
                return json.loads(raw)
    except Exception:
        pass

    try:
        with get_session() as session:
            _ensure_native_table(session)
            res = session.execute(
                text("SELECT data_json FROM native_document_store WHERE collection_name=:col AND doc_id=:id"),
                {"col": collection_name, "id": str(doc_id)}
            ).fetchone()
            if res and res[0]:
                return json.loads(res[0])
    except Exception as exc:
        logger.error("Error reading native doc %s/%s: %s", collection_name, doc_id, exc)
    return None

def _set_native_doc(collection_name, doc_id, data, merge=True):
    """Persist document via atomic upsert with error propagation.

    Uses INSERT ... ON CONFLICT DO UPDATE (Postgres) or INSERT OR REPLACE (SQLite)
    to avoid the race condition of separate DELETE + INSERT under concurrent writers.
    """
    final_data = (data or {}).copy()
    if merge:
        existing = _get_native_doc(collection_name, doc_id) or {}
        for k, v in list(final_data.items()):
            if hasattr(v, 'value') and ('Increment' in type(v).__name__ or 'Increment' in getattr(getattr(v, '__class__', None), '__name__', '')):
                base = existing.get(k, 0) or 0
                final_data[k] = base + v.value
            elif 'Sentinel' in type(v).__name__ or type(v).__name__ == '_ServerTimestamp':
                final_data[k] = datetime.now(timezone.utc).isoformat()
            elif 'DELETE_FIELD' in str(type(v)):
                final_data.pop(k, None)
                existing.pop(k, None)
        existing.update(final_data)
        final_data = existing
    else:
        for k, v in list(final_data.items()):
            if hasattr(v, 'value') and ('Increment' in type(v).__name__ or 'Increment' in getattr(getattr(v, '__class__', None), '__name__', '')):
                final_data[k] = v.value
            elif 'Sentinel' in type(v).__name__ or type(v).__name__ == '_ServerTimestamp':
                final_data[k] = datetime.now(timezone.utc).isoformat()
            elif 'DELETE_FIELD' in str(type(v)):
                final_data.pop(k, None)

    data_json = json.dumps(final_data, cls=CustomJSONEncoder)

    try:
        redis_url = os.environ.get('REDIS_URL') or os.environ.get('RATELIMIT_STORAGE_URL')
        if redis_url and redis_url.startswith('redis'):
            import redis
            r = redis.Redis.from_url(redis_url, decode_responses=True)
            r.set(f"doc:{collection_name}:{doc_id}", data_json)
    except Exception as exc:
        logger.warning("Redis sync warning for %s/%s: %s", collection_name, doc_id, exc)

    dialect = _db_dialect_name()
    try:
        with get_session() as session:
            _ensure_native_table(session)
            params = {"col": collection_name, "id": str(doc_id), "data": data_json}
            if dialect == 'postgresql':
                # Atomic upsert — single statement, no race window
                session.execute(text(
                    "INSERT INTO native_document_store (collection_name, doc_id, data_json, updated_at) "
                    "VALUES (:col, :id, :data, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (collection_name, doc_id) "
                    "DO UPDATE SET data_json = EXCLUDED.data_json, updated_at = CURRENT_TIMESTAMP"
                ), params)
            else:
                # SQLite: INSERT OR REPLACE is atomic against the composite PK
                session.execute(text(
                    "INSERT OR REPLACE INTO native_document_store (collection_name, doc_id, data_json, updated_at) "
                    "VALUES (:col, :id, :data, CURRENT_TIMESTAMP)"
                ), params)
    except Exception as exc:
        logger.error("Database write failed for native doc %s/%s: %s", collection_name, doc_id, exc)
        raise RuntimeError(f"Database write failed for {collection_name}/{doc_id}: {exc}") from exc

def _delete_native_doc(collection_name, doc_id):
    """Delete document from shared multi-worker storage with error propagation."""
    try:
        redis_url = os.environ.get('REDIS_URL') or os.environ.get('RATELIMIT_STORAGE_URL')
        if redis_url and redis_url.startswith('redis'):
            import redis
            r = redis.Redis.from_url(redis_url, decode_responses=True)
            r.delete(f"doc:{collection_name}:{doc_id}")
    except Exception as exc:
        logger.warning("Redis delete warning for %s/%s: %s", collection_name, doc_id, exc)

    try:
        with get_session() as session:
            _ensure_native_table(session)
            session.execute(text("DELETE FROM native_document_store WHERE collection_name=:col AND doc_id=:id"),
                            {"col": collection_name, "id": str(doc_id)})
            session.commit()
    except Exception as exc:
        logger.error("Database delete failed for native doc %s/%s: %s", collection_name, doc_id, exc)
        raise RuntimeError(f"Database delete failed for {collection_name}/{doc_id}: {exc}") from exc

def _query_native_docs(collection_name, filters=None, limit=None, orders=None):
    """Query documents from shared persistent storage."""
    docs = []
    try:
        with get_session() as session:
            _ensure_native_table(session)
            rows = session.execute(
                text("SELECT doc_id, data_json FROM native_document_store WHERE collection_name=:col"),
                {"col": collection_name}
            ).fetchall()
            for r in rows:
                if r[1]:
                    docs.append((r[0], json.loads(r[1])))
    except Exception as exc:
        logger.error("Error querying native docs for %s: %s", collection_name, exc)

    results = []
    for doc_id, data in docs:
        if all(_py_match(data.get(field), op, val) for field, op, val in (filters or [])):
            results.append(SQLDocumentSnapshot(doc_id, data.copy(), exists=True,
                                               collection_name=collection_name))

    results = _sort_snapshots(results, orders or [])
    if limit is not None:
        results = results[:limit]
    return iter(results)


def _load_shadow(record):
    raw = getattr(record, 'extra_json', None)
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, dict) else {}
    except (TypeError, ValueError):
        return {}


def _derive_legacy_event_fields(d):
    """Fill the nested fields templates expect for events stored before the
    document shadow existed (only when they are missing)."""
    if not d.get('spoc_id') and d.get('coordinator_id'):
        d['spoc_id'] = d['coordinator_id']
    if 'reg_deadline' not in d and d.get('deadline'):
        d['reg_deadline'] = d['deadline']
    if not isinstance(d.get('fees'), dict):
        d['fees'] = {'regular': d.get('entry_fee') or 0}
    if not isinstance(d.get('limits'), dict):
        d['limits'] = {
            'max_participants': d.get('max_participants') or 0,
            'team_min': d.get('team_min') or 1,
            'team_max': d.get('team_max') or 1,
        }
    if 'is_team_event' not in d:
        d['is_team_event'] = (d.get('team_max') or 1) > 1
    prizes = d.get('prizes')
    if isinstance(prizes, str) and prizes.startswith('{'):
        try:
            d['prizes'] = json.loads(prizes)
        except ValueError:
            pass


def _sort_snapshots(snapshots, orders):
    # Apply the last order_by first so earlier ones take precedence (stable sort)
    for field, direction in reversed(orders):
        desc = direction == 'DESCENDING' or str(direction).lower() == 'desc'
        snapshots = sorted(snapshots, key=lambda s: _sort_key(s._data.get(field)), reverse=desc)
    return snapshots


# ── Mock Classes Mimicking Firestore ─────────────────────────────────────────

class SQLDocumentSnapshot:
    """Mock DocumentSnapshot mimicking Firestore."""
    def __init__(self, doc_id, data, exists=True, collection_name=None):
        self.id = doc_id
        self.exists = exists
        self._data = data or {}
        self._collection_name = collection_name

    @property
    def reference(self):
        return SQLDocumentReference(self._collection_name, self.id)

    def to_dict(self):
        return self._data.copy()

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data


class SQLDocumentReference:
    """Mock DocumentReference mimicking Firestore."""
    def __init__(self, collection_name, doc_id):
        self.collection_name = collection_name
        self.id = doc_id
        self.model_class = COLLECTION_MAP.get(collection_name)

    def _is_native(self):
        return self.collection_name in PURE_FIRESTORE_COLLECTIONS or not self.model_class

    def _find_record(self, session):
        if self.collection_name in STRING_PK_COLLECTIONS:
            return session.query(self.model_class).filter_by(id=str(self.id)).first()
        if self.collection_name == 'event_forms':
            return session.query(self.model_class).filter_by(event_id=to_uuid(self.id)).first()
        return session.query(self.model_class).filter_by(id=to_uuid(self.id)).first()

    def get(self):
        if self._is_native():
            doc_data = _get_native_doc(self.collection_name, self.id)
            if doc_data is None:
                return SQLDocumentSnapshot(self.id, None, exists=False, collection_name=self.collection_name)
            return SQLDocumentSnapshot(self.id, doc_data, exists=True, collection_name=self.collection_name)

        with get_session() as session:
            record = self._find_record(session)
            if not record:
                return SQLDocumentSnapshot(self.id, None, exists=False, collection_name=self.collection_name)
            data = self._record_to_dict(record, session)
            return SQLDocumentSnapshot(self.id, data, exists=True, collection_name=self.collection_name)

    def set(self, data, merge=True):
        data = dict(data or {})

        if self._is_native():
            current = _get_native_doc(self.collection_name, self.id) or {}
            resolved = _resolve_transforms(data, current)
            final = dict(current) if merge else {}
            for key, val in resolved.items():
                if val is _DELETE:
                    final.pop(key, None)
                else:
                    final[key] = val
            _set_native_doc(self.collection_name, self.id, final, merge=False)
            return

        with get_session() as session:
            record = self._find_record(session)
            existed = record is not None
            current = self._record_to_dict(record, session) if existed and _has_transforms(data) else {}
            resolved = _resolve_transforms(data, current)

            # Increments on numeric columns become atomic `col = col + n` updates
            atomic = {}
            if existed:
                for key, val in data.items():
                    if _transform_kind(val) != 'Increment':
                        continue
                    attr = FIELD_MAP.get(key, key)
                    col = record.__mapper__.columns.get(attr)
                    if col is not None and col.type.__class__.__name__ in ('Integer', 'Float', 'Numeric', 'BigInteger'):
                        atomic[key] = (attr, val.value)
                        resolved.pop(key, None)

            deleted = [k for k, v in resolved.items() if v is _DELETE]
            for key in deleted:
                resolved.pop(key)

            col_data = _with_column_aliases(self.collection_name, resolved)
            if not existed:
                record = self._dict_to_new_record(col_data)
                session.add(record)
            self._update_record_fields(record, col_data, session)
            for key in deleted:
                self._clear_field(record, key, session)
            for attr, amount in atomic.values():
                setattr(record, attr, getattr(type(record), attr) + amount)

            if hasattr(record, 'extra_json'):
                shadow = _load_shadow(record) if (existed and merge) else {}
                shadow.update(resolved)
                for key in list(deleted) + list(atomic):
                    shadow.pop(key, None)
                record.extra_json = json.dumps(shadow, cls=CustomJSONEncoder)

            session.commit()

    def update(self, data):
        self.set(data, merge=True)

    def delete(self):
        if self._is_native():
            _delete_native_doc(self.collection_name, self.id)
            return

        with get_session() as session:
            if self.collection_name in STRING_PK_COLLECTIONS:
                session.query(self.model_class).filter_by(id=str(self.id)).delete()
            elif self.collection_name == 'event_forms':
                session.query(self.model_class).filter_by(event_id=to_uuid(self.id)).delete()
            else:
                session.query(self.model_class).filter_by(id=to_uuid(self.id)).delete()
            session.commit()

    def _clear_field(self, record, key, session):
        """Handle DELETE_FIELD for a column-backed or relational field."""
        if self.collection_name == 'registrations' and key == 'scores':
            session.query(Score).filter_by(registration_id=to_uuid(self.id)).delete()
            return
        attr = FIELD_MAP.get(key, key)
        col = record.__mapper__.columns.get(attr)
        if col is None:
            return
        if col.nullable:
            setattr(record, attr, None)
        elif col.default is not None and col.default.is_scalar:
            # NOT NULL columns with a default (e.g. events.visibility='Public') reset to it
            setattr(record, attr, col.default.arg)

    def collection(self, name):
        # Fallback nested collection reference stub
        return SQLCollectionReference(f"{self.collection_name}/{self.id}/{name}")

    def _record_to_dict(self, record, session) -> dict:
        """Convert a SQLAlchemy model record to a Firestore-styled dictionary."""
        d = {}
        for prop in record.__mapper__.column_attrs:
            if prop.key == 'extra_json':
                continue
            val = getattr(record, prop.key)
            # handle enums
            if hasattr(val, 'value'):
                val = val.value
            # handle UUID
            if isinstance(val, uuid.UUID):
                val = str(val)
            # handle decimal
            if isinstance(val, decimal.Decimal):
                val = float(val)
            # handle datetime/date objects to string/isoformat
            if isinstance(val, (datetime, date)):
                val = val.isoformat()

            # Map flat Python attribute key back to firestore format
            firestore_field = prop.key
            for f_key, pg_val in FIELD_MAP.items():
                if pg_val == prop.key:
                    firestore_field = f_key
                    break
            d[firestore_field] = val

        # Handle specific nested properties
        if self.collection_name == 'users':
            # Firestore uses 'password'
            d['password'] = record.password_hash
            d['is_active'] = record.is_active

        elif self.collection_name == 'events':
            # Expose custom columns
            d['open_hall_mode'] = record.open_hall_mode
            d['scoring_locked'] = record.scoring_locked
            d['judging_criteria'] = json.loads(record.judging_criteria_json) if record.judging_criteria_json else []
            d['staff'] = json.loads(record.staff_json) if record.staff_json else []
            # Overview/description fallback
            d['overview'] = record.description
            d['slug'] = getattr(record, 'slug', None)
            d['organization_id'] = getattr(record, 'organization_id', None)
            d['event_type'] = getattr(record, 'event_type', 'competition')
            d['event_mode'] = getattr(record, 'event_mode', 'offline')
            d['timezone'] = getattr(record, 'timezone', 'Asia/Kolkata')
            d['capacity'] = getattr(record, 'capacity', 200)
            d['pricing_type'] = getattr(record, 'pricing_type', 'free')
            d['currency'] = getattr(record, 'currency', 'INR')
            d['workflow_config'] = json.loads(record.workflow_config_json) if getattr(record, 'workflow_config_json', None) else {}
            d['workflow_config_json'] = getattr(record, 'workflow_config_json', None)
            d['evaluation_config'] = json.loads(record.evaluation_config_json) if getattr(record, 'evaluation_config_json', None) else {}
            d['ticket_tiers'] = json.loads(record.ticket_tiers_json) if getattr(record, 'ticket_tiers_json', None) else []
            d['notification_rules'] = json.loads(record.notification_rules_json) if getattr(record, 'notification_rules_json', None) else []
            d['room_id'] = getattr(record, 'room_id', None)
            d['roomId'] = getattr(record, 'room_id', None)
            d['visibility'] = getattr(record, 'visibility', 'Public') or 'Public'
            d['org_unit_id'] = getattr(record, 'org_unit_id', None)
            d['orgUnitId'] = getattr(record, 'org_unit_id', None)
            d['organization_id'] = getattr(record, 'organization_id', None)
            d['organizationId'] = getattr(record, 'organization_id', None)
            if hasattr(record, 'room') and record.room:
                d['room_name'] = record.room.name

        elif self.collection_name == 'rooms':
            d['room_id'] = record.id
            d['roomId'] = record.id
            d['building_id'] = record.building_id
            d['buildingId'] = record.building_id
            d['room_number'] = record.room_number
            d['roomNumber'] = record.room_number
            if getattr(record, 'facilities_json', None):
                try:
                    d['facilities'] = json.loads(record.facilities_json) if isinstance(record.facilities_json, str) else record.facilities_json
                except Exception:
                    d['facilities'] = [f.strip() for f in str(record.facilities_json).split(',') if f.strip()]
            else:
                d['facilities'] = []

        elif self.collection_name == 'venue_bookings':
            d['booking_id'] = record.id
            d['room_id'] = record.room_id
            d['roomId'] = record.room_id
            d['event_id'] = str(record.event_id) if record.event_id else None
            d['eventId'] = str(record.event_id) if record.event_id else None
            d['session_id'] = record.session_id
            d['sessionId'] = record.session_id
            d['start_time'] = record.start_time.isoformat() if record.start_time else None
            d['startTime'] = record.start_time.isoformat() if record.start_time else None
            d['end_time'] = record.end_time.isoformat() if record.end_time else None
            d['endTime'] = record.end_time.isoformat() if record.end_time else None

        elif self.collection_name == 'organizations':
            d['settings'] = json.loads(record.settings_json) if getattr(record, 'settings_json', None) else {}
            d['theme'] = {
                'primary_color': getattr(record, 'primary_color', '#1a2557'),
                'accent_color': getattr(record, 'accent_color', '#f37021'),
            }

        elif self.collection_name == 'registrations':
            d['student_email'] = record.lead_email
            d['checkin_time'] = getattr(record, 'checkin_time', None)
            d['ticket_id'] = getattr(record, 'ticket_id', None)
            if getattr(record, 'feedback_json', None):
                try:
                    d['feedback'] = json.loads(record.feedback_json)
                except Exception:
                    d['feedback'] = None
            else:
                d['feedback'] = None
            # Retrieve nested team members
            # Each member row keeps the dict it was written from (BLK-06), so
            # keys like role or per-member attendance survive; older rows fall
            # back to the columns.
            m_list = []
            for m in record.members:
                stored = _load_shadow(m)
                m_list.append(stored or {
                    'name': m.name,
                    'email': m.email,
                    'phone': m.phone,
                    'usn': m.usn,
                    'college': m.college,
                    'dept': m.department,
                })
            d['members'] = m_list

            # Retrieve nested scores
            s_dict = {}
            for s in record.scores:
                s_dict[s.judge_id] = _load_shadow(s) or {
                    'judge_name': s.judge_name,
                    'total': s.total,
                    'criteria': json.loads(s.criteria) if s.criteria else {},
                    'feedback': s.feedback,
                    'timestamp': s.scored_at.isoformat() if s.scored_at else None,
                }
            d['scores'] = s_dict

        elif self.collection_name == 'tickets':
            d['id'] = record.id
            d['ticket_id'] = record.id
            d['event_id'] = str(record.event_id)
            d['registration_id'] = str(record.registration_id)
            d['user_email'] = record.user_email
            d['ticket_type'] = record.ticket_type
            d['ticket_code'] = record.ticket_code
            d['qr_token_hash'] = record.qr_token_hash
            d['gate_assignment'] = record.gate_assignment
            d['seat_assignment'] = record.seat_assignment
            d['status'] = record.status
            d['checked_in'] = bool(record.checked_in_at or record.status == 'checked_in')
            d['checked_in_at'] = record.checked_in_at.isoformat() if record.checked_in_at else None
            d['created_at'] = record.created_at.isoformat() if record.created_at else None

        elif self.collection_name == 'event_forms':
            if record.fields_json:
                try:
                    loaded = json.loads(record.fields_json)
                    if isinstance(loaded, list):
                        d = {'fields': loaded, 'form_title': 'Registration Form', 'form_desc': ''}
                    elif isinstance(loaded, dict):
                        d = loaded
                        if 'fields' not in d:
                            d['fields'] = []
                except Exception:
                    d = {'fields': [], 'form_title': 'Registration Form', 'form_desc': ''}
            else:
                d = {'fields': [], 'form_title': 'Registration Form', 'form_desc': ''}

        elif self.collection_name == 'form_submissions':
            # The whole submission, answers nested as written (UPG-45)
            d = _submission_document(record.answers_json)
            d['event_id'] = str(record.event_id)
            d['registration_id'] = str(record.registration_id)
            if record.submitted_at and not d.get('submitted_at'):
                d['submitted_at'] = record.submitted_at.isoformat()

        elif self.collection_name == 'push_subscriptions':
            d['user_id'] = record.user_email
            d['subscription'] = {
                'endpoint': record.endpoint,
                'keys': {
                    'p256dh': record.p256dh,
                    'auth': record.auth_key
                }
            }
            d['updated_at'] = record.created_at.isoformat() if record.created_at else None

        if hasattr(record, 'extra_json'):
            self._merge_shadow(record, d)
        if self.collection_name == 'events':
            _derive_legacy_event_fields(d)
        return d

    def _merge_shadow(self, record, d):
        """Overlay the stored document onto the column values.

        The stored value wins when it is a richer form of the same data (e.g.
        role 'ClubSPOC' for enum SPOC, a prizes dict for its JSON string); if
        the column was changed some other way, the column value wins.
        """
        columns = record.__mapper__.columns
        for key, val in _load_shadow(record).items():
            attr = FIELD_MAP.get(key, key)
            col = columns.get(attr)
            if col is None:
                if key not in d:
                    d[key] = val
                continue
            current = getattr(record, attr)
            if val in (None, '') and current not in (None, ''):
                # An empty document value never hides a real column value
                # (e.g. category None -> enum default Technical)
                d[key] = _normalize_out(current)
                continue
            try:
                same = _normalize_out(self._convert_for_column(attr, col, val)) == _normalize_out(current)
            except Exception:
                same = False
            d[key] = val if same else _normalize_out(current)

    def _dict_to_new_record(self, data):
        """Build a new SQLAlchemy model record from a Firestore-styled dictionary."""
        kwargs = {}
        if self.collection_name == 'users':
            kwargs['id'] = self.id
            kwargs['email'] = self.id.lower()
            kwargs['name'] = safe_str(data.get('name', 'Unknown User'))
            kwargs['phone'] = safe_str(data.get('phone', ''))
            kwargs['role'] = self._get_enum_role(data.get('role', 'Participant'))
            kwargs['college'] = safe_str(data.get('college', ''))
            kwargs['department'] = safe_str(data.get('department', ''))
            kwargs['password_hash'] = safe_str(data.get('password') or data.get('passwordHash') or '')
            kwargs['is_active'] = bool(data.get('is_active', data.get('isActive', True)))
            kwargs['created_at'] = self._get_datetime(data.get('created_at', data.get('createdAt')))
            return User(**kwargs)

        elif self.collection_name == 'events':
            kwargs['id'] = to_uuid(self.id)
            kwargs['organization_id'] = safe_str(data.get('organization_id') or data.get('organizationId') or data.get('org_id') or '') or None
            kwargs['slug'] = safe_str(data.get('slug', '')) or None
            kwargs['title'] = safe_str(data.get('title', 'Untitled Event'))
            kwargs['description'] = safe_str(data.get('description') or data.get('overview') or '')
            kwargs['category'] = self._get_enum_category(data.get('category', 'Technical'))
            kwargs['event_type'] = safe_str(data.get('event_type') or data.get('eventType') or 'competition')
            kwargs['event_mode'] = safe_str(data.get('event_mode') or data.get('eventMode') or 'offline')
            kwargs['timezone'] = safe_str(data.get('timezone') or 'Asia/Kolkata')
            kwargs['date'] = self._get_date(data.get('date'))
            kwargs['deadline'] = self._get_date(data.get('deadline')) if data.get('deadline') else None
            kwargs['start_datetime'] = self._get_datetime(data.get('start_datetime') or data.get('startDatetime'))
            kwargs['end_datetime'] = self._get_datetime(data.get('end_datetime') or data.get('endDatetime'))
            kwargs['venue'] = safe_str(data.get('venue', 'Unknown Venue'))
            kwargs['status'] = self._get_enum_status(data.get('status', 'active'))
            kwargs['capacity'] = int(data.get('capacity') or data.get('max_participants') or 200)
            kwargs['pricing_type'] = safe_str(data.get('pricing_type') or data.get('pricingType') or 'free')
            kwargs['currency'] = safe_str(data.get('currency') or 'INR')
            kwargs['max_teams'] = data.get('max_teams', data.get('max_participants', 100))
            kwargs['min_team_size'] = data.get('min_team_size', data.get('team_min', 1))
            kwargs['max_team_size'] = data.get('max_team_size', data.get('team_max', 1))
            kwargs['fee'] = float(data.get('fee', data.get('entry_fee', 0.0)))
            kwargs['total_rounds'] = data.get('total_rounds', data.get('totalRounds', 1))
            kwargs['active_round'] = data.get('active_round', data.get('activeRound', 1))
            kwargs['poster_url'] = safe_str(data.get('poster_url') or data.get('banner_url') or '')
            kwargs['rules'] = safe_str(data.get('rules') or '')
            kwargs['prizes'] = safe_str(data.get('prizes') or '')
            kwargs['coordinator_id'] = data.get('coordinator_id') or data.get('created_by_email') or data.get('spoc_id')
            kwargs['spoc_id'] = safe_str(data.get('spoc_id') or '') or None
            kwargs['open_hall_mode'] = bool(data.get('open_hall_mode', False))
            kwargs['scoring_locked'] = bool(data.get('scoring_locked', False))
            kwargs['judging_criteria_json'] = json.dumps(data.get('judging_criteria', []))
            kwargs['staff_json'] = json.dumps(data.get('staff', []))
            kwargs['workflow_config_json'] = json.dumps(data.get('workflow_config')) if isinstance(data.get('workflow_config'), (dict, list)) else (safe_str(data.get('workflow_config_json') or data.get('workflowConfigJson') or '') or None)
            kwargs['evaluation_config_json'] = json.dumps(data.get('evaluation_config')) if isinstance(data.get('evaluation_config'), (dict, list)) else (safe_str(data.get('evaluation_config_json') or data.get('evaluationConfigJson') or '') or None)
            kwargs['ticket_tiers_json'] = json.dumps(data.get('ticket_tiers')) if isinstance(data.get('ticket_tiers'), (dict, list)) else (safe_str(data.get('ticket_tiers_json') or data.get('ticketTiersJson') or '') or None)
            kwargs['notification_rules_json'] = json.dumps(data.get('notification_rules')) if isinstance(data.get('notification_rules'), (dict, list)) else (safe_str(data.get('notification_rules_json') or data.get('notificationRulesJson') or '') or None)
            kwargs['org_unit_id'] = safe_str(data.get('org_unit_id') or data.get('orgUnitId') or '') or None
            kwargs['certificate_config_json'] = json.dumps(data.get('certificate_config')) if isinstance(data.get('certificate_config'), (dict, list)) else (safe_str(data.get('certificate_config_json') or data.get('certificateConfigJson') or '') or None)
            kwargs['registration_count'] = int(data.get('registration_count', 0) or 0)
            kwargs['created_at'] = self._get_datetime(data.get('created_at', data.get('createdAt')))
            return Event(**kwargs)

        elif self.collection_name == 'registrations':
            kwargs['id'] = to_uuid(self.id)
            kwargs['event_id'] = to_uuid(data.get('event_id'))
            kwargs['lead_name'] = safe_str(data.get('lead_name') or data.get('leadName', 'Unknown Lead'))
            kwargs['lead_email'] = safe_str(data.get('lead_email') or data.get('leadEmail', ''))
            kwargs['lead_phone'] = safe_str(data.get('lead_phone') or data.get('leadPhone') or data.get('phone', ''))
            kwargs['team_name'] = safe_str(data.get('team_name') or data.get('teamName') or '')
            kwargs['status'] = self._get_enum_reg_status(data.get('status', 'Confirmed'))
            kwargs['payment_status'] = self._get_enum_payment_status(data.get('payment_status') or data.get('paymentStatus', 'unpaid'))
            kwargs['payment_id'] = safe_str(data.get('payment_id') or data.get('paymentId') or '')
            kwargs['attendance'] = self._get_enum_attendance(data.get('attendance', 'Pending'))
            kwargs['current_round'] = data.get('current_round', data.get('currentRound', 1))
            kwargs['is_eliminated'] = bool(data.get('is_eliminated', data.get('isEliminated', False)))
            kwargs['qr_code_url'] = safe_str(data.get('qr_code_url') or data.get('qrCodeUrl') or '')
            kwargs['notes'] = safe_str(data.get('notes') or '')
            kwargs['assigned_judge_email'] = safe_str(data.get('assigned_judge_email') or '')
            kwargs['amount_paid'] = float(data.get('amount_paid', data.get('fee', 0.0)))
            kwargs['payment_mode'] = safe_str(data.get('payment_mode', ''))
            kwargs['assigned_room'] = safe_str(data.get('assigned_room', ''))
            kwargs['checkin_time'] = safe_str(data.get('checkin_time') or '') or None
            kwargs['ticket_id'] = safe_str(data.get('ticket_id') or '') or None
            kwargs['feedback_json'] = json.dumps(data.get('feedback')) if isinstance(data.get('feedback'), (dict, list)) else (safe_str(data.get('feedback_json') or '') or None)
            kwargs['created_at'] = self._get_datetime(data.get('registered_at') or data.get('createdAt'))
            return Registration(**kwargs)

        elif self.collection_name == 'event_forms':
            kwargs['event_id'] = to_uuid(self.id)
            kwargs['fields_json'] = json.dumps(data)
            kwargs['created_at'] = datetime.now(timezone.utc)
            return EventForm(**kwargs)

        elif self.collection_name == 'form_submissions':
            kwargs['id'] = to_uuid(self.id)
            kwargs['event_id'] = to_uuid(data.get('event_id'))
            kwargs['registration_id'] = to_uuid(data.get('registration_id') or data.get('reg_id') or data.get('regId'))
            kwargs['answers_json'] = json.dumps(data)
            kwargs['submitted_at'] = self._get_datetime(data.get('submitted_at', data.get('submittedAt')))
            return FormSubmission(**kwargs)

        elif self.collection_name == 'audit_log':
            kwargs['id'] = to_uuid(self.id)
            # utils.log_action writes the actor as 'user' (BLK-06)
            kwargs['actor_email'] = safe_str(data.get('actor_email') or data.get('actorEmail')
                                             or data.get('user') or 'system')
            kwargs['action'] = safe_str(data.get('action', 'unknown'))
            kwargs['target_id'] = safe_str(data.get('target_id') or data.get('targetId') or '')
            kwargs['detail'] = safe_str(data.get('detail') or data.get('details') or '')
            kwargs['created_at'] = self._get_datetime(data.get('created_at', data.get('createdAt')))
            return AuditLog(**kwargs)

        elif self.collection_name == 'push_subscriptions':
            kwargs['id'] = to_uuid(self.id)
            kwargs['user_email'] = safe_str(data.get('user_id', data.get('user_email', 'unknown')))
            sub = data.get('subscription', {})
            if isinstance(sub, str):
                try:
                    sub = json.loads(sub)
                except Exception:
                    sub = {}
            kwargs['endpoint'] = safe_str(sub.get('endpoint', data.get('endpoint', '')))
            keys = sub.get('keys', {})
            kwargs['p256dh'] = safe_str(keys.get('p256dh', data.get('p256dh', '')))
            kwargs['auth_key'] = safe_str(keys.get('auth', data.get('auth_key', '')))
            kwargs['created_at'] = self._get_datetime(data.get('updated_at', data.get('created_at', data.get('createdAt'))))
            return PushSubscription(**kwargs)

        elif self.collection_name == 'announcements':
            kwargs['id'] = to_uuid(self.id)
            kwargs['event_id'] = safe_str(data.get('event_id', ''))
            kwargs['event_title'] = safe_str(data.get('event_title', ''))
            kwargs['message'] = safe_str(data.get('message', ''))
            kwargs['priority'] = safe_str(data.get('priority', 'info'))
            kwargs['spoc_email'] = safe_str(data.get('spoc_email', ''))
            kwargs['timestamp'] = safe_str(data.get('timestamp', ''))
            return Announcement(**kwargs)

        elif self.collection_name == 'organizations':
            kwargs['id'] = str(self.id)
            kwargs['name'] = safe_str(data.get('name', 'Unnamed Organization'))
            kwargs['slug'] = safe_str(data.get('slug', str(self.id)).lower().strip())
            kwargs['domain'] = safe_str(data.get('domain', ''))
            kwargs['plan'] = safe_str(data.get('plan', 'free'))
            kwargs['logo_url'] = safe_str(data.get('logo_url', ''))
            kwargs['favicon_url'] = safe_str(data.get('favicon_url', ''))
            theme = data.get('theme', {})
            kwargs['primary_color'] = safe_str(theme.get('primary_color', data.get('primary_color', '#1a2557')))
            kwargs['accent_color'] = safe_str(theme.get('accent_color', data.get('accent_color', '#f37021')))
            kwargs['custom_domain'] = data.get('custom_domain')
            # Unique column: an organisation without a key stores NULL, not '' (BLK-06)
            kwargs['api_key'] = safe_str(data.get('api_key') or '') or None
            kwargs['owner_email'] = safe_str(data.get('owner_email', ''))
            kwargs['is_active'] = bool(data.get('is_active', True))
            kwargs['settings_json'] = json.dumps(data.get('settings', {})) if isinstance(data.get('settings'), dict) else safe_str(data.get('settings_json', ''))
            kwargs['created_at'] = self._get_datetime(data.get('created_at'))
            kwargs['updated_at'] = self._get_datetime(data.get('updated_at'))
            return Organization(**kwargs)

        elif self.collection_name == 'tickets':
            kwargs['id'] = str(self.id)
            kwargs['event_id'] = to_uuid(data.get('event_id'))
            kwargs['registration_id'] = to_uuid(data.get('registration_id'))
            kwargs['user_email'] = safe_str(data.get('user_email', ''))
            kwargs['ticket_type'] = safe_str(data.get('ticket_type', 'General'))
            kwargs['ticket_code'] = safe_str(data.get('ticket_code', f"TKT-{uuid.uuid4().hex[:8].upper()}"))
            kwargs['qr_token_hash'] = safe_str(data.get('qr_token_hash', ''))
            kwargs['gate_assignment'] = safe_str(data.get('gate_assignment', ''))
            kwargs['seat_assignment'] = safe_str(data.get('seat_assignment', ''))
            kwargs['status'] = safe_str(data.get('status', 'active'))
            # A new ticket isn't checked in: no value stays NULL, not "now" (BLK-06)
            kwargs['checked_in_at'] = self._get_datetime(data['checked_in_at']) if data.get('checked_in_at') else None
            kwargs['created_at'] = self._get_datetime(data.get('created_at'))
            return Ticket(**kwargs)

        elif self.collection_name == 'event_sessions':
            kwargs['id'] = str(self.id)
            kwargs['event_id'] = to_uuid(data.get('event_id'))
            kwargs['track_name'] = safe_str(data.get('track_name', 'Main Track'))
            kwargs['title'] = safe_str(data.get('title', 'Untitled Session'))
            kwargs['speaker_name'] = safe_str(data.get('speaker_name', ''))
            kwargs['speaker_bio'] = safe_str(data.get('speaker_bio', ''))
            kwargs['room_number'] = safe_str(data.get('room_number', ''))
            kwargs['start_time'] = self._get_datetime(data.get('start_time'))
            kwargs['end_time'] = self._get_datetime(data.get('end_time'))
            kwargs['capacity'] = int(data.get('capacity', 100) or 100)
            kwargs['created_at'] = self._get_datetime(data.get('created_at'))
            return EventSession(**kwargs)

        elif self.collection_name == 'project_submissions':
            kwargs['id'] = to_uuid(self.id)
            kwargs['event_id'] = to_uuid(data.get('event_id'))
            kwargs['registration_id'] = to_uuid(data.get('registration_id'))
            kwargs['team_name'] = safe_str(data.get('team_name', 'Team'))
            kwargs['project_title'] = safe_str(data.get('project_title') or data.get('project_name', 'Project'))
            kwargs['tagline'] = safe_str(data.get('tagline', ''))
            kwargs['problem_statement'] = safe_str(data.get('problem_statement', ''))
            kwargs['solution_overview'] = safe_str(data.get('solution_overview', ''))
            kwargs['tech_stack'] = safe_str(data.get('tech_stack', ''))
            kwargs['github_url'] = safe_str(data.get('github_url', ''))
            kwargs['demo_url'] = safe_str(data.get('demo_url', ''))
            kwargs['video_url'] = safe_str(data.get('video_url', ''))
            kwargs['slide_deck_url'] = safe_str(data.get('slide_deck_url', ''))
            kwargs['milestone_stage'] = safe_str(data.get('milestone_stage', 'Ideation'))
            kwargs['submitted_at'] = self._get_datetime(data.get('submitted_at'))
            return ProjectSubmission(**kwargs)

        elif self.collection_name == 'org_units':
            kwargs['id'] = str(self.id)
            kwargs['organization_id'] = safe_str(data.get('organization_id') or data.get('organizationId') or 'default')
            kwargs['parent_id'] = safe_str(data.get('parent_id') or data.get('parentId')) or None
            kwargs['type'] = safe_str(data.get('type', 'department'))
            kwargs['name'] = safe_str(data.get('name', 'Unnamed Unit'))
            kwargs['slug'] = safe_str(data.get('slug', str(self.id)).lower().strip())
            kwargs['created_at'] = self._get_datetime(data.get('created_at'))
            kwargs['updated_at'] = self._get_datetime(data.get('updated_at'))
            return OrgUnit(**kwargs)

        elif self.collection_name == 'role_assignments':
            kwargs['id'] = str(self.id)
            kwargs['user_id'] = safe_str(data.get('user_id') or data.get('userId', '')).lower().strip()
            kwargs['role'] = safe_str(data.get('role', 'Participant'))
            kwargs['scope_type'] = safe_str(data.get('scope_type') or data.get('scopeType', 'university'))
            kwargs['scope_id'] = safe_str(data.get('scope_id') or data.get('scopeId')) or None
            kwargs['created_at'] = self._get_datetime(data.get('created_at'))
            return RoleAssignment(**kwargs)

        elif self.collection_name == 'campuses':
            kwargs['id'] = str(self.id)
            kwargs['organization_id'] = safe_str(data.get('organization_id') or data.get('organizationId', 'default'))
            kwargs['name'] = safe_str(data.get('name', 'Main Campus'))
            kwargs['slug'] = safe_str(data.get('slug', str(self.id)).lower().strip())
            kwargs['address'] = safe_str(data.get('address', ''))
            kwargs['created_at'] = self._get_datetime(data.get('created_at'))
            kwargs['updated_at'] = self._get_datetime(data.get('updated_at'))
            return Campus(**kwargs)

        elif self.collection_name == 'buildings':
            kwargs['id'] = str(self.id)
            kwargs['campus_id'] = safe_str(data.get('campus_id') or data.get('campusId', ''))
            kwargs['name'] = safe_str(data.get('name', 'Building'))
            kwargs['code'] = safe_str(data.get('code', ''))
            kwargs['created_at'] = self._get_datetime(data.get('created_at'))
            kwargs['updated_at'] = self._get_datetime(data.get('updated_at'))
            return Building(**kwargs)

        elif self.collection_name == 'rooms':
            kwargs['id'] = str(self.id)
            kwargs['building_id'] = safe_str(data.get('building_id') or data.get('buildingId', ''))
            kwargs['name'] = safe_str(data.get('name', 'Room'))
            kwargs['room_number'] = safe_str(data.get('room_number') or data.get('roomNumber', ''))
            kwargs['capacity'] = int(data.get('capacity', 50) or 50)
            kwargs['type'] = safe_str(data.get('type', 'classroom'))
            fac = data.get('facilities', data.get('facilities_json', []))
            kwargs['facilities_json'] = json.dumps(fac) if isinstance(fac, (dict, list)) else safe_str(fac)
            kwargs['created_at'] = self._get_datetime(data.get('created_at'))
            kwargs['updated_at'] = self._get_datetime(data.get('updated_at'))
            return Room(**kwargs)

        elif self.collection_name == 'venue_bookings':
            kwargs['id'] = str(self.id)
            kwargs['room_id'] = safe_str(data.get('room_id') or data.get('roomId', ''))
            kwargs['event_id'] = to_uuid(data.get('event_id') or data.get('eventId'))
            kwargs['session_id'] = safe_str(data.get('session_id') or data.get('sessionId')) or None
            kwargs['start_time'] = self._get_datetime(data.get('start_time') or data.get('startTime'))
            kwargs['end_time'] = self._get_datetime(data.get('end_time') or data.get('endTime'))
            kwargs['status'] = safe_str(data.get('status', 'confirmed'))
            kwargs['notes'] = safe_str(data.get('notes', ''))
            kwargs['created_at'] = self._get_datetime(data.get('created_at'))
            kwargs['updated_at'] = self._get_datetime(data.get('updated_at'))
            return VenueBooking(**kwargs)

        return None


    def _convert_for_column(self, mapped_key, col, val):
        """Convert a document value to the Python type stored in column `mapped_key`."""
        # Only users.role is an enum; role_assignments.role is a free string (scoped RBAC)
        if mapped_key == 'role' and self.collection_name == 'users':
            return self._get_enum_role(val)
        if mapped_key == 'category':
            return self._get_enum_category(val)
        if mapped_key == 'status' and self.collection_name == 'events':
            return self._get_enum_status(val)
        if mapped_key == 'status' and self.collection_name == 'registrations':
            return self._get_enum_reg_status(val)
        if mapped_key == 'payment_status':
            return self._get_enum_payment_status(val)
        if mapped_key == 'attendance':
            return self._get_enum_attendance(val)

        if mapped_key == 'api_key' and self.collection_name == 'organizations':
            return safe_str(val or '') or None
        if mapped_key == 'spoc_id' and self.collection_name == 'events':
            return safe_str(val or '') or None

        type_name = col.type.__class__.__name__
        if mapped_key in ('created_at', 'updated_at', 'submitted_at', 'checked_in_at', 'start_time', 'end_time') or 'DateTime' in type_name:
            if not val and col.nullable:
                return None  # parse_datetime would invent "now" (BLK-06)
            return self._get_datetime(val)
        if mapped_key in ('date', 'deadline'):
            return self._get_date(val)
        if type_name in ('UUID', 'PgUUID'):
            return to_uuid(val) if val else val
        if 'Integer' in type_name:
            try:
                return int(val)
            except (ValueError, TypeError):
                return val
        if isinstance(val, (dict, list)):
            return safe_str(val)
        return val

    def _update_record_fields(self, record, data, session):
        """Update fields on an existing record based on Firestore inputs."""
        if self.collection_name == 'form_submissions':
            # Keep the whole submission (who, when, answers) in its JSON
            # column, not only the answers (UPG-45)
            stored = _submission_document(record.answers_json)
            stored.update({k: v for k, v in data.items() if k not in ('id', 'answersJson', 'answers_json')})
            record.answers_json = json.dumps(stored, default=str)
            data = {k: v for k, v in data.items() if FIELD_MAP.get(k, k) != 'answers_json'}
        for key, val in data.items():
            # Translate keys
            mapped_key = FIELD_MAP.get(key, key)
            if mapped_key == 'id':
                continue  # never rewrite the primary key from document data
            if hasattr(record, mapped_key):
                col_prop = record.__mapper__.column_attrs.get(mapped_key)
                col = col_prop.columns[0] if col_prop is not None else record.__mapper__.columns.get(mapped_key)
                if col is not None:
                    val = self._convert_for_column(mapped_key, col, val)
                    setattr(record, mapped_key, val)

            # Specific column assignments
            if self.collection_name == 'users' and key == 'password':
                record.password_hash = safe_str(val)

            elif self.collection_name == 'events':
                if key == 'open_hall_mode':
                    record.open_hall_mode = bool(val)
                elif key == 'scoring_locked':
                    record.scoring_locked = bool(val)
                elif key == 'judging_criteria':
                    record.judging_criteria_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key == 'staff':
                    record.staff_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key == 'overview':
                    record.description = safe_str(val)
                elif key in ('workflow_config', 'workflow_config_json', 'workflowConfigJson'):
                    record.workflow_config_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key in ('evaluation_config', 'evaluation_config_json', 'evaluationConfigJson'):
                    record.evaluation_config_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key in ('ticket_tiers', 'ticket_tiers_json', 'ticketTiersJson'):
                    record.ticket_tiers_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key in ('notification_rules', 'notification_rules_json', 'notificationRulesJson'):
                    record.notification_rules_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key in ('event_type', 'eventType'):
                    record.event_type = safe_str(val)
                elif key in ('pricing_type', 'pricingType'):
                    record.pricing_type = safe_str(val)
                elif key == 'capacity':
                    try:
                        record.capacity = int(val)
                    except (ValueError, TypeError):
                        pass
                elif key in ('org_unit_id', 'orgUnitId'):
                    record.org_unit_id = safe_str(val) or None
                elif key == 'visibility':
                    record.visibility = safe_str(val) or 'Public'
                elif key in ('certificate_config', 'certificate_config_json', 'certificateConfigJson'):
                    record.certificate_config_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)

            elif self.collection_name == 'registrations':
                if key in ('feedback', 'feedback_json'):
                    record.feedback_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key == 'checkin_time':
                    record.checkin_time = safe_str(val)
                elif key == 'ticket_id':
                    record.ticket_id = safe_str(val)

        # Handle nested relations for registrations
        if self.collection_name == 'registrations':
            reg_id = to_uuid(self.id)
            if 'members' in data:
                # Re-sync members
                session.query(TeamMember).filter_by(registration_id=reg_id).delete()
                for idx, m in enumerate(data['members']):
                    if isinstance(m, dict):
                        member = TeamMember(
                            id=uuid.uuid5(uuid.NAMESPACE_DNS, f"{self.id}_member_{idx}"),
                            registration_id=reg_id,
                            name=safe_str(m.get('name', 'Unknown')),
                            email=safe_str(m.get('email', '')),
                            phone=safe_str(m.get('phone', '')),
                            usn=safe_str(m.get('usn', '')),
                            college=safe_str(m.get('college', '')),
                            department=safe_str(m.get('dept') or m.get('department') or ''),
                            extra_json=json.dumps(m, cls=CustomJSONEncoder),
                        )
                        session.add(member)

            if 'scores' in data and isinstance(data['scores'], dict):
                # Update specific judges scores
                for judge_id, s_data in data['scores'].items():
                    if isinstance(s_data, dict):
                        existing_score = session.query(Score).filter_by(registration_id=reg_id, judge_id=judge_id).first()
                        criteria_data = s_data.get('criteria') or s_data.get('details') or {}
                        total_val = float(s_data.get('total', 0.0))

                        if not existing_score:
                            score = Score(
                                registration_id=reg_id,
                                judge_id=judge_id,
                                judge_name=safe_str(s_data.get('judge_name', '')),
                                round=s_data.get('round', record.current_round),
                                total=total_val,
                                criteria=json.dumps(criteria_data),
                                feedback=safe_str(s_data.get('remarks') or s_data.get('feedback') or ''),
                                scored_at=self._get_datetime(s_data.get('timestamp') or s_data.get('submitted_at')),
                                extra_json=json.dumps(s_data, cls=CustomJSONEncoder),
                            )
                            session.add(score)
                        else:
                            existing_score.total = total_val
                            existing_score.criteria = json.dumps(criteria_data)
                            existing_score.feedback = safe_str(s_data.get('remarks') or s_data.get('feedback') or '')
                            existing_score.scored_at = self._get_datetime(s_data.get('timestamp') or s_data.get('submitted_at'))
                            existing_score.extra_json = json.dumps(s_data, cls=CustomJSONEncoder)

            elif self.collection_name == 'push_subscriptions':
                if key == 'subscription' and isinstance(val, dict):
                    record.endpoint = val.get('endpoint', '')
                    keys = val.get('keys', {})
                    record.p256dh = keys.get('p256dh', '')
                    record.auth_key = keys.get('auth', '')

    # Type Resolvers
    def _get_datetime(self, val):
        return parse_datetime(val)

    def _get_date(self, val):
        return parse_date(val)

    # Enum columns: the same mapping queries use (_canonical_enum_value), so a
    # value is stored under the member a filter will look for; values with no
    # member fall back to a default and are matched on the document (BLK-06).
    @staticmethod
    def _to_member(enum_cls, val, default):
        member = _canonical_enum_value(enum_cls, val)
        return member if isinstance(member, enum_cls) else default

    def _get_enum_role(self, val):
        return self._to_member(UserRole, val, UserRole.Participant)

    def _get_enum_category(self, val):
        return self._to_member(EventCategory, val, EventCategory.Technical)

    def _get_enum_status(self, val):
        return self._to_member(EventStatus, val, EventStatus.active)

    def _get_enum_reg_status(self, val):
        return self._to_member(RegistrationStatus, val, RegistrationStatus.confirmed)

    def _get_enum_payment_status(self, val):
        return self._to_member(PaymentStatus, val, PaymentStatus.unpaid)

    def _get_enum_attendance(self, val):
        return self._to_member(AttendanceStatus, val, AttendanceStatus.Pending)


_NO_SQL = object()


def _cast_filter_value(col_attr, val):
    """Cast a filter value for SQL. Returns (value, exact).

    `exact` is False when the SQL comparison can only narrow the result (an
    enum column queried with a value that has no member); the caller then
    re-checks the stored document value. `_NO_SQL` means skip the SQL clause.
    """
    enum_cls = getattr(getattr(col_attr, 'type', None), 'enum_class', None)
    if enum_cls is None:
        return _cast_value(col_attr, val), True
    aliases = ENUM_ALIASES.get(enum_cls, {})

    def one(v):
        if isinstance(v, enum_cls):
            return v, True
        key = str(v).strip().lower()
        if key in aliases:
            return aliases[key], True
        for member in enum_cls:
            if member.name.lower() == key or str(member.value).lower() == key:
                return member, True
        return None, False

    if isinstance(val, (list, tuple, set)):
        pairs = [one(v) for v in val]
        members = [m for m, _ in pairs if m is not None]
        return members, all(ok for _, ok in pairs)
    member, ok = one(val)
    return (member if ok else _NO_SQL), ok


def _cast_value(col_attr, val):
    if val is None:
        return None
    if hasattr(col_attr, 'type') and col_attr.type is not None:
        type_name = col_attr.type.__class__.__name__
        if 'UUID' in type_name:
            if isinstance(val, (list, tuple)):
                return [to_uuid(v) for v in val]
            return to_uuid(val)
        elif 'Enum' in type_name and hasattr(col_attr.type, 'enum_class'):
            enum_cls = col_attr.type.enum_class
            if isinstance(val, str):
                for member in enum_cls:
                    if member.name.lower() == val.strip().lower() or member.value.lower() == val.strip().lower():
                        return member
                return val
        elif 'Date' in type_name and 'DateTime' not in type_name:
            if isinstance(val, str):
                parsed = parse_date(val)
                if parsed:
                    return parsed
            elif isinstance(val, datetime):
                return val.date()
        elif 'DateTime' in type_name:
            if isinstance(val, str):
                parsed = parse_datetime(val)
                if parsed:
                    return parsed
    return val


def _canonical_enum_value(enum_cls, val):
    """An enum-backed document value in comparable form.

    Explicit aliases (e.g. Coordinator/EventCoordinator, Student/Participant,
    any case) map to the same member; anything else compares as lower-case
    text, so 'UniversityAdmin' never equals the 'Participant' fallback.
    """
    if isinstance(val, enum_cls):
        return val
    key = str(val).strip().lower()
    aliases = ENUM_ALIASES.get(enum_cls, {})
    if key in aliases:
        return aliases[key]
    for member in enum_cls:
        if member.name.lower() == key or str(member.value).lower() == key:
            return member
    return key


def _enum_match(enum_cls, doc_val, op, val):
    if doc_val is None:
        return _py_match(doc_val, op, val)
    doc = _canonical_enum_value(enum_cls, doc_val)
    if op == '==':
        return doc == _canonical_enum_value(enum_cls, val)
    if op == '!=':
        return doc != _canonical_enum_value(enum_cls, val)
    if op in ('in', 'not-in', 'not_in'):
        wanted = {_canonical_enum_value(enum_cls, v) for v in (val or [])}
        return (doc in wanted) == (op == 'in')
    return _py_match(doc_val, op, val)


class SQLQuery:
    """Mock Query builder translating filters to SQLAlchemy query objects."""
    def __init__(self, collection):
        self.collection = collection
        self.filters = []
        self.orders = []
        self._limit = None
        self._offset = 0

    def where(self, field=None, op=None, value=None, filter=None):
        if filter is not None:
            # Handles FieldFilter objects
            f_path = getattr(filter, 'field_path', None) or getattr(filter, 'field', None)
            f_op = getattr(filter, 'op_string', None) or getattr(filter, 'op', None) or getattr(filter, 'operator', None)
            # google FieldFilter exposes `.value`; the local fallback stub uses `.val`
            f_val = filter.value if hasattr(filter, 'value') else getattr(filter, 'val', None)
            self.filters.append((f_path, f_op, f_val))
        else:
            self.filters.append((field, op, value))
        return self

    def order_by(self, field, direction=None):
        self.orders.append((field, direction))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def offset(self, n):
        """Skip the first n results (pagination, UPG-19). Pushed into SQL with
        the limit when every filter and order is a plain column."""
        self._offset = max(int(n or 0), 0)
        return self

    def count(self):
        """How many documents match: one SQL COUNT when every filter is a plain
        column, else by loading the matches."""
        model = self.collection.model
        pushable = (model is not None and self.collection.id not in PURE_FIRESTORE_COLLECTIONS
                    and not self.filters)
        if pushable:
            from sqlalchemy import func, select
            with get_session() as session:
                return int(session.execute(select(func.count()).select_from(model)).scalar() or 0)
        saved = (self._limit, self._offset)
        self._limit, self._offset = None, 0
        try:
            return sum(1 for _ in self.stream())
        finally:
            self._limit, self._offset = saved

    def stream(self):
        model = self.collection.model
        if self.collection.id in PURE_FIRESTORE_COLLECTIONS or not model:
            docs = list(_query_native_docs(self.collection.id, filters=self.filters, orders=self.orders))
            end = None if self._limit is None else self._offset + self._limit
            return iter(docs[self._offset:end])

        column_keys = {prop.key for prop in model.__mapper__.column_attrs} - {'extra_json'}
        sql_ops = {'==', '!=', '>', '<', '>=', '<=', 'in'}
        py_filters = []   # evaluated on the full document after loading
        enum_filters = []  # enum-backed fields: always compared on the real value
        with get_session() as session:
            query = session.query(model)

            for field, op, val in self.filters:
                mapped_field = FIELD_MAP.get(field, field)
                if mapped_field not in column_keys or op not in sql_ops:
                    py_filters.append((field, op, val))
                    continue
                col_attr = getattr(model, mapped_field)
                enum_cls = getattr(getattr(col_attr, 'type', None), 'enum_class', None)
                if enum_cls is not None:
                    # The column holds a coarse value: unknown document values
                    # (e.g. 'evaluation', 'UniversityAdmin', 'NSS') fall back to a
                    # default member. So SQL only narrows where that can't drop a
                    # match, and the stored document value decides (BLK-06).
                    enum_filters.append((field, mapped_field, enum_cls, op, val))
                    wanted = [_canonical_enum_value(enum_cls, v)
                              for v in (val if op == 'in' else [val])]
                    if op in ('==', 'in') and all(isinstance(w, enum_cls) for w in wanted):
                        query = query.filter(col_attr.in_(wanted))
                    continue
                casted_val, exact = _cast_filter_value(col_attr, val)
                if not exact:
                    # e.g. category 'Workshop' has no enum member: narrow in SQL
                    # where possible, then match the stored value exactly
                    py_filters.append((field, op, val))
                    if casted_val is _NO_SQL:
                        continue

                if op == '==':
                    query = query.filter(col_attr == casted_val)
                elif op == '!=':
                    query = query.filter(col_attr != casted_val)
                elif op == '>':
                    query = query.filter(col_attr > casted_val)
                elif op == '<':
                    query = query.filter(col_attr < casted_val)
                elif op == '>=':
                    query = query.filter(col_attr >= casted_val)
                elif op == '<=':
                    query = query.filter(col_attr <= casted_val)
                elif op == 'in':
                    query = query.filter(col_attr.in_(casted_val or []))

            sql_sortable = all(FIELD_MAP.get(f, f) in column_keys for f, _ in self.orders)
            if sql_sortable:
                for field, direction in self.orders:
                    col_attr = getattr(model, FIELD_MAP.get(field, field))
                    if direction == 'DESCENDING' or str(direction).lower() == 'desc':
                        query = query.order_by(col_attr.desc())
                    else:
                        query = query.order_by(col_attr.asc())

            pushed = not py_filters and not enum_filters and sql_sortable
            if pushed and self._offset:
                query = query.offset(self._offset)
            if self._limit is not None and pushed:
                query = query.limit(self._limit)

            snapshots = []
            for record in query.all():
                doc_id = str(record.id) if hasattr(record, 'id') else ''
                ref = SQLDocumentReference(self.collection.id, doc_id)
                data = ref._record_to_dict(record, session)
                snapshots.append(SQLDocumentSnapshot(doc_id, data, exists=True,
                                                     collection_name=self.collection.id))

        if py_filters:
            snapshots = [s for s in snapshots
                         if all(_py_match(s._data.get(f), op, v) for f, op, v in py_filters)]
        if enum_filters:
            snapshots = [s for s in snapshots
                         if all(_enum_match(cls, s._data.get(f, s._data.get(mf)), op, v)
                                for f, mf, cls, op, v in enum_filters)]
        if not sql_sortable:
            snapshots = _sort_snapshots(snapshots, self.orders)
        if not pushed and self._offset:
            snapshots = snapshots[self._offset:]
        if self._limit is not None:
            snapshots = snapshots[:self._limit]
        return iter(snapshots)


class SQLCollectionReference:
    """Mock CollectionReference mimicking Firestore."""
    def __init__(self, collection_name):
        self.id = collection_name
        self.model = COLLECTION_MAP.get(collection_name)

    def document(self, doc_id=None) -> SQLDocumentReference:
        if not doc_id:
            # Generate a new UUID string
            doc_id = str(uuid.uuid4())
        return SQLDocumentReference(self.id, doc_id)

    def add(self, data):
        new_id = str(uuid.uuid4())
        doc_ref = self.document(new_id)
        doc_ref.set(data, merge=False)
        return (None, doc_ref)

    def where(self, field=None, op=None, value=None, filter=None) -> SQLQuery:
        q = SQLQuery(self)
        return q.where(field, op, value, filter)

    def order_by(self, field, direction=None) -> SQLQuery:
        q = SQLQuery(self)
        return q.order_by(field, direction)

    def limit(self, n) -> SQLQuery:
        q = SQLQuery(self)
        return q.limit(n)

    def offset(self, n) -> SQLQuery:
        return SQLQuery(self).offset(n)

    def count(self) -> int:
        return SQLQuery(self).count()

    def stream(self):
        q = SQLQuery(self)
        return q.stream()


class SQLBatch:
    """Mock WriteBatch mimicking Firestore."""
    def __init__(self):
        self._ops = []

    def set(self, ref, data):
        self._ops.append(('set', ref, data))

    def update(self, ref, data):
        self._ops.append(('update', ref, data))

    def delete(self, ref):
        self._ops.append(('delete', ref, None))

    def commit(self):
        # Execute operations in a single database transaction
        for op, ref, data in self._ops:
            if op == 'set':
                ref.set(data, merge=True)
            elif op == 'update':
                ref.update(data)
            elif op == 'delete':
                ref.delete()
        self._ops.clear()


class SQLFirestoreAdapter:
    """Mock Firestore client providing complete adapter interfaces to SQLAlchemy."""
    def __init__(self):
        from db_pg import _is_production, init_db, require_schema_at_head, DatabaseConfigError
        if _is_production():
            # Production never issues CREATE or ALTER at start-up: migrations
            # build the schema, and start-up refuses a database not at head (UPG-16).
            require_schema_at_head()
        else:
            # Development: create missing tables and align columns on start.
            try:
                init_db()
            except DatabaseConfigError:
                raise
            except Exception as exc:
                logger.info("Database table init note: %s", exc)
            try:
                verify_and_align_schema()
            except Exception as exc:
                logger.info("Schema alignment note: %s", exc)
        try:
            self._ensure_root_units()
        except Exception as exc:
            logger.info("Root org unit note: %s", exc)

    def _ensure_root_units(self):
        """Create the 'default' organization and 'central' org unit if missing.

        New events default to org_unit_id='central' (routes_spoc.create_event), and
        events.orgUnitId / org_units.organizationId are foreign keys, so these rows
        must exist before the first event is created.

        Safe when several server processes start at once and on every restart:
        both rows are inserted with INSERT ... ON CONFLICT DO NOTHING in one
        transaction, so a concurrent or repeated start-up is a no-op and existing
        rows (e.g. an organization renamed by an admin) are never overwritten.
        """
        import secrets as _secrets
        now = datetime.now(timezone.utc)
        org_row = {
            'id': 'default', 'name': 'Sapthagiri NPS University', 'slug': 'default',
            'plan': 'free', 'is_active': True, 'created_at': now, 'updated_at': now,
            # organizations.apiKey is unique; don't take the '' slot other orgs default to
            'api_key': 'sk_default_' + _secrets.token_hex(16),
        }
        unit_row = {
            'id': 'central', 'organization_id': 'default', 'parent_id': None,
            'type': 'central', 'name': 'Central Administration', 'slug': 'central',
            'created_at': now, 'updated_at': now,
        }
        dialect = _db_dialect_name()
        if dialect == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert as _insert
        elif dialect == 'sqlite':
            from sqlalchemy.dialects.sqlite import insert as _insert
        else:
            _insert = None

        with get_session() as session:
            if _insert is not None:
                session.execute(_insert(Organization).values(**org_row).on_conflict_do_nothing())
                session.execute(_insert(OrgUnit).values(**unit_row).on_conflict_do_nothing())
            else:  # other databases: best effort, a concurrent duplicate raises and is logged
                if not session.get(Organization, 'default'):
                    session.add(Organization(**org_row))
                    session.flush()
                if not session.get(OrgUnit, 'central'):
                    session.add(OrgUnit(**unit_row))
            session.commit()

    def collection(self, name) -> SQLCollectionReference:
        return SQLCollectionReference(name)

    def document(self, path) -> SQLDocumentReference:
        parts = path.split('/')
        if len(parts) >= 2:
            return SQLDocumentReference(parts[0], parts[1])
        raise ValueError(f"Invalid document path: {path}")

    def batch(self) -> SQLBatch:
        return SQLBatch()


# ── Parsing Helpers ─────────────────────────────────────────────────────────

def parse_date(val) -> date:
    if not val:
        return date.today()
    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()
    try:
        if hasattr(val, 'date'):
            return val.date()
        dt = date_parser.parse(str(val))
        return dt.date()
    except Exception:
        return date.today()


def parse_datetime(val) -> datetime:
    if not val:
        return datetime.now(timezone.utc)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val
    try:
        if hasattr(val, 'to_dict'):
            return val
        dt = date_parser.parse(str(val))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)
