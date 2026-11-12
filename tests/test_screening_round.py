"""
tests/test_screening_round.py — UPG-238 on the real database layer.

When more people wait than there are seats, the hosting SPOC writes a
screening round on the registrations page: multiple-choice questions with the
right answer and points, when it opens and closes, an optional time limit.
Opening it tells each lead waiting (a portal notice and one email with the
link). Each lead answers once, between the times; the answers are scored on
submit, the right answers never reach the page. The waitlist shows each score
and sorts by it; "Accept the top N" accepts exactly the N best (a tie goes to
whoever joined earlier), each registered and emailed; the others stay waiting
and aren't told (D-13, as proposed, approved by the owner on 2026-11-12).
"""
import datetime
from zoneinfo import ZoneInfo

from tests import test_spoc_waitlist as _wl
from tests.test_integration_flow import _login, _unique, _user
from tests.test_spoc_waitlist import _entry, _full_event, _join, _page, _regs_of

host = _wl.host   # UPG-211's fixture, through UPG-230's tests

IST = ZoneInfo('Asia/Kolkata')


def _local(hours):
    return (datetime.datetime.now(IST) + datetime.timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M')


def _post(client, event_id, action, **data):
    return client.post(f'/coordinator/registrations/{event_id}/screening/{action}', data=data)


def _flashes(client):
    with client.session_transaction() as s:
        out = [m for _, m in s.get('_flashes', [])]
        s.pop('_flashes', None)
    return ' '.join(out)


def _round(h, event_id, minutes=''):
    """Two questions (2 points and 1 point), open from an hour ago for two hours."""
    owner = h['owner']
    _post(owner, event_id, 'question', text='2 + 2 = ?', option_1='3', option_2='4', option_3='5',
          answer='2', points='2')
    _post(owner, event_id, 'question', text='HTML stands for?', option_1='HyperText Markup Language',
          option_2='High Tech Modern Language', answer='1', points='1')
    _post(owner, event_id, 'times', opens_at=_local(-1), closes_at=_local(1), minutes=minutes)
    return h['db'].collection('events').document(event_id).get().to_dict()['screening']


def _lead_client(h, email):
    _user(h['db'], email, 'Student', name='Wanda Wait')
    return _login(h['app'], email, 'Student')


def _answer(client, event_id, s, right=(True, True)):
    """Answer the round: each question right or wrong as asked."""
    data = {}
    for q, ok in zip(s['questions'], right):
        data[f"q_{q['id']}"] = str(q['answer'] if ok else (q['answer'] + 1) % len(q['options']))
    return client.post(f'/participant/screening/{event_id}', data=data)


def _sheet(h, event_id, wl_id):
    doc = h['db'].collection('screening_answers').document(f"{event_id}__{wl_id}").get()
    return doc.to_dict() if doc.exists else None


# ── Criterion 1: the SPOC writes and opens a round; only people waiting, once, between its times

def test_the_spoc_writes_and_opens_a_round_and_each_lead_waiting_is_told(host):
    h = host
    event_id = _full_event(h)
    _, lead, mate = _join(h, event_id, 'Quiz Team')
    s = _round(h, event_id)
    assert [q['points'] for q in s['questions']] == [2, 1] and s['questions'][0]['answer'] == 1
    assert not s.get('published')
    page = _page(h['owner'], event_id)
    assert 'data-screening-question-form' in page and '2 + 2 = ?' in page and 'Not open to people yet' in page

    # Not open yet: the student page doesn't exist for people
    assert _lead_client(h, lead).get(f'/participant/screening/{event_id}').status_code == 404

    h['emails'].clear()
    resp = _post(h['owner'], event_id, 'open')
    assert resp.status_code == 302 and 'open to the 1 lead waiting' in _flashes(h['owner'])
    [mail] = [m for m in h['emails'] if m['to'] == lead]
    assert 'Screening round' in mail['subject'] and f'/participant/screening/{event_id}' in mail['message']
    assert [m for m in h['emails'] if m['to'] == mate] == []          # the lead answers for the team
    notes = [n.to_dict() for n in h['db'].collection('notifications_v2').stream()
             if n.to_dict().get('user_email') == lead and n.to_dict().get('type') == 'screening_round']
    assert len(notes) == 1

    # Fixed once open: the questions can't change
    _post(h['owner'], event_id, 'question', text='Late question?', option_1='a', option_2='b', answer='1', points='1')
    assert "can't change" in _flashes(h['owner'])
    assert len(h['db'].collection('events').document(event_id).get().to_dict()['screening']['questions']) == 2


def test_only_a_waiting_lead_answers_once_between_the_times(host):
    h = host
    event_id = _full_event(h)
    wl_id, lead, mate = _join(h, event_id, 'Once Only')
    s = _round(h, event_id)
    _post(h['owner'], event_id, 'open')

    client = _lead_client(h, lead)
    page = client.get(f'/participant/screening/{event_id}').get_data(as_text=True)
    assert 'data-screening-form' in page and '2 + 2 = ?' in page
    assert 'Right answer' not in page and '"answer"' not in page        # the right answers stay on the server
    # The dashboard's waitlist card links to it
    dash = client.get('/participant/dashboard').get_data(as_text=True)
    assert 'data-take-screening' in dash and f'/participant/screening/{event_id}' in dash

    assert _answer(client, event_id, s).status_code == 302
    sheet = _sheet(h, event_id, wl_id)
    assert sheet['score'] == 3 and sheet['max_score'] == 3 and sheet['submitted_at']
    _answer(client, event_id, s, right=(False, False))                # a second try is refused
    assert 'already received' in _flashes(client) and _sheet(h, event_id, wl_id)['score'] == 3
    assert 'data-screening-received' in client.get(f'/participant/screening/{event_id}').get_data(as_text=True)
    assert 'data-take-screening' not in client.get('/participant/dashboard').get_data(as_text=True)

    # A team member is told the lead answers; a stranger has nothing to answer
    member = _lead_client(h, mate)
    assert 'data-screening-member' in member.get(f'/participant/screening/{event_id}').get_data(as_text=True)
    stranger = _lead_client(h, f"{_unique('stranger')}@test.edu")
    assert 'data-screening-not-waiting' in stranger.get(f'/participant/screening/{event_id}').get_data(as_text=True)
    stranger.post(f'/participant/screening/{event_id}', data={})
    assert len([d for d in h['db'].collection('screening_answers').where('event_id', '==', event_id).stream()]) == 1


def test_before_it_opens_and_after_it_closes_nothing_is_answered(host):
    h = host
    db = h['db']
    event_id = _full_event(h)
    wl_id, lead, _ = _join(h, event_id, 'Early Bird')
    s = _round(h, event_id)
    _post(h['owner'], event_id, 'open')
    client = _lead_client(h, lead)
    later = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).isoformat()
    db.collection('events').document(event_id).update({'screening': dict(s, published=True, opens_at=later,
                                                                         closes_at=later)})
    page = client.get(f'/participant/screening/{event_id}').get_data(as_text=True)
    assert 'data-screening-upcoming' in page and 'data-screening-form' not in page
    _answer(client, event_id, s)
    assert "isn't open" in _flashes(client) and _sheet(h, event_id, wl_id) is None

    past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)).isoformat()
    db.collection('events').document(event_id).update({'screening': dict(s, published=True, opens_at=past,
                                                                         closes_at=past)})
    assert 'data-screening-closed' in client.get(f'/participant/screening/{event_id}').get_data(as_text=True)
    _answer(client, event_id, s)
    assert 'has closed' in _flashes(client) and _sheet(h, event_id, wl_id) is None


def test_answers_after_the_time_limit_do_not_count(host):
    h = host
    db = h['db']
    event_id = _full_event(h)
    wl_id, lead, _ = _join(h, event_id, 'Slow Coach')
    s = _round(h, event_id, minutes='10')
    _post(h['owner'], event_id, 'open')
    client = _lead_client(h, lead)
    assert 'data-screening-ends' in client.get(f'/participant/screening/{event_id}').get_data(as_text=True)
    started = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=20)).isoformat()
    db.collection('screening_answers').document(f"{event_id}__{wl_id}").update({'started_at': started})
    _answer(client, event_id, s)
    sheet = _sheet(h, event_id, wl_id)
    assert sheet['late'] is True and sheet['score'] == 0 and sheet['submitted_at']


# ── Criterion 2: scored by the right answers; the waitlist shows and sorts by score

def test_the_waitlist_shows_each_score_and_sorts_by_it(host):
    h = host
    event_id = _full_event(h)
    low, low_lead, _ = _join(h, event_id, 'Low Score')
    high, high_lead, _ = _join(h, event_id, 'High Score')
    none, _, _ = _join(h, event_id, 'No Answer')
    s = _round(h, event_id)
    _post(h['owner'], event_id, 'open')
    _answer(_lead_client(h, low_lead), event_id, s, right=(False, True))     # 1 of 3
    _answer(_lead_client(h, high_lead), event_id, s)                         # 3 of 3

    page = _page(h['owner'], event_id)
    assert '2 of 3 answered' in page
    row = page[page.index(f'data-waitlist-entry="{high}"'):]
    assert '<strong>3</strong>/3' in row[:row.index('</tr>')] and 'Rank 1' in row[:row.index('</tr>')]
    row = page[page.index(f'data-waitlist-entry="{none}"'):]
    assert 'Not answered' in row[:row.index('</tr>')]
    # In line by default; by score on request, unanswered last
    assert page.index(f'data-waitlist-entry="{low}"') < page.index(f'data-waitlist-entry="{high}"')
    by_score = h['owner'].get(f'/coordinator/registrations/{event_id}?wl=score').get_data(as_text=True)
    order = [by_score.index(f'data-waitlist-entry="{x}"') for x in (high, low, none)]
    assert order == sorted(order)


# ── Criterion 3: "Accept the top N" accepts exactly the N best; ties go to the earlier joiner

def test_accept_the_top_two_accepts_exactly_the_best_two_and_the_rest_stay_waiting(host):
    h = host
    event_id = _full_event(h)
    teams = {}
    for name in ('Tie Early', 'Tie Late', 'Best', 'Worst'):
        teams[name] = _join(h, event_id, name)
    s = _round(h, event_id)
    _post(h['owner'], event_id, 'open')
    scores = {'Tie Early': (True, False), 'Tie Late': (True, False), 'Best': (True, True), 'Worst': (False, False)}
    for name, right in scores.items():
        _answer(_lead_client(h, teams[name][1]), event_id, s, right=right)
    h['emails'].clear()

    resp = h['owner'].post(f'/coordinator/registrations/{event_id}/accept_top', data={'n': '2'})
    assert resp.status_code == 302
    flashes = _flashes(h['owner'])
    assert 'Accepted the top 2 by score: Best (3/3), Tie Early (2/3).' in flashes and 'Each was emailed.' in flashes
    for name in ('Best', 'Tie Early'):
        wl_id, lead, _ = teams[name]
        assert _entry(h, wl_id)['status'] == 'promoted'
        [reg] = _regs_of(h, event_id, lead)
        assert reg['status'] == 'Confirmed'
        assert len([m for m in h['emails'] if m['to'] == lead]) == 1
    for name in ('Tie Late', 'Worst'):                                     # stay waiting, not told
        wl_id, lead, _ = teams[name]
        assert _entry(h, wl_id)['status'] == 'waiting' and _regs_of(h, event_id, lead) == []
        assert [m for m in h['emails'] if m['to'] == lead] == []
    assert h['count'](event_id) == 3                                       # 1 seat + 2 accepted
    assert any(a.to_dict().get('action') == 'WAITLIST_ACCEPTED' and 'top 2 of the screening round'
               in a.to_dict().get('details', '') for a in h['db'].collection('audit_log').stream())


# ── Only the hosting SPOC writes, opens and accepts ─────────────────────────

def test_another_spoc_and_a_coordinator_can_not_run_the_round(host):
    h = host
    event_id = _full_event(h)
    other = f"{_unique('otherspoc')}@test.edu"
    _user(h['db'], other, 'ClubSPOC')
    other_client = _login(h['app'], other, 'ClubSPOC')
    coord = f"{_unique('coord')}@test.edu"
    _user(h['db'], coord, 'EventCoordinator')
    coord_client = _login(h['app'], coord, 'EventCoordinator')
    for client in (other_client, coord_client):
        assert _post(client, event_id, 'question', text='x?', option_1='a', option_2='b', answer='1',
                     points='1').status_code == 403
        assert _post(client, event_id, 'open').status_code == 403
        assert client.post(f'/coordinator/registrations/{event_id}/accept_top', data={'n': '1'}).status_code == 403
    assert not h['db'].collection('events').document(event_id).get().to_dict().get('screening')
