"""
tests/test_privacy_rights.py — UPG-22 on the real database layer: consent is
required at registration and stored with time and notice version; a person's
data export holds only their own data (a team member sees nothing of the lead
or others, aliases included); deletion can be scheduled and cancelled, and the
cron clean-up carries out only due requests, after which the person can't log
in and their registrations hold no name, email or phone; shared-layout pages
link the privacy notice.
"""
import datetime
import json

import pytest

from services_privacy import PRIVACY_NOTICE_VERSION
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

CRON = 'cron-secret-for-pytest'


@pytest.fixture
def site(real_app, monkeypatch):
    flask_app, db = real_app
    monkeypatch.setenv('CRON_SECRET', CRON)
    spoc = f"{_unique('privspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (datetime.date.today() + datetime.timedelta(days=15)).isoformat()

    def event(team=False):
        event_id = _create_event(owner, db, _unique('Privacy Day'), day, team=team)
        db.collection('events').document(event_id).update({'status': 'registration_open'})
        return event_id
    return {'app': flask_app, 'db': db, 'event': event}


def _regs(d, event_id):
    return [r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_registration_needs_consent_and_stores_it_with_time_and_version(site):
    d = site
    event_id = d['event']()
    form = {'full_name': 'Con Sent', 'email': f"{_unique('consent')}@test.edu", 'phone': '9876543210', 'usn': '1SN20CS016'}
    client = d['app'].test_client()
    refused = client.post(f'/forms/submit/{event_id}', data=form, follow_redirects=True)
    assert 'register you without it' in refused.get_data(as_text=True) and _regs(d, event_id) == []
    client.post(f'/forms/submit/{event_id}', data={**form, 'privacy_consent': 'yes'})
    [reg] = _regs(d, event_id)
    assert reg['privacy_consent']['version'] == PRIVACY_NOTICE_VERSION and reg['privacy_consent']['at']


# ── Criterion 2 and the member view ────────────────────────────────────────

def test_the_export_holds_only_the_persons_own_data(site):
    d = site
    event_id, solo_id = d['event'](team=True), d['event']()
    lead, member, stranger = (f"{_unique(k)}@test.edu" for k in ('privlead', 'privmember', 'stranger'))
    _user(d['db'], member, 'Student')
    d['app'].test_client().post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Lena Lead', 'email': lead, 'phone': '9111111111', 'usn': '1SN20CS017',
        'team_name': 'Quiet Team', 'member_1_name': 'Manu Member', 'member_1_email': member, 'member_1_usn': '1SN20CS018'})
    d['app'].test_client().post(f'/forms/submit/{solo_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Sam Stranger', 'email': stranger, 'phone': '9222222222', 'usn': '1SN20CS019'})

    resp = _login(d['app'], member, 'Student').post('/compliance/export-data')
    assert resp.status_code == 200
    data = json.loads(resp.get_data(as_text=True))
    dump = json.dumps(data)
    assert member in dump and 'Quiet Team' in dump
    for other in (lead, 'Lena Lead', '9111111111', stranger, 'Sam Stranger', '9222222222'):
        assert other not in dump, other
    assert 'password' not in json.dumps(data.get('profile', {})).lower()


# ── Criterion 3, the cancel path and "only due requests" ───────────────────

def test_deletion_can_be_cancelled_and_the_cleanup_only_does_due_requests(site):
    d = site
    event_id = d['event']()
    gone, waiting = f"{_unique('gone')}@test.edu", f"{_unique('waiting')}@test.edu"
    for email, name in ((gone, 'Gina Gone'), (waiting, 'Will Wait')):
        _user(d['db'], email, 'Student')
        d['app'].test_client().post(f'/forms/submit/{event_id}', data={
            'privacy_consent': 'yes', 'full_name': name, 'email': email, 'phone': '9333333333', 'usn': '1SN20CS020'})
    gone_client, waiting_client = _login(d['app'], gone, 'Student'), _login(d['app'], waiting, 'Student')

    def pending(email):
        return [r for r in (x.to_dict() for x in d['db'].collection('deletion_requests').stream())
                if r.get('email') == email and r.get('status') == 'pending']

    gone_client.post('/compliance/delete-request', data={})                 # no confirmation: nothing
    assert pending(gone) == []
    gone_client.post('/compliance/delete-request', data={'confirm': 'yes'})
    assert len(pending(gone)) == 1
    gone_client.post('/compliance/cancel-deletion', data={})                # the cancel path
    assert pending(gone) == []
    gone_client.post('/compliance/delete-request', data={'confirm': 'yes'})
    waiting_client.post('/compliance/delete-request', data={'confirm': 'yes'})

    # Only the first one's grace period has ended
    past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
    for doc in d['db'].collection('deletion_requests').stream():
        if (doc.to_dict() or {}).get('email') == gone and doc.to_dict().get('status') == 'pending':
            d['db'].collection('deletion_requests').document(doc.id).update({'scheduled_deletion_at': past})
    assert d['app'].test_client().post('/internal/cron/cleanup', headers={'X-Cron-Secret': CRON}).status_code == 200

    login = d['app'].test_client().post('/login', data={'role': 'Student', 'email': gone, 'password': PASSWORD})
    assert login.headers['Location'] == '/login'                              # can't log in
    names = [r.get('lead_name') for r in _regs(d, event_id)]
    assert 'Gina Gone' not in names and 'Will Wait' in names
    leftovers = json.dumps(_regs(d, event_id))
    assert gone not in leftovers and 'Gina Gone' not in leftovers
    assert len(pending(waiting)) == 1                                          # not due: untouched
    assert d['db'].collection('users').document(waiting).get().exists


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_shared_layout_pages_link_the_privacy_notice(site):
    d = site
    student = f"{_unique('footer')}@test.edu"
    _user(d['db'], student, 'Student')
    client = _login(d['app'], student, 'Student')
    for path in ('/events', '/participant/dashboard', '/participant/my_events', '/profile/', '/calendar'):
        page = client.get(path).get_data(as_text=True)
        assert 'href="/privacy"' in page, path
    assert d['app'].test_client().get('/privacy').status_code == 200
