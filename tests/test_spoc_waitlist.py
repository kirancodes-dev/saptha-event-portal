"""
tests/test_spoc_waitlist.py — UPG-230 and UPG-231 on the real database layer.

UPG-230: the SPOC's registrations page shows the event's waitlist, first in
line first, with what each person filled in; the hosting SPOC accepts anyone
on it (a free event confirms them with a ticket, a paid one holds the seat for
payment; they're told); coordinators see it without the Accept button, another
SPOC gets 403.

UPG-231: each registration (and each waitlist entry) opens to everything the
form gave: the lead's details, each member's, and every question on the form
with its label and answer.
"""
import time

from tests import test_spoc_cancel_team as _cancel
from tests.test_integration_flow import _login, _unique, _user

host = _cancel.host   # UPG-211's fixture: an event's hosting SPOC, register(), reg(), count()

# A form the SPOC built: the lead's USN and phone asked by hand (random ids,
# as the builder saves them), a question of the SPOC's own and a heading
FORM = [
    {'id': 'full_name', 'type': 'text', 'label': 'Full Name', 'required': True},
    {'id': 'email', 'type': 'email', 'label': 'Email Address', 'required': True},
    {'id': 'f_usn001', 'type': 'text', 'label': 'USN'},
    {'id': 'f_mob001', 'type': 'tel', 'label': 'Phone Number'},
    {'id': 'f_head01', 'type': 'heading', 'label': 'About your project'},
    {'id': 'f_idea01', 'type': 'text', 'label': 'Project idea'},
    {'id': 'f_tshi01', 'type': 'text', 'label': 'T-shirt size'},
]


def _page(client, event_id):
    resp = client.get(f'/coordinator/registrations/{event_id}')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _full_event(h, **fields):
    """An event whose one seat is taken, so the form puts people on the waitlist."""
    event_id = h['event'](**fields)
    limits = h['db'].collection('events').document(event_id).get().to_dict().get('limits') or {}
    h['db'].collection('events').document(event_id).update({'limits': dict(limits, max_participants=1)})
    if fields.get('fee'):   # a paid team holds its seat only once it has paid: count it as taken
        h['db'].collection('events').document(event_id).update({'registration_count': 1})
    else:
        h['register'](event_id, team_name='Seat Takers')
    assert h['count'](event_id) == 1
    return event_id


def _join(h, event_id, team_name, full_name='Wanda Wait', **extra):
    lead, mate = f"{_unique('wlead')}@test.edu", f"{_unique('wmate')}@test.edu"
    resp = h['app'].test_client().post(f'/forms/submit/{event_id}', data=dict({
        'privacy_consent': 'yes', 'full_name': full_name, 'email': lead, 'phone': '9123456780',
        'usn': '1SN22CS410', 'team_name': team_name,
        'member_1_name': 'Max Mate', 'member_1_email': mate, 'member_1_usn': '1SN22CS411'}, **extra))
    assert resp.status_code == 302, resp.data[:300]
    [wl_id] = [d.id for d in h['db'].collection('waitlists').where('event_id', '==', event_id).stream()
               if d.to_dict().get('email') == lead]
    time.sleep(0.01)                                   # distinct join times
    return wl_id, lead, mate


def _entry(h, wl_id):
    return h['db'].collection('waitlists').document(wl_id).get().to_dict()


def _regs_of(h, event_id, lead):
    return [dict(d.to_dict(), id=d.id) for d in h['db'].collection('registrations')
            .where('event_id', '==', event_id).stream() if d.to_dict().get('lead_email') == lead]


def _accept(client, event_id, wl_id):
    return client.post(f'/coordinator/registrations/{event_id}/accept_waitlist', data={'wl_id': wl_id})


def _notices(db, email):
    return [n.to_dict() for n in db.collection('notifications_v2').stream() if n.to_dict().get('user_email') == email]


# ── UPG-230 criterion 1: the waitlist shows on the SPOC's page ──────────────

def test_the_page_lists_the_waitlist_in_line_with_what_each_person_filled_in(host):
    h = host
    event_id = _full_event(h)
    first, first_lead, _ = _join(h, event_id, 'First Wait', full_name='Fay First')
    second, second_lead, _ = _join(h, event_id, 'Second Wait', full_name='Sid Second')
    html = _page(h['owner'], event_id)

    assert 'data-waitlist' in html and 'Waitlist: 2 waiting' in html
    assert 'data-waitlist-count>2 on the waitlist<' in html
    assert html.index(f'data-waitlist-entry="{first}"') < html.index(f'data-waitlist-entry="{second}"')
    row = html[html.index(f'data-waitlist-entry="{first}"'):]
    row = row[:row.index('</tr>')]
    assert '#1' in row and 'First Wait' in row and 'Fay First' in row and first_lead in row
    assert 'data-waitlist-fee>Free<' in row
    assert '9123456780' in row and '1SN22CS410' in row and '2 members' in row
    second_row = html[html.index(f'data-waitlist-entry="{second}"'):]
    assert '#2' in second_row[:second_row.index('</tr>')]
    # Its details open under it: the member's USN and email too
    details = html[html.index(f'id="wl-details-{first}"'):]
    details = details[:details.index('</tr>')]
    assert 'Max Mate' in details and '1SN22CS411' in details
    # One seat, taken: the page says the event is full
    assert '1 seats · full' in html


def test_an_event_nobody_waits_for_says_so(host):
    h = host
    event_id = h['event']()
    h['register'](event_id)
    html = _page(h['owner'], event_id)
    assert 'data-waitlist-empty' in html and 'Waitlist: 0 waiting' in html and 'data-accept-waitlist' not in html


def test_someone_who_joined_from_the_event_page_shows_with_name_email_and_phone(host):
    h = host
    db = host['db']
    event_id = _full_event(h)
    email = f"{_unique('json')}@test.edu"
    _user(db, email, 'Student', name='Jo Json')
    resp = _login(h['app'], email, 'Student').post(f'/waitlist/join/{event_id}',
                                                    json={'name': 'Jo Json', 'phone': '9000011111'})
    assert resp.status_code == 201, resp.data
    html = _page(h['owner'], event_id)
    wl_id = resp.get_json()['waitlist_id']
    row = html[html.index(f'data-waitlist-entry="{wl_id}"'):]
    row = row[:row.index('</tr>')]
    assert 'Jo Json' in row and email in row and '9000011111' in row


# ── UPG-230 criterion 2: the hosting SPOC accepts anyone on it ──────────────

def test_the_hosting_spoc_accepts_the_second_in_line_on_a_free_event(host):
    h = host
    db = host['db']
    event_id = _full_event(h)
    first, first_lead, _ = _join(h, event_id, 'First Wait')
    second, second_lead, _ = _join(h, event_id, 'Second Wait')
    html = _page(h['owner'], event_id)
    assert f'data-bs-target="#accept-{second}"' in html and 'data-accept-form' in html
    # The dialog says no seat is free before they press it
    dialog = html[html.index(f'id="accept-{second}"'):]
    assert 'data-over-capacity' in dialog[:dialog.index('</form>')]

    resp = _accept(h['owner'], event_id, second)
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/coordinator/registrations/{event_id}')
    [reg] = _regs_of(h, event_id, second_lead)
    assert reg['status'] == 'Confirmed' and reg['source'] == 'waitlist_promotion'
    assert reg['team_name'] == 'Second Wait' and reg['lead_usn'] == '1SN22CS410'   # what they filled in
    assert list(db.collection('tickets').where('registration_id', '==', reg['id']).stream())
    assert _entry(h, second)['status'] == 'promoted'
    assert _entry(h, first)['status'] == 'waiting'                     # the first still waits, now alone
    assert h['count'](event_id) == 2
    assert any(n.get('type') == 'waitlist_promoted' for n in _notices(db, second_lead))
    assert any(a.to_dict().get('action') == 'WAITLIST_ACCEPTED' and second_lead in a.to_dict().get('details', '')
               and h['spoc'] in a.to_dict().get('details', '') for a in db.collection('audit_log').stream())

    html = _page(h['owner'], event_id)
    assert f'data-waitlist-entry="{second}"' not in html and 'Waitlist: 1 waiting' in html
    first_row = html[html.index(f'data-waitlist-entry="{first}"'):]
    assert '#1' in first_row[:first_row.index('</tr>')]
    assert f'data-reg="{reg["id"]}"' in html                          # now in the registrations


def test_on_a_paid_event_the_accepted_team_is_sent_a_pay_link(host):
    h = host
    db = host['db']
    event_id = _full_event(h, fee=200, entry_fee=200)
    wl_id, lead, _ = _join(h, event_id, 'Payers')
    html = _page(h['owner'], event_id)
    row = html[html.index(f'data-waitlist-entry="{wl_id}"'):]
    assert 'data-waitlist-fee>Pays to confirm<' in row[:row.index('</tr>')]
    dialog = html[html.index(f'id="accept-{wl_id}"'):]
    assert 'sent a link to pay' in dialog[:dialog.index('</form>')]
    assert _accept(h['owner'], event_id, wl_id).status_code == 302
    [reg] = _regs_of(h, event_id, lead)
    assert reg['status'] == 'pending_payment' and reg['payment_status'] == 'Pending'
    assert not list(db.collection('tickets').where('registration_id', '==', reg['id']).stream())
    assert any(n.get('link') == f"/payment/pay/{reg['reg_id']}" for n in _notices(db, lead))


# ── UPG-230 criterion 3: only the hosting SPOC, once, for this event ────────

def test_coordinators_see_the_waitlist_without_accept_and_another_spoc_gets_403(host):
    h = host
    db, flask_app = host['db'], host['app']
    event_id = _full_event(h)
    wl_id, lead, _ = _join(h, event_id, 'Waiters')

    coord = f"{_unique('coord')}@test.edu"
    _user(db, coord, 'EventCoordinator')
    db.collection('events').document(event_id).update({'coordinators': [coord]})
    coord_c = _login(flask_app, coord, 'EventCoordinator')
    html = _page(coord_c, event_id)
    assert f'data-waitlist-entry="{wl_id}"' in html and 'data-accept-waitlist' not in html
    assert _accept(coord_c, event_id, wl_id).status_code == 403

    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    other_c = _login(flask_app, other, 'ClubSPOC')
    assert _accept(other_c, event_id, wl_id).status_code == 403
    assert other_c.get(f'/coordinator/registrations/{event_id}').status_code == 403
    assert _entry(h, wl_id)['status'] == 'waiting' and not _regs_of(h, event_id, lead)


def test_accepting_twice_another_events_entry_or_someone_already_registered_changes_nothing(host):
    h = host
    db = host['db']
    event_id = _full_event(h)
    wl_id, lead, _ = _join(h, event_id, 'Twice')
    assert _accept(h['owner'], event_id, wl_id).status_code == 302
    count = h['count'](event_id)
    assert _accept(h['owner'], event_id, wl_id).status_code == 302       # no longer waiting
    assert len(_regs_of(h, event_id, lead)) == 1 and h['count'](event_id) == count

    other_event = _full_event(h)
    other_wl, other_lead, _ = _join(h, other_event, 'Elsewhere')
    assert _accept(h['owner'], event_id, other_wl).status_code == 302     # not this event's
    assert _entry(h, other_wl)['status'] == 'waiting' and not _regs_of(h, other_event, other_lead)

    # Someone who registered another way meanwhile is taken off the line, not registered twice
    third, third_lead, _ = _join(h, event_id, 'Already In')
    db.collection('registrations').document(_unique('REG')).set({
        'event_id': event_id, 'lead_email': third_lead, 'lead_name': 'Al Ready', 'status': 'Confirmed'})
    count = h['count'](event_id)
    assert _accept(h['owner'], event_id, third).status_code == 302
    assert _entry(h, third)['status'] == 'already_registered'
    assert len(_regs_of(h, event_id, third_lead)) == 1 and h['count'](event_id) == count


def test_the_spoc_dashboard_names_the_waitlist(host):
    h = host
    event_id = h['event']()
    html = h['owner'].get('/spoc/dashboard').get_data(as_text=True)
    link = html[html.index(f'href="/coordinator/registrations/{event_id}"'):]
    assert 'Waitlist' in link[:link.index('</a>')]


# ── UPG-231: every detail the form gave, on the SPOC's page ─────────────────

def test_each_registration_opens_to_every_detail_the_form_gave(host):
    h = host
    db = host['db']
    event_id = h['event']()
    db.collection('event_forms').document(event_id).set({'fields': FORM})
    reg_id = _unique('REG')
    db.collection('registrations').document(reg_id).set({
        'reg_id': reg_id, 'event_id': event_id, 'lead_name': 'Lena Lead', 'lead_email': 'lena@test.edu',
        'lead_usn': '', 'lead_phone': '', 'team_name': 'Apex.devs', 'registered_at': '2026-11-10 05:46:17',
        'participant_type': 'student', 'ticket_type_name': 'Early bird',
        'members': [{'role': 'Lead', 'name': 'Lena Lead', 'email': 'lena@test.edu'},
                    {'role': 'Member', 'name': 'Hima TS', 'email': 'hima@test.edu', 'usn': '25SUUBEAML231',
                     'phone': '9000000003'}],
        'form_answers': {'full_name': 'Lena Lead', 'email': 'lena@test.edu', 'f_usn001': '25suubeaml013',
                         'f_mob001': '9000000001', 'f_idea01': 'A study planner',
                         'f_gone01': 'Answer to a removed question'},
        'attendance': 'Pending', 'payment_status': 'Free'})
    [reg_id] = [d.id for d in db.collection('registrations').where('event_id', '==', event_id).stream()]
    html = _page(h['owner'], event_id)
    assert 'data-details-all' in html
    row = html[html.index(f'data-reg="{reg_id}"'):]
    assert f'data-bs-target="#details-{reg_id}"' in row[:row.index('</tr>')]
    details = html[html.index(f'data-details-row="{reg_id}"'):]
    details = details[:details.index('</tr>')]

    # The lead: USN and phone from the questions asked by hand, department and year from the USN
    for text in ('25SUUBEAML013', '9000000001', '>AML<', '>2025<', 'Early bird', 'lena@test.edu'):
        assert text in details, text
    # Each member's own details
    assert 'Hima TS' in details and '25SUUBEAML231' in details and 'hima@test.edu' in details
    assert '9000000003' in details
    # Every question on the form, by its label, in order; unanswered ones say so
    questions = [q for q in ('Project idea', 'T-shirt size') if q in details]
    assert questions == ['Project idea', 'T-shirt size']
    assert details.index('Project idea') < details.index('A study planner') < details.index('T-shirt size')
    tshirt = details[details.index('T-shirt size'):]
    assert 'Not answered' in tshirt[:tshirt.index('</dd>')]
    assert 'f_gone01 (no longer on the form)' in details and 'Answer to a removed question' in details
    assert 'About your project' not in details                       # a heading isn't a question
    # The USN and phone questions aren't listed twice
    assert details.count('9000000001') == 1


def test_a_registration_from_the_form_shows_its_own_answers(host):
    h = host
    db = host['db']
    event_id = h['event']()
    reg_id, lead, mate = h['register'](event_id)
    db.collection('registrations').document(reg_id).update(
        {'form_answers': dict(h['reg'](reg_id).get('form_answers') or {}, f_diet01='Vegetarian')})
    html = _page(h['owner'], event_id)
    details = html[html.index(f'data-details-row="{reg_id}"'):]
    details = details[:details.index('</tr>')]
    for text in ('Lena Lead', '1SN22CS300', '9876543210', lead, 'Mo Mate', '1SN22CS301', mate, 'Vegetarian'):
        assert text in details, text
