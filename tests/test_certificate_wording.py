"""
tests/test_certificate_wording.py — what an issued certificate's PDF says, on
the real database layer: the event's hours (UPG-130).
"""
import pytest

import certificate_pdf
import services_certificates as certs
from tests.test_certificate_types import _signature
from tests.test_integration_flow import _create_event, _login, _unique, _user
from utils_storage import get_private


@pytest.fixture
def issue(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('wordspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')

    def run(registration, **fields):
        import services_signatories
        event_id = _create_event(owner, db, _unique('Worded Event'), '2031-07-07', team=False)
        db.collection('events').document(event_id).update(dict({'status': 'completed', 'staff': []}, **fields))
        services_signatories.add(db, event_id, name='Dr. A. Kumar', title='Principal', image=_signature(), actor=spoc)
        db.collection('registrations').document(_unique('REG')).set(dict({
            'event_id': event_id, 'lead_email': f"{_unique('word')}@test.edu", 'status': 'Confirmed',
            'attendance': 'Present'}, **registration))
        certs.issue_event(db, event_id, spoc)
        [cert] = [c for c in certs.for_event(event_id) if c['name'] == registration['lead_name']]
        return event_id, cert, ' '.join(certificate_pdf.text_of(get_private(cert['pdf_key'])).split())
    return {'app': flask_app, 'db': db, 'owner': owner, 'run': run}


def test_upg130_the_hours_are_in_the_pdf(issue):
    _, cert, text = issue['run']({'lead_name': 'Hari Hours'}, activity_hours=12, activity_points=5)
    assert '12 hours' in text and '5 activity points' in text and 'Hari Hours' in text
