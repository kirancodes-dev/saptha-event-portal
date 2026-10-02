"""
tests/test_spoc_event_authz.py — BLK-17 on the real database layer: a SPOC
acts only on events they may manage. Another SPOC gets 403 on every SPOC
route that changes or reveals an event, and nothing changes.
"""
import datetime
import io

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user
from tests.test_registration_no_auto_login import _form


@pytest.fixture
def two_spocs(real_app, monkeypatch):
    """SPOC A owns event A (with one registration); SPOC B owns event B (with one)."""
    flask_app, db = real_app
    import utils_email
    monkeypatch.setattr(utils_email, '_send', lambda *a, **k: True)

    def spoc_with_event(tag):
        spoc = f"{_unique('spoc' + tag)}@test.edu"
        _user(db, spoc, 'ClubSPOC')
        client = _login(flask_app, spoc, 'ClubSPOC')
        event_id = _create_event(client, db, _unique('Event ' + tag), datetime.date.today().isoformat(), team=False)
        student = f"{_unique('stu' + tag)}@test.edu"
        _user(db, student, 'Student')
        assert _login(flask_app, student, 'Student').post(
            f'/forms/submit/{event_id}', data=_form(student)).status_code == 302
        reg_id = next(d.id for d in db.collection('registrations').where('event_id', '==', event_id).stream())
        return client, event_id, reg_id

    a = spoc_with_event('a')
    b = spoc_with_event('b')
    return flask_app, db, a, b


def _snapshot(db, event_id):
    regs = sorted((d.id, sorted(d.to_dict().items(), key=str))
                  for d in db.collection('registrations').where('event_id', '==', event_id).stream())
    notes = len(list(db.collection('announcements').where('event_id', '==', event_id).stream()))
    event = db.collection('events').document(event_id).get().to_dict()
    return sorted(event.items(), key=str), regs, notes


WRITES = [
    ('end_event', 'post', '/spoc/end_event/{e}', {'data': {'template_id': '1'}}),
    ('announce', 'post', '/spoc/announce/{e}', {'data': {'message': 'Hijacked', 'priority': 'info'}}),
    ('agenda', 'post', '/spoc/agenda/{e}', {'data': {'session_title[]': ['X'], 'session_time[]': ['10:00']}}),
    ('publish_results', 'post', '/spoc/publish_results/{e}', {}),
    ('toggle_openhall', 'post', '/spoc/toggle_openhall/{e}', {}),
    ('upload_cert_templates', 'post', '/spoc/upload_cert_templates/{e}',
     {'data': {'cert_template': (io.BytesIO(b'%PDF-1.4'), 't.pdf')}, 'content_type': 'multipart/form-data'}),
    ('upload_judges_csv', 'post', '/spoc/upload_judges_csv/{e}',
     {'data': {'judges_csv': (io.BytesIO(b'name,email\nEve,eve-csv@test.edu\n'), 'j.csv')},
      'content_type': 'multipart/form-data'}),
    ('add_judge', 'post', '/spoc/add_judge/{e}', {'data': {'judge_name': 'Eve', 'judge_email': 'eve-add@test.edu'}}),
    ('setup_rooms', 'post', '/spoc/setup_rooms/{e}', {'data': {'room_name[]': ['Lab 1'], 'room_capacity[]': ['10']}}),
    ('reassign_room', 'post', '/spoc/reassign_room/{e}/{r}', {'json': {'room': 'Hijacked Lab'}}),
]
READS = [
    ('agenda page', '/spoc/agenda/{e}'),
    ('judging audit', '/spoc/judging/audit/{e}'),
    ('schedule optimizer', '/spoc/schedule/optimize/{e}'),
    ('NFC verify', '/spoc/ticket/nfc-verify/{e}'),
    ('judge matchmaker', '/spoc/judging/matchmaker/{e}'),
]


# ── Criteria 1 and 2 ───────────────────────────────────────────────────────

def test_another_spoc_gets_403_on_every_route_and_nothing_changes(two_spocs):
    flask_app, db, (client_a, event_a, reg_a), (client_b, event_b, reg_b) = two_spocs
    before = _snapshot(db, event_a)

    for name, method, path, kwargs in WRITES:
        resp = getattr(client_b, method)(path.format(e=event_a, r=reg_a), **kwargs)
        assert resp.status_code == 403, (name, resp.status_code)
    for name, path in READS:
        resp = client_b.get(path.format(e=event_a))
        assert resp.status_code == 403, (name, resp.status_code)

    assert _snapshot(db, event_a) == before
    for judge in ('eve-csv@test.edu', 'eve-add@test.edu'):
        assert not db.collection('users').document(judge).get().exists


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_owner_still_manages_their_event(two_spocs):
    flask_app, db, (client_a, event_a, reg_a), _ = two_spocs
    judge = f"{_unique('judge')}@test.edu"

    assert client_a.post(f'/spoc/add_judge/{event_a}', data={'judge_name': 'Jo', 'judge_email': judge}).status_code == 302
    staff = db.collection('events').document(event_a).get().to_dict().get('staff', [])
    assert any(s.get('email') == judge and s.get('role') == 'Judge' for s in staff)

    before = bool(db.collection('events').document(event_a).get().to_dict().get('open_hall_mode'))
    client_a.post(f'/spoc/toggle_openhall/{event_a}')
    assert bool(db.collection('events').document(event_a).get().to_dict().get('open_hall_mode')) is not before

    assert client_a.get(f'/spoc/agenda/{event_a}').status_code == 200
    assert client_a.get(f'/spoc/judging/audit/{event_a}').status_code == 200
    assert client_a.post(f'/spoc/reassign_room/{event_a}/{reg_a}', json={'room': 'Lab 2'}).get_json()['room'] == 'Lab 2'

    client_a.post(f'/spoc/publish_results/{event_a}')
    event = db.collection('events').document(event_a).get().to_dict()
    assert event['status'] == 'completed' and event['results_published'] is True


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_owner_cant_reassign_another_events_registration(two_spocs):
    flask_app, db, (client_a, event_a, reg_a), (client_b, event_b, reg_b) = two_spocs
    before = db.collection('registrations').document(reg_b).get().to_dict().get('assigned_room')
    resp = client_a.post(f'/spoc/reassign_room/{event_a}/{reg_b}', json={'room': 'Hijacked Lab'})
    assert resp.status_code == 404
    assert db.collection('registrations').document(reg_b).get().to_dict().get('assigned_room') == before
