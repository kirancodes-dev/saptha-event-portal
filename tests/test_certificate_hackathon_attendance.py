"""
tests/test_certificate_hackathon_attendance.py — UPG-338: on a two-day
hackathon everyone checked in is owed the participation certificate, scanned
on one day or both (the event runs straight through, so nobody is scanned on
day two). Other multi-day events still need enough of their days.
"""
import services_certificates as certs
from tests.test_certificate_issuing import site  # noqa: F401  (the UPG-124 fixture)

TWO_DAYS = {'date': '2031-05-05', 'end_date': '2031-05-06'}


def _owed(d, event_id):
    event = d['db'].collection('events').document(event_id).get().to_dict()
    return sorted(r['name'] for r in certs.recipients(d['db'], event_id, event) if r['cert_type'] == 'participation')


def _people(d, event_id):
    d['reg'](event_id, 'Day One', attendance_days=['2031-05-05'])
    d['reg'](event_id, 'Both Days', attendance_days=['2031-05-05', '2031-05-06'])
    d['reg'](event_id, 'Never Came', attendance='')
    d['reg'](event_id, 'Team Lead', attendance_days=['2031-05-05'], team_name='Builders',
             members=[{'name': 'Mate Here', 'email': 'mate.here@test.edu', 'attendance': 'Present'},
                      {'name': 'Mate Away', 'email': 'mate.away@test.edu', 'attendance': 'Absent'}])


def test_a_two_day_hackathon_counts_one_check_in_as_attended(site):  # noqa: F811
    d = site
    event_id = d['event'](event_type='hackathon', **TWO_DAYS)
    _people(d, event_id)
    assert _owed(d, event_id) == ['Both Days', 'Day One', 'Mate Here', 'Team Lead']   # not the absent
    page = d['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert 'Participation certificates only (4)' in page


def test_another_two_day_event_still_needs_both_days(site):  # noqa: F811
    d = site
    event_id = d['event'](event_type='seminar', **TWO_DAYS)
    _people(d, event_id)
    assert _owed(d, event_id) == ['Both Days']                                         # 80% of two days, as before


def test_issuing_gives_every_checked_in_hackathon_participant_theirs(site):  # noqa: F811
    d = site
    event_id = d['event'](event_type='hackathon', **TWO_DAYS)
    _people(d, event_id)
    certs.issue_event(d['db'], event_id, d['people']['owner'], only=['participation'])
    issued = sorted(c['name'] for c in certs.for_event(event_id) if c['cert_type'] == 'participation')
    assert issued == ['Both Days', 'Day One', 'Mate Here', 'Team Lead']
