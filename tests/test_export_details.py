"""
tests/test_export_details.py — UPG-222 on the real database layer: the
registrations export (Excel and CSV) shows every detail a team gave. The
lead's USN and phone come from a question the SPOC added by hand in the
builder, else from the account; department and year come from the
university's USNs (25SUUBEAML231); each member has their own columns; each
question on the form has its own column, in the form's order.
"""
import csv
import datetime
import io

import openpyxl
import pytest

import services_export
from tests.test_integration_flow import _create_event, _login, _unique, _user

# A form like SAPTHAHACKS'26's: its lead USN and phone are questions added by
# hand in the builder, with random ids (as on the live page, 2026-11-10)
FORM = [
    {'id': 'full_name', 'type': 'text', 'label': 'Full Name', 'required': True},
    {'id': 'email', 'type': 'email', 'label': 'Email Address', 'required': True},
    {'id': 'f_usn001', 'type': 'text', 'label': 'USN', 'required': True},
    {'id': 'f_mob001', 'type': 'tel', 'label': 'Phone Number', 'required': True},
    {'id': 'f_head01', 'type': 'heading', 'label': 'About your project'},
    {'id': 'f_skil01', 'type': 'checkbox_group', 'label': 'Skills', 'options': ['Python', 'ML', 'Web']},
    {'id': 'f_shrt01', 'type': 'text', 'label': 'Short Answer'},
    {'id': 'f_mail02', 'type': 'email', 'label': 'Email Address'},
]


@pytest.fixture
def hack(real_app):
    flask_app, db = real_app
    owner, lead, solo = (f"{_unique(k)}@test.edu" for k in ('owner', 'lead', 'solo'))
    _user(db, owner, 'ClubSPOC')
    _user(db, lead, 'Student')
    _user(db, solo, 'Student')
    db.collection('users').document(solo).update({'usn': '24SUUBECS0758', 'phone': '9000000002'})
    client = _login(flask_app, owner, 'ClubSPOC')
    event_id = _create_event(client, db, _unique('Hack Export'), datetime.date.today().isoformat(), team=True)
    db.collection('event_forms').document(event_id).set({'fields': FORM})
    team = _unique('REG')
    db.collection('registrations').document(team).set({
        'reg_id': team, 'event_id': event_id, 'lead_name': 'Lena Lead', 'lead_email': lead,
        'lead_usn': '', 'lead_phone': '', 'team_name': 'Apex.devs', 'registered_at': '2026-11-10 05:46:17',
        'members': [{'role': 'Lead', 'name': 'Lena Lead', 'email': lead, 'usn': ''},
                    {'role': 'Member', 'name': 'Hima TS', 'email': 'hima@test.edu', 'usn': '25SUUBEAML231', 'phone': '9000000003',
                     'confirmed_at': '2026-11-10 06:00:00'},
                    {'role': 'Member', 'name': 'Alif P', 'email': 'alif@test.edu', 'usn': ''}],
        'form_answers': {'full_name': 'Lena Lead', 'email': lead, 'f_usn001': '25suubeaml013',
                         'f_mob001': '9000000001', 'f_skil01': ['Python', 'ML'], 'f_shrt01': 'A study planner',
                         'f_mail02': 'lena.alt@test.edu', 'f_gone01': 'Answer to a removed question'},
        'attendance': 'Pending', 'payment_status': 'Free'})
    single = _unique('REG')
    db.collection('registrations').document(single).set({
        'reg_id': single, 'event_id': event_id, 'lead_name': 'Sam Solo', 'lead_email': solo,
        'team_name': 'Six Seven', 'registered_at': '2026-11-10 05:53:23', 'members': [],
        'form_answers': {'full_name': 'Sam Solo', 'email': solo}, 'attendance': 'Pending', 'payment_status': 'Free'})
    return {'app': flask_app, 'db': db, 'owner': client, 'event_id': event_id, 'team': team, 'single': single}


def _sheets(hack):
    e = hack['event_id']
    resp = hack['owner'].get(f'/spoc/export_excel/{e}')
    assert resp.status_code == 200
    rows = list(openpyxl.load_workbook(io.BytesIO(resp.data)).worksheets[0].iter_rows(values_only=True))
    excel = [dict(zip(rows[0], [('' if v is None else str(v)) for v in r])) for r in rows[1:]]
    resp = hack['owner'].get(f'/spoc/export_csv/{e}')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    return {'excel': (list(rows[0]), excel), 'csv': (next(csv.reader(io.StringIO(text))), list(csv.DictReader(io.StringIO(text))))}


def _row(rows, team):
    return next(r for r in rows if r['Team'] == team)


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_leads_usn_and_phone_come_from_the_spocs_own_question_or_the_account(hack):
    for name, (_, rows) in _sheets(hack).items():
        team = _row(rows, 'Apex.devs')
        assert (team['Lead USN'], team['Lead Phone']) == ('25SUUBEAML013', '9000000001'), name
        solo = _row(rows, 'Six Seven')
        assert (solo['Lead USN'], solo['Lead Phone']) == ('24SUUBECS0758', '9000000002'), name


def test_department_and_year_come_from_the_universitys_usns(hack):
    for name, (_, rows) in _sheets(hack).items():
        assert (_row(rows, 'Apex.devs')['Department'], _row(rows, 'Apex.devs')['Year']) == ('AML', '2025'), name
        assert (_row(rows, 'Six Seven')['Department'], _row(rows, 'Six Seven')['Year']) == ('CS', '2024'), name
    for usn, expected in (('24BECSE0624', ('CSE', '2024')), ('26SUUBEADS044', ('ADS', '2026')),
                          ('1SN22CS007', ('CS', '2022')), ('1AM24CI037', ('CI', '2024')), ('F', ('', ''))):
        assert services_export.department_and_year({}, None, usn) == expected, usn


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_each_member_has_their_own_columns(hack):
    for name, (header, rows) in _sheets(hack).items():
        team, solo = _row(rows, 'Apex.devs'), _row(rows, 'Six Seven')
        assert (team['Member 2 Name'], team['Member 2 USN'], team['Member 2 Email'],
                team['Member 2 Confirmed']) == ('Hima TS', '25SUUBEAML231', 'hima@test.edu', 'Yes'), name
        assert team['Member 2 Phone'] == '9000000003', name
        assert (team['Member 3 Name'], team['Member 3 USN'], team['Member 3 Phone'],
                team['Member 3 Confirmed']) == ('Alif P', '', '', 'No'), name
        assert 'Member 4 Name' not in header   # no team has three others
        assert solo['Member 2 Name'] == '' and solo['Member 2 Confirmed'] == '', name
        # The Members cell no longer shows "()" for a member without a USN
        assert team['Members'] == 'Hima TS (25SUUBEAML231) [Confirmed]; Alif P [Waiting]', name


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_every_question_on_the_form_has_a_column_in_the_forms_order(hack):
    for name, (header, rows) in _sheets(hack).items():
        team = _row(rows, 'Apex.devs')
        questions = header[header.index('Member 3 Confirmed') + 1:header.index('Attendance')]
        assert questions == ['Skills', 'Short Answer', 'Email Address',
                             'f_gone01 (no longer on the form)'], name
        assert (team['Skills'], team['Short Answer'], team['Email Address']) == \
            ('Python, ML', 'A study planner', 'lena.alt@test.edu'), name
        assert team['f_gone01 (no longer on the form)'] == 'Answer to a removed question'
        # Headings aren't columns, and the USN and phone questions are shown once, as the lead's
        assert 'About your project' not in header and 'USN' not in header and 'Phone Number' not in header
        assert len(header) == len(set(header)) and all(len(r) == len(header) for r in rows), name


def test_the_all_events_export_keeps_the_same_columns_for_every_event(hack):
    rows = [r for r in services_export.all_registration_rows(hack['db']) if r[1] in (hack['team'], hack['single'])]
    assert len(rows) == 2 and all(len(r) == 1 + len(services_export.COLUMNS) for r in rows)
    team = next(r for r in rows if r[1] == hack['team'])
    assert team[1 + services_export.COLUMNS.index('Lead USN')] == '25SUUBEAML013'
