"""
tests/test_shared_layout.py — UPG-23 (a–h): every template a route renders
extends the shared document (templates/layouts/document.html, directly or via
base_classic.html, layouts/standalone.html or layouts/fullscreen.html); each
key page of each role answers 200 with the shared footer and its navigation;
at 375px no key page scrolls sideways and the headings and form fields seen at
1280px are still there.

The browser checks load each page as the app rendered it for that role, in
headless Chromium, with the page's /static files from disk and Bootstrap from
tests/fixtures (the exact file the templates load from jsDelivr: its SHA-384
must match their integrity attribute). Nothing leaves the machine.
"""
import base64
import datetime
import glob
import hashlib
import os
import re

import pytest

from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, 'templates')
BOOTSTRAP = os.path.join(ROOT, 'tests', 'fixtures', 'bootstrap-5.3.3.min.css')
DOCUMENT = 'layouts/document.html'


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def _rendered_templates():
    """Every template name a route module passes to render_template as a literal."""
    names = set()
    for path in glob.glob(os.path.join(ROOT, '*.py')):
        with open(path, encoding='utf-8') as f:
            names |= set(re.findall(r'''render_template\(\s*['"]([^'"]+\.html)['"]''', f.read()))
    return names


def _extends(name):
    with open(os.path.join(TEMPLATES, name), encoding='utf-8') as f:
        m = re.search(r'''{%-?\s*extends\s+['"]([^'"]+)['"]''', f.read())
    return m.group(1) if m else None


def _chain(name):
    chain = [name]
    while (parent := _extends(chain[-1])) and parent not in chain:
        chain.append(parent)
    return chain


# Not pages: HTML a page fetches and inserts (the home page's event popup asks
# /event/<id>?fragment=1 for this, UPG-92)
FRAGMENTS = {'public/event_fragment.html'}


def test_every_rendered_template_extends_the_shared_document():
    rendered = _rendered_templates() - FRAGMENTS
    assert len(rendered) > 100
    for name in FRAGMENTS:                       # a fragment has no document of its own
        with open(os.path.join(TEMPLATES, name), encoding='utf-8') as f:
            assert '<html' not in f.read().lower(), name
    missing = [n for n in rendered if not os.path.isfile(os.path.join(TEMPLATES, n))]
    assert missing == []
    outside = {n: _chain(n) for n in rendered if n != DOCUMENT and DOCUMENT not in _chain(n)}
    assert outside == {}


# ── Criterion 2 ─────────────────────────────────────────────────────────────

@pytest.fixture
def roles(real_app):
    flask_app, db = real_app
    people = {k: f"{_unique('lay' + k)}@test.edu" for k in ('spoc', 'coord', 'judge', 'student', 'admin')}
    for key, role in (('spoc', 'ClubSPOC'), ('coord', 'EventCoordinator'), ('judge', 'Judge'),
                      ('student', 'Student'), ('admin', 'SuperAdmin')):
        _user(db, people[key], role, name=f'Layout {key.title()}')
    spoc = _login(flask_app, people['spoc'], 'ClubSPOC')
    day = (datetime.date.today() + datetime.timedelta(days=12)).isoformat()
    event_id = _create_event(spoc, db, _unique('Layout Hack'), day, team=False)
    db.collection('events').document(event_id).update({
        'status': 'registration_open',
        'staff': [{'name': 'C', 'email': people['coord'], 'role': 'EventCoordinator'},
                  {'name': 'J', 'email': people['judge'], 'role': 'Judge'}]})
    student = _login(flask_app, people['student'], 'Student')
    student.post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes', 'full_name': 'Layout Student',
                                                    'email': people['student'], 'phone': '9876543210',
                                                    'usn': '1SN20CS321'})
    [reg] = db.collection('registrations').where('event_id', '==', event_id).stream()
    admin = flask_app.test_client()
    resp = admin.post('/login', data={'role': 'SuperAdmin', 'email': people['admin'], 'password': PASSWORD,
                                      'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert resp.status_code == 302 and resp.headers['Location'] != '/login'
    clients = {'anonymous': flask_app.test_client(), 'student': student, 'spoc': spoc, 'admin': admin,
               'coord': _login(flask_app, people['coord'], 'EventCoordinator'),
               'judge': _login(flask_app, people['judge'], 'Judge')}
    return {'clients': clients, 'event_id': event_id, 'reg_id': reg.id}


def _key_pages(d):
    e, r = d['event_id'], d['reg_id']
    return {
        'anonymous': ['/', '/events', f'/event/{e}', f'/forms/register/{e}', '/login', '/privacy', '/terms',
                      '/calendar'],
        'student': ['/participant/dashboard', '/participant/my_events', '/profile/', '/participant/ledger',
                    f'/ticket/{r}'],
        'spoc': ['/spoc/dashboard', '/spoc/create_event', f'/spoc/event/{e}/review'],
        'coord': ['/coordinator/dashboard', f'/coordinator/registrations/{e}'],
        'judge': ['/judge/dashboard'],
        'admin': ['/admin/dashboard', '/admin/users', '/admin/events', '/admin/registrations'],
    }


# The footer landmark with the privacy notice and terms: the shared one
# (includes/site_footer.html), or the home page's own (index.html)
FOOTER = re.compile(r'<footer\b[^>]*role="contentinfo"[^>]*>(?:(?!</footer>).)*href="/privacy"'
                    r'(?:(?!</footer>).)*href="/terms"', re.S)
# A way around: the app's navigation, or on a standalone page its Back link
# (includes/back_link.html, UPG-103; the ticket's own "Back to dashboard")
NAV = re.compile(r'<nav\b|role="navigation"|class="page-back-float|class="btn-back')


def test_each_key_page_answers_with_the_shared_footer_and_navigation(roles):
    problems = []
    for who, paths in _key_pages(roles).items():
        for path in paths:
            resp = roles['clients'][who].get(path)
            html = resp.get_data(as_text=True)
            if resp.status_code != 200:
                problems.append((who, path, resp.status_code))
            elif not FOOTER.search(html):
                problems.append((who, path, 'no shared footer'))
            elif not NAV.search(html):
                problems.append((who, path, 'no navigation'))
    assert problems == [], "\n".join(map(str, problems))


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_bootstrap_fixture_is_the_file_the_templates_load():
    with open(os.path.join(TEMPLATES, 'layouts', '_bootstrap_css.html'), encoding='utf-8') as f:
        tag = f.read()
    with open(BOOTSTRAP, 'rb') as f:
        digest = 'sha384-' + base64.b64encode(hashlib.sha384(f.read()).digest()).decode()
    assert 'bootstrap@5.3.3/dist/css/bootstrap.min.css' in tag and f'integrity="{digest}"' in tag


MEASURE = """() => {
  const vw = window.innerWidth;
  const visible = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  // Overflowing content is fine inside a box the user can scroll (a .table-responsive);
  // cut off by a box that hides it, or by the page edge, it's lost.
  // ...or inside a track that moves by itself (the home page's photo marquee, a CSS animation)
  const scrollable = el => { for (let a = el.parentElement; a && a !== document.documentElement; a = a.parentElement) {
      if (getComputedStyle(a).animationName !== 'none') return true;
      const o = getComputedStyle(a).overflowX;
      if (o === 'auto' || o === 'scroll') return a.getBoundingClientRect().right <= vw + 1;
      if (o !== 'visible') return false; }
    return false; };
  // What a person sees: text, images and controls (a row's negative gutter margin isn't content)
  const content = el => /^(IMG|SVG|INPUT|SELECT|TEXTAREA|BUTTON|VIDEO|CANVAS|IFRAME)$/i.test(el.tagName) ||
    [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  const cut = [...document.querySelectorAll('body *')].filter(el => {
      const r = el.getBoundingClientRect(); return content(el) && visible(el) && r.right > vw + 1 &&
        getComputedStyle(el).position !== 'fixed' && !scrollable(el); })
    .slice(0, 5).map(el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
                       (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\\s+/).join('.') : ''));
  window.scrollTo(10000, 0);
  const scrolled = window.scrollX;
  window.scrollTo(0, 0);
  const root = document.querySelector('main') || document.body;
  const desktopOnly = el => !!el.closest(DESKTOP_ONLY);
  return {
    scrolled, width: vw, cut,
    headings: [...root.querySelectorAll('h1,h2,h3')].filter(h => visible(h) && !desktopOnly(h))
                .map(h => h.innerText.trim()).filter(Boolean),
    fields: [...root.querySelectorAll('input:not([type=hidden]),select,textarea')].filter(f => visible(f) && !desktopOnly(f))
              .map(f => f.name || f.id).filter(Boolean),
  };
}"""

# Shown only on wide screens by design, with nothing a phone user needs: the
# login page's brand panel (static/css/global.css: .auth-info-panel)
DESKTOP_ONLY = '.auth-info-panel'

# Pages whose phone layout opens a panel with a tap (master/detail): what to tap
# before comparing. The SPOC dashboard shows its event list first on a phone and
# the overview after "Overview" (static/js/pages/spoc__dashboard.js).
PHONE_TAP = {'/spoc/dashboard': '#tour-global-btn'}


def _measure(browser, html, path, width):
    from tests.headless import ORIGIN, _serve_static
    with open(BOOTSTRAP, 'rb') as f:
        bootstrap = f.read()
    page = browser.new_page(viewport={'width': width, 'height': 900})
    try:
        def handle(route):
            url = route.request.url
            if route.request.resource_type == 'document' and url.split('?')[0] == ORIGIN + path.split('?')[0]:
                return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
            if 'bootstrap@5.3.3/dist/css/bootstrap.min.css' in url:
                return route.fulfill(status=200, body=bootstrap, content_type='text/css')
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        page.wait_for_timeout(300)
        measure = MEASURE.replace('DESKTOP_ONLY', repr(DESKTOP_ONLY))
        seen = page.evaluate(measure)
        if width < 600 and path in PHONE_TAP:       # a phone sees both views, one after the other
            page.click(PHONE_TAP[path])
            page.wait_for_timeout(200)
            other = page.evaluate(measure)
            seen = dict(other, headings=seen['headings'] + other['headings'], fields=seen['fields'] + other['fields'],
                        scrolled=max(seen['scrolled'], other['scrolled']), cut=seen['cut'] + other['cut'])
        return seen
    finally:
        page.close()


def test_key_pages_fit_a_375px_phone_and_lose_nothing(roles):
    from tests.headless import chromium
    p, browser = chromium()
    problems = []
    try:
        for who, paths in _key_pages(roles).items():
            for path in paths:
                html = roles['clients'][who].get(path).get_data(as_text=True)
                wide_screen = _measure(browser, html, path, 1280)
                phone = _measure(browser, html, path, 375)
                if phone['scrolled'] or phone['cut']:
                    problems.append((who, path, f"scrolls sideways {phone['scrolled']}px, cut off:", phone['cut']))
                lost_headings = [h for h in wide_screen['headings'] if h not in phone['headings']]
                lost_fields = [f for f in wide_screen['fields'] if f not in phone['fields']]
                if lost_headings or lost_fields:
                    problems.append((who, path, 'hidden at 375px', lost_headings, lost_fields))
    finally:
        browser.close()
        p.stop()
    assert problems == [], "\n".join(map(str, problems))
