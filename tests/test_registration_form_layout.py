"""
tests/test_registration_form_layout.py — UPG-150: the registration form is a
full-page, official form: the event summary beside the form across the page on
a wide screen, numbered sections (the team in its own), and underlined fields
instead of boxes; nothing scrolls sideways on a phone. Measured in headless
Chromium on the page the app renders, as in UPG-28.
"""
import datetime
import os
import re

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user
from tests.test_phone_journey import CONTRAST, DESKTOP, PHONE, _routes
from tests.test_shared_layout import DESKTOP_ONLY, MEASURE


@pytest.fixture
def forms(real_app, tmp_path):
    flask_app, db = real_app
    spoc = f"{_unique('rfspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    solo = _create_event(owner, db, _unique('Form Talk'), day, team=False)
    team = _create_event(owner, db, _unique('Form Hack'), day, team=True)
    db.collection('events').document(team).update({'total_rounds': 3})
    for event_id in (solo, team):
        db.collection('events').document(event_id).update({'status': 'registration_open'})
    shots = os.environ.get('UPG150_SHOTS') or str(tmp_path / 'shots')
    os.makedirs(shots, exist_ok=True)
    return {'app': flask_app, 'db': db, 'solo': solo, 'team': team, 'shots': shots}


LAYOUT = """() => {
  const main = document.querySelector('.app-main'), cs = getComputedStyle(main);
  const content = main.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const a = document.querySelector('.reg-summary').getBoundingClientRect();
  const b = document.querySelector('.reg-sheet').getBoundingClientRect();
  return {content, left: Math.min(a.left, b.left), right: Math.max(a.right, b.right),
          beside: a.right <= b.left && Math.abs(a.top - b.top) < 4};
}"""

BORDERS = """() => [...document.querySelectorAll(
    '#reg-form input:not([type=hidden]):not([type=radio]):not([type=checkbox]), #reg-form select, #reg-form textarea')]
  .filter(el => el.getClientRects().length)
  .map(el => { const s = getComputedStyle(el);
    return [el.name, s.borderTopWidth, s.borderLeftWidth, s.borderRightWidth, s.borderBottomWidth, s.borderBottomStyle]; })"""


def _open(d, event_id, size):
    from tests.headless import chromium, live_server
    p, browser = chromium()
    server = live_server(d['app'])
    server.__enter__()
    context = browser.new_context(viewport=size)
    _routes(context, server.url)
    page = context.new_page()
    page.goto(f"{server.url}/forms/register/{event_id}", wait_until='load')

    def close():
        browser.close()
        p.stop()
        server.__exit__(None, None, None)
    return page, close


# ── Criterion 1: across the page, the summary beside the form ─────────────────

@pytest.mark.parametrize('which', ['solo', 'team'])
def test_the_form_and_summary_fill_the_page_side_by_side(forms, which):
    page, close = _open(forms, forms[which], DESKTOP)
    try:
        seen = page.evaluate(LAYOUT)
        page.screenshot(path=os.path.join(forms['shots'], f'{which}-1280.png'), full_page=True)
        assert seen['beside'], seen
        assert (seen['right'] - seen['left']) >= 0.85 * seen['content'], seen
        assert page.evaluate(CONTRAST) == []
    finally:
        close()


# ── Criterion 2: underlined fields ─────────────────────────────────────────────

def test_every_field_is_underlined_not_boxed(forms):
    page, close = _open(forms, forms['team'], DESKTOP)
    try:
        fields = page.evaluate(BORDERS)
        names = {f[0] for f in fields}
        assert {'full_name', 'email', 'phone', 'usn', 'team_name', 'member_1_name'} <= names, names
        for name, top, left, right, bottom, style in fields:
            assert (top, left, right) == ('0px', '0px', '0px'), (name, top, left, right)
            assert float(bottom[:-2]) >= 1 and style == 'solid', (name, bottom, style)
    finally:
        close()


# ── Criterion 3: numbered sections, the team in its own ────────────────────────

def test_the_form_is_in_numbered_sections_with_the_team_on_its_own(forms):
    client = forms['app'].test_client()
    team = client.get(f"/forms/register/{forms['team']}").get_data(as_text=True)
    assert re.findall(r'data-section="(\w+)"', team) == ['participant', 'team', 'declaration']
    assert [int(n) for n in re.findall(r'<span class="reg-step">(\d+)</span>', team)] == [1, 2, 3]
    team_part = team[team.index('data-section="team"'):team.index('data-section="declaration"')]
    assert 'name="team_name"' in team_part and 'name="member_1_email"' in team_part
    participant = team[team.index('data-section="participant"'):team.index('data-section="team"')]
    assert 'name="full_name"' in participant and 'name="email"' in participant
    assert 'Team size' in team and '2–4 people' in team and '3 rounds' in team

    solo = client.get(f"/forms/register/{forms['solo']}").get_data(as_text=True)
    assert re.findall(r'data-section="(\w+)"', solo) == ['participant', 'declaration']
    assert 'name="privacy_consent"' in solo[solo.index('data-section="declaration"'):]


def test_a_builder_heading_stays_with_the_questions_after_it():
    from routes_forms import form_sections
    fields = [{'id': 'h1', 'type': 'heading', 'label': 'About you'}, {'id': 'full_name', 'type': 'text'},
              {'id': 'email', 'type': 'email'}, {'id': 'h2', 'type': 'heading', 'label': 'Your project'},
              {'id': 'idea', 'type': 'textarea'}, {'id': 'team_name', 'type': 'text'},
              {'id': 'team_members', 'type': 'heading'}, {'id': 'member_1_name', 'type': 'text'}]
    s = form_sections(fields)
    assert [f['id'] for f in s['participant']] == ['h1', 'full_name', 'email']
    assert [f['id'] for f in s['details']] == ['h2', 'idea']
    assert [f['id'] for f in s['team']] == ['team_name', 'team_members', 'member_1_name']


# ── Criterion 5 (owner, 2026-10-31): each member in a block of their own ──────

MEMBER_ROWS = """() => [...document.querySelectorAll('.reg-member')].map(b => {
  const r = b.getBoundingClientRect();
  return {n: b.dataset.member, top: r.top, bottom: r.bottom,
          fields: [...b.querySelectorAll('input')].map(i => {
            const q = i.getBoundingClientRect(); return [i.name, q.top, q.bottom]; })};
})"""


def test_each_team_member_has_a_block_of_their_own(forms):
    html = forms['app'].test_client().get(f"/forms/register/{forms['team']}").get_data(as_text=True)
    blocks = re.findall(r'data-member="(\d+)">(.*?)</div>\s*</div>', html, re.S)
    assert [n for n, _ in blocks] == ['2', '3', '4']
    for n, body in blocks:
        i = int(n) - 1
        assert re.findall(r'name="(member_\d+_\w+)"', body) == [f'member_{i}_name', f'member_{i}_email',
                                                               f'member_{i}_usn'], (n, body)
        assert f'Member {n}' in body
    assert 'Required' in blocks[0][1] and 'Optional' in blocks[2][1]   # a 2–4 team: member 2 is required

    for size in (DESKTOP, PHONE):
        page, close = _open(forms, forms['team'], size)
        try:
            seen = page.evaluate(MEMBER_ROWS)
            if size is DESKTOP:
                page.screenshot(path=os.path.join(forms['shots'], 'team-members-1280.png'), full_page=True)
            assert [b['n'] for b in seen] == ['2', '3', '4']
            for before, after in zip(seen, seen[1:]):
                assert before['bottom'] <= after['top'], (before, after)   # blocks never share a row
            for b in seen:
                assert all(b['top'] <= top and bottom <= b['bottom'] for _, top, bottom in b['fields']), b
            if size is DESKTOP:   # name, email and USN on one row
                assert len({round(top) for _, top, _ in seen[0]['fields']}) == 1, seen[0]
        finally:
            close()


def test_more_details_per_member_wrap_inside_their_block(forms):
    """A form that asks each member for five details: the extra ones go to the
    next row of the same block, three to a row, never beside another member."""
    db = forms['db']
    fields = [{'id': 'full_name', 'type': 'text', 'label': 'Full Name', 'required': True},
              {'id': 'email', 'type': 'email', 'label': 'Email', 'required': True}]
    for i in (1, 2, 3):
        for key, label in (('name', 'Name'), ('email', 'Email'), ('usn', 'USN'),
                           ('phone', 'Phone'), ('department', 'Department')):
            fields.append({'id': f'member_{i}_{key}', 'type': 'text', 'label': f'Member {i + 1} {label}'})
    db.collection('event_forms').document(forms['team']).set({'fields': fields})

    html = forms['app'].test_client().get(f"/forms/register/{forms['team']}").get_data(as_text=True)
    assert re.findall(r'data-section="(\w+)"', html) == ['participant', 'team', 'declaration']   # no empty section

    page, close = _open(forms, forms['team'], DESKTOP)
    try:
        seen = page.evaluate(MEMBER_ROWS)
        page.screenshot(path=os.path.join(forms['shots'], 'team-members-5-details-1280.png'), full_page=True)
        assert [b['n'] for b in seen] == ['2', '3', '4']
        for before, after in zip(seen, seen[1:]):
            assert before['bottom'] <= after['top'], (before, after)
        for b in seen:
            assert [f[0].rsplit('_', 1)[1] for f in b['fields']] == ['name', 'email', 'usn', 'phone', 'department']
            assert all(b['top'] <= top and bottom <= b['bottom'] for _, top, bottom in b['fields']), b
            rows = sorted({round(top) for _, top, _ in b['fields']})
            assert len(rows) == 2, b                                  # 3 on the first row, 2 below
            assert [round(f[1]) for f in b['fields']].count(rows[0]) == 3, b
    finally:
        close()


def test_team_blocks_group_fields_by_member():
    from routes_forms import team_blocks
    team = [{'id': 'team_name', 'type': 'text', 'label': 'Team Name'},
            {'id': 'team_members', 'type': 'heading', 'label': 'Team members'},
            {'id': 'member_1_name', 'type': 'text', 'label': 'Member 2 Name', 'required': True},
            {'id': 'member_1_email', 'type': 'email', 'label': 'Member 2 Email', 'required': True},
            {'id': 'member_2_name', 'type': 'text', 'label': 'Member 3 Name'},
            {'id': 'member_2_email', 'type': 'email', 'label': 'Member 3 Email'}]
    b = team_blocks(team)
    assert [f['id'] for f in b['general']] == ['team_name', 'team_members']
    assert [(m['n'], m['required'], [f['label'] for f in m['fields']]) for m in b['members']] == [
        (2, True, ['Name', 'Email']), (3, False, ['Name', 'Email'])]
    assert team[2]['label'] == 'Member 2 Name'   # the schema itself is untouched


# ── Criterion 4: a phone ───────────────────────────────────────────────────────

@pytest.mark.parametrize('which', ['solo', 'team'])
def test_no_sideways_scroll_on_a_phone(forms, which):
    page, close = _open(forms, forms[which], PHONE)
    try:
        seen = page.evaluate(MEASURE.replace('DESKTOP_ONLY', repr(DESKTOP_ONLY)))
        page.screenshot(path=os.path.join(forms['shots'], f'{which}-375.png'), full_page=True)
        assert not seen['scrolled'] and not seen['cut'], seen
        fields = page.evaluate(BORDERS)
        assert fields and all(f[1] == '0px' and f[4] != '0px' for f in fields)
    finally:
        close()
