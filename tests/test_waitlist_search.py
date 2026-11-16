"""
tests/test_waitlist_search.py — UPG-302 on the real database layer.

The waitlist on the SPOC's registrations page has a search of its own: any
part of the team name, the lead's name, email, USN or phone, or a member's
name, USN or email finds the entry, whatever the capitals; the place shown is
the place in the whole line; accepting from a search comes back to it; a long
line scrolls inside its card with its headings in view. The registrations
list's search ignores capitals too.
"""
import re

from tests import test_spoc_waitlist as wl
from tests.test_integration_flow import _login, _unique, _user  # noqa: F401

host = wl.host


def _three(h):
    """A full event with three teams waiting, each with its own details."""
    event_id = wl._full_event(h)
    rows = []
    for team, name, usn, phone, mate in (('Alpha Wait', 'Asha Rao', '1SN22CS501', '9000000001', 'Kiran Mate'),
                                         ('Bravo Squad', 'Bala Iyer', '1SN22CS502', '9000000002', 'Leela Nair'),
                                         ('Charlie Crew', 'Chitra Das', '1SN22CS503', '9000000003', 'Mohan Pai')):
        wl_id, lead, member = wl._join(h, event_id, team, full_name=name, usn=usn, phone=phone, member_1_name=mate)
        rows.append({'id': wl_id, 'lead': lead, 'mate': member, 'team': team})
    return event_id, rows


def _get(client, event_id, query=''):
    resp = client.get(f'/coordinator/registrations/{event_id}{query}')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _shown(html, rows):
    return [r['team'] for r in rows if f'data-waitlist-entry="{r["id"]}"' in html]


def _card(html):
    start = html.index('id="waitlist"')
    return html[start:html.index('</details>', start)]


# ── Criterion 1: any detail finds the entry, in any case ─────────────────────

def test_the_waitlist_search_finds_an_entry_by_any_detail_whatever_the_capitals(host):
    h = host
    event_id, rows = _three(h)
    bravo = rows[1]
    for q in ('bravo', 'BRAVO SQUAD', 'bala iyer', bravo['lead'].upper(), '1sn22cs502', '9000000002',
              'leela', bravo['mate'].upper()):
        html = _get(h['owner'], event_id, f'?wq={q}')
        assert _shown(html, rows) == ['Bravo Squad'], q
    # Part of a name finds every entry it is part of
    assert _shown(_get(h['owner'], event_id, '?wq=WAIT'), rows) == ['Alpha Wait']
    assert _shown(_get(h['owner'], event_id, '?wq=1sn22cs50'), rows) == ['Alpha Wait', 'Bravo Squad', 'Charlie Crew']


def test_a_found_entry_keeps_its_place_in_the_whole_line_and_the_count_says_how_many_match(host):
    h = host
    event_id, rows = _three(h)
    html = _get(h['owner'], event_id, '?wq=charlie')
    card = _card(html)
    assert re.search(r'<details[^>]*id="waitlist"[^>]* open>', html), 'the waitlist opens on a search'
    assert 'Waitlist: 3 waiting' in card                     # the heading still counts everyone
    assert '1 of 3 waiting match “charlie”' in card and 'data-waitlist-found' in card
    row = card[card.index(f'data-waitlist-entry="{rows[2]["id"]}"'):]
    assert '#3' in row[:row.index('</tr>')]
    # Its Accept dialog says it is third in line
    assert 'is #3 in line' in html and 'ahead of the 2 before them' in html
    # Only the found entry's dialog is on the page
    assert f'id="accept-{rows[2]["id"]}"' in html and f'id="accept-{rows[0]["id"]}"' not in html


def test_nobody_matching_says_so_and_one_click_shows_everyone_again(host):
    h = host
    event_id, rows = _three(h)
    card = _card(_get(h['owner'], event_id, '?wq=zzz-nobody'))
    assert 'Nobody on the waitlist matches “zzz-nobody”.' in card
    assert _shown(card, rows) == [] and 'data-waitlist-table' not in card
    clear = re.search(r'<a href="([^"]*)"[^>]*data-waitlist-clear', card)
    assert clear and clear.group(1) == f'/coordinator/registrations/{event_id}#waitlist'
    assert _shown(_get(h['owner'], event_id), rows) == ['Alpha Wait', 'Bravo Squad', 'Charlie Crew']
    # No search, no count line and no clear link
    plain = _card(_get(h['owner'], event_id))
    assert 'data-waitlist-found' not in plain and 'data-waitlist-clear' not in plain


# ── Criterion 2: the two searches on the page keep each other ───────────────

def test_the_waitlist_search_keeps_the_lists_search_and_filters_and_the_other_way_round(host):
    h = host
    event_id, rows = _three(h)
    html = _get(h['owner'], event_id, '?q=seat&sort=name&wq=bravo')
    form = html[html.index('data-waitlist-search'):]
    form = form[:form.index('</form>')]
    assert 'name="q" value="seat"' in form and 'name="sort" value="name"' in form
    assert 'name="wq" value="bravo"' in form and form.count('name="wq"') == 1
    assert re.search(r'action="/coordinator/registrations/[^"]+#waitlist"', html[html.index('<form', html.index(
        'id="waitlist"')):])
    # The list's own search box keeps the waitlist's search
    listing = html[html.index('id="list-search-q"') - 2000:html.index('id="list-search-q"')]
    assert 'name="wq" value="bravo"' in listing
    # The clear link keeps the list's search and filters
    clear = re.search(r'<a href="([^"]*)"[^>]*data-waitlist-clear', html).group(1)
    assert clear.startswith(f'/coordinator/registrations/{event_id}?') and clear.endswith('#waitlist')
    assert 'q=seat' in clear and 'sort=name' in clear and 'wq=' not in clear


# ── Criterion 3: accepting from a search comes back to the same search ──────

def test_accepting_from_a_search_comes_back_to_the_search(host):
    h = host
    event_id, rows = _three(h)
    html = _get(h['owner'], event_id, '?wq=Bravo Squad')
    dialog = html[html.index(f'id="accept-{rows[1]["id"]}"'):]
    dialog = dialog[:dialog.index('</dialog>')]
    assert 'name="wq" value="Bravo Squad"' in dialog
    resp = h['owner'].post(f'/coordinator/registrations/{event_id}/accept_waitlist',
                           data={'wl_id': rows[1]['id'], 'wq': 'Bravo Squad'})
    assert resp.status_code == 302
    # The top of the page, where the message is, with the search kept: the waitlist opens searched
    assert resp.headers['Location'].endswith(f'/coordinator/registrations/{event_id}?wq=Bravo+Squad')
    assert wl._regs_of(h, event_id, rows[1]['lead'])            # they were accepted
    card = _card(_get(h['owner'], event_id, '?wq=Bravo+Squad'))
    assert 'Nobody on the waitlist matches “Bravo Squad”.' in card and 'Waitlist: 2 waiting' in card
    # Refused (already accepted): back to the waitlist itself, still searched
    resp = h['owner'].post(f'/coordinator/registrations/{event_id}/accept_waitlist',
                           data={'wl_id': rows[1]['id'], 'wq': 'Bravo Squad'})
    assert resp.headers['Location'].endswith(f'/coordinator/registrations/{event_id}?wq=Bravo+Squad#waitlist')
    # Without a search, as before
    resp = wl._accept(h['owner'], event_id, rows[0]['id'])
    assert resp.headers['Location'].endswith(f'/coordinator/registrations/{event_id}')


def test_a_coordinator_searches_the_waitlist_too_but_still_has_no_accept(host):
    h = host
    event_id, rows = _three(h)
    coord = f"{_unique('coord')}@test.edu"
    _user(h['db'], coord, 'EventCoordinator')
    h['db'].collection('events').document(event_id).update({'coordinators': [coord]})
    client = _login(h['app'], coord, 'EventCoordinator')
    html = _get(client, event_id, '?wq=ALPHA')
    assert _shown(html, rows) == ['Alpha Wait'] and 'data-accept-waitlist' not in html


# ── Criterion 4: a long line scrolls inside its card ─────────────────────────

def test_a_long_waitlist_scrolls_inside_its_card_with_its_headings_in_view(host):
    h = host
    event_id, rows = _three(h)
    card = _card(_get(h['owner'], event_id))
    box = re.search(r'<div class="[^"]*\bwl-scroll\b[^"]*"[^>]*>', card)
    assert box and 'tabindex="0"' in box.group(0) and 'data-waitlist-scroll' in box.group(0)
    assert card.index('data-waitlist-scroll') < card.index('data-waitlist-table')
    with open('static/css/registrations.css', encoding='utf-8') as handle:
        css = handle.read()
    rule = re.search(r'\.wl-scroll \{([^}]*)\}', css).group(1)
    assert 'max-height' in rule and 'overflow-y: auto' in rule
    assert re.search(r'\.wl-scroll > table > thead th \{[^}]*position: sticky;[^}]*top: 0', css)


# ── Criterion 5: the registrations list's search ignores capitals ───────────

def test_the_registrations_lists_search_ignores_capitals(host):
    h = host
    event_id = h['event']()
    h['register'](event_id, team_name='Quiet Quokkas')
    for q in ('quiet quokkas', 'QUIET QUOKKAS', 'qUiEt'):
        html = _get(h['owner'], event_id, f'?q={q}')
        section = html[html.index('id="registrations"'):]
        assert 'Quiet Quokkas' in section, q
    section = _get(h['owner'], event_id, '?q=nobody-at-all')
    assert 'Quiet Quokkas' not in section[section.index('id="registrations"'):]


def test_every_search_box_script_compares_in_lower_case():
    """The page scripts that filter as you type lower-case both what is typed
    and what it is compared with (checked 2026-11-16: these are all of them)."""
    checks = {
        'static/js/pages/spoc__room_allocation.js': ["getElementById('searchBox').value.toLowerCase()"],
        'static/js/pages/spoc__dashboard.js': ["getElementById('event-search').value.toLowerCase()",
                                               'card.dataset.title.toLowerCase()'],
        'static/js/pages/index.js': ['searchInput.value.trim().toLowerCase()'],
        'static/js/pages/analytics__hub.js': ['findBox.value.trim().toLowerCase()', 'e.title.toLowerCase()'],
        'static/js/command-palette.js': ['e.target.value.toLowerCase()', 'item.name.toLowerCase()'],
        'templates/spoc/room_allocation.html': ["reg.assigned_room or '')) | lower"],
        'templates/index.html': ['data-search="{{ event.title.lower() }}'],
        'templates/spoc/scan.html': ["value.toLowerCase()", 'r.lead_name.toLowerCase()'],
    }
    for path, needles in checks.items():
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
        for needle in needles:
            assert needle in text, (path, needle)
