"""
tests/test_rubric_judging.py — UPG-04 on the real database layer: judging works
with the rubric the create form saves ({name, max_score}); a score above the
criterion's maximum is refused; the judge's dashboard lists events in the newer
workflow states; scoring stops when the SPOC locks it.
"""
import datetime
import json

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def judged(real_app):
    flask_app, db = real_app
    spoc, judge = f"{_unique('rubspoc')}@test.edu", f"{_unique('rubjudge')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, judge, 'Judge')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = datetime.date.today().isoformat()

    def event(status='in_progress'):
        event_id = _create_event(owner, db, _unique('Rubric Hack'), day, team=False)
        db.collection('events').document(event_id).update({
            'status': status, 'judging_criteria': [{'name': 'Innovation', 'description': 'New ideas', 'max_score': 10}],
            'staff': [{'name': 'Judy', 'email': judge, 'role': 'Judge'}]})
        reg_id = _unique('REG')
        db.collection('registrations').document(reg_id).set({
            'event_id': event_id, 'lead_email': f"{_unique('team')}@test.edu", 'lead_name': 'Team Nova',
            'team_name': 'Team Nova', 'status': 'Confirmed', 'attendance': 'Present', 'payment_status': 'Free'})
        return event_id, reg_id
    return {'app': flask_app, 'db': db, 'judge': judge, 'client': _login(flask_app, judge, 'Judge'), 'event': event}


def test_a_rubric_score_is_stored_and_shown_on_the_leaderboard(judged):
    d = judged
    event_id, reg_id = d['event']()
    resp = d['client'].post(f'/judge/submit_score/{reg_id}', json={'scores': {'Innovation': 8}})
    assert resp.status_code == 200 and resp.get_json()['status'] == 'ok'
    scores = d['db'].collection('registrations').document(reg_id).get().to_dict()['scores']
    assert scores[d['judge']]['total'] == 8
    board = json.dumps(d['app'].test_client().get(f'/live/data/{event_id}').get_json())
    assert 'Team Nova' in board and ('8.0' in board or ': 8' in board)


def test_a_score_above_the_maximum_is_refused(judged):
    d = judged
    _, reg_id = d['event']()
    resp = d['client'].post(f'/judge/submit_score/{reg_id}', json={'scores': {'Innovation': 11}})
    assert resp.status_code == 400 and 'between 0 and 10' in resp.get_json()['message']
    assert not d['db'].collection('registrations').document(reg_id).get().to_dict().get('scores')


def test_the_dashboard_lists_events_in_progress_and_in_evaluation(judged):
    d = judged
    titles = []
    for status in ('in_progress', 'evaluation'):
        event_id, _ = d['event'](status)
        titles.append(d['db'].collection('events').document(event_id).get().to_dict()['title'])
    page = d['client'].get('/judge/dashboard').get_data(as_text=True)
    assert all(t in page for t in titles)


def test_scoring_after_the_spoc_locks_it_is_refused(judged):
    d = judged
    event_id, reg_id = d['event']()
    d['db'].collection('events').document(event_id).update({'scoring_locked': True})
    resp = d['client'].post(f'/judge/submit_score/{reg_id}', json={'scores': {'Innovation': 7}})
    assert resp.status_code == 403 and resp.get_json()['status'] == 'locked'
    assert not d['db'].collection('registrations').document(reg_id).get().to_dict().get('scores')
