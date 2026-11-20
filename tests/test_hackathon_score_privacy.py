"""
tests/test_hackathon_score_privacy.py — UPG-336: in the hackathon's finale
(round 2) the SPOC changes any judge's mark for a team on the hackathon page,
until the results are out; the team's score, rank and results follow. Teams
never see a score or the judges' marks: not on their dashboard while judging
goes on, and once the results are out they see only their place (dashboard,
hackathon page, result email).
"""
import re

import services_hackathon_eval as ev
import services_leaderboard
import utils_email
from tests.test_hackathon_finale import fin  # noqa: F401  (the UPG-309 fixture)
from tests.test_hackathon_marks import CODES, _csv, mk  # noqa: F401
from tests.test_hackathon_phase2 import p2  # noqa: F401
from tests.test_hackathon_portal import hack  # noqa: F401


def _mark(fin, eid, team, judge, score, client=None):  # noqa: F811
    return (client or fin['owner']).post(f"/spoc/hackathon/{eid}/judge_mark/{team['id']}",
                                         data={'judge': judge, 'score': str(score)})


def _dash(team):
    resp = team['client'].get('/participant/dashboard')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


# 1. While the finale is judged, a team's dashboard shows no score and no judge's marks
def test_a_team_sees_no_score_while_judging_goes_on(fin):  # noqa: F811
    eid, teams, judges, emails = fin['finale']()
    assert fin['score'](judges[0], teams['Alpha'], (37, 26, 24)).status_code == 200    # 87
    html = _dash(teams['Alpha'])
    assert fin['ev'](eid)['title'] in html
    for leak in ('Your score', 'data-scores', 'raw_total', 'Score breakdown', 'scoreModal', '>87<', emails[0]):
        assert leak not in html, leak
    assert 'data-place' not in html                               # no place before the results


# 2. The SPOC sees each judge's mark and changes one; the score and ranking follow
def test_the_spoc_changes_a_judges_mark_and_the_ranking_follows(fin):  # noqa: F811
    eid, teams, judges, emails = fin['finale']()
    fin['score'](judges[0], teams['Alpha'], (30, 20, 20))        # 70
    fin['score'](judges[1], teams['Alpha'], (30, 20, 20))        # 70
    fin['score'](judges[0], teams['Bravo'], (35, 25, 20))        # 80
    page = fin['owner'].get(f'/spoc/hackathon/{eid}').get_data(as_text=True)
    assert f'data-judge-mark="{emails[0]}"' in page and f'/judge_mark/{teams["Alpha"]["id"]}' in page
    assert 'until you publish the results' in page

    resp = _mark(fin, eid, teams['Alpha'], emails[0], 96)
    assert resp.status_code == 302 and resp.headers['Location'].endswith('#ranking')
    assert services_leaderboard.score_of(fin['reg'](teams['Alpha'])) == (83.0, 2)       # (96 + 70) / 2
    rows = {r['team']: r for r in fin['rows'](eid)}
    assert rows['Alpha']['rank'] == 1 and rows['Bravo']['rank'] == 2
    entry = fin['reg'](teams['Alpha'])['scores'][emails[0]]
    assert entry['raw_total'] == 96 and entry['spoc_edit']['from'] == 70 and entry['details']   # the judge's own marks kept
    # changed twice: "was" stays the judge's own mark
    _mark(fin, eid, teams['Alpha'], emails[0], 90)
    assert fin['reg'](teams['Alpha'])['scores'][emails[0]]['spoc_edit']['from'] == 70
    page = fin['owner'].get(f'/spoc/hackathon/{eid}').get_data(as_text=True)
    assert 'edited (was 70)' in page
    # the other judge's mark is untouched
    assert fin['reg'](teams['Alpha'])['scores'][emails[1]]['raw_total'] == 70


# 3. Only a number within the criteria total, only a judge who scored, only the SPOC
def test_a_mark_is_checked_and_only_the_spoc_changes_it(fin):  # noqa: F811
    eid, teams, judges, emails = fin['finale']()
    fin['score'](judges[0], teams['Alpha'], (30, 20, 20))
    for bad in ('101', '-1', 'abc'):
        _mark(fin, eid, teams['Alpha'], emails[0], bad)
        assert fin['reg'](teams['Alpha'])['scores'][emails[0]]['raw_total'] == 70, bad
    ok, msg = ev.set_judge_mark(fin['db'], eid, fin['ev'](eid) | {'id': eid}, teams['Alpha']['id'], emails[1], 50, 'x')
    assert not ok and "hasn't scored" in msg
    for client in (fin['stranger'], judges[1], teams['Alpha']['client']):
        assert _mark(fin, eid, teams['Alpha'], emails[0], 10, client=client).status_code == 403
    assert fin['reg'](teams['Alpha'])['scores'][emails[0]]['raw_total'] == 70


# 4. After the results: the team sees its place only, everywhere; the marks are fixed
def test_after_the_results_a_team_sees_only_its_place(fin, monkeypatch):  # noqa: F811
    eid, teams, judges, emails = fin['finale']()
    fin['score'](judges[0], teams['Charlie'], (37, 26, 24))      # 87
    fin['score'](judges[0], teams['Alpha'], (30, 20, 20))        # 70
    fin['score'](judges[0], teams['Bravo'], (33, 22, 22))        # 77
    mails = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: mails.append((to, html)) or True)
    assert fin['owner'].post(f'/spoc/publish_results/{eid}').status_code == 302
    assert fin['reg'](teams['Charlie'])['final_rank'] == 1

    html = _dash(teams['Charlie'])                                # the event is over: a past card
    card = re.search(r'<div id="past">.*?<div id="discover"', html, re.S).group(0)
    meta = re.search(r'past-card__meta">(.*?)</div>', card, re.S).group(1)
    assert 'Rank #1' in meta and '87' not in meta
    for leak in ('Your score', 'data-scores', 'raw_total', '/100'):
        assert leak not in card, leak
    assert 'Score breakdown' not in html and 'data-scores' not in html
    # on a card still active (the event not marked over) the place shows as "Your place: 1st"
    fin['db'].collection('events').document(eid).update({'status': 'in_progress'})
    html = _dash(teams['Charlie'])
    place = re.search(r'data-place>(.*?)</div>\s*</div>', html, re.S)
    assert place and '1st' in place.group(1) and 'Your place' in place.group(1) and '87' not in place.group(1)
    fin['db'].collection('events').document(eid).update({'status': 'completed'})

    portal = teams['Charlie']['client'].get(f'/hackathon/{eid}').get_data(as_text=True)
    result = re.search(r'id="results".*?</section>', portal, re.S).group(0)
    assert 'rank 1' in result and '87' not in result and 'score' not in result.lower()

    lead_mail = [h for to, h in mails if to == teams['Charlie']['lead']]
    assert lead_mail and 'Rank 1' in lead_mail[0] and 'score' not in lead_mail[0].lower()

    # the marks can't change now
    _mark(fin, eid, teams['Alpha'], emails[0], 99)
    assert fin['reg'](teams['Alpha'])['scores'][emails[0]]['raw_total'] == 70
    page = fin['owner'].get(f'/spoc/hackathon/{eid}').get_data(as_text=True)
    forms = re.findall(r'<form[^>]*data-judge-mark=.*?</form>', page, re.S)
    assert forms and all('name="score"' not in f for f in forms)


def test_the_whatsapp_result_has_no_score_when_none_is_given():
    import utils_whatsapp
    sent = []
    orig = utils_whatsapp._send
    utils_whatsapp._send = lambda phone, body: sent.append(body) or True
    try:
        utils_whatsapp.send_result_whatsapp('9000000000', 'Lena', 'Hack', 1, None)
        utils_whatsapp.send_result_whatsapp('9000000000', 'Lena', 'Hack', 2, 81.5)
    finally:
        utils_whatsapp._send = orig
    assert 'Score' not in sent[0] and 'Your Rank:* 1' in sent[0]
    assert 'Score:*     81.5' in sent[1]                           # other events as before
