"""
tests/test_event_summary.py — UPG-273 on the real database layer: the event
summary report gives registrations, attendance and no-shows, results, feedback
and certificates for each event; its figures are the numbers of records behind
them; it filters by event date, category and event; it says what each column
counts; its files carry the same figures; and each person sees only the events
they may see the figures of.
"""
import csv
import datetime
import io
import re

import pytest

import services_certificates as certs
import services_summary as summary
from tests import test_certificate_lists as _lists
from tests.test_integration_flow import _create_event, _login, _unique, _user

site = _lists.site
PAST, FUTURE = '2026-03-10', '2030-12-12'


def _add(db, event_id, n, **fields):
    made = []
    for _ in range(n):
        reg_id = _unique('REG')
        db.collection('registrations').document(reg_id).set(dict(
            {'event_id': event_id, 'lead_name': f"Person {_unique('p')}", 'lead_email': f"{_unique('es')}@test.edu",
             'status': 'Confirmed'}, **fields))
        made.append(reg_id)
    return made


@pytest.fixture
def report(site):
    """A finished event with every kind of record, an event still to come,
    and another organiser's event."""
    d = site
    db = d['db']
    tag = _unique('Cat')
    held = d['event'](people=0, date=PAST, end_date=PAST, category=tag, results_published=True)        # the organiser's own certificate
    present = _add(db, held, 5, attendance='Present')
    _add(db, held, 1, status='checked_in')
    _add(db, held, 2)                                               # confirmed, never came
    _add(db, held, 1, status='Waitlisted')
    _add(db, held, 1, status='Pending')
    _add(db, held, 2, status='Cancelled')
    for reg_id, score in zip(present, (90, 80, 80, 70, 60)):        # 1st, two share 2nd, 4th, 5th
        db.collection('registrations').document(reg_id).update({'scores': {'j@test.edu': {'total': score}}})
    certs.issue_event(db, held, 'tester')
    for n, rating in enumerate((5, 4, 2)):
        db.collection('feedback_responses').document(f'{held}:{present[n]}:x{n}@test.edu').set(
            {'event_id': held, 'reg_id': present[n], 'email': f'x{n}@test.edu', 'rating': rating, 'comments': 'ok'})
    db.collection('registrations').document(present[4]).update({'feedback': {'rating': 3, 'comments': 'old way'}})

    coming = d['event'](people=0, date=FUTURE, category=tag, status='registration_open')
    _add(db, coming, 3)
    _add(db, coming, 1, status='Cancelled')

    other_spoc = f"{_unique('esother')}@test.edu"
    _user(db, other_spoc, 'ClubSPOC')
    theirs = _create_event(_login(d['app'], other_spoc, 'ClubSPOC'), db, _unique('Their Event'), PAST, team=False)
    db.collection('events').document(theirs).update({'category': tag})
    _add(db, theirs, 4, attendance='Present')
    d.update(held=held, coming=coming, theirs=theirs, tag=tag, present=present)
    return d


def _row(html, event_id):
    """One event's figures as the page shows them: {column: text}."""
    found = re.search(r'<tr data-event="%s">(.*?)</tr>' % re.escape(event_id), html, re.S)
    assert found, f'no row for {event_id}'
    return {k: ' '.join(re.sub(r'<[^>]+>', ' ', v).split())
            for k, v in re.findall(r'data-k="(\w+)">(.*?)</td>', found.group(1), re.S)}


def _total(html):
    found = re.search(r'<tr data-total>(.*?)</tr>', html, re.S)
    return {k: ' '.join(re.sub(r'<[^>]+>', ' ', v).split())
            for k, v in re.findall(r'data-k="(\w+)">(.*?)</td>', found.group(1), re.S)}


def _page(d, who='owner', **query):
    query.setdefault('category', d['tag'])
    return d[who].get('/reports/events', query_string=query).get_data(as_text=True)


# ── Criterion 1: every figure is the number of records behind it ────────────

def test_each_figure_is_the_number_of_records_the_lists_show(report):
    import routes_feedback
    d = report
    db = d['db']
    page = _page(d)
    held, coming = _row(page, d['held']), _row(page, d['coming'])
    assert held == {'registrations': '12', 'confirmed': '8', 'waitlisted': '1', 'pending': '1', 'cancelled': '2',
                    'attended': '6', 'not_selected': '0', 'no_shows': '2', 'attendance_rate': '75.0%',
                    'results': 'Yes', 'placed': '3', 'feedback': '4', 'rating': '3.5',
                    'certificates': held['certificates']}
    # the same numbers, counted straight from the records
    records = [r.to_dict() for r in db.collection('registrations').where('event_id', '==', d['held']).stream()]
    assert len(records) == 12
    assert sum(1 for r in records if r.get('attendance') == 'Present' or r['status'] == 'checked_in') == 6
    assert len(routes_feedback.event_responses(d['held'])) == 4
    exported = d['owner'].get(f"/feedback/export/{d['held']}").get_data(as_text=True)
    assert len(list(csv.reader(io.StringIO(exported)))) - 1 == 4
    valid = [c for c in certs.for_event(d['held']) if c['status'] == 'valid']
    assert int(held['certificates']) == len(valid) >= 6
    listed = d['owner'].get(f"/certificates/events/{d['held']}/export.csv").get_data(as_text=True)
    assert len(list(csv.reader(io.StringIO(listed)))) - 1 == len(valid)
    # what the columns promise: the parts add up
    n = {k: int(v) for k, v in held.items() if v.isdigit()}
    assert n['registrations'] == n['confirmed'] + n['waitlisted'] + n['pending'] + n['cancelled']
    assert n['confirmed'] == n['attended'] + n['no_shows'] + n['not_selected']

    # an event still to come has no no-shows and no rate yet
    assert coming['registrations'] == '4' and coming['confirmed'] == '3' and coming['cancelled'] == '1'
    assert coming['no_shows'] == '—' and coming['attendance_rate'] == '—' and coming['rating'] == '—'
    assert coming['results'] == 'No' and coming['placed'] == '0' and coming['feedback'] == '0'

    # the total row is the sum of the rows shown
    total = _total(page)
    for key in ('registrations', 'confirmed', 'waitlisted', 'pending', 'cancelled', 'attended', 'placed', 'feedback', 'certificates'):
        assert int(total[key]) == int(held[key]) + int(coming[key]), key
    assert total['no_shows'] == '2' and total['attendance_rate'] == '75.0%' and total['results'] == '1 of 2'
    assert total['rating'] == '3.5' and 'Total: 2 events, 1 finished' in page

    # a record changes, the report follows: one no-show is marked present, a certificate is revoked
    late = next(r.id for r in db.collection('registrations').where('event_id', '==', d['held']).stream()
                if r.to_dict()['status'] == 'Confirmed' and r.to_dict().get('attendance') != 'Present')
    db.collection('registrations').document(late).update({'attendance': 'Present'})
    certs.update(valid[0]['id'], status='revoked')
    again = _row(_page(d), d['held'])
    assert again['attended'] == '7' and again['no_shows'] == '1' and again['attendance_rate'] == '87.5%'
    assert int(again['certificates']) == len(valid) - 1


def test_a_team_left_off_the_entry_list_is_not_a_no_show(report):
    import services_entry
    d = report
    d['db'].collection('events').document(d['held']).update({services_entry.SWITCH: True})
    for reg_id in d['present']:
        d['db'].collection('registrations').document(reg_id).update({services_entry.FIELD: True})
    row = _row(_page(d), d['held'])
    # the 2 confirmed registrations that never came were not selected: not expected, not no-shows
    assert row['not_selected'] == '2' and row['no_shows'] == '0' and row['attended'] == '6'
    assert row['attendance_rate'] == '100.0%' and row['confirmed'] == '8'


# ── Criterion 2: date range, category and event filters ─────────────────────

def test_the_report_filters_by_event_date_category_and_event(report):
    d = report
    both = _page(d)
    assert f'data-event="{d["held"]}"' in both and f'data-event="{d["coming"]}"' in both
    past = _page(d, **{'from': '2026-01-01', 'to': '2026-12-31'})
    assert f'data-event="{d["held"]}"' in past and f'data-event="{d["coming"]}"' not in past
    assert 'Events from 1 January 2026 to 31 December 2026' in past and 'Total: 1 event, 1 finished' in past
    assert _total(past)['registrations'] == '12'
    edge = _page(d, **{'from': PAST, 'to': PAST})                    # the range includes both ends
    assert f'data-event="{d["held"]}"' in edge
    later = _page(d, **{'from': '2026-03-11'})
    assert f'data-event="{d["held"]}"' not in later and f'data-event="{d["coming"]}"' in later
    assert 'Events on or after 11 March 2026' in later
    one = _page(d, event=d['coming'])
    assert f'data-event="{d["coming"]}"' in one and f'data-event="{d["held"]}"' not in one and 'one event' in one
    assert 'data-no-events' in _page(d, category=_unique('Nothing'))
    # the filters stay filled in, and the files follow them
    assert 'name="from" value="2026-01-01"' in past and 'name="to" value="2026-12-31"' in past
    assert re.search(r'href="/reports/events\.csv\?[^"]*from=2026-01-01', past)

    swapped = _page(d, **{'from': '2026-12-31', 'to': '2026-01-01'})
    assert 'The From date is after the To date, so they were swapped.' in swapped and f'data-event="{d["held"]}"' in swapped
    odd = _page(d, **{'from': 'yesterday'})
    assert 'isn&#39;t a date' in odd or "isn't a date" in odd
    assert f'data-event="{d["held"]}"' in odd and f'data-event="{d["coming"]}"' in odd


def test_filters_read_and_described():
    f = summary.read_filters({'from': '2026-04-01', 'to': '2027-03-31', 'category': ' Technical '})
    assert f['from'] == datetime.date(2026, 4, 1) and f['to'] == datetime.date(2027, 3, 31) and f['problems'] == []
    assert summary.describe(f) == ("Events from 1 April 2026 to 31 March 2027, category Technical. "
                                   "Dates are the day each event starts.")
    assert summary.describe(summary.read_filters({})).startswith('Events on any date.')
    assert len(summary.read_filters({'from': '31/03/2027', 'to': 'x'})['problems']) == 2


# ── Criterion 3: each column says what it counts ────────────────────────────

def test_the_page_and_the_files_say_what_each_column_counts(report):
    import openpyxl
    d = report
    page = _page(d)
    definitions = page.split('data-definitions')[1]
    for _, heading, text in summary.DEFINITIONS:
        assert f'<dt>{heading}</dt>' in definitions
        assert text[:40].replace("'", '&#39;') in definitions or text[:40] in definitions
    assert 'payments are not in this report' in page
    listed = list(csv.reader(io.StringIO(d['owner'].get('/reports/events/definitions.csv').get_data(as_text=True))))
    assert listed[0] == ['Column', 'What it counts'] and [r[0] for r in listed[1:]] == [h for _, h, _ in summary.DEFINITIONS]
    book = openpyxl.load_workbook(io.BytesIO(d['owner'].get('/reports/events.xlsx', query_string={'category': d['tag']}).data))
    assert book.sheetnames == ['Event summary', 'What the columns count']
    sheet = [list(r) for r in book['What the columns count'].iter_rows(values_only=True)]
    assert sheet[1][0] == 'This report' and 'Events on any date' in sheet[1][1] and len(sheet) == 2 + len(summary.DEFINITIONS)


# ── Criterion 4: the files carry the page's figures ─────────────────────────

def test_the_csv_and_excel_files_have_the_same_rows_and_total_as_the_page(report):
    import openpyxl
    d = report
    page = _page(d)
    held, total = _row(page, d['held']), _total(page)
    resp = d['owner'].get('/reports/events.csv', query_string={'category': d['tag']})
    assert resp.mimetype == 'text/csv' and 'filename=event-summary.csv' in resp.headers['Content-Disposition']
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert rows[0] == summary.COLUMNS and len(rows) == 4                 # heading, two events, the total
    by_key = dict(zip([k for k, _, _ in summary.DEFINITIONS], rows[1][4:]))
    assert rows[1][1] == PAST and rows[1][2] == d['tag']
    for key in ('registrations', 'confirmed', 'waitlisted', 'pending', 'cancelled', 'attended', 'no_shows', 'placed',
                'feedback', 'certificates'):
        assert by_key[key] == held[key], key
    assert by_key['attendance_rate'] == '75.0' and by_key['results'] == 'Yes' and by_key['rating'] == '3.5'
    assert rows[2][11] == '' and rows[2][12] == ''                       # not counted yet: blank, not 0
    last = dict(zip([k for k, _, _ in summary.DEFINITIONS], rows[3][4:]))
    assert rows[3][0] == 'Total (2 events)' and last['registrations'] == total['registrations'] == '16'
    assert last['certificates'] == total['certificates'] and last['results'] == '1'

    book = openpyxl.load_workbook(io.BytesIO(d['owner'].get('/reports/events.xlsx', query_string={'category': d['tag']}).data))
    sheet = [['' if v is None else str(v) for v in r] for r in book['Event summary'].iter_rows(values_only=True)]
    assert sheet[0] == summary.COLUMNS and [r[4] for r in sheet[1:]] == ['12', '4', '16']

    ranged = d['owner'].get('/reports/events.csv', query_string={'category': d['tag'], 'from': '2026-01-01', 'to': '2026-12-31'})
    assert 'filename=event-summary-from-2026-01-01-to-2026-12-31.csv' in ranged.headers['Content-Disposition']
    assert len(list(csv.reader(io.StringIO(ranged.get_data(as_text=True))))) == 3
    audit = [a.to_dict() for a in d['db'].collection('audit_log').where('action', '==', 'REPORT_EXPORTED').stream()]
    assert any('event summary (csv)' in str(a.get('details')) for a in audit)
    assert d['owner'].get('/reports/events.pdf').status_code == 404


# ── Criterion 5: each person sees their own events' figures ─────────────────

def test_an_organiser_sees_their_events_and_the_admin_sees_all(report):
    d = report
    mine = _page(d)
    assert f'data-event="{d["theirs"]}"' not in mine and 'The events you can see the figures of' in mine
    assert d['theirs'] not in d['owner'].get('/reports/events.csv', query_string={'category': d['tag']}).get_data(as_text=True)
    assert f'data-event="{d["theirs"]}"' not in _page(d, event=d['theirs'])      # asking for it by ID changes nothing
    everything = _page(d, who='admin')
    for event_id in (d['held'], d['coming'], d['theirs']):
        assert f'data-event="{event_id}"' in everything
    assert _total(everything)['registrations'] == '20' and 'Every event' in everything
    elsewhere = _page(d, who='other')                                # another organiser: none of these
    for event_id in (d['held'], d['coming'], d['theirs']):
        assert f'data-event="{event_id}"' not in elsewhere

    student = f"{_unique('esstudent')}@test.edu"
    _user(d['db'], student, 'Student')
    learner = _login(d['app'], student, 'Student')
    for path in ('/reports/events', '/reports/events.csv', '/reports/events.xlsx', '/reports/events/definitions.csv'):
        assert learner.get(path).status_code in (302, 403), path
        assert d['app'].test_client().get(path).status_code in (302, 401), path
    # the links that lead here
    assert 'href="/reports/events"' in d['admin'].get('/admin/analytics').get_data(as_text=True)
    assert 'data-summary-link' in d['owner'].get('/spoc/analytics').get_data(as_text=True)
