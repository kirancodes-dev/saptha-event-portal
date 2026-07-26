import uuid
import json
import logging
from datetime import datetime, date, timezone
from dateutil import parser as date_parser
try:
    from sqlalchemy.orm import Session
except Exception:
    sqlalchemy = None
from db_pg import get_session
from models_pg import (
    User, Event, Registration, TeamMember, Score, EventForm,
    FormSubmission, AuditLog, PushSubscription, UserRole, EventCategory,
    EventStatus, RegistrationStatus, PaymentStatus, AttendanceStatus
)

logger = logging.getLogger(__name__)

# --- Helpers (Migrated from db_adapter.py) ---

def to_uuid(doc_id):
    if not doc_id:
        return None
    try:
        return uuid.UUID(doc_id)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, doc_id)

def safe_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return str(val)

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

# --- Repositories ---

class BaseRepository:
    model = None

    @classmethod
    def get_by_id(cls, session: Session, id_val):
        if cls.model is None: return None
        return session.query(cls.model).filter(cls.model.id == to_uuid(id_val)).first()

class UserRepository(BaseRepository):
    model = User

    @classmethod
    def get_by_email(cls, session: Session, email: str):
        return session.query(User).filter(User.email == email.lower()).first()

    @classmethod
    def create_or_update(cls, session: Session, email: str, data: dict):
        user = cls.get_by_email(session, email)
        if not user:
            user = User(
                id=uuid.uuid4(),
                email=email.lower(),
                name=safe_str(data.get('name', 'Unknown User')),
                phone=safe_str(data.get('phone', '')),
                role=cls._parse_role(data.get('role', 'Participant')),
                college=safe_str(data.get('college', '')),
                department=safe_str(data.get('department', '')),
                password_hash=safe_str(data.get('password') or data.get('passwordHash') or ''),
                is_active=bool(data.get('is_active', data.get('isActive', True))),
                created_at=parse_datetime(data.get('created_at', data.get('createdAt')))
            )
            session.add(user)
        else:
            # Update fields
            for key, val in data.items():
                if key == 'role':
                    user.role = cls._parse_role(val)
                elif key == 'password':
                    user.password_hash = safe_str(val)
                elif hasattr(user, key):
                    setattr(user, key, val)

        return user

    @staticmethod
    def _parse_role(val) -> UserRole:
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
        if hasattr(val, 'value'): return val
        cleaned = str(val).strip().lower()
        return role_map.get(cleaned, UserRole.Participant)

class EventRepository(BaseRepository):
    model = Event

    @classmethod
    def create_or_update(cls, session: Session, event_id: str, data: dict):
        uid = to_uuid(event_id)
        event = session.query(Event).filter(Event.id == uid).first()

        if not event:
            event = Event(
                id=uid,
                title=safe_str(data.get('title', 'Untitled Event')),
                description=safe_str(data.get('description') or data.get('overview') or ''),
                category=cls._parse_category(data.get('category', 'Technical')),
                date=parse_date(data.get('date')),
                deadline=parse_date(data.get('deadline')) if data.get('deadline') else None,
                venue=safe_str(data.get('venue', 'Unknown Venue')),
                status=cls._parse_status(data.get('status', 'active')),
                max_teams=data.get('max_teams', data.get('max_participants', 100)),
                min_team_size=data.get('min_team_size', data.get('team_min', 1)),
                max_team_size=data.get('max_team_size', data.get('team_max', 1)),
                fee=float(data.get('fee', data.get('entry_fee', 0.0))),
                total_rounds=data.get('total_rounds', data.get('totalRounds', 1)),
                active_round=data.get('active_round', data.get('activeRound', 1)),
                poster_url=safe_str(data.get('poster_url') or data.get('banner_url') or ''),
                rules=safe_str(data.get('rules') or ''),
                prizes=safe_str(data.get('prizes') or ''),
                coordinator_id=data.get('coordinator_id') or data.get('created_by_email') or data.get('spoc_id'),
                open_hall_mode=bool(data.get('open_hall_mode', False)),
                scoring_locked=bool(data.get('scoring_locked', False)),
                judging_criteria_json=json.dumps(data.get('judging_criteria', [])),
                staff_json=json.dumps(data.get('staff', [])),
                created_at=parse_datetime(data.get('created_at', data.get('createdAt')))
            )
            session.add(event)
        else:
            # Update logic
            for key, val in data.items():
                if key == 'category':
                    event.category = cls._parse_category(val)
                elif key == 'status':
                    event.status = cls._parse_status(val)
                elif key == 'open_hall_mode':
                    event.open_hall_mode = bool(val)
                elif key == 'scoring_locked':
                    event.scoring_locked = bool(val)
                elif key == 'judging_criteria':
                    event.judging_criteria_json = json.dumps(val)
                elif key == 'staff':
                    event.staff_json = json.dumps(val)
                elif key == 'overview':
                    event.description = safe_str(val)
                elif hasattr(event, key):
                    setattr(event, key, val)

        return event

    @staticmethod
    def _parse_category(val) -> EventCategory:
        cat_map = {
            "technical": EventCategory.Technical,
            "tech": EventCategory.Technical,
            "cultural": EventCategory.Cultural,
            "sports": EventCategory.Sports,
            "management": EventCategory.Management,
        }
        if hasattr(val, 'value'): return val
        cleaned = str(val).strip().lower()
        return cat_map.get(cleaned, EventCategory.Technical)

    @staticmethod
    def _parse_status(val) -> EventStatus:
        status_map = {
            "active": EventStatus.active,
            "inactive": EventStatus.inactive,
            "completed": EventStatus.completed,
            "cancelled": EventStatus.cancelled,
        }
        if hasattr(val, 'value'): return val
        cleaned = str(val).strip().lower()
        return status_map.get(cleaned, EventStatus.active)

class AuditLogRepository(BaseRepository):
    model = AuditLog

    @classmethod
    def log(cls, session: Session, user_email: str, action: str, details: str = ""):
        log_entry = AuditLog(
            id=uuid.uuid4(),
            actor_email=user_email,
            action=action,
            target_id=details,
            detail=details,
            created_at=datetime.now(timezone.utc)
        )
        session.add(log_entry)
        return log_entry
