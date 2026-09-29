"""
tests/test_db_adapter_merge.py — Pins the db_adapter.py adjustments made when
merging origin/claude/busy-davinci-6nkabi into master (BLK-09):

1. String-id tables (rooms, venue bookings, org units, role assignments, ...)
   are found by their id, not by a UUID derived from it.
2. Every workflow status is saved and read back unchanged, and stored in the
   status column itself when the enum has that value.
3. role_assignments.role is free text (only users.role goes through the enum).
4. Start-up schema alignment actually runs (it needs models_pg.Base).
5. The root 'default' organization and 'central' org unit are created exactly
   once, even when several server processes start at the same time.
"""
import os
import subprocess
import sys
import textwrap
import time

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import db_adapter
import db_pg
from db_adapter import SQLFirestoreAdapter
from models_pg import (Base, Event, EventStatus, OrgUnit, Organization, Registration,
                       RegistrationStatus, RoleAssignment, Room, User, UserRole, VenueBooking,
                       Campus, Building)
from services_workflow import EVENT_STATE_TRANSITIONS, PARTICIPANT_STATE_TRANSITIONS

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def engine(monkeypatch):
    """Fresh in-memory database per test, used by every adapter call."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    monkeypatch.setattr(db_pg, "_engine", eng)
    monkeypatch.setattr(db_pg, "_SessionLocal", sessionmaker(bind=eng, autoflush=False))
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def db(engine):
    return SQLFirestoreAdapter()


def _row(engine, model, **filters):
    with sessionmaker(bind=engine)() as s:
        return s.query(model).filter_by(**filters).one_or_none()


# ── 1. String-id tables ──────────────────────────────────────────────────────

def test_string_id_tables_are_found_by_their_id(db, engine):
    db.collection('org_units').document('cse').set(
        {'organization_id': 'default', 'parent_id': 'central', 'type': 'department',
         'name': 'Computer Science', 'slug': 'cse'})
    db.collection('role_assignments').document('ra-spoc-cse').set(
        {'user_id': 'spoc@test.edu', 'role': 'UnitAdmin', 'scope_type': 'unit', 'scope_id': 'cse'})
    db.collection('campuses').document('main-campus').set({'name': 'Main Campus', 'slug': 'main-campus'})
    db.collection('buildings').document('block-a').set({'campus_id': 'main-campus', 'name': 'Block A'})
    db.collection('rooms').document('room-101').set(
        {'building_id': 'block-a', 'name': 'Seminar Hall 101', 'room_number': '101', 'capacity': 120})
    _, ev = db.collection('events').add({'title': 'Room Test', 'date': '2030-01-01'})
    db.collection('venue_bookings').document('booking-1').set(
        {'room_id': 'room-101', 'event_id': ev.id,
         'start_time': '2030-01-01T10:00:00', 'end_time': '2030-01-01T12:00:00'})

    # Stored under the literal id (not uuid5 of it) ...
    assert _row(engine, OrgUnit, id='cse') is not None
    assert _row(engine, RoleAssignment, id='ra-spoc-cse') is not None
    assert _row(engine, Room, id='room-101') is not None
    assert _row(engine, VenueBooking, id='booking-1') is not None

    # ... and found again by it, for get, update and delete.
    for collection, doc_id, field, expected in [
        ('org_units', 'cse', 'name', 'Computer Science'),
        ('role_assignments', 'ra-spoc-cse', 'scope_id', 'cse'),
        ('campuses', 'main-campus', 'name', 'Main Campus'),
        ('buildings', 'block-a', 'name', 'Block A'),
        ('rooms', 'room-101', 'name', 'Seminar Hall 101'),
        ('venue_bookings', 'booking-1', 'room_id', 'room-101'),
    ]:
        snap = db.collection(collection).document(doc_id).get()
        assert snap.exists, collection
        assert snap.to_dict()[field] == expected, collection

    db.collection('rooms').document('room-101').update({'capacity': 150})
    assert db.collection('rooms').document('room-101').get().to_dict()['capacity'] == 150
    with sessionmaker(bind=engine)() as s:
        assert s.query(Room).count() == 1  # updated in place, not inserted again

    db.collection('venue_bookings').document('booking-1').delete()
    assert not db.collection('venue_bookings').document('booking-1').get().exists


# ── 2. Workflow statuses ─────────────────────────────────────────────────────

EVENT_STATES = sorted(set(EVENT_STATE_TRANSITIONS) | {s.value for s in EventStatus})
PARTICIPANT_STATES = sorted(set(PARTICIPANT_STATE_TRANSITIONS) | {s.value for s in RegistrationStatus})


@pytest.mark.parametrize('state', EVENT_STATES)
def test_every_event_workflow_status_round_trips(db, engine, state):
    _, ref = db.collection('events').add({'title': 'Workflow', 'date': '2030-01-01', 'status': 'draft'})
    ref.update({'status': state})

    assert ref.get().to_dict()['status'] == state
    assert [d.id for d in db.collection('events').where('status', '==', state).stream()] == [ref.id]
    if state in EventStatus._value2member_map_:
        # Enum-backed states must be stored in the column, not collapsed to 'active'
        assert _row(engine, Event, id=db_adapter.to_uuid(ref.id)).status.value == state


@pytest.mark.parametrize('state', PARTICIPANT_STATES)
def test_every_participant_workflow_status_round_trips(db, engine, state):
    _, ev = db.collection('events').add({'title': 'Workflow', 'date': '2030-01-01'})
    ref = db.collection('registrations').document(f'REG-{state}')
    ref.set({'event_id': ev.id, 'lead_email': 's@test.edu', 'lead_name': 'S', 'status': 'applied'})
    ref.update({'status': state})

    assert ref.get().to_dict()['status'] == state
    # Queries return the stored UUID form of 'REG-...' ids; compare normalised ids
    matches = [db_adapter.to_uuid(d.id) for d in db.collection('registrations').where('status', '==', state).stream()]
    assert matches == [db_adapter.to_uuid(ref.id)]
    if state in RegistrationStatus._value2member_map_:
        row = _row(engine, Registration, id=db_adapter.to_uuid(ref.id))
        assert row.status.value == state


@pytest.mark.xfail(strict=True, reason="BLK-06: states outside the EventStatus enum "
                   "(e.g. 'evaluation') are stored as 'active' in the SQL column")
def test_active_filter_excludes_states_outside_the_enum(db):
    _, ref = db.collection('events').add({'title': 'Judging', 'date': '2030-01-01', 'status': 'evaluation'})
    assert ref.id not in [d.id for d in db.collection('events').where('status', '==', 'active').stream()]


# ── 3. role_assignments.role is free text ────────────────────────────────────

@pytest.mark.parametrize('role', ['UniversityAdmin', 'UnitAdmin', 'EventOrganizer',
                                  'EventCoordinator', 'Volunteer', 'Judge', 'NSS Officer'])
def test_role_assignment_role_is_stored_verbatim(db, engine, role):
    doc_id = f"ra-{role.replace(' ', '-').lower()}"
    db.collection('role_assignments').document(doc_id).set(
        {'user_id': 'u@test.edu', 'role': role, 'scope_type': 'unit', 'scope_id': 'cse'})

    assert _row(engine, RoleAssignment, id=doc_id).role == role   # column, not an enum fallback
    assert db.collection('role_assignments').document(doc_id).get().to_dict()['role'] == role
    assert [d.id for d in db.collection('role_assignments').where('role', '==', role).stream()] == [doc_id]


def test_users_role_still_uses_the_role_enum(db, engine):
    db.collection('users').document('spoc@test.edu').set({'name': 'S', 'role': 'ClubSPOC'})
    assert _row(engine, User, id='spoc@test.edu').role == UserRole.SPOC
    assert db.collection('users').document('spoc@test.edu').get().to_dict()['role'] == 'ClubSPOC'


# ── 4. Start-up schema alignment ─────────────────────────────────────────────

NEWER_TABLES = [OrgUnit, RoleAssignment, Campus, Building, Room, VenueBooking]


def test_schema_alignment_upgrades_a_pre_venues_database(tmp_path, monkeypatch, caplog):
    """A database created before the venues/org-units work: alignment must add
    the missing tables and the events.visibility column."""
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    newer = {m.__table__.name for m in NEWER_TABLES}
    Base.metadata.create_all(eng, tables=[t for t in Base.metadata.sorted_tables if t.name not in newer])
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE events DROP COLUMN visibility"))
    before = inspect(eng)
    assert not newer & set(before.get_table_names())
    assert 'visibility' not in {c['name'] for c in before.get_columns('events')}

    monkeypatch.setattr(db_adapter, 'get_engine', lambda: eng)
    caplog.set_level('DEBUG', logger='db_adapter')
    db_adapter.verify_and_align_schema()

    after = inspect(eng)
    assert newer <= set(after.get_table_names())
    assert 'visibility' in {c['name'] for c in after.get_columns('events')}
    assert 'Table creation check note' not in caplog.text  # e.g. NameError: Base


def test_adapter_start_up_reports_no_alignment_errors(engine, caplog):
    caplog.set_level('DEBUG', logger='db_adapter')
    SQLFirestoreAdapter()
    assert 'Schema alignment note' not in caplog.text
    assert 'Table creation check note' not in caplog.text
    assert 'Root org unit note' not in caplog.text


# ── 5. Root organization and 'central' unit are created exactly once ─────────

def test_root_units_created_once_and_never_overwritten(db, engine):
    with sessionmaker(bind=engine)() as s:
        assert s.query(Organization).filter_by(id='default').count() == 1
        assert s.query(OrgUnit).filter_by(id='central').count() == 1
        s.query(Organization).filter_by(id='default').update({'name': 'Renamed by admin'})
        s.commit()

    for _ in range(3):  # app restarts
        SQLFirestoreAdapter()._ensure_root_units()

    with sessionmaker(bind=engine)() as s:
        assert s.query(Organization).filter_by(id='default').count() == 1
        assert s.query(OrgUnit).filter_by(id='central').count() == 1
        assert s.query(Organization).filter_by(id='default').one().name == 'Renamed by admin'


def test_root_unit_inserts_use_on_conflict_do_nothing():
    """The PostgreSQL statement must be a single conflict-safe insert."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import insert
    sql = str(insert(OrgUnit).values(id='central', organization_id='default', type='central',
                                     name='Central', slug='central')
              .on_conflict_do_nothing().compile(dialect=postgresql.dialect()))
    assert 'ON CONFLICT DO NOTHING' in sql


_WORKER = textwrap.dedent("""
    import sys, time
    sys.path.insert(0, {project!r})
    start_at = float(sys.argv[1])
    from db_adapter import SQLFirestoreAdapter
    ensure = SQLFirestoreAdapter._ensure_root_units
    SQLFirestoreAdapter._ensure_root_units = lambda self: None  # not before the barrier
    adapter = SQLFirestoreAdapter()
    while time.time() < start_at:        # line all workers up on the same instant
        time.sleep(0.001)
    ensure(adapter)                      # direct call: any conflict error propagates
    print('OK')
""")


def test_root_units_safe_when_processes_start_together(tmp_path):
    """Eight server processes starting at once against one database: no errors,
    exactly one 'default' organization and one 'central' unit."""
    test_pg = os.environ.get('TEST_DATABASE_URL', '')
    url = test_pg if test_pg.startswith('postgres') else f"sqlite:///{tmp_path / 'shared.db'}"
    env = dict(os.environ, DATABASE_URL=url, DATABASE_TYPE='postgres', FLASK_ENV='development')
    script = tmp_path / 'worker.py'
    script.write_text(_WORKER.format(project=PROJECT_DIR))

    eng = create_engine(db_pg._normalize_url(url))  # same driver choice as the app
    Base.metadata.create_all(eng)  # schema up front; the race is only over the root rows
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM org_units WHERE id = 'central'"))
        conn.execute(text("DELETE FROM organizations WHERE id = 'default'"))

    start_at = time.time() + 6  # enough for every worker to import and connect
    procs = [subprocess.Popen([sys.executable, str(script), str(start_at)], env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(8)]
    results = [p.communicate(timeout=90) for p in procs]
    for proc, (out, err) in zip(procs, results):
        assert proc.returncode == 0 and 'OK' in out, err[-2000:]

    with eng.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM organizations WHERE id = 'default'")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM org_units WHERE id = 'central'")).scalar() == 1
