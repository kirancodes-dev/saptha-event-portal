"""
tests/test_five_pages_no_500.py — UPG-59 on the real database layer: the five
pages the route crawl found answering 500 answer 200, a redirect, 403 or 404
for every role, with the data that broke each one: a judge on the staff list
with no name (AI match page), a student who isn't registered (exams, hackathon
submission), a registration with no registration time (SPOC stats; only the
document store can hold one, so that case runs on the mock database).
"""
import pytest

from tests.test_integration_flow import _unique, _user
from tests.test_shared_layout import roles  # noqa: F401  (fixture)

OK = {200, 302, 403, 404}


@pytest.fixture
def broken_data(roles):  # noqa: F811
    d = roles
    import models
    db = models.db
    nameless_judge = f"{_unique('nameless')}@test.edu"
    _user(db, nameless_judge, 'Judge')
    event = db.collection('events').document(d['event_id']).get().to_dict()
    db.collection('events').document(d['event_id']).update({
        'staff': list(event.get('staff') or []) + [{'email': nameless_judge, 'role': 'Judge'}]})   # no 'name'
    db.collection('registrations').document(_unique('REG')).set({
        'event_id': d['event_id'], 'lead_email': f"{_unique('notime')}@test.edu", 'lead_name': 'No Time',
        'status': 'Confirmed', 'registered_at': None})
    outsider = f"{_unique('outsider')}@test.edu"
    _user(db, outsider, 'Student')
    from tests.test_integration_flow import _login
    d['clients']['outsider'] = _login(d['clients']['anonymous'].application, outsider, 'Student')
    return d


def test_the_five_pages_never_answer_500(broken_data):
    d = broken_data
    e = d['event_id']
    pages = [f'/ai/match_page/{e}', f'/exams/{e}', '/gamification/leaderboard', f'/hackathon/submit/{e}',
             '/spoc/api/stats']
    seen = {}
    for who, client in d['clients'].items():
        for path in pages:
            seen[(who, path)] = client.get(path).status_code
    assert {k: v for k, v in seen.items() if v not in OK} == {}
    # The people each page is for get it
    assert seen[('spoc', f'/ai/match_page/{e}')] == 200
    assert seen[('admin', f'/ai/match_page/{e}')] == 200
    assert seen[('student', '/gamification/leaderboard')] == 200
    assert seen[('spoc', '/spoc/api/stats')] == 200
    assert seen[('student', f'/hackathon/submit/{e}')] == 200            # registered
    assert seen[('outsider', f'/hackathon/submit/{e}')] == 302           # not registered: sent to the event
    assert seen[('outsider', f'/exams/{e}')] == 302


def test_not_registered_is_sent_to_the_event_page(broken_data):
    d = broken_data
    for path in (f"/exams/{d['event_id']}", f"/hackathon/submit/{d['event_id']}"):
        resp = d['clients']['outsider'].get(path)
        assert resp.status_code == 302 and f"/event/{d['event_id']}" in resp.headers['Location'], path


def test_the_stats_api_counts_every_registration(broken_data):
    d = broken_data
    data = d['clients']['spoc'].get('/spoc/api/stats').get_json()
    [mine] = [e for e in data['events'] if e['id'] == d['event_id']]
    assert mine['reg_count'] == 2                      # the student's, and one saved with registered_at None
    assert data['total_regs'] >= 2 and isinstance(data['recent_activity'], list)


def test_the_stats_api_survives_a_registration_with_no_time(client, mock_db, monkeypatch):
    """On the SQL layer a registration always has a time (it falls back to when
    the row was made); in the document store it can be missing, which made the
    sort compare None with text (UPG-59)."""
    import routes_spoc
    monkeypatch.setattr(routes_spoc, 'db', mock_db)
    spoc = 'statsspoc@test.edu'
    mock_db.collection('users').document(spoc).set({'name': 'Stats', 'role': 'ClubSPOC', 'email': spoc})
    mock_db.collection('events').document('evt-stats').set({'title': 'Stats Night', 'spoc_id': spoc,
                                                            'status': 'registration_open'})
    for rid, at in (('r-timed', '2026-10-01 10:00:00'), ('r-untimed', None)):
        mock_db.collection('registrations').document(rid).set({'event_id': 'evt-stats', 'lead_name': rid,
                                                               'lead_email': f'{rid}@test.edu', 'registered_at': at,
                                                               'status': 'Confirmed'})
    with client.session_transaction() as sess:
        sess.update({'user_id': spoc, 'role': 'ClubSPOC', 'name': 'Stats'})
    resp = client.get('/spoc/api/stats')
    assert resp.status_code == 200, resp.data[:300]
    [mine] = [e for e in resp.get_json()['events'] if e['id'] == 'evt-stats']
    assert mine['reg_count'] == 2
