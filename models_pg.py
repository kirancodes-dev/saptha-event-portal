"""
models_pg.py — SQLAlchemy ORM models for SapthaEvent PostgreSQL (SQL Connect)

Column names in Python use snake_case (PostgreSQL convention).
SQL Connect GraphQL field names use camelCase — the mapping is handled
by SQL Connect automatically when it generates the DDL.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, Date
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _utcnow():
    return datetime.now(timezone.utc)


# ── Enums ────────────────────────────────────────────────────────────────────
class UserRole(enum.Enum):
    SuperAdmin  = "SuperAdmin"
    Coordinator = "Coordinator"
    SPOC        = "SPOC"
    Judge       = "Judge"
    Participant = "Participant"


class EventCategory(enum.Enum):
    Technical  = "Technical"
    Cultural   = "Cultural"
    Sports     = "Sports"
    Management = "Management"


class EventStatus(enum.Enum):
    active    = "active"
    inactive  = "inactive"
    completed = "completed"
    cancelled = "cancelled"


class RegistrationStatus(enum.Enum):
    pending    = "pending"
    confirmed  = "confirmed"
    cancelled  = "cancelled"
    waitlisted = "waitlisted"


class PaymentStatus(enum.Enum):
    unpaid   = "unpaid"
    paid     = "paid"
    waived   = "waived"
    refunded = "refunded"


class AttendanceStatus(enum.Enum):
    Present = "Present"
    Absent  = "Absent"
    Pending = "Pending"


# ── Models ───────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id            = Column(String(128), primary_key=True)
    email         = Column(String(255), nullable=False, unique=True, index=True)
    name          = Column(String(200), nullable=False)
    phone         = Column(String(20))
    role          = Column(Enum(UserRole), nullable=False, default=UserRole.Participant)
    college       = Column(String(200))
    department    = Column(String(100))
    password_hash = Column("passwordHash", String(255))
    is_active     = Column("isActive", Boolean, nullable=False, default=True)
    created_at    = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at    = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'email': self.email, 'name': self.name,
            'phone': self.phone, 'role': self.role.value if self.role else None,
            'college': self.college, 'department': self.department,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Event(Base):
    __tablename__ = "events"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title          = Column(String(300), nullable=False)
    description    = Column(Text)
    category       = Column(Enum(EventCategory), nullable=False)
    date           = Column(Date, nullable=False)
    deadline       = Column(Date)
    venue          = Column(String(300), nullable=False)
    status         = Column(Enum(EventStatus), nullable=False, default=EventStatus.active)
    max_teams      = Column("maxTeams", Integer)
    min_team_size  = Column("minTeamSize", Integer, nullable=False, default=1)
    max_team_size  = Column("maxTeamSize", Integer, nullable=False, default=1)
    fee            = Column(Float, nullable=False, default=0.0)
    total_rounds   = Column("totalRounds", Integer, nullable=False, default=1)
    active_round   = Column("activeRound", Integer, nullable=False, default=1)
    poster_url     = Column("posterUrl", String(500))
    rules          = Column(Text)
    prizes         = Column(Text)
    coordinator_id = Column("coordinatorId", String(128))
    created_at     = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at     = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    registrations = relationship("Registration", back_populates="event", cascade="all, delete-orphan")
    event_form    = relationship("EventForm", back_populates="event", uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': str(self.id), 'title': self.title, 'description': self.description,
            'category': self.category.value if self.category else None,
            'date': self.date.isoformat() if self.date else None,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'venue': self.venue,
            'status': self.status.value if self.status else None,
            'max_teams': self.max_teams, 'min_team_size': self.min_team_size,
            'max_team_size': self.max_team_size, 'fee': self.fee,
            'total_rounds': self.total_rounds, 'active_round': self.active_round,
            'poster_url': self.poster_url, 'rules': self.rules, 'prizes': self.prizes,
            'coordinator_id': self.coordinator_id,
        }


class Registration(Base):
    __tablename__ = "registrations"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id       = Column("eventId", UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_name      = Column("leadName", String(200), nullable=False)
    lead_email     = Column("leadEmail", String(255), nullable=False, index=True)
    lead_phone     = Column("leadPhone", String(20), nullable=False)
    team_name      = Column("teamName", String(200))
    status         = Column(Enum(RegistrationStatus), nullable=False, default=RegistrationStatus.confirmed)
    payment_status = Column("paymentStatus", Enum(PaymentStatus), nullable=False, default=PaymentStatus.unpaid)
    payment_id     = Column("paymentId", String(200))
    attendance     = Column(Enum(AttendanceStatus), nullable=False, default=AttendanceStatus.Pending)
    current_round  = Column("currentRound", Integer, nullable=False, default=1)
    is_eliminated  = Column("isEliminated", Boolean, nullable=False, default=False)
    qr_code_url    = Column("qrCodeUrl", String(500))
    notes          = Column(Text)
    created_at     = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at     = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    event   = relationship("Event", back_populates="registrations")
    members = relationship("TeamMember", back_populates="registration", cascade="all, delete-orphan")
    scores  = relationship("Score", back_populates="registration", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': str(self.id), 'event_id': str(self.event_id),
            'lead_name': self.lead_name, 'lead_email': self.lead_email,
            'lead_phone': self.lead_phone, 'team_name': self.team_name,
            'status': self.status.value if self.status else None,
            'payment_status': self.payment_status.value if self.payment_status else None,
            'payment_id': self.payment_id,
            'attendance': self.attendance.value if self.attendance else None,
            'current_round': self.current_round, 'is_eliminated': self.is_eliminated,
            'qr_code_url': self.qr_code_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TeamMember(Base):
    __tablename__ = "team_members"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registration_id = Column("registrationId", UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False, index=True)
    name            = Column(String(200), nullable=False)
    email           = Column(String(255))
    phone           = Column(String(20))
    usn             = Column(String(50))
    college         = Column(String(200))
    department      = Column(String(100))

    registration = relationship("Registration", back_populates="members")

    def to_dict(self):
        return {
            'id': str(self.id), 'name': self.name, 'email': self.email,
            'phone': self.phone, 'usn': self.usn, 'college': self.college,
            'department': self.department,
        }


class Score(Base):
    __tablename__ = "scores"

    registration_id = Column("registrationId", UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="CASCADE"), primary_key=True)
    judge_id        = Column("judgeId", String(128), primary_key=True)
    judge_name      = Column("judgeName", String(200))
    round           = Column(Integer, nullable=False)
    total           = Column(Float, nullable=False)
    criteria        = Column(Text)
    feedback        = Column(Text)
    scored_at       = Column("scoredAt", DateTime(timezone=True), nullable=False, default=_utcnow)

    registration = relationship("Registration", back_populates="scores")

    def to_dict(self):
        return {
            'registration_id': str(self.registration_id), 'judge_id': self.judge_id,
            'judge_name': self.judge_name, 'round': self.round, 'total': self.total,
            'criteria': self.criteria, 'feedback': self.feedback,
            'scored_at': self.scored_at.isoformat() if self.scored_at else None,
        }


class EventForm(Base):
    __tablename__ = "event_forms"

    event_id    = Column("eventId", UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    fields_json = Column("fieldsJson", Text, nullable=False)
    created_at  = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)

    event = relationship("Event", back_populates="event_form")


class FormSubmission(Base):
    __tablename__ = "form_submissions"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id        = Column("eventId", UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    registration_id = Column("registrationId", UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False, index=True)
    answers_json    = Column("answersJson", Text, nullable=False)
    submitted_at    = Column("submittedAt", DateTime(timezone=True), nullable=False, default=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_email = Column("actorEmail", String(255), nullable=False)
    action      = Column(String(200), nullable=False)
    target_id   = Column("targetId", String(200))
    detail      = Column(Text)
    created_at  = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_email = Column("userEmail", String(255), nullable=False, index=True)
    endpoint   = Column(Text, nullable=False)
    p256dh     = Column(String(255), nullable=False)
    auth_key   = Column("authKey", Text, nullable=False)
    created_at = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
