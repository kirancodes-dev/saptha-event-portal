"""
tests/test_form_submission_documents.py — UPG-45 on the real database layer:
a form submission reads back as it was written (who, when, and the answers
nested under 'answers'), on SQLite and PostgreSQL. Before, the SQL adapter
kept only the answers and returned them flattened, so the responses page and
the forms export showed empty answers.
"""
import datetime
import json

from db_adapter import to_uuid
from tests.test_integration_flow import _create_event, _login, _unique, _user
from utils import record_form_submission


def _event_and_registration(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('subspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Form Night'),
                             datetime.date.today().isoformat(), team=False)
    reg_id = _unique('REG')
    db.collection('registrations').document(reg_id).set({'reg_id': reg_id, 'event_id': event_id,
                                                         'lead_name': 'Sam', 'lead_email': 'sam@test.edu'})
    return db, event_id, reg_id


def _submissions(db, event_id):
    return [d for d in db.collection('form_submissions').where('event_id', '==', event_id).stream()]


def test_a_submission_reads_back_whole(real_app):
    db, event_id, reg_id = _event_and_registration(real_app)
    answers = {'full_name': 'Sam Sub', 'email': 'sam@test.edu', 'tshirt': 'L', 'topics': ['AI', 'Web']}
    record_form_submission(db, event_id, reg_id, 'sam@test.edu', 'Sam Sub', answers)

    docs = _submissions(db, event_id)
    assert len(docs) == 1
    doc = docs[0].to_dict()
    assert doc['answers'] == answers
    assert doc['name'] == 'Sam Sub' and doc['email'] == 'sam@test.edu' and doc['reg_id'] == reg_id
    assert doc['submitted_at'][:10] == datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    assert to_uuid(doc['event_id']) == to_uuid(event_id)

    # An update changes only what it names
    docs[0].reference.update({'reviewed': True})
    again = _submissions(db, event_id)[0].to_dict()
    assert again['answers'] == answers and again['reviewed'] is True and again['name'] == 'Sam Sub'


def test_a_row_stored_before_the_fix_reads_back_as_answers(real_app):
    db, event_id, reg_id = _event_and_registration(real_app)
    from db_pg import get_session
    from models_pg import FormSubmission
    with get_session() as s:
        s.add(FormSubmission(event_id=to_uuid(event_id), registration_id=to_uuid(reg_id),
                             answers_json=json.dumps({'full_name': 'Old Row', 'tshirt': 'S'}),
                             submitted_at=datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)))
    doc = _submissions(db, event_id)[0].to_dict()
    assert doc['answers'] == {'full_name': 'Old Row', 'tshirt': 'S'}
    assert doc['submitted_at'].startswith('2026-09-01')
