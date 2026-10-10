"""
tests/test_no_html_injection.py — BLK-19: names, titles and messages that
other people typed never run as HTML in the pages our scripts build.

tests/html_sinks.py finds every value a script puts into HTML; each must go
through static/js/escape.js (escapeHtml, escapeJsAttr, safeUrl) or be a
reviewed exception.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

from tests import html_sinks
from tests.html_sinks import script_findings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER_CALL = re.compile(r'\b(escapeHtml|escapeJsAttr|safeUrl)\s*\(')


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_every_value_put_into_html_is_escaped():
    found = html_sinks.findings()
    assert not found, 'Values put into HTML without escapeHtml/escapeJsAttr/safeUrl:\n  ' + '\n  '.join(
        f'{path}:{line}: ${{{expr}}}  after {ctx!r}' for path, line, expr, ctx in found)


def test_every_page_that_escapes_loads_the_helpers():
    """A template whose scripts call the helpers loads static/js/escape.js
    (directly, or through the shared layout) before its own scripts."""
    missing = []
    out = subprocess.run(['git', '-C', ROOT, 'ls-files', 'templates'], capture_output=True, text=True).stdout.split()
    with open(os.path.join(ROOT, 'templates', 'base_classic.html'), encoding='utf-8') as fh:
        layout = fh.read()
    assert layout.index('src="/static/js/escape.js"') < layout.index('{% block extra_js %}')
    for path in out:
        if not path.endswith('.html') or path in html_sinks.NOT_RENDERED:
            continue
        with open(os.path.join(ROOT, path), encoding='utf-8') as fh:
            text = fh.read()
        inline = [m for m in re.finditer(r'<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>', text, re.S | re.I)
                  if HELPER_CALL.search(m.group(1))]
        if not inline or re.search(r'{%\s*extends\s+["\']base_classic\.html["\']', text):
            continue
        loader = text.find('src="/static/js/escape.js"')
        if loader == -1 or loader > inline[0].start():
            missing.append(path)
    assert not missing, f'call escapeHtml/escapeJsAttr/safeUrl without loading /static/js/escape.js first: {missing}'


def test_static_scripts_dont_rely_on_helpers_they_dont_load():
    """Shared scripts load on many pages; they build DOM nodes instead."""
    for name in os.listdir(os.path.join(ROOT, 'static', 'js')):
        if name.endswith('.js') and name != 'escape.js':
            with open(os.path.join(ROOT, 'static', 'js', name), encoding='utf-8') as fh:
                assert not HELPER_CALL.search(fh.read()), name


@pytest.mark.parametrize('js', [
    'el.innerHTML = `<b>${name}</b>`;',
    "el.innerHTML = '<td>' + name + '</td>';",
    "html += '<td>' + (r.name || 'Unknown') + '</td>';",
    "var row = '<tr>' +\n  '<td>' + r.name + '</td>' +\n  '</tr>';",
    'el.innerHTML = data.message;',
    "el.insertAdjacentHTML('beforeend', msg);",
    "el.insertAdjacentHTML('beforeend', `<li>${x}</li>`);",
    'x = `<a href="${escapeHtml(url)}">go</a>`;',
    'x = `<img src="${escapeHtml(url)}">`;',
    "x = `<button onclick=\"go('${escapeHtml(id)}')\">`;",
    "document.write('<p>' + q + '</p>');",
    'x = `<li>${cond ? name : \'none\'}</li>`;',
    "x = `<b>${t === 'h' ? 'Heading' : t === 'p' ? name : 'Divider'}</b>`;",
    "el.innerHTML = items.map(function(n) { var t = n.a; return t; }).join('');",
    "el.innerHTML = items.map(function(n) { return '<b>' + n.a + '</b>'; }).join('');",
    'list.innerHTML = items.map(i => `<li>${i}</li>`).join(\'\');',
])
def test_the_scan_flags_unescaped_values(js):
    assert script_findings(js)


@pytest.mark.parametrize('js', [
    'el.innerHTML = `<b>${escapeHtml(name)}</b>`;',
    "el.innerHTML = '<td>' + escapeHtml(r.name || 'Unknown') + '</td>';",
    'el.innerHTML = `<i class="${ok ? \'a\' : \'b\'}"></i>`;',
    'el.innerHTML = items.map(i => `<li>${escapeHtml(i)}</li>`).join(\'\');',
    'el.innerHTML = rowsHtml;',
    'el.innerHTML = html;',
    "el.innerHTML = items.map(function(n) { var t = n.a; return '<b>' + escapeHtml(t) + '</b>'; }).join('');",
    "x = `<b>${t === 'h' ? 'Heading' : t === 'p' ? 'Info' : 'Divider'}</b>`;",
    "el.innerHTML = '<p>Loading…</p>';",
    'x = `<a href="${safeUrl(u)}">go</a>`;',
    'x = `<button onclick="go(${escapeJsAttr(id)})">`;',
    'msg = `Hello ${name}`;',
    'var re = /<div>/; el.textContent = name;',
    "el.innerHTML = '<span>' + 42 + '</span>';",
])
def test_the_scan_accepts_escaped_and_literal_values(js):
    assert script_findings(js) == [], script_findings(js)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

@pytest.mark.skipif(not shutil.which('node'), reason='needs Node.js to run static/js/escape.js')
def test_the_helpers_turn_markup_into_text():
    script = """
      const h = require(process.argv[1]);
      console.log(JSON.stringify({
        html: h.escapeHtml('<img src=x onerror=alert(1)> & "q" \\'s\\' `t`'),
        none: [h.escapeHtml(null), h.escapeHtml(undefined), h.escapeHtml(0)],
        js: h.escapeJsAttr("x'); alert(1); ('"),
        urls: ['javascript:alert(1)', ' JaVaScRiPt:alert(1)', 'java\\tscript:alert(1)', 'data:text/html,<b>',
               'vbscript:x', 'https://ok.example/a?b=1&c=2', 'http://x', '/ticket/1', '#top', 'mailto:a@b.c',
               'relative/path'].map(h.safeUrl),
      }));
    """
    out = subprocess.run(['node', '-e', script, os.path.join(ROOT, 'static', 'js', 'escape.js')],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got['html'] == '&lt;img src=x onerror=alert(1)&gt; &amp; &quot;q&quot; &#39;s&#39; &#96;t&#96;'
    assert got['none'] == ['', '', '0']
    assert got['js'] == '&quot;x&#39;); alert(1); (&#39;&quot;'
    assert got['urls'] == ['#', '#', '#', '#', '#', 'https://ok.example/a?b=1&amp;c=2', 'http://x', '/ticket/1',
                           '#top', 'mailto:a@b.c', 'relative/path']


# ── Criterion 3 ─────────────────────────────────────────────────────────────

PAYLOAD = '<img src=x onerror=alert(1)>'


def test_a_markup_name_is_stored_as_typed_and_shown_as_text(real_app):
    """Registering as <img src=x onerror=alert(1)> keeps the name, and the staff
    pages that list registrants show it as text, whether Jinja renders it
    (escaped) or a script receives it as JSON (\\u003c…)."""
    import datetime
    from tests.test_integration_flow import _create_event, _login, _unique, _user
    flask_app, db = real_app
    spoc = f"{_unique('xss-spoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Markup Night'), datetime.date.today().isoformat(), team=False)
    student = f"{_unique('xss-student')}@test.edu"
    _user(db, student, 'Student')
    resp = _login(flask_app, student, 'Student').post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes',
        'full_name': PAYLOAD, 'email': student, 'phone': '9876543210', 'usn': '1SN22CS666', 'team_name': PAYLOAD})
    assert resp.status_code == 302

    reg = next(d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream())
    assert reg['lead_name'] == PAYLOAD  # kept exactly as typed

    for url in (f'/coordinator/registrations/{event_id}', f'/spoc/scan/{event_id}'):
        page = owner.get(url)
        assert page.status_code == 200, url
        html = page.get_data(as_text=True)
        assert PAYLOAD not in html, url
        assert '&lt;img src=x onerror=alert(1)&gt;' in html or '\\u003cimg src=x onerror=alert(1)\\u003e' in html, url

    found = owner.post('/checkin/kiosk/search', json={'event_id': event_id, 'query': 'img'}).get_json()
    assert [r['lead_name'] for r in found['results']] == [PAYLOAD]  # JSON data; the kiosk escapes it when shown
