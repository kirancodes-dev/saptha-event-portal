"""
tests/test_reach_and_reports_phone.py — the browser pass for UPG-144 to
UPG-146, in headless Chromium against the app on a local server, each page
measured at 375px and 1280px (UPG-23's measure): the IQAC report flow (the
organiser fills and submits a report, the IQAC coordinator sees it and runs
the builder), the impact dashboard, the open-events page, and a student from
another college registering for an open event.
"""
import datetime

import pytest
from werkzeug.security import generate_password_hash

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user
from tests.test_phone_journey import PHONE, _check, _login_in_browser, _routes


@pytest.fixture
def world(real_app, tmp_path):
    import os
    flask_app, db = real_app
    people = {k: f"{_unique('ph' + k)}@test.edu" for k in ('spoc', 'iqac', 'admin')}
    _user(db, people['spoc'], 'ClubSPOC')
    _user(db, people['admin'], 'SuperAdmin')
    db.collection('users').document(people['iqac']).set({'name': 'Iqbal IQAC', 'role': 'IQACCoordinator',
                                                         'password': generate_password_hash(PASSWORD)})
    owner = _login(flask_app, people['spoc'], 'ClubSPOC')
    held = (datetime.date.today() - datetime.timedelta(days=9)).isoformat()
    past = _create_event(owner, db, _unique('Phone Seminar'), '2031-01-01', team=False)
    db.collection('events').document(past).update({'status': 'completed', 'date': held, 'end_datetime': held,
                                                   'end_date': '', 'department': 'Computer Science', 'staff': []})
    upcoming = _create_event(owner, db, _unique('Phone Open Hack'),
                             (datetime.date.today() + datetime.timedelta(days=12)).isoformat(), team=False)
    db.collection('events').document(upcoming).update({'status': 'registration_open', 'audience': 'open',
                                                       'allowed_participants': ['student', 'external']})
    shots = os.environ.get('CERT_SHOTS') or str(tmp_path / 'shots')
    os.makedirs(shots, exist_ok=True)
    return {'app': flask_app, 'db': db, 'people': people, 'past': past, 'upcoming': upcoming, 'shots': shots}


def test_reports_impact_open_events_and_an_external_registration_fit_both_widths(world):
    from tests.headless import chromium, live_server
    d = world
    problems = []
    p, browser = chromium()
    try:
        with live_server(d['app']) as server:
            base = server.url

            # The organiser fills and submits the NAAC report
            ctx = browser.new_context(viewport=PHONE)
            _routes(ctx, base)
            page = ctx.new_page()
            _login_in_browser(page, base, d['people']['spoc'], 'ClubSPOC')
            page.goto(f"{base}/naac/events/{d['past']}/report")
            _check(page, d, 'naac-1-report', problems)
            page.fill('#f-objectives', 'Introduce applied AI')
            page.fill('#f-summary', 'Two expert talks and a hands-on session.')
            page.fill('#f-outcomes', 'Students built a small classifier.')
            page.fill('#f-resource_name', 'Dr. R. Rao')
            page.click('button[name=action][value=submit]')
            page.wait_for_load_state('load')
            assert 'Report submitted' in page.content()

            # The IQAC coordinator sees no missing report for it and runs the builder
            iqac = browser.new_context(viewport=PHONE)
            _routes(iqac, base)
            ipage = iqac.new_page()
            _login_in_browser(ipage, base, d['people']['iqac'], 'IQACCoordinator')
            assert '/naac/' in ipage.url
            _check(ipage, d, 'naac-2-iqac', problems)
            ipage.goto(f'{base}/naac/report')
            assert 'Summary by NAAC category' in ipage.content()
            _check(ipage, d, 'naac-3-builder', problems)

            # The Super Admin's impact dashboard
            admin = browser.new_context(viewport=PHONE)
            _routes(admin, base)
            apage = admin.new_page()
            apage.goto(f'{base}/login')
            apage.select_option('#roleSelect', 'SuperAdmin')
            apage.fill('#emailInput', d['people']['admin'])
            apage.fill('#passwordInput', PASSWORD)
            apage.fill('#secretKeyInput', d['app'].config.get('MASTER_SECRET_KEY', ''))
            apage.click('button[type=submit]')
            apage.wait_for_load_state('load')
            apage.goto(f'{base}/impact/dashboard')
            assert 'Per year' in apage.content()
            _check(apage, d, 'impact-1-dashboard', problems)

            # Open events, and a student from another college registers
            guest = browser.new_context(viewport=PHONE)
            _routes(guest, base)
            gpage = guest.new_page()
            gpage.goto(f'{base}/open-events')
            assert 'Phone Open Hack' in gpage.content()
            _check(gpage, d, 'open-1-list', problems)
            gpage.goto(f"{base}/forms/register/{d['upcoming']}")
            _check(gpage, d, 'open-2-form', problems)
            gpage.check('input[name=participant_type][value=external]')
            gpage.fill('#designation', 'Student')
            gpage.fill('#institution', 'RV College of Engineering')
            for name, value in (('full_name', 'Gita Guest'), ('email', f"{_unique('gita')}@other.edu"),
                                ('phone', '9876501112')):
                field = gpage.locator(f'form [name="{name}"]')
                if field.count():
                    field.first.fill(value)
            gpage.check('[name="privacy_consent"]')
            gpage.click('form button[type=submit]')
            gpage.wait_for_load_state('load')
            _check(gpage, d, 'open-3-registered', problems)
    finally:
        browser.close()
        p.stop()
    regs = [r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', d['upcoming']).stream()]
    assert [(r['participant_type'], r['institution']) for r in regs] == [('external', 'RV College of Engineering')]
    assert problems == []
