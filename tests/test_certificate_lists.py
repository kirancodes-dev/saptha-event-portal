"""
tests/test_certificate_lists.py — UPG-128 on the real database layer: an
event's certificate list (25 a page, searched by name, number and type) and
its CSV and XLSX exports with the same rows; the college-wide counts per
department, event type and month.
"""
import csv
import datetime
import io
import re

import pytest

import services_certificates as certs
from tests.test_certificate_types import _signature
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user


@pytest.fixture
def site(real_app, monkeypatch):
    flask_app, db = real_app
    spoc, other = f"{_unique('lsspoc')}@test.edu", f"{_unique('lsother')}@test.edu"
    admin = f"{_unique('lsadmin')}@test.edu"
    _user(db, spoc, 'ClubSPOC', name='Lata Organiser')
    _user(db, other, 'ClubSPOC')
    _user(db, admin, 'SuperAdmin')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    monkeypatch.setattr(certs, 'render', lambda event, cert: b'%PDF-1.4 ' + cert['number'].encode())

    def event(people=0, **fields):
        import services_signatories
        event_id = _create_event(owner, db, _unique('Listed Event'), '2030-12-12', team=False)
        db.collection('events').document(event_id).update(dict({'status': 'completed', 'staff': []}, **fields))
        services_signatories.add(db, event_id, name='Dr. A. Kumar', title='Principal', image=_signature(), actor=spoc)
        for i in range(people):
            db.collection('registrations').document(_unique('REG')).set({
                'event_id': event_id, 'lead_name': f'Student {i:02d}', 'lead_email': f"{_unique('ls')}@test.edu",
                'status': 'Confirmed', 'attendance': 'Present'})
        certs.issue_event(db, event_id, spoc)
        return event_id
    admin_client = flask_app.test_client()
    admin_client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                      'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    return {'app': flask_app, 'db': db, 'owner': owner, 'other': _login(flask_app, other, 'ClubSPOC'),
            'admin': admin_client, 'event': event}


def _numbers(html):
    return re.findall(r'<code>(SE-[0-9A-Z-]+)</code>', html)


def _csv_numbers(text):
    return [row[0] for row in list(csv.reader(io.StringIO(text)))[1:]]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_list_pages_at_25_searches_and_exports_the_same_rows(site):
    import openpyxl
    d = site
    event_id = d['event'](people=59)                                           # + the organiser: 60
    url = f'/certificates/events/{event_id}/list'
    assert d['other'].get(url).status_code == 403
    pages = [d['owner'].get(f'{url}?page={n}').get_data(as_text=True) for n in (1, 2, 3)]
    assert [len(_numbers(p)) for p in pages] == [25, 25, 10]
    assert 'Showing 1–25 of 60' in pages[0] and 'Page 3 of 3' in pages[2]
    listed = [n for p in pages for n in _numbers(p)]
    assert len(set(listed)) == 60

    every = d['owner'].get(f'/certificates/events/{event_id}/export.csv')
    assert every.mimetype == 'text/csv' and sorted(_csv_numbers(every.get_data(as_text=True))) == sorted(listed)
    book = openpyxl.load_workbook(io.BytesIO(d['owner'].get(f'/certificates/events/{event_id}/export.xlsx').data))
    sheet = [list(r) for r in book['Certificates'].iter_rows(values_only=True)]
    assert sheet[0] == certs.EXPORT_COLUMNS and sorted(r[0] for r in sheet[1:]) == sorted(listed)

    student_07 = next(c for c in certs.for_event(event_id) if c['name'] == 'Student 07')
    for q, expected in (('Student 07', [student_07['number']]), (student_07['number'].lower(), [student_07['number']]),
                        ('organiser', [c['number'] for c in certs.for_event(event_id) if c['cert_type'] == 'organiser'])):
        page = d['owner'].get(f'{url}?q={q}').get_data(as_text=True)
        assert _numbers(page) == expected, q
        assert _csv_numbers(d['owner'].get(f'/certificates/events/{event_id}/export.csv?q={q}')
                            .get_data(as_text=True)) == expected, q


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_college_wide_counts_match_the_certificates_issued(site):
    d = site
    tag = _unique('Dept').upper()
    a = d['event'](people=3, department=f'{tag}-CSE', event_type='workshop')       # 3 completion + organiser
    b = d['event'](people=2, department=f'{tag}-ECE', event_type='hackathon')      # 2 participation + organiser
    moved = [c for c in certs.for_event(a) if c['cert_type'] == 'completion'][0]
    certs.update(moved['id'], issued_at=datetime.datetime(2030, 11, 5, tzinfo=datetime.timezone.utc))
    revoked = [c for c in certs.for_event(b) if c['cert_type'] == 'participation'][0]
    certs.update(revoked['id'], status='revoked')                               # revoked: not counted
    month = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m')
    mine = {(r['department'], r['event_type'], r['month']): r['certificates']
            for r in certs.college_counts(d['db']) if r['department'].startswith(tag)}
    assert mine == {(f'{tag}-CSE', 'workshop', month): 3, (f'{tag}-CSE', 'workshop', '2030-11'): 1,
                    (f'{tag}-ECE', 'hackathon', month): 2}

    assert d['owner'].get('/certificates/reports/counts').status_code == 403
    page = d['admin'].get('/certificates/reports/counts')
    assert page.status_code == 200 and f'{tag}-CSE' in page.get_data(as_text=True)
    rows = list(csv.reader(io.StringIO(d['admin'].get('/certificates/reports/counts?format=csv').get_data(as_text=True))))
    assert rows[0] == ['Department', 'Event type', 'Month', 'Certificates']
    assert [f'{tag}-ECE', 'hackathon', month, '2'] in rows
