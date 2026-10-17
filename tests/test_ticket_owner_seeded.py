"""
tests/test_ticket_owner_seeded.py — UPG-69 (ticket part; certificate
verification is deferred with certificates): a registration written straight
into the table, as seed.py does, still belongs to its student. They open
/ticket/<their registration> (200) and see their name.
"""
import uuid

from tests.test_integration_flow import _create_event, _login, _unique, _user


def test_a_student_opens_their_seeded_registrations_ticket_and_sees_their_name(real_app):
    from db_pg import get_session
    from db_adapter import to_uuid
    from models_pg import Registration
    flask_app, db = real_app
    spoc, student = f"{_unique('seedspoc')}@test.edu", f"{_unique('seeded')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, student, 'Student')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Seeded Day'), '2030-06-01', team=False)

    reg_uuid = uuid.uuid4()
    with get_session() as s:     # the columns only, no stored document: what seed.py writes
        s.add(Registration(id=reg_uuid, event_id=to_uuid(event_id), lead_name='Meera Seeded',
                           lead_email=student, lead_phone='9876543210'))
    reg = db.collection('registrations').document(str(reg_uuid)).get().to_dict()
    assert reg['lead_email'] == student and reg['lead_name'] == 'Meera Seeded'

    resp = _login(flask_app, student, 'Student').get(f'/ticket/{reg_uuid}')
    assert resp.status_code == 200, resp.headers.get('Location')
    assert 'Meera Seeded' in resp.get_data(as_text=True)
    # Someone else is still refused
    other = f"{_unique('notmine')}@test.edu"
    _user(db, other, 'Student')
    assert _login(flask_app, other, 'Student').get(f'/ticket/{reg_uuid}').status_code == 302
