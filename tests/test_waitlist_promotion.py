"""
tests/test_waitlist_promotion.py — UPG-112 on the real database layer: one
waitlist promotion (routes_waitlist.auto_promote), reached both from the SPOC's
"promote next" and from a student's cancellation (through
tasks.waitlist_tasks.promote_from_waitlist), takes people in the order they
joined and issues the promoted person a ticket. `position` can't decide the
order: it's the number still waiting plus one, so it repeats or runs backwards
once someone has been promoted or has left.
"""
import time

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def waitlist(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('wlspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Full Talk'), '2031-02-02', team=False)   # status active

    def student(label):
        email = f"{_unique(label)}@test.edu"
        _user(db, email, 'Student', name=label.title())
        return email, _login(flask_app, email, 'Student')

    def join(client):
        resp = client.post(f'/waitlist/join/{event_id}', json={'name': 'W', 'phone': '9876543210'})
        assert resp.status_code in (200, 201), resp.data
        time.sleep(0.01)                                   # distinct join times

    def entry(email):
        [w] = [d.to_dict() for d in db.collection('waitlists').where('event_id', '==', event_id).stream()
               if d.to_dict().get('user_email') == email]
        return w

    def registration(email):
        return [d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream()
                if d.to_dict().get('lead_email') == email]

    return {'app': flask_app, 'db': db, 'owner': owner, 'event_id': event_id, 'student': student, 'join': join,
            'entry': entry, 'registration': registration}


def test_promotion_follows_join_order_and_issues_a_ticket(waitlist):
    d = waitlist
    (a, a_c), (b, b_c), (c, c_c), (late, late_c) = (d['student'](k) for k in ('ana', 'ben', 'cleo', 'dev'))
    for client in (a_c, b_c, c_c):
        d['join'](client)
    assert [d['entry'](e)['position'] for e in (a, b, c)] == [1, 2, 3]

    # The SPOC promotes the first in line, and the second leaves
    resp = d['owner'].post(f"/waitlist/promote/{d['event_id']}")
    assert resp.status_code == 200 and resp.get_json()['promoted']['user_email'] == a
    assert b_c.delete(f"/waitlist/leave/{d['event_id']}").status_code == 200
    d['join'](late_c)                                      # joins last, but gets position 2, ahead of Cleo's 3
    assert d['entry'](late)['position'] < d['entry'](c)['position']

    # A seat frees up when a registered student cancels: Cleo, who joined first, goes next
    holder, holder_c = d['student']('holder')
    reg_id = _unique('REG')
    d['db'].collection('registrations').document(reg_id).set({
        'event_id': d['event_id'], 'lead_email': holder, 'lead_name': 'Holder', 'status': 'Confirmed'})
    assert holder_c.post(f'/participant/cancel/{reg_id}').status_code == 302

    assert d['entry'](c)['status'] == 'promoted'
    assert d['entry'](late)['status'] == 'waiting'
    [reg] = d['registration'](c)
    assert reg['status'] == 'Confirmed' and reg.get('ticket_id')
    ticket = d['db'].collection('tickets').document(reg['ticket_id']).get().to_dict()
    assert ticket['user_email'] == c and ticket['event_id'] == d['event_id']
    assert d['registration'](late) == []


def test_the_task_and_the_spoc_route_share_one_promotion():
    import inspect

    import routes_waitlist
    from tasks import waitlist_tasks
    assert 'auto_promote(db, event_id)' in inspect.getsource(waitlist_tasks.promote_from_waitlist)
    assert 'auto_promote(db, event_id)' in inspect.getsource(routes_waitlist.promote_next)
    assert not [n for n in dir(waitlist_tasks) if n.startswith('promote') and n != 'promote_from_waitlist']
