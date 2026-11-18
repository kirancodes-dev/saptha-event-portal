"""
tests/test_waitlist_delete.py — UPG-317 on the real database layer.

The hosting SPOC deletes one person or team from the waitlist, or the whole
waitlist, from the waitlist card, after ticking to confirm. Only those still
waiting go; accepted teams, other events' waitlists and accounts stay. The
person no longer sees the entry in their portal and can sign up again.
Coordinators see no Delete, and they and other SPOCs get 403.
"""
import services_waitlist
from tests import test_spoc_waitlist as wl
from tests.test_integration_flow import _login, _unique, _user

host = wl.host


def _delete(client, event_id, confirm=True, **data):
    if confirm:
        data['confirm'] = 'yes'
    return client.post(f'/coordinator/registrations/{event_id}/delete_waitlist', data=data)


def _exists(h, wl_id):
    return h['db'].collection('waitlists').document(wl_id).get().exists


def _card(html):
    start = html.index('id="waitlist"')
    return html[start:html.index('</details>', start)]


def _audit(h, action, event_id):
    return [a.to_dict() for a in h['db'].collection('audit_log').stream()
            if a.to_dict().get('action') == action and event_id in str(a.to_dict().get('details') or '')]


# ── Criterion 1: the buttons and their dialogs ──────────────────────────────

def test_each_waiting_row_has_delete_and_the_card_has_delete_the_whole_waitlist(host):
    h = host
    event_id = wl._full_event(h)
    first, _, _ = wl._join(h, event_id, 'First Wait')
    second, _, _ = wl._join(h, event_id, 'Second Wait')
    html = wl._page(h['owner'], event_id)
    card = _card(html)
    assert 'Delete the whole waitlist (2)' in card and 'data-bs-target="#wl-delete-all"' in card
    for wl_id in (first, second):
        row = card[card.index(f'data-waitlist-entry="{wl_id}"'):]
        assert f'data-bs-target="#wl-delete-{wl_id}"' in row[:row.index('</tr>')]
        dialog = html[html.index(f'id="wl-delete-{wl_id}"'):]
        dialog = dialog[:dialog.index('</dialog>')]
        assert 'name="confirm" value="yes"' in dialog and 'required' in dialog
        assert f'name="wl_id" value="{wl_id}"' in dialog and "They aren't told" in dialog
    whole = html[html.index('id="wl-delete-all"'):]
    whole = whole[:whole.index('</dialog>')]
    assert 'name="all" value="1"' in whole and 'All 2 waiting' in whole and 'Delete all 2' in whole
    # A search: the whole-list dialog says it is everyone, not only those shown
    searched = h['owner'].get(f'/coordinator/registrations/{event_id}?wq=second').get_data(as_text=True)
    whole = searched[searched.index('id="wl-delete-all"'):]
    assert 'not only the ones your search shows' in whole[:whole.index('</dialog>')]


def test_nobody_waiting_shows_no_delete_buttons(host):
    h = host
    event_id = wl._full_event(h)
    html = wl._page(h['owner'], event_id)
    assert 'data-delete-waitlist-all' not in html and 'id="wl-delete-all"' not in html


# ── Criterion 2: delete one ─────────────────────────────────────────────────

def test_the_spoc_deletes_one_entry_and_the_rest_keep_their_line(host):
    h = host
    event_id = wl._full_event(h)
    first, first_lead, _ = wl._join(h, event_id, 'First Wait')
    second, second_lead, second_mate = wl._join(h, event_id, 'Second Wait')
    third, _, _ = wl._join(h, event_id, 'Third Wait')
    # The person sees it in their portal before
    assert any(r['id'] == second for r in services_waitlist.standing(h['db'], second_lead))

    resp = _delete(h['owner'], event_id, wl_id=second)
    assert resp.status_code == 302 and resp.headers['Location'].endswith('#waitlist')
    assert not _exists(h, second) and _exists(h, first) and _exists(h, third)
    html = wl._page(h['owner'], event_id)
    assert 'Second Wait deleted from the waitlist.' in html
    card = _card(html)
    assert 'Waitlist: 2 waiting' in card and f'data-waitlist-entry="{second}"' not in card
    third_row = card[card.index(f'data-waitlist-entry="{third}"'):]
    assert '#2' in third_row[:third_row.index('</tr>')]                 # the line closes up
    # Gone from the lead's and the member's portal; their accounts stay
    assert not any(r['id'] == second for r in services_waitlist.standing(h['db'], second_lead))
    assert not any(r['id'] == second for r in services_waitlist.standing(h['db'], second_mate))
    [entry] = _audit(h, 'WAITLIST_DELETED', event_id)
    assert second_lead in entry['details'] and h['spoc'] in entry['details'] and first_lead not in entry['details']


def test_a_deleted_person_can_sign_up_again(host):
    h = host
    event_id = wl._full_event(h)
    wl_id, lead, _ = wl._join(h, event_id, 'Come Back')
    assert _delete(h['owner'], event_id, wl_id=wl_id).status_code == 302
    resp = h['app'].test_client().post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Wanda Wait', 'email': lead, 'phone': '9123456780',
        'usn': '1SN22CS410', 'team_name': 'Come Back',
        'member_1_name': 'Max Mate', 'member_1_email': f"{_unique('wmate')}@test.edu", 'member_1_usn': '1SN22CS411'})
    assert resp.status_code == 302
    again = [d.to_dict() for d in h['db'].collection('waitlists').where('event_id', '==', event_id).stream()
             if d.to_dict().get('email') == lead]
    assert [e['status'] for e in again] == ['waiting']


# ── Criterion 3: delete the whole waitlist ──────────────────────────────────

def test_deleting_the_whole_waitlist_takes_only_this_events_waiting_entries(host):
    h = host
    db = h['db']
    event_id = wl._full_event(h)
    accepted, accepted_lead, _ = wl._join(h, event_id, 'Accepted Team')
    assert wl._accept(h['owner'], event_id, accepted).status_code == 302
    waiting = [wl._join(h, event_id, f'Wait {n}')[0] for n in range(3)]
    other_event = wl._full_event(h)
    elsewhere, _, _ = wl._join(h, other_event, 'Elsewhere')

    resp = _delete(h['owner'], event_id, all='1', wq='wait')
    assert resp.status_code == 302 and '?wq=wait' in resp.headers['Location']
    assert not any(_exists(h, w) for w in waiting)
    assert _exists(h, elsewhere) and wl._entry(h, elsewhere)['status'] == 'waiting'
    assert wl._entry(h, accepted)['status'] == 'promoted'               # the accepted team's record stays
    [reg] = wl._regs_of(h, event_id, accepted_lead)
    assert reg['status'] == 'Confirmed'
    assert services_waitlist.waiting(db, event_id) == []
    html = wl._page(h['owner'], event_id)
    assert 'The waitlist is deleted: 3 waiting removed.' in html
    assert 'Waitlist: 0 waiting' in html and 'data-waitlist-empty' in html
    [entry] = _audit(h, 'WAITLIST_DELETED', event_id)
    assert 'deleted 3 from the waitlist' in entry['details']
    # Nothing left: says so and deletes nothing
    _delete(h['owner'], event_id, all='1')
    assert 'Nobody is waiting, so nothing was deleted.' in wl._page(h['owner'], event_id)


# ── Criterion 4: only with the tick, only this event, only the hosting SPOC ─

def test_without_the_tick_or_for_another_events_entry_nothing_is_deleted(host):
    h = host
    event_id = wl._full_event(h)
    wl_id, _, _ = wl._join(h, event_id, 'Stay Put')
    _delete(h['owner'], event_id, confirm=False, wl_id=wl_id)
    _delete(h['owner'], event_id, confirm=False, all='1')
    assert _exists(h, wl_id)
    assert 'Tick the box to confirm; nothing was deleted from the waitlist.' in wl._page(h['owner'], event_id)

    other_event = wl._full_event(h)
    other, _, _ = wl._join(h, other_event, 'Not Yours')
    _delete(h['owner'], event_id, wl_id=other)
    assert _exists(h, other) and _exists(h, wl_id)
    assert 'Nobody was deleted: they' in wl._page(h['owner'], event_id)
    _delete(h['owner'], event_id)                                        # neither one nor all
    assert _exists(h, wl_id)
    assert not _audit(h, 'WAITLIST_DELETED', event_id)


def test_coordinators_see_no_delete_and_they_and_another_spoc_get_403(host):
    h = host
    db, flask_app = h['db'], h['app']
    event_id = wl._full_event(h)
    wl_id, _, _ = wl._join(h, event_id, 'Guarded')

    coord = f"{_unique('coord')}@test.edu"
    _user(db, coord, 'EventCoordinator')
    db.collection('events').document(event_id).update({'coordinators': [coord]})
    coord_c = _login(flask_app, coord, 'EventCoordinator')
    html = wl._page(coord_c, event_id)
    assert f'data-waitlist-entry="{wl_id}"' in html
    assert 'data-delete-waitlist' not in html and 'id="wl-delete-all"' not in html
    assert _delete(coord_c, event_id, wl_id=wl_id).status_code == 403
    assert _delete(coord_c, event_id, all='1').status_code == 403

    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    other_c = _login(flask_app, other, 'ClubSPOC')
    assert _delete(other_c, event_id, wl_id=wl_id).status_code == 403
    assert _delete(other_c, event_id, all='1').status_code == 403
    assert _exists(h, wl_id) and wl._entry(h, wl_id)['status'] == 'waiting'
