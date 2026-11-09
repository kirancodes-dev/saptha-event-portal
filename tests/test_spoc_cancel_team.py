"""
tests/test_spoc_cancel_team.py — UPG-211 on the real database layer: the SPOC
who hosts an event cancels a team's registration, with a reason, until the
team is checked in. The seat is freed, the ticket is refused at the scanner,
everyone on the team gets a portal notice and the lead an email (none in a
portal-mode hackathon). Another SPOC and the event's coordinator get 403.
"""
import datetime

import pytest

import utils_email
from routes_ticket import generate_ticket_token
from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def host(real_app, monkeypatch):
    flask_app, db = real_app
    emails = []
    monkeypatch.setattr(utils_email, 'send_email_notification',
                        lambda to, subject, message, event_name='': emails.append(
                            {'to': to, 'subject': subject, 'message': message}) or True)
    spoc = f"{_unique('cxspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()

    def event(**fields):
        event_id = _create_event(owner, db, _unique('Cancel Cup'), day, team=True)
        db.collection('events').document(event_id).update(
            dict({'status': 'registration_open', 'venue': 'Hall A', 'member_confirm': False}, **fields))
        return event_id

    def register(event_id, team_name='Byte Force'):
        lead, mate = f"{_unique('lead')}@test.edu", f"{_unique('mate')}@test.edu"
        resp = flask_app.test_client().post(f'/forms/submit/{event_id}', data={
            'privacy_consent': 'yes', 'full_name': 'Lena Lead', 'email': lead, 'phone': '9876543210',
            'usn': '1SN22CS300', 'team_name': team_name,
            'member_1_name': 'Mo Mate', 'member_1_email': mate, 'member_1_usn': '1SN22CS301'})
        assert resp.status_code == 302, resp.data[:300]
        [reg_id] = [d.id for d in db.collection('registrations').where('event_id', '==', event_id).stream()
                    if d.to_dict().get('lead_email') == lead]
        return reg_id, lead, mate

    def cancel(client, event_id, reg_id, reason='Duplicate team'):
        return client.post(f'/coordinator/registrations/{event_id}/cancel_team',
                           data={'reg_id': reg_id, 'reason': reason})

    def reg(reg_id):
        return db.collection('registrations').document(reg_id).get().to_dict()

    def count(event_id):
        return int(db.collection('events').document(event_id).get().to_dict().get('registration_count') or 0)

    return {'app': flask_app, 'db': db, 'owner': owner, 'spoc': spoc, 'event': event, 'register': register,
            'cancel': cancel, 'reg': reg, 'count': count, 'emails': emails}


def _notices(db, email):
    return [n.to_dict() for n in db.collection('notifications_v2').stream()
            if n.to_dict().get('user_email') == email and n.to_dict().get('type') == 'cancellation']


def _scan(h, client, event_id, reg_id):
    with h['app'].app_context():
        token = generate_ticket_token(reg_id, event_id, 'Lena Lead')
    return client.post('/ticket/api/checkin', json={'token': token, 'event_id': event_id, 'source': 'scan'})


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_hosting_spoc_cancels_a_team_and_its_seat_ticket_and_people_follow(host):
    h = host
    db = h['db']
    event_id = h['event']()
    reg_id, lead, mate = h['register'](event_id)
    keep_id, _, _ = h['register'](event_id, team_name='Keepers')
    before = h['count'](event_id)

    resp = h['cancel'](h['owner'], event_id, reg_id, 'Registered twice')
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/coordinator/registrations/{event_id}')
    r = h['reg'](reg_id)
    assert r['status'].lower() == 'cancelled' and r['cancel_reason'] == 'Registered twice'
    assert r['cancelled_by'] == h['spoc'] and r['cancelled_at']
    assert h['count'](event_id) == before - 1                       # the seat is free
    assert h['reg'](keep_id)['status'].lower() != 'cancelled'       # only that team

    # The ticket is refused at the scanner
    scan = _scan(h, h['owner'], event_id, reg_id)
    assert scan.status_code == 409 and scan.get_json()['status'] == 'cancelled'
    assert _scan(h, h['owner'], event_id, keep_id).status_code == 200

    # Everyone on the team is told, with the reason; the lead also by email
    for person in (lead, mate):
        [notice] = _notices(db, person)
        assert 'Registered twice' in notice['message']
    assert [e['to'] for e in h['emails']] == [lead] and 'Registered twice' in h['emails'][0]['message']

    # Audit-logged, with who and why
    assert any(a.to_dict().get('action') == 'REGISTRATION_CANCELLED'
               and reg_id in a.to_dict().get('details', '') and 'Registered twice' in a.to_dict().get('details', '')
               and h['spoc'] in a.to_dict().get('details', '') for a in db.collection('audit_log').stream())

    # A second press changes nothing (the seat isn't freed twice)
    h['cancel'](h['owner'], event_id, reg_id)
    assert h['count'](event_id) == before - 1 and len(h['emails']) == 1


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_only_the_hosting_spoc_may_cancel_and_the_page_shows_the_button_to_them_only(host):
    h = host
    db, flask_app = h['db'], h['app']
    event_id = h['event']()
    reg_id, _, _ = h['register'](event_id)

    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    coord = f"{_unique('coord')}@test.edu"
    _user(db, coord, 'EventCoordinator')
    db.collection('events').document(event_id).update({'coordinators': [coord]})
    coord_c = _login(flask_app, coord, 'EventCoordinator')
    assert h['cancel'](_login(flask_app, other, 'ClubSPOC'), event_id, reg_id).status_code == 403
    assert h['cancel'](coord_c, event_id, reg_id).status_code == 403
    assert h['reg'](reg_id)['status'].lower() != 'cancelled'

    owner_page = h['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert 'data-cancel-team' in owner_page and f'value="{reg_id}"' in owner_page
    coord_page = coord_c.get(f'/coordinator/registrations/{event_id}')
    assert coord_page.status_code == 200 and 'data-cancel-team' not in coord_page.get_data(as_text=True)

    # The SPOC's dashboard links to the page
    assert f'/coordinator/registrations/{event_id}' in h['owner'].get('/spoc/dashboard').get_data(as_text=True)


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_no_cancel_without_a_reason_after_check_in_or_for_another_events_team(host):
    h = host
    event_id, elsewhere = h['event'](), h['event']()
    reg_id, _, _ = h['register'](event_id)
    other_id, _, _ = h['register'](elsewhere)

    h['cancel'](h['owner'], event_id, reg_id, reason='  ')
    assert h['reg'](reg_id)['status'].lower() != 'cancelled'
    h['cancel'](h['owner'], event_id, other_id)                      # through the wrong event
    assert h['reg'](other_id)['status'].lower() != 'cancelled'

    assert _scan(h, h['owner'], event_id, reg_id).status_code == 200   # the team enters the hall
    page = h['owner'].get(f'/coordinator/registrations/{event_id}').get_data(as_text=True)
    assert "Checked in: can&#39;t be cancelled" in page or "Checked in: can't be cancelled" in page
    h['cancel'](h['owner'], event_id, reg_id)
    assert h['reg'](reg_id)['status'].lower() != 'cancelled'
    assert h['emails'] == []


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_a_portal_mode_hackathon_team_gets_portal_notices_and_no_email(host):
    h = host
    event_id = h['event'](event_type='hackathon', timezone='Asia/Kolkata')
    import services_hackathon as hk
    assert hk.portal_only(h['db'].collection('events').document(event_id).get().to_dict())
    reg_id, lead, mate = h['register'](event_id)
    h['emails'].clear()
    h['cancel'](h['owner'], event_id, reg_id, 'Not from this college')
    assert h['reg'](reg_id)['status'].lower() == 'cancelled'
    assert h['emails'] == []
    assert all(len(_notices(h['db'], p)) == 1 for p in (lead, mate))
