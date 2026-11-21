"""
tests/test_late_checkin.py — UPG-378: check-in is open from the event's first
day to its last, in India (it was only the first day, by the server's clock),
and after the event the SPOC marks someone who came but wasn't scanned as
present, from the scan page's list, so the participation certificate counts
them. A cancelled team can't be marked; who marked whom is kept.
"""
import datetime

import pytest

import services_registration_state as rs
from tests.test_integration_flow import _create_event, _login, _unique, _user

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _day(offset):
    return (datetime.datetime.now(IST).date() + datetime.timedelta(days=offset)).isoformat()


# ── the window ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('first, last, key', [
    (1, 1, 'before'), (0, 0, 'open'), (-1, 0, 'open'), (-1, 1, 'open'), (-2, -1, 'over'), (-1, None, 'over'),
])
def test_the_checkin_window_runs_from_the_first_day_to_the_last_in_india(first, last, key):
    event = {'date': _day(first)}
    if last is not None:
        event['end_date'] = _day(last)
    window = rs.checkin_window(event)
    assert window['key'] == key
    assert window['first'] == rs.day_text(_day(first))


def test_an_event_without_a_date_is_open():
    assert rs.checkin_window({})['key'] == 'open'


# ── the SPOC's check-in ─────────────────────────────────────────────────────

@pytest.fixture
def spoc_event(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('lspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    client = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(client, db, _unique('Late Event'), _day(10), team=False)

    def register(name):
        email = f"{_unique('lstu')}@test.edu"
        assert flask_app.test_client().post(f'/forms/submit/{event_id}', data={
            'privacy_consent': 'yes', 'full_name': name, 'email': email, 'phone': '9876543210',
            'usn': '1SN21CS001'}).status_code == 302
        regs = [d for d in db.collection('registrations').where('event_id', '==', event_id).stream()
                if (d.to_dict() or {}).get('lead_email') == email]
        return regs[0].id

    def days(first, last):
        db.collection('events').document(event_id).update({'date': _day(first), 'end_date': _day(last), 'status': 'active'})

    def checkin(reg_id, **body):
        return client.post(f'/spoc/api/checkin/{event_id}/{reg_id}', json=body)

    def reg(reg_id):
        return db.collection('registrations').document(reg_id).get().to_dict()
    return {'app': flask_app, 'db': db, 'client': client, 'spoc': spoc, 'event_id': event_id,
            'register': register, 'days': days, 'checkin': checkin, 'reg': reg}


def test_day_two_of_a_two_day_event_checks_in(spoc_event):
    s = spoc_event
    rid = s['register']('Day Two')
    s['days'](-1, 0)
    resp = s['checkin'](rid)
    assert resp.status_code == 200 and resp.get_json()['status'] == 'success'
    assert s['reg'](rid)['attendance'] == 'Present'
    assert not s['reg'](rid).get('checkin_late')


def test_before_the_event_says_when_check_in_opens(spoc_event):
    s = spoc_event
    rid = s['register']('Too Early')
    s['days'](3, 4)
    resp = s['checkin'](rid)
    assert resp.status_code == 403
    assert resp.get_json()['message'] == f"Check-in opens on {rs.day_text(_day(3))}."
    assert s['reg'](rid).get('attendance') != 'Present'
    # asking for a late mark before the event changes nothing
    assert s['checkin'](rid, late=True).status_code == 403


def test_after_the_event_the_spoc_marks_present_and_the_certificate_counts_them(spoc_event):
    s = spoc_event
    rid = s['register']('Came Unscanned')
    s['days'](-2, -1)

    resp = s['checkin'](rid)                         # a plain scan after the event
    assert resp.status_code == 403 and 'Mark present' in resp.get_json()['message']
    assert s['reg'](rid).get('attendance') != 'Present'

    resp = s['checkin'](rid, late=True)
    body = resp.get_json()
    assert resp.status_code == 200 and body['status'] == 'success', body
    reg = s['reg'](rid)
    assert reg['attendance'] == 'Present' and reg['checkin_late'] is True and reg['checked_in_by'] == s['spoc']
    assert reg['attendance_days'] == [_day(-2), _day(-1)]   # both days, so the 80% rule counts them
    logs = [d.to_dict() for d in s['db'].collection('audit_log').stream()]
    assert any(l.get('action') == 'LATE_CHECKIN' and rid in l.get('details', '') and s['spoc'] in l.get('details', '')
               for l in logs)
    assert s['checkin'](rid, late=True).get_json()['status'] == 'already_in'

    import services_certificates as certs
    event = s['db'].collection('events').document(s['event_id']).get().to_dict()
    owed = certs.recipients(s['db'], s['event_id'], event)
    assert any(r.get('reg_id') == rid or r.get('registration_id') == rid or rid in str(r) for r in owed), owed


def test_a_cancelled_registration_cannot_be_marked_present(spoc_event):
    s = spoc_event
    rid = s['register']('Cancelled One')
    s['db'].collection('registrations').document(rid).update({'status': 'cancelled'})
    s['days'](-2, -1)
    resp = s['checkin'](rid, late=True)
    assert resp.status_code == 409 and 'cancelled' in resp.get_json()['message']
    assert s['reg'](rid).get('attendance') != 'Present'


def test_the_scan_page_after_the_event_offers_mark_present(spoc_event):
    s = spoc_event
    s['register']('Listed')
    s['days'](-2, -1)
    html = s['client'].get(f"/spoc/scan/{s['event_id']}").get_data(as_text=True)
    assert 'const CHECKIN_OVER    = true;' in html
    assert 'data-late-checkin-note' in html and f"/certificates/events/{s['event_id']}" in html
    assert 'data-checkin-over' in html and rs.day_text(_day(-1)) in html
    assert "'Mark present'" in html and 'late: true' in html

    s['days'](-1, 0)                                  # day two: the scanner is open, no late marks
    html = s['client'].get(f"/spoc/scan/{s['event_id']}").get_data(as_text=True)
    assert 'const CHECKIN_OVER    = false;' in html and 'Scanner locked' not in html
    assert 'data-late-checkin-note' not in html


def test_the_coordinator_scanner_is_open_on_day_two(spoc_event):
    s = spoc_event
    coord = f"{_unique('lcoord')}@test.edu"
    _user(s['db'], coord, 'EventCoordinator')
    assert s['client'].post(f"/spoc/assign_coordinator/{s['event_id']}", data={
        'coordinator_email': coord, 'coordinator_name': 'Cora'}).status_code == 302
    s['days'](-1, 0)
    html = _login(s['app'], coord, 'EventCoordinator').get(f"/coordinator/scan/{s['event_id']}").get_data(as_text=True)
    assert 'Scanner locked' not in html
    s['days'](-2, -1)
    html = _login(s['app'], coord, 'EventCoordinator').get(f"/coordinator/scan/{s['event_id']}").get_data(as_text=True)
    assert 'Scanner locked' in html and 'ask the event' in html
