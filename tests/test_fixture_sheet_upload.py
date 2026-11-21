"""
tests/test_fixture_sheet_upload.py — UPG-391: the SPOC sets which teams play
each match (M-01 …) from an Excel or CSV fixture sheet, matched by the
registered team names; a sheet typed by hand ("M1", "Team A", a title row
above the header) works too; all or nothing.
"""
import csv
import datetime
import io

from openpyxl import Workbook, load_workbook

import services_sports as sports
from tests.test_kabaddi_premier_league import _generate, league  # noqa: F401
from tests.test_sports_tournament import _play, _t, cup  # noqa: F401


def _xlsx(rows):
    book = Workbook()
    for row in rows:
        book.active.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _upload(client, event_id, raw, name):
    return client.post(f'/tournament/{event_id}/schedule/upload', data={'file': (io.BytesIO(raw), name)},
                       content_type='multipart/form-data', follow_redirects=True).get_data(as_text=True)


def _pair(t, i):
    name = sports.names(t)
    m = t['matches'][i]
    return name[m['home']], name[m['away']]


def test_the_excel_sheet_goes_out_and_sets_the_teams_of_each_match(league):  # noqa: F811
    d, event_id, ids = league
    _generate(d, event_id, ids)
    page = d['owner'].get(f'/tournament/{event_id}').get_data(as_text=True)
    assert f'/tournament/{event_id}/schedule.xlsx' in page and 'accept=".xlsx,.csv' in page and 'Team 1' in page

    resp = d['owner'].get(f'/tournament/{event_id}/schedule.xlsx')
    assert resp.status_code == 200 and resp.mimetype.endswith('spreadsheetml.sheet')
    rows = [list(r) for r in load_workbook(io.BytesIO(resp.data)).active.iter_rows(values_only=True)]
    assert rows[0] == list(sports.SCHEDULE_COLUMNS) and len(rows) == 29
    assert rows[1][:4] == ['M-01', 'Pool A · Leg 1 · Round 1', 'Garuda Sena', 'Vajra']

    rows[1][2:4] = ['neuro  ninjas', 'MALNAD FIGHTERS']        # spacing and capitals don't matter
    rows[2][2:5] = ['Garuda Sena', 'Vajra', datetime.datetime(2026, 11, 24)]
    rows[2][5] = datetime.time(15, 30)
    page = _upload(d['owner'], event_id, _xlsx(rows), 'fixtures.xlsx')
    assert 'Schedule saved: 2 matches changed.' in page
    t = _t(d, event_id)
    assert _pair(t, 0) == ('Neuro Ninjas', 'Malnad Fighters') and _pair(t, 1) == ('Garuda Sena', 'Vajra')
    assert (t['matches'][1]['date'], t['matches'][1]['time']) == ('2026-11-24', '15:30')
    assert _pair(t, 2) == ('Garuda Sena', 'Neuro Ninjas')       # untouched


def test_a_hand_typed_sheet_with_a_title_m1_and_team_a_b_works(league):  # noqa: F811
    d, event_id, ids = league
    _generate(d, event_id, ids)
    rows = [['Sapthagiri Kabaddi Premier League'], [],
            ['Match No', 'Team A', 'Team B', 'Court'],
            ['M1', 'Vajra', 'Garuda Sena', 'Main court'],
            ['2', 'Neuro Ninjas', 'Malnad Fighters', '']]
    page = _upload(d['owner'], event_id, _xlsx(rows), 'mine.xlsx')
    assert 'Schedule saved: 2 matches changed.' in page
    t = _t(d, event_id)
    assert _pair(t, 0) == ('Vajra', 'Garuda Sena') and t['matches'][0]['venue'] == 'Main court'
    assert _pair(t, 1) == ('Neuro Ninjas', 'Malnad Fighters')

    out = io.StringIO()                                          # the same as CSV
    csv.writer(out).writerows([['#', 'Home', 'Away'], ['M-03', 'Vajra', 'Neuro Ninjas']])
    assert 'Schedule saved: 1 match changed.' in _upload(d['owner'], event_id, out.getvalue().encode(), 'mine.csv')
    assert _pair(_t(d, event_id), 2) == ('Vajra', 'Neuro Ninjas')


def test_a_wrong_name_a_played_match_or_a_team_against_itself_changes_nothing(league):  # noqa: F811
    d, event_id, ids = league
    t = _generate(d, event_id, ids)
    _play(d['owner'], event_id, t['matches'][0], 30, 22)
    rows = [['Match', 'Team 1', 'Team 2'],
            ['M-01', 'Neuro Ninjas', 'Vajra'],                   # played
            ['M-02', 'Garuda Senaa', 'Vajra'],                   # a typo
            ['M-03', 'Vajra', 'vajra'],                          # itself
            ['M-04', 'Garuda Sena', 'Neuro Ninjas']]             # fine, but all or nothing
    page = _upload(d['owner'], event_id, _xlsx(rows), 'bad.xlsx')
    assert 'Nothing was changed.' in page
    assert 'Row 2 (M-01): it has been played' in page
    assert 'Row 3 (M-02): no team is called' in page and 'Garuda Senaa' in page
    assert "Row 4 (M-03): a team can&#39;t play itself" in page or "Row 4 (M-03): a team can't play itself" in page
    assert _pair(_t(d, event_id), 3) == ('Vajra', 'Malnad Fighters')

    assert 'needs a Match column' in _upload(d['owner'], event_id, _xlsx([['Team 1', 'Team 2']]), 'x.xlsx')
    assert "couldn" in _upload(d['owner'], event_id, b'not an excel file', 'x.xlsx')


def test_playoff_rows_wait_for_make_the_playoffs(league):  # noqa: F811
    d, event_id, ids = league
    _generate(d, event_id, ids)
    rows = [['Match', 'Team 1', 'Team 2'], ['M-01', 'Vajra', 'Garuda Sena'],
            ['M-29', '1st Pool A', '2nd Pool B'], ['M-31', 'Winner SF1', 'Winner SF2']]
    page = _upload(d['owner'], event_id, _xlsx(rows), 'all.xlsx')
    assert 'Schedule saved: 1 match changed.' in page and 'M-29, M-31 will be made by Make the playoffs' in page
    assert len(_t(d, event_id)['matches']) == 28


def test_only_the_spoc_uploads_the_fixture_sheet(league):  # noqa: F811
    d, event_id, ids = league
    _generate(d, event_id, ids)
    assert d['coord'].get(f'/tournament/{event_id}/schedule.xlsx').status_code == 403
    resp = d['coord'].post(f'/tournament/{event_id}/schedule/upload', data={
        'file': (io.BytesIO(_xlsx([['Match', 'Team 1', 'Team 2'], ['M-01', 'Vajra', 'Garuda Sena']])), 'x.xlsx')},
        content_type='multipart/form-data')
    assert resp.status_code == 403
