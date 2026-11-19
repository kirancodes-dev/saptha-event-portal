"""
tests/test_certificate_issue_which.py — UPG-331 on the real database layer:
"Issue certificates" lets the organiser issue only the participation (or
completion) certificates, the list's first choice, or every certificate the
event owes; participation-only leaves the staff, organiser, speakers and
winners for later, and a later "every certificate" gives nobody one twice.
"""
import re

import services_certificates as certs
from tests.test_certificate_issuing import _flash, site  # noqa: F401


def _staffed_event(d, **fields):
    staff = [{'name': 'Cora', 'email': 'cora.coord@test.edu', 'role': 'EventCoordinator'}]
    event_id = d['event'](**fields)
    d['db'].collection('events').document(event_id).update({'staff': staff})
    for name in ('Asha Rao', 'Bilal Khan', 'Chitra N'):
        d['reg'](event_id, name)
    d['reg'](event_id, 'Absent Arun', attendance='Absent')
    return event_id


def test_participation_only_issues_just_the_participants_then_all_adds_the_rest(site):  # noqa: F811
    d = site
    event_id = _staffed_event(d)
    owed = {r['cert_type'] for r in certs.recipients(d['db'], event_id)}
    assert {'participation', 'organiser'} <= owed and len(owed) >= 3     # the coordinator's type too

    d['owner'].post(f'/certificates/events/{event_id}/issue', data={'which': 'participation'})
    assert 'Issuing 3 participation certificates' in _flash(d['owner'])
    got = certs.for_event(event_id)
    assert sorted(c['name'] for c in got) == ['Asha Rao', 'Bilal Khan', 'Chitra N']
    assert {c['cert_type'] for c in got} == {'participation'}

    d['owner'].post(f'/certificates/events/{event_id}/issue', data={'which': 'all'})
    got = certs.for_event(event_id)
    assert {c['cert_type'] for c in got} == owed
    assert len([c for c in got if c['cert_type'] == 'participation']) == 3      # nobody twice
    assert d['other'].post(f'/certificates/events/{event_id}/issue', data={'which': 'participation'}).status_code == 403


def test_the_list_starts_on_participation_only_with_the_counts(site):  # noqa: F811
    d = site
    event_id = _staffed_event(d)
    owed = certs.recipients(d['db'], event_id)
    html = d['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    options = re.findall(r'<option value="(participation|all)"( selected)?>([^<]*)</option>', html)
    assert [(v, bool(s)) for v, s, _ in options] == [('participation', True), ('all', False)]
    assert options[0][2] == 'Participation certificates only (3)'
    assert options[1][2].startswith(f'Every certificate the event owes ({len(owed)})')


def test_a_workshop_issues_its_completion_certificates_only(site):  # noqa: F811
    d = site
    event_id = _staffed_event(d, event_type='workshop')
    html = d['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert 'Completion certificates only (3)' in html
    d['owner'].post(f'/certificates/events/{event_id}/issue', data={'which': 'participation'})
    assert 'Issuing 3 completion certificates' in _flash(d['owner'])
    assert {c['cert_type'] for c in certs.for_event(event_id)} == {'completion'}
