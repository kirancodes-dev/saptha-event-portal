"""
tests/test_entry_selection.py — UPG-214 on the real database layer: the SPOC
quietly chooses which registered teams may attend. With the event's entry list
on, only selected teams get in, through every way in (scanner, kiosk, self
check-in, the coordinator's and the admin's attendance marks); the team is
never told and hears nothing more; reports don't count them absent; the scan
screen keeps the list on the phone for offline scans.
"""
import datetime
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import services_entry
import utils_email
from routes_ticket import generate_ticket_token
from tests.test_checkin_security_real_db import _venue_code
from tests.test_integration_flow import _create_event, _login, _unique, _user

ROOT = Path(__file__).resolve().parent.parent
QUIET_WORDS = ('entry list', 'not selected', 'not on the', 'selected to attend')


@pytest.fixture
def gate(real_app, monkeypatch):
    flask_app, db = real_app
    emails = []
    monkeypatch.setattr(utils_email, 'send_email_notification',
                        lambda to, subject, message, event_name='': emails.append(to) or True)
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: emails.append(to) or True)
    spoc = f"{_unique('gspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()

    def event(**fields):
        event_id = _create_event(owner, db, _unique('Gate Cup'), day, team=True)
        db.collection('events').document(event_id).update(
            dict({'status': 'registration_open', 'venue': 'Hall A', 'member_confirm': False}, **fields))
        return event_id

    def register(event_id, team_name, usn='1SN22CS700'):
        lead, mate = f"{_unique('lead')}@test.edu", f"{_unique('mate')}@test.edu"
        _user(db, lead, 'Student', name=f'{team_name} Lead')
        client = _login(flask_app, lead, 'Student')
        resp = client.post(f'/forms/submit/{event_id}', data={
            'privacy_consent': 'yes', 'full_name': f'{team_name} Lead', 'email': lead, 'phone': '9876543210',
            'usn': usn, 'team_name': team_name,
            'member_1_name': 'Mo Mate', 'member_1_email': mate, 'member_1_usn': '1SN22CS701'})
        assert resp.status_code == 302, resp.data[:300]
        [reg_id] = [d.id for d in db.collection('registrations').where('event_id', '==', event_id).stream()
                    if d.to_dict().get('lead_email') == lead]
        return {'id': reg_id, 'lead': lead, 'mate': mate, 'client': client, 'name': team_name, 'usn': usn}

    def entry(event_id, action, client=None, **data):
        return (client or owner).post(f'/coordinator/registrations/{event_id}/entry',
                                      data=dict(data, action=action))

    def scan(event_id, team, client=None):
        with flask_app.app_context():
            token = generate_ticket_token(team['id'], event_id, team['name'] + ' Lead')
        return (client or owner).post('/ticket/api/checkin',
                                      json={'token': token, 'event_id': event_id, 'source': 'scan'})

    def reg(team):
        return db.collection('registrations').document(team['id']).get().to_dict()

    return {'app': flask_app, 'db': db, 'owner': owner, 'spoc': spoc, 'event': event, 'register': register,
            'entry': entry, 'scan': scan, 'reg': reg, 'emails': emails}


def _flashes(client):
    with client.session_transaction() as sess:
        return ' '.join(m for _c, m in sess.get('_flashes', []))


def _notices(db, *emails):
    return [n.to_dict() for n in db.collection('notifications_v2').stream()
            if n.to_dict().get('user_email') in emails]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_only_selected_teams_get_in_at_the_scanner_and_nobody_is_told(gate):
    g = gate
    db = g['db']
    eid = g['event']()
    a, b = g['register'](eid, _unique('Alpha')), g['register'](eid, _unique('Bravo'))
    notices_before = len(_notices(db, a['lead'], a['mate'], b['lead'], b['mate']))
    emails_before = list(g['emails'])

    # Off by default: everyone may enter
    assert services_entry.on(db.collection('events').document(eid).get().to_dict()) is False
    assert g['entry'](eid, 'switch', on='1').status_code == 302
    assert g['entry'](eid, 'select', reg_id=a['id']).status_code == 302

    refused = g['scan'](eid, b)
    assert refused.status_code == 409 and refused.get_json()['status'] == 'not_selected'
    assert refused.get_json()['message'] == services_entry.REFUSED
    assert g['reg'](b)['attendance'] != 'Present' and g['reg'](b)['entry_refused'] == 1
    assert any(x.to_dict().get('action') == 'CHECKIN_REFUSED' and b['id'] in x.to_dict().get('details', '')
               for x in db.collection('audit_log').stream())
    assert g['scan'](eid, a).status_code == 200 and g['reg'](a)['attendance'] == 'Present'

    # A team registering after the selection isn't on it
    c = g['register'](eid, _unique('Charlie'))
    assert g['scan'](eid, c).get_json()['status'] == 'not_selected'

    # Nobody is told: no notice, no email, and the team's own pages say nothing
    assert len(_notices(db, a['lead'], a['mate'], b['lead'], b['mate'])) == notices_before
    assert not set(g['emails'][len(emails_before):]) & {a['lead'], a['mate'], b['lead'], b['mate']}
    for path in ('/participant/dashboard', f"/ticket/{b['id']}"):
        page = b['client'].get(path)
        assert page.status_code == 200, path
        text = page.get_data(as_text=True).lower()
        assert not any(w in text for w in QUIET_WORDS), path

    # Turned off: every registered team may enter again
    g['entry'](eid, 'switch', on='0')
    assert g['scan'](eid, b).status_code == 200


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_only_the_hosting_spoc_may_choose_and_the_page_shows_it(gate):
    g = gate
    db, app = g['db'], g['app']
    eid = g['event']()
    a = g['register'](eid, _unique('Alpha'))
    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    coord = f"{_unique('coord')}@test.edu"
    _user(db, coord, 'EventCoordinator')
    db.collection('events').document(eid).update({'coordinators': [coord]})
    coord_c = _login(app, coord, 'EventCoordinator')
    for client in (_login(app, other, 'ClubSPOC'), coord_c):
        assert g['entry'](eid, 'switch', client=client, on='1').status_code == 403
        assert g['entry'](eid, 'select_all', client=client).status_code == 403
    assert services_entry.on(db.collection('events').document(eid).get().to_dict()) is False

    g['entry'](eid, 'switch', on='1', limit='40')
    owner_page = g['owner'].get(f'/coordinator/registrations/{eid}').get_data(as_text=True)
    for marker in ('data-entry-list', 'data-entry-switch', 'data-entry-tick', 'data-entry-actions',
                   'data-entry-state="not_selected"', 'Hall seats 40'):
        assert marker in owner_page, marker
    coord_page = coord_c.get(f'/coordinator/registrations/{eid}').get_data(as_text=True)
    assert 'data-entry-list' in coord_page and 'data-entry-state="not_selected"' in coord_page
    assert 'data-entry-tick' not in coord_page and 'data-entry-switch' not in coord_page
    assert a['name'] in coord_page


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_select_all_csv_shortlist_and_who_can_be_ticked(gate):
    g = gate
    db, owner = g['db'], g['owner']
    eid, elsewhere = g['event'](), g['event']()
    a, b, c = (g['register'](eid, _unique(n)) for n in ('Alpha', 'Bravo', 'Charlie'))
    stranger = g['register'](elsewhere, _unique('Stranger'))
    g['entry'](eid, 'switch', on='1', limit='1')

    g['entry'](eid, 'select_all')
    assert all(g['reg'](t)['entry_selected'] for t in (a, b, c))
    assert "more than the hall's 1 seats" in _flashes(owner)
    g['entry'](eid, 'unselect_all')
    assert not any(g['reg'](t).get('entry_selected') for t in (a, b, c))

    # Another event's team can't be ticked through this one
    g['entry'](eid, 'select', reg_id=stranger['id'])
    assert not g['reg'](stranger).get('entry_selected')

    # A CSV of team names and emails, with a header and a row that matches nothing
    csv = f"Team name,Email\n{a['name']},\n,{b['lead']}\nNobody Team,nobody@test.edu\n"
    import io
    owner.post(f'/coordinator/registrations/{eid}/entry',
               data={'action': 'csv', 'file': (io.BytesIO(csv.encode()), 'list.csv')},
               content_type='multipart/form-data')
    assert g['reg'](a)['entry_selected'] and g['reg'](b)['entry_selected'] and not g['reg'](c).get('entry_selected')
    assert 'Not found in this event: Nobody Team' in _flashes(owner)

    # Out of the competition: can't be ticked; the shortlist button takes it off
    db.collection('registrations').document(c['id']).update({'is_eliminated': True})
    g['entry'](eid, 'select', reg_id=c['id'])
    assert not g['reg'](c).get('entry_selected') and 'out of the competition' in _flashes(owner)
    g['entry'](eid, 'unselect_all')
    g['entry'](eid, 'shortlist')
    assert g['reg'](a)['entry_selected'] and g['reg'](b)['entry_selected'] and not g['reg'](c).get('entry_selected')

    # Checked in: stays on the list
    assert g['scan'](eid, a).status_code == 200
    g['entry'](eid, 'unselect', reg_id=a['id'])
    assert g['reg'](a)['entry_selected'] and 'already checked in' in _flashes(owner)

    # A paid team taken off: the SPOC is reminded about the refund (the team isn't told)
    db.collection('registrations').document(b['id']).update({'payment_status': 'Paid'})
    g['entry'](eid, 'unselect', reg_id=b['id'])
    assert not g['reg'](b)['entry_selected'] and 'ask the admin to refund' in _flashes(owner)

    # The filters
    selected = owner.get(f'/coordinator/registrations/{eid}?entry=selected').get_data(as_text=True)
    assert a['name'] in selected and b['name'] not in selected
    not_selected = owner.get(f'/coordinator/registrations/{eid}?entry=not_selected').get_data(as_text=True)
    assert b['name'] in not_selected and a['name'] not in not_selected
    paid = owner.get(f'/coordinator/registrations/{eid}?pay=paid').get_data(as_text=True)
    assert b['name'] in paid and a['name'] not in paid
    assert any(x.to_dict().get('action') == 'ENTRY_SELECTION' and eid in x.to_dict().get('details', '')
               for x in db.collection('audit_log').stream())


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_every_other_way_in_follows_the_list(gate):
    g = gate
    db, app = g['db'], g['app']
    eid = g['event']()
    a = g['register'](eid, _unique('Alpha'))
    g['entry'](eid, 'switch', on='1')
    db.collection('events').document(eid).update({'status': 'active', 'allow_self_checkin': True})

    # Self check-in: "see the desk", no reason given
    d = {'app': app}
    resp = a['client'].post(f'/checkin/{eid}/submit', data={'code': _venue_code(d, eid)})
    assert resp.status_code == 302 and services_entry.SEE_DESK in _flashes(a['client'])
    assert g['reg'](a).get('attendance') != 'Present'

    # The kiosk, the coordinator's tick and the admin's attendance setting
    kiosk = g['owner'].post(f"/checkin/kiosk/confirm/{a['id']}")
    assert kiosk.status_code == 409 and kiosk.get_json()['status'] == 'not_selected'
    tick = g['owner'].post('/coordinator/mark_attendance_granular',
                           json={'reg_id': a['id'], 'present_usns': [a['usn']]})
    assert tick.status_code == 409 and tick.get_json()['status'] == 'not_selected'
    admin = f"{_unique('admin')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    admin_c = _login(app, admin, 'SuperAdmin')
    admin_c.post(f"/admin/registrations/{a['id']}/attendance", data={'attendance': 'Present'})
    assert g['reg'](a).get('attendance') != 'Present' and 'entry list' in _flashes(admin_c)
    # Marking absent is still allowed
    admin_c.post(f"/admin/registrations/{a['id']}/attendance", data={'attendance': 'Absent'})
    assert g['reg'](a).get('attendance') == 'Absent'

    # Selected: self check-in works
    g['entry'](eid, 'select', reg_id=a['id'])
    resp = a['client'].post(f'/checkin/{eid}/submit', data={'code': _venue_code(d, eid)})
    assert g['reg'](a).get('attendance') == 'Present'


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_teams_not_on_the_list_hear_nothing_more(gate, monkeypatch):
    g = gate
    db, owner = g['db'], g['owner']
    import routes_coordinator
    import tasks.email_tasks
    import tasks.scheduled_tasks as jobs
    queued = []
    monkeypatch.setattr(tasks.email_tasks.send_ticket_email_task, 'delay', lambda **k: queued.append(k['to_email']))
    monkeypatch.setattr(tasks.email_tasks.send_generic_email_task, 'delay', lambda **k: queued.append(k['to_email']))
    broadcast = []
    monkeypatch.setattr(routes_coordinator, 'send_broadcast_email',
                        lambda to, subject, message, title='': broadcast.extend(to))
    eid = g['event']()
    a, b = g['register'](eid, _unique('Alpha')), g['register'](eid, _unique('Bravo'))
    g['entry'](eid, 'switch', on='1')
    g['entry'](eid, 'select', reg_id=a['id'])
    ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()

    # The day-before and 3-day reminders
    db.collection('events').document(eid).update({'status': 'active',
                                                  'date': (ist + datetime.timedelta(days=1)).isoformat()})
    jobs.send_24h_reminders()
    assert a['lead'] in queued and b['lead'] not in queued and b['mate'] not in queued
    queued.clear()
    db.collection('events').document(eid).update({'date': (ist + datetime.timedelta(days=3)).isoformat()})
    jobs.send_3day_reminders()
    assert a['lead'] in queued and b['lead'] not in queued

    # The SPOC's email blast and the coordinator's broadcast
    g['emails'].clear()
    owner.post(f'/spoc/blast_email/{eid}', data={'subject': 'Bring ID', 'body': 'Carry your ID.', 'audience': 'all'})
    assert a['lead'] in g['emails'] and b['lead'] not in g['emails']
    owner.post(f'/coordinator/broadcast/{eid}', data={'subject': 'Hall', 'message': 'Hall B.'})
    assert a['lead'] in broadcast and b['lead'] not in broadcast

    # A venue change: only the teams that may come are told
    import services_venue
    ev = db.collection('events').document(eid).get().to_dict()
    before = len(_notices(db, b['lead'], b['mate']))
    services_venue.notify_event_details_changed(db, event_id=eid, previous_data=ev,
                                                new_data=dict(ev, venue='Hall Z'))
    assert len(_notices(db, b['lead'], b['mate'])) == before
    assert _notices(db, a['lead'])


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_reports_and_exports_dont_count_them_absent(gate):
    g = gate
    db, owner = g['db'], g['owner']
    eid = g['event']()
    a, b, c = (g['register'](eid, _unique(n), usn=f'1SN22CS7{i}0') for i, n in enumerate(('Alpha', 'Bravo', 'Charlie')))
    g['entry'](eid, 'switch', on='1')
    g['entry'](eid, 'select', reg_id=[a['id'], c['id']])
    assert g['scan'](eid, a).status_code == 200

    import services_export
    report = services_export.event_report(db, eid)
    assert report['registered'] == 3 and report['present'] == 1 and report['not_selected'] == 1
    import io

    import openpyxl
    sheet = openpyxl.load_workbook(io.BytesIO(services_export.event_report_xlsx(db, eid))).worksheets[0]
    summary = {r[0]: r[1] for r in sheet.iter_rows(values_only=True) if r and r[0]}
    assert summary['Not selected to attend'] == 1 and summary['Attendance %'] == 50.0   # 1 of the 2 expected

    csv = owner.get(f'/coordinator/export_registrations/{eid}').get_data(as_text=True).splitlines()
    assert csv[0].endswith('Selected to attend')
    by_team = {line.split(',')[0]: line for line in csv[1:]}
    assert by_team[g['reg'](b).get('reg_id') or b['id']].endswith(',No')
    assert by_team[g['reg'](a).get('reg_id') or a['id']].endswith(',Yes')

    # The analytics page: B wasn't expected, so it's no no-show; C (selected, absent) is
    import services_insights
    past = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    event = dict(db.collection('events').document(eid).get().to_dict(), id=eid, date=past)
    regs = [dict(d.to_dict(), event_id=eid) for d in db.collection('registrations').where('event_id', '==', eid).stream()]
    [row] = [r for r in services_insights.build([event], regs)['events'] if r['id'] == eid]
    assert row['not_selected'] == 1 and row['no_show'] == 1 and row['attendance_rate'] == 50.0
    assert row['attended'] + row['no_show'] + row['upcoming'] + row['other'] == row['registered']

    # No participation certificate for a team that never got in
    cert = owner.get(f"/coordinator/certificate/{b['id']}/{b['usn']}")
    assert cert.status_code == 403

    # With the list off, the export has no such column
    g['entry'](eid, 'switch', on='0')
    assert not owner.get(f'/coordinator/export_registrations/{eid}').get_data(as_text=True) \
        .splitlines()[0].endswith('Selected to attend')


# ── Criterion 7 ─────────────────────────────────────────────────────────────

def test_the_scan_screen_shows_the_list_and_keeps_it_for_offline_scans(gate):
    g = gate
    db, app = g['db'], g['app']
    eid = g['event']()
    a, b = g['register'](eid, _unique('Alpha')), g['register'](eid, _unique('Bravo'))
    hud = g['owner'].get(f'/coordinator/scan-hud/{eid}').get_data(as_text=True)
    assert 'data-entry-hud hidden' in hud                      # off: nothing shown
    g['entry'](eid, 'switch', on='1')
    g['entry'](eid, 'select', reg_id=a['id'])
    g['scan'](eid, b)
    hud = g['owner'].get(f'/coordinator/scan-hud/{eid}').get_data(as_text=True)
    assert 'data-entry-hud' in hud and 'data-entry-hud hidden' not in hud
    assert 'Not On Entry List' in hud and 'offlineEntryBlocked' in hud

    data = g['owner'].get(f'/coordinator/scan-hud/{eid}/entry.json').get_json()
    assert data['on'] is True and data['selected'] == 1 and data['not_selected'] == 1 and data['refused'] == 1
    assert b['id'] in data['blocked'] and a['id'] not in data['blocked']
    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    assert _login(app, other, 'ClubSPOC').get(f'/coordinator/scan-hud/{eid}/entry.json').status_code == 403


def test_the_phone_turns_away_a_listed_ticket_offline(gate):
    """static/js/offline-sync.js itself, run in Node with the browser's globals."""
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js not installed')
    g = gate
    with g['app'].app_context():
        blocked = generate_ticket_token('reg-blocked-1', 'ev1', 'Bravo Lead')
        allowed = generate_ticket_token('reg-ok-2', 'ev1', 'Ä Lead with ünïcode')
    script = """
const vm = require('vm'); const fs = require('fs');
const store = {};
const ctx = { window: { addEventListener() {} }, localStorage: {
    getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
  atob, TextDecoder, Uint8Array, JSON, console, String, Array };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const w = ctx.window, [blocked, allowed] = JSON.parse(process.argv[2]);
const out = {};
out.before = w.offlineEntryBlocked(blocked, 'ev1');
w.saveEntryList('ev1', { on: true, blocked: ['reg-blocked-1'] });
out.token = w.offlineEntryBlocked(blocked, 'ev1');
out.link = w.offlineEntryBlocked('https://x.run.app/ticket/verify/' + blocked + '?s=1', 'ev1');
out.allowed = w.offlineEntryBlocked(allowed, 'ev1');
out.otherEvent = w.offlineEntryBlocked(blocked, 'ev2');
out.junk = w.offlineEntryBlocked('not a ticket', 'ev1');
w.saveEntryList('ev1', { on: false, blocked: ['reg-blocked-1'] });
out.off = w.offlineEntryBlocked(blocked, 'ev1');
console.log(JSON.stringify(out));
"""
    res = subprocess.run([node, '-e', script, str(ROOT / 'static/js/offline-sync.js'), json.dumps([blocked, allowed])],
                         capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == {'before': False, 'token': True, 'link': True, 'allowed': False,
                                      'otherEvent': False, 'junk': False, 'off': False}
