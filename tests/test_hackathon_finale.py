"""
tests/test_hackathon_finale.py — UPG-309: the hackathon's finale after the
shortlist. Every judge sees every finalist (none assigned, none checked in)
and finds a team by name or code; a judge's score is the criteria marks added
up; a team's score is the average of the judges who scored it; round-1 marks
don't count; the results rank the finalists by the judges' average.
"""

import re

import pytest

import services_hackathon_eval as ev
import services_leaderboard
from tests.test_hackathon_marks import CODES, _csv, mk  # noqa: F401  (the UPG-308 fixture)
from tests.test_hackathon_phase2 import p2  # noqa: F401
from tests.test_hackathon_portal import hack  # noqa: F401
from tests.test_integration_flow import _login, _unique, _user

CRITERIA = [{'name': 'Innovation', 'max_score': 40}, {'name': 'Tech', 'max_score': 30},
            {'name': 'Demo', 'max_score': 30}]


@pytest.fixture
def fin(mk):  # noqa: F811
    h = mk

    def finale(n=3, criteria=CRITERIA, judges=3):
        """Five teams, round 1 marked from a file, the top n in the finale, and judges."""
        eid, teams = h['mk_setup']()
        h['after']()
        marks = {'Alpha': 95, 'Bravo': 90, 'Charlie': 85, 'Delta': 40, 'Echo': 30}
        h['upload'](eid, _csv([[CODES[k], v] for k, v in marks.items()]), n=n)
        assert h['mk_submit'](eid, n=n).status_code == 302
        emails = [f"{_unique('fjudge')}@test.edu" for _ in range(judges)]
        for e in emails:
            _user(h['db'], e, 'Judge')
        h['db'].collection('events').document(eid).update({
            'judging_criteria': criteria, 'open_hall_mode': False,
            'staff': [{'name': f'Judge {i}', 'email': e, 'role': 'Judge'} for i, e in enumerate(emails)]})
        clients = [_login(h['app'], e, 'Judge') for e in emails]
        return eid, teams, clients, emails

    def score(client, t, values):
        return client.post(f"/judge/score_inline/{t['id']}", json={
            'scores': dict(zip([c['name'] for c in CRITERIA], values)), 'remarks': ''})

    h.update({'finale': finale, 'score': score})
    return h


def _cards(html):
    return set(re.findall(r'id="card-([^"]+)"', html))


# 1. Every judge sees every finalist, none assigned, none checked in; no team that is out
def test_every_judge_sees_every_finalist(fin):
    eid, teams, judges, emails = fin['finale']()
    finalists = {teams[n]['id'] for n in ('Alpha', 'Bravo', 'Charlie')}
    assert all(fin['reg'](teams[n])['attendance'] != 'Present' for n in ('Alpha', 'Bravo', 'Charlie'))
    # one finalist assigned to the first judge must still show to the others
    fin['db'].collection('registrations').document(teams['Alpha']['id']).update(
        {'assigned_judge_email': emails[0]})
    for client in judges:
        page = client.get(f'/judge/event/{eid}')
        assert page.status_code == 200
        assert _cards(page.get_data(as_text=True)) == finalists
    # the dashboard counts the same three finalists, and this judge's own scores
    assert '<strong>0 / 3</strong>' in judges[1].get('/judge/dashboard').get_data(as_text=True)
    assert fin['score'](judges[1], teams['Bravo'], (20, 20, 20)).status_code == 200
    assert '<strong>1 / 3</strong>' in judges[1].get('/judge/dashboard').get_data(as_text=True)
    assert '<strong>0 / 3</strong>' in judges[2].get('/judge/dashboard').get_data(as_text=True)


# 2. The team code on each card and a search by name or code
def test_the_judge_finds_a_team_by_name_or_code(fin):
    eid, teams, judges, _ = fin['finale']()
    html = judges[0].get(f'/judge/event/{eid}').get_data(as_text=True)
    assert 'data-team-search' in html
    assert f'data-team-code>{CODES["Alpha"]}<' in html
    card = re.search(r'id="card-%s"[^>]*data-team-find="([^"]+)"' % re.escape(teams['Bravo']['id']), html)
    assert card and 'bravo' in card.group(1) and CODES['Bravo'].lower() in card.group(1)


# 3. A judge's score is the marks added up; a team's score averages whoever scored it
def test_a_score_is_the_sum_and_a_team_averages_its_judges(fin):
    eid, teams, judges, _ = fin['finale']()
    r = fin['score'](judges[0], teams['Alpha'], (35, 25, 20))
    assert r.status_code == 200 and r.get_json()['message'] == 'Score saved: 80 / 100'
    assert fin['score'](judges[1], teams['Alpha'], (30, 30, 30)).status_code == 200
    assert fin['score'](judges[2], teams['Bravo'], (40, 30, 25)).status_code == 200
    # the full-page form says the same
    resp = judges[2].post(f"/judge/submit_score/{teams['Charlie']['id']}",
                          json={'scores': {'Innovation': 20, 'Tech': 20, 'Demo': 20}},
                          headers={'Accept': 'application/json'})
    assert resp.get_json()['message'] == 'Score saved: 60 / 100'
    assert services_leaderboard.score_of(fin['reg'](teams['Alpha'])) == (85.0, 2)   # (80 + 90) / 2
    assert services_leaderboard.score_of(fin['reg'](teams['Bravo'])) == (95.0, 1)   # one judge only
    page = judges[0].get(f'/judge/event/{eid}').get_data(as_text=True)
    assert re.search(r'id="card-%s".*?score-badge done">80<' % re.escape(teams['Alpha']['id']), page, re.S)


# 4. The finale ranking: judges' average, how many judges, no round-1 marks or SPOC score
def test_the_finale_ranking_uses_only_the_judges(fin):
    eid, teams, judges, _ = fin['finale']()
    fin['score'](judges[0], teams['Charlie'], (40, 30, 30))
    fin['score'](judges[1], teams['Charlie'], (30, 20, 20))
    rows = {r['team']: r for r in fin['rows'](eid)}
    assert set(rows) == {'Alpha', 'Bravo', 'Charlie'}
    assert rows['Charlie']['key'] == 85.0 and rows['Charlie']['judges_n'] == 2
    assert rows['Alpha']['key'] is None                       # its 95 from the file doesn't count
    html = fin['owner'].get(f'/spoc/hackathon/{eid}').get_data(as_text=True)
    assert 'data-finale-judging' in html and 'Your score &amp; note' not in html
    unscored = re.search(r'data-finale-unscored>(.*?)</span>', html, re.S).group(1)
    assert 'Alpha' in unscored and 'Bravo' in unscored and 'Charlie' not in unscored


# 5. The results rank the finalists by the judges' average only
def test_results_rank_finalists_by_the_judges(fin):
    eid, teams, judges, _ = fin['finale']()
    fin['score'](judges[0], teams['Charlie'], (40, 30, 30))      # 100
    fin['score'](judges[1], teams['Charlie'], (38, 28, 28))      # 94 → 97
    fin['score'](judges[0], teams['Alpha'], (30, 20, 20))        # 70
    fin['score'](judges[2], teams['Bravo'], (35, 25, 25))        # 85
    event = fin['ev'](eid) | {'id': eid}
    ev.publish_results(fin['db'], eid, event, actor='test')
    outcome = {n: fin['reg'](teams[n]) for n in ('Alpha', 'Bravo', 'Charlie', 'Delta')}
    assert outcome['Charlie']['final_rank'] == 1 and outcome['Charlie']['final_score'] == 97.0
    assert outcome['Bravo']['final_rank'] == 2 and outcome['Alpha']['final_rank'] == 3
    assert outcome['Delta']['result_outcome'] == 'Participant'


# 6. The criteria total is shown, with a warning when it isn't 100
def test_criteria_that_dont_add_up_to_100_are_flagged(fin):
    eid, _, _, _ = fin['finale'](criteria=[{'name': 'Innovation', 'max_score': 40},
                                           {'name': 'Tech', 'max_score': 30},
                                           {'name': 'Demo', 'max_score': 20}])
    html = fin['owner'].get(f'/spoc/hackathon/{eid}').get_data(as_text=True)
    assert 'data-criteria-not-100' in html and 'add up to 90' in html
    fin['db'].collection('events').document(eid).update({'judging_criteria': CRITERIA})
    html = fin['owner'].get(f'/spoc/hackathon/{eid}').get_data(as_text=True)
    assert 'data-criteria-not-100' not in html and 'total <strong>100</strong>' in html


def test_before_the_shortlist_assigned_judging_is_unchanged(fin):
    """A non-hackathon event still shows a judge only checked-in teams assigned to them."""
    eid, teams = fin['mk_setup'](('Alpha',), file_mode=False)
    judge = f"{_unique('fjudge')}@test.edu"
    _user(fin['db'], judge, 'Judge')
    fin['db'].collection('events').document(eid).update(
        {'staff': [{'name': 'J', 'email': judge, 'role': 'Judge'}], 'judging_criteria': CRITERIA})
    from routes_judge import finale_round
    assert not finale_round(fin['ev'](eid) | {'id': eid})




# 1. (the setting) On by itself after the evaluators' marks; a switch for other rounds; staff only
def test_every_judge_every_finalist_is_a_setting(fin):
    from tests.test_judging_modes import _mode, _score, _shortlist, _two_judges
    eid, teams, _, _ = fin['finale']()
    assert ev.finale_open(fin['ev'](eid))                 # the marks' Submit turned it on
    assert 'data-finale-open="1"' in fin['owner'].get(f'/spoc/hackathon/{eid}').get_data(as_text=True)

    # a round scored by judges then shortlisted: judged as before until the SPOC switches
    eid, teams = fin['setup'](names=('Alpha', 'Bravo'))
    _mode(fin, eid, 'judges')
    (j1, _), _ = _two_judges(fin, eid)
    fin['after']()
    _score(j1, teams['Alpha']['id'], Innovation=9, Design=9)
    _, go, expected = _shortlist(fin, eid, 1)
    fin['owner'].post(f'/spoc/hackathon/{eid}/shortlist/confirm', data={'go': go, 'expected_round': expected})
    assert not ev.finale_open(fin['ev'](eid))
    assert _cards(j1.get(f'/judge/event/{eid}').get_data(as_text=True)) == set()   # none checked in
    assert fin['stranger'].post(f'/spoc/hackathon/{eid}/finale_judges', data={'open': '1'}).status_code == 403
    assert not ev.finale_open(fin['ev'](eid))
    assert fin['owner'].post(f'/spoc/hackathon/{eid}/finale_judges', data={'open': '1'}).status_code == 302
    assert _cards(j1.get(f'/judge/event/{eid}').get_data(as_text=True)) == {teams['Alpha']['id']}
    fin['owner'].post(f'/spoc/hackathon/{eid}/finale_judges', data={'open': '0'})
    assert _cards(j1.get(f'/judge/event/{eid}').get_data(as_text=True)) == set()
