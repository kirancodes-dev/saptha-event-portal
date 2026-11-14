"""
tests/test_registration_filters.py — UPG-264 on the real database layer: the
SPOC's registrations list filters by status, members' confirmation, a member
with no email, check-in, team size, the entry list and payment, the filters
combine with each other and with the search, and the list sorts.

Five teams on one event (2 to 4 people a team):
  Alpha    4 people, everyone confirmed, checked in       (registered first)
  Bravo    2 people, the member hasn't confirmed
  Charlie  3 people, one member has no email
  Delta    2 people, cancelled
  Echo     1 person (below the minimum)                   (registered last)
"""
import re

from tests.test_integration_flow import _login, _unique, _user
from tests.test_team_member_confirm import team  # noqa: F401  (fixture)

import services_team_confirm as confirm

NAMES = ('Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo')


def _five(t, **fields):
    db = t['db']
    event_id = t['event'](**fields)
    regs = {}
    for n, (name, mates) in enumerate((('Alpha', 3), ('Bravo', 1), ('Charlie', 2), ('Delta', 1), ('Echo', 1))):
        emails = t['mates'](mates)
        _, reg_id = t['register'](event_id, emails, team_name=f'{name} Squad')
        regs[name] = reg_id
        db.collection('registrations').document(reg_id).update({'registered_at': f'2026-11-0{n + 1}T10:00:00'})
        if name == 'Alpha':
            for email in emails:
                confirm.confirm(db, reg_id, email, 'link')
            db.collection('registrations').document(reg_id).update({'attendance': 'Present'})
    reg = t['reg'](regs['Charlie'])
    members = [dict(m, email='', name='No Mail') if m is reg['members'][-1] else m for m in reg['members']]
    db.collection('registrations').document(regs['Charlie']).update({'members': members})
    db.collection('registrations').document(regs['Delta']).update({'status': 'cancelled'})
    lead_only = [m for m in t['reg'](regs['Echo'])['members'] if confirm.is_lead(t['reg'](regs['Echo']), m)]
    db.collection('registrations').document(regs['Echo']).update({'members': lead_only})
    return event_id


def _shown(t, event_id, query=''):
    html = t['owner'].get(f'/coordinator/registrations/{event_id}{query}').get_data(as_text=True)
    table = html[html.index('id="registrations-heading"'):]
    table = table[table.index('data-filter-sort'):]
    found = [(table.find(f'{n} Squad'), n) for n in NAMES if f'{n} Squad' in table]
    return [n for _, n in sorted(found)], html


# ── Criterion 1: each filter keeps only its teams ──────────────────────────

def test_each_filter_keeps_only_the_teams_it_names(team):  # noqa: F811
    t = team
    event_id = _five(t)
    everyone, html = _shown(t, event_id)
    assert everyone == ['Echo', 'Delta', 'Charlie', 'Bravo', 'Alpha']        # newest first, as before
    for key in ('status', 'members', 'checkin', 'size', 'entry', 'pay', 'sort'):
        assert f'data-filter="{key}"' in html, key
    for query, expected in (
            ('?status=active', ['Echo', 'Charlie', 'Bravo', 'Alpha']),
            ('?status=cancelled', ['Delta']),
            ('?members=all_confirmed', ['Echo', 'Alpha']),
            ('?members=unconfirmed', ['Charlie', 'Bravo']),
            ('?members=no_email', ['Charlie']),
            ('?checkin=in', ['Alpha']),
            ('?checkin=out', ['Echo', 'Delta', 'Charlie', 'Bravo']),
            ('?size=below_min', ['Echo']),
            ('?size=full', ['Alpha']),
            ('?size=room', ['Echo', 'Delta', 'Charlie', 'Bravo']),
            ('?pay=paid', []),
            ('?pay=unpaid', ['Echo', 'Delta', 'Charlie', 'Bravo', 'Alpha'])):
        shown, page = _shown(t, event_id, query)
        assert shown == expected, query
        if not expected:
            assert 'No registrations match this filter.' in page


# ── Criterion 2: filters combine, with each other and with the search ──────

def test_filters_combine_with_each_other_and_the_search(team):  # noqa: F811
    t = team
    event_id = _five(t)
    shown, html = _shown(t, event_id, '?status=active&checkin=out&size=room')
    assert shown == ['Echo', 'Charlie', 'Bravo']
    assert 'Showing 3 of 5.' in html and 'data-filter-clear' in html and 'data-filter-count' in html
    assert re.search(r'<option value="active" selected>', html)
    # The search box keeps the filters, and the filter form keeps the search
    form = html[html.index('role="search"'):]
    form = form[:form.index('</form>')]
    assert 'name="status" value="active"' in form and 'name="size" value="room"' in form
    shown, html = _shown(t, event_id, '?status=active&checkin=out&q=Bravo')
    assert shown == ['Bravo'] and 'name="q" value="Bravo"' in html[html.index('data-filter-sort'):]
    # An unknown value is ignored: everything shows
    shown, _ = _shown(t, event_id, '?status=bogus&sort=sideways')
    assert shown == ['Echo', 'Delta', 'Charlie', 'Bravo', 'Alpha']


# ── Criterion 3: the list sorts ────────────────────────────────────────────

def test_the_list_sorts_by_date_name_size_and_waiting_members(team):  # noqa: F811
    t = team
    event_id = _five(t)
    assert _shown(t, event_id, '?sort=oldest')[0] == ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo']
    assert _shown(t, event_id, '?sort=team')[0] == ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo']
    assert _shown(t, event_id, '?sort=most')[0] == ['Alpha', 'Charlie', 'Delta', 'Bravo', 'Echo']
    assert _shown(t, event_id, '?sort=fewest')[0] == ['Echo', 'Delta', 'Bravo', 'Charlie', 'Alpha']
    # Most members not confirmed first (Charlie's member with no email counts)
    assert _shown(t, event_id, '?sort=waiting')[0][:1] == ['Charlie']
    assert _shown(t, event_id, '?status=active&sort=oldest')[0] == ['Alpha', 'Bravo', 'Charlie', 'Echo']


# ── Criterion 4: only what applies to the event; only the event's staff ────

def test_the_form_offers_only_what_applies_and_another_spoc_gets_403(team):  # noqa: F811
    t = team
    event_id = _five(t, member_confirm=False)
    _, html = _shown(t, event_id)
    members = html[html.index('data-filter="members"'):]
    members = members[:members.index('</select>')]
    assert 'no_email' in members and 'all_confirmed' not in members and 'unconfirmed' not in members
    other = f"{_unique('otherspoc')}@test.edu"
    _user(t['db'], other, 'ClubSPOC')
    resp = _login(t['app'], other, 'ClubSPOC').get(f'/coordinator/registrations/{event_id}?status=active')
    assert resp.status_code == 403
