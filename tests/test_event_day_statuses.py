"""
tests/test_event_day_statuses.py — UPG-43 on the real database layer: event-day
screens and jobs follow the event-day statuses (published, registration open or
closed, in progress, and the old `active`), never a cancelled event: the
coordinator's scanner list and walk-in form, venue self check-in, and the
day-before reminder through the cron endpoint.
"""
import datetime

from routes_checkin import _get_venue_serializer
from tests import test_notices
from tests.test_integration_flow import _login, _unique, _user
from tests.test_notices import CRON, _day, _to

site = test_notices.site
brevo = test_notices.brevo
offline = test_notices.offline
TODAY = datetime.date.today().isoformat()


def _coordinator(d, *event_ids):
    email = f"{_unique('daycoord')}@test.edu"
    _user(d['db'], email, 'EventCoordinator')
    for event_id in event_ids:
        d['db'].collection('events').document(event_id).update(
            {'staff': [{'name': 'C', 'email': email, 'role': 'EventCoordinator'}]})
    return _login(d['app'], email, 'EventCoordinator')


# ── Criteria 1 and 2 ────────────────────────────────────────────────────────

def test_the_scanner_list_and_walk_in_form_show_open_events_not_cancelled_ones(site):
    d = site
    (open_id, open_title), (gone_id, gone_title) = d['event'](TODAY), d['event'](TODAY, status='cancelled')
    coord = _coordinator(d, open_id, gone_id)
    scanner = coord.get('/coordinator/scanner').get_data(as_text=True)
    assert open_title in scanner and gone_title not in scanner
    walk_in = coord.get('/coordinator/on_spot').get_data(as_text=True)
    assert open_title in walk_in and gone_title not in walk_in


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_venue_self_check_in_works_while_running_and_not_when_cancelled(site):
    d = site
    (running_id, _), (gone_id, _) = d['event'](TODAY, status='in_progress'), d['event'](TODAY, status='cancelled')
    student = f"{_unique('selfin')}@test.edu"
    _user(d['db'], student, 'Student')
    for event_id in (running_id, gone_id):
        d['db'].collection('events').document(event_id).update({'allow_self_checkin': True})
        d['db'].collection('registrations').document(_unique('REG')).set({
            'event_id': event_id, 'lead_email': student, 'lead_name': 'Self In', 'status': 'Confirmed',
            'payment_status': 'Free', 'attendance': 'Pending'})
    client = _login(d['app'], student, 'Student')
    with d['app'].app_context():
        codes = {e: _get_venue_serializer().dumps({'event_id': e}) for e in (running_id, gone_id)}

    ok = client.post(f'/checkin/{running_id}/submit', data={'code': codes[running_id]})
    assert ok.status_code == 200
    [reg] = [r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', running_id).stream()]
    assert reg['attendance'] == 'Present'

    refused = client.post(f'/checkin/{gone_id}/submit', data={'code': codes[gone_id]})
    assert refused.status_code == 400 and refused.get_json()['error'] == 'This event is not running'
    assert client.get(f'/checkin/{gone_id}').status_code == 200   # the page says check-in is closed
    [gone] = [r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', gone_id).stream()]
    assert gone['attendance'] == 'Pending'


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_day_before_reminder_reaches_closed_registration_events_not_cancelled_ones(site, brevo):
    d = site
    closed_id, closed_title = d['event'](_day(1))
    gone_id, gone_title = d['event'](_day(1))
    keep, _ = d['register'](closed_id, 'keep')
    lost, _ = d['register'](gone_id, 'lost')
    d['db'].collection('events').document(closed_id).update({'status': 'registration_closed'})
    d['db'].collection('events').document(gone_id).update({'status': 'cancelled'})
    brevo.clear()
    resp = d['app'].test_client().post('/internal/cron/reminders', headers={'X-Cron-Secret': CRON})
    assert resp.status_code == 200
    assert [m['subject'] for m in _to(brevo, keep)] == [f'✅ Registered — {closed_title}']
    assert _to(brevo, lost) == []
