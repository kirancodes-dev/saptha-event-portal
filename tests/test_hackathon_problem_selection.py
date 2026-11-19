"""
tests/test_hackathon_problem_selection.py — UPG-321 (owner's request, 2026-11-19).

The SPOC sets a time when teams choose a problem statement, can lock it,
reopen it and extend it. In that time each team's lead chooses one released
problem statement on the team's hackathon page (and may change it until it
closes); then it is locked, and the submission and everything after it use
that one. Optionally a cap of teams per problem statement, first come, first
served. The SPOC assigns one to a team that didn't choose. A hackathon with
no selection time works as before.
"""
import datetime
import threading

import services_hackathon as hk
from tests.test_hackathon_portal import PDF, _ist, _page, hack  # noqa: F401  (fixture)
from tests.test_integration_flow import _login


def _setup(h, cap=0, opens='2026-11-20T11:00', closes='2026-11-20T17:00', titles=('Clean water', 'Smart farm')):
    """A hackathon with released problem statements, a submission form open
    20–22 Nov and a selection time; the clock at 10:00 IST on 20 Nov."""
    eid = h['event']()
    for t in titles:
        assert h['problem'](eid, t).status_code == 302
    assert h['form'](eid).status_code == 302
    resp = h['owner'].post(f'/spoc/hackathon/{eid}/selection',
                           data={'sel_opens_at': opens, 'sel_closes_at': closes, 'cap': str(cap)})
    assert resp.status_code == 302
    pids = {p['title']: p['id'] for p in hk.problems(h['ev'](eid))}
    return eid, pids


def _at(h, day, clock):
    h['clock']['now'] = _ist(day, clock)


def _choose(t, eid, pid):
    return t['client'].post(f'/hackathon/{eid}/choose', data={'pid': pid})


def _reg(h, t):
    return h['db'].collection('registrations').document(t['reg_id']).get().to_dict()


def _audit(h, action):
    return [d.to_dict() for d in h['db'].collection('audit_log').where('action', '==', action).stream()]


def _flash(client):
    with client.session_transaction() as s:
        return ' '.join(m for _c, m in s.get('_flashes', []))


# ── Criterion 1: the SPOC sets the time (and a cap); teams are told ─────────

def test_the_spoc_sets_when_teams_choose_and_every_team_sees_it(hack):
    h = hack
    eid, _pids = _setup(h, cap=3)
    s = hk.selection(h['ev'](eid))
    assert s['opens_at'] == _ist('2026-11-20', '11:00').isoformat()
    assert s['closes_at'] == _ist('2026-11-20', '17:00').isoformat()
    assert s['cap'] == 3 and s['locked'] is False
    assert any(u['title'] == 'Choose your problem statement' for u in hk.updates(h['ev'](eid)))
    assert _audit(h, 'HACKATHON_SELECTION_SAVED')

    page = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert 'id="selection"' in page and 'data-sel-window="not_open"' in page and 'at most 3 teams' in page

    t = h['team'](eid)
    page = _page(t['client'], f'/hackathon/{eid}')
    assert 'data-selection="not_open"' in page and 'Team leads choose one problem statement from' in page
    assert 'data-stage="selection"' in page

    # Bad input is refused and changes nothing
    for bad in ({'sel_opens_at': '', 'sel_closes_at': '2026-11-20T17:00'},
                {'sel_opens_at': '2026-11-20T17:00', 'sel_closes_at': '2026-11-20T11:00'},
                {'sel_opens_at': '2026-11-20T11:00', 'sel_closes_at': '2026-11-20T17:00', 'cap': '-1'},
                {'sel_opens_at': '2026-11-20T11:00', 'sel_closes_at': '2026-11-20T17:00', 'cap': 'many'}):
        h['owner'].post(f'/spoc/hackathon/{eid}/selection', data=bad)
        assert hk.selection(h['ev'](eid))['cap'] == 3

    # Another SPOC can't touch it
    for path in ('selection', 'selection/lock', 'selection/reopen', 'selection/extend', 'selection/assign'):
        assert h['stranger'].post(f'/spoc/hackathon/{eid}/{path}', data={'minutes': '60'}).status_code == 403


# ── Criterion 2: the lead chooses only while it is open, by the server's clock ─

def test_the_lead_chooses_and_changes_only_while_choosing_is_open(hack):
    h = hack
    eid, pids = _setup(h)
    t = h['team'](eid)

    _choose(t, eid, pids['Clean water'])                          # 10:00, opens at 11:00
    assert 'problem_choice' not in _reg(h, t)
    assert 'Choosing opens on' in _flash(t['client'])

    _at(h, '2026-11-20', '12:00')
    _choose(t, eid, pids['Clean water'])
    assert _reg(h, t)['problem_choice']['pid'] == pids['Clean water']
    page = _page(t['client'], f'/hackathon/{eid}')
    assert f'data-chosen="{pids["Clean water"]}"' in page and 'Change to this one' in page
    assert hk.taken(eid, h['ev'](eid)) == {pids['Clean water']: 1, pids['Smart farm']: 0}

    _choose(t, eid, pids['Smart farm'])                           # changed while open
    choice = _reg(h, t)['problem_choice']
    assert choice['pid'] == pids['Smart farm'] and choice['title'] == 'Smart farm' and choice['set_by_spoc'] is False
    assert hk.taken(eid, h['ev'](eid)) == {pids['Clean water']: 0, pids['Smart farm']: 1}

    _at(h, '2026-11-20', '17:00')                                  # closed: locked
    _choose(t, eid, pids['Clean water'])
    assert _reg(h, t)['problem_choice']['pid'] == pids['Smart farm']
    assert 'locked' in _flash(t['client'])
    page = _page(t['client'], f'/hackathon/{eid}')
    assert 'data-selection="closed"' in page and 'data-choose=' not in page and 'Locked.' in page


def test_only_the_lead_and_only_a_released_problem_statement(hack):
    h = hack
    eid, pids = _setup(h)
    h['owner'].post(f'/spoc/hackathon/{eid}/problems', data={
        'title': 'Later one', 'description': 'Later.', 'release': 'later', 'release_at': '2026-11-21T09:00'})
    later = next(p['id'] for p in hk.problems(h['ev'](eid)) if p['title'] == 'Later one')
    mate = f"mate-{eid[:6]}@test.edu"
    t = h['team'](eid, members=(mate,))
    _at(h, '2026-11-20', '12:00')

    _choose(t, eid, later)                                        # not released yet
    assert 'problem_choice' not in _reg(h, t)
    _choose(t, eid, 'nope')
    assert 'problem_choice' not in _reg(h, t)

    from tests.test_integration_flow import _user
    _user(h['db'], mate, 'Student')
    member = _login(h['app'], mate, 'Student')
    assert member.post(f'/hackathon/{eid}/choose', data={'pid': pids['Clean water']}).status_code == 403
    ok, message = hk.choose(h['db'], eid, h['ev'](eid), t['reg_id'], _reg(h, t), pids['Clean water'], mate)
    assert not ok and 'Only the team lead' in message
    assert 'problem_choice' not in _reg(h, t)


# ── Criterion 3: a cap per problem statement, first come, first served ──────

def test_a_full_problem_statement_cant_be_chosen(hack):
    h = hack
    eid, pids = _setup(h, cap=1)
    a, b = h['team'](eid, 'Alpha'), h['team'](eid, 'Beta')
    _at(h, '2026-11-20', '12:00')

    _choose(a, eid, pids['Clean water'])
    assert _reg(h, a)['problem_choice']['pid'] == pids['Clean water']
    page = _page(b['client'], f'/hackathon/{eid}')
    assert f'data-full="{pids["Clean water"]}"' in page and f'data-choose="{pids["Smart farm"]}"' in page

    _choose(b, eid, pids['Clean water'])
    assert 'problem_choice' not in _reg(h, b)
    assert 'is full' in _flash(b['client'])
    _choose(b, eid, pids['Smart farm'])
    assert _reg(h, b)['problem_choice']['pid'] == pids['Smart farm']

    # Alpha moves away: its place is free again
    _choose(a, eid, pids['Smart farm'])
    assert 'problem_choice' in _reg(h, a) and _reg(h, a)['problem_choice']['pid'] == pids['Clean water']   # Smart farm is full
    c = h['team'](eid, 'Gamma')
    _choose(c, eid, pids['Clean water'])
    assert 'problem_choice' not in _reg(h, c)

    # A cancelled team's place is given back when the problem statement looks full
    h['db'].collection('registrations').document(a['reg_id']).update({'status': 'Cancelled'})
    _choose(c, eid, pids['Clean water'])
    assert _reg(h, c)['problem_choice']['pid'] == pids['Clean water']


def test_teams_choosing_at_the_same_moment_never_pass_the_cap(hack):
    h = hack
    eid, pids = _setup(h, cap=2)
    teams = [h['team'](eid, f'T{i}') for i in range(6)]
    _at(h, '2026-11-20', '12:00')
    event = h['ev'](eid)
    results = []

    def go(t):
        with h['app'].app_context():
            results.append(hk.choose(h['db'], eid, dict(event), t['reg_id'], _reg(h, t), pids['Clean water'],
                                     t['lead'])[0])

    threads = [threading.Thread(target=go, args=(t,)) for t in teams]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert results.count(True) == 2
    assert sum(1 for t in teams if (_reg(h, t).get('problem_choice') or {}).get('pid')) == 2
    assert hk.taken(eid, h['ev'](eid))[pids['Clean water']] == 2


# ── Criterion 4: lock, reopen, extend ───────────────────────────────────────

def test_the_spoc_locks_reopens_and_extends(hack):
    h = hack
    eid, pids = _setup(h)
    t = h['team'](eid)
    _at(h, '2026-11-20', '12:00')
    url = f'/spoc/hackathon/{eid}/selection'

    h['owner'].post(f'{url}/lock')
    assert hk.selection_window(h['ev'](eid)) == 'locked' and _audit(h, 'HACKATHON_SELECTION_LOCKED')
    assert any(u['title'] == 'Problem statements are locked' for u in hk.updates(h['ev'](eid)))
    _choose(t, eid, pids['Clean water'])
    assert 'problem_choice' not in _reg(h, t)
    assert 'data-selection="locked"' in _page(t['client'], f'/hackathon/{eid}')

    h['owner'].post(f'{url}/reopen')
    assert hk.selection_window(h['ev'](eid)) == 'open' and _audit(h, 'HACKATHON_SELECTION_REOPENED')
    _choose(t, eid, pids['Clean water'])
    assert _reg(h, t)['problem_choice']['pid'] == pids['Clean water']

    # After the close, reopening needs an extension; an extension still in the past is refused
    _at(h, '2026-11-20', '19:00')
    h['owner'].post(f'{url}/lock')
    h['owner'].post(f'{url}/reopen')
    assert hk.selection_window(h['ev'](eid)) == 'locked'
    h['owner'].post(f'{url}/extend', data={'minutes': '60'})            # 17:00 + 1 h is still past
    assert hk.selection(h['ev'](eid))['closes_at'] == _ist('2026-11-20', '17:00').isoformat()

    h['owner'].post(f'{url}/extend', data={'minutes': 'custom', 'custom_hours': '3', 'custom_minutes': '0',
                                            'reason': 'More time'})
    s = hk.selection(h['ev'](eid))
    assert s['closes_at'] == _ist('2026-11-20', '20:00').isoformat() and s['locked'] is False
    assert s['extensions'][-1]['minutes'] == 180 and s['extensions'][-1]['reason'] == 'More time'
    assert hk.selection_window(h['ev'](eid)) == 'open' and _audit(h, 'HACKATHON_SELECTION_EXTENDED')
    assert any('extended by 3 hours' in u['title'] for u in hk.updates(h['ev'](eid)))
    _choose(t, eid, pids['Smart farm'])
    assert _reg(h, t)['problem_choice']['pid'] == pids['Smart farm']
    assert 'More time' in _page(h['owner'], f'/spoc/hackathon/{eid}')


# ── Criterion 5: the submission is for the chosen problem statement ─────────

def test_the_submission_uses_the_locked_choice_and_waits_for_one(hack):
    h = hack
    eid, pids = _setup(h, opens='2026-11-20T09:00', closes='2026-11-20T11:00')
    t, u = h['team'](eid, 'Alpha'), h['team'](eid, 'Beta')
    _choose(t, eid, pids['Clean water'])                          # 10:00, open
    _at(h, '2026-11-20', '12:00')                                  # locked; submissions open

    page = _page(t['client'], f'/hackathon/{eid}')
    assert 'data-locked-problem' in page and 'Clean water' in page
    h['submit'](t, eid, Project_title='Water app', Problem_statement=pids['Smart farm'],
                GitHub_repository='https://github.com/a/b', Presentation=PDF)
    sub = h['sub'](t)
    assert sub['problem_id'] == pids['Clean water'] and sub['problem_title'] == 'Clean water'
    assert sub['answers'][h['field_ids'](eid)['Problem statement']] == pids['Clean water']

    # Beta didn't choose: it can't submit until the SPOC assigns one
    h['submit'](u, eid, Project_title='Farm app', Problem_statement=pids['Smart farm'],
                GitHub_repository='https://github.com/a/c', Presentation=PDF)
    assert not h['sub'](u)
    assert "hasn't chosen a problem statement" in _flash(u['client'])
    assert 'id="selNotChosen"' in _page(h['owner'], f'/spoc/hackathon/{eid}')


# ── Criterion 6: the SPOC assigns one (audited, the team told) ──────────────

def test_the_spoc_assigns_a_problem_statement_and_the_submission_follows(hack):
    h = hack
    eid, pids = _setup(h, cap=1, opens='2026-11-20T09:00', closes='2026-11-20T11:00')
    a, b = h['team'](eid, 'Alpha'), h['team'](eid, 'Beta')
    _choose(a, eid, pids['Clean water'])
    _at(h, '2026-11-20', '12:00')

    # Assigned past the cap: the SPOC decides
    h['owner'].post(f'/spoc/hackathon/{eid}/selection/assign', data={'reg_id': b['reg_id'], 'pid': pids['Clean water']})
    choice = _reg(h, b)['problem_choice']
    assert choice['pid'] == pids['Clean water'] and choice['set_by_spoc'] is True
    assert _audit(h, 'HACKATHON_PROBLEM_ASSIGNED')
    notes = [d.to_dict() for d in h['db'].collection('notifications_v2').where('user_email', '==', b['lead']).stream()]
    assert any('Clean water' in n.get('message', '') for n in notes)

    h['submit'](b, eid, Project_title='Water two', GitHub_repository='https://github.com/a/d', Presentation=PDF)
    assert h['sub'](b)['problem_id'] == pids['Clean water']

    # A change by the SPOC moves the team's submission with it
    h['owner'].post(f'/spoc/hackathon/{eid}/selection/assign', data={'reg_id': b['reg_id'], 'pid': pids['Smart farm']})
    sub = h['sub'](b)
    assert sub['problem_id'] == pids['Smart farm'] and sub['problem_title'] == 'Smart farm'
    assert sub['answers'][h['field_ids'](eid)['Problem statement']] == pids['Smart farm']
    assert hk.taken(eid, h['ev'](eid)) == {pids['Clean water']: 1, pids['Smart farm']: 1}

    # Only this event's active teams, and only released problem statements
    other = h['event']()
    stranger_team = h['team'](other, 'Elsewhere')
    h['owner'].post(f'/spoc/hackathon/{eid}/selection/assign', data={'reg_id': stranger_team['reg_id'],
                                                                     'pid': pids['Clean water']})
    assert 'problem_choice' not in _reg(h, stranger_team)


def test_a_change_while_open_moves_an_earlier_submission(hack):
    h = hack
    eid, pids = _setup(h, opens='2026-11-20T09:00', closes='2026-11-21T09:00')
    t = h['team'](eid)
    _at(h, '2026-11-20', '12:00')                                  # both open
    _choose(t, eid, pids['Clean water'])
    h['submit'](t, eid, Project_title='App', GitHub_repository='https://github.com/a/b', Presentation=PDF)
    assert h['sub'](t)['problem_id'] == pids['Clean water']
    before = hk.page_version(h['ev'](eid), _reg(h, t), h['sub'](t))
    _choose(t, eid, pids['Smart farm'])
    assert h['sub'](t)['problem_id'] == pids['Smart farm']
    assert hk.page_version(h['ev'](eid), _reg(h, t), h['sub'](t)) != before   # the open page reloads


# ── Criterion 7: a hackathon without a selection time works as before ───────

def test_without_a_selection_time_teams_pick_on_the_form_as_before(hack):
    h = hack
    eid = h['event']()
    h['problem'](eid, 'Clean water')
    h['problem'](eid, 'Smart farm')
    h['form'](eid)
    pids = {p['title']: p['id'] for p in hk.problems(h['ev'](eid))}
    t = h['team'](eid)
    _at(h, '2026-11-20', '12:00')
    assert hk.selection_window(h['ev'](eid)) == 'not_set'

    page = _page(t['client'], f'/hackathon/{eid}')
    assert 'data-selection=' not in page and 'data-locked-problem' not in page and 'Choose a problem statement…' in page
    assert 'data-stage="selection"' not in page
    assert t['client'].post(f'/hackathon/{eid}/choose', data={'pid': pids['Clean water']}).status_code == 302
    assert 'problem_choice' not in _reg(h, t)

    h['submit'](t, eid, Project_title='Farm', Problem_statement=pids['Smart farm'],
                GitHub_repository='https://github.com/a/b', Presentation=PDF)
    assert h['sub'](t)['problem_id'] == pids['Smart farm']
    page = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert 'id="selection"' in page and 'id="selBoard"' not in page
