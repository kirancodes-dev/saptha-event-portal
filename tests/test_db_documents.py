"""
tests/test_db_documents.py — Document fidelity of the SQL Firestore adapter.

Routes are written against Firestore's schemaless documents; these tests pin
that the SQL adapter keeps every field, honours every filter, and applies
Firestore write transforms.
"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db_pg
from db_adapter import SQLFirestoreAdapter, to_uuid
from models_pg import Base, Event, User, UserRole, EventCategory


@pytest.fixture(autouse=True)
def sqlite_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db_pg, "_engine", engine)
    monkeypatch.setattr(db_pg, "_SessionLocal", sessionmaker(bind=engine, autoflush=False))
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    return SQLFirestoreAdapter()


def _spoc_event(**overrides):
    data = {
        'title': 'FlowTest Hack', 'category': 'Technical', 'date': '2030-05-05',
        'reg_deadline': '2030-05-01', 'venue': 'Hall A', 'time': '10:00',
        'is_team_event': True, 'visibility': 'public',
        'coordinators': ['c1@test.edu'],
        'limits': {'team_min': 2, 'team_max': 4, 'max_participants': 50},
        'fees': {'regular': 100},
        'prizes': {'1st': '5000', '2nd': '3000', '3rd': '1000'},
        'spoc_id': 'spoc1@test.edu',
        'organizer': {'name': 'Spoc One', 'email': 'spoc1@test.edu'},
        'status': 'active', 'results_published': False,
    }
    data.update(overrides)
    return data


def _event_row(engine, event_id):
    with sessionmaker(bind=engine)() as s:
        return s.query(Event).filter_by(id=to_uuid(event_id)).one()


def test_event_document_round_trips_every_field(db, sqlite_db):
    _, ref = db.collection('events').add(_spoc_event())
    doc = ref.get().to_dict()

    assert doc['spoc_id'] == 'spoc1@test.edu'
    assert doc['fees'] == {'regular': 100}
    assert doc['limits'] == {'team_min': 2, 'team_max': 4, 'max_participants': 50}
    assert doc['prizes'] == {'1st': '5000', '2nd': '3000', '3rd': '1000'}
    assert doc['is_team_event'] is True
    assert doc['reg_deadline'] == '2030-05-01'
    assert doc['coordinators'] == ['c1@test.edu']
    assert doc['organizer']['name'] == 'Spoc One'
    assert doc['results_published'] is False

    # The relational columns are populated too, so SQL queries/reports work
    row = _event_row(sqlite_db, ref.id)
    assert row.fee == 100.0
    assert row.coordinator_id == 'spoc1@test.edu'
    assert row.min_team_size == 2 and row.max_team_size == 4
    assert str(row.deadline) == '2030-05-01'


def test_merge_update_keeps_existing_fields(db):
    _, ref = db.collection('events').add(_spoc_event())
    ref.update({'results_published': True, 'title': 'Renamed'})
    doc = ref.get().to_dict()
    assert doc['results_published'] is True
    assert doc['title'] == 'Renamed'
    assert doc['fees'] == {'regular': 100}


def test_column_changed_outside_adapter_wins_over_stale_document(db, sqlite_db):
    _, ref = db.collection('events').add(_spoc_event(title='Original'))
    with sessionmaker(bind=sqlite_db)() as s:
        s.query(Event).filter_by(id=to_uuid(ref.id)).update({'title': 'Edited in SQL'})
        s.commit()
    assert ref.get().to_dict()['title'] == 'Edited in SQL'


def test_filter_on_document_only_field_is_applied(db):
    db.collection('events').add(_spoc_event(spoc_id='a@test.edu', title='A'))
    db.collection('events').add(_spoc_event(spoc_id='b@test.edu', title='B'))

    mine = list(db.collection('events').where('spoc_id', '==', 'a@test.edu').stream())
    assert [d.to_dict()['title'] for d in mine] == ['A']
    assert list(db.collection('events').where('spoc_id', '==', 'nobody').stream()) == []
    assert list(db.collection('events').where('no_such_field', '==', 'x').stream()) == []


def test_order_and_limit_on_document_only_field(db):
    for i, rank in enumerate([3, 1, 2]):
        db.collection('events').add(_spoc_event(title=f'E{i}', popularity=rank))
    docs = list(db.collection('events').order_by('popularity', direction='DESCENDING').limit(2).stream())
    assert [d.to_dict()['popularity'] for d in docs] == [3, 2]


def test_enum_columns_normalised_but_document_keeps_original(db, sqlite_db):
    db.collection('users').document('spoc@test.edu').set({'name': 'S', 'role': 'ClubSPOC'})
    db.collection('users').document('stu@test.edu').set({'name': 'P', 'role': 'Student'})

    assert db.collection('users').document('spoc@test.edu').get().to_dict()['role'] == 'ClubSPOC'
    with sessionmaker(bind=sqlite_db)() as s:
        assert s.query(User).filter_by(id='spoc@test.edu').one().role == UserRole.SPOC

    spocs = list(db.collection('users').where('role', '==', 'ClubSPOC').stream())
    assert [d.id for d in spocs] == ['spoc@test.edu']
    students = list(db.collection('users').where('role', 'in', ['Student', 'Participant']).stream())
    assert [d.id for d in students] == ['stu@test.edu']


def test_enum_filter_with_value_outside_enum_matches_exactly(db, sqlite_db):
    db.collection('events').add(_spoc_event(title='WS', category='Workshop'))
    db.collection('events').add(_spoc_event(title='Tech', category='Technical'))

    workshops = list(db.collection('events').where('category', '==', 'Workshop').stream())
    assert [d.to_dict()['title'] for d in workshops] == ['WS']
    with sessionmaker(bind=sqlite_db)() as s:
        assert {e.category for e in s.query(Event).all()} == {EventCategory.Technical}


def test_empty_document_value_does_not_hide_column_value(db):
    # e.g. create_event storing request.form.get('category') == None
    _, ref = db.collection('events').add(_spoc_event(category=None))
    doc = ref.get().to_dict()
    assert doc['category'] == 'Technical'   # enum column default, not None
    assert doc['category'].lower() == 'technical'  # templates call .lower()


def test_legacy_rows_without_document_get_derived_fields(db, sqlite_db):
    event_id = str(uuid.uuid4())
    with sessionmaker(bind=sqlite_db)() as s:
        s.add(Event(id=uuid.UUID(event_id), title='Old', category=EventCategory.Sports,
                    date=__import__('datetime').date(2030, 1, 1), venue='Ground',
                    fee=50.0, min_team_size=1, max_team_size=3, max_teams=20,
                    coordinator_id='old-spoc@test.edu', prizes='{"1st": "Cup"}'))
        s.commit()
    doc = db.collection('events').document(event_id).get().to_dict()
    assert doc['spoc_id'] == 'old-spoc@test.edu'
    assert doc['fees'] == {'regular': 50.0}
    assert doc['limits'] == {'max_participants': 20, 'team_min': 1, 'team_max': 3}
    assert doc['is_team_event'] is True
    assert doc['prizes'] == {'1st': 'Cup'}


def test_firestore_write_transforms(db):
    from google.cloud.firestore_v1 import Increment, ArrayUnion, ArrayRemove, DELETE_FIELD, SERVER_TIMESTAMP

    _, ref = db.collection('events').add(_spoc_event(registration_count=0, staff=[]))
    ref.update({'registration_count': Increment(1)})
    ref.update({'registration_count': Increment(2)})
    ref.update({'staff': ArrayUnion([{'email': 'x@test.edu'}])})
    ref.update({'staff': ArrayUnion([{'email': 'x@test.edu'}, {'email': 'y@test.edu'}])})
    ref.update({'coordinators': ArrayRemove(['c1@test.edu'])})
    ref.update({'visibility': DELETE_FIELD, 'closed_at': SERVER_TIMESTAMP})

    doc = ref.get().to_dict()
    assert doc['registration_count'] == 3
    assert doc['staff'] == [{'email': 'x@test.edu'}, {'email': 'y@test.edu'}]
    assert doc['coordinators'] == []
    assert 'visibility' not in doc
    assert doc['closed_at']


def test_delete_field_clears_registration_scores(db):
    from google.cloud.firestore_v1 import DELETE_FIELD

    _, ev = db.collection('events').add(_spoc_event())
    ref = db.collection('registrations').document(str(uuid.uuid4()))
    ref.set({'event_id': ev.id, 'lead_email': 's@test.edu', 'lead_name': 'S',
             'scores': {'judge@test.edu': {'total': 9, 'criteria': {}}}})
    assert ref.get().to_dict()['scores']
    ref.update({'scores': DELETE_FIELD, 'current_round': 2})
    doc = ref.get().to_dict()
    assert doc['scores'] == {}
    assert doc['current_round'] == 2


def test_transforms_on_document_store_collections(db):
    from google.cloud.firestore_v1 import Increment

    ref = db.collection('coupons').document('SAVE10')
    ref.set({'code': 'SAVE10', 'current_uses': 0})
    ref.update({'current_uses': Increment(1)})
    assert ref.get().to_dict() == {'code': 'SAVE10', 'current_uses': 1}


def test_snapshot_reference_supports_update_and_delete(db):
    db.collection('notifications').document('n1').set({'user': 'u', 'read': False})
    snap = next(db.collection('notifications').where('user', '==', 'u').stream())
    snap.reference.update({'read': True})
    assert db.collection('notifications').document('n1').get().to_dict()['read'] is True
    snap.reference.delete()
    assert not db.collection('notifications').document('n1').get().exists


def test_fallback_field_filter_value_is_read():
    class FieldFilter:  # the stub app modules use when google-cloud-firestore is absent
        def __init__(self, field=None, op=None, val=None):
            self.field, self.op, self.val = field, op, val

    q = SQLFirestoreAdapter().collection('events').where(filter=FieldFilter('spoc_id', '==', 'z'))
    assert q.filters == [('spoc_id', '==', 'z')]


def test_production_refuses_missing_database(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.delenv('ALLOW_SQLITE_IN_PRODUCTION', raising=False)
    monkeypatch.setattr(db_pg, 'DATABASE_URL', '')
    monkeypatch.setattr(db_pg, 'CLOUD_SQL_INSTANCE', '')
    monkeypatch.setattr(db_pg, '_engine', None)
    with pytest.raises(db_pg.DatabaseConfigError):
        db_pg._build_engine()

    monkeypatch.setattr(db_pg, 'DATABASE_URL', 'sqlite:///x.db')
    with pytest.raises(db_pg.DatabaseConfigError):
        db_pg._build_engine()
