"""
models_pg.py — SQLAlchemy ORM models for SapthaEvent PostgreSQL (SQL Connect)

Column names in Python use snake_case (PostgreSQL convention).
SQL Connect GraphQL field names use camelCase — the mapping is handled
by SQL Connect automatically when it generates the DDL.
"""
import enum
import json
import uuid
from datetime import datetime, timezone

try:
    from sqlalchemy import (
        Boolean, Column, DateTime, Enum, Float, ForeignKey,
        Integer, String, Text, Date, Index
    )
except Exception:
    sqlalchemy = None
try:
    from sqlalchemy.dialects.postgresql import UUID
except Exception:
    sqlalchemy = None
try:
    from sqlalchemy.orm import DeclarativeBase, relationship
except Exception:
    DeclarativeBase = object
    relationship = None


class Base(DeclarativeBase):
    pass


def _utcnow():
    return datetime.now(timezone.utc)


# ── Enums ────────────────────────────────────────────────────────────────────
class UserRole(enum.Enum):
    SuperAdmin       = "SuperAdmin"
    Coordinator      = "Coordinator"
    SPOC             = "SPOC"
    Judge            = "Judge"
    Participant      = "Participant"
    UniversityAdmin  = "UniversityAdmin"
    UnitAdmin        = "UnitAdmin"
    EventOrganizer   = "EventOrganizer"
    EventCoordinator = "EventCoordinator"
    Volunteer        = "Volunteer"


class EventCategory(enum.Enum):
    Technical  = "Technical"
    Cultural   = "Cultural"
    Sports     = "Sports"
    Management = "Management"


class EventStatus(enum.Enum):
    draft               = "draft"
    pending_approval    = "pending_approval"
    published           = "published"
    registration_open   = "registration_open"
    registration_closed = "registration_closed"
    in_progress         = "in_progress"
    evaluation          = "evaluation"
    active              = "active"
    inactive            = "inactive"
    completed           = "completed"
    certified           = "certified"
    cancelled           = "cancelled"
    archived            = "archived"


class RegistrationStatus(enum.Enum):
    pending    = "pending"
    confirmed  = "confirmed"
    cancelled  = "cancelled"
    waitlisted = "waitlisted"
    checked_in = "checked_in"
    # Participant workflow states (services_workflow.PARTICIPANT_STATE_TRANSITIONS),
    # stored as themselves rather than falling back to 'confirmed' (BLK-06)
    applied         = "applied"
    pending_payment = "pending_payment"
    round_1         = "round_1"
    shortlisted     = "shortlisted"
    finalist        = "finalist"
    winner          = "winner"
    runner_up       = "runner_up"
    eliminated      = "eliminated"
    completed       = "completed"
    certified       = "certified"


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
    # Schemaless overflow: the full Firestore-style document, so fields without
    # a dedicated column survive a write/read round-trip (see db_adapter).
    extra_json    = Column("extra_json", Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id, 'email': self.email, 'name': self.name,
            'phone': self.phone, 'role': self.role.value if self.role else None,
            'college': self.college, 'department': self.department,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Organization(Base):
    __tablename__ = "organizations"

    id            = Column(String(128), primary_key=True)
    name          = Column(String(255), nullable=False)
    slug          = Column(String(100), nullable=False, unique=True, index=True)
    domain        = Column(String(255), index=True)
    plan          = Column(String(50), nullable=False, default="free")
    logo_url      = Column("logoUrl", String(500))
    favicon_url   = Column("faviconUrl", String(500))
    primary_color = Column("primaryColor", String(20), default="#1a2557")
    accent_color  = Column("accentColor", String(20), default="#f37021")
    custom_domain = Column("customDomain", String(255), unique=True)
    api_key       = Column("apiKey", String(128), unique=True, index=True)
    owner_email   = Column("ownerEmail", String(255))
    is_active     = Column("isActive", Boolean, nullable=False, default=True)
    settings_json = Column("settingsJson", Text)
    created_at    = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at    = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    # Schemaless overflow: the full Firestore-style document, so fields without
    # a dedicated column survive a write/read round-trip (see db_adapter).
    extra_json    = Column("extra_json", Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'domain': self.domain,
            'plan': self.plan,
            'logo_url': self.logo_url,
            'favicon_url': self.favicon_url,
            'primary_color': self.primary_color,
            'accent_color': self.accent_color,
            'custom_domain': self.custom_domain,
            'owner_email': self.owner_email,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class OrgUnit(Base):
    __tablename__ = "org_units"

    id              = Column(String(128), primary_key=True)
    organization_id = Column("organizationId", String(128), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id       = Column("parentId", String(128), ForeignKey("org_units.id", ondelete="SET NULL"), nullable=True, index=True)
    type            = Column(String(50), nullable=False)  # 'central' | 'department' | 'club'
    name            = Column(String(255), nullable=False)
    slug            = Column(String(100), nullable=False, index=True)
    created_at      = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at      = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'parent_id': self.parent_id,
            'type': self.type,
            'name': self.name,
            'slug': self.slug,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        Index("idx_role_user_scope", "userId", "scopeType", "scopeId"),
    )

    id         = Column(String(128), primary_key=True)
    user_id    = Column("userId", String(255), nullable=False, index=True)
    role       = Column(String(50), nullable=False)
    scope_type = Column("scopeType", String(50), nullable=False)  # 'university' | 'unit' | 'event'
    scope_id   = Column("scopeId", String(128), nullable=True, index=True)
    created_at = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'role': self.role,
            'scope_type': self.scope_type,
            'scope_id': self.scope_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Campus(Base):
    __tablename__ = "campuses"

    id              = Column(String(128), primary_key=True)
    organization_id = Column("organizationId", String(128), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name            = Column(String(255), nullable=False)
    slug            = Column(String(100), nullable=False, unique=True, index=True)
    address         = Column(Text)
    created_at      = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at      = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    buildings = relationship("Building", back_populates="campus", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'organizationId': self.organization_id,
            'name': self.name,
            'slug': self.slug,
            'address': self.address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Building(Base):
    __tablename__ = "buildings"

    id         = Column(String(128), primary_key=True)
    campus_id  = Column("campusId", String(128), ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False, index=True)
    name       = Column(String(255), nullable=False)
    code       = Column(String(50))
    created_at = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    campus = relationship("Campus", back_populates="buildings")
    rooms  = relationship("Room", back_populates="building", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'campus_id': self.campus_id,
            'campusId': self.campus_id,
            'name': self.name,
            'code': self.code,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Room(Base):
    __tablename__ = "rooms"

    id              = Column(String(128), primary_key=True)
    building_id     = Column("buildingId", String(128), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False, index=True)
    name            = Column(String(255), nullable=False)
    room_number     = Column("roomNumber", String(100))
    capacity        = Column(Integer, nullable=False, default=50)
    type            = Column(String(50), nullable=False, default="classroom")  # auditorium | lab | classroom | seminar_hall | outdoor
    facilities_json = Column("facilitiesJson", Text)
    created_at      = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at      = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    building = relationship("Building", back_populates="rooms")
    bookings = relationship("VenueBooking", back_populates="room", cascade="all, delete-orphan")

    def to_dict(self):
        facilities = []
        if self.facilities_json:
            try:
                facilities = json.loads(self.facilities_json) if isinstance(self.facilities_json, str) else self.facilities_json
            except Exception:
                facilities = [f.strip() for f in str(self.facilities_json).split(',') if f.strip()]
        return {
            'id': self.id,
            'building_id': self.building_id,
            'buildingId': self.building_id,
            'name': self.name,
            'room_number': self.room_number,
            'roomNumber': self.room_number,
            'capacity': self.capacity,
            'type': self.type,
            'facilities': facilities,
            'facilities_json': self.facilities_json,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("idx_events_status_date", "status", "date"),
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column("organizationId", String(128), index=True, nullable=True)
    org_unit_id    = Column("orgUnitId", String(128), ForeignKey("org_units.id", ondelete="SET NULL"), nullable=True, index=True)
    room_id        = Column("roomId", String(128), ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True, index=True)
    title          = Column(String(300), nullable=False)
    slug           = Column(String(300), index=True, nullable=True)
    description    = Column(Text)
    category       = Column(Enum(EventCategory), nullable=False)
    visibility     = Column(String(50), nullable=False, default="Public")
    event_type     = Column("eventType", String(100), default="competition")
    event_mode     = Column("eventMode", String(50), default="offline")
    timezone       = Column(String(100), default="Asia/Kolkata")
    date           = Column(Date, nullable=False)
    deadline       = Column(Date)
    start_datetime = Column("startDatetime", DateTime(timezone=True), nullable=True)
    end_datetime   = Column("endDatetime", DateTime(timezone=True), nullable=True)
    venue          = Column(String(300), nullable=False)
    status         = Column(Enum(EventStatus), nullable=False, default=EventStatus.active)
    capacity       = Column(Integer, default=200)
    pricing_type   = Column("pricingType", String(50), default="free")
    currency       = Column(String(10), default="INR")
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
    # The owning SPOC; routes and services_permission filter on it (BLK-06)
    spoc_id        = Column("spoc_id", String(255), nullable=True, index=True)
    registration_count = Column("registration_count", Integer, nullable=False, default=0)
    open_hall_mode = Column("open_hall_mode", Boolean, nullable=False, default=False)
    scoring_locked = Column("scoring_locked", Boolean, nullable=False, default=False)
    judging_criteria_json = Column("judging_criteria_json", Text)
    staff_json     = Column("staff_json", Text)
    workflow_config_json = Column("workflowConfigJson", Text, nullable=True)
    evaluation_config_json = Column("evaluationConfigJson", Text, nullable=True)
    ticket_tiers_json = Column("ticketTiersJson", Text, nullable=True)
    notification_rules_json = Column("notificationRulesJson", Text, nullable=True)
    certificate_config_json = Column("certificateConfigJson", Text, nullable=True)
    created_at     = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at     = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    # Schemaless overflow: the full Firestore-style document, so fields without
    # a dedicated column survive a write/read round-trip (see db_adapter).
    extra_json    = Column("extra_json", Text, nullable=True)

    registrations = relationship("Registration", back_populates="event", cascade="all, delete-orphan")
    event_form    = relationship("EventForm", back_populates="event", uselist=False, cascade="all, delete-orphan")
    room          = relationship("Room", foreign_keys=[room_id])

    def to_dict(self):
        return {
            'id': str(self.id),
            'organization_id': self.organization_id,
            'organizationId': self.organization_id,
            'org_unit_id': self.org_unit_id,
            'orgUnitId': self.org_unit_id,
            'room_id': self.room_id,
            'roomId': self.room_id,
            'room_name': self.room.name if self.room else None,
            'title': self.title, 'slug': self.slug, 'description': self.description,
            'category': self.category.value if self.category else None,
            'visibility': self.visibility or 'Public',
            'event_type': self.event_type, 'event_mode': self.event_mode,
            'timezone': self.timezone,
            'date': self.date.isoformat() if self.date else None,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'start_datetime': self.start_datetime.isoformat() if self.start_datetime else None,
            'end_datetime': self.end_datetime.isoformat() if self.end_datetime else None,
            'venue': self.venue,
            'status': self.status.value if self.status else None,
            'capacity': self.capacity, 'pricing_type': self.pricing_type, 'currency': self.currency,
            'max_teams': self.max_teams, 'min_team_size': self.min_team_size,
            'max_team_size': self.max_team_size, 'fee': self.fee,
            'total_rounds': self.total_rounds, 'active_round': self.active_round,
            'poster_url': self.poster_url, 'rules': self.rules, 'prizes': self.prizes,
            'coordinator_id': self.coordinator_id,
            'registration_count': self.registration_count or 0,
            'workflow_config': json.loads(self.workflow_config_json) if self.workflow_config_json else {},
            'evaluation_config': json.loads(self.evaluation_config_json) if self.evaluation_config_json else {},
            'ticket_tiers': json.loads(self.ticket_tiers_json) if self.ticket_tiers_json else [],
            'notification_rules': json.loads(self.notification_rules_json) if self.notification_rules_json else [],
            'certificate_config': json.loads(self.certificate_config_json) if self.certificate_config_json else {},
        }


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (
        Index("idx_registrations_event_attendance_status", "eventId", "attendance", "status"),
    )

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
    assigned_judge_email = Column("assigned_judge_email", String(255))
    amount_paid    = Column("amount_paid", Float)
    payment_mode   = Column("payment_mode", String(100))
    assigned_room  = Column("assigned_room", String(100))
    checkin_time   = Column("checkin_time", String(100), nullable=True)
    ticket_id      = Column("ticket_id", String(128), nullable=True)
    feedback_json  = Column("feedback_json", Text, nullable=True)
    created_at     = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at     = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    # Schemaless overflow: the full Firestore-style document, so fields without
    # a dedicated column survive a write/read round-trip (see db_adapter).
    extra_json    = Column("extra_json", Text, nullable=True)

    event   = relationship("Event", back_populates="registrations")
    members = relationship("TeamMember", back_populates="registration", cascade="all, delete-orphan")
    scores  = relationship("Score", back_populates="registration", cascade="all, delete-orphan")

    def to_dict(self):
        fb = None
        if self.feedback_json:
            try:
                fb = json.loads(self.feedback_json)
            except Exception:
                fb = None
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
            'checkin_time': self.checkin_time,
            'ticket_id': self.ticket_id,
            'feedback': fb,
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
    # Schemaless overflow: the full Firestore-style document, so fields without
    # a dedicated column survive a write/read round-trip (see db_adapter).
    extra_json    = Column("extra_json", Text, nullable=True)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_email = Column("userEmail", String(255), nullable=False, index=True)
    endpoint   = Column(Text, nullable=False)
    p256dh     = Column(String(255), nullable=False)
    auth_key   = Column("authKey", Text, nullable=False)
    created_at = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)


class PaymentOrder(Base):
    """A Razorpay order created by this server (BLK-03).

    Payment verification accepts only orders recorded here, for the same
    event, payer and amount; ``payment_id`` is unique so a payment can be
    used once.
    """
    __tablename__ = "payment_orders"

    id           = Column(String(128), primary_key=True)  # Razorpay order id
    event_id     = Column("eventId", String(128), nullable=False, index=True)
    email        = Column(String(255), nullable=False, index=True)
    amount_paise = Column("amountPaise", Integer, nullable=False)
    currency     = Column(String(8), nullable=False, default="INR")
    coupon_code  = Column("couponCode", String(64), nullable=True)
    status       = Column(String(20), nullable=False, default="created")  # created | paid
    payment_id   = Column("paymentId", String(128), nullable=True, unique=True)
    reg_id       = Column("regId", String(128), nullable=True)
    created_at   = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    paid_at      = Column("paidAt", DateTime(timezone=True), nullable=True)


class Announcement(Base):
    __tablename__ = "announcements"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id    = Column("event_id", String(100), nullable=True, index=True)
    event_title = Column("event_title", String(255), nullable=True)
    message     = Column(Text, nullable=False)
    priority    = Column(String(50), nullable=False, default="info")
    spoc_email  = Column("spoc_email", String(255), nullable=True)
    timestamp   = Column(String(100), nullable=False)


class ProjectSubmission(Base):
    __tablename__ = "project_submissions"

    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id          = Column("eventId", UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    registration_id   = Column("registrationId", UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False, index=True)
    team_name         = Column("teamName", String(200), nullable=False)
    project_title     = Column("projectTitle", String(255), nullable=False)
    tagline           = Column(String(500))
    problem_statement = Column("problemStatement", Text)
    solution_overview = Column("solutionOverview", Text)
    tech_stack        = Column("techStack", String(500))
    github_url        = Column("githubUrl", String(500))
    demo_url          = Column("demoUrl", String(500))
    video_url         = Column("videoUrl", String(500))
    slide_deck_url    = Column("slideDeckUrl", String(500))
    milestone_stage   = Column("milestoneStage", String(50), nullable=False, default="Ideation")
    score_impact      = Column("scoreImpact", Float, default=0.0)
    score_tech        = Column("scoreTech", Float, default=0.0)
    score_ux          = Column("scoreUx", Float, default=0.0)
    score_pitch       = Column("scorePitch", Float, default=0.0)
    total_score       = Column("totalScore", Float, default=0.0)
    submitted_at      = Column("submittedAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at        = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    # Schemaless overflow: the full Firestore-style document, so fields without
    # a dedicated column survive a write/read round-trip (see db_adapter).
    extra_json    = Column("extra_json", Text, nullable=True)


class Ticket(Base):
    __tablename__ = "tickets"

    id               = Column(String(128), primary_key=True)
    event_id         = Column("eventId", UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    registration_id  = Column("registrationId", UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_email       = Column("userEmail", String(255), nullable=False, index=True)
    ticket_type      = Column("ticketType", String(100), nullable=False, default="General")
    ticket_code      = Column("ticketCode", String(100), nullable=False, unique=True, index=True)
    qr_token_hash    = Column("qrTokenHash", String(255), nullable=False)
    gate_assignment  = Column("gateAssignment", String(100))
    seat_assignment  = Column("seatAssignment", String(100))
    status           = Column("status", String(50), nullable=False, default="active")
    checked_in_at    = Column("checkedInAt", DateTime(timezone=True))
    created_at       = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    # Schemaless overflow: the full Firestore-style document, so fields without
    # a dedicated column survive a write/read round-trip (see db_adapter).
    extra_json    = Column("extra_json", Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': str(self.event_id),
            'registration_id': str(self.registration_id),
            'user_email': self.user_email,
            'ticket_type': self.ticket_type,
            'ticket_code': self.ticket_code,
            'qr_token_hash': self.qr_token_hash,
            'gate_assignment': self.gate_assignment,
            'seat_assignment': self.seat_assignment,
            'status': self.status,
            'checked_in_at': self.checked_in_at.isoformat() if self.checked_in_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class EventSession(Base):
    __tablename__ = "event_sessions"

    id            = Column(String(128), primary_key=True)
    event_id      = Column("eventId", UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    track_name    = Column("trackName", String(100), default="Main Track")
    title         = Column("title", String(300), nullable=False)
    speaker_name  = Column("speakerName", String(200))
    speaker_bio   = Column("speakerBio", Text)
    room_number   = Column("roomNumber", String(100))
    start_time    = Column("startTime", DateTime(timezone=True), nullable=False)
    end_time      = Column("endTime", DateTime(timezone=True), nullable=False)
    capacity      = Column("capacity", Integer, default=100)
    created_at    = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    # Schemaless overflow: the full Firestore-style document, so fields without
    # a dedicated column survive a write/read round-trip (see db_adapter).
    extra_json    = Column("extra_json", Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': str(self.event_id),
            'track_name': self.track_name,
            'title': self.title,
            'speaker_name': self.speaker_name,
            'speaker_bio': self.speaker_bio,
            'room_number': self.room_number,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'capacity': self.capacity,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class VenueBooking(Base):
    __tablename__ = "venue_bookings"
    __table_args__ = (
        Index("idx_venue_bookings_room_time", "roomId", "startTime", "endTime", "status"),
    )

    id         = Column(String(128), primary_key=True)
    room_id    = Column("roomId", String(128), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id   = Column("eventId", UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = Column("sessionId", String(128), ForeignKey("event_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    start_time = Column("startTime", DateTime(timezone=True), nullable=False)
    end_time   = Column("endTime", DateTime(timezone=True), nullable=False)
    status     = Column(String(50), nullable=False, default="confirmed")  # hold | confirmed | cancelled
    notes      = Column(Text)
    created_at = Column("createdAt", DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column("updatedAt", DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    room  = relationship("Room", back_populates="bookings")
    event = relationship("Event")

    def to_dict(self):
        return {
            'id': self.id,
            'room_id': self.room_id,
            'roomId': self.room_id,
            'event_id': str(self.event_id) if self.event_id else None,
            'eventId': str(self.event_id) if self.event_id else None,
            'session_id': self.session_id,
            'sessionId': self.session_id,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'startTime': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'endTime': self.end_time.isoformat() if self.end_time else None,
            'status': self.status,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
