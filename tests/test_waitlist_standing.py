"""
tests/test_waitlist_standing.py — UPG-236 on the real database layer.

A person on a waitlist (the one who joined, or a member of the team that
joined) sees in their portal where they stand: still waiting, with their
place and how many are ahead; accepted and registered; accepted with a fee to
pay (the lead gets the pay link); already registered; or left. The dashboard
shows the ones still open (waiting, or a fee to pay), My events' Waitlisted
tab shows them all, and its JSON carries them too. Nobody else sees them.
"""
from tests import test_spoc_waitlist as _wl
from tests.test_integration_flow import _login, _unique, _user
from tests.test_spoc_waitlist import _accept, _full_event, _join, _regs_of

host = _wl.host   # UPG-211's fixture, through UPG-230's tests


def _student(h, email):
    """Log in as this person (the form made their account; give it a known password)."""
    _user(h['db'], email, 'Student', name='Wanda Wait')
    return _login(h['app'], email, 'Student')


def _get(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, (path, resp.status_code, resp.headers.get('Location'))
    return resp.get_data(as_text=True)


def _card(html, state):
    """The text of the first waitlist card in this state."""
    i = html.index(f'data-waitlist-standing="{state}"')
    return html[i:html.index('</li>', i)]


# ── Criterion 1: waiting, with their place, on the dashboard and My events ──

def test_a_person_waiting_sees_their_place_on_the_dashboard_and_in_my_events(host):
    h = host
    event_id = _full_event(h)
    title = h['db'].collection('events').document(event_id).get().to_dict()['title']
    _join(h, event_id, 'First Wait')
    _, second_lead, _ = _join(h, event_id, 'Second Wait')
    client = _student(h, second_lead)
    dash = _get(client, '/participant/dashboard')
    assert 'data-dashboard-waitlist' in dash
    card = _card(dash, 'waiting')
    assert title in card and 'Team Second Wait' in card
    assert "You're #2 in line</strong>, 1 ahead of you." in card and 'Waiting for a seat' in card
    assert f'href="/event/{event_id}"' in card
    mine = _get(client, '/participant/my_events?tab=waitlisted')
    assert "You're #2 in line" in _card(mine, 'waiting')
    assert 'Waitlisted <span class="portal-tab-count">1</span>' in mine
    data = client.get('/participant/my_events?format=json').get_json()
    [entry] = data['waitlist']
    assert entry['state'] == 'waiting' and entry['place'] == 2 and entry['ahead'] == 1 and entry['waiting_total'] == 2


# ── Criterion 2: a member of the team that joined sees it too ───────────────

def test_a_team_member_on_a_waiting_team_sees_it_and_who_joined(host):
    h = host
    event_id = _full_event(h)
    _, _, mate = _join(h, event_id, 'Mates Wait', full_name='Lara Lead')
    client = _student(h, mate)
    card = _card(_get(client, '/participant/dashboard'), 'waiting')
    assert "You're #1 in line</strong>: you're next." in card
    assert 'Your team lead, Lara Lead, joined for your team.' in card


# ── Criterion 3: accepted (free): registered, and the places close up ───────

def test_once_accepted_the_person_sees_they_are_registered_and_the_next_moves_up(host):
    h = host
    event_id = _full_event(h)
    first, first_lead, _ = _join(h, event_id, 'First Wait')
    _, second_lead, _ = _join(h, event_id, 'Second Wait')
    _accept(h['owner'], event_id, first)
    first_client = _student(h, first_lead)
    # Nothing left to do: not on the dashboard's waitlist; My events says accepted
    assert 'data-dashboard-waitlist' not in _get(first_client, '/participant/dashboard')
    card = _card(_get(first_client, '/participant/my_events?tab=waitlisted'), 'accepted')
    assert 'Accepted: registered' in card and 'href="/participant/my_events?tab=registered"' in card
    assert len(_regs_of(h, event_id, first_lead)) == 1
    # The second in line is now next
    second = _card(_get(_student(h, second_lead), '/participant/dashboard'), 'waiting')
    assert "You're #1 in line</strong>: you're next." in second


# ── Criterion 4: accepted on a paid event: the lead gets the pay link ───────

def test_accepted_on_a_paid_event_the_lead_sees_the_pay_link_and_a_member_is_told_who_pays(host):
    h = host
    event_id = _full_event(h, fee=200)
    wl_id, lead, mate = _join(h, event_id, 'Pay Team', full_name='Pia Payer')
    _accept(h['owner'], event_id, wl_id)
    [reg] = _regs_of(h, event_id, lead)
    card = _card(_get(_student(h, lead), '/participant/dashboard'), 'pay')
    assert 'Accepted: pay to confirm' in card and f'href="/payment/pay/{reg["reg_id"]}"' in card
    member = _card(_get(_student(h, mate), '/participant/dashboard'), 'pay')
    assert 'Your team lead, Pia Payer, pays the fee to confirm the seat.' in member
    assert '/payment/pay/' not in member


# ── Criterion 5: left, and already registered, say so ───────────────────────

def test_left_and_already_registered_entries_say_so(host):
    h = host
    event_id = _full_event(h)
    left_id, lead, _ = _join(h, event_id, 'Gone Team')
    h['db'].collection('waitlists').document(left_id).update({'status': 'cancelled'})
    other = _full_event(h)
    dup_id, _, _ = _join(h, other, 'Dup Team')
    # The same lead also joined another event's waitlist and was already registered there
    h['db'].collection('waitlists').document(dup_id).update({'status': 'already_registered',
                                                             'email': lead, 'user_email': lead})
    client = _student(h, lead)
    mine = _get(client, '/participant/my_events?tab=waitlisted')
    assert 'You left this waitlist.' in _card(mine, 'left')
    assert 'already registered' in _card(mine, 'already')
    assert 'data-dashboard-waitlist' not in _get(client, '/participant/dashboard')


# ── Criterion 6: nobody else sees someone's waitlist ────────────────────────

def test_another_student_sees_no_one_elses_waitlist(host):
    h = host
    event_id = _full_event(h)
    _join(h, event_id, 'Private Wait')
    stranger = f"{_unique('stranger')}@test.edu"
    client = _student(h, stranger)
    assert 'data-waitlist-standing' not in _get(client, '/participant/dashboard')
    mine = _get(client, '/participant/my_events?tab=waitlisted')
    assert 'data-waitlist-standing' not in mine and 't on any waitlist. When an event is full' in mine
    assert client.get('/participant/my_events?format=json').get_json()['waitlist'] == []
