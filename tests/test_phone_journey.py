"""
tests/test_phone_journey.py — UPG-28: the student journey and the scanner on a
375px phone, in headless Chromium against the app on a local server.

The student logs in through the login form, finds an event, registers through
its form, opens the ticket, registers for a paid event and reaches the payment
page; a coordinator opens the scanner with the camera replaced by a stand-in
that "reads" the student's ticket QR, and the real check-in marks them
present; the student then opens the feedback form. Every page is measured at
375×812 and 1280×800: the page never scrolls sideways and no text, image or
control is cut off (UPG-23's measure). The certificate step is
tests/test_certificate_phone.py (UPG-132).

Screenshots go to $UPG28_SHOTS when it's set (outside git), else a temp dir.
"""
import datetime
import os

import pytest

from routes_ticket import generate_ticket_token
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user
from tests.test_shared_layout import BOOTSTRAP, DESKTOP_ONLY, MEASURE

PHONE = {'width': 375, 'height': 812}
DESKTOP = {'width': 1280, 'height': 800}

# Stands in for html5-qrcode (the CDN file is blocked): start() succeeds and keeps the decode callback,
# so the test can play "the camera read this QR"
FAKE_QR = """
window.Html5Qrcode = function (id) { this.id = id; };
Html5Qrcode.prototype.start = function (camera, config, onSuccess) {
  window.__decoded = onSuccess; window.__cameraStarted = true; return Promise.resolve();
};
Html5Qrcode.prototype.pause = function () {}; Html5Qrcode.prototype.resume = function () {};
Html5Qrcode.prototype.stop = function () { return Promise.resolve(); };
"""


@pytest.fixture
def journey(real_app, tmp_path):
    flask_app, db = real_app
    spoc, coord, student = (f"{_unique(k)}@test.edu" for k in ('jspoc', 'jcoord', 'jstudent'))
    _user(db, spoc, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    _user(db, student, 'Student', name='Jo Student')
    db.collection('users').document(student).update({'usn': '1SN20CS777', 'phone': '9876543210'})
    owner = _login(flask_app, spoc, 'ClubSPOC')
    today = datetime.date.today().isoformat()       # the scanner opens on the event day
    staff = [{'name': 'Cora', 'email': coord, 'role': 'EventCoordinator'}]
    free = _create_event(owner, db, _unique('Phone Talk'), today, team=False)
    paid = _create_event(owner, db, _unique('Phone Paid'), today, fee=150, team=False)
    for event_id in (free, paid):
        db.collection('events').document(event_id).update({'status': 'registration_open', 'staff': staff,
                                                           'reg_deadline': today})
    shots = os.environ.get('UPG28_SHOTS') or str(tmp_path / 'shots')
    os.makedirs(shots, exist_ok=True)
    return {'app': flask_app, 'db': db, 'free': free, 'paid': paid, 'coord': coord, 'student': student,
            'shots': shots}


def _routes(context, base):
    with open(BOOTSTRAP, 'rb') as f:
        bootstrap = f.read()

    def handle(route):
        url = route.request.url
        if url.startswith(base):
            return route.continue_()
        if 'bootstrap@5.3.3/dist/css' in url:
            return route.fulfill(status=200, body=bootstrap, content_type='text/css')
        return route.abort()                         # nothing leaves the machine
    context.route('**/*', handle)
    # The page loads html5-qrcode with an integrity hash, so a stand-in served in
    # its place would be refused: define it before any page script runs instead
    context.add_init_script(FAKE_QR)


def _login_in_browser(page, base, email, role):
    page.goto(f'{base}/login')
    # Volunteer, IQAC coordinator and department admin are off the menu
    # (UPG-204) but the server still accepts them, so for those roles the
    # test adds the option back and posts the same form
    if not page.locator(f'#roleSelect option[value="{role}"]').count():
        page.eval_on_selector('#roleSelect', '(el, r) => el.add(new Option(r, r))', role)
    page.select_option('#roleSelect', role)
    page.fill('#emailInput', email)
    page.fill('#passwordInput', PASSWORD)
    page.click('button[type=submit]')
    page.wait_for_load_state('load')
    assert '/login' not in page.url, page.url


# Headings readable against what's behind them: WCAG contrast of at least 3:1
# (large text) against the nearest ancestor with a solid background colour
CONTRAST = """() => {
  const rgb = c => (c.match(/[\\d.]+/g) || []).map(Number);
  const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const behind = el => { for (let a = el; a; a = a.parentElement) { const s = getComputedStyle(a);
      if (s.backgroundImage !== 'none') return null;           // an image or gradient: can't judge
      const c = rgb(s.backgroundColor); if (c.length === 3 || (c.length === 4 && c[3] >= 0.95)) return c.slice(0, 3); }
    return [255, 255, 255]; };
  return [...document.querySelectorAll('h1,h2,h3')].filter(h => h.getBoundingClientRect().height > 0 && h.innerText.trim())
    .map(h => { const bg = behind(h); if (!bg) return null; const fg = rgb(getComputedStyle(h).color).slice(0, 3);
      const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x); return [h.innerText.trim().slice(0, 40), (a + 0.05) / (b + 0.05)]; })
    .filter(x => x && x[1] < 3);
}"""


# A footer pinned to the bottom of the screen (site_footer_fixed) suits a page
# that fits the screen; on a longer page its text lands on the page's own text
UNDER_PINNED_FOOTER = """() => {
  const foot = document.querySelector('.site-footer--fixed');
  if (!foot || getComputedStyle(foot).position !== 'fixed') return [];
  const hits = new Set();
  for (const y of [0, document.documentElement.scrollHeight]) {
    window.scrollTo(0, y);
    const f = foot.getBoundingClientRect();
    for (const el of document.querySelectorAll('body *')) {
      if (foot.contains(el) || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      if (r.height && s.visibility !== 'hidden' && r.bottom > f.top + 2 && r.top < f.bottom - 2 && r.right > f.left && r.left < f.right)
        hits.add(el.innerText.trim().slice(0, 40));
    }
  }
  window.scrollTo(0, 0);
  return [...hits];
}"""


def _check(page, d, label, problems):
    """Measure the page as it is now at both widths, and screenshot both."""
    measure = MEASURE.replace('DESKTOP_ONLY', repr(DESKTOP_ONLY))
    for name, size in (('375', PHONE), ('1280', DESKTOP)):
        page.set_viewport_size(size)
        page.wait_for_timeout(150)
        seen = page.evaluate(measure)
        page.screenshot(path=os.path.join(d['shots'], f'{label}-{name}.png'), full_page=True)
        if seen['scrolled'] or seen['cut']:
            problems.append((label, name, seen['scrolled'], seen['cut']))
        covered = page.evaluate(UNDER_PINNED_FOOTER)
        if covered:
            problems.append((label, name, 'text under the pinned footer', covered[:4]))
        faint = page.evaluate(CONTRAST)
        if faint:
            problems.append((label, name, 'low-contrast headings', faint))
    page.set_viewport_size(PHONE)


def _fill_registration(page, d):
    for name, value in (('full_name', 'Jo Student'), ('phone', '9876543210'), ('usn', '1SN20CS777')):
        field = page.locator(f'form [name="{name}"]')
        if field.count() and field.first.is_editable() and not field.first.input_value():
            field.first.fill(value)
    page.check('[name="privacy_consent"]')


def test_the_student_journey_and_the_scanner_fit_a_phone(journey):
    from tests.headless import chromium, live_server
    d = journey
    problems = []
    p, browser = chromium()
    try:
        with live_server(d['app']) as server:
            base = server.url
            student_ctx = browser.new_context(viewport=PHONE)
            _routes(student_ctx, base)
            page = student_ctx.new_page()
            _login_in_browser(page, base, d['student'], 'Student')
            _check(page, d, '1-dashboard', problems)

            # Discover
            page.goto(f'{base}/events')
            _check(page, d, '2-events', problems)
            page.goto(f"{base}/event/{d['free']}")
            _check(page, d, '3-event', problems)

            # Register
            page.goto(f"{base}/forms/register/{d['free']}")
            _check(page, d, '4-register', problems)
            _fill_registration(page, d)
            page.click('form button[type=submit]')
            page.wait_for_load_state('load')
            _check(page, d, '5-registered', problems)
            regs = [r for r in d['db'].collection('registrations').where('event_id', '==', d['free']).stream()
                    if r.to_dict().get('lead_email') == d['student']]
            assert len(regs) == 1, 'the form registered the student'
            reg_id = regs[0].id

            # Ticket
            page.goto(f'{base}/ticket/{reg_id}')
            _check(page, d, '6-ticket', problems)

            # Pay (a paid event's form leads to the payment page)
            page.goto(f"{base}/forms/register/{d['paid']}")
            _fill_registration(page, d)
            page.click('form button[type=submit]')
            page.wait_for_load_state('load')
            assert f"/payment/checkout/{d['paid']}" in page.url, page.url
            _check(page, d, '7-pay', problems)

            # Check-in: the coordinator's scanner on a phone, the camera mocked
            coord_ctx = browser.new_context(viewport=PHONE)
            _routes(coord_ctx, base)
            scanner = coord_ctx.new_page()
            _login_in_browser(scanner, base, d['coord'], 'EventCoordinator')
            scanner.goto(f"{base}/coordinator/scan/{d['free']}")
            scanner.wait_for_function('() => window.__cameraStarted === true')
            _check(scanner, d, '8-scanner', problems)
            with d['app'].app_context():               # the token the ticket's QR carries
                token = generate_ticket_token(reg_id, d['free'], 'Jo Student')
            scanner.evaluate('token => window.__decoded(token)', token)
            scanner.wait_for_selector('#attendance-view:not(.d-none)')
            _check(scanner, d, '9-checked-in', problems)
            assert d['db'].collection('registrations').document(reg_id).get().to_dict()['attendance'] == 'Present'

            # Feedback
            page.goto(f'{base}/feedback/submit/{reg_id}')
            assert page.locator('form').count() >= 1
            _check(page, d, '10-feedback', problems)
    finally:
        browser.close()
        p.stop()
    assert problems == [], '\n'.join(map(str, problems))
