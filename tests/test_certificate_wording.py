"""
tests/test_certificate_wording.py — what an issued certificate's PDF says, on
the real database layer: the event's hours (UPG-130), a faculty member's
designation and institution on an FDP certificate (UPG-131), and no invented
venue on a certificate, its preview (UPG-136) or the participant's certificate
page (UPG-141).
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


def test_upg131_an_fdp_certificate_shows_designation_and_institution(issue):
    _, cert, text = issue['run']({'lead_name': 'Dr. Meera Iyer', 'designation': 'Assistant Professor',
                                  'institution': 'Example College of Engineering'}, event_type='fdp', activity_hours=30)
    assert cert['cert_type'] == 'completion'
    assert 'Dr. Meera Iyer' in text and 'Assistant Professor, Example College of Engineering' in text
    assert '30 hours' in text


def test_upg136_no_certificate_page_or_pdf_invents_a_venue(issue):
    db, client = issue['db'], issue['owner']
    event_id, cert, text = issue['run']({'lead_name': 'Vera Venueless'}, venue='', room_name='', event_mode='offline')
    assert 'Main Campus' not in text
    reg_id = _unique('REG')
    db.collection('registrations').document(reg_id).set({
        'event_id': event_id, 'lead_name': 'Legacy Lee', 'lead_email': f"{_unique('lee')}@test.edu",
        'status': 'Confirmed', 'attendance': 'Present'})
    old_hash = 'a' * 63 + 'b'
    db.collection('verified_certificates').document(old_hash).set({
        'student_name': 'Hashed Hana', 'event_title': 'Worded Event', 'event_id': event_id,
        'cert_type': 'participation', 'issued_at': '2031-07-07T10:00:00'})
    for path in (f'/verify/{reg_id}/preview', f'/verify/{old_hash}/preview'):
        page = client.get(path).get_data(as_text=True)
        assert 'Main Campus' not in page and 'Venue to be announced' in page, path
    db.collection('events').document(event_id).update({'event_mode': 'online'})
    assert 'Online' in client.get(f'/verify/{old_hash}/preview').get_data(as_text=True)


def test_upg141_the_participant_certificate_page_never_says_at_nothing(issue):
    db = issue['db']
    from tests.test_integration_flow import _login, _user
    event_id, cert, _ = issue['run']({'lead_name': 'Nila Noplace', 'lead_email': f"{_unique('nila')}@test.edu"},
                                     venue='', room_name='', event_mode='offline')
    _user(db, cert['email'], 'Student')
    student = _login(issue['app'], cert['email'], 'Student')
    page = student.get(f"/participant/certificate/{cert['reg_id']}").get_data(as_text=True)
    assert 'at Venue to be announced.' in page and 'at .' not in page
    db.collection('events').document(event_id).update({'event_mode': 'online'})
    assert 'at Online.' in student.get(f"/participant/certificate/{cert['reg_id']}").get_data(as_text=True)
