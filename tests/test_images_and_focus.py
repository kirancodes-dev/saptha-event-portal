"""
tests/test_images_and_focus.py — UPG-27: static/img stays under 1.5 MB; every
<img> in the templates (and any the app's scripts build) has alt; on the key
pages, every image below the first screen (1280×800) loads lazily; global.css
defines a :focus-visible style, and a keyboard user sees a focus outline.
"""
import glob
import os
import re

from tests.test_shared_layout import BOOTSTRAP, _key_pages, roles  # noqa: F401  (fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_static_img_is_under_1_5_mb():
    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, files in os.walk(os.path.join(ROOT, 'static', 'img'))
                for f in files)
    assert 0 < total < 1.5 * 1024 * 1024


# ── Criterion 2 ─────────────────────────────────────────────────────────────

IMG = re.compile(r'<img\b[^>]*>', re.I | re.S)


def test_every_template_image_has_alt():
    missing = []
    for path in glob.glob(os.path.join(ROOT, 'templates', '**', '*.html'), recursive=True):
        with open(path, encoding='utf-8') as f:
            for tag in IMG.findall(f.read()):
                if not re.search(r'\balt\s*=', tag):
                    missing.append(f"{os.path.relpath(path, ROOT)}: {tag[:80]}")
    assert missing == []


def test_every_image_the_app_scripts_build_has_alt():
    missing = []
    for path in glob.glob(os.path.join(ROOT, 'static', 'js', '**', '*.js'), recursive=True):
        if '.min.' in path or 'vendor' in path:
            continue
        with open(path, encoding='utf-8') as f:
            for n, line in enumerate(f, 1):
                if line.lstrip().startswith(('*', '//', '/*')):      # comments that mention an <img>
                    continue
                for tag in re.findall(r'<img\b[^>]*>', line):
                    if 'alt=' not in tag:
                        missing.append(f'{os.path.relpath(path, ROOT)}:{n}')
    assert missing == []


BELOW_THE_FOLD = """() => [...document.images]
  .filter(img => { const r = img.getBoundingClientRect(), s = getComputedStyle(img);
                   return r.width > 0 && r.height > 0 && s.display !== 'none' && r.top + window.scrollY >= innerHeight; })
  .filter(img => img.getAttribute('loading') !== 'lazy')
  .map(img => (img.getAttribute('src') || '').slice(0, 60))"""


def test_images_below_the_first_screen_load_lazily(roles):  # noqa: F811
    from tests.headless import ORIGIN, _serve_static, chromium
    d = roles
    # A sponsor logo and a banner, so the event page shows images further down
    import models
    models.db.collection('events').document(d['event_id']).update({
        'sponsors': [{'name': 'Acme Labs', 'logo_url': '/static/img/email-logo.png', 'tier': 'Gold'}],
        'banner_url': '/static/img/event_slide1.webp'})
    with open(BOOTSTRAP, 'rb') as f:
        bootstrap = f.read()
    p, browser = chromium()
    problems, below = [], 0
    try:
        for who, paths in _key_pages(d).items():
            for path in paths:
                html = d['clients'][who].get(path).get_data(as_text=True)
                page = browser.new_page(viewport={'width': 1280, 'height': 800})
                page.route('**/*', _serving(html, bootstrap, _serve_static))
                page.goto(ORIGIN + path, wait_until='load')
                page.wait_for_timeout(200)
                below += page.evaluate("() => [...document.images].filter(i => i.getBoundingClientRect().top"
                                       " + scrollY >= innerHeight && i.getBoundingClientRect().height > 0).length")
                eager = page.evaluate(BELOW_THE_FOLD)
                page.close()
                if eager:
                    problems.append((who, path, eager))
    finally:
        browser.close()
        p.stop()
    assert below >= 3                                      # the check saw images below the fold
    assert problems == [], '\n'.join(map(str, problems))


def _serving(html, bootstrap, serve_static):
    def handle(route):
        if route.request.resource_type == 'document':
            return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html'})
        if 'bootstrap@5.3.3/dist/css' in route.request.url:
            return route.fulfill(status=200, body=bootstrap, content_type='text/css')
        return serve_static(route)
    return handle


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_global_css_defines_a_focus_visible_style():
    with open(os.path.join(ROOT, 'static', 'css', 'global.css'), encoding='utf-8') as f:
        css = f.read()
    rule = re.search(r'(?m)^:focus-visible\s*{([^}]*)}', css)
    assert rule and re.search(r'outline\s*:\s*(?!none)[^;]+', rule.group(1))


def test_a_keyboard_user_sees_where_the_focus_is(real_app):
    from tests.headless import ORIGIN, _serve_static, chromium
    flask_app, _ = real_app
    with open(BOOTSTRAP, 'rb') as f:
        bootstrap = f.read()
    html = flask_app.test_client().get('/login').get_data(as_text=True)
    p, browser = chromium()
    try:
        page = browser.new_page()
        page.route('**/*', _serving(html, bootstrap, _serve_static))
        page.goto(ORIGIN + '/login', wait_until='load')
        seen = []
        for _ in range(6):                                  # tab through the first few controls
            page.keyboard.press('Tab')
            seen.append(page.evaluate("""() => { const el = document.activeElement, s = getComputedStyle(el);
                return [el.tagName, s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0 || s.boxShadow !== 'none'];
            }"""))
    finally:
        browser.close()
        p.stop()
    focused = [s for s in seen if s[0] not in ('BODY', 'HTML')]
    assert focused and all(visible for _, visible in focused), seen
