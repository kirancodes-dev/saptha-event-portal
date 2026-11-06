"""
tests/test_hackathon_rehearsal.py — UPG-198: the whole hackathon once, end to
end, on the real database layer, as the owner will run it (2026-11-05):

ten teams register through the public form, two problem statements (one now,
one at a set time), the form opens, teams submit and edit, the deadline is
extended for a late team, the form closes, AI scores every submission (Gemini
replaced), the SPOC shortlists four, a judge scores the finalists, the SPOC
publishes. Each lead gets exactly two emails (registration, result); members
get none; everything else reaches them on the team page.
"""
import json

from werkzeug.security import generate_password_hash

import routes_forms
import services_hackathon as hk
import services_hackathon_eval as ev
import utils_email
from tests.test_hackathon_phase2 import _judge, _shortlist, make_pdf, reply
from tests.test_hackathon_portal import _ist, _page, hack  # noqa: F401  (the Phase 1 fixture)
from tests.test_integration_flow import PASSWORD, _login, _unique

TEAMS = ('Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel', 'India', 'Juliet')
# AI score per criterion (×10 = the total); Juliet is the late team
AI = {'Alpha': 5, 'Bravo': 9, 'Charlie': 7, 'Delta': 3, 'Echo': 6,
      'Foxtrot': 8, 'Golf': 4, 'Hotel': 2, 'India': 1, 'Juliet': 6.5}


def test_ten_teams_run_the_whole_hackathon_with_two_emails_each(hack, monkeypatch):  # noqa: F811
    h = hack
    db, owner, clock, sent = h['db'], h['owner'], h['clock'], h['sent']
    monkeypatch.setattr(routes_forms, 'send_registration_confirmed_email',
                        utils_email.send_registration_confirmed_email)
    monkeypatch.setitem(h['app'].config, 'GEMINI_API_KEY', 'test-key')
    calls = []

    def fake_model(system, data):
        calls.append(data)
        return reply(AI[json.loads(data)['project_title'].split()[0]])
    monkeypatch.setattr(ev, '_call_model', fake_model)

    eid = h['event']()
    assert hk.email_mode(h['ev'](eid)) == 'portal'

    # ── Ten teams register through the public form ───────────────────────────
    teams = {}
    for i, name in enumerate(TEAMS):
        lead, mate = f"{_unique(name.lower())}@test.edu", f"{_unique(name.lower() + 'mate')}@test.edu"
        resp = h['app'].test_client().post(f'/forms/submit/{eid}', data={
            'privacy_consent': 'yes', 'full_name': f'{name} Lead', 'email': lead,
            'phone': f'98765432{i:02d}', 'usn': f'1SN22CS4{i:02d}', 'team_name': name,
            'member_1_name': f'{name} Mate', 'member_1_email': mate, 'member_1_usn': f'1SN22CS5{i:02d}'})
        assert resp.status_code == 302, (name, resp.data[:300])
        # The lead sets a password from the email; here it is set directly
        db.collection('users').document(lead).update({'password': generate_password_hash(PASSWORD)})
        reg_id = hk.team_for(db, eid, lead)[0]
        assert reg_id, name
        teams[name] = {'lead': lead, 'mate': mate, 'id': reg_id, 'reg_id': reg_id, 'client': _login(h['app'], lead, 'Student')}
    registration = list(sent)
    assert sorted(m['to'] for m in registration) == sorted(t['lead'] for t in teams.values())
    for m in registration:
        assert 'https://chat.whatsapp.com/HackGroup123' in m['html'] and f'/hackathon/{eid}' in m['html']

    # ── Problem statements: one now, one at 12:00 IST ────────────────────────
    assert h['problem'](eid, 'Clean water').status_code == 302
    assert h['problem'](eid, 'Smart farms', release='later', at='2026-11-20T12:00').status_code == 302
    alpha = teams['Alpha']['client']
    page = _page(alpha, f'/hackathon/{eid}')
    assert 'Clean water' in page and 'Smart farms' not in page
    clock['now'] = _ist('2026-11-20', '12:01')
    assert 'Smart farms' in _page(alpha, f'/hackathon/{eid}')
    pids = {p['title']: p['id'] for p in hk.problems(h['ev'](eid))}

    # ── The form: open 09:00 on the 20th to 18:00 on the 22nd (IST) ─────────
    assert h['form'](eid).status_code == 302
    for name in TEAMS[:-1]:
        t = teams[name]
        resp = h['submit'](t, eid, Project_title=f'{name} Project',
                           Problem_statement=pids['Smart farms' if name in ('Bravo', 'Golf') else 'Clean water'],
                           GitHub_repository=f'https://github.com/x/{name}',
                           Presentation=make_pdf(f'{name} deck'), Approach=f'{name} approach')
        assert resp.status_code == 302 and h['sub'](t)['project_title'] == f'{name} Project', name
    # Bravo edits before the deadline
    clock['now'] = _ist('2026-11-22', '17:00')
    h['submit'](teams['Bravo'], eid, Project_title='Bravo Project v2', Problem_statement=pids['Smart farms'],
                GitHub_repository='https://github.com/x/Bravo', Approach='Bravo approach, revised')
    edited = h['sub'](teams['Bravo'])
    assert edited['project_title'] == 'Bravo Project v2' and edited['versions'] == 2

    # ── Juliet is late; the SPOC extends by an hour ──────────────────────────
    clock['now'] = _ist('2026-11-22', '18:20')
    late = dict(Project_title='Juliet Project', Problem_statement=pids['Clean water'],
                GitHub_repository='https://github.com/x/Juliet', Presentation=make_pdf('Juliet deck'))
    h['submit'](teams['Juliet'], eid, **late)
    assert h['sub'](teams['Juliet']) == {}
    owner.post(f'/spoc/hackathon/{eid}/extend', data={'minutes': '60', 'reason': 'Power cut'})
    assert hk.form(h['ev'](eid))['closes_at'] == _ist('2026-11-22', '19:00').isoformat()
    assert 'Power cut' in _page(teams['Juliet']['client'], f'/hackathon/{eid}')
    h['submit'](teams['Juliet'], eid, **late)
    assert h['sub'](teams['Juliet'])['project_title'] == 'Juliet Project'

    # ── Closed: no more edits ────────────────────────────────────────────────
    clock['now'] = _ist('2026-11-22', '19:05')
    h['submit'](teams['Alpha'], eid, Project_title='Too late')
    assert h['sub'](teams['Alpha'])['project_title'] == 'Alpha Project'

    # ── AI scores all ten, batch by batch as the page drives it ──────────────
    owner.post(f'/spoc/hackathon/{eid}/ai/start')
    for _ in range(20):
        progress = owner.post(f'/spoc/hackathon/{eid}/ai/next', json={},
                              headers={'Accept': 'application/json'}).get_json()
        if progress['finished']:
            break
    assert progress['scored'] == 10 and progress['not_scored'] == 0 and len(calls) == 10
    assert 'Bravo Project v2' in ''.join(calls), "the edited submission is the one scored"

    # ── Shortlist the top four: Bravo 90, Foxtrot 80, Charlie 70, Juliet 65 ──
    _html, go, expected = _shortlist(h, eid, 4)
    finalists = {n for n, t in teams.items() if t['id'] in go}
    assert finalists == {'Bravo', 'Foxtrot', 'Charlie', 'Juliet'}
    owner.post(f'/spoc/hackathon/{eid}/shortlist/confirm', data={'go': go, 'expected_round': expected})
    out_page = _page(teams['Alpha']['client'], f'/hackathon/{eid}').replace('&#39;', "'")
    assert "Your team wasn't shortlisted" in out_page
    assert "wasn't shortlisted" not in _page(teams['Bravo']['client'], f'/hackathon/{eid}').replace('&#39;', "'")

    # ── The judge sees and scores the four finalists ─────────────────────────
    judge = _judge(h, eid)
    for t in teams.values():
        db.collection('registrations').document(t['id']).update({'attendance': 'Present'})
    listing = _page(judge, f'/judge/event/{eid}')
    for name in TEAMS:
        assert (f'<div class="team-name">{name}</div>' in listing) == (name in finalists), name
    for name, value in (('Bravo', 7), ('Foxtrot', 9), ('Charlie', 8), ('Juliet', 6)):
        assert judge.post(f"/judge/submit_score/{teams[name]['id']}",
                          json={'scores': {'Innovation': value}}).status_code < 400

    # ── Publish: one result email per lead ───────────────────────────────────
    clock['now'] = _ist('2026-11-28', '17:00')
    resp = owner.post(f'/spoc/publish_results/{eid}', follow_redirects=True)
    assert 'Result emails: 10 sent to team leads.' in resp.get_data(as_text=True)
    results = sent[len(registration):]
    assert sorted(m['to'] for m in results) == sorted(t['lead'] for t in teams.values())
    assert all(m['subject'].startswith('Results') for m in results)

    # The whole run: 20 emails, two per lead, none to a member
    assert len(sent) == 20, [(m['to'], m['subject']) for m in sent]
    for t in teams.values():
        assert sum(m['to'] == t['lead'] for m in sent) == 2
    assert not {t['mate'] for t in teams.values()} & {m['to'] for m in sent}

    # Every team sees its outcome on its page
    expected_outcomes = {'Foxtrot': 'Winner', 'Charlie': 'Runner-up', 'Bravo': 'Second runner-up',
                         'Juliet': 'Finalist', 'Alpha': 'Participant', 'India': 'Participant'}
    for name, label in expected_outcomes.items():
        page = _page(teams[name]['client'], f'/hackathon/{eid}')
        assert f'data-outcome="{label}"' in page and 'Winner</strong>: Foxtrot' in page, name

    # Publishing again sends nothing more
    owner.post(f'/spoc/publish_results/{eid}')
    assert len(sent) == 20
