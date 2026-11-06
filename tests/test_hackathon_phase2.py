"""
tests/test_hackathon_phase2.py — Phase 2 of the hackathon (owner's request,
2026-11-05), on the real database layer with Gemini replaced:

  * UPG-192: after the deadline AI scores each submission against the SPOC's
    criteria; a bad reply is "not scored"; one failure doesn't stop the rest;
    starting again resumes; no key means no calls; judges never see it.
  * UPG-193: the ranking (the SPOC's score overrides the AI total), the
    shortlist preview with ties, confirm (history, portal notices, the
    "Finalists announced" update, no email) and undo.
  * UPG-194: judges see only finalists and their submissions (no AI score);
    publishing from either path emails each team's lead exactly once and
    nobody else; results and certificates on the team's page.
"""
import datetime
import json
import re

import pytest

import services_hackathon as hk
import services_hackathon_eval as ev
from tests.test_hackathon_portal import _page, _reg_id, hack  # noqa: F401  (the Phase 1 fixture)
from tests.test_integration_flow import PASSWORD, _login, _unique, _user

UTC = datetime.timezone.utc
AFTER = datetime.datetime(2026, 11, 23, 4, 30, tzinfo=UTC)   # the day after the deadline
NAMES = ('Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo')


def make_pdf(text: str) -> bytes:
    """A one-page PDF whose text pdfium can read."""
    stream = f"BT /F1 18 Tf 50 700 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


def reply(value=8, reason='Solid work.', **override):
    scores = {c: value for c, _ in ev.DEFAULT_CRITERIA}
    scores.update(override)
    return json.dumps({'scores': scores, 'reason': reason})


@pytest.fixture
def p2(hack, monkeypatch):  # noqa: F811
    h = hack
    monkeypatch.setitem(h['app'].config, 'GEMINI_API_KEY', 'test-key')
    calls, script = [], {}

    def fake(system, data):
        calls.append({'system': system, 'data': data})
        title = json.loads(data)['project_title']
        answer = script.get(title.split()[0], script.get('*', reply()))
        if isinstance(answer, Exception):
            raise answer
        return answer(data) if callable(answer) else answer
    monkeypatch.setattr(ev, '_call_model', fake)

    def setup(names=NAMES, submit=None):
        h['clock']['now'] = datetime.datetime(2026, 11, 20, 4, 30, tzinfo=UTC)   # submissions open
        eid = h['event']()
        h['problem'](eid, 'Clean water')
        pid = hk.problems(h['ev'](eid))[0]['id']
        assert h['form'](eid).status_code == 302
        teams = {}
        for name in names:
            t = h['team'](eid, name, members=(f"{_unique(name.lower() + 'mate')}@test.edu",))
            teams[name] = t
            if submit is None or name in submit:
                resp = h['submit'](t, eid, Project_title=f"{name} Project", Problem_statement=pid,
                                   GitHub_repository=f'https://github.com/x/{name}',
                                   Presentation=make_pdf(f"{name} deck slide text"), Approach=f"{name} approach notes")
                assert resp.status_code == 302 and h['sub'](t), name
            t['id'] = _reg_id(h['db'], t)
        return eid, teams

    def after():
        h['clock']['now'] = AFTER

    def score_all(eid):
        h['owner'].post(f'/spoc/hackathon/{eid}/ai/start')
        for _ in range(20):
            p = h['owner'].post(f'/spoc/hackathon/{eid}/ai/next', json={},
                                headers={'Accept': 'application/json'}).get_json()
            if p['finished']:
                return p
        raise AssertionError('the run never finished')

    def scored(eid, values):
        """AI totals by team: value × 10 (every criterion gets `value`)."""
        script.clear()
        script.update({name: reply(v) for name, v in values.items()})
        return score_all(eid)

    def rows(eid, sort='rank'):
        return ev.ranking(h['db'], eid, h['ev'](eid) | {'id': eid}, sort)

    def reg(t):
        return h['db'].collection('registrations').document(t['id']).get().to_dict()

    def notices(email):
        return [d.to_dict() for d in h['db'].collection('notifications_v2').where('user_email', '==', email).stream()]

    h.update({'calls': calls, 'script': script, 'setup': setup, 'after': after, 'score_all': score_all,
              'scored': scored, 'rows': rows, 'reg': reg, 'notices': notices})
    return h


def _order(html):
    return re.findall(r'<tr data-reg="([^"]+)"', html)


def _judge(h, eid):
    judge = f"{_unique('hkjudge')}@test.edu"
    _user(h['db'], judge, 'Judge')
    h['db'].collection('events').document(eid).update({
        'open_hall_mode': True, 'staff': [{'name': 'Judy', 'email': judge, 'role': 'Judge'}],
        'judging_criteria': [{'name': 'Innovation', 'description': 'Ideas', 'max_score': 10}]})
    return _login(h['app'], judge, 'Judge')


def _shortlist(h, eid, n, teams=None):
    form = {'mode': 'top_n', 'n': str(n)} if teams is None else {'mode': 'pick', 'pick': teams}
    page = h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/preview', data=form)
    assert page.status_code == 200, page.headers.get('Location')
    html = page.get_data(as_text=True)
    go = re.findall(r'name="go" value="([^"]+)"', html)
    found = re.search(r'name="expected_round" value="(\d+)"', html)
    assert found, html[:300]
    return html, go, found.group(1)


# ═══ UPG-192: AI scoring ════════════════════════════════════════════════════

def test_ai_scores_every_submission_after_the_deadline_and_not_before(p2):
    h = p2
    eid, teams = h['setup']()
    # Before the deadline: refused, nothing called
    resp = h['owner'].post(f'/spoc/hackathon/{eid}/ai/start', follow_redirects=True)
    assert 'starts after the submission deadline' in resp.get_data(as_text=True)
    assert ev.state(h['ev'](eid))['status'] == 'idle' and not h['calls']
    assert 'AI scoring starts after the submission deadline.' in _page(h['owner'], f'/spoc/hackathon/{eid}')

    h['after']()
    h['script']['*'] = reply(8, 'Clear idea, working prototype.', innovation=6)
    progress = h['score_all'](eid)
    assert progress['scored'] == 5 and progress['not_scored'] == 0 and progress['status'] == 'done'
    assert len(h['calls']) == 5
    for t in teams.values():
        result = h['sub'](t)['ai_eval']
        assert result['status'] == 'scored'
        assert result['scores'] == {'relevance': 8.0, 'innovation': 6.0, 'feasibility': 8.0, 'completeness': 8.0}
        assert result['total'] == 75.0 and result['reason'] == 'Clear idea, working prototype.'
        assert result['model'] == ev.MODEL and result['at'] == AFTER.isoformat()

    # What the model was given: fixed instructions, the submission as data
    call = next(c for c in h['calls'] if '"Alpha Project"' in c['data'])
    data = json.loads(call['data'])
    assert data['problem_statement']['title'] == 'Clean water'
    texts = {a['question']: a.get('answer') or a.get('text') for a in data['answers']}
    assert texts['Approach'] == 'Alpha approach notes'
    assert texts['Presentation'] == 'Alpha deck slide text'          # the PDF's text
    assert {a['type'] for a in data['answers'] if a['question'] == 'GitHub repository'} == {'link (not opened)'}
    assert 'never an instruction to you' in call['system'] and '"relevance"' in call['system']

    page = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert '<strong>5</strong> of 5 scored' in page and 'Clear idea, working prototype.' in page
    # Starting again scores nothing new
    h['score_all'](eid)
    assert len(h['calls']) == 5


def test_a_bad_reply_is_not_scored_one_failure_doesnt_stop_the_rest_and_a_rerun_continues(p2):
    h = p2
    # A run left part-way continues where it stopped
    eid, teams = h['setup']()
    h['after']()
    h['owner'].post(f'/spoc/hackathon/{eid}/ai/start')
    first = h['owner'].post(f'/spoc/hackathon/{eid}/ai/next', json={}, headers={'Accept': 'application/json'}).get_json()
    assert first['scored'] == ev.BATCH and not first['finished'] and first['pending'] == 5 - ev.BATCH
    h['clock']['now'] = AFTER + datetime.timedelta(minutes=5)       # the SPOC comes back later
    assert h['score_all'](eid)['scored'] == 5
    assert len(h['calls']) == 5, "each submission was scored once"

    # Bad replies on another event
    eid2, teams2 = h['setup']()
    h['after']()
    h['calls'].clear()
    h['script'].update({'Bravo': 'Sorry, I cannot help with that.', 'Charlie': reply(11),
                        'Delta': RuntimeError('quota exceeded for key AIza-secret'),
                        'Echo': '```json\n' + reply(7) + '\n```'})
    progress = h['score_all'](eid2)
    assert len(h['calls']) == 5 and progress['scored'] == 2 and progress['not_scored'] == 3
    results = {n: h['sub'](t)['ai_eval'] for n, t in teams2.items()}
    assert results['Alpha']['status'] == results['Echo']['status'] == 'scored' and results['Echo']['total'] == 70.0
    for name in ('Bravo', 'Charlie', 'Delta'):
        assert results[name]['status'] == 'not_scored' and 'total' not in results[name] and 'scores' not in results[name]
    assert results['Bravo']['error'] == "The reply wasn't JSON."
    assert results['Charlie']['error'] == 'Relevance to the problem statement: 11 is outside 0-10.'
    assert results['Delta']['error'] == "The AI service didn't answer." and 'secret' not in json.dumps(results)
    rows = {r['team']: r for r in h['rows'](eid2)}
    assert rows['Bravo']['ai_total'] is None and rows['Bravo']['key'] is None
    assert 'Not scored' in _page(h['owner'], f'/spoc/hackathon/{eid2}')

    # Re-run one submission
    h['script'].update({'Delta': reply(9)})
    h['owner'].post(f"/spoc/hackathon/{eid2}/ai/{rows['Delta']['sub_id']}/rerun")
    assert h['sub'](teams2['Delta'])['ai_eval']['total'] == 90.0 and len(h['calls']) == 6
    # Starting again retries only what failed before it started
    h['clock']['now'] = AFTER + datetime.timedelta(minutes=10)
    h['script'].update({'Bravo': reply(6), 'Charlie': reply(5)})
    h['score_all'](eid2)
    assert len(h['calls']) == 8
    assert {n: h['sub'](t)['ai_eval'].get('total') for n, t in teams2.items()} == \
        {'Alpha': 80.0, 'Bravo': 60.0, 'Charlie': 50.0, 'Delta': 90.0, 'Echo': 70.0}

    # The reply parser refuses anything not exactly as asked
    crits = ev.criteria({})
    for raw in ('', '[]', '{"scores": []}', reply(True), reply(-1), reply(float('nan')),
                json.dumps({'scores': {'relevance': 5}}), reply(5, 'x' * ev.REPLY_CHARS), reply('7')):
        with pytest.raises(ev.ReplyError):
            ev.parse_reply(raw, crits)
    scores, reason = ev.parse_reply(reply(7.5, 'x' * 900, extra=3), crits)
    assert scores['relevance'] == 7.5 and 'extra' not in scores and len(reason) == ev.REASON_CHARS


def test_the_spoc_sets_criteria_until_a_submission_is_scored(p2):
    h = p2
    eid, teams = h['setup'](names=('Alpha', 'Bravo'))
    h['owner'].post(f'/spoc/hackathon/{eid}/ai/criteria',
                    data={'criterion_0': 'Impact', 'criterion_1': 'Code quality', 'criterion_2': ''})
    assert ev.criteria(h['ev'](eid)) == [{'id': 'impact', 'label': 'Impact'},
                                         {'id': 'code_quality', 'label': 'Code quality'}]
    h['after']()
    h['script']['*'] = json.dumps({'scores': {'impact': 6, 'code_quality': 8}, 'reason': 'ok'})
    h['score_all'](eid)
    assert h['sub'](teams['Alpha'])['ai_eval']['total'] == 70.0
    resp = h['owner'].post(f'/spoc/hackathon/{eid}/ai/criteria', data={'criterion_0': 'Other'}, follow_redirects=True)
    assert "can't change now" in resp.get_data(as_text=True).replace('&#39;', "'")
    assert [c['id'] for c in ev.criteria(h['ev'](eid))] == ['impact', 'code_quality']


def test_without_a_key_ai_scoring_is_off_and_nothing_is_called(p2, monkeypatch):
    h = p2
    monkeypatch.setitem(h['app'].config, 'GEMINI_API_KEY', '')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    eid, _teams = h['setup'](names=('Alpha', 'Bravo'))
    h['after']()
    page = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert 'AI scoring is off' in page and 'Start AI scoring' not in page
    resp = h['owner'].post(f'/spoc/hackathon/{eid}/ai/start', follow_redirects=True)
    assert 'AI scoring is off' in resp.get_data(as_text=True)
    h['owner'].post(f'/spoc/hackathon/{eid}/ai/next')
    assert not h['calls'] and ev.state(h['ev'](eid))['status'] == 'idle'
    # The SPOC still ranks by hand
    alpha = next(r for r in h['rows'](eid) if r['team'] == 'Alpha')
    h['owner'].post(f"/spoc/hackathon/{eid}/review/{alpha['reg_id']}", data={'score': '64', 'note': 'Good demo'})
    assert next(r for r in h['rows'](eid) if r['team'] == 'Alpha')['key'] == 64.0


def test_another_spoc_gets_403_and_judges_never_see_the_ai_score(p2):
    h = p2
    eid, teams = h['setup'](names=('Alpha', 'Bravo'))
    h['after']()
    h['script']['*'] = reply(8, 'Distinctive AI reasoning text.')
    h['score_all'](eid)
    sub_id = h['rows'](eid)[0]['sub_id']
    reg_id = teams['Alpha']['id']
    for method, url in (('get', f'/spoc/hackathon/{eid}'), ('post', f'/spoc/hackathon/{eid}/ai/start'),
                        ('post', f'/spoc/hackathon/{eid}/ai/next'), ('post', f'/spoc/hackathon/{eid}/ai/criteria'),
                        ('post', f'/spoc/hackathon/{eid}/ai/{sub_id}/rerun'),
                        ('post', f'/spoc/hackathon/{eid}/review/{reg_id}'),
                        ('post', f'/spoc/hackathon/{eid}/shortlist/preview'),
                        ('post', f'/spoc/hackathon/{eid}/shortlist/confirm'),
                        ('post', f'/spoc/hackathon/{eid}/shortlist/undo'),
                        ('post', f'/spoc/hackathon/{eid}/results/resend'),
                        ('get', f'/hackathon/{eid}/review/{reg_id}')):
        assert getattr(h['stranger'], method)(url).status_code == 403, url
    assert not ev.shortlist(h['ev'](eid))

    judge = _judge(h, eid)
    for t in teams.values():
        h['db'].collection('registrations').document(t['id']).update({'attendance': 'Present'})
    listing = _page(judge, f'/judge/event/{eid}')
    view = _page(judge, f'/hackathon/{eid}/review/{reg_id}')
    assert 'Alpha approach notes' in view
    for html in (listing, view):
        assert 'Distinctive AI reasoning' not in html and 'AI evaluation' not in html and '80.0' not in html
    staff_view = _page(h['owner'], f'/hackathon/{eid}/review/{reg_id}')
    assert 'Distinctive AI reasoning text.' in staff_view and '80.0 / 100' in staff_view
    # The team's own page doesn't show it either
    assert 'Distinctive AI reasoning' not in _page(teams['Alpha']['client'], f'/hackathon/{eid}')


# ═══ UPG-193: the ranking and the shortlist ════════════════════════════════

def test_the_ranking_sorts_by_ai_and_by_the_spoc_and_keeps_the_override(p2):
    h = p2
    eid, teams = h['setup']()
    h['after']()
    h['scored'](eid, {'Alpha': 5, 'Bravo': 9, 'Charlie': 7, 'Delta': 3, 'Echo': 6})
    ids = {n: t['id'] for n, t in teams.items()}
    by_name = {v: k for k, v in ids.items()}
    assert [by_name[i] for i in _order(_page(h['owner'], f'/spoc/hackathon/{eid}'))] == \
        ['Bravo', 'Charlie', 'Echo', 'Alpha', 'Delta']

    # The SPOC's score overrides the AI total in the ranking, not in the AI sort
    resp = h['owner'].post(f"/spoc/hackathon/{eid}/review/{ids['Delta']}", data={'score': '95', 'note': 'Best demo'})
    assert resp.status_code == 302
    page = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert [by_name[i] for i in _order(page)] == ['Delta', 'Bravo', 'Charlie', 'Echo', 'Alpha']
    assert 'Best demo' in page
    assert [by_name[i] for i in _order(_page(h['owner'], f'/spoc/hackathon/{eid}?sort=ai'))] == \
        ['Bravo', 'Charlie', 'Echo', 'Alpha', 'Delta']
    top = h['rows'](eid)[0]
    assert (top['team'], top['rank'], top['ai_total'], top['spoc_score']) == ('Delta', 1, 30.0, 95.0)

    # Kept when the AI score is re-run; a bad score is refused; blank clears it
    h['script']['Delta'] = reply(4)
    h['owner'].post(f"/spoc/hackathon/{eid}/ai/{top['sub_id']}/rerun")
    assert h['rows'](eid)[0]['team'] == 'Delta' and h['sub'](teams['Delta'])['spoc_review']['note'] == 'Best demo'
    h['owner'].post(f"/spoc/hackathon/{eid}/review/{ids['Delta']}", data={'score': '140'})
    assert h['sub'](teams['Delta'])['spoc_review']['score'] == 95.0
    h['owner'].post(f"/spoc/hackathon/{eid}/review/{ids['Delta']}", data={'score': '', 'note': ''})
    assert [r['team'] for r in h['rows'](eid)][-1] == 'Delta'


def test_shortlisting_the_top_3_of_5_moves_3_on_and_eliminates_2_with_no_email(p2):
    h = p2
    eid, teams = h['setup']()
    h['after']()
    h['scored'](eid, {'Alpha': 5, 'Bravo': 9, 'Charlie': 7, 'Delta': 3, 'Echo': 6})
    h['sent'].clear()
    html, go, expected = _shortlist(h, eid, 3)
    assert sorted(go) == sorted(teams[n]['id'] for n in ('Bravo', 'Charlie', 'Echo'))
    assert 'To the finale (3)' in html and 'Eliminated (2)' in html and 'Tie at the cut-off' not in html
    assert not h['ev'](eid).get('shortlist_published'), 'a preview changes nothing'

    resp = h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/confirm', data={'go': go, 'expected_round': expected},
                           follow_redirects=True)
    assert 'Finalists announced' in resp.get_data(as_text=True)
    event = h['ev'](eid)
    assert event['active_round'] == 2 and event['total_rounds'] == 2 and event['shortlist_published'] is True
    for name, t in teams.items():
        reg = h['reg'](t)
        entry = reg['round_history'][-1]
        if name in ('Bravo', 'Charlie', 'Echo'):
            assert reg['current_round'] == 2 and not reg['is_eliminated'] and entry['result'] == 'qualified'
            title = 'Shortlisted for the finale'
        else:
            assert reg['is_eliminated'] and reg['eliminated_in_round'] == 1 and entry['result'] == 'eliminated'
            title = 'Shortlist result'
        assert entry['round'] == 1 and entry['kind'] == 'shortlist'
        assert entry['score'] == {'Alpha': 50.0, 'Bravo': 90.0, 'Charlie': 70.0, 'Delta': 30.0, 'Echo': 60.0}[name]
        for person in (t['lead'], reg['members'][0]['email']):
            assert any(n['title'].startswith(title) for n in h['notices'](person)), (name, person)
    update = hk.updates(h['ev'](eid))[0]
    assert update['title'] == 'Finalists announced' and 'Bravo, Charlie, Echo' in update['message']
    assert h['sent'] == [], 'nothing is emailed in portal mode'
    # A second confirm of the same preview changes nothing
    again = h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/confirm', data={'go': go, 'expected_round': expected},
                            follow_redirects=True)
    assert 'already announced' in again.get_data(as_text=True) and h['ev'](eid)['active_round'] == 2

    # By hand: a team that didn't submit can't be picked
    eid2, teams2 = h['setup'](names=('Alpha', 'Bravo', 'Charlie'), submit=('Alpha', 'Bravo'))
    resp = h['owner'].post(f'/spoc/hackathon/{eid2}/shortlist/preview',
                           data={'mode': 'pick', 'pick': [teams2['Charlie']['id']]}, follow_redirects=True)
    assert "didn" in resp.get_data(as_text=True) and not h['ev'](eid2).get('shortlist_published')
    html, go, expected = _shortlist(h, eid2, 0, teams=[teams2['Alpha']['id']])
    assert go == [teams2['Alpha']['id']] and 'no submission' in html
    h['owner'].post(f'/spoc/hackathon/{eid2}/shortlist/confirm', data={'go': go, 'expected_round': expected})
    assert h['reg'](teams2['Charlie'])['is_eliminated'] and h['reg'](teams2['Bravo'])['is_eliminated']
    assert not h['reg'](teams2['Alpha'])['is_eliminated']


def test_a_tie_at_the_cut_is_shown_and_undo_restores_everyone_until_judging_starts(p2):
    h = p2
    eid, teams = h['setup']()
    h['after']()
    h['scored'](eid, {'Alpha': 5, 'Bravo': 9, 'Charlie': 7, 'Delta': 7, 'Echo': 6})
    html, go, expected = _shortlist(h, eid, 2)
    assert 'Tie at the cut-off' in html and 'Charlie, Delta' in html and '<strong>3</strong> finalists instead of 2' in html
    assert sorted(go) == sorted(teams[n]['id'] for n in ('Bravo', 'Charlie', 'Delta'))
    before = {n: h['reg'](t) for n, t in teams.items()}

    h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/confirm', data={'go': go, 'expected_round': expected})
    assert h['reg'](teams['Alpha'])['is_eliminated']
    page = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert 'Undo the shortlist' in page
    h['clock']['now'] += datetime.timedelta(minutes=1)
    resp = h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/undo', follow_redirects=True)
    assert 'shortlist is undone' in resp.get_data(as_text=True)
    for name, t in teams.items():
        reg = h['reg'](t)
        assert reg['current_round'] == 1 and reg['is_eliminated'] is False
        assert (reg.get('round_history') or []) == (before[name].get('round_history') or [])
    event = h['ev'](eid)
    assert event['active_round'] == 1 and event['shortlist_published'] is False and event['total_rounds'] == 1
    assert hk.updates(event)[0]['title'] == 'Shortlist withdrawn'
    assert any(n['title'].startswith('Shortlist withdrawn') for n in h['notices'](teams['Alpha']['lead']))
    assert h['sent'] == []

    # Shortlisted again; once a judge scores a finalist, undo is refused
    html, go, expected = _shortlist(h, eid, 1)
    assert [g for g in go] == [teams['Bravo']['id']]
    h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/confirm', data={'go': go, 'expected_round': expected})
    judge = _judge(h, eid)
    h['db'].collection('registrations').document(teams['Bravo']['id']).update({'attendance': 'Present'})
    assert judge.post(f"/judge/submit_score/{teams['Bravo']['id']}", json={'scores': {'Innovation': 8}}).status_code < 400
    resp = h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/undo', follow_redirects=True)
    assert "Judges have started scoring" in resp.get_data(as_text=True)
    assert h['reg'](teams['Alpha'])['is_eliminated'] and h['ev'](eid)['active_round'] == 2


def test_an_eliminated_team_sees_it_is_out_and_the_form_is_closed_to_it(p2):
    h = p2
    eid, teams = h['setup'](names=('Alpha', 'Bravo'))
    h['after']()
    h['scored'](eid, {'Alpha': 9, 'Bravo': 4})
    _html, go, expected = _shortlist(h, eid, 1)
    h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/confirm', data={'go': go, 'expected_round': expected})
    page = _page(teams['Bravo']['client'], f'/hackathon/{eid}')
    assert "wasn't shortlisted" in page.replace('&#39;', "'")
    assert re.search(r'data-stage="shortlist" data-state="done"', page)
    assert "Your team is shortlisted" in _page(teams['Alpha']['client'], f'/hackathon/{eid}')

    # Even if the SPOC reopens submissions, the form isn't there for Bravo and the server refuses
    h['owner'].post(f'/spoc/hackathon/{eid}/extend', data={'minutes': '1440'})
    assert hk.window(h['ev'](eid)) == 'open'
    page = _page(teams['Bravo']['client'], f'/hackathon/{eid}')
    assert 'action="/hackathon/' not in page and 'Submissions are closed to your team' in page
    before = h['sub'](teams['Bravo'])['updated_at']
    h['submit'](teams['Bravo'], eid, Project_title='Sneaky edit')
    assert h['sub'](teams['Bravo'])['updated_at'] == before and h['sub'](teams['Bravo'])['project_title'] == 'Bravo Project'
    assert f'action="/hackathon/{eid}/submit"' in _page(teams['Alpha']['client'], f'/hackathon/{eid}')


# ═══ UPG-194: the finale and the results ═══════════════════════════════════

def _finale(h, names=NAMES, top=3, values=None):
    eid, teams = h['setup'](names=names)
    h['after']()
    h['scored'](eid, values or {'Alpha': 5, 'Bravo': 9, 'Charlie': 7, 'Delta': 3, 'Echo': 6})
    _html, go, expected = _shortlist(h, eid, top)
    h['owner'].post(f'/spoc/hackathon/{eid}/shortlist/confirm', data={'go': go, 'expected_round': expected})
    judge = _judge(h, eid)
    for t in teams.values():
        h['db'].collection('registrations').document(t['id']).update({'attendance': 'Present'})
    return eid, teams, judge


def test_a_judge_sees_only_the_finalists_with_their_submissions_and_no_ai_score(p2):
    h = p2
    eid, teams, judge = _finale(h)
    listing = _page(judge, f'/judge/event/{eid}')
    for name in ('Bravo', 'Charlie', 'Echo'):
        assert f'<div class="team-name">{name}</div>' in listing
        assert f"/hackathon/{eid}/review/{teams[name]['id']}" in listing
    for name in ('Alpha', 'Delta'):
        assert f'<div class="team-name">{name}</div>' not in listing
        assert judge.get(f"/hackathon/{eid}/review/{teams[name]['id']}").status_code == 403
    view = _page(judge, f"/hackathon/{eid}/review/{teams['Bravo']['id']}")
    assert 'Bravo approach notes' in view and 'Solid work.' not in view and 'AI evaluation' not in view
    fid = h['field_ids'](eid)['Presentation']
    pdf = judge.get(f"/hackathon/{eid}/file/{teams['Bravo']['id']}/{fid}")
    assert pdf.status_code == 200 and pdf.data.startswith(b'%PDF-')
    assert judge.get(f"/hackathon/{eid}/file/{teams['Alpha']['id']}/{fid}").status_code == 403


@pytest.mark.parametrize('path', ['spoc', 'coordinator'])
def test_publishing_emails_each_lead_once_and_every_team_sees_the_results(p2, path):
    h = p2
    eid, teams, judge = _finale(h)
    for name, value in (('Bravo', 7), ('Charlie', 9), ('Echo', 5)):
        assert judge.post(f"/judge/submit_score/{teams[name]['id']}", json={'scores': {'Innovation': value}}).status_code < 400
    h['sent'].clear()
    h['clock']['now'] += datetime.timedelta(hours=1)
    if path == 'spoc':
        publisher = h['owner']
        url = f'/spoc/publish_results/{eid}'
    else:
        admin = f"{_unique('hkadmin')}@test.edu"
        _user(h['db'], admin, 'SuperAdmin')
        publisher = h['app'].test_client()
        assert publisher.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                              'secret_key': h['app'].config.get('MASTER_SECRET_KEY', '')}
                              ).headers['Location'] != '/login'
        url = f'/coordinator/publish_results/{eid}'
    resp = publisher.post(url, follow_redirects=True)
    assert 'Result emails: 5 sent to team leads.' in resp.get_data(as_text=True)

    results = [m for m in h['sent'] if 'Results' in m['subject']]
    assert sorted(m['to'] for m in results) == sorted(t['lead'] for t in teams.values())
    assert len(h['sent']) == 5, [m['subject'] for m in h['sent']]
    members = {h['reg'](t)['members'][0]['email'] for t in teams.values()}
    assert not members & {m['to'] for m in h['sent']}
    outcome = {}
    for m in results:
        found = re.search(r'font-weight:800;color:#1a2557;margin:0;">([^<]+)<', m['html'])
        assert found, m['subject']
        outcome[m['to']] = found.group(1)
    assert outcome == {teams['Charlie']['lead']: 'Winner', teams['Bravo']['lead']: 'Runner-up',
                       teams['Echo']['lead']: 'Second runner-up', teams['Alpha']['lead']: 'Participant',
                       teams['Delta']['lead']: 'Participant'}
    assert f'/hackathon/{eid}' in results[0]['html']

    # Publishing again sends nothing more
    publisher.post(url)
    assert len(h['sent']) == 5

    for name, label in (('Charlie', 'Winner'), ('Bravo', 'Runner-up'), ('Alpha', 'Participant')):
        page = _page(teams[name]['client'], f'/hackathon/{eid}')
        assert f'data-outcome="{label}"' in page and 'Winner</strong>: Charlie' in page
    assert hk.updates(h['ev'](eid))[0]['title'] == 'Results are out'
    assert any(n['title'].startswith('Results are out') for n in h['notices'](h['reg'](teams['Delta'])['members'][0]['email']))


def test_result_emails_held_back_by_the_daily_limit_are_sent_later_once(p2, monkeypatch):
    import utils_email
    h = p2
    eid, teams, judge = _finale(h, names=('Alpha', 'Bravo'), top=1, values={'Alpha': 9, 'Bravo': 2})
    judge.post(f"/judge/submit_score/{teams['Alpha']['id']}", json={'scores': {'Innovation': 8}})
    limited = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: limited.append(to) and False)
    resp = h['owner'].post(f'/spoc/publish_results/{eid}', follow_redirects=True)
    assert '2 not sent' in resp.get_data(as_text=True)
    assert '2 team lead(s) haven' in _page(h['owner'], f'/spoc/hackathon/{eid}')
    sent = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: sent.append(to) or True)
    h['owner'].post(f'/spoc/hackathon/{eid}/results/resend')
    h['owner'].post(f'/spoc/hackathon/{eid}/results/resend')
    assert sorted(sent) == sorted(t['lead'] for t in teams.values())
    assert 'Send the remaining result emails' not in _page(h['owner'], f'/spoc/hackathon/{eid}')


def test_certificates_show_on_the_team_page_and_are_not_emailed_in_portal_mode(p2, monkeypatch):
    import services_certificates as certs
    import services_signatories
    from tests.test_certificate_types import _signature
    h = p2
    eid, teams, judge = _finale(h, names=('Alpha', 'Bravo'), top=1, values={'Alpha': 9, 'Bravo': 2})
    judge.post(f"/judge/submit_score/{teams['Alpha']['id']}", json={'scores': {'Innovation': 8}})
    h['owner'].post(f'/spoc/publish_results/{eid}')
    monkeypatch.setattr(certs, '_ist_today', lambda: datetime.date(2026, 12, 1))
    services_signatories.add(h['db'], eid, name='Dr. A. Kumar', title='Principal', image=_signature(), actor=h['spoc'])
    h['sent'].clear()
    certs.issue_event(h['db'], eid, h['spoc'], only=['participation'])
    mine = ev.certificates_for(eid, h['reg'](teams['Alpha']))
    assert {c['email'] for c in mine} >= {teams['Alpha']['lead']}
    page = _page(teams['Alpha']['client'], f'/hackathon/{eid}')
    assert f"/certificates/c/{mine[0]['number']}/pdf" in page and 'id="certificates"' in page
    assert h['sent'] == [], 'certificates stay in the portal'
