"""
tests/test_db_filters_real_values.py — BLK-06a on the real SQL database
layer: filters compare the values the app stored, not the coarse enum column.
"""
import uuid

import pytest
from sqlalchemy import event as sa_event


@pytest.fixture
def db(real_app):
    return real_app[1]


def _u(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _emails(stream):
    return {d.id for d in stream}


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_role_filters_match_the_stored_role(db):
    admin = f"{_u('uadmin')}@test.edu"
    student = f"{_u('stu')}@test.edu"
    participant = f"{_u('part')}@test.edu"
    legacy_coord = f"{_u('coord')}@test.edu"
    db.collection('users').document(admin).set({'name': 'A', 'role': 'UniversityAdmin'})
    db.collection('users').document(student).set({'name': 'S', 'role': 'Student'})
    db.collection('users').document(participant).set({'name': 'P', 'role': 'Participant'})
    db.collection('users').document(legacy_coord).set({'name': 'C', 'role': 'Coordinator'})
    mine = {admin, student, participant, legacy_coord}

    def role(value, op='=='):
        return _emails(db.collection('users').where('role', op, value).stream()) & mine

    assert role('UniversityAdmin') == {admin}
    # The admin is stored in the column as the 'Participant' fallback; it must not match
    assert role('Participant') == {student, participant}  # Student and Participant are synonyms
    assert role('participant') == {student, participant}  # any case
    assert role('EventCoordinator') == {legacy_coord}      # legacy synonym kept
    assert role(['UniversityAdmin', 'Coordinator'], 'in') == {admin, legacy_coord}
    assert admin in role('Participant', '!=')


def test_category_filters_match_the_stored_category(db):
    tag = _u('cat')
    _, nss = db.collection('events').add({'title': f'NSS drive {tag}', 'date': '2030-01-01', 'category': 'NSS'})
    _, tech = db.collection('events').add({'title': f'Hack {tag}', 'date': '2030-01-01', 'category': 'Technical'})

    def cat(value):
        return {d.id for d in db.collection('events').where('category', '==', value).stream()} & {nss.id, tech.id}

    assert cat('Technical') == {tech.id}  # NSS is stored as 'Technical' in the column
    assert cat('NSS') == {nss.id}


# ── Criterion 6 (workflow states keep their value) ─────────────────────────

def test_workflow_states_are_stored_as_themselves(db, real_app):
    from db_adapter import to_uuid
    from db_pg import get_session
    from models_pg import Event, Registration

    _, ev = db.collection('events').add({'title': 'Judging', 'date': '2030-01-01', 'status': 'evaluation'})
    reg = db.collection('registrations').document(_u('REG'))
    reg.set({'event_id': ev.id, 'lead_email': 's@test.edu', 'lead_name': 'S', 'status': 'Pending Payment'})
    with get_session() as s:
        assert s.get(Event, to_uuid(ev.id)).status.value == 'evaluation'
        assert s.get(Registration, to_uuid(reg.id)).status.value == 'pending_payment'
    assert ev.id not in {d.id for d in db.collection('events').where('status', '==', 'active').stream()}
    held = {to_uuid(d.id) for d in db.collection('registrations').where('status', '==', 'confirmed').stream()}
    assert to_uuid(reg.id) not in held


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_audit_log_records_the_real_actor(real_app):
    flask_app, db = real_app
    from db_pg import get_session
    from models_pg import AuditLog
    from utils import log_action

    actor = f"{_u('actor')}@test.edu"
    action = _u('TEST_ACTION')
    with flask_app.test_request_context('/'):
        from flask import session
        session['user_id'] = actor
        session['role'] = 'ClubSPOC'
        log_action(db, action, 'details')
    with get_session() as s:
        row = s.query(AuditLog).filter(AuditLog.action == action).one()
        assert row.actor_email == actor
    assert [d.to_dict()['user'] for d in db.collection('audit_log').where('actor_email', '==', actor).stream()] == [actor]


# ── Criterion 7 ─────────────────────────────────────────────────────────────

def test_spoc_id_is_an_indexed_column_answered_by_sql(real_app):
    flask_app, db = real_app
    from db_pg import get_engine
    from models_pg import Event

    assert Event.__table__.c.spoc_id.index is True
    spoc = f"{_u('spoc')}@test.edu"
    _, mine = db.collection('events').add({'title': 'Mine', 'date': '2030-01-01', 'spoc_id': spoc})
    _, other = db.collection('events').add({'title': 'Other', 'date': '2030-01-01', 'spoc_id': 'x@test.edu'})

    statements = []

    def capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    engine = get_engine()
    sa_event.listen(engine, 'before_cursor_execute', capture)
    try:
        found = [d.id for d in db.collection('events').where('spoc_id', '==', spoc).stream()]
    finally:
        sa_event.remove(engine, 'before_cursor_execute', capture)
    assert found == [mine.id]
    selects = [s for s in statements if 'FROM events' in s]
    assert selects and 'WHERE' in selects[0] and 'spoc_id' in selects[0].split('WHERE', 1)[1]


# ── Criterion 8 ─────────────────────────────────────────────────────────────

def test_organisations_without_api_keys_can_coexist(db):
    from db_pg import get_session
    from models_pg import Organization

    a, b = _u('org-a'), _u('org-b')
    db.collection('organizations').document(a).set({'name': 'A', 'slug': a})
    db.collection('organizations').document(b).set({'name': 'B', 'slug': b})
    with get_session() as s:
        assert s.get(Organization, a).api_key is None
        assert s.get(Organization, b).api_key is None
    db.collection('organizations').document(a).update({'api_key': ''})
    assert db.collection('organizations').document(a).get().exists
