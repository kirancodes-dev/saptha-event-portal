"""
tests/test_feedback.py — UPG-05 on the real database layer: feedback opens
after check-in, each attendee (lead or team member) answers once, and the
event's staff read a summary and export it; nobody else can.
"""
import csv
import datetime
import io

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def fb(real_app):
    flask_app, db = real_app
    p = {k: f"{_unique(k)}@test.edu" for k in ('owner', 'other_spoc', 'lead', 'mate1', 'mate2', 'absent', 'outsider')}
    _user(db, p['owner'], 'ClubSPOC')
    _user(db, p['other_spoc'], 'ClubSPOC')
    for key in ('lead', 'mate1', 'mate2', 'absent', 'outsider'):
        _user(db, p[key], 'Student')
    owner = _login(flask_app, p['owner'], 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Feedback Fest'), datetime.date.today().isoformat(), team=True)
    team = _unique('REG')
    db.collection('registrations').document(team).set({
        'reg_id': team, 'event_id': event_id, 'lead_name': 'Lia Lead', 'lead_email': p['lead'], 'team_name': 'Owls',
        'attendance': 'Present', 'payment_status': 'Free', 'members': [
            {'role': 'Lead', 'name': 'Lia Lead', 'email': p['lead'], 'usn': 'U1', 'attendance': 'Present'},
            {'role': 'Member', 'name': 'Mo One', 'email': p['mate1'], 'usn': 'U2', 'attendance': 'Present'},
            {'role': 'Member', 'name': 'Mia Two', 'email': p['mate2'], 'usn': 'U3', 'attendance': 'Present'}]})
    absent = _unique('REG')
    db.collection('registrations').document(absent).set({
        'reg_id': absent, 'event_id': event_id, 'lead_name': 'Ab Sent', 'lead_email': p['absent'],
        'team_name': 'Ghosts', 'attendance': 'Pending', 'payment_status': 'Free', 'members': []})
    return {'app': flask_app, 'db': db, 'p': p, 'owner': owner, 'event_id': event_id, 'team': team, 'absent': absent}


def _student(d, key):
    return _login(d['app'], d['p'][key], 'Student')


def _send(client, reg_id, rating, comment):
    return client.post(f'/participant/feedback/{reg_id}', data={'rating': str(rating), 'comments': comment})


def _responses(d):
    return [doc.to_dict() for doc in d['db'].collection('feedback_responses').where('event_id', '==', d['event_id']).stream()]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_an_attendee_sends_feedback_and_staff_read_it_back(fb):
    d = fb
    lead = _student(d, 'lead')
    assert lead.get(f"/participant/feedback/{d['team']}").status_code == 200
    assert _send(lead, d['team'], 5, 'Loved the finals').status_code == 302
    [response] = _responses(d)
    assert response['rating'] == 5 and response['email'] == d['p']['lead'] and response['name'] == 'Lia Lead'
    assert d['db'].collection('registrations').document(d['team']).get().to_dict()['feedback']['rating'] == 5

    page = d['owner'].get(f"/feedback/view/{d['event_id']}", follow_redirects=True)
    assert page.status_code == 200 and 'Loved the finals' in page.get_data(as_text=True)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_summary_works_with_no_responses_and_with_three(fb):
    d = fb
    empty = d['owner'].get(f"/feedback/analytics/{d['event_id']}")
    assert empty.status_code == 200
    for key, rating in (('lead', 5), ('mate1', 4), ('mate2', 2)):  # each team member answers for themselves
        assert _send(_student(d, key), d['team'], rating, f'From {key}').status_code == 302
    assert len(_responses(d)) == 3
    page = d['owner'].get(f"/feedback/analytics/{d['event_id']}")
    html = page.get_data(as_text=True)
    assert page.status_code == 200 and all(f'From {k}' in html for k in ('lead', 'mate1', 'mate2'))
    summary = d['owner'].get(f"/feedback/summary/{d['event_id']}").get_json()
    assert summary['total_reviews'] == 3 and summary['avg_rating'] == 3.7


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_someone_not_on_the_registration_gets_403(fb):
    d = fb
    outsider = _student(d, 'outsider')
    assert outsider.get(f"/participant/feedback/{d['team']}").status_code == 403
    assert _send(outsider, d['team'], 1, 'Hijack').status_code == 403
    assert _responses(d) == []


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_old_submit_url_redirects_to_the_one_route(fb):
    d = fb
    resp = _student(d, 'lead').post(f"/feedback/submit/{d['team']}", data={'rating': '4'})
    assert resp.status_code == 307 and resp.headers['Location'].endswith(f"/participant/feedback/{d['team']}")


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_feedback_needs_check_in_and_each_person_answers_once(fb):
    d = fb
    absent = _student(d, 'absent')
    assert _send(absent, d['absent'], 3, 'Never came').status_code == 302
    assert _responses(d) == []

    lead = _student(d, 'lead')
    _send(lead, d['team'], 5, 'First answer')
    resp = _send(lead, d['team'], 1, 'Changed my mind')
    assert resp.status_code == 302
    [response] = _responses(d)
    assert response['rating'] == 5 and response['comments'] == 'First answer'

    # A team member marked absent at the door can't answer either
    reg = d['db'].collection('registrations').document(d['team']).get().to_dict()
    reg['members'][2]['attendance'] = 'Absent'
    d['db'].collection('registrations').document(d['team']).update({'members': reg['members']})
    _send(_student(d, 'mate2'), d['team'], 4, 'Was not there')
    assert len(_responses(d)) == 1


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_the_export_has_one_row_per_response_for_the_events_staff_only(fb):
    d = fb
    for key, rating in (('lead', 5), ('mate1', 3)):
        _send(_student(d, key), d['team'], rating, f'Row {key}')
    resp = d['owner'].get(f"/feedback/export/{d['event_id']}")
    assert resp.status_code == 200 and resp.mimetype == 'text/csv'
    rows = list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))
    assert sorted((r['Email'], r['Rating'], r['Comments']) for r in rows) == sorted([
        (d['p']['lead'], '5', 'Row lead'), (d['p']['mate1'], '3', 'Row mate1')])
    assert all(r['Team'] == 'Owls' for r in rows)

    other = _login(d['app'], d['p']['other_spoc'], 'ClubSPOC')
    for client in (other, _student(d, 'lead')):
        assert client.get(f"/feedback/export/{d['event_id']}").status_code in (302, 403)
    assert other.get(f"/feedback/export/{d['event_id']}").status_code == 403
    assert other.get(f"/feedback/analytics/{d['event_id']}").status_code == 403
    assert other.get(f"/feedback/summary/{d['event_id']}").status_code == 403


# ── "Require feedback before the certificate", per person ──────────────────

def test_the_certificate_rule_asks_each_member_for_their_own_feedback(fb):
    d = fb
    d['db'].collection('events').document(d['event_id']).update({
        'status': 'completed', 'workflow_config': {'rules': {'require_feedback_for_certificate': True}}})
    lead, mate = _student(d, 'lead'), _student(d, 'mate1')
    _send(lead, d['team'], 5, 'Done')
    assert lead.get(f"/participant/certificate/{d['team']}").status_code == 200
    resp = mate.get(f"/participant/certificate/{d['team']}")
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f"/participant/feedback/{d['team']}")
    _send(mate, d['team'], 4, 'Me too')
    assert mate.get(f"/participant/certificate/{d['team']}").status_code == 200
