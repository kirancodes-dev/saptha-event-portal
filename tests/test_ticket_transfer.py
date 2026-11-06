"""
tests/test_ticket_transfer.py — UPG-161: the lead hands a ticket to someone
else. The old ticket stops working at every scanner and the new holder's
works; ineligible recipients, the cut-off, events without transfers, team
members and a recipient who would pay more are all refused.
"""
import datetime

import pytest

import services_transfer
from routes_ticket import ticket_token_for
from tests.test_integration_flow import _create_event, _login, _unique, _user


def _person(db, flask_app, name, **profile):
    email = f"{_unique(name)}@test.edu"
    _user(db, email, 'Student', name=name.title())
    if profile:
        db.collection('users').document(email).update(profile)
    return email, _login(flask_app, email, 'Student')


@pytest.fixture
def trip(real_app):
    """A future event that allows transfers, a registrant and their ticket."""
    flask_app, db = real_app
    owner = f"{_unique('trspoc')}@test.edu"
    coord = f"{_unique('trcoord')}@test.edu"
    _user(db, owner, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    spoc = _login(flask_app, owner, 'ClubSPOC')
    event_id = _create_event(spoc, db, _unique('Transfer Fest'), '2030-08-01', fee=0, team=False)
    db.collection('events').document(event_id).update({
        'status': 'registration_open', 'transfers_allowed': True, 'transfer_cutoff_hours': 24,
        'staff': [{'name': 'C', 'email': coord, 'role': 'EventCoordinator'}]})
    holder, holder_client = _person(db, flask_app, 'hana')
    assert holder_client.post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Hana Holder', 'email': holder, 'phone': '9876543210',
        'usn': '1SN22CS010'}).status_code == 302
    reg_doc = next(iter(db.collection('registrations').where('event_id', '==', event_id).stream()))
    return {'app': flask_app, 'db': db, 'event_id': event_id, 'reg_id': reg_doc.id, 'holder': holder,
            'holder_client': holder_client, 'staff': _login(flask_app, coord, 'EventCoordinator'), 'spoc': spoc}


def _reg(t):
    return t['db'].collection('registrations').document(t['reg_id']).get().to_dict()


def _token(t):
    with t['app'].app_context():
        return ticket_token_for(t['reg_id'], _reg(t))


def _transfer(t, client, email, reg_id=None):
    return client.post(f"/participant/transfer/{reg_id or t['reg_id']}", data={'email': email, 'confirm': 'yes'})


def _scan(t, token):
    return t['staff'].post('/ticket/api/checkin', json={'token': token, 'event_id': t['event_id']})


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_after_a_transfer_the_old_ticket_is_refused_and_the_new_one_works(trip):
    t = trip
    old_token = _token(t)
    with t['app'].app_context():   # an untransferred ticket's token is exactly what it always was
        from routes_ticket import generate_ticket_token
        assert old_token == generate_ticket_token(t['reg_id'], t['event_id'], 'Hana Holder')
    assert 'data-transfer-link' in t['holder_client'].get(f"/ticket/{t['reg_id']}").get_data(as_text=True)

    new_email, new_client = _person(t['db'], t['app'], 'neel', usn='1SN22CS099', phone='9000000001')
    resp = _transfer(t, t['holder_client'], new_email)
    assert resp.status_code == 302
    reg = _reg(t)
    assert reg['lead_email'] == new_email and reg['lead_name'] == 'Neel' and reg['ticket_gen'] == 1
    assert reg['transfers'][0]['from'] == t['holder'] and reg['transfers'][0]['to'] == new_email
    assert [m['email'] for m in reg['members']] == [new_email]

    # The old QR is refused everywhere: scanner, verify page, verify API, session scan
    refused = _scan(t, old_token)
    assert refused.status_code == 409 and refused.get_json()['status'] == 'transferred'
    assert t['staff'].post(f'/ticket/verify/{old_token}').status_code == 200   # the page says why…
    assert _reg(t).get('attendance') != 'Present'                               # …and marks nobody
    assert t['staff'].get(f'/ticket/verify/{old_token}').status_code == 409
    assert t['staff'].post(f'/ticket/api/verify/{old_token}').status_code == 409

    new_token = _token(t)
    assert new_token != old_token
    ok = _scan(t, new_token)
    assert ok.status_code == 200 and ok.get_json()['status'] == 'success' and ok.get_json()['name'] == 'Neel'

    # The new holder sees the ticket; the old holder no longer does
    assert new_client.get(f"/ticket/{t['reg_id']}").status_code == 200
    assert t['holder_client'].get(f"/ticket/{t['reg_id']}").status_code in (302, 403)
    logs = [d.to_dict() for d in t['db'].collection('audit_log').stream()]
    assert any(t['reg_id'] in str(entry.get('details') or entry.get('message') or entry)
               and 'TICKET_TRANSFERRED' in str(entry) for entry in logs)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_an_ineligible_recipient_is_refused(trip):
    t = trip
    before = _reg(t)

    # Campus-only: a students-only event can't go to an external participant
    guest, _ = _person(t['db'], t['app'], 'gita', participant_type='external', institution='Elsewhere')
    resp = _transfer(t, t['holder_client'], guest)
    assert resp.status_code == 303
    assert 'This event is for students only' in t['holder_client'].get(resp.location).get_data(as_text=True)

    # Placement rules: the recipient's own record decides
    t['db'].collection('events').document(t['event_id']).update(
        {'is_placement': True, 'placement': {'branches': ['CSE'], 'min_cgpa': 7.0}})
    mech, _ = _person(t['db'], t['app'], 'mani', department='MECH', cgpa=9.1)
    low, _ = _person(t['db'], t['app'], 'lata', department='CSE', cgpa=6.2)
    for email, why in ((mech, 'This drive is for CSE students'), (low, 'CGPA of at least 7')):
        resp = _transfer(t, t['holder_client'], email)
        assert resp.status_code == 303
        assert why in t['holder_client'].get(resp.location).get_data(as_text=True)

    # No account, someone already registered, and one's own email
    nobody = f"{_unique('ghost')}@test.edu"
    assert _transfer(t, t['holder_client'], nobody).status_code == 303
    assert _transfer(t, t['holder_client'], t['holder']).status_code == 303
    assert _reg(t)['lead_email'] == before['lead_email'] and not _reg(t).get('ticket_gen')


def test_a_recipient_who_would_pay_more_is_refused(trip):
    t = trip
    t['db'].collection('events').document(t['event_id']).update(
        {'allowed_participants': ['student', 'faculty'], 'fees': {'regular': 0, 'student': 0, 'faculty': 500}})
    prof, _ = _person(t['db'], t['app'], 'prof', participant_type='faculty', institution='SNPSU',
                      designation='Professor')
    resp = _transfer(t, t['holder_client'], prof)
    assert resp.status_code == 303
    assert 'would pay Rs 500' in t['holder_client'].get(resp.location).get_data(as_text=True)
    assert _reg(t)['lead_email'] == t['holder']


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_after_the_cut_off_or_without_transfers_it_is_refused(trip, monkeypatch):
    t = trip
    friend, _ = _person(t['db'], t['app'], 'fara')
    start = datetime.datetime(2030, 8, 1, 10, 0, tzinfo=services_transfer.IST)

    monkeypatch.setattr(services_transfer, '_now', lambda: start - datetime.timedelta(hours=23))
    page = t['holder_client'].get(f"/participant/transfer/{t['reg_id']}").get_data(as_text=True)
    assert 'Transfers for this event have closed' in page and 'name="email"' not in page
    assert _transfer(t, t['holder_client'], friend).status_code == 303
    assert _reg(t)['lead_email'] == t['holder']

    monkeypatch.setattr(services_transfer, '_now', lambda: start - datetime.timedelta(hours=25))
    t['db'].collection('events').document(t['event_id']).update({'transfers_allowed': False})
    assert 'allow ticket transfers' in t['holder_client'].get(
        f"/participant/transfer/{t['reg_id']}").get_data(as_text=True)
    assert _transfer(t, t['holder_client'], friend).status_code == 303
    assert 'data-transfer-link' not in t['holder_client'].get(f"/ticket/{t['reg_id']}").get_data(as_text=True)
    assert _reg(t)['lead_email'] == t['holder']

    # Allowed and before the cut-off it goes through
    t['db'].collection('events').document(t['event_id']).update({'transfers_allowed': True})
    assert _transfer(t, t['holder_client'], friend).status_code == 302
    assert _reg(t)['lead_email'] == friend


def test_the_wizard_saves_the_transfer_settings(trip):
    import services_event_types
    from werkzeug.datastructures import MultiDict
    base = {'event_type': 'workshop', 'title': 'W', 'date': '2030-09-01', 'time': '10:00', 'venue': 'Hall',
            'description': 'd', 'reg_deadline': '2030-08-30'}
    data, _, _ = services_event_types.parse_form(MultiDict(dict(base, transfers_allowed='on', transfer_cutoff_hours='48')))
    assert data['transfers_allowed'] is True and data['transfer_cutoff_hours'] == 48
    data, _, _ = services_event_types.parse_form(MultiDict(base))
    assert data['transfers_allowed'] is False and data['transfer_cutoff_hours'] == 24
    _, errors, _ = services_event_types.parse_form(MultiDict(dict(base, transfer_cutoff_hours='9999')))
    assert any('720 hours' in e for e in errors)
    assert services_event_types.form_values({'fees': {'regular': 0}, 'transfers_allowed': True, 'transfer_cutoff_hours': 6})[
        'transfer_cutoff_hours'] == '6'


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_only_the_lead_transfers_a_team_registration(trip):
    t = trip
    mate, mate_client = _person(t['db'], t['app'], 'mira')
    t['db'].collection('registrations').document(t['reg_id']).update({
        'team_name': 'Byte Force',
        'members': [{'role': 'Lead', 'name': 'Hana Holder', 'email': t['holder']},
                    {'role': 'Member', 'name': 'Mira', 'email': mate}]})
    friend, _ = _person(t['db'], t['app'], 'fynn')

    page = mate_client.get(f"/participant/transfer/{t['reg_id']}").get_data(as_text=True)
    assert 'Only the person who registered can transfer this ticket' in page
    assert _transfer(t, mate_client, friend).status_code == 303
    assert _reg(t)['lead_email'] == t['holder']
    assert 'data-transfer-link' not in mate_client.get(f"/ticket/{t['reg_id']}").get_data(as_text=True)
    stranger, stranger_client = _person(t['db'], t['app'], 'sam')
    assert _transfer(t, stranger_client, friend).status_code == 403

    # The lead can: the new person takes the lead's place and the team stays
    assert _transfer(t, t['holder_client'], friend).status_code == 302
    reg = _reg(t)
    assert reg['lead_email'] == friend and reg['team_name'] == 'Byte Force'
    assert [(m['role'], m['email']) for m in reg['members']] == [('Lead', friend), ('Member', mate)]
