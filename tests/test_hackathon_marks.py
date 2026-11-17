"""
tests/test_hackathon_marks.py — UPG-308: a hackathon round marked outside the
portal. The evaluators get the submissions with each team's code; they send
back the team code and the score; the SPOC uploads it, checks it and presses
Submit, which saves the marks and sends the top N to the next round.
"""
import csv
import io

import openpyxl
import pytest

import services_export
import services_hackathon_eval as ev
import services_hackathon_marks as marks
from tests.test_hackathon_phase2 import p2  # noqa: F401  (the Phase 2 fixture)
from tests.test_hackathon_portal import hack  # noqa: F401

NAMES = ('Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo')
CODES = {'Alpha': 'XL987A', 'Bravo': 'BR4V0B', 'Charlie': 'CH4RL1', 'Delta': 'D3LT4D', 'Echo': 'ECH05E'}


@pytest.fixture
def mk(p2):  # noqa: F811
    h = p2

    def setup(names=NAMES, submit=None, file_mode=True):
        eid, teams = h['setup'](names, submit)
        for name, t in teams.items():
            h['db'].collection('registrations').document(t['id']).update({'team_code': CODES[name]})
        if file_mode:
            r = h['owner'].post(f'/spoc/hackathon/{eid}/evaluation_mode', data={'mode': 'file'})
            assert r.status_code == 302 and ev.mode(h['ev'](eid)) == ev.FILE
        return eid, teams

    def upload(eid, text, n=10, name='marks.csv'):
        data = text.encode() if isinstance(text, str) else text
        return h['owner'].post(f'/spoc/hackathon/{eid}/marks/preview',
                               data={'file': (io.BytesIO(data), name), 'n': str(n)},
                               content_type='multipart/form-data')

    def submit(eid, n=10, client=None):
        upload_id = marks.kept(h['ev'](eid) | {'id': eid}).get('id', '')
        return (client or h['owner']).post(f'/spoc/hackathon/{eid}/marks/submit',
                                           data={'upload_id': upload_id, 'n': str(n), 'expected_round': '1'})

    def file_score(t):
        sub = h['sub'](t)
        return (sub.get('file_score') or {}).get('score')

    h.update({'mk_setup': setup, 'upload': upload, 'mk_submit': submit, 'file_score': file_score})
    return h


def _csv(rows, head=('Team code', 'Score')):
    out = io.StringIO()
    w = csv.writer(out)
    if head:
        w.writerow(head)
    w.writerows(rows)
    return out.getvalue()


# 1. The registrations export shows the team code
def test_registrations_export_has_the_team_code(mk):
    eid, teams = mk['mk_setup'](('Alpha', 'Bravo'), file_mode=False)
    columns, rows = services_export.registration_table(mk['db'], eid)
    assert 'Team code' in columns
    at = columns.index('Team code')
    assert sorted(r[at] for r in rows) == sorted([CODES['Alpha'], CODES['Bravo']])
    book = openpyxl.load_workbook(io.BytesIO(services_export.registrations_xlsx(mk['db'], eid)))
    heads = [c.value for c in book.worksheets[0][1]]
    assert 'Team code' in heads


# 2. The file for the evaluators, staff only (8)
def test_the_file_for_the_evaluators(mk):
    eid, teams = mk['mk_setup'](submit=('Alpha', 'Bravo', 'Charlie'))
    mk['after']()
    resp = mk['owner'].get(f'/spoc/hackathon/{eid}/evaluators.csv')
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert rows[0][:3] == ['Team code', 'Score (out of 100)', 'Team']
    assert sorted(r[0] for r in rows[1:]) == sorted(CODES[n] for n in ('Alpha', 'Bravo', 'Charlie'))
    assert all(r[1] == '' for r in rows[1:])                         # the score is left for the evaluators
    alpha = next(r for r in rows[1:] if r[0] == CODES['Alpha'])
    assert 'https://github.com/x/Alpha' in alpha                     # a link in full
    assert any('/hackathon/' in c and '/file/' in c for c in alpha)  # the PDF as its portal link
    x = mk['owner'].get(f'/spoc/hackathon/{eid}/evaluators.xlsx')
    assert x.status_code == 200
    sheet = openpyxl.load_workbook(io.BytesIO(x.data)).worksheets[0]
    assert sheet['A1'].value == 'Team code' and sheet.max_row == 4
    assert mk['stranger'].get(f'/spoc/hackathon/{eid}/evaluators.xlsx').status_code == 403
    assert teams['Alpha']['client'].get(f'/spoc/hackathon/{eid}/evaluators.csv').status_code == 403


# 3. A third way to score the round
def test_outside_evaluators_is_a_way_to_score_the_round(mk):
    eid, _ = mk['mk_setup'](('Alpha',))
    page = mk['owner'].get(f'/spoc/hackathon/{eid}').get_data(as_text=True)
    assert 'Outside evaluators (upload marks)' in page and 'data-file-round' in page
    assert 'evaluators.xlsx' in page


# 4. Reading the file: headings, two bare columns, codes in any case
def test_reading_headings_or_the_first_two_columns():
    with_heads = _csv([['x', 'xl987a', '78.5'], ['y', ' br4v0b ', '90']], head=('Team', 'Team ID', 'Marks'))
    lines = marks.read(with_heads.encode(), 'a.csv')
    assert [(l['code'], l['score']) for l in lines] == [('XL987A', 78.5), ('BR4V0B', 90)]
    bare = marks.read(b'XL987A,78\nBR4V0B,91\n', 'b.csv')
    assert [(l['code'], l['score']) for l in bare] == [('XL987A', 78), ('BR4V0B', 91)]
    bad = marks.read(_csv([['XL987A', 'abc'], ['BR4V0B', '120']]).encode(), 'c.csv')
    assert [l['error'] for l in bad] == ["isn't a number", "isn't from 0 to 100"]
    book = openpyxl.Workbook()
    book.active.append(['Team Code', 'Score'])
    book.active.append(['xl987a', 64])
    buf = io.BytesIO()
    book.save(buf)
    assert [(l['code'], l['score']) for l in marks.read(buf.getvalue(), 'd.xlsx')] == [('XL987A', 64)]
    with pytest.raises(marks.MarksError):
        marks.read(b'', 'e.csv')
    with pytest.raises(marks.MarksError):
        marks.read(b'whatever', 'old.xls')


def test_the_preview_shows_what_to_fix_and_saves_nothing(mk):
    eid, teams = mk['mk_setup'](submit=('Alpha', 'Bravo', 'Charlie', 'Delta'))
    mk['after']()
    text = _csv([[CODES['Alpha'], 80], ['ZZZ999', 70], [CODES['Bravo'], 'abc'], [CODES['Charlie'], 60],
                 [CODES['Charlie'], 61], [CODES['Echo'], 50]])
    page = mk['upload'](eid, text)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'data-marks-fix' in html
    assert 'ZZZ999' in html and 'in the file twice' in html and 'abc' in html
    assert "didn&#39;t submit" in html                      # Echo has a code but no submission
    assert 'data-marks-missing' in html and 'Delta' in html  # submitted, not in the file
    assert 'disabled' in html.split('data-marks-submit')[1]
    assert all(mk['file_score'](t) is None for n, t in teams.items() if n != 'Echo')
    assert not ev.shortlist(mk['ev'](eid))


# 5. Submit is refused while anything is left to fix
def test_submit_is_refused_while_the_file_has_problems(mk):
    eid, teams = mk['mk_setup'](submit=('Alpha', 'Bravo'))
    mk['after']()
    mk['upload'](eid, _csv([[CODES['Alpha'], 80], ['NOPE00', 70]]))
    r = mk['mk_submit'](eid)
    assert r.status_code == 302
    assert mk['file_score'](teams['Alpha']) is None and not ev.shortlist(mk['ev'](eid))


# 6. Submit saves the marks and sends the top N to the next round in one step
def test_submit_saves_marks_and_sends_the_top_n_through(mk):
    eid, teams = mk['mk_setup']()
    mk['after']()
    scores = {'Alpha': 91, 'Bravo': 72.5, 'Charlie': 88, 'Delta': 40}       # Echo isn't in the file
    page = mk['upload'](eid, _csv([[CODES[n].lower(), s] for n, s in scores.items()]), n=2)
    html = page.get_data(as_text=True)
    assert 'data-marks-fix' not in html and 'Echo' in html
    r = mk['mk_submit'](eid, n=2)
    assert r.status_code == 302
    for name, score in scores.items():
        assert mk['file_score'](teams[name]) == score
    assert mk['file_score'](teams['Echo']) is None
    through = {n for n, t in teams.items() if not mk['reg'](t).get('is_eliminated')}
    assert through == {'Alpha', 'Charlie'}
    assert all(mk['reg'](teams[n])['current_round'] == 2 for n in through)
    sl = ev.shortlist(mk['ev'](eid))
    assert sl and sl['to_round'] == 2 and sorted(sl['finalists']) == ['Alpha', 'Charlie']
    assert mk['notices'](teams['Delta']['lead'])                       # every team is told on its page
    page = mk['owner'].get(f'/spoc/hackathon/{eid}').get_data(as_text=True)
    assert 'Finalists announced' in page


def test_teams_tied_at_the_cut_go_through_together(mk):
    eid, teams = mk['mk_setup']()
    mk['after']()
    mk['upload'](eid, _csv([[CODES['Alpha'], 90], [CODES['Bravo'], 80], [CODES['Charlie'], 80],
                            [CODES['Delta'], 70], [CODES['Echo'], 60]]), n=2)
    assert mk['mk_submit'](eid, n=2).status_code == 302
    through = {n for n, t in teams.items() if not mk['reg'](t).get('is_eliminated')}
    assert through == {'Alpha', 'Bravo', 'Charlie'}


# 7. A team whose code was reset after the file went out still matches
def test_an_old_team_code_still_matches(mk):
    eid, teams = mk['mk_setup'](('Alpha', 'Bravo'))
    alpha = teams['Alpha']
    r = alpha['client'].post(f"/teams/{alpha['id']}/regenerate")
    assert r.status_code == 302
    reg = mk['reg'](alpha)
    assert reg['team_code'] != CODES['Alpha'] and CODES['Alpha'] in reg['team_code_history']
    mk['after']()
    html = mk['upload'](eid, _csv([[CODES['Alpha'], 77], [CODES['Bravo'], 66]]), n=1).get_data(as_text=True)
    assert 'data-marks-fix' not in html
    assert mk['mk_submit'](eid, n=1).status_code == 302
    assert mk['file_score'](alpha) == 77 and not mk['reg'](alpha).get('is_eliminated')


# 8. Only the event's staff may upload or submit
def test_only_staff_may_upload_or_submit(mk):
    eid, teams = mk['mk_setup'](('Alpha',))
    mk['after']()
    body = {'file': (io.BytesIO(b'XL987A,50\n'), 'm.csv'), 'n': '1'}
    assert mk['stranger'].post(f'/spoc/hackathon/{eid}/marks/preview', data=body,
                               content_type='multipart/form-data').status_code == 403
    mk['upload'](eid, 'XL987A,50\n', n=1)
    assert mk['mk_submit'](eid, n=1, client=mk['stranger']).status_code == 403
    assert mk['mk_submit'](eid, n=1, client=teams['Alpha']['client']).status_code == 403
    assert mk['file_score'](teams['Alpha']) is None


def test_marks_wait_for_the_deadline(mk):
    eid, _ = mk['mk_setup'](('Alpha',))
    r = mk['upload'](eid, 'XL987A,50\n', n=1)          # submissions still open
    assert r.status_code == 302
    assert not marks.kept(mk['ev'](eid))


def test_a_judge_scored_round_is_unchanged(mk):
    """The SPOC's own score still overrides in the AI and judges modes."""
    eid, teams = mk['mk_setup'](('Alpha',), file_mode=False)
    mk['after']()
    mk['owner'].post(f"/spoc/hackathon/{eid}/review/{teams['Alpha']['id']}", data={'score': '55', 'note': ''})
    row = mk['rows'](eid)[0]
    assert row['key'] == 55 and row['spoc_score'] == 55

