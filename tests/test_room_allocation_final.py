"""
tests/test_room_allocation_final.py — UPG-306 on the real database layer.

The SPOC's rooms: a room number or name and a capacity in people; "Auto-fill"
makes a draft in registration order, a team kept whole, cancelled teams left
out; the draft is the SPOC's alone. The final check lists each room and what to
fix; "Allocate final" writes the rooms onto registrations and tells teams by
email to the lead, on the website, or both. Later changes reach teams only on
the next Allocate final, and only the teams they change.
"""
import csv
import io

import pytest

import utils_email
from tests import test_spoc_cancel_team as _cancel
from tests.test_integration_flow import _login, _unique, _user

host = _cancel.host


@pytest.fixture
def rooms(host, monkeypatch):
    h = host
    sent = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: sent.append(
        {'to': str(to).lower(), 'subject': subject, 'html': html}) or True)
    h['sent'] = sent

    def team(event_id, name, people=2, at='2026-01-01 10:00:00', status=None):
        """A registered team of `people` (the lead included), registered at `at`."""
        reg_id, lead, mate = h['register'](event_id, team_name=name)
        members = list(h['reg'](reg_id).get('members') or [])
        for i in range(people - len(members)):
            members.append({'name': f'Extra {i}', 'email': f"{_unique('xtra')}@test.edu", 'usn': f'1SN22CS9{i:02d}'})
        update = {'members': members[:people], 'registered_at': at}
        if status:
            update['status'] = status
        h['db'].collection('registrations').document(reg_id).update(update)
        return {'id': reg_id, 'lead': lead, 'mate': mate, 'name': name}

    def setup(client, event_id, rows, action='save'):
        return client.post(f'/spoc/setup_rooms/{event_id}', data={
            'room_name[]': [r[0] for r in rows], 'capacity[]': [str(r[1]) for r in rows], 'action': action})

    def plan(event_id):
        return h['db'].collection('events').document(event_id).get().to_dict().get('room_plan') or {}

    def final(client, event_id, **ticks):
        return client.post(f'/spoc/room_allocation/{event_id}/final',
                           data={k: '1' for k, on in ticks.items() if on})

    def dashboard(email):
        _user(h['db'], email, 'Student', name='Pat Participant')
        return _login(h['app'], email, 'Student').get('/participant/dashboard').get_data(as_text=True)

    def room_emails(to=None):
        return [m for m in sent if m['subject'].startswith('🏛️ Your Room') and (to is None or m['to'] == to)]

    def notices(email):
        return [n.to_dict() for n in h['db'].collection('notifications_v2').stream()
                if n.to_dict().get('user_email') == email and n.to_dict().get('type') == 'room']

    h.update(team=team, setup=setup, plan=plan, final=final, dashboard=dashboard, room_emails=room_emails,
             notices=notices)
    return h


def _assigned(h, reg_id):
    return h['reg'](reg_id).get('assigned_room')


# ── Criterion 1: rooms, auto-fill, nothing shown ─────────────────────────────

def test_auto_fill_drafts_in_registration_order_keeps_teams_whole_and_shows_nobody(rooms):
    h = rooms
    event_id = h['event']()
    first = h['team'](event_id, 'First Four', people=4, at='2026-01-01 09:00:00')
    second = h['team'](event_id, 'Second Three', people=3, at='2026-01-01 09:05:00')
    third = h['team'](event_id, 'Third Two', people=2, at='2026-01-01 09:10:00')
    gone = h['team'](event_id, 'Gone Team', people=2, at='2026-01-01 08:00:00', status='cancelled')

    resp = h['setup'](h['owner'], event_id, [('101', 6), ('Lab 2', 5), ('', 9), ('Zero', 0)], action='allocate')
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/spoc/room_allocation/{event_id}')
    p = h['plan'](event_id)
    assert p['rooms'] == [{'name': '101', 'capacity': 6}, {'name': 'Lab 2', 'capacity': 5}]
    # 4 people fill 101 to 4 of 6; 3 don't fit in the 2 left, so Lab 2; 2 fit in 101's last 2 seats
    assert p['draft'] == {first['id']: '101', second['id']: 'Lab 2', third['id']: '101'}
    assert gone['id'] not in p['draft']

    # Nobody else sees a room: no registration has one, nor the dashboards
    for t in (first, second, third):
        assert not _assigned(h, t['id'])
    for email in (first['lead'], first['mate']):
        assert 'data-my-room' not in h['dashboard'](email)
    assert h['room_emails']() == []

    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert 'data-room-state="draft"' in page and 'nobody sees these rooms yet' in page
    assert 'Gone Team' not in page and 'First Four' in page


def test_a_team_too_big_for_every_room_stays_without_one(rooms):
    h = rooms
    event_id = h['event']()
    big = h['team'](event_id, 'Big Band', people=4)
    h['setup'](h['owner'], event_id, [('Small', 3)], action='allocate')
    assert big['id'] not in h['plan'](event_id)['draft']


# ── Criterion 2: moving a team changes the draft only; other SPOCs can't ─────

def test_moving_a_team_changes_only_the_draft_and_another_spoc_cant(rooms):
    h = rooms
    event_id = h['event']()
    t = h['team'](event_id, 'Movers')
    h['setup'](h['owner'], event_id, [('A1', 10), ('B1', 10)], action='allocate')
    resp = h['owner'].post(f'/spoc/reassign_room/{event_id}/{t["id"]}', json={'room': 'B1'})
    data = resp.get_json()
    assert data['status'] == 'ok' and data['room'] == 'B1'
    assert {r['name']: r['people'] for r in data['rooms']} == {'A1': 0, 'B1': 2}
    assert h['plan'](event_id)['draft'][t['id']] == 'B1'
    assert not _assigned(h, t['id'])
    # "No room" takes it out of the draft
    assert h['owner'].post(f'/spoc/reassign_room/{event_id}/{t["id"]}', json={'room': ''}).get_json()['unallocated'] == 1
    assert t['id'] not in h['plan'](event_id)['draft']

    other = f"{_unique('otherspoc')}@test.edu"
    _user(h['db'], other, 'ClubSPOC')
    client = _login(h['app'], other, 'ClubSPOC')
    assert client.get(f'/spoc/room_allocation/{event_id}').status_code == 403
    assert client.get(f'/spoc/room_allocation/{event_id}/review').status_code == 403
    assert client.get(f'/spoc/room_allocation/{event_id}/export.csv').status_code == 403
    assert client.post(f'/spoc/reassign_room/{event_id}/{t["id"]}', json={'room': 'A1'}).status_code == 403
    assert client.post(f'/spoc/room_allocation/{event_id}/autofill').status_code == 403
    assert h['final'](client, event_id, email=True, website=True).status_code == 403
    assert t['id'] not in h['plan'](event_id)['draft']
    # The owner can't move another event's team through their own event
    other_event = h['event']()
    stranger = h['team'](other_event, 'Strangers')
    assert h['owner'].post(f'/spoc/reassign_room/{event_id}/{stranger["id"]}', json={'room': 'A1'}).status_code == 404


# ── Criterion 3: the final check and the CSV ─────────────────────────────────

def test_the_final_check_lists_rooms_and_what_to_fix_and_the_csv_has_every_team(rooms):
    h = rooms
    event_id = h['event']()
    a = h['team'](event_id, 'Alpha Team', people=3, at='2026-01-01 09:00:00')
    b = h['team'](event_id, 'Bravo Team', people=3, at='2026-01-01 09:01:00')
    h['setup'](h['owner'], event_id, [('R1', 4)], action='allocate')        # Alpha in, Bravo doesn't fit
    h['owner'].post(f'/spoc/reassign_room/{event_id}/{b["id"]}', json={'room': 'R1'})   # now 6 of 4
    late = h['team'](event_id, 'Late Team', people=2, at='2099-01-01 00:00:00')       # after the draft

    page = h['owner'].get(f'/spoc/room_allocation/{event_id}/review').get_data(as_text=True)
    room = page[page.index('data-review-room="R1"'):]
    room = room[:room.index('</table>')]
    assert '6 of 4 seats' in room and '2 team(s)' in room and 'over by 2' in room
    assert 'Alpha Team' in room and 'Bravo Team' in room
    assert 'R1 has 6 people for 4 seats.' in page
    unallocated = page[page.index('data-review-unallocated'):]
    assert 'Late Team' in unallocated and 'after the draft' in unallocated
    assert '1 team(s) registered after the draft was made.' in page
    assert 'name="anyway"' in page and 'name="email"' in page and 'name="website"' in page

    resp = h['owner'].get(f'/spoc/room_allocation/{event_id}/export.csv')
    assert resp.status_code == 200 and resp.mimetype == 'text/csv'
    table = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert table[0][:2] == ['Room', 'Team']
    assert sorted((r[0], r[1]) for r in table[1:]) == [('No room', 'Late Team'), ('R1', 'Alpha Team'),
                                                       ('R1', 'Bravo Team')]
    assert {r[1]: r[4] for r in table[1:]}['Alpha Team'] == '3'
    assert not any(_assigned(h, t['id']) for t in (a, b, late))


def test_a_room_not_in_the_list_is_named_on_the_final_check(rooms):
    h = rooms
    event_id = h['event']()
    t = h['team'](event_id, 'Lost Team')
    h['setup'](h['owner'], event_id, [('R1', 10)])
    h['owner'].post(f'/spoc/reassign_room/{event_id}/{t["id"]}', json={'room': 'Annex'})
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}/review').get_data(as_text=True)
    assert "Annex isn&#39;t in your room list" in page and 'data-review-unknown' in page


# ── Criterion 4: what stops Allocate final ───────────────────────────────────

def test_allocate_final_needs_a_tick_and_over_capacity_needs_allocate_anyway(rooms):
    h = rooms
    event_id = h['event']()
    a = h['team'](event_id, 'Alpha', people=3, at='2026-01-01 09:00:00')
    b = h['team'](event_id, 'Bravo', people=3, at='2026-01-01 09:01:00')
    h['setup'](h['owner'], event_id, [('R1', 4)], action='allocate')
    h['owner'].post(f'/spoc/reassign_room/{event_id}/{b["id"]}', json={'room': 'R1'})

    resp = h['final'](h['owner'], event_id)
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/review')
    assert not _assigned(h, a['id']) and not h['plan'](event_id).get('final')

    h['final'](h['owner'], event_id, website=True)                          # over capacity: refused
    assert not _assigned(h, a['id']) and not h['plan'](event_id).get('final')

    h['final'](h['owner'], event_id, website=True, anyway=True)
    assert _assigned(h, a['id']) == 'R1' and _assigned(h, b['id']) == 'R1'


def test_allocate_final_with_an_empty_draft_is_refused(rooms):
    h = rooms
    event_id = h['event']()
    t = h['team'](event_id, 'Nobody Placed')
    h['setup'](h['owner'], event_id, [('R1', 10)])
    h['final'](h['owner'], event_id, email=True, website=True)
    assert not _assigned(h, t['id']) and not h['plan'](event_id).get('final')
    assert h['room_emails']() == []


# ── Criterion 5: email to the team lead only ─────────────────────────────────

@pytest.mark.parametrize('portal', [False, True])
def test_email_only_reaches_each_lead_once_and_keeps_the_room_off_the_site(rooms, portal):
    h = rooms
    event_id = h['event'](**({'participant_emails': 'portal'} if portal else {'participant_emails': 'all'}))
    t1 = h['team'](event_id, 'Email One', people=3, at='2026-01-01 09:00:00')
    t2 = h['team'](event_id, 'Email Two', people=2, at='2026-01-01 09:01:00')
    h['setup'](h['owner'], event_id, [('Hall 7', 10)], action='allocate')

    resp = h['final'](h['owner'], event_id, email=True)
    assert resp.status_code == 302
    for t in (t1, t2):
        mails = h['room_emails'](t['lead'])
        assert len(mails) == 1 and 'Hall 7' in mails[0]['subject'] and 'Hall 7' in mails[0]['html']
        assert h['room_emails'](t['mate']) == []
        assert h['notices'](t['lead']) == [] and h['notices'](t['mate']) == []
        assert _assigned(h, t['id']) == 'Hall 7'
    others = [m for m in h['room_emails']() if m['to'] not in (t1['lead'], t2['lead'])]
    assert others == []
    # Not on the participant's site, lead's or member's
    assert 'data-my-room' not in h['dashboard'](t1['lead'])
    assert 'data-my-room' not in h['dashboard'](t1['mate'])
    # The scanner (staff) sees it
    scan = _cancel._scan(h, h['owner'], event_id, t1['id']).get_json()
    assert (scan.get('details') or scan).get('room') == 'Hall 7', scan
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert 'data-room-state="final"' in page and 'emailed to team leads only' in page


# ── Criterion 6: on the website only ─────────────────────────────────────────

def test_website_only_shows_the_room_to_the_lead_and_every_member_and_sends_no_email(rooms):
    h = rooms
    event_id = h['event'](participant_emails='all')
    t = h['team'](event_id, 'Site Team', people=3)
    h['setup'](h['owner'], event_id, [('Lab 9', 10)], action='allocate')
    h['final'](h['owner'], event_id, website=True)

    assert h['room_emails']() == []
    members = [m['email'] for m in h['reg'](t['id'])['members'] if m.get('email')]
    assert len(set(members) | {t['lead']}) == 3
    for email in set(members) | {t['lead']}:
        assert len(h['notices'](email)) == 1, email
        page = h['dashboard'](email)
        assert 'data-my-room' in page and 'Room Lab 9' in page, email


# ── Criterion 7: changes after a final ───────────────────────────────────────

def test_after_a_final_a_change_waits_for_the_next_one_which_tells_only_the_teams_it_changes(rooms):
    h = rooms
    event_id = h['event'](participant_emails='all')
    stay = h['team'](event_id, 'Stayers', at='2026-01-01 09:00:00')
    mover = h['team'](event_id, 'Movers', at='2026-01-01 09:01:00')
    dropped = h['team'](event_id, 'Dropped', at='2026-01-01 09:02:00')
    h['setup'](h['owner'], event_id, [('R1', 10), ('R2', 10)], action='allocate')
    h['final'](h['owner'], event_id, email=True, website=True)
    assert len(h['room_emails']()) == 3
    assert all(len(h['notices'](t['lead'])) == 1 for t in (stay, mover, dropped))

    h['owner'].post(f'/spoc/reassign_room/{event_id}/{mover["id"]}', json={'room': 'R2'})
    h['owner'].post(f'/spoc/reassign_room/{event_id}/{dropped["id"]}', json={'room': ''})
    # Not shown until Allocate final
    assert _assigned(h, mover['id']) == 'R1' and _assigned(h, dropped['id']) == 'R1'
    assert 'Room R1' in h['dashboard'](mover['mate'])
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert "2 change(s) in the draft below aren't sent yet." in page

    h['final'](h['owner'], event_id, email=True, website=True)
    assert _assigned(h, mover['id']) == 'R2' and not _assigned(h, dropped['id']) and _assigned(h, stay['id']) == 'R1'
    assert len(h['room_emails'](mover['lead'])) == 2 and 'R2' in h['room_emails'](mover['lead'])[-1]['subject']
    assert len(h['room_emails'](stay['lead'])) == 1 and len(h['notices'](stay['lead'])) == 1
    assert len(h['notices'](mover['mate'])) == 2
    withdrawn = [n for n in h['notices'](dropped['lead']) if 'withdrawn' in n['message']]
    assert len(withdrawn) == 1
    assert any('Room withdrawn' in m['subject'] and m['to'] == dropped['lead'] for m in h['sent'])
    assert 'Room R2' in h['dashboard'](mover['mate'])
    assert 'data-my-room' not in h['dashboard'](dropped['lead'])

    # Pressing it again sends nothing more
    count, notes = len(h['sent']), len(h['notices'](mover['lead']))
    h['final'](h['owner'], event_id, email=True, website=True)
    assert len(h['sent']) == count and len(h['notices'](mover['lead'])) == notes


def test_ticking_the_website_later_tells_teams_already_emailed_once_on_the_site(rooms):
    h = rooms
    event_id = h['event'](participant_emails='all')
    t = h['team'](event_id, 'Later Site')
    h['setup'](h['owner'], event_id, [('R1', 10)], action='allocate')
    h['final'](h['owner'], event_id, email=True)
    assert 'data-my-room' not in h['dashboard'](t['mate'])
    h['final'](h['owner'], event_id, email=True, website=True)
    assert len(h['room_emails'](t['lead'])) == 1                      # no second email
    assert len(h['notices'](t['lead'])) == 1 and 'Room R1' in h['dashboard'](t['mate'])


# ── Criterion 8: rooms given before UPG-306 ──────────────────────────────────

def test_rooms_given_before_the_draft_step_still_show_and_arent_emailed_again(rooms):
    h = rooms
    event_id = h['event'](participant_emails='all')
    t = h['team'](event_id, 'Old Timers')
    db = h['db']
    db.collection('events').document(event_id).update({'rooms': [{'name': 'Old Hall', 'capacity': 50}],
                                                       'room_emails_sent': 1})
    db.collection('registrations').document(t['id']).update({'assigned_room': 'Old Hall'})

    assert 'Room Old Hall' in h['dashboard'](t['mate'])
    page = h['owner'].get(f'/spoc/room_allocation/{event_id}').get_data(as_text=True)
    assert 'given before the draft step' in page
    assert 'data-room-state="final"' in page

    h['final'](h['owner'], event_id, email=True, website=True)
    assert h['room_emails']() == [] and h['notices'](t['lead']) == []
    assert _assigned(h, t['id']) == 'Old Hall' and 'Room Old Hall' in h['dashboard'](t['mate'])


def test_the_old_send_room_emails_button_now_goes_to_the_final_check(rooms):
    h = rooms
    event_id = h['event']()
    t = h['team'](event_id, 'Button Team')
    h['setup'](h['owner'], event_id, [('R1', 10)], action='allocate')
    resp = h['owner'].post(f'/spoc/send_room_emails/{event_id}')
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/review')
    assert h['room_emails']() == [] and not _assigned(h, t['id'])
