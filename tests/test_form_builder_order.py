"""
tests/test_form_builder_order.py — UPG-216 on the real database layer: the
registration page shows the SPOC's form as built in the builder. The title
and description the SPOC gives the form are kept (the SQL store drops them
from the form, so they're kept on the event) and come back in the builder;
the questions keep the SPOC's order, phone and USN included; in the builder,
name and email stay at the top, where the page always shows them.
"""
import json
import re
import shutil
import subprocess

import pytest

from tests.test_form_builder_choices import EMAIL, NAME, SHIRT, fb  # noqa: F401  (fixture)

PHONE = {'id': 'phone', 'type': 'tel', 'label': 'Phone Number', 'required': True}
USN = {'id': 'usn', 'type': 'text', 'label': 'USN', 'required': False}
HEADING = {'id': 'h1', 'type': 'heading', 'label': 'About your project'}
IDEA = {'id': 'idea', 'type': 'textarea', 'label': 'Your idea', 'required': False}


def _names_in_order(page):
    """The answer names the page asks for, top to bottom, without team and system fields."""
    names = re.findall(r'<(?:input|select|textarea)\b[^>]*\bname="([^"]+)"', page)
    skip = ('csrf_token', 'submission_id', 'privacy_consent', 'whatsapp_opt_in', 'participant_type', 'ticket_type')
    return list(dict.fromkeys(n for n in names if n not in skip and not n.startswith('member_')))


def _section(page, title):
    """The HTML of the page section headed `title`."""
    start = page.index(title)
    nxt = re.search(r'<legend\b', page[start + len(title):])
    return page[start:start + len(title) + (nxt.start() if nxt else len(page))]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_title_and_description_the_spoc_gives_are_kept(fb):  # noqa: F811
    event_id = fb['event']()
    resp = fb['save'](event_id, [NAME, EMAIL, SHIRT], form_title='Code Sprint Entry',
                      form_desc='Tell us about your team.')
    assert resp.status_code == 200
    page = fb['page'](event_id)
    assert '<h2 id="reg-form-title">Code Sprint Entry</h2>' in page
    assert 'Tell us about your team.' in page

    # The builder opens with them
    builder = fb['owner'].get(f'/forms/builder/{event_id}').get_data(as_text=True)
    existing = json.loads(re.search(r'const existingForm = (.*);\n', builder).group(1))
    assert existing['form_title'] == 'Code Sprint Entry'
    assert existing['form_desc'] == 'Tell us about your team.'

    # A second save replaces them, an empty description included
    assert fb['save'](event_id, [NAME, EMAIL, SHIRT], form_title='Final Entry', form_desc='').status_code == 200
    page = fb['page'](event_id)
    assert '<h2 id="reg-form-title">Final Entry</h2>' in page
    assert 'Tell us about your team.' not in page


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_page_keeps_the_spocs_order_phone_and_usn_included(fb):  # noqa: F811
    event_id = fb['event']()
    # Phone right after email opens the form with name and email; USN, put
    # below the SPOC's own questions, stays there; the heading stays above its question
    assert fb['save'](event_id, [NAME, EMAIL, PHONE, SHIRT, HEADING, IDEA, USN]).status_code == 200
    page = fb['page'](event_id)
    assert _names_in_order(page)[:6] == ['full_name', 'email', 'phone', 'shirt', 'idea', 'usn']
    participant = _section(page, 'Participant details')
    assert 'name="phone"' in participant and 'name="usn"' not in participant
    details = _section(page, 'Registration details')
    assert details.index('About your project') < details.index('name="idea"') < details.index('name="usn"')

    # Phone moved below a question leaves "Participant details" too
    assert fb['save'](event_id, [NAME, EMAIL, SHIRT, PHONE]).status_code == 200
    page = fb['page'](event_id)
    assert _names_in_order(page)[:4] == ['full_name', 'email', 'shirt', 'phone']
    assert 'name="phone"' not in _section(page, 'Participant details')


def test_a_form_not_built_in_the_builder_keeps_its_layout(fb):  # noqa: F811
    from routes_forms import form_sections
    fields = [NAME, EMAIL, SHIRT, PHONE]
    # Without `chosen` (wizard and template forms) phone still opens the form, as before
    assert [f['id'] for f in form_sections(fields)['participant']] == ['full_name', 'email', 'phone']
    assert [f['id'] for f in form_sections(fields, chosen=True)['participant']] == ['full_name', 'email']


# ── Criterion 3 ─────────────────────────────────────────────────────────────

_NODE_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
function el() {
  return { style: {}, dataset: {}, classList: { add() {}, remove() {}, toggle() {} }, value: '', innerHTML: '',
           addEventListener() {}, appendChild() {}, querySelectorAll() { return []; }, remove() {} };
}
const ctx = { console, JSON,
  document: { addEventListener() {}, getElementById: el, createElement: el, querySelectorAll() { return []; } },
  window: { addEventListener() {} }, escapeHtml: (s) => String(s == null ? '' : s) };
vm.createContext(ctx);
vm.runInContext(src, ctx);
const out = vm.runInContext(`
  const ids = () => fields.map(f => f.id);
  const log = [];
  fields = [{id:'phone', type:'tel'}, {id:'q1', type:'text'}, {id:'full_name', type:'text'}, {id:'email', type:'email'}];
  renderCanvas(); log.push(ids());
  moveField('email', 1); log.push(ids());
  moveField('phone', -1); log.push(ids());
  moveField('q1', -1); log.push(ids());
  fields.unshift(fields.pop()); renderCanvas(); log.push(ids());
  log;`, ctx);
process.stdout.write(JSON.stringify(out));
"""


def test_the_builder_keeps_name_and_email_at_the_top(fb, tmp_path):  # noqa: F811
    event_id = fb['event']()
    builder = fb['owner'].get(f'/forms/builder/{event_id}').get_data(as_text=True)
    assert 'Always asked, always first' in builder
    if not shutil.which('node'):
        pytest.skip('Node is not installed')
    script = re.search(r'<script nonce="[^"]*">(.*?)</script>', builder, re.S).group(1)
    (tmp_path / 'builder.js').write_text(script)
    (tmp_path / 'harness.js').write_text(_NODE_HARNESS)
    run = subprocess.run(['node', str(tmp_path / 'harness.js'), str(tmp_path / 'builder.js')],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    steps = json.loads(run.stdout)
    # Name and email go to the top, the rest keep their order
    assert steps[0] == ['full_name', 'email', 'phone', 'q1']
    # Email can't be moved down, and nothing moves above it
    assert steps[1] == steps[0]
    assert steps[2] == steps[0]
    # Other questions still move among themselves
    assert steps[3] == ['full_name', 'email', 'q1', 'phone']
    # A question dropped above name goes back below email
    assert steps[4] == ['full_name', 'email', 'phone', 'q1']
