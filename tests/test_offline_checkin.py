"""
tests/test_offline_checkin.py — UPG-269: check-in keeps working at the door
without a connection, and what a phone keeps is safe.

Server (real database layer): a scan kept offline is recorded at the time and
on the day it was made; the first check-in to reach the server is the record,
whichever device made it. Browser (headless Chromium on the real scanner
page): a repeat and a wrong-event ticket are told apart offline; each kept
scan gets the server's answer in a report that stays; a scan the server can't
decide yet stays on the device; another account on the same phone can neither
see nor send the scans; signing out deletes them and the saved entry list.
"""
import datetime

import pytest

from routes_ticket import generate_ticket_token, scan_time
from tests import test_checkin_unified as _cu
from tests.test_integration_flow import _login

gate = _cu.gate   # today's event, an assigned coordinator, the owner
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _offline_scan(client, token, event_id, at):
    return client.post('/ticket/api/checkin', json={'token': token, 'event_id': event_id,
                                                    'source': 'offline queue', 'scanned_at': at})


# ── Criterion 1: the time the ticket was scanned ────────────────────────────

def test_a_scan_kept_offline_counts_for_the_day_it_was_made(gate):
    d = gate
    reg_id, token = _cu._registration(d)
    made = (datetime.datetime.now(IST) - datetime.timedelta(days=1)).replace(hour=23, minute=50, second=0, microsecond=0)
    resp = _offline_scan(d['staff'], token, d['event_id'], made.astimezone(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'))
    assert resp.status_code == 200 and resp.get_json()['status'] == 'success'
    reg = _cu._reg(d, reg_id)
    assert reg['attendance'] == 'Present' and reg['attendance_days'] == [made.date().isoformat()]
    assert reg['checkin_time'] == made.astimezone().strftime('%H:%M:%S')
    assert datetime.datetime.fromisoformat(reg['checkin_scanned_at']) == made
    assert reg['checkin_synced_at'] and reg['checked_in_by'] == d['people']['coord_in']

    # an online scan records no offline fields
    other, token2 = _cu._registration(d)
    assert _cu._scan(d['staff'], token2, d['event_id']).get_json()['status'] == 'success'
    assert 'checkin_scanned_at' not in _cu._reg(d, other)


@pytest.mark.parametrize('value', ['', 'yesterday', '2031-01-01T10:00:00Z', '2020-01-01T10:00:00Z',
                                   '2026-01-01T10:00:00'])
def test_a_time_that_cannot_be_believed_is_ignored(gate, value):
    d = gate
    assert scan_time(value) is None                 # missing, unreadable, future, too old, or without a zone
    reg_id, token = _cu._registration(d)
    assert _offline_scan(d['staff'], token, d['event_id'], value).get_json()['status'] == 'success'
    reg = _cu._reg(d, reg_id)
    assert reg['attendance_days'] == [datetime.datetime.now(IST).date().isoformat()]
    assert 'checkin_scanned_at' not in reg


# ── Criterion 2: two devices, one ticket ────────────────────────────────────

def test_the_first_check_in_to_reach_the_server_is_the_record(gate):
    d = gate
    reg_id, token = _cu._registration(d)
    earlier = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)).isoformat()

    # device B (the owner, online) checks the person in; device A scanned earlier but was offline
    assert _cu._scan(d['owner'], token, d['event_id']).get_json()['status'] == 'success'
    first = _cu._reg(d, reg_id)
    late = _offline_scan(d['staff'], token, d['event_id'], earlier)
    assert late.status_code == 200 and late.get_json()['status'] == 'already_in'
    assert late.get_json()['checkin_time'] == first['checkin_time']
    after = _cu._reg(d, reg_id)
    assert after['checked_in_by'] == d['people']['owner'] and after['checkin_time'] == first['checkin_time']
    assert after['attendance_days'] == first['attendance_days'] and 'checkin_scanned_at' not in after

    # the other way round: A's kept scan arrives first, B's later scan changes nothing
    reg2, token2 = _cu._registration(d)
    assert _offline_scan(d['staff'], token2, d['event_id'], earlier).get_json()['status'] == 'success'
    assert _cu._scan(d['owner'], token2, d['event_id']).get_json()['status'] == 'already_in'
    assert _cu._reg(d, reg2)['checked_in_by'] == d['people']['coord_in']
    present = [r for r in d['db'].collection('registrations').where('event_id', '==', d['event_id']).stream()
               if r.to_dict().get('attendance') == 'Present']
    assert len(present) == 2


# ── Criterion 3: the account key on the page ────────────────────────────────

def _key(html):
    import re
    return re.search(r'<meta name="checkin-staff" content="([^"]*)">', html).group(1)


def test_the_page_names_the_account_without_saying_who(gate):
    d = gate
    hud = f"/coordinator/scan-hud/{d['event_id']}"
    mine = _key(d['staff'].get(hud).get_data(as_text=True))
    assert len(mine) == 20 and mine == _key(d['staff'].get('/coordinator/scanner').get_data(as_text=True))
    assert d['people']['coord_in'] not in mine and d['people']['coord_in'].split('@')[0] not in mine
    assert _key(d['owner'].get(hud).get_data(as_text=True)) not in ('', mine)
    assert _key(d['app'].test_client().get('/login').get_data(as_text=True)) == ''
    with open(_cu.os.path.join(_cu.ROOT, 'static', 'js', 'offline-sync.js')) as fh:
        js = fh.read()
    for secret in ('SECRET_KEY', 'TICKET_SECRET', 'signature ==', 'hmac'):
        assert secret not in js             # nothing on the phone can sign or verify a ticket


# ── Criteria 4–7: the scanner page itself ───────────────────────────────────

def test_the_scanner_keeps_scans_safely_and_reports_what_the_server_said(gate):
    from tests.headless import chromium, live_server
    from tests.test_phone_journey import PHONE, _login_in_browser, _routes
    d = gate
    db, event_id = d['db'], d['event_id']
    regs = [_cu._registration(d) for _ in range(4)]
    with d['app'].app_context():
        elsewhere = generate_ticket_token('REG-elsewhere', 'another-event-id', 'Other Person')
    hud = f'/coordinator/scan-hud/{event_id}'
    p, browser = chromium()
    try:
        with live_server(d['app']) as server:
            ctx = browser.new_context(viewport=PHONE)
            _routes(ctx, server.url)
            page = ctx.new_page()
            dialogs = []
            page.on('dialog', lambda dlg: (dialogs.append(dlg.message), dlg.accept() if dialogs.count('accept') else dlg.dismiss()))

            def scan(token, title):
                page.evaluate('(t) => window.__decoded(t)', token)
                page.wait_for_selector('#feedback-banner.show')
                assert page.inner_text('#banner-title') == title, page.inner_text('#banner-msg')
                page.wait_for_selector('#feedback-banner:not(.show)')
                page.wait_for_timeout(100)

            def waiting():
                return page.evaluate('() => window.countOfflineCheckins()')

            def open_hud(email, role):
                ctx.clear_cookies()          # the phone changes hands without a sign-out
                _login_in_browser(page, server.url, email, role)
                page.goto(server.url + hud)
                page.wait_for_function('() => window.__cameraStarted === true')

            open_hud(d['people']['coord_in'], 'EventCoordinator')
            page.wait_for_timeout(300)

            # ── offline: kept, a repeat, a ticket for another event
            ctx.set_offline(True)
            scan(regs[0][1], 'Offline Check-In Queued')
            scan(regs[0][1], 'Already Scanned')
            scan(elsewhere, 'Wrong Event')
            scan(regs[1][1], 'Offline Check-In Queued')
            assert waiting() == 2 and page.inner_text('#sync-count') == '2'
            assert all(_cu._reg(d, r)['attendance'] == 'Pending' for r, _ in regs)
            kept = page.evaluate("""() => new Promise((done) => {
                const open = indexedDB.open('SapthaOfflineCheckin');
                open.onsuccess = () => { const all = open.result.transaction('pending_checkins').objectStore('pending_checkins').getAll();
                                         all.onsuccess = () => done(all.result); }; })""")
            assert [sorted(row) for row in kept] == [['eventId', 'id', 'queuedAt', 'staff', 'token']] * 2
            assert all(d['people']['coord_in'] not in str(row) for row in kept)

            # another device checks the second person in meanwhile
            assert _cu._scan(d['owner'], regs[1][1], event_id).get_json()['status'] == 'success'

            # ── back online: each kept scan gets the server's answer, and the report stays
            ctx.set_offline(False)
            page.wait_for_selector('#sync-report', state='visible')
            assert page.inner_text('#sync-report-title') == \
                'Offline scans sent: 1 checked in, 1 already in, 0 refused, 0 still waiting'
            rows = page.locator('#sync-report-list li').all_inner_texts()
            assert len(rows) == 2 and rows[0].startswith('Checked in') and rows[1].startswith('Already checked in')
            assert waiting() == 0
            first = _cu._reg(d, regs[0][0])
            assert first['attendance'] == 'Present' and first['checked_in_by'] == d['people']['coord_in']
            assert first['checkin_scanned_at']
            assert _cu._reg(d, regs[1][0])['checked_in_by'] == d['people']['owner']
            page.wait_for_timeout(2500)
            assert page.is_visible('#sync-report')              # not a toast: it stays until closed
            page.click('#sync-report-close')
            assert not page.is_visible('#sync-report')

            # ── a scan the server can't decide yet stays on the device
            ctx.set_offline(True)
            scan(regs[2][1], 'Offline Check-In Queued')
            db.collection('events').document(event_id).update({'staff': []})     # taken off the staff meanwhile
            ctx.set_offline(False)
            page.wait_for_selector('#sync-report', state='visible')
            assert 'still waiting' in page.inner_text('#sync-report-title') and '1 still waiting' in page.inner_text('#sync-report-title')
            assert waiting() == 1 and _cu._reg(d, regs[2][0])['attendance'] == 'Pending'
            db.collection('events').document(event_id).update({
                'staff': [{'name': 'In', 'email': d['people']['coord_in'], 'role': 'EventCoordinator'}]})

            # ── another account on the same phone: can't see or send it
            page.goto('about:blank')
            open_hud(d['people']['owner'], 'ClubSPOC')
            page.wait_for_selector('#other-scans', state='visible')
            assert page.inner_text('#other-scans-count') == '1 scan'
            assert waiting() == 0 and page.inner_text('#sync-count') == '0'
            page.wait_for_timeout(3600)                          # past the send that follows a page load
            assert _cu._reg(d, regs[2][0])['attendance'] == 'Pending'
            assert page.evaluate('() => window.countOtherOfflineCheckins()') == 1

            # ── the first account again: its scan is still there and is sent
            page.goto('about:blank')
            open_hud(d['people']['coord_in'], 'EventCoordinator')
            page.wait_for_selector('#sync-report', state='visible', timeout=15000)
            assert _cu._reg(d, regs[2][0])['attendance'] == 'Present'
            assert _cu._reg(d, regs[2][0])['checked_in_by'] == d['people']['coord_in']
            page.click('#sync-report-close')

            # ── signing out with a scan that can't be sent: asked first, then everything is deleted
            page.wait_for_function(f"() => !!localStorage.getItem('sapthaEntryList:{event_id}')")
            ctx.set_offline(True)
            scan(regs[3][1], 'Offline Check-In Queued')
            assert page.evaluate("() => window.signOutClearingOfflineData('/logout')") is False     # "Cancel"
            assert len(dialogs) == 1 and "1 check-in scan saved on this device hasn't reached the server" in dialogs[0]
            assert waiting() == 1
            dialogs.append('accept')
            page.evaluate("() => { window.__left = false; window.signOutClearingOfflineData('#signed-out').then((ok) => { window.__left = ok; }); }")
            page.wait_for_function('() => window.__left === true')
            assert waiting() == 0
            assert page.evaluate(f"() => localStorage.getItem('sapthaEntryList:{event_id}')") is None
            assert _cu._reg(d, regs[3][0])['attendance'] == 'Pending'

            # ── the ordinary log-out link goes through the same clearing
            ctx.set_offline(False)
            page.goto(server.url + '/coordinator/dashboard')
            page.evaluate(f"() => localStorage.setItem('sapthaEntryList:{event_id}', '{{}}')")
            page.click('a[href="/logout"]')
            page.wait_for_url(lambda url: '/coordinator' not in url)
            assert page.evaluate(f"() => localStorage.getItem('sapthaEntryList:{event_id}')") is None
            assert page.get_attribute('meta[name="checkin-staff"]', 'content') == ''
    finally:
        browser.close()
        p.stop()


def test_the_scanner_links_the_name_search_for_tickets_that_cannot_be_scanned(gate):
    d = gate
    page = d['staff'].get(f"/coordinator/scan-hud/{d['event_id']}").get_data(as_text=True)
    assert f'href="/checkin/kiosk?event_id={d["event_id"]}" data-find-by-name' in page
    assert _login(d['app'], d['people']['coord_in'], 'EventCoordinator').get(
        f"/checkin/kiosk?event_id={d['event_id']}").status_code == 200
