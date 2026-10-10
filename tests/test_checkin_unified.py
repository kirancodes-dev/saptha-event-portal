"""
tests/test_checkin_unified.py — UPG-02 on the real database layer: one
check-in that every scanner uses (POST /ticket/api/checkin). It takes the
ticket's signed token only, lets in only staff who may check in at that
event, applies one payment rule, and a repeat changes nothing.
"""
import datetime
import os
import re
import shutil
import subprocess
import threading

import pytest

import routes_ticket
from db_adapter import to_uuid
from routes_ticket import generate_ticket_token
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = datetime.date.today().isoformat()


@pytest.fixture
def gate(real_app):
    """Today's event with one registration made through the form, an assigned
    and an unassigned coordinator, and the registrant."""
    flask_app, db = real_app
    people = {k: f"{_unique(k)}@test.edu" for k in ('owner', 'coord_in', 'coord_out', 'student')}
    _user(db, people['owner'], 'ClubSPOC')
    _user(db, people['coord_in'], 'EventCoordinator')
    _user(db, people['coord_out'], 'EventCoordinator')
    _user(db, people['student'], 'Student')
    owner = _login(flask_app, people['owner'], 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Gate Day'), TODAY, fee=0, team=False)
    db.collection('events').document(event_id).update({
        'status': 'registration_open',
        'staff': [{'name': 'In', 'email': people['coord_in'], 'role': 'EventCoordinator'}]})
    student = _login(flask_app, people['student'], 'Student')
    assert student.post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes',
        'full_name': 'Tara Ticket', 'email': people['student'], 'phone': '9876543210',
        'usn': '1SN22CS007'}).status_code == 302
    reg_id = next(iter(db.collection('registrations').where('event_id', '==', event_id).stream())).id
    return {'app': flask_app, 'db': db, 'people': people, 'event_id': event_id, 'reg_id': reg_id,
            'owner': owner, 'student': student,
            'staff': _login(flask_app, people['coord_in'], 'EventCoordinator')}


def _reg(d, reg_id=None):
    return d['db'].collection('registrations').document(reg_id or d['reg_id']).get().to_dict()


def _scan(client, scanned, event_id=None, source='scan'):
    return client.post('/ticket/api/checkin', json={'token': scanned, 'event_id': event_id, 'source': source})


def _ticket_qr_text(d, monkeypatch):
    """What the QR on the registrant's ticket page encodes: what a scanner reads."""
    encoded = []
    real = routes_ticket.generate_qr_base64
    monkeypatch.setattr(routes_ticket, 'generate_qr_base64', lambda data: encoded.append(data) or real(data))
    page = d['student'].get(f"/ticket/{d['reg_id']}")
    assert page.status_code == 200 and 'data:image/png;base64,' in page.get_data(as_text=True)
    assert len(encoded) == 1
    return encoded[0]


def _registration(d, event_id=None, **fields):
    """A registration written straight to the database, and its ticket token."""
    reg_id = _unique('REG')
    event_id = event_id or d['event_id']
    data = {'event_id': event_id, 'lead_name': f'Guest {reg_id[-4:]}', 'lead_email': f'{reg_id}@test.edu',
            'team_name': 'Individual', 'attendance': 'Pending', 'payment_status': 'Free', 'members': []}
    data.update(fields)
    d['db'].collection('registrations').document(reg_id).set(data)
    with d['app'].app_context():
        token = generate_ticket_token(reg_id, event_id, data['lead_name'])
    return reg_id, token


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_ticket_page_qr_checks_in_once_and_a_rescan_reports_the_first_time(gate, monkeypatch):
    d = gate
    scanned = _ticket_qr_text(d, monkeypatch)
    assert '/ticket/verify/' in scanned

    monkeypatch.setattr(routes_ticket, '_now', lambda: '09:15:42')
    first = _scan(d['staff'], scanned, d['event_id'])
    assert first.status_code == 200
    body = first.get_json()
    assert body['status'] == 'success' and body['checkin_time'] == '09:15:42'
    assert body['name'] == 'Tara Ticket' and body['reg_id'] == d['reg_id']
    assert [m['usn'] for m in body['members']] == ['1SN22CS007'] and 'email' not in body['members'][0]
    reg = _reg(d)
    assert reg['attendance'] == 'Present' and reg['checkin_time'] == '09:15:42'

    monkeypatch.setattr(routes_ticket, '_now', lambda: '09:47:03')
    again = _scan(d['staff'], scanned, d['event_id'])
    assert again.status_code == 200
    body = again.get_json()
    assert body['status'] == 'already_in' and body['message'] == 'Already checked in at 09:15.'
    assert body['checkin_time'] == '09:15:42'
    assert _reg(d)['checkin_time'] == '09:15:42'

    # Saving per-member attendance afterwards keeps the first time
    resp = d['staff'].post('/coordinator/mark_attendance_granular',
                           json={'reg_id': d['reg_id'], 'present_usns': ['1SN22CS007']})
    assert resp.get_json()['status'] == 'success'
    assert _reg(d)['checkin_time'] == '09:15:42'


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_unassigned_staff_students_and_visitors_cant_check_in(gate, monkeypatch):
    d = gate
    scanned = _ticket_qr_text(d, monkeypatch)
    outsider = _login(d['app'], d['people']['coord_out'], 'EventCoordinator')
    for client in (outsider, d['student']):
        resp = _scan(client, scanned)
        assert resp.status_code == 403 and resp.get_json()['status'] == 'forbidden'
        assert 'Tara' not in resp.get_data(as_text=True)
    assert _scan(d['app'].test_client(), scanned).status_code == 401
    assert _reg(d)['attendance'] == 'Pending'


# ── Criterion 3 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('status', ['Free', 'free', 'FREE', 'Waived', 'Paid', 'paid', 'Paid (Stripe)'])
def test_free_waived_and_paid_registrations_are_let_in_in_any_case(gate, status):
    d = gate
    reg_id, token = _registration(d, payment_status=status)
    # The read-only checks never call it unpaid either
    api = d['staff'].get(f'/ticket/api/verify/{token}')
    assert api.status_code == 200 and api.get_json()['status'] == 'success'
    page = d['staff'].get(f'/ticket/verify/{token}')
    assert page.status_code == 200 and 'Payment pending' not in page.get_data(as_text=True)
    resp = _scan(d['staff'], token)
    assert resp.status_code == 200 and resp.get_json()['status'] == 'success'
    assert _reg(d, reg_id)['attendance'] == 'Present'


@pytest.mark.parametrize('fields', [
    {'payment_status': 'Pending'}, {'payment_status': 'unpaid'}, {'payment_status': 'Refunded'},
    {'payment_status': ''},  # no status at all, on an event with a fee
])
def test_an_unpaid_registration_on_a_paid_event_is_refused(gate, fields):
    d = gate
    d['db'].collection('events').document(d['event_id']).update({'entry_fee': 200})
    reg_id, token = _registration(d, **fields)
    resp = _scan(d['staff'], token)
    assert resp.status_code == 402 and resp.get_json()['status'] == 'unpaid'
    assert _reg(d, reg_id)['attendance'] == 'Pending'


def test_no_status_on_a_free_event_is_free(gate):
    d = gate
    reg_id, token = _registration(d, payment_status='')
    assert _scan(d['staff'], token).get_json()['status'] == 'success'


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_replaying_an_offline_queue_twice_checks_each_in_once(gate):
    d = gate
    queue = [_registration(d)[1] for _ in range(3)]

    first = [_scan(d['staff'], token, d['event_id'], 'offline queue') for token in queue]
    assert [r.status_code for r in first] == [200, 200, 200]
    assert [r.get_json()['status'] for r in first] == ['success'] * 3
    reg_ids = [r.get_json()['reg_id'] for r in first]
    times = {reg_id: _reg(d, reg_id)['checkin_time'] for reg_id in reg_ids}
    assert all(_reg(d, reg_id)['attendance'] == 'Present' for reg_id in reg_ids)

    again = [_scan(d['staff'], token, d['event_id'], 'offline queue') for token in queue]
    assert [r.get_json()['status'] for r in again] == ['already_in'] * 3
    for resp in again:
        reg_id = resp.get_json()['reg_id']
        assert resp.get_json()['checkin_time'] == times[reg_id]
        assert _reg(d, reg_id)['checkin_time'] == times[reg_id]


def _live_server(flask_app):
    from werkzeug.serving import make_server
    server = make_server('127.0.0.1', 0, flask_app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.mark.skipif(not shutil.which('node'), reason='needs Node.js to run static/js/offline-sync.js')
def test_the_browser_queue_sends_each_scan_once_and_replays_safely(gate):
    """static/js/offline-sync.js itself, run in Node against the live app: three
    scans (one scanned twice) queued offline, then sent; then queued again."""
    d = gate
    queue = [_registration(d)[1] for _ in range(3)]
    server = _live_server(d['app'])
    try:
        out = subprocess.run(
            ['node', os.path.join(ROOT, 'tests', 'js', 'offline_sync_harness.js')],
            input='\n'.join(queue + [queue[0]]), capture_output=True, text=True, timeout=60,
            env=dict(os.environ, BASE_URL=f'http://127.0.0.1:{server.server_port}',
                     LOGIN_EMAIL=d['people']['coord_in'], LOGIN_PASSWORD=PASSWORD,
                     LOGIN_ROLE='EventCoordinator', EVENT_ID=d['event_id']))
    finally:
        server.shutdown()
    assert out.returncode == 0, out.stderr
    lines = dict(line.split('=', 1) for line in out.stdout.split() if '=' in line)
    assert lines['queued_first'] == '3' and lines['posts_first'] == '3'
    assert lines['first'] == 'sent:3,alreadyIn:0,refused:0,kept:0' and lines['left_first'] == '0'
    assert lines['second'] == 'sent:0,alreadyIn:3,refused:0,kept:0' and lines['left_second'] == '0'
    assert lines['offline_kept'] == '1'  # a scan made while the server can't be reached waits
    regs = [d['db'].collection('registrations').document(r).get().to_dict()
            for r in [doc.id for doc in d['db'].collection('registrations').where('event_id', '==', d['event_id']).stream()]]
    assert sum(1 for r in regs if r.get('attendance') == 'Present') == 3


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def _function_body(html, name):
    match = re.search(r'function ' + name + r'\s*\([^)]*\)\s*\{', html)
    assert match, name
    depth, i = 1, match.end()
    while depth:
        depth += {'{': 1, '}': -1}.get(html[i], 0)
        i += 1
    return html[match.end():i]


def test_every_scanner_calls_the_one_endpoint_and_it_refuses_registration_ids(gate):
    d = gate
    pages = {
        'coordinator': (d['staff'], f"/coordinator/scan/{d['event_id']}", 'fetchTicket'),
        'hud':         (d['staff'], f"/coordinator/scan-hud/{d['event_id']}", 'processScan'),
        'kiosk':       (d['staff'], f"/checkin/kiosk?event_id={d['event_id']}", 'triggerSearch'),
        'spoc':        (d['owner'], f"/spoc/scan/{d['event_id']}", 'onQRDetected'),
    }
    for name, (client, url, handler) in pages.items():
        resp = client.get(url)
        assert resp.status_code == 200, (name, resp.status_code)
        body = _function_body(resp.get_data(as_text=True), handler)
        assert "'/ticket/api/checkin'" in body, name
        for old in ('/coordinator/get_ticket', '/ticket/api/verify', '/spoc/api/checkin', '/checkin/kiosk/confirm'):
            assert old not in body, (name, old)
    with open(os.path.join(ROOT, 'static', 'js', 'offline-sync.js')) as fh:
        queue_js = fh.read()
    assert "CHECKIN_URL = '/ticket/api/checkin'" in queue_js and '/checkin/kiosk/confirm' not in queue_js
    assert 'src="/static/js/offline-sync.js"' in d['staff'].get(f"/coordinator/scan-hud/{d['event_id']}").get_data(as_text=True)

    for raw in (d['reg_id'], f"https://events.example/ticket/verify/{d['reg_id']}", ''):
        resp = _scan(d['staff'], raw)
        assert resp.status_code == 400 and resp.get_json()['status'] == 'invalid', raw
    assert _reg(d)['attendance'] == 'Pending'


# ── The rest of "What to build" ─────────────────────────────────────────────

def test_a_ticket_whose_event_is_gone_is_refused_everywhere(client, mock_db):
    """BLK-12's note: /ticket/verify POST skipped the staff check when the event
    was missing. A registration can outlive its event only where nothing
    enforces the link (Firestore mode), so this runs on the in-memory store."""
    mock_db.collection('registrations').document('REG-ORPHAN').set({
        'event_id': 'evt_gone', 'lead_name': 'Orphan', 'attendance': 'Pending', 'payment_status': 'Free'})
    token = generate_ticket_token('REG-ORPHAN', 'evt_gone', 'Orphan')
    with client.session_transaction() as sess:
        sess.update(user_id='coord@test.edu', role='EventCoordinator', category='General')
    for resp in (client.post('/ticket/api/checkin', json={'token': token}),
                 client.post(f'/ticket/verify/{token}'), client.post(f'/ticket/api/verify/{token}')):
        assert resp.status_code == 404
    assert mock_db.collection('registrations').document('REG-ORPHAN').get().to_dict()['attendance'] == 'Pending'


def test_another_events_ticket_is_refused_at_this_events_scanner(gate):
    d = gate
    other_event = _create_event(d['owner'], d['db'], _unique('Other Gate'), TODAY, fee=0, team=False)
    d['db'].collection('events').document(other_event).update({
        'staff': [{'name': 'In', 'email': d['people']['coord_in'], 'role': 'EventCoordinator'}]})
    reg_id, token = _registration(d, event_id=other_event)
    resp = _scan(d['staff'], token, d['event_id'])
    assert resp.status_code == 409 and resp.get_json()['status'] == 'wrong_event'
    assert _reg(d, reg_id)['attendance'] == 'Pending'


def test_the_kiosk_name_search_finds_by_name_team_member_and_usn_and_confirms_once(gate, monkeypatch):
    d = gate
    reg_id, _ = _registration(d, lead_name='Ravi Lead', team_name='Byte Busters', members=[
        {'name': 'Ravi Lead', 'usn': '1SN22CS101'}, {'name': 'Meera Member', 'usn': '1SN22CS102'}])
    for query in ('ravi', 'Byte Bus', 'meera', '1sn22cs102'):
        found = d['staff'].post('/checkin/kiosk/search', json={'event_id': d['event_id'], 'query': query})
        assert [to_uuid(r['reg_id']) for r in found.get_json()['results']] == [to_uuid(reg_id)], query

    monkeypatch.setattr(routes_ticket, '_now', lambda: '10:05:00')
    first = d['staff'].post(f'/checkin/kiosk/confirm/{reg_id}')
    assert first.status_code == 200 and first.get_json()['success'] is True
    again = d['staff'].post(f'/checkin/kiosk/confirm/{reg_id}')
    assert again.get_json()['already_present'] is True and again.get_json()['message'] == 'Already checked in at 10:05.'

    d['db'].collection('events').document(d['event_id']).update({'entry_fee': 150})
    unpaid_id, _ = _registration(d, payment_status='Pending')
    resp = d['staff'].post(f'/checkin/kiosk/confirm/{unpaid_id}')
    assert resp.status_code == 402 and resp.get_json()['success'] is False
    assert _reg(d, unpaid_id)['attendance'] == 'Pending'
