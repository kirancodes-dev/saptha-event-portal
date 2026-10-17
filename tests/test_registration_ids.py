"""
tests/test_registration_ids.py — UPG-95 on the real database layer:
registration IDs can't collide, even within one millisecond, and a new
registration is never written over an existing one.
"""
import time

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user
from utils import RegistrationExists, create_registration, generate_reg_id


@pytest.fixture
def event(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('idspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Id Day'), '2030-06-01', team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open'})
    return flask_app, db, event_id


def _form(email):
    return {'privacy_consent': 'yes', 'full_name': 'Id Test', 'email': email, 'phone': '9876543210', 'usn': '1SN20CS011'}


def test_two_registrations_in_the_same_millisecond_get_different_ids(event, monkeypatch):
    flask_app, db, event_id = event
    monkeypatch.setattr(time, 'time', lambda: 1_800_000_000.123)   # the clock stands still
    emails = [f"{_unique('same')}@test.edu" for _ in range(2)]
    for email in emails:
        resp = flask_app.test_client().post(f'/forms/submit/{event_id}', data=_form(email))
        assert resp.headers['Location'] == '/registration/confirmed'
    regs = {r.to_dict()['lead_email']: r.to_dict() for r in
            db.collection('registrations').where('event_id', '==', event_id).stream()}
    assert set(emails) <= set(regs)                      # both rows exist
    ids = [regs[e]['reg_id'] for e in emails]
    assert ids[0] != ids[1] and all(i.startswith('REG-') and len(i) == 24 for i in ids)


def test_a_new_registration_is_never_written_over_an_existing_one(event):
    _, db, event_id = event
    reg_id = generate_reg_id()
    create_registration(db, reg_id, {'reg_id': reg_id, 'event_id': event_id, 'lead_email': 'first@test.edu',
                                     'status': 'Confirmed'})
    with pytest.raises(RegistrationExists):
        create_registration(db, reg_id, {'reg_id': reg_id, 'event_id': event_id, 'lead_email': 'second@test.edu',
                                         'status': 'Confirmed'})
    assert db.collection('registrations').document(reg_id).get().to_dict()['lead_email'] == 'first@test.edu'


def test_ids_are_unique_in_bulk_and_waitlist_ids_too():
    ids = {generate_reg_id() for _ in range(5000)}
    assert len(ids) == 5000
    assert generate_reg_id('WL').startswith('WL-')
