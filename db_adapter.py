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
    Organization, Ticket, EventSession,
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
}

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
    'event_type': 'event_type',
    'eventType': 'event_type',
    'event_mode': 'event_mode',
    'eventMode': 'event_mode',
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
    ]
    cols_registrations = [
        ('assigned_judge_email', 'VARCHAR(255)'),
        ('amount_paid', 'DOUBLE PRECISION'),
        ('payment_mode', 'VARCHAR(100)'),
        ('assigned_room', 'VARCHAR(100)')
    ]
    
    if not engine:
        return
    is_sqlite = engine.url.drivername.startswith('sqlite')
    if is_sqlite:
        return
        
    try:
        with engine.connect() as conn:
            # Events alignment
            for col, col_type in cols_events:
                res = conn.execute(text(f"""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='events' AND column_name='{col}'
                """)).fetchone()
                if not res:
                    logger.info("Aligning Schema: Adding column '%s' to 'events'...", col)
                    conn.execute(text(f"ALTER TABLE events ADD COLUMN {col} {col_type}"))
            
            # Registrations alignment
            for col, col_type in cols_registrations:
                res = conn.execute(text(f"""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='registrations' AND column_name='{col}'
                """)).fetchone()
                if not res:
                    logger.info("Aligning Schema: Adding column '%s' to 'registrations'...", col)
                    conn.execute(text(f"ALTER TABLE registrations ADD COLUMN {col} {col_type}"))
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
        return super().default(o)

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
        existing.update(final_data)
        final_data = existing

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

def _query_native_docs(collection_name, filters=None, limit=None):
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
        match = True
        if filters:
            for field, op, val in filters:
                doc_val = data.get(field)
                if op == '==' and doc_val != val:
                    match = False; break
                elif op == '!=' and doc_val == val:
                    match = False; break
                elif op == '>' and (doc_val is None or doc_val <= val):
                    match = False; break
                elif op == '<' and (doc_val is None or doc_val >= val):
                    match = False; break
                elif op == '>=' and (doc_val is None or doc_val < val):
                    match = False; break
                elif op == '<=' and (doc_val is None or doc_val > val):
                    match = False; break
                elif op == 'in' and (doc_val not in val if val else True):
                    match = False; break
        if match:
            results.append(SQLDocumentSnapshot(doc_id, data.copy(), exists=True))

    if limit is not None:
        results = results[:limit]
    return iter(results)


# ── Mock Classes Mimicking Firestore ─────────────────────────────────────────

class SQLDocumentSnapshot:
    """Mock DocumentSnapshot mimicking Firestore."""
    def __init__(self, doc_id, data, exists=True):
        self.id = doc_id
        self.exists = exists
        self._data = data or {}

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

    def get(self):
        if self.collection_name in PURE_FIRESTORE_COLLECTIONS:
            doc_data = _get_native_doc(self.collection_name, self.id)
            if doc_data is None:
                return SQLDocumentSnapshot(self.id, None, exists=False)
            return SQLDocumentSnapshot(self.id, doc_data, exists=True)

        if not self.model_class:
            doc_data = _get_native_doc(self.collection_name, self.id)
            if doc_data is None:
                return SQLDocumentSnapshot(self.id, None, exists=False)
            return SQLDocumentSnapshot(self.id, doc_data, exists=True)

        with get_session() as session:
            # Map search primary key
            if self.collection_name in ('users', 'organizations', 'tickets', 'event_sessions'):
                record = session.query(self.model_class).filter_by(id=str(self.id)).first()
            elif self.collection_name == 'event_forms':
                record = session.query(self.model_class).filter_by(event_id=to_uuid(self.id)).first()
            else:
                record = session.query(self.model_class).filter_by(id=to_uuid(self.id)).first()

            if not record:
                return SQLDocumentSnapshot(self.id, None, exists=False)

            data = self._record_to_dict(record, session)
            return SQLDocumentSnapshot(self.id, data, exists=True)

    def set(self, data, merge=True):
        if self.collection_name in PURE_FIRESTORE_COLLECTIONS:
            _set_native_doc(self.collection_name, self.id, data, merge=merge)
            return

        if not self.model_class:
            _set_native_doc(self.collection_name, self.id, data, merge=merge)
            return

        with get_session() as session:
            if self.collection_name in ('users', 'organizations', 'tickets', 'event_sessions'):
                record = session.query(self.model_class).filter_by(id=str(self.id)).first()
            elif self.collection_name == 'event_forms':
                record = session.query(self.model_class).filter_by(event_id=to_uuid(self.id)).first()
            else:
                record = session.query(self.model_class).filter_by(id=to_uuid(self.id)).first()

            if not record:
                # Insert path
                record = self._dict_to_new_record(data)
                session.add(record)
                # Call update_record_fields to handle nested relations/members/scores for new records too
                self._update_record_fields(record, data, session)
            else:
                # Update/Merge path
                self._update_record_fields(record, data, session)

            session.commit()

    def update(self, data):
        self.set(data, merge=True)

    def delete(self):
        if self.collection_name in PURE_FIRESTORE_COLLECTIONS:
            _delete_native_doc(self.collection_name, self.id)
            return

        if not self.model_class:
            _delete_native_doc(self.collection_name, self.id)
            return

        with get_session() as session:
            if self.collection_name in ('users', 'organizations', 'tickets', 'event_sessions'):
                session.query(self.model_class).filter_by(id=str(self.id)).delete()
            elif self.collection_name == 'event_forms':
                session.query(self.model_class).filter_by(event_id=to_uuid(self.id)).delete()
            else:
                session.query(self.model_class).filter_by(id=to_uuid(self.id)).delete()
            session.commit()

    def collection(self, name):
        # Fallback nested collection reference stub
        return SQLCollectionReference(f"{self.collection_name}/{self.id}/{name}")

    def _record_to_dict(self, record, session) -> dict:
        """Convert a SQLAlchemy model record to a Firestore-styled dictionary."""
        d = {}
        for prop in record.__mapper__.column_attrs:
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
            d['evaluation_config'] = json.loads(record.evaluation_config_json) if getattr(record, 'evaluation_config_json', None) else {}
            d['ticket_tiers'] = json.loads(record.ticket_tiers_json) if getattr(record, 'ticket_tiers_json', None) else []
            d['notification_rules'] = json.loads(record.notification_rules_json) if getattr(record, 'notification_rules_json', None) else []

        elif self.collection_name == 'organizations':
            d['settings'] = json.loads(record.settings_json) if getattr(record, 'settings_json', None) else {}
            d['theme'] = {
                'primary_color': getattr(record, 'primary_color', '#1a2557'),
                'accent_color': getattr(record, 'accent_color', '#f37021'),
            }

        elif self.collection_name == 'registrations':
            d['student_email'] = record.lead_email
            # Retrieve nested team members
            m_list = []
            for m in record.members:
                m_list.append({
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
                s_dict[s.judge_id] = {
                    'judge_name': s.judge_name,
                    'total': s.total,
                    'criteria': json.loads(s.criteria) if s.criteria else {},
                    'feedback': s.feedback,
                    'timestamp': s.scored_at.isoformat() if s.scored_at else None,
                }
            d['scores'] = s_dict

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
            if record.answers_json:
                try:
                    d = json.loads(record.answers_json)
                except Exception:
                    pass
            d['event_id'] = str(record.event_id)
            d['registration_id'] = str(record.registration_id)

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

        return d

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
            kwargs['title'] = safe_str(data.get('title', 'Untitled Event'))
            kwargs['description'] = safe_str(data.get('description') or data.get('overview') or '')
            kwargs['category'] = self._get_enum_category(data.get('category', 'Technical'))
            kwargs['date'] = self._get_date(data.get('date'))
            kwargs['deadline'] = self._get_date(data.get('deadline')) if data.get('deadline') else None
            kwargs['venue'] = safe_str(data.get('venue', 'Unknown Venue'))
            kwargs['status'] = self._get_enum_status(data.get('status', 'active'))
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
            kwargs['open_hall_mode'] = bool(data.get('open_hall_mode', False))
            kwargs['scoring_locked'] = bool(data.get('scoring_locked', False))
            kwargs['judging_criteria_json'] = json.dumps(data.get('judging_criteria', []))
            kwargs['staff_json'] = json.dumps(data.get('staff', []))
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
            kwargs['actor_email'] = safe_str(data.get('actor_email', 'system'))
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
            kwargs['api_key'] = safe_str(data.get('api_key', ''))
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
            kwargs['checked_in_at'] = self._get_datetime(data.get('checked_in_at'))
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

        return None


    def _update_record_fields(self, record, data, session):
        """Update fields on an existing record based on Firestore inputs."""
        for key, val in data.items():
            # Translate keys
            mapped_key = FIELD_MAP.get(key, key)
            if hasattr(record, mapped_key):
                col = record.__mapper__.columns.get(mapped_key)
                if col is not None:
                    # Enums mappings
                    if mapped_key == 'role':
                        val = self._get_enum_role(val)
                    elif mapped_key == 'category':
                        val = self._get_enum_category(val)
                    elif mapped_key == 'status' and self.collection_name == 'events':
                        val = self._get_enum_status(val)
                    elif mapped_key == 'status' and self.collection_name == 'registrations':
                        val = self._get_enum_reg_status(val)
                    elif mapped_key == 'payment_status':
                        val = self._get_enum_payment_status(val)
                    elif mapped_key == 'attendance':
                        val = self._get_enum_attendance(val)
                    
                    # DateTime conversions
                    if mapped_key in ('created_at', 'updated_at', 'submitted_at', 'checked_in_at', 'start_time', 'end_time') or 'DateTime' in col.type.__class__.__name__:
                        val = self._get_datetime(val)
                    elif mapped_key in ('date', 'deadline'):
                        val = self._get_date(val)

                    # UUID conversions
                    elif col.type.__class__.__name__ in ('UUID', 'PgUUID'):
                        if val:
                            val = to_uuid(val)
                    # Handle dict/list values for String/Text columns
                    elif isinstance(val, (dict, list)):
                        val = safe_str(val)
                    
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
                elif key in ('workflow_config', 'workflow_config_json'):
                    record.workflow_config_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key in ('evaluation_config', 'evaluation_config_json'):
                    record.evaluation_config_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key in ('ticket_tiers', 'ticket_tiers_json'):
                    record.ticket_tiers_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key in ('notification_rules', 'notification_rules_json'):
                    record.notification_rules_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)

            elif self.collection_name == 'organizations':
                if key == 'settings':
                    record.settings_json = json.dumps(val) if isinstance(val, (dict, list)) else safe_str(val)
                elif key == 'theme' and isinstance(val, dict):
                    if 'primary_color' in val: record.primary_color = val['primary_color']
                    if 'accent_color' in val: record.accent_color = val['accent_color']

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
                            department=safe_str(m.get('dept') or m.get('department') or '')
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
                                scored_at=self._get_datetime(s_data.get('timestamp') or s_data.get('submitted_at'))
                            )
                            session.add(score)
                        else:
                            existing_score.total = total_val
                            existing_score.criteria = json.dumps(criteria_data)
                            existing_score.feedback = safe_str(s_data.get('remarks') or s_data.get('feedback') or '')
                            existing_score.scored_at = self._get_datetime(s_data.get('timestamp') or s_data.get('submitted_at'))

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

    def _get_enum_role(self, val) -> UserRole:
        role_map = {
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
        if hasattr(val, 'value'):
            return val
        cleaned = str(val).strip().lower()
        return role_map.get(cleaned, UserRole.Participant)

    def _get_enum_category(self, val) -> EventCategory:
        cat_map = {
            "technical": EventCategory.Technical,
            "tech": EventCategory.Technical,
            "cultural": EventCategory.Cultural,
            "sports": EventCategory.Sports,
            "management": EventCategory.Management,
        }
        if hasattr(val, 'value'):
            return val
        cleaned = str(val).strip().lower()
        return cat_map.get(cleaned, EventCategory.Technical)

    def _get_enum_status(self, val) -> EventStatus:
        status_map = {
            "active": EventStatus.active,
            "inactive": EventStatus.inactive,
            "completed": EventStatus.completed,
            "cancelled": EventStatus.cancelled,
            "archived": EventStatus.archived,
        }
        if hasattr(val, 'value'):
            return val
        cleaned = str(val).strip().lower()
        return status_map.get(cleaned, EventStatus.active)

    def _get_enum_reg_status(self, val) -> RegistrationStatus:
        status_map = {
            "confirmed": RegistrationStatus.confirmed,
            "approved": RegistrationStatus.confirmed,
            "pending": RegistrationStatus.pending,
            "cancelled": RegistrationStatus.cancelled,
            "waitlisted": RegistrationStatus.waitlisted,
        }
        if hasattr(val, 'value'):
            return val
        cleaned = str(val).strip().lower()
        return status_map.get(cleaned, RegistrationStatus.confirmed)

    def _get_enum_payment_status(self, val) -> PaymentStatus:
        status_map = {
            "paid": PaymentStatus.paid,
            "unpaid": PaymentStatus.unpaid,
            "waived": PaymentStatus.waived,
            "refunded": PaymentStatus.refunded,
        }
        if hasattr(val, 'value'):
            return val
        cleaned = str(val).strip().lower()
        return status_map.get(cleaned, PaymentStatus.unpaid)

    def _get_enum_attendance(self, val) -> AttendanceStatus:
        status_map = {
            "present": AttendanceStatus.Present,
            "absent": AttendanceStatus.Absent,
            "pending": AttendanceStatus.Pending,
        }
        if hasattr(val, 'value'):
            return val
        cleaned = str(val).strip().lower()
        return status_map.get(cleaned, AttendanceStatus.Pending)


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
        elif 'Date' in type_name and not 'DateTime' in type_name:
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


class SQLQuery:
    """Mock Query builder translating filters to SQLAlchemy query objects."""
    def __init__(self, collection):
        self.collection = collection
        self.filters = []
        self.orders = []
        self._limit = None

    def where(self, field=None, op=None, value=None, filter=None):
        if filter is not None:
            # Handles FieldFilter objects
            f_path = getattr(filter, 'field_path', None) or getattr(filter, 'field', None)
            f_op = getattr(filter, 'op_string', None) or getattr(filter, 'op', None) or getattr(filter, 'operator', None)
            f_val = getattr(filter, 'value', None)
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

    def stream(self):
        if self.collection.id in PURE_FIRESTORE_COLLECTIONS:
            return _query_native_docs(self.collection.id, filters=self.filters, limit=self._limit)

        if not self.collection.model:
            return _query_native_docs(self.collection.id, filters=self.filters, limit=self._limit)

        with get_session() as session:
            query = session.query(self.collection.model)
            
            # Apply where filters
            for field, op, val in self.filters:
                mapped_field = FIELD_MAP.get(field, field)
                col_attr = getattr(self.collection.model, mapped_field, None)
                if col_attr is None:
                    continue

                casted_val = _cast_value(col_attr, val)

                # Parse operators
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
                    query = query.filter(col_attr.in_(casted_val))

            # Apply order columns
            for field, direction in self.orders:
                mapped_field = FIELD_MAP.get(field, field)
                col_attr = getattr(self.collection.model, mapped_field, None)
                if col_attr is not None:
                    if direction == 'DESCENDING' or str(direction).lower() == 'desc':
                        query = query.order_by(col_attr.desc())
                    else:
                        query = query.order_by(col_attr.asc())

            # Apply limits
            if self._limit is not None:
                query = query.limit(self._limit)

            records = query.all()
            
            # Convert to Firestoresnapshots
            snapshots = []
            for record in records:
                ref = SQLDocumentReference(self.collection.id, str(record.id) if hasattr(record, 'id') else '')
                data = ref._record_to_dict(record, session)
                snapshots.append(SQLDocumentSnapshot(str(record.id) if hasattr(record, 'id') else '', data, exists=True))
                
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
        # Create all tables if they do not exist
        from db_pg import init_db
        try:
            init_db()
        except Exception as exc:
            logger.info("Database table init note: %s", exc)
        # Auto-align live postgres schemas on start
        try:
            verify_and_align_schema()
        except Exception as exc:
            logger.info("Schema alignment note: %s", exc)

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
