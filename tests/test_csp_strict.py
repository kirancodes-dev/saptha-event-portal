"""
tests/test_csp_strict.py — UPG-25: the CSP's script-src has a per-request nonce
and no 'unsafe-inline'; no template has an inline <script> without the nonce
or an on…= handler attribute (nor does any app script build one into HTML);
each role's key pages, loaded in headless Chromium under the CSP header the
app sent with them, report no CSP violation, and every data-h-* handler on
them is registered.
"""
import glob
import os
import re

from tests.test_shared_layout import _key_pages, roles  # noqa: F401  (fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, 'templates')


def _script_src(csp):
    return next((d.strip() for d in csp.split(';') if d.strip().startswith('script-src')), '')


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_script_src_has_a_nonce_and_no_unsafe_inline(real_app):
    flask_app, _ = real_app
    client = flask_app.test_client()
    first, second = (_script_src(client.get('/').headers['Content-Security-Policy']) for _ in range(2))
    assert first and "'unsafe-inline'" not in first and "'unsafe-eval'" not in first
    nonces = [re.search(r"'nonce-([^']+)'", s).group(1) for s in (first, second)]
    assert nonces[0] != nonces[1]                         # a fresh nonce for every response
    page = client.get('/login')
    nonce = re.search(r"'nonce-([^']+)'", page.headers['Content-Security-Policy']).group(1)
    inline = re.findall(r'<script\b(?![^>]*\bsrc=)([^>]*)>', page.get_data(as_text=True))
    assert all(f'nonce="{nonce}"' in attrs or 'application/json' in attrs or 'ld+json' in attrs for attrs in inline)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

HANDLER_ATTR = re.compile(r'''<[a-zA-Z][^<>]*?\s(on[a-z]+)\s*=\s*["']''', re.S)
NOT_RUN = re.compile(r'''type\s*=\s*["'](application/(ld\+)?json|text/template|text/x-template)''', re.I)


def test_no_template_has_an_inline_script_without_the_nonce_or_a_handler_attribute():
    bare, handlers = [], []
    for path in glob.glob(os.path.join(TEMPLATES, '**', '*.html'), recursive=True):
        name = os.path.relpath(path, TEMPLATES)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        for m in re.finditer(r'<script\b([^>]*)>', text, re.I):
            attrs = m.group(1)
            if re.search(r'\bsrc\s*=', attrs) or NOT_RUN.search(attrs):
                continue
            if 'nonce="{{ csp_nonce() }}"' not in attrs:
                bare.append(f'{name}:{text[:m.start()].count(chr(10)) + 1}')
        markup = re.sub(r'<script\b.*?</script>', '', text, flags=re.S | re.I)   # attributes, not script text
        handlers += [f'{name}: {m.group(1)}' for m in HANDLER_ATTR.finditer(markup)]
    assert bare == [] and handlers == []


def test_no_app_script_builds_an_inline_handler_into_html():
    found = []
    for path in glob.glob(os.path.join(ROOT, 'static', 'js', '**', '*.js'), recursive=True):
        if '.min.' in path or 'vendor' in path:
            continue
        with open(path, encoding='utf-8') as f:
            for n, line in enumerate(f, 1):
                if re.search(r'''<[a-z][^'"`]*\son[a-z]+\s*=\s*\\?["']''', line):
                    found.append(f'{os.path.relpath(path, ROOT)}:{n}')
    assert found == []


# ── Criterion 3 ─────────────────────────────────────────────────────────────

UNBOUND = """() => {
  const keys = new Set();
  for (const el of document.querySelectorAll('*'))
    for (const a of el.attributes)
      if (a.name.startsWith('data-h-') && !/^data-h-a\\d+$/.test(a.name)) keys.add(a.value);
  return [...keys].filter(k => typeof (window.SE_H || {})[k] !== 'function');
}"""


def _serve(html, csp):
    """The page as the app sent it, with its CSP header; /static from disk."""
    from tests.headless import _serve_static

    def handle(route):
        if route.request.resource_type == 'document':
            return route.fulfill(status=200, body=html, headers={
                'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': csp})
        return _serve_static(route)
    return handle


def test_key_pages_load_with_no_csp_violation_and_every_handler_bound(roles):  # noqa: F811
    from tests.headless import ORIGIN, chromium
    p, browser = chromium()
    problems, pages = [], 0
    try:
        for who, paths in _key_pages(roles).items():
            for path in paths:
                resp = roles['clients'][who].get(path)
                html, csp = resp.get_data(as_text=True), resp.headers['Content-Security-Policy']
                page = browser.new_page()
                violations = []
                page.on('console', lambda m, v=violations: v.append(m.text) if 'Content Security Policy' in m.text
                        or 'no handler registered' in m.text else None)

                page.route('**/*', _serve(html, csp))
                page.goto(ORIGIN + path, wait_until='load')
                page.wait_for_timeout(300)
                unbound = page.evaluate(UNBOUND)
                page.close()
                pages += 1
                if violations or unbound:
                    problems.append((who, path, violations[:3], unbound[:5]))
    finally:
        browser.close()
        p.stop()
    assert pages == sum(len(v) for v in _key_pages(roles).values()) >= 20
    assert problems == [], '\n'.join(map(str, problems))
