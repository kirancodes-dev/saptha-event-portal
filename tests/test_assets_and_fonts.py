"""
tests/test_assets_and_fonts.py — UPG-24: one Bootstrap (5.3.3), defined only in
the layout partials; every CDN script and stylesheet carries integrity and
crossorigin (Razorpay's checkout.js, changed in place by Razorpay with no
published hash, is the one exception); the only fonts are the three families
global.css uses, self-hosted, and that's all a page requests.
"""
import glob
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, 'templates')
FAMILIES = {'Inter', 'Plus Jakarta Sans', 'Outfit'}
FONT_FILES = {'Inter-latin-wght-normal.woff2', 'PlusJakartaSans-latin-wght-normal.woff2',
              'Outfit-latin-wght-normal.woff2'}
UNHASHED_OK = ('https://checkout.razorpay.com/',)


def _templates():
    for path in glob.glob(os.path.join(TEMPLATES, '**', '*.html'), recursive=True):
        with open(path, encoding='utf-8') as f:
            yield os.path.relpath(path, TEMPLATES), f.read()


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_one_bootstrap_defined_only_in_the_layout_partials():
    old, elsewhere = [], []
    for name, text in _templates():
        if 'bootstrap@5.3.0' in text or 'bootstrap/5.3.0' in text:
            old.append(name)
        if re.search(r'''(?:href|src)=["'][^"']*bootstrap[@/][\d.]+[^"']*\.(?:css|js)''', text) \
                and name not in ('layouts/_bootstrap_css.html', 'layouts/_bootstrap_js.html'):
            elsewhere.append(name)
    assert old == [] and elsewhere == []
    with open(os.path.join(TEMPLATES, 'layouts', '_bootstrap_css.html')) as f:
        css = f.read()
    with open(os.path.join(TEMPLATES, 'layouts', '_bootstrap_js.html')) as f:
        js = f.read()
    assert 'bootstrap@5.3.3/dist/css/bootstrap.min.css' in css and 'bootstrap@5.3.3/dist/js/' in js


# ── Criterion 2 ─────────────────────────────────────────────────────────────

TAG = re.compile(r'<(script|link)\b[^>]*>', re.I | re.S)


def _external(tag):
    attr = 'src' if tag.lower().startswith('<script') else 'href'
    m = re.search(rf'''\b{attr}\s*=\s*["'](https?:)?//([^"']+)["']''', tag, re.I)
    return m and ('https://' + m.group(2))


def test_every_cdn_script_and_stylesheet_has_integrity_and_crossorigin():
    unhashed, checked = [], 0
    for name, text in _templates():
        for m in TAG.finditer(text):
            tag = m.group(0)
            if m.group(1).lower() == 'link' and not re.search(r'''rel\s*=\s*["']stylesheet''', tag, re.I):
                continue
            url = _external(tag)
            if not url or url.startswith(UNHASHED_OK):
                continue
            checked += 1
            if not (re.search(r'\bintegrity\s*=\s*["\']sha(256|384|512)-', tag) and re.search(r'\bcrossorigin\b', tag)):
                unhashed.append(f'{name}: {url}')
    assert checked >= 5                                   # the partials and the pinned libraries
    assert unhashed == []


def test_razorpay_is_the_only_unhashed_script():
    seen = {m.group(0) for _, text in _templates() for m in re.finditer(r'https://checkout\.razorpay\.com/[^"\']+', text)}
    assert seen <= {'https://checkout.razorpay.com/v1/checkout.js'}


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_only_the_three_families_are_declared_and_nothing_loads_web_fonts():
    with open(os.path.join(ROOT, 'static', 'css', 'fonts.css')) as f:
        declared = set(re.findall(r"font-family:\s*'([^']+)'", f.read()))
    assert declared == FAMILIES
    assert {f for f in os.listdir(os.path.join(ROOT, 'static', 'fonts')) if f.endswith('.woff2')} == FONT_FILES
    sources = [text for _, text in _templates()]
    for css in glob.glob(os.path.join(ROOT, 'static', 'css', '*.css')):
        with open(css, encoding='utf-8') as f:
            sources.append(f.read())
    for text in sources:
        assert 'fonts.googleapis.com' not in text and 'fonts.gstatic.com' not in text
        for face in re.findall(r'@font-face\s*{([^}]*)}', text):
            family = re.search(r"font-family:\s*['\"]?([^;'\"]+)", face).group(1)
            assert family in FAMILIES or 'Font Awesome' in family, family


@pytest.mark.parametrize('path', ['/', '/login', '/events', '/privacy'])
def test_a_page_requests_only_the_self_hosted_fonts(real_app, path):
    from tests.headless import ORIGIN, _serve_static, chromium
    flask_app, _ = real_app
    html = flask_app.test_client().get(path).get_data(as_text=True)
    p, browser = chromium()
    fonts = []
    try:
        page = browser.new_page()
        page.on('request', lambda r: fonts.append(r.url) if r.resource_type == 'font'
                or 'fonts.g' in r.url else None)

        def handle(route):
            if route.request.resource_type == 'document':
                return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        page.wait_for_timeout(300)
    finally:
        browser.close()
        p.stop()
    own = {u.rsplit('/', 1)[-1] for u in fonts if u.startswith(ORIGIN + '/static/fonts/')}
    others = [u for u in fonts if not u.startswith(ORIGIN + '/static/fonts/')
              and 'fontawesome' not in u and 'font-awesome' not in u]
    assert own and own <= FONT_FILES and others == []
