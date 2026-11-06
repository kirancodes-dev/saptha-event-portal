import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models_pg import Base
import db_pg
from db_adapter import SQLFirestoreAdapter


@pytest.fixture(scope="function", autouse=True)
def setup_test_db(monkeypatch):
    """Set up an in-memory SQLite database patched into db_pg for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    monkeypatch.setattr(db_pg, "_engine", engine)
    monkeypatch.setattr(db_pg, "_SessionLocal", SessionLocal)

    yield engine

    Base.metadata.drop_all(engine)


def test_event_registration_count_and_archived_status():
    adapter = SQLFirestoreAdapter()
    today = datetime.date.today().strftime('%Y-%m-%d')
    # 1. Create event with registration_count
    event_ref = adapter.collection('events').document('test-event-lifecycle-1')
    event_ref.set({
        'title': 'Lifecycle Test Event',
        'category': 'Technical',
        'date': today,
        'venue': 'Lab 1',
        'status': 'active',
        'registration_count': 42,
    })

    # Read back
    doc = event_ref.get()
    assert doc.exists
    data = doc.to_dict()
    assert data['registration_count'] == 42
    assert data['status'] == 'active'

    # Update status to archived
    event_ref.update({'status': 'archived'})
    doc = event_ref.get()
    assert doc.to_dict()['status'] == 'archived'


def test_event_query_date_pushdown_and_ordering():
    adapter = SQLFirestoreAdapter()
    today = datetime.date.today()
    past_date = (today - datetime.timedelta(days=5)).strftime('%Y-%m-%d')
    future_date1 = (today + datetime.timedelta(days=2)).strftime('%Y-%m-%d')
    future_date2 = (today + datetime.timedelta(days=5)).strftime('%Y-%m-%d')

    adapter.collection('events').document('test-past-evt').set({
        'title': 'Past Event', 'category': 'Technical', 'date': past_date, 'venue': 'V1', 'status': 'active'
    })
    adapter.collection('events').document('test-future-evt-2').set({
        'title': 'Future Event 2', 'category': 'Technical', 'date': future_date2, 'venue': 'V2', 'status': 'active'
    })
    adapter.collection('events').document('test-future-evt-1').set({
        'title': 'Future Event 1', 'category': 'Technical', 'date': future_date1, 'venue': 'V1', 'status': 'active'
    })

    # Query with date pushdown >= today
    today_str = today.strftime('%Y-%m-%d')
    results = list(
        adapter.collection('events')
        .where('status', '==', 'active')
        .where('date', '>=', today_str)
        .order_by('date')
        .stream()
    )

    result_titles = [r.to_dict()['title'] for r in results]
    assert 'Past Event' not in result_titles
    assert 'Future Event 1' in result_titles
    assert 'Future Event 2' in result_titles

    # Verify order: earliest first
    idx1 = result_titles.index('Future Event 1')
    idx2 = result_titles.index('Future Event 2')
    assert idx1 < idx2
