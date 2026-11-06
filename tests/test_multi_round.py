"""
tests/test_multi_round.py — UPG-149 on the real database layer: a hackathon
with 2–3 rounds runs from round 1 to published results; every round's scores
are kept; no team is stranded on an old round; the final round can't be
advanced and a stale page can't advance twice; ties at the top-N cut all go
through; every team is emailed; the coordinator uses the same rule; judges
can't score teams that are out; students see where they stand.
"""
import datetime

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def hack(real_app, monkeypatch):
    flask_app, db = real_app
    spoc, judge, judge2 = (f"{_unique(k)}@test.edu" for k in ('mrspoc', 'mrjudge', 'mrjudge2'))
    _user(db, spoc, 'ClubSPOC')
    _user(db, judge, 'Judge')
    _user(db, judge2, 'Judge')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    judges = {judge: _login(flask_app, judge, 'Judge'), judge2: _login(flask_app, judge2, 'Judge')}

    sent = []
    import utils_email
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: sent.append((to, subject)) or True)

    def event(rounds=3):
        event_id = _create_event(owner, db, _unique('Round Hack'), datetime.date.today().isoformat(), team=False)
        db.collection('events').document(event_id).update({
            'status': 'in_progress', 'total_rounds': rounds, 'active_round': 1,
            'judging_criteria': [{'name': 'Innovation', 'description': 'Ideas', 'max_score': 10}],
            'staff': [{'name': 'Judy', 'email': judge, 'role': 'Judge'},
                      {'name': 'Jo', 'email': judge2, 'role': 'Judge'}]})
        return event_id

    def team(event_id, name, present=True, lead=None, members=()):
        reg_id = _unique('REG')
        db.collection('registrations').document(reg_id).set({
            'event_id': event_id, 'lead_email': lead or f"{_unique('lead')}@test.edu", 'lead_name': f"{name} Lead",
            'team_name': name, 'status': 'Confirmed', 'payment_status': 'Free',
            'attendance': 'Present' if present else 'Pending', 'current_round': 1, 'is_eliminated': False,
            'members': [{'role': 'Member', 'name': m, 'email': m} for m in members]})
        return reg_id

    def score(reg_id, value, who=judge):
        return judges[who].post(f'/judge/submit_score/{reg_id}', json={'scores': {'Innovation': value}})

    def advance(event_id, **form):
        return owner.post(f'/spoc/advance_round/{event_id}', data={k: str(v) for k, v in form.items()})

    def reg(reg_id):
        return db.collection('registrations').document(reg_id).get().to_dict()

    def ev(event_id):
        return db.collection('events').document(event_id).get().to_dict()

    return {'app': flask_app, 'db': db, 'owner': owner, 'judge': judge, 'judge2': judge2, 'sent': sent,
            'event': event, 'team': team, 'score': score, 'advance': advance, 'reg': reg, 'ev': ev}


# ── Criterion 1: three rounds, history kept, final ranking on the final round ──

def test_a_three_round_hackathon_runs_to_results_and_keeps_every_round(hack):
    h = hack
    eid = h['event'](rounds=3)
    a, b, c, d = (h['team'](eid, n) for n in ('Alpha', 'Bravo', 'Charlie', 'Delta'))
    for rid, value in ((a, 9), (b, 7), (c, 5), (d, 3)):
        assert h['score'](rid, value).status_code == 200

    h['advance'](eid, mode='top_n', top_n=2, round=1)
    assert h['ev'](eid)['active_round'] == 2
    assert [h['reg'](r)['current_round'] for r in (a, b)] == [2, 2]
    assert all(h['reg'](r)['is_eliminated'] and h['reg'](r)['eliminated_in_round'] == 1 for r in (c, d))
    assert h['reg'](a)['scores'] == {}   # a clean sheet for round 2 …
    first = h['reg'](a)['round_history'][0]   # … and round 1 kept
    assert first['round'] == 1 and first['score'] == 9 and first['result'] == 'qualified'
    assert first['scores'][h['judge']]['details'] == {'Innovation': 9}

    for rid, value in ((a, 6), (b, 8)):
        assert h['score'](rid, value).status_code == 200
    h['advance'](eid, mode='top_n', top_n=1, round=2)
    assert h['ev'](eid)['active_round'] == 3
    assert h['reg'](b)['current_round'] == 3
    assert h['reg'](a)['is_eliminated'] and h['reg'](a)['eliminated_in_round'] == 2

    assert h['score'](b, 10).status_code == 200
    resp = h['owner'].post(f'/spoc/publish_results/{eid}')
    assert resp.status_code == 302 and h['ev'](eid)['results_published'] is True

    from services_leaderboard import for_event
    board = for_event(h['db'], eid)
    assert [(r['team'], r['score'], r['rank']) for r in board] == [('Bravo', 10.0, 1)]
    assert [(e['round'], e['score'], e['result']) for e in h['reg'](b)['round_history']] == \
        [(1, 7.0, 'qualified'), (2, 8.0, 'qualified')]
    assert [(e['round'], e['score'], e['result']) for e in h['reg'](a)['round_history']] == \
        [(1, 9.0, 'qualified'), (2, 6.0, 'eliminated')]


# ── Criterion 2: no stranded teams ─────────────────────────────────────────────

def test_unscored_teams_stop_the_advance_or_are_eliminated_never_stranded(hack):
    h = hack
    eid = h['event'](rounds=2)
    scored, waiting, absent = h['team'](eid, 'Scored'), h['team'](eid, 'Waiting'), h['team'](eid, 'Absent', present=False)
    h['score'](scored, 8)

    h['advance'](eid, mode='top_n', top_n=1, round=1)   # a present team has no score
    assert h['ev'](eid)['active_round'] == 1
    assert not any(h['reg'](r).get('is_eliminated') for r in (scored, waiting, absent))
    assert h['reg'](scored).get('round_history') in (None, [])

    h['advance'](eid, mode='top_n', top_n=1, round=1, eliminate_unscored='yes')
    assert h['ev'](eid)['active_round'] == 2
    assert h['reg'](scored)['current_round'] == 2
    assert h['reg'](waiting)['is_eliminated'] and h['reg'](waiting)['round_history'][-1]['result'] == 'eliminated'
    assert h['reg'](absent)['is_eliminated'] and h['reg'](absent)['round_history'][-1]['result'] == 'absent'
    for doc in h['db'].collection('registrations').where('event_id', '==', eid).stream():
        r = doc.to_dict()
        assert r.get('is_eliminated') or r.get('current_round') == 2, 'no team is left on round 1'


# ── Criterion 3: the final round, and a stale page ─────────────────────────────

def test_the_final_round_cant_be_advanced_and_a_stale_page_changes_nothing(hack):
    h = hack
    eid = h['event'](rounds=2)
    teams = [h['team'](eid, n) for n in ('One', 'Two', 'Three')]
    for rid, value in zip(teams, (9, 8, 2)):
        h['score'](rid, value)
    h['advance'](eid, mode='top_n', top_n=2, round=1)
    assert h['ev'](eid)['active_round'] == 2
    before = {r: h['reg'](r) for r in teams}

    h['advance'](eid, mode='top_n', top_n=1, round=1)   # the same page sent again
    assert h['ev'](eid)['active_round'] == 2
    assert {r: h['reg'](r) for r in teams} == before

    for rid in teams[:2]:
        h['score'](rid, 5)
    h['advance'](eid, mode='top_n', top_n=1, round=2)   # round 2 of 2 is the final
    assert h['ev'](eid)['active_round'] == 2
    assert not h['reg'](teams[1]).get('is_eliminated')

    page = h['owner'].get(f'/spoc/round_panel/{eid}').get_data(as_text=True)
    assert 'Round 2 of 2' in page and 'id="final-round"' in page
    assert f'/spoc/advance_round/{eid}' not in page
    assert 'id="past-rounds"' in page and 'Three' in page


# ── Criterion 4: ties at the cut ───────────────────────────────────────────────

def test_top_n_lets_every_team_tied_at_the_cut_through(hack):
    h = hack
    eid = h['event'](rounds=3)
    a, b, c, d = (h['team'](eid, n) for n in ('A', 'B', 'C', 'D'))
    for rid, value in ((a, 9), (b, 7), (c, 7), (d, 3)):
        h['score'](rid, value)
    h['advance'](eid, mode='top_n', top_n=2, round=1)
    assert [h['reg'](r).get('current_round') for r in (a, b, c)] == [2, 2, 2]
    assert h['reg'](d)['is_eliminated']


# ── Criterion 5: one email per person ──────────────────────────────────────────

def test_every_person_on_each_team_gets_one_result_email(hack, monkeypatch):
    import app as app_module   # team members get emails only when the owner turns it on (UPG-152)
    monkeypatch.setitem(app_module.app.config, 'NOTIFY_TEAM_MEMBERS', True)
    h = hack
    eid = h['event'](rounds=2)
    member_in, member_out = f"{_unique('min')}@test.edu", f"{_unique('mout')}@test.edu"
    win = h['team'](eid, 'Win', members=[member_in])
    lose = h['team'](eid, 'Lose', members=[member_out])
    h['score'](win, 9)
    h['score'](lose, 4)
    h['sent'].clear()
    h['advance'](eid, mode='cutoff', cutoff=5, round=1)

    advanced = sorted(to for to, subject in h['sent'] if 'advanced to Round 2' in subject)
    out = sorted(to for to, subject in h['sent'] if subject.startswith('Round 1 result'))
    assert advanced == sorted([h['reg'](win)['lead_email'], member_in])
    assert out == sorted([h['reg'](lose)['lead_email'], member_out])
    assert len(h['sent']) == 4


# ── Criterion 6: the coordinator's promote uses the same rule ──────────────────

def test_the_coordinators_promote_uses_the_average_and_keeps_history(hack):
    h = hack
    eid = h['event'](rounds=3)
    pair, solo = h['team'](eid, 'Pair'), h['team'](eid, 'Solo')
    h['score'](pair, 6)
    h['score'](pair, 6, who=h['judge2'])   # average 6, sum 12
    h['score'](solo, 10)
    resp = h['owner'].post(f'/coordinator/promote_round/{eid}', data={'cutoff_score': '10', 'round': '1'})
    assert resp.status_code == 302
    assert h['ev'](eid)['active_round'] == 2
    assert h['reg'](solo)['current_round'] == 2
    assert h['reg'](pair)['is_eliminated'], 'the average (6), not the sum (12), is compared with the cut-off'
    assert h['reg'](pair)['round_history'][0]['score'] == 6.0

    resp = h['owner'].post(f'/coordinator/promote_round/{eid}', data={'cutoff_score': '0', 'round': '1'})
    assert h['ev'](eid)['active_round'] == 2, 'a stale coordinator form changes nothing'


# ── Criterion 7: judges can't score teams that are out ─────────────────────────

def test_judges_cant_score_eliminated_teams_or_teams_on_another_round(hack):
    h = hack
    eid = h['event'](rounds=3)
    keep, drop = h['team'](eid, 'Keep'), h['team'](eid, 'Drop')
    h['score'](keep, 9)
    h['score'](drop, 2)
    h['advance'](eid, mode='top_n', top_n=1, round=1)

    resp = h['score'](drop, 10)
    assert resp.status_code == 409
    assert h['reg'](drop)['scores'][h['judge']]['total'] == 2, 'nothing stored'

    behind = h['team'](eid, 'Behind')   # still on round 1 while the event is on round 2
    resp = h['score'](behind, 7)
    assert resp.status_code == 409 and not h['reg'](behind).get('scores')
    inline = _login(h['app'], h['judge'], 'Judge').post(f'/judge/score_inline/{drop}',
                                                       json={'scores': {'Innovation': 10}})
    assert inline.status_code == 409

    assert h['score'](keep, 8).status_code == 200


# ── Criterion 8: students and the round panel see where things stand ───────────

def test_students_see_their_round_and_the_panel_says_round_x_of_n(hack):
    h = hack
    db, app = h['db'], h['app']
    eid = h['event'](rounds=3)
    up_email, out_email = f"{_unique('stuup')}@test.edu", f"{_unique('stuout')}@test.edu"
    _user(db, up_email, 'Student')
    _user(db, out_email, 'Student')
    up, out = h['team'](eid, 'Rising', lead=up_email), h['team'](eid, 'Falling', lead=out_email)

    page = h['owner'].get(f'/spoc/round_panel/{eid}').get_data(as_text=True)
    assert 'Round 1 of 3' in page and 'id="final-round"' not in page
    up_client = _login(app, up_email, 'Student')
    assert 'Round 1 of 3' in up_client.get('/participant/dashboard').get_data(as_text=True)

    h['score'](up, 9)
    h['score'](out, 1)
    h['advance'](eid, mode='top_n', top_n=1, round=1)

    assert 'Qualified for round 2 of 3' in up_client.get('/participant/dashboard').get_data(as_text=True)
    assert 'Qualified for round 2 of 3' in up_client.get(f'/ticket/{up}').get_data(as_text=True)
    out_client = _login(app, out_email, 'Student')
    assert 'Not qualified after round 1 of 3' in out_client.get('/participant/dashboard').get_data(as_text=True)
    assert 'Not qualified after round 1 of 3' in out_client.get(f'/ticket/{out}').get_data(as_text=True)
    h['score'](up, 7)   # the advance form appears once the round has a score
    page = h['owner'].get(f'/spoc/round_panel/{eid}').get_data(as_text=True)
    assert 'Round 2 of 3' in page and f'/spoc/advance_round/{eid}' in page and 'name="round" value="2"' in page


def test_a_one_round_event_shows_no_round_status(hack):
    from services_rounds import status_for
    assert status_for({'total_rounds': 1}, {'current_round': 1}) is None
    assert status_for({}, {'current_round': 1}) is None
