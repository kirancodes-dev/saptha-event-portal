"""
tests/test_member_dashboard.py — UPG-227 on the real database layer: a team
member who signs in sees their team's registration on their dashboard (the
event, the team and its lead, the ticket, the team page, their own attendance
and certificate), without the lead-only actions; the lead's dashboard is as
before.
"""
import services_team_confirm as confirm
from routes_participant import member_registrations
from tests import test_registration_edit as _edit
from tests.test_integration_flow import _login, _user

team = _edit.team   # the lead Lena, members Hima and Alif (UPG-225's fixture)
_reg = _edit._reg


def _dash(client):
    resp = client.get('/participant/dashboard')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _as(t, email):
    _user(t['db'], email, 'Student')
    return _login(t['app'], email, 'Student')


def _title(t):
    return t['db'].collection('events').document(t['event_id']).get().to_dict()['title']


def test_a_member_sees_their_teams_registration_without_the_leads_actions(team):
    t = team
    hima = _as(t, t['hima'])
    html = _dash(hima)
    rid = t['reg_id']
    assert _title(t) in html
    assert 'data-my-team="member"' in html and 'Apex' in html and 'led by Lena Lead' in html
    assert 'data-ask-lead' in html and t['lead'] in html
    for link in (f'/ticket/{rid}', f'/teams/{rid}', f'/participant/badge/{rid}', f"/event/{t['event_id']}"):
        assert f'href="{link}"' in html, link
    assert '(you)' in html
    # Only the lead cancels, edits and opens the hackathon page
    assert f'/participant/cancel/{rid}' not in html
    assert 'data-edit-details' not in html and 'data-hackathon-page' not in html
    # Not offered as an event to register for
    assert f"/forms/register/{t['event_id']}" not in html
    # The links open for them
    assert hima.get(f'/ticket/{rid}').status_code == 200
    assert hima.get(f'/teams/{rid}').status_code == 200


def test_the_leads_dashboard_keeps_their_actions(team):
    t = team
    html = _dash(t['lead_client'])
    rid = t['reg_id']
    assert 'data-my-team="lead"' in html and _reg(t)['team_code'] in html
    assert f'/participant/cancel/{rid}' in html and 'data-edit-details' in html
    assert f'href="/teams/{rid}"' in html and 'data-ask-lead' not in html
    assert html.count(f'href="/ticket/{rid}"') == 1      # listed once, as the lead's


def test_a_members_own_attendance_and_certificate(team):
    t, db = team, team['db']
    hima, alif = _as(t, t['hima']), _as(t, t['alif'])
    assert t['spoc'].post(f"/spoc/api/checkin/{t['event_id']}/{t['reg_id']}", json={'round': 1}).status_code == 200
    confirm.update_member(db, t['reg_id'], t['hima'], lambda m: {'attendance': 'Absent'})
    assert 'ticket-chip-absent' in _dash(hima)
    assert 'ticket-chip-attended' in _dash(alif)       # nothing recorded for Alif: the team's

    db.collection('events').document(t['event_id']).update({'status': 'completed'})
    certificate = f"/participant/certificate/{t['reg_id']}"
    assert certificate not in _dash(hima)
    assert certificate in _dash(alif)


def test_only_people_on_the_team_see_it_and_a_cancelled_one_is_past(team):
    t, db = team, team['db']
    alif = _as(t, t['alif'])
    ticket = f"/ticket/{t['reg_id']}"
    assert ticket in _dash(alif)
    assert t['lead_client'].post(f"/teams/{t['reg_id']}/remove", data={'email': t['alif']}).status_code == 302
    html = _dash(alif)
    assert ticket not in html and 'data-my-team' not in html
    assert ticket not in _dash(_as(t, 'nobody.on.it@test.edu'))

    hima = _as(t, t['hima'])
    db.collection('registrations').document(t['reg_id']).update({'status': 'Cancelled'})
    html = _dash(hima)
    assert _title(t) in html and 'ticket-chip-cancelled' in html and 'data-ask-lead' not in html


def test_my_events_lists_a_members_team_with_their_own_attendance(team):
    t, db = team, team['db']
    hima, alif = _as(t, t['hima']), _as(t, t['alif'])

    def ids(client, tab):
        return [r['id'] for r in client.get('/participant/api/my_events').get_json()[tab]]

    assert t['reg_id'] in ids(hima, 'registered') and t['reg_id'] in ids(hima, 'upcoming')
    assert ids(t['lead_client'], 'registered').count(t['reg_id']) == 1
    assert t['spoc'].post(f"/spoc/api/checkin/{t['event_id']}/{t['reg_id']}", json={'round': 1}).status_code == 200
    confirm.update_member(db, t['reg_id'], t['hima'], lambda m: {'attendance': 'Absent'})
    assert t['reg_id'] not in ids(hima, 'attended')
    assert t['reg_id'] in ids(alif, 'attended')
    assert t['reg_id'] in ids(t['lead_client'], 'attended')
    assert 'Edit Hack' in alif.get('/participant/my_events').get_data(as_text=True)


def test_the_lookup_finds_member_rows_not_the_leads(team):
    t = team
    with t['app'].app_context():
        assert [rid for rid, _ in member_registrations(t['hima'].upper())] == [t['reg_id']]
        assert member_registrations(t['lead']) == []
        assert member_registrations('') == []
