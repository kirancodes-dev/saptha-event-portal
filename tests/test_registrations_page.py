"""
tests/test_registrations_page.py — UPG-234 and UPG-235 on the real database layer.

UPG-234: the SPOC's registrations page works without Bootstrap's script (its
layout loads none): each row's Details opens under it, "Show all details"
opens every row, Cancel, Delete and Accept open as dialogs; the waitlist is
folded away until the SPOC opens it (and stays open while they work); search,
Clear, the filters and the pages come back to the list, not the top of the
page; a summary gives the numbers; every control is labelled.

UPG-235: accepting from the waitlist works on a full event and takes the count
past the limit, which the SPOC is shown; the lead gets an email saying they
were accepted (with a link to pay on a paid event), also in a portal-mode
hackathon, and the team one portal notice each.
"""
import re
from urllib.parse import urlparse

from tests import headless
from tests import test_spoc_waitlist as _wl
from tests.test_spoc_waitlist import _accept, _full_event, _join, _notices, _page, _regs_of

host = _wl.host   # UPG-211's fixture, through UPG-230's tests


def _seat_takers_id(h, event_id):
    [reg_id] = [d.id for d in h['db'].collection('registrations').where('event_id', '==', event_id).stream()
                if d.to_dict().get('team_name') == 'Seat Takers']
    return reg_id


def _browse(h, event_id, steps, query='', size=(1280, 800)):
    """Open the SPOC's page (as the app rendered it, with the app's CSP) in
    headless Chromium and run steps(page). Any document request to the page's
    path gets the page again, so a search or a reload stays on it."""
    path = f'/coordinator/registrations/{event_id}'
    resp = h['owner'].get(path + query)
    assert resp.status_code == 200
    html, csp = resp.get_data(as_text=True), resp.headers.get('Content-Security-Policy', '')
    p, browser = headless.chromium()
    try:
        page = browser.new_page(viewport={'width': size[0], 'height': size[1]})
        problems = []
        page.on('pageerror', lambda e: problems.append(str(e)))
        page.on('console', lambda m: problems.append(m.text)
                if m.type == 'error' and 'Content Security Policy' in m.text else None)

        def handle(route):
            if urlparse(route.request.url).path == path and route.request.resource_type == 'document':
                headers = {'Content-Type': 'text/html; charset=utf-8'}
                if csp:
                    headers['Content-Security-Policy'] = csp
                return route.fulfill(status=200, body=html, headers=headers)
            return headless._serve_static(route)
        page.route('**/*', handle)
        page.goto(headless.ORIGIN + path + query, wait_until='load')
        steps(page)
        assert problems == []
    finally:
        browser.close()
        p.stop()


def _is_open(page, selector):
    return page.locator(selector).evaluate('el => el.open')


# ── UPG-234 criterion 1: Details opens under its row, and all of them at once ─

def test_details_opens_under_its_row_and_show_all_opens_every_row(host):
    h = host
    event_id = _full_event(h)
    reg_id = _seat_takers_id(h, event_id)

    def steps(page):
        row = page.locator(f'#details-{reg_id}')
        button = page.locator(f'[data-toggle-row][data-bs-target="#details-{reg_id}"]')
        assert not row.is_visible() and button.get_attribute('aria-expanded') == 'false'
        button.click()
        assert row.is_visible() and button.get_attribute('aria-expanded') == 'true'
        assert 'Lena Lead' in row.inner_text() and 'Mo Mate' in row.inner_text()
        assert button.inner_text().strip().startswith('Hide details')
        button.click()
        assert not row.is_visible() and button.get_attribute('aria-expanded') == 'false'
        # Show all details opens every registration (not the waitlist's rows)
        page.locator('[data-details-all]').click()
        assert row.is_visible()
        assert page.locator('[data-details-all]').inner_text().strip() == 'Hide all details'
        page.locator('[data-details-all]').click()
        assert not row.is_visible()
    _browse(h, event_id, steps)


# ── UPG-234 criterion 2: Cancel, Delete and Accept open as dialogs ──────────

def test_cancel_delete_and_accept_open_as_dialogs_and_close_again(host):
    h = host
    event_id = _full_event(h)
    reg_id = _seat_takers_id(h, event_id)
    wl_id, _, _ = _join(h, event_id, 'Wait Team')

    def steps(page):
        for opener, dialog, close in (
                (f'[data-bs-target="#cancel-{reg_id}"]', f'#cancel-{reg_id}', 'Keep it'),
                (f'[data-bs-target="#delete-{reg_id}"]', f'#delete-{reg_id}', 'Keep it')):
            assert not _is_open(page, dialog)
            page.locator(opener).click()
            assert _is_open(page, dialog) and page.locator(dialog).is_visible()
            page.locator(dialog).get_by_role('button', name=close).click()
            assert not _is_open(page, dialog)
        # The cancel dialog puts the cursor in the reason box; Escape closes it
        page.locator(f'[data-bs-target="#cancel-{reg_id}"]').click()
        assert page.evaluate('document.activeElement.id') == f'reason-{reg_id}'
        page.keyboard.press('Escape')
        assert not _is_open(page, f'#cancel-{reg_id}')
        # Accept is in the waitlist, which opens first
        page.locator('#waitlist > summary').click()
        page.locator(f'[data-bs-target="#accept-{wl_id}"]').click()
        assert _is_open(page, f'#accept-{wl_id}')
        assert 'past' in page.locator(f'#accept-{wl_id} [data-over-capacity]').inner_text() \
            or 'over the limit' in page.locator(f'#accept-{wl_id} [data-over-capacity]').inner_text()
        page.locator(f'#accept-{wl_id}').get_by_role('button', name='Not now').click()
        assert not _is_open(page, f'#accept-{wl_id}')
    _browse(h, event_id, steps)


# ── UPG-234 criterion 3: the waitlist is folded until the SPOC opens it ─────

def test_the_waitlist_is_folded_until_opened_and_stays_open_while_working(host):
    h = host
    event_id = _full_event(h)
    wl_id, _, _ = _join(h, event_id, 'Wait Team')

    def steps(page):
        assert not _is_open(page, '#waitlist')
        assert not page.locator(f'[data-waitlist-entry="{wl_id}"]').is_visible()
        page.locator('#waitlist > summary').click()
        assert _is_open(page, '#waitlist') and page.locator(f'[data-waitlist-entry="{wl_id}"]').is_visible()
        # Its own Details opens the person's form answers
        page.locator(f'[data-bs-target="#wl-details-{wl_id}"]').click()
        assert 'Max Mate' in page.locator(f'#wl-details-{wl_id}').inner_text()
        # Still open after the page reloads (a search, an action)
        page.reload(wait_until='load')
        assert _is_open(page, '#waitlist')
        page.locator('#waitlist > summary').click()
        assert not _is_open(page, '#waitlist')
        page.wait_for_function("() => Object.values(sessionStorage).includes('closed')")
        page.reload(wait_until='load')
        assert not _is_open(page, '#waitlist')
        # The "on the waitlist" link at the top opens it
        page.locator('[data-waitlist-count]').click()
        assert _is_open(page, '#waitlist')
    _browse(h, event_id, steps)


# ── UPG-234 criterion 4: search, Clear, filters and pages come back to the list ─

def test_search_clear_filters_and_pages_return_to_the_list_not_the_top(host):
    h = host
    event_id = _full_event(h)
    html = _page(h['owner'], event_id)
    form = re.search(r'<form method="get" action="([^"]+)"[^>]*role="search"', html)
    assert form and form.group(1) == f'/coordinator/registrations/{event_id}#registrations'
    filters = html[html.index('data-entry-filters'):]
    filters = filters[:filters.index('</nav>')]
    links = re.findall(r'href="([^"]+)"', filters)
    assert len(links) == 5 and all(link.endswith('#registrations') for link in links)
    resp = h['owner'].get(f'/coordinator/registrations/{event_id}?q=Lena')
    searched = resp.get_data(as_text=True)
    assert re.search(r'href="[^"]*#registrations" class="btn btn-link">Clear</a>', searched)
    # Pages too (an event with room for three teams)
    roomy = h['event']()
    for i in range(3):
        h['register'](roomy, team_name=f'Page Team {i}')
    paged = h['owner'].get(f'/coordinator/registrations/{roomy}?per_page=2').get_data(as_text=True)
    assert re.search(r'href="[^"]*page=2[^"]*#registrations" rel="next"', paged)

    def steps(page):
        page.fill('#list-search-q', 'Lena')
        with page.expect_navigation():
            page.locator('form[role="search"] button[type="submit"]').click()
        assert 'q=Lena' in page.url and page.url.endswith('#registrations')
        # The window scrolls (smoothly, global.css) to the list, as far down as
        # the page goes, instead of staying at the top of the page
        page.wait_for_function("""() => {
            const top = document.getElementById('registrations').getBoundingClientRect().top + window.scrollY;
            const most = document.scrollingElement.scrollHeight - window.innerHeight;
            return window.scrollY > 0 && Math.abs(window.scrollY - Math.min(top, most)) < 5;
        }""", timeout=5000)
    _browse(h, event_id, steps, size=(375, 640))   # a phone


# ── UPG-234 criterion 5: the numbers at a glance, and everything labelled ───

def test_the_summary_gives_the_numbers_and_every_control_is_labelled(host):
    h = host
    event_id = _full_event(h)
    _join(h, event_id, 'Wait Team')
    html = _page(h['owner'], event_id)
    summary = html[html.index('data-summary '):]
    summary = summary[:summary.index('</ul>')]
    assert re.search(r'data-summary-registered>\s*<span class="reg-summary__num">1</span>', summary)
    assert '1 / 1' in summary and 'seats taken · full' in summary
    assert re.search(r'data-summary-waitlist>\s*<span class="reg-summary__num">1</span>', summary)
    # The page needs no Bootstrap script: nothing asks for it
    assert 'data-bs-toggle="collapse"' not in html and 'data-bs-toggle="modal"' not in html
    assert '/static/js/pages/coordinator__registrations.js' in html
    # Every button's target, every aria-controls and every dialog's title exists
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    for target in re.findall(r'data-bs-target="#([^"]+)"', html):
        assert target in ids, target
    for target in re.findall(r'aria-controls="([^"]+)"', html):
        assert target in ids, target
    dialogs = re.findall(r'<dialog [^>]*>', html)
    assert dialogs and all(re.search(r'aria-labelledby="([^"]+)"', d).group(1) in ids for d in dialogs)
    # Both tables say what they are
    assert html.count('<caption') == 2
    # Each Details, Accept, Cancel and Delete says whose it is to a screen reader
    assert '<span class="visually-hidden"> of Seat Takers</span>' in html
    assert '<span class="visually-hidden"> Wait Team</span>' in html


# ── UPG-235 criterion 1: accepted past the limit; the count says so ─────────

def test_accepting_on_a_full_event_goes_past_the_limit_and_the_spoc_sees_by_how_much(host):
    h = host
    event_id = _full_event(h)
    first, first_lead, _ = _join(h, event_id, 'First Wait')
    second, second_lead, _ = _join(h, event_id, 'Second Wait')
    assert _accept(h['owner'], event_id, first).status_code == 302
    assert h['count'](event_id) == 2
    resp = _accept(h['owner'], event_id, second)
    assert resp.status_code == 302 and h['count'](event_id) == 3
    assert len(_regs_of(h, event_id, first_lead)) == 1 and len(_regs_of(h, event_id, second_lead)) == 1
    html = _page(h['owner'], event_id)    # the flash, then the page
    assert 'The event now has 3 registrations for 1 seat (2 over the limit).' in html
    summary = html[html.index('data-summary '):]
    assert '3 / 1' in summary[:summary.index('</ul>')] and '2 over the limit' in summary
    assert 'Seats: 3 of 1 taken · 2 over the limit' in html


# ── UPG-235 criterion 2: the lead is emailed that they were accepted ────────

def test_the_accepted_lead_gets_an_email_saying_they_were_accepted(host):
    h = host
    event_id = _full_event(h)
    title = h['db'].collection('events').document(event_id).get().to_dict()['title']
    wl_id, lead, mate = _join(h, event_id, 'Glad Team', full_name='Gita Glad')
    h['emails'].clear()
    _accept(h['owner'], event_id, wl_id)
    assert [e['to'] for e in h['emails']] == [lead]
    mail = h['emails'][0]
    assert mail['subject'] == f"Accepted: you're registered for {title}"
    assert 'Hi Gita Glad' in mail['message'] and 'accepted your team Glad Team' in mail['message']
    assert '/participant/dashboard' in mail['message'] and 'Hall A' in mail['message']
    # One portal notice each, not two (the shared promotion step is quiet here)
    for person in (lead, mate):
        notes = [n for n in _notices(h['db'], person) if n.get('type') == 'waitlist_promoted']
        assert len(notes) == 1, person
    html = _page(h['owner'], event_id)
    assert f'An email telling them was sent to {lead}.' in html


def test_a_paid_event_emails_the_link_to_pay(host):
    h = host
    event_id = _full_event(h, fee=200)
    wl_id, lead, _ = _join(h, event_id, 'Pay Team')
    h['emails'].clear()
    _accept(h['owner'], event_id, wl_id)
    [reg] = _regs_of(h, event_id, lead)
    [mail] = h['emails']
    assert mail['to'] == lead and mail['subject'].startswith('Accepted from the waitlist: pay to confirm')
    assert f"/payment/pay/{reg['reg_id']}" in mail['message']


def test_a_portal_mode_hackathon_still_emails_the_acceptance(host):
    h = host
    event_id = _full_event(h, event_type='hackathon', timezone='Asia/Kolkata')
    import services_hackathon as hk
    assert hk.portal_only(h['db'].collection('events').document(event_id).get().to_dict())
    wl_id, lead, _ = _join(h, event_id, 'Hack Team')
    h['emails'].clear()
    _accept(h['owner'], event_id, wl_id)
    assert [e['to'] for e in h['emails']] == [lead]
    assert 'accepted' in h['emails'][0]['message']
