"""
tests/test_download_columns.py — UPG-325: every Excel/CSV download lets the
person tick the columns they want (all ticked to start). The page asks for
the file's columns with ?list_columns=1 and downloads with one col= per
column kept; no col gives the whole file, as before.
"""
import csv
import io

import openpyxl
import pytest

import services_export
from tests.test_exports import ev  # noqa: F401
from tests.test_hackathon_marks import CODES, mk  # noqa: F401
from tests.test_hackathon_phase2 import p2  # noqa: F401
from tests.test_hackathon_portal import _page, hack  # noqa: F401
from tests.test_integration_flow import _login, _unique, _user


def _rows(resp):
    assert resp.status_code == 200 and resp.mimetype.startswith('text/csv'), resp.status_code
    return list(csv.reader(io.StringIO(resp.get_data(as_text=True))))


def _sheet(resp):
    assert resp.status_code == 200 and resp.mimetype.endswith('spreadsheetml.sheet'), resp.status_code
    return [list(r) for r in openpyxl.load_workbook(io.BytesIO(resp.data)).worksheets[0].iter_rows(values_only=True)]


def _admin(ev):  # noqa: F811
    email = f"{_unique('coladmin')}@test.edu"
    _user(ev['db'], email, 'SuperAdmin')
    client = ev['app'].test_client()
    client.post('/login', data={'role': 'SuperAdmin', 'email': email, 'password': 'Str0ng!Pass#1',
                                'secret_key': ev['app'].config.get('MASTER_SECRET_KEY', '')})
    return client


# 1. Choosing: the file's order, the required columns always, nothing ticked = everything
def test_choosing_keeps_the_files_order_and_the_required_columns(real_app):
    flask_app, _ = real_app
    columns, rows = ['A', 'B', 'C', 'D'], [[1, 2, 3, 4], [5, 6, 7]]
    assert services_export.pick_columns(columns, rows) == (columns, rows)        # outside a request
    with flask_app.test_request_context('/x?col=D&col=B'):
        assert services_export.pick_columns(columns, rows) == (['B', 'D'], [[2, 4], [6, '']])
        assert services_export.pick_columns(columns, rows, keep=('A',))[0] == ['A', 'B', 'D']
        assert services_export.to_csv(rows, columns).splitlines()[0] == 'B,D'
    with flask_app.test_request_context('/x'):
        assert services_export.pick_columns(columns, rows) == (columns, rows)
    with flask_app.test_request_context('/x?col=Nothing'):
        assert services_export.pick_columns(columns, rows) == (columns, rows)    # none known: the whole file
    with flask_app.test_request_context('/x?list_columns=1'):
        assert services_export.probing()
        with pytest.raises(services_export.ColumnList) as got:
            services_export.to_xlsx([('S', columns, rows)], keep=('C', 'Z'))
        assert got.value.columns == columns and got.value.required == ['C']


# 2. The list of columns, for the registrations downloads (SPOC, coordinator, filtered)
def test_the_page_gets_the_list_of_columns(ev):  # noqa: F811
    e = ev['event_id']
    coord = _login(ev['app'], ev['p']['coord_in'], 'EventCoordinator')
    for client, url in ((ev['owner'], f'/spoc/export_csv/{e}'), (ev['owner'], f'/spoc/export_excel/{e}'),
                        (coord, f'/coordinator/export_registrations/{e}'), (coord, f'/coordinator/export_excel/{e}'),
                        (coord, f'/coordinator/registrations/{e}/export_filtered')):
        r = client.get(url + ('&' if '?' in url else '?') + 'list_columns=1')
        assert r.status_code == 200 and r.is_json, url
        info = r.get_json()
        assert info['columns'][:3] == ['Ticket ID', 'Lead Name', 'Lead USN'] and info['required'] == [], url
    # The same rights as the file itself
    other = _login(ev['app'], ev['p']['other_spoc'], 'ClubSPOC')
    assert other.get(f'/spoc/export_csv/{e}?list_columns=1').status_code in (302, 403)


# 3. Only the ticked columns come down, CSV and Excel; no col = the whole file as before
def test_only_the_ticked_columns_come_down(ev):  # noqa: F811
    e = ev['event_id']
    full = _rows(ev['owner'].get(f'/spoc/export_csv/{e}'))
    assert full[0][:2] == ['Ticket ID', 'Lead Name'] and len(full[0]) > 10
    picked = _rows(ev['owner'].get(f'/spoc/export_csv/{e}?col=Team&col=Lead+Name&col=Lead+Email'))
    assert picked[0] == ['Lead Name', 'Lead Email', 'Team']                       # in the file's own order
    assert sorted(r[2] for r in picked[1:]) == ['Byte Force', 'Solo Stars']
    assert any(r[0] == 'Tara Team' for r in picked[1:])
    book = _sheet(ev['owner'].get(f'/spoc/export_excel/{e}?col=Team&col=Payment+Status'))
    assert book[0] == ['Team', 'Payment Status'] and len(book) == 3
    assert _sheet(ev['owner'].get(f'/spoc/export_excel/{e}'))[0] == full[0]

    # The filtered download keeps its filters and takes the columns
    coord = _login(ev['app'], ev['p']['coord_in'], 'EventCoordinator')
    rows = _rows(coord.get(f'/coordinator/registrations/{e}/export_filtered?q=Byte&col=Team'))
    assert rows == [['Team'], ['Byte Force']]


# 4. The evaluators' file always keeps the team code and the score; asking for the list isn't a download
def test_the_evaluators_file_keeps_team_code_and_score(mk):  # noqa: F811
    eid, _ = mk['mk_setup'](submit=('Alpha', 'Bravo'))
    mk['after']()

    def downloads():
        return [d.to_dict() for d in mk['db'].collection('audit_log').stream()
                if d.to_dict().get('action') == 'HACKATHON_EVALUATORS_FILE' and eid in str(d.to_dict())]

    info = mk['owner'].get(f'/spoc/hackathon/{eid}/evaluators.xlsx?list_columns=1').get_json()
    assert info['required'] == ['Team code', 'Score (out of 100)'] and 'Problem' in info['columns']
    assert downloads() == []                                                      # only the list, not audited
    rows = _rows(mk['owner'].get(f'/spoc/hackathon/{eid}/evaluators.csv?col=Team'))
    assert rows[0] == ['Team code', 'Score (out of 100)', 'Team']
    assert sorted(r[0] for r in rows[1:]) == sorted([CODES['Alpha'], CODES['Bravo']])
    assert _sheet(mk['owner'].get(f'/spoc/hackathon/{eid}/evaluators.xlsx?col=Lead'))[0] == \
        ['Team code', 'Score (out of 100)', 'Lead']
    assert len(downloads()) == 2


# 5. The admin's downloads and the form answers take the columns too
def test_admin_and_form_answer_downloads_take_the_columns(ev):  # noqa: F811
    admin = _admin(ev)
    info = admin.get('/admin/analytics/export/events?list_columns=1').get_json()
    assert info['columns'] == ['event_id', 'title', 'category', 'date', 'venue', 'status', 'entry_fee',
                               'registration_count']
    rows = _rows(admin.get('/admin/analytics/export/events?col=title'))
    assert rows[0] == ['title'] and all(len(r) == 1 for r in rows[1:])
    assert _rows(admin.get('/admin/analytics/export/revenue?col=revenue_inr&col=title'))[0] == ['title', 'revenue_inr']
    assert _rows(admin.get('/admin/analytics/export/payments?col=email'))[0] == ['email']
    assert len(_rows(admin.get('/admin/analytics/export/events'))[0]) == 8              # all, as before
    before = [d.to_dict() for d in ev['db'].collection('audit_log').stream()]
    admin.get('/admin/analytics/export/events?list_columns=1')
    assert len([d for d in ev['db'].collection('audit_log').stream()]) == len(before)   # the list isn't a download

    e = ev['event_id']
    form = ev['owner'].get(f'/forms/responses/export/{e}?list_columns=1').get_json()
    assert form['columns'][:3] == ['Submitted At', 'Name', 'Email']
    assert _rows(ev['owner'].get(f'/forms/responses/export/{e}?col=Email'))[0] == ['Email']


# 6. The download buttons open the column box
def test_the_download_buttons_open_the_column_box(ev, mk):  # noqa: F811
    e = ev['event_id']
    spoc = _page(ev['owner'], '/spoc/dashboard')
    for url in (f'/spoc/export_excel/{e}', f'/spoc/export_csv/{e}'):
        assert f'<a data-pick-columns href="{url}"' in spoc, url
    coord = _login(ev['app'], ev['p']['coord_in'], 'EventCoordinator')
    page = _page(coord, f'/coordinator/registrations/{e}')
    assert f'<a data-pick-columns href="/coordinator/export_registrations/{e}"' in page
    assert 'data-pick-columns href="/coordinator/registrations/' in page

    eid, _ = mk['mk_setup'](('Alpha',))
    manage = _page(mk['owner'], f'/spoc/hackathon/{eid}')
    assert f'data-pick-columns class="btn btn-sm btn-outline-primary" href="/spoc/hackathon/{eid}/evaluators.xlsx"' in manage
    assert f'data-pick-columns class="btn btn-sm btn-outline-secondary" href="/spoc/hackathon/{eid}/evaluators.csv"' in manage

    js = open('static/js/global.js', encoding='utf-8').read()
    assert "a[data-pick-columns]" in js and "list_columns" in js and "'col'" in js
    assert 'Select all' in js and 'Select none' in js
