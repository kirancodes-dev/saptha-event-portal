"""
tests/test_frontend_errors.py — UPG-60: in headless Chromium, with the app's
own static files and the real CDN libraries (integrity-checked copies,
tests/headless.py), no key page and none of the pages UPG-60 fixed logs a page
error or asks for a /static/ file that doesn't exist.
"""
import os

from tests.headless import STATIC, cdn_stand_ins
from tests.test_shared_layout import _key_pages, roles  # noqa: F401  (fixture)


def _pages(d):
    pages = _key_pages(d)
    e = d['event_id']
    pages['spoc'] += [f'/spoc/round_panel/{e}', f'/spoc/ai_report/{e}', f'/tournament/{e}']
    pages['admin'] += ['/admin/payments', '/admin/audit_log']
    pages['anonymous'] += [f'/tournament/fixtures/{e}', '/verify']
    return pages


def test_no_page_logs_an_error_or_a_missing_static_file(roles):  # noqa: F811
    from tests.headless import ORIGIN, chromium
    d = roles
    cdn = cdn_stand_ins()
    p, browser = chromium()
    problems, loaded = [], 0
    try:
        for who, paths in _pages(d).items():
            for path in paths:
                resp = d['clients'][who].get(path)
                if resp.status_code != 200:
                    problems.append((who, path, f'status {resp.status_code}'))
                    continue
                html = resp.get_data(as_text=True)
                errors, missing = [], []
                page = browser.new_page()
                page.on('pageerror', lambda e, errors=errors: errors.append(str(e)[:200]))
                page.route('**/*', _serve(html, cdn, missing))
                page.goto(ORIGIN + path, wait_until='load')
                page.wait_for_timeout(400)
                page.close()
                loaded += 1
                if errors or missing:
                    problems.append((who, path, errors[:3], missing[:5]))
    finally:
        browser.close()
        p.stop()
    assert loaded >= 28
    assert problems == [], '\n'.join(map(str, problems))


def _serve(html, cdn, missing):
    from tests.headless import _serve_static

    def handle(route):
        url = route.request.url
        if route.request.resource_type == 'document':
            return route.fulfill(status=200, body=html, headers={'Content-Type': 'text/html; charset=utf-8'})
        if url in cdn:
            body, ctype = cdn[url]
            return route.fulfill(status=200, body=body, content_type=ctype,
                                 headers={'Access-Control-Allow-Origin': '*'})
        path = url.split('://', 1)[-1].split('/', 1)[-1].split('?')[0]
        if url.startswith('http://localhost/static/') and not os.path.isfile(os.path.join(STATIC, path[len('static/'):])):
            missing.append('/' + path)
        return _serve_static(route)
    return handle
