"""
tests/test_exports.py — UPG-03 on the real database layer: one export of an
event's registrations (CSV and Excel) for the SPOC, coordinator and admin, a
one-click event report, and 403 for anyone without export_data on the event.
"""
import csv
import datetime
import io

import openpyxl
import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def ev(real_app):
    """An event with a team registration (Present) and a paid one, plus the
    owner, an assigned and an unassigned coordinator, another SPOC and a student."""
    flask_app, db = real_app
    p = {k: f"{_unique(k)}@test.edu" for k in ('owner', 'other_spoc', 'coord_in', 'coord_out', 'student', 'tara', 'paul')}
    for key, role in (('owner', 'ClubSPOC'), ('other_spoc', 'ClubSPOC'), ('coord_in', 'EventCoordinator'),
                      ('coord_out', 'EventCoordinator'), ('student', 'Student')):
        _user(db, p[key], role)
    _user(db, p['tara'], 'Student')
    db.collection('users').document(p['tara']).update({'department': 'CSE'})
    owner = _login(flask_app, p['owner'], 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Export Fest'), datetime.date.today().isoformat(), fee=200, team=True)
    db.collection('events').document(event_id).update({
        'staff': [{'email': p['coord_in'], 'name': 'Coord', 'role': 'EventCoordinator'}]})
    team = _unique('REG')
    db.collection('registrations').document(team).set({
        'reg_id': team, 'event_id': event_id, 'lead_name': 'Tara Team', 'lead_email': p['tara'],
        'lead_phone': '9876500001', 'lead_usn': '1SN22CS001', 'team_name': 'Byte Force',
        'members': [{'name': 'Tara Team', 'email': p['tara'], 'usn': '1SN22CS001'},
                    {'name': 'Mo Member', 'email': 'mo@test.edu', 'usn': '1SN22CS002'}],
        'attendance': 'Present', 'checkin_time': '09:30:00', 'payment_status': 'Paid', 'amount_paid': 200,
        'scores': {'j@test.edu': {'total': 8}}, 'certificate_id': 'abc123', 'registered_at': '2026-10-01 10:00:00',
        'feedback': {'rating': 4}})
    paid = _unique('REG')
    db.collection('registrations').document(paid).set({
        'reg_id': paid, 'event_id': event_id, 'lead_name': '=HYPERLINK("http://evil.example","Paul")',
        'lead_email': p['paul'], 'lead_phone': '+91 98765 00002', 'lead_usn': '1SN23EC010', 'team_name': 'Solo Stars',
        'members': [], 'attendance': 'Pending', 'payment_status': 'Paid (Stripe)', 'amount_paid': 200,
        'registered_at': '2026-10-02 11:00:00'})
    return {'app': flask_app, 'db': db, 'p': p, 'event_id': event_id, 'owner': owner, 'team': team, 'paid': paid}


def _csv(resp):
    assert resp.status_code == 200 and resp.mimetype == 'text/csv', resp.status_code
    return list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))


def _xlsx(resp, sheet=None):
    assert resp.status_code == 200 and resp.mimetype.endswith('spreadsheetml.sheet'), resp.status_code
    wb = openpyxl.load_workbook(io.BytesIO(resp.data))
    ws = wb[sheet] if sheet else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    return [dict(zip(rows[0], r)) for r in rows[1:]]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_every_export_gives_both_registrations_with_real_columns(ev):
    e = ev['event_id']
    coord = _login(ev['app'], ev['p']['coord_in'], 'EventCoordinator')
    exports = {
        'spoc csv': _csv(ev['owner'].get(f'/spoc/export_csv/{e}')),
        'spoc excel': _xlsx(ev['owner'].get(f'/spoc/export_excel/{e}')),
        'coordinator csv': _csv(coord.get(f'/coordinator/export_registrations/{e}')),
        'coordinator excel': _xlsx(coord.get(f'/coordinator/export_excel/{e}')),
    }
    for name, rows in exports.items():
        assert len(rows) == 2, name
        for row in rows:
            for column in ('Lead Name', 'Lead Email', 'Lead Phone', 'Team', 'Attendance', 'Payment Status', 'Lead USN',
                           'Department', 'Year'):
                assert str(row[column] or '').strip(), (name, column, row)
        team = next(r for r in rows if r['Team'] == 'Byte Force')
        assert team['Lead Name'] == 'Tara Team' and team['Department'] == 'CSE' and team['Year'] == '2022'
        assert 'Mo Member (1SN22CS002)' in team['Members'] and team['Attendance'] == 'Present'
        assert str(team['Score']) in ('8', '8.0') and str(team['Rank']) == '1' and team['Certificate ID'] == 'abc123'
        solo = next(r for r in rows if r['Team'] == 'Solo Stars')
        assert solo['Department'] == 'EC' and solo['Year'] == '2023'
        assert solo['Payment Status'] == 'Paid (Stripe)' and str(solo['Amount (Rs)']) == '200'
        assert solo['Lead Phone'] == '+91 98765 00002'
        assert solo['Lead Name'].startswith("'=")  # a name a spreadsheet would run is quoted

    admin = f"{_unique('exportadmin')}@test.edu"
    _user(ev['db'], admin, 'SuperAdmin')
    client = ev['app'].test_client()
    client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': 'Str0ng!Pass#1',
                                'secret_key': ev['app'].config.get('MASTER_SECRET_KEY', '')})
    rows = [r for r in _csv(client.get('/admin/analytics/export/registrations')) if r['Ticket ID'] in (ev['team'], ev['paid'])]
    assert len(rows) == 2 and all(r['Event'] and r['Lead Email'] and r['Payment Status'] for r in rows)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('who', ['other_spoc', 'coord_out', 'student'])
def test_nobody_without_export_rights_gets_any_export(ev, who):
    role = {'other_spoc': 'ClubSPOC', 'coord_out': 'EventCoordinator', 'student': 'Student'}[who]
    client = _login(ev['app'], ev['p'][who], role)
    e = ev['event_id']
    for url in (f'/spoc/export_csv/{e}', f'/spoc/export_excel/{e}', f'/spoc/event_report/{e}',
                f'/coordinator/export_registrations/{e}', f'/coordinator/export_excel/{e}',
                f'/forms/responses/export/{e}', '/admin/analytics/export/registrations'):
        resp = client.get(url)
        assert resp.status_code == 403, (who, url, resp.status_code)
        assert 'Tara Team' not in resp.get_data(as_text=True)


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_report_counts_attendance_by_department_and_year(ev):
    db, e = ev['db'], ev['event_id']
    extra = _unique('REG')
    db.collection('registrations').document(extra).set({
        'reg_id': extra, 'event_id': e, 'lead_name': 'Ivy Present', 'lead_email': 'ivy@test.edu',
        'lead_usn': '1SN22ME005', 'attendance': 'Present', 'payment_status': 'Paid', 'feedback': {'rating': 5}})
    present = sum(1 for d in db.collection('registrations').where('event_id', '==', e).stream()
                  if (d.to_dict() or {}).get('attendance') == 'Present')
    assert present == 2

    resp = ev['owner'].get(f'/spoc/event_report/{e}')
    summary = {r['Item']: r['Value'] for r in _xlsx(resp, 'Summary')}
    assert summary['Registered'] == 3 and summary['Present'] == present
    assert summary['Average feedback rating'] == 4.5 and summary['Feedback responses'] == 2
    by_dept = {r['Department']: (r['Registered'], r['Present']) for r in _xlsx(resp, 'By department')}
    assert by_dept == {'CSE': (1, 1), 'EC': (1, 0), 'ME': (1, 1)}
    by_year = {r['Year']: (r['Registered'], r['Present']) for r in _xlsx(resp, 'By year')}
    assert by_year == {'2022': (2, 2), '2023': (1, 0)}
    winners = _xlsx(resp, 'Winners')
    assert [(w['Rank'], w['Name'], w['Team']) for w in winners] == [(1, 'Tara Team', 'Byte Force')]
    assert len(_xlsx(resp, 'Registrations')) == 3


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_organiser_downloads_the_report_from_the_dashboard(ev):
    page = ev['owner'].get('/spoc/dashboard')
    assert page.status_code == 200
    link = f"/spoc/event_report/{ev['event_id']}"
    assert f'href="{link}"' in page.get_data(as_text=True)
    resp = ev['owner'].get(link)
    assert resp.status_code == 200 and 'attachment' in resp.headers['Content-Disposition']
    assert _xlsx(resp, 'Summary')
