"""
tests/test_judging_modes.py: who scores a hackathon's submission round and
who sees the leaderboard.

UPG-298  The SPOC chooses AI evaluation or judges for the round teams submit
         in; judges then score every team that submitted (no check-in), after
         the deadline, and the SPOC ranks and shortlists by their average.
UPG-299  AI criteria carry a description for the AI and marks that add up to
         100; the AI total is weighted by them.
UPG-300  Every leaderboard is hidden from the public until the event's SPOC
         makes it public; the event's staff always see it.
"""
import json

import pytest

import services_hackathon_eval as ev
from tests.test_hackathon_phase2 import _judge, _shortlist, p2  # noqa: F401  (the fixture)
from tests.test_hackathon_portal import _page, hack  # noqa: F401
from tests.test_integration_flow import _login, _unique, _user

TEAM = 'Zephyr Squad'


# ═══ UPG-300: the leaderboard is hidden until the SPOC makes it public ══════

@pytest.fixture
def board(hack):  # noqa: F811
    """An event with one scored team, its SPOC, a judge, a coordinator, an admin."""
    h = hack
    db, app = h['db'], h['app']
    eid = h['event']()
    t = h['team'](eid, TEAM)
    reg_id = next(d.id for d in db.collection('registrations').where('event_id', '==', eid).stream())
    judge, coord, admin = (f"{_unique(n)}@test.edu" for n in ('lbjudge', 'lbcoord', 'lbadmin'))
    _user(db, judge, 'Judge')
    _user(db, coord, 'EventCoordinator')
    _user(db, admin, 'SuperAdmin')
    db.collection('events').document(eid).update({
        'staff': [{'name': 'Judy', 'email': judge, 'role': 'Judge'}], 'coordinators': [coord]})
    db.collection('registrations').document(reg_id).update({
        'attendance': 'Present',
        'scores': {judge: {'details': {'Overall Score': 87}, 'total': 87, 'raw_total': 87, 'judge_name': 'Judy'}}})
    h.update({'eid': eid, 'student': t['client'], 'judge': _login(app, judge, 'Judge'),
              'coord': _login(app, coord, 'EventCoordinator'), 'admin': _login(app, admin, 'SuperAdmin'),
              'anon': app.test_client()})
    return h


def _first_snapshot(client, eid):
    resp = client.get(f'/live/stream/{eid}', buffered=False)
    chunk = next(iter(resp.response))
    resp.close()
    text = chunk.decode() if isinstance(chunk, bytes) else chunk
    return json.loads(text.split('data: ', 1)[1])


def _views(client, eid):
    """What a client gets from every address that shows the leaderboard."""
    html = client.get(f'/participant/leaderboard/{eid}', headers={'Accept': 'text/html'})
    data = client.get(f'/participant/leaderboard/{eid}', headers={'Accept': 'application/json'})
    return {'html': html, 'json': data, 'live': client.get(f'/live/data/{eid}'),
            'stream': _first_snapshot(client, eid),
            'api': client.get(f'/api/v1/leaderboard/{eid}'),
            'api_event': client.get(f'/api/v1/events/{eid}/leaderboard'),
            'projector': client.get(f'/live/{eid}')}


def test_a_new_leaderboard_is_hidden_from_the_public_on_every_address(board):  # noqa: F811
    b = board
    assert 'leaderboard_public' not in b['ev'](b['eid'])
    for who in ('anon', 'student'):
        v = _views(b[who], b['eid'])
        # (the student's own name, "Zephyr Squad Lead", is in the page header)
        html = v['html'].get_data(as_text=True).replace(f'{TEAM} Lead', '')
        assert v['html'].status_code == 200 and 'data-leaderboard-hidden' in html and TEAM not in html
        assert 'Not public yet' in html and '87' not in html.split('data-leaderboard-hidden', 1)[1][:400]
        assert v['json'].status_code == 403
        assert v['json'].get_json()['status'] == 'hidden' and v['json'].get_json()['data'] == []
        live = v['live'].get_json()
        assert live['hidden'] is True and live['board'] == [] and TEAM not in json.dumps(live)
        assert v['stream']['hidden'] is True and v['stream']['board'] == [] and TEAM not in json.dumps(v['stream'])
        for key in ('api', 'api_event'):
            assert v[key].status_code == 403 and TEAM not in v[key].get_data(as_text=True)
            assert 'not_public' in v[key].get_data(as_text=True)
        projector = v['projector'].get_data(as_text=True).replace(f'{TEAM} Lead', '')
        assert v['projector'].status_code == 200 and TEAM not in projector


def test_the_events_staff_see_the_hidden_board_marked_as_not_public(board):  # noqa: F811
    b = board
    for who in ('owner', 'judge', 'coord', 'admin'):
        html = b[who].get(f'/participant/leaderboard/{b["eid"]}', headers={'Accept': 'text/html'})
        page = html.get_data(as_text=True)
        assert html.status_code == 200 and TEAM in page and 'data-leaderboard-staff-only' in page, who
        assert 'data-leaderboard-hidden' not in page, who
        live = b[who].get(f'/live/data/{b["eid"]}').get_json()
        assert live['hidden'] is False and live['staff_only'] is True and TEAM in json.dumps(live), who
        data = b[who].get(f'/participant/leaderboard/{b["eid"]}', headers={'Accept': 'application/json'})
        assert data.status_code == 200 and data.get_json()['public'] is False, who
    # A SPOC of another event is not staff here
    assert TEAM not in b['stranger'].get(f'/live/data/{b["eid"]}').get_data(as_text=True)


def test_only_the_events_spoc_switches_it_and_then_everyone_sees_it(board):  # noqa: F811
    b = board
    eid = b['eid']
    for who in ('stranger', 'coord', 'judge', 'student'):
        resp = b[who].post(f'/spoc/leaderboard_visibility/{eid}', data={'public': '1'})
        assert resp.status_code in (302, 403), who
        assert 'leaderboard_public' not in b['ev'](eid), who
    assert b['stranger'].post(f'/spoc/leaderboard_visibility/{eid}', data={'public': '1'}).status_code == 403

    # The switch is on the results page, the round panel and the hackathon page
    for path in (f'/spoc/results/{eid}', f'/spoc/round_panel/{eid}', f'/spoc/hackathon/{eid}'):
        assert 'data-leaderboard-switch="hidden"' in _page(b['owner'], path), path

    resp = b['owner'].post(f'/spoc/leaderboard_visibility/{eid}', data={'public': '1', 'back': 'rounds'})
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/spoc/round_panel/{eid}')
    event = b['ev'](eid)
    assert event['leaderboard_public'] is True and event['leaderboard_public_changed_by']
    assert event['leaderboard_public_changed_at']
    assert 'data-leaderboard-switch="public"' in _page(b['owner'], f'/spoc/results/{eid}')

    v = _views(b['anon'], eid)
    page = v['html'].get_data(as_text=True)
    assert TEAM in page and 'data-leaderboard-hidden' not in page and 'data-leaderboard-staff-only' not in page
    assert v['json'].status_code == 200 and v['json'].get_json()['public'] is True
    assert TEAM in json.dumps(v['json'].get_json())
    live = v['live'].get_json()
    assert live['hidden'] is False and live['staff_only'] is False and TEAM in json.dumps(live)
    assert v['stream']['hidden'] is False and TEAM in json.dumps(v['stream'])
    for key in ('api', 'api_event'):
        assert v[key].status_code == 200 and TEAM in v[key].get_data(as_text=True), key

    # And hidden again
    b['owner'].post(f'/spoc/leaderboard_visibility/{eid}', data={'public': '0'})
    assert b['ev'](eid)['leaderboard_public'] is False
    assert b['anon'].get(f'/live/data/{eid}').get_json()['hidden'] is True
    assert b['anon'].get(f'/api/v1/leaderboard/{eid}').status_code == 403


def test_a_copied_event_starts_hidden_and_students_get_the_link_only_once_public(board):  # noqa: F811
    b = board
    eid = b['eid']
    dash = b['student'].get('/participant/dashboard').get_data(as_text=True)
    assert f'/participant/leaderboard/{eid}' not in dash
    b['owner'].post(f'/spoc/leaderboard_visibility/{eid}', data={'public': '1'})
    dash = b['student'].get('/participant/dashboard').get_data(as_text=True)
    assert f'/participant/leaderboard/{eid}' in dash and 'data-leaderboard-link' in dash

    resp = b['owner'].post(f'/spoc/clone_event/{eid}')
    copy_id = resp.headers['Location'].rsplit('/', 1)[1]
    copy = b['ev'](copy_id)
    assert copy and copy_id != eid
    assert not any(k.startswith('leaderboard_public') for k in copy)
    assert b['anon'].get(f'/live/data/{copy_id}').get_json()['hidden'] is True


# ═══ UPG-299: AI criteria with a description and marks ══════════════════════

def _criteria(h, eid, rows):
    data = {}
    for i, (label, description, marks) in enumerate(rows):
        data.update({f'criterion_{i}': label, f'description_{i}': description, f'marks_{i}': marks})
    resp = h['owner'].post(f'/spoc/hackathon/{eid}/ai/criteria', data=data, follow_redirects=True)
    return resp.get_data(as_text=True)


def test_criteria_marks_must_add_up_to_100_and_are_all_or_none(p2):  # noqa: F811
    h = p2
    eid, _ = h['setup'](names=('Alpha',))
    before = ev.criteria(h['ev'](eid))
    for rows, message in (
            ([('Impact', '', '60'), ('Polish', '', '30')], 'The marks add up to 90; they must add up to 100.'),
            ([('Impact', '', '60'), ('Polish', '', '')],
             'Give marks for every criterion, or leave all of them empty for equal weights.'),
            ([('Impact', '', '0'), ('Polish', '', '100')], 'Impact: marks are a whole number from 1 to 100.'),
            ([('Impact', '', 'lots'), ('Polish', '', '50')], 'Impact: marks are a whole number from 1 to 100.'),
            ([('', 'Orphan text', ''), ('Polish', '', '')], 'Criterion 1 has a description or marks but no name.')):
        page = _criteria(h, eid, rows)
        assert message in page, (rows, page[page.find('alert'):][:300])
        assert ev.criteria(h['ev'](eid)) == before, rows

    page = _criteria(h, eid, [('Impact', 'Does it help people with the problem?', '70'),
                              ('Polish', 'Is the demo finished and clear?', '30')])
    saved = ev.criteria(h['ev'](eid))
    assert [(c['label'], c['description'], c['weight']) for c in saved] == [
        ('Impact', 'Does it help people with the problem?', 70), ('Polish', 'Is the demo finished and clear?', 30)]
    html = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert 'value="Does it help people with the problem?"' in html and 'name="marks_0"' in html and 'value="70"' in html

    # No marks at all: equal weights, nothing stored
    _criteria(h, eid, [('Impact', '', ''), ('Polish', '', '')])
    saved = ev.criteria(h['ev'](eid))
    assert all('weight' not in c and 'description' not in c for c in saved)
    assert ev.weights(saved) == [50.0, 50.0]


def test_the_ai_is_told_each_criterion_and_its_marks_and_the_total_is_weighted(p2):  # noqa: F811
    h = p2
    eid, teams = h['setup'](names=('Alpha', 'Bravo'))
    _criteria(h, eid, [('Impact', 'Does it help people with the problem?', '70'),
                       ('Polish', 'Is the demo finished?', '30')])
    ids = [c['id'] for c in ev.criteria(h['ev'](eid))]
    h['after']()
    h['script']['Alpha'] = json.dumps({'scores': {ids[0]: 10, ids[1]: 5}, 'reason': 'Strong impact.'})
    h['script']['Bravo'] = json.dumps({'scores': {ids[0]: 5, ids[1]: 10}, 'reason': 'Polished.'})
    progress = h['score_all'](eid)
    assert progress['scored'] == 2
    system = h['calls'][0]['system']
    assert 'Does it help people with the problem?' in system and 'worth 70 of 100 marks' in system
    assert 'worth 30 of 100 marks' in system
    assert h['sub'](teams['Alpha'])['ai_eval']['total'] == 85.0   # 10/10 × 70 + 5/10 × 30
    assert h['sub'](teams['Bravo'])['ai_eval']['total'] == 65.0   # 5/10 × 70 + 10/10 × 30
    assert [r['team'] for r in h['rows'](eid)] == ['Alpha', 'Bravo']

    # Fixed once scoring started
    page = _criteria(h, eid, [('Impact', '', '50'), ('Polish', '', '50')])
    assert ev.criteria(h['ev'](eid))[0]['weight'] == 70
    assert "Submissions are already scored with the current criteria; they can&#39;t change now." in page


# ═══ UPG-298: AI or judges for the submission round ═════════════════════════

def _mode(h, eid, mode, who='owner'):
    return h[who].post(f'/spoc/hackathon/{eid}/evaluation_mode', data={'mode': mode}, follow_redirects=True)


def _two_judges(h, eid, criteria=None, open_hall=False):
    """Two judges on the event (not open hall unless asked); returns their clients and emails."""
    emails = [f"{_unique('mjudge')}@test.edu" for _ in range(2)]
    for e in emails:
        _user(h['db'], e, 'Judge')
    h['db'].collection('events').document(eid).update({
        'open_hall_mode': open_hall,
        'staff': [{'name': f'Judge {i}', 'email': e, 'role': 'Judge'} for i, e in enumerate(emails, 1)],
        'judging_criteria': criteria or [{'name': 'Innovation', 'max_score': 10}, {'name': 'Design', 'max_score': 10}]})
    return [_login(h['app'], e, 'Judge') for e in emails], emails


def _score(client, reg_id, **values):
    return client.post(f'/judge/score_inline/{reg_id}', json={'scores': values})


def test_the_spoc_chooses_judges_and_then_ai_scoring_is_refused(p2):  # noqa: F811
    h = p2
    eid, teams = h['setup'](names=('Alpha', 'Bravo'))
    assert ev.mode(h['ev'](eid)) == 'ai'
    assert 'data-evaluation-mode="ai"' in _page(h['owner'], f'/spoc/hackathon/{eid}')

    assert h['stranger'].post(f'/spoc/hackathon/{eid}/evaluation_mode', data={'mode': 'judges'}).status_code == 403
    assert ev.mode(h['ev'](eid)) == 'ai'
    assert 'Choose AI evaluation or judges.' in _mode(h, eid, 'robots').get_data(as_text=True)

    page = _mode(h, eid, 'judges').get_data(as_text=True)
    assert 'Judges score this round' in page
    event = h['ev'](eid)
    assert ev.mode(event) == 'judges' and event['hackathon']['evaluation_mode_changed']['from'] == 'ai'
    html = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert 'data-evaluation-mode="judges"' in html and 'data-judges-round' in html
    assert 'Start AI scoring' not in html and 'Judges (out of 100)' in html and 'AI total' not in html

    h['after']()
    resp = h['owner'].post(f'/spoc/hackathon/{eid}/ai/start', follow_redirects=True)
    assert ev.JUDGED in resp.get_data(as_text=True) and not h['calls']
    assert ev.state(h['ev'](eid))['status'] == 'idle'
    sub_id = next(h['db'].collection('project_submissions')
                  .where('registration_id', '==', teams['Alpha']['id']).stream()).id
    ok, message = ev.rerun(h['db'], eid, h['ev'](eid) | {'id': eid}, sub_id)
    assert not ok and message == ev.JUDGED and not h['calls']


def test_judges_score_every_submitted_team_after_the_deadline_without_check_in(p2):  # noqa: F811
    h = p2
    eid, teams = h['setup'](names=('Alpha', 'Bravo', 'Charlie'), submit=('Alpha', 'Bravo'))
    _mode(h, eid, 'judges')
    (j1, j2), emails = _two_judges(h, eid)
    assert all(h['reg'](t)['attendance'] == 'Pending' for t in teams.values())

    # Before the deadline: nothing to score yet
    page = _page(j1, f'/judge/event/{eid}')
    assert 'Submissions are still open' in page and 'Alpha' not in page
    resp = _score(j1, teams['Alpha']['id'], Innovation=5, Design=5)
    assert resp.status_code == 409 and 'still open' in resp.get_json()['message']

    h['after']()
    for client in (j1, j2):
        page = _page(client, f'/judge/event/{eid}')
        assert 'Alpha' in page and 'Bravo' in page and 'Charlie' not in page
        assert 'data-judge-submission-round' in page and 'View submission' in page
    dash = _page(j1, '/judge/dashboard')
    assert '0 / 2' in dash
    resp = _score(j1, teams['Charlie']['id'], Innovation=5, Design=5)
    assert resp.status_code == 409 and "didn't submit" in resp.get_json()['message']

    # A team assigned to one judge is that judge's only
    h['db'].collection('registrations').document(teams['Bravo']['id']).update(
        {'assigned_judge_email': emails[1], 'assigned_judge_name': 'Judge 2'})
    assert 'Bravo' not in _page(j1, f'/judge/event/{eid}') and 'Bravo' in _page(j2, f'/judge/event/{eid}')
    assert 'Alpha' in _page(j2, f'/judge/event/{eid}')

    assert _score(j1, teams['Alpha']['id'], Innovation=8, Design=6).get_json()['status'] == 'ok'
    assert '1 / 1' in _page(j1, '/judge/dashboard')
    # The judge opens the submission and never sees the AI's view of it
    view = _page(j1, f'/hackathon/{eid}/review/{teams["Alpha"]["id"]}')
    assert 'Alpha approach notes' in view and 'AI evaluation' not in view


def test_the_ranking_is_the_judges_average_and_the_spoc_shortlists_from_it(p2):  # noqa: F811
    h = p2
    eid, teams = h['setup'](names=('Alpha', 'Bravo', 'Charlie'), submit=('Alpha', 'Bravo'))
    _mode(h, eid, 'judges')
    (j1, j2), _ = _two_judges(h, eid)
    h['after']()
    preview = h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/preview', data={'mode': 'top_n', 'n': '1'},
                              follow_redirects=True).get_data(as_text=True)
    assert "Wait for the judges&#39; scores" in preview or "Wait for the judges' scores" in preview

    _score(j1, teams['Alpha']['id'], Innovation=8, Design=6)     # 14 of 20 = 70
    _score(j2, teams['Alpha']['id'], Innovation=10, Design=10)   # 20 of 20 = 100
    _score(j1, teams['Bravo']['id'], Innovation=9, Design=9)     # 18 of 20 = 90
    rows = {r['team']: r for r in h['rows'](eid)}
    assert rows['Alpha']['judges'] == 85.0 and rows['Alpha']['judges_n'] == 2
    assert rows['Bravo']['judges'] == 90.0 and rows['Bravo']['judges_n'] == 1
    assert rows['Charlie']['key'] is None and not rows['Charlie']['submitted']
    assert [r['team'] for r in h['rows'](eid)][:2] == ['Bravo', 'Alpha']
    html = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert '85.0' in html and '2 judge(s)' in html and '2</strong> of 2 submitted team(s) scored' in html

    # The SPOC's own score still overrides
    h['owner'].post(f'/spoc/hackathon/{eid}/review/{teams["Alpha"]["id"]}', data={'score': '95', 'note': ''})
    assert [r['team'] for r in h['rows'](eid)][:2] == ['Alpha', 'Bravo']

    _, go, expected = _shortlist(h, eid, 1)
    assert go == [teams['Alpha']['id']]
    resp = h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/confirm',
                           data={'go': go, 'expected_round': expected})
    assert resp.status_code == 302
    alpha, bravo = h['reg'](teams['Alpha']), h['reg'](teams['Bravo'])
    assert alpha['current_round'] == 2 and not alpha.get('scores') and bravo['is_eliminated']
    assert alpha['round_history'][-1]['score'] == 95.0 and len(alpha['round_history'][-1]['scores']) == 2

    # Undo gives the finalist its judges' scores back
    assert h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/undo').status_code == 302
    alpha = h['reg'](teams['Alpha'])
    assert alpha['current_round'] == 1 and len(alpha['scores']) == 2
    assert {r['team']: r['judges'] for r in h['rows'](eid)}['Alpha'] == 85.0


def test_the_finale_after_the_shortlist_is_judged_as_before(p2):  # noqa: F811
    h = p2
    eid, teams = h['setup'](names=('Alpha', 'Bravo'))
    _mode(h, eid, 'judges')
    (j1, _), emails = _two_judges(h, eid)
    h['after']()
    _score(j1, teams['Alpha']['id'], Innovation=9, Design=9)
    _score(j1, teams['Bravo']['id'], Innovation=2, Design=2)
    _, go, expected = _shortlist(h, eid, 1)
    h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/confirm', data={'go': go, 'expected_round': expected})
    assert not ev.judges_score_submissions(h['ev'](eid))
    # The finale: checked-in finalists assigned to the judge, as for any judged round
    h['db'].collection('registrations').document(teams['Alpha']['id']).update(
        {'assigned_judge_email': emails[0], 'assigned_judge_name': 'Judge 1'})
    assert 'Alpha' not in _page(j1, f'/judge/event/{eid}')
    h['db'].collection('registrations').document(teams['Alpha']['id']).update({'attendance': 'Present'})
    page = _page(j1, f'/judge/event/{eid}')
    assert 'Alpha' in page and 'Bravo' not in page
    assert _score(j1, teams['Alpha']['id'], Innovation=7, Design=7).get_json()['status'] == 'ok'
    # The shortlist's round can't be switched any more
    assert 'undo it before changing' in _mode(h, eid, 'ai').get_data(as_text=True)


def test_the_round_keeps_its_scorer_once_scoring_has_started(p2):  # noqa: F811
    h = p2
    # Judges have scored: it stays with the judges
    eid, teams = h['setup'](names=('Alpha',))
    _mode(h, eid, 'judges')
    (j1, _), _ = _two_judges(h, eid)
    assert 'AI scores this round' in _mode(h, eid, 'ai').get_data(as_text=True)   # nothing scored: free to change
    _mode(h, eid, 'judges')
    h['after']()
    _score(j1, teams['Alpha']['id'], Innovation=5, Design=5)
    assert 'Judges have started scoring' in _mode(h, eid, 'ai').get_data(as_text=True)
    assert ev.mode(h['ev'](eid)) == 'judges'

    # AI has scored: it stays with AI
    eid2, _ = h['setup'](names=('Delta',))
    h['after']()
    h['scored'](eid2, {'Delta': 7})
    assert 'AI scoring has started' in _mode(h, eid2, 'judges').get_data(as_text=True)
    assert ev.mode(h['ev'](eid2)) == 'ai'
    # Before judges mode, judges at a hackathon still need check-in as before
    judge = _judge(h, eid2)
    assert 'Delta' not in _page(judge, f'/judge/event/{eid2}')

    # Results published: no change
    eid3, _ = h['setup'](names=('Echo',))
    h['db'].collection('events').document(eid3).update({'results_published': True})
    assert "Results are published" in _mode(h, eid3, 'judges').get_data(as_text=True)
    assert ev.mode(h['ev'](eid3)) == 'ai'
