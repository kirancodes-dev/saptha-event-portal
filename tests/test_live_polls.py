"""
tests/test_live_polls.py — UPG-160: live polls and Q&A. Only attendees checked
in to the event vote, once each; an upvote counts once per person; hidden and
pending questions stay off the projector; text shows as text; the event
report has the poll results.
"""
import io

import openpyxl

import services_interact as live
from tests.test_checkin_unified import _registration, _scan, gate  # noqa: F401  (fixture)
from tests.test_integration_flow import _login, _unique, _user


def _attendee(d, name):
    """A person registered for the event, logged in; checked in when asked."""
    email = f"{_unique(name)}@test.edu"
    _user(d['db'], email, 'Student')
    reg_id, token = _registration(d, lead_name=name.title(), lead_email=email)
    return _login(d['app'], email, 'Student'), token


def _open_poll(d, question='Best language?', options='Python\nRust\nGo', **extra):
    resp = d['staff'].post(f"/interact/{d['event_id']}/polls",
                           data=dict({'question': question, 'options': options}, **extra))
    assert resp.status_code == 302
    return live.polls_for(d['event_id'])[-1]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_only_checked_in_attendees_vote_once_each_and_counts_are_right(gate):  # noqa: F811
    d = gate
    poll = _open_poll(d)
    ana, ana_token = _attendee(d, 'ana')
    ben, ben_token = _attendee(d, 'ben')
    late, _ = _attendee(d, 'late')                       # registered, never scanned
    for token in (ana_token, ben_token):
        assert _scan(d['staff'], token, d['event_id']).get_json()['status'] == 'success'

    # Not checked in: no poll shown and the vote is refused
    assert 'Best language?' not in late.get(f"/interact/{d['event_id']}").get_data(as_text=True)
    assert late.post(f"/interact/poll/{poll['id']}/vote", data={'choice': '0'}).status_code == 403
    outsider = f"{_unique('outsider')}@test.edu"
    _user(d['db'], outsider, 'Student')
    assert _login(d['app'], outsider, 'Student').post(f"/interact/poll/{poll['id']}/vote",
                                                      data={'choice': '0'}).status_code == 403

    assert 'Best language?' in ana.get(f"/interact/{d['event_id']}").get_data(as_text=True)
    ana.post(f"/interact/poll/{poll['id']}/vote", data={'choice': '1'})
    ana.post(f"/interact/poll/{poll['id']}/vote", data={'choice': '2'})      # a second vote isn't counted
    ben.post(f"/interact/poll/{poll['id']}/vote", data={'choice': '1'})
    ben.post(f"/interact/poll/{poll['id']}/vote", data={'choice': ['0', '1']})  # single choice: one option
    assert live.results(poll) == {'votes': 2, 'counts': [0, 2, 0]}

    # A multiple-choice poll counts each option picked; a closed poll takes no votes
    multi = _open_poll(d, question='Which days?', options='Mon\nTue\nWed', multiple='on')
    ana.post(f"/interact/poll/{multi['id']}/vote", data={'choice': ['0', '2']})
    assert live.results(multi) == {'votes': 1, 'counts': [1, 0, 1]}
    d['staff'].post(f"/interact/poll/{multi['id']}/status", data={'status': 'closed'})
    ben.post(f"/interact/poll/{multi['id']}/vote", data={'choice': '1'})
    assert live.results(multi) == {'votes': 1, 'counts': [1, 0, 1]}

    # A team member of a checked-in registration takes part too
    mate = f"{_unique('mate')}@test.edu"
    _user(d['db'], mate, 'Student')
    _, team_token = _registration(d, lead_name='Lead', lead_email=f"{_unique('lead')}@test.edu",
                                  members=[{'name': 'Mate', 'email': mate}])
    _scan(d['staff'], team_token, d['event_id'])
    assert _login(d['app'], mate, 'Student').post(f"/interact/poll/{poll['id']}/vote",
                                                  data={'choice': '0'}).status_code == 302
    assert live.results(poll) == {'votes': 3, 'counts': [1, 2, 0]}


def test_only_the_events_staff_host(gate):  # noqa: F811
    d = gate
    attendee, token = _attendee(d, 'cara')
    _scan(d['staff'], token, d['event_id'])
    outsider = _login(d['app'], d['people']['coord_out'], 'EventCoordinator')
    for client in (attendee, outsider):
        assert client.get(f"/interact/{d['event_id']}/host").status_code == 403
        assert client.post(f"/interact/{d['event_id']}/polls",
                           data={'question': 'X', 'options': 'a\nb'}).status_code == 403
        assert client.get(f"/interact/{d['event_id']}/screen").status_code == 403
    assert live.polls_for(d['event_id']) == []
    for client in (d['owner'], d['staff']):
        assert client.get(f"/interact/{d['event_id']}/host").status_code == 200


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_an_upvote_counts_once_and_hidden_questions_stay_off_the_projector(gate):  # noqa: F811
    d = gate
    ana, a_token = _attendee(d, 'ana')
    ben, b_token = _attendee(d, 'ben')
    for token in (a_token, b_token):
        _scan(d['staff'], token, d['event_id'])
    ana.post(f"/interact/{d['event_id']}/questions", data={'text': 'Will slides be shared?'})
    ana.post(f"/interact/{d['event_id']}/questions", data={'text': 'Off-topic rant'})
    shared, rant = sorted(live.questions_for(d['event_id']), key=lambda q: q['text'])[::-1]
    assert shared['text'] == 'Will slides be shared?'

    for _ in range(3):
        ben.post(f"/interact/question/{shared['id']}/upvote")
    ana.post(f"/interact/question/{shared['id']}/upvote")
    assert live.get_question(shared['id']) and \
        next(q for q in live.questions_for(d['event_id']) if q['id'] == shared['id'])['votes'] == 2

    d['staff'].post(f"/interact/question/{rant['id']}/status", data={'status': 'hidden'})
    screen = d['staff'].get(f"/interact/{d['event_id']}/screen").get_data(as_text=True)
    data = d['staff'].get(f"/interact/{d['event_id']}/data").get_json()
    assert 'Will slides be shared?' in screen and 'Off-topic rant' not in screen
    assert [q['text'] for q in data['questions']] == ['Will slides be shared?']
    assert 'Off-topic rant' not in ben.get(f"/interact/{d['event_id']}").get_data(as_text=True)

    # Moderated: a new question waits for the host before anyone sees it
    d['staff'].post(f"/interact/{d['event_id']}/settings", data={'qa_moderated': 'on'})
    ben.post(f"/interact/{d['event_id']}/questions", data={'text': 'Pending one'})
    assert 'Pending one' not in d['staff'].get(f"/interact/{d['event_id']}/screen").get_data(as_text=True)
    assert 'Pending one' in d['staff'].get(f"/interact/{d['event_id']}/host").get_data(as_text=True)
    pending = next(q for q in live.questions_for(d['event_id'], statuses=('pending',)))
    d['staff'].post(f"/interact/question/{pending['id']}/status", data={'status': 'visible'})
    assert 'Pending one' in d['staff'].get(f"/interact/{d['event_id']}/screen").get_data(as_text=True)


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_a_question_with_a_script_shows_as_text(gate):  # noqa: F811
    d = gate
    ana, token = _attendee(d, 'ana')
    _scan(d['staff'], token, d['event_id'])
    nasty = '<script>alert(1)</script><img src=x onerror=alert(2)>'
    ana.post(f"/interact/{d['event_id']}/questions", data={'text': nasty})
    _open_poll(d, question='<b>Bold?</b>', options='<i>yes</i>\nno')
    for page in (ana.get(f"/interact/{d['event_id']}").get_data(as_text=True),
                 d['staff'].get(f"/interact/{d['event_id']}/host").get_data(as_text=True),
                 d['staff'].get(f"/interact/{d['event_id']}/screen").get_data(as_text=True)):
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in page
        assert '<script>alert(1)' not in page and '<img src=x' not in page
    screen = d['staff'].get(f"/interact/{d['event_id']}/screen").get_data(as_text=True)
    assert '&lt;b&gt;Bold?&lt;/b&gt;' in screen and '<i>yes</i>' not in screen
    # The projector's live updates set text, never HTML
    js = open('static/js/pages/interact__screen.js').read()
    assert 'textContent' in js and 'innerHTML' not in js


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_event_report_includes_poll_results(gate):  # noqa: F811
    d = gate
    poll = _open_poll(d, question='Rate the keynote', options='Great\nOkay')
    voters = []
    for name in ('ana', 'ben', 'cy'):
        client, token = _attendee(d, name)
        _scan(d['staff'], token, d['event_id'])
        voters.append(client)
    for client, choice in zip(voters, ('0', '0', '1')):
        client.post(f"/interact/poll/{poll['id']}/vote", data={'choice': choice})

    resp = d['owner'].get(f"/spoc/event_report/{d['event_id']}")
    assert resp.status_code == 200
    sheet = openpyxl.load_workbook(io.BytesIO(resp.data))['Polls']
    rows = [[c.value for c in row] for row in sheet.iter_rows()]
    assert rows[0][:3] == ['Poll', 'Option', 'Answers']
    assert rows[1:] == [['Rate the keynote', 'Great', 2, 66.7, 3], ['Rate the keynote', 'Okay', 1, 33.3, 3]]
