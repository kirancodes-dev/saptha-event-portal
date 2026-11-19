"""
tests/test_hackathon_update_delete.py — UPG-323: the SPOC deletes an update
from "Updates for teams" (a doubled reminder, a mistake); teams stop seeing it.
"""
import services_hackathon as hk
from tests.test_hackathon_portal import _page, hack  # noqa: F401
from tests.test_integration_flow import _login, _unique, _user


def _updates(h, eid):
    return hk.updates(h['ev'](eid))


# 1. Each update on the SPOC's page has a Delete button that asks first
def test_each_update_has_a_delete_button_that_asks_first(hack):  # noqa: F811
    h = hack
    eid = h['event']()
    h['owner'].post(f'/spoc/hackathon/{eid}/update', data={'title': 'Reminder', 'message': 'Submit by 8.'})
    h['owner'].post(f'/spoc/hackathon/{eid}/update', data={'title': 'Reminder', 'message': 'Submit by 8.'})
    page = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert page.count('data-delete-update') == 2
    assert f'action="/spoc/hackathon/{eid}/update/delete"' in page
    assert 'data-confirm="Delete this update? Teams will no longer see it."' in page
    for u in _updates(h, eid):
        assert f'name="key" value="{u["id"]}"' in page


# 2. Deleting one of two identical updates leaves the other; teams no longer see it
def test_deleting_one_update_leaves_the_others_and_teams_stop_seeing_it(hack):  # noqa: F811
    h = hack
    eid = h['event']()
    t = h['team'](eid)
    h['owner'].post(f'/spoc/hackathon/{eid}/update', data={'title': 'Mentors at 3 PM'})
    h['owner'].post(f'/spoc/hackathon/{eid}/update', data={'title': 'Wrong room posted'})
    h['owner'].post(f'/spoc/hackathon/{eid}/update', data={'title': 'Mentors at 3 PM'})
    before = t['client'].get(f'/hackathon/{eid}/state').get_json()['version']
    wrong = next(u for u in _updates(h, eid) if u['title'] == 'Wrong room posted')
    r = h['owner'].post(f'/spoc/hackathon/{eid}/update/delete', data={'key': wrong['id']})
    assert r.status_code == 302 and r.headers['Location'].endswith('#updates')
    titles = [u['title'] for u in _updates(h, eid)]
    assert titles == ['Mentors at 3 PM', 'Mentors at 3 PM']
    assert 'Wrong room posted' not in _page(t['client'], f'/hackathon/{eid}')
    assert t['client'].get(f'/hackathon/{eid}/state').get_json()['version'] != before   # open pages refresh

    dup = _updates(h, eid)[0]
    h['owner'].post(f'/spoc/hackathon/{eid}/update/delete', data={'key': dup['id']})
    assert [u['title'] for u in _updates(h, eid)] == ['Mentors at 3 PM']   # one copy stays

    # Deleting again, or an unknown one, changes nothing
    r = h['owner'].post(f'/spoc/hackathon/{eid}/update/delete', data={'key': dup['id']}, follow_redirects=True)
    assert 'That update is already gone.' in r.get_data(as_text=True)
    assert len(_updates(h, eid)) == 1


# 3. Staff of the event only, and audited
def test_only_the_events_staff_delete_and_it_is_audited(hack):  # noqa: F811
    h = hack
    eid = h['event']()
    t = h['team'](eid)
    h['owner'].post(f'/spoc/hackathon/{eid}/update', data={'title': 'Keep me'})
    key = _updates(h, eid)[0]['id']
    assert h['stranger'].post(f'/spoc/hackathon/{eid}/update/delete', data={'key': key}).status_code == 403
    assert t['client'].post(f'/spoc/hackathon/{eid}/update/delete', data={'key': key}).status_code == 403
    student = f"{_unique('st')}@test.edu"
    _user(h['db'], student, 'Student')
    assert _login(h['app'], student, 'Student').post(f'/spoc/hackathon/{eid}/update/delete',
                                                     data={'key': key}).status_code == 403
    assert len(_updates(h, eid)) == 1

    h['owner'].post(f'/spoc/hackathon/{eid}/update/delete', data={'key': key})
    assert _updates(h, eid) == []
    lines = [d.to_dict() for d in h['db'].collection('audit_log').stream()]
    assert any(l.get('action') == 'HACKATHON_UPDATE_DELETED' and 'Keep me' in str(l.get('details') or l)
               for l in lines)


# 4. An older update without an id is deleted by its time
def test_an_update_without_an_id_is_deleted_by_its_time(hack):  # noqa: F811
    h = hack
    eid = h['event']()
    event = h['ev'](eid)
    hk.post_update(h['db'], eid, event, 'Old one')
    data = hk.data(event)
    data['updates'][0].pop('id')
    hk._save(h['db'], eid, data)
    old = _updates(h, eid)[0]
    assert 'id' not in old
    page = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert f'name="key" value="{old["at"]}"' in page
    h['owner'].post(f'/spoc/hackathon/{eid}/update/delete', data={'key': old['at']})
    assert _updates(h, eid) == []
