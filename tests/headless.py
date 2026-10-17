"""
tests/headless.py — run a page the app rendered in headless Chromium and
collect its script errors and CSP violations (UPG-67, UPG-70, UPG-72).

The page's own /static files are served from disk; every other request
(CDNs, the network) is blocked, so a test never leaves the machine. Tests that
use it skip when Playwright or its Chromium isn't installed
(`pip install playwright && python -m playwright install chromium`).
"""
import mimetypes
import os
from urllib.parse import urlparse

import pytest

ORIGIN = 'http://localhost'
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')


def chromium():
    sync_api = pytest.importorskip('playwright.sync_api')
    try:
        p = sync_api.sync_playwright().start()
        browser = p.chromium.launch()
    except Exception as exc:   # browser not downloaded
        pytest.skip(f'headless Chromium unavailable: {exc}')
    return p, browser


def _serve_static(route):
    path = urlparse(route.request.url).path
    if path.startswith('/static/'):
        local = os.path.normpath(os.path.join(STATIC, path[len('/static/'):]))
        if local.startswith(STATIC) and os.path.isfile(local):
            with open(local, 'rb') as fh:
                return route.fulfill(status=200, body=fh.read(),
                                     content_type=mimetypes.guess_type(local)[0] or 'application/octet-stream')
    return route.abort()


def page_problems(html, path='/', csp=None, wait_ms=500):
    """Load `html` as if served at `path` (with the given CSP header, if any);
    return (page errors, CSP violations, navigations)."""
    p, browser = chromium()
    try:
        page = browser.new_page()
        errors, csp_violations, navigations = [], [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: csp_violations.append(m.text)
                if m.type == 'error' and 'Content Security Policy' in m.text else None)
        page.on('framenavigated', lambda f: navigations.append(f.url) if f == page.main_frame else None)

        def handle(route):
            if urlparse(route.request.url).path == path and route.request.resource_type == 'document':
                headers = {'Content-Type': 'text/html; charset=utf-8'}
                if csp:
                    headers['Content-Security-Policy'] = csp
                return route.fulfill(status=200, body=html, headers=headers)
            return _serve_static(route)
        page.route('**/*', handle)
        page.goto(ORIGIN + path, wait_until='load')
        page.wait_for_timeout(wait_ms)
        return errors, csp_violations, navigations
    finally:
        browser.close()
        p.stop()
