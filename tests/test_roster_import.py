"""
tests/test_roster_import.py — UPG-271 on the real database layer: a roster
CSV is checked first and changes nothing; the preview says what each row
would do and what is wrong with the rows that can't be used; duplicates are
caught in the file and against the accounts; only the administrator who
uploaded the file can confirm it, and confirming writes exactly what the
preview said.
"""
import csv
import datetime
import io
import re

import pytest

import services_roster as roster
from tests.test_integration_flow import PASSWORD, _login, _unique, _user

HEAD = 'email,name,usn,department,year,section,cgpa,backlogs'


@pytest.fixture
def office(real_app):
    flask_app, db = real_app
    people = {k: f"{_unique('ros' + k)}@test.edu" for k in ('admin', 'admin2', 'spoc')}
    _user(db, people['admin'], 'SuperAdmin')
    _user(db, people['admin2'], 'SuperAdmin')
    _user(db, people['spoc'], 'ClubSPOC')

    def admin(key):
        client = flask_app.test_client()
        client.post('/login', data={'role': 'SuperAdmin', 'email': people[key], 'password': PASSWORD,
                                    'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
        return client
    yield {'app': flask_app, 'db': db, 'people': people, 'admin': admin('admin'), 'admin2': admin('admin2'),
           'spoc': _login(flask_app, people['spoc'], 'ClubSPOC'), 'tag': _unique('r').lower()}
    for doc in db.collection(roster.COLLECTION).stream():
        db.collection(roster.COLLECTION).document(doc.id).delete()


def _file(*rows, head=HEAD):
    return (head + '\n' + '\n'.join(rows) + '\n')


def _check(client, text, name='roster.csv'):
    return client.post('/admin/users/import/check', data={'file': (io.BytesIO(text.encode()), name)},
                       content_type='multipart/form-data')


def _user_doc(d, email):
    doc = d['db'].collection('users').document(email).get()
    return doc.to_dict() if doc.exists else None


def _rows(html):
    """{line: (action, text of the row)} from the preview table."""
    return {int(line): (action, re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body)))
            for line, action, body in re.findall(r'<tr data-line="(\d+)" data-action="(\w+)">(.*?)</tr>', html, re.S)}


def _counts(html):
    return {k: int(v) for k, v in re.findall(r'data-count="(\w+)"[^>]*><strong>(\d+)</strong>', html)}


# ── Criterion 1: checking changes nothing; the preview says what would happen

def test_the_file_is_checked_first_and_nothing_changes_until_it_is_confirmed(office):
    d = office
    t = d['tag']
    known = f'{t}.known@test.edu'
    same = f'{t}.same@test.edu'
    _user(d['db'], known, 'Student')
    d['db'].collection('users').document(known).update({'name': 'Known Student', 'usn': f'{t}K1'.upper(), 'department': 'CSE'})
    _user(d['db'], same, 'Student')
    d['db'].collection('users').document(same).update({'name': 'Same Student', 'department': 'ECE'})
    before_known = _user_doc(d, known)

    went = _check(d['admin'], _file(
        f'{t}.new1@test.edu,New One,{t}N1,CSE,2,A,8.4,0',
        f'{t}.new2@test.edu,,{t}N2,ISE,1,B,,',
        f'{known},Known Student,{t}K1,ECE,3,,7.25,1',
        f'{same},Same Student,,ECE,,,,',
        '',
        f'{t}.new3@test.edu,"Rao, Asha",{t}N3,CSE,2,A,9,0'))
    assert went.status_code == 302 and re.fullmatch(r'/admin/users/import/[\w-]{10,40}', went.headers['Location'])
    preview = d['admin'].get(went.headers['Location'])
    html = preview.get_data(as_text=True)
    assert preview.status_code == 200 and 'Nothing has been changed yet.' in html
    assert _counts(html) == {'create': 3, 'update': 1, 'same': 1, 'skip': 0}
    rows = _rows(html)
    assert [rows[n][0] for n in sorted(rows)] == ['create', 'create', 'update', 'same', 'create'] and sorted(rows) == [2, 3, 4, 5, 7]
    assert 'No name' in rows[3][1] and 'Rao, Asha' in rows[7][1]
    assert 'Department: CSE → ECE' in rows[4][1] and 'Year: 3' in rows[4][1] and 'CGPA: 7.25' in rows[4][1]
    assert 'Name:' not in rows[4][1]                             # what doesn't change isn't listed
    assert d['admin'].get(went.headers['Location'] + '?show=update').get_data(as_text=True).count('<tr data-line=') == 1

    # nothing was written by the check
    assert _user_doc(d, f'{t}.new1@test.edu') is None and _user_doc(d, known) == before_known

    confirm = d['admin'].post(went.headers['Location'] + '/confirm', data={'existing': 'update'}, follow_redirects=True)
    assert 'Roster imported: 3 new students added, 1 updated.' in confirm.get_data(as_text=True)
    new1, new2, new3 = (_user_doc(d, f'{t}.new{n}@test.edu') for n in (1, 2, 3))
    assert new1['usn'] == f'{t}N1'.upper() and new1['cgpa'] == 8.4 and new1['backlogs'] == 0 and new1['role'] == 'Student'
    assert new1['needs_password_reset'] is True
    assert new2['name'] == f'{t}.new2' and 'cgpa' not in new2 and new3['name'] == 'Rao, Asha'
    after = _user_doc(d, known)
    assert after['department'] == 'ECE' and after['year'] == '3' and after['cgpa'] == 7.25 and after['backlogs'] == 1
    assert after['name'] == 'Known Student' and after['password'] == before_known['password']
    # the waiting file is gone, and so is its page
    assert not list(d['db'].collection(roster.COLLECTION).stream())
    assert d['admin'].get(went.headers['Location']).status_code == 302
    assert any(a.to_dict().get('action') == 'STUDENT_ROSTER_IMPORTED' and d['people']['admin'] in str(a.to_dict().get('details'))
               and '3 created, 1 updated' in str(a.to_dict().get('details')) for a in d['db'].collection('audit_log').stream())


# ── Criterion 2: every row that can't be used says why ──────────────────────

def test_rows_that_cannot_be_used_say_why_and_are_left_out(office):
    d = office
    t = d['tag']
    taken = f'{t}.taken@test.edu'
    _user(d['db'], taken, 'Student')
    d['db'].collection('users').document(taken).update({'usn': f'{t}TAKEN'.upper()})
    went = _check(d['admin'], _file(
        f'{t}.ok@test.edu,Fine Student,{t}OK,CSE,2,A,8,0',          # 2
        f',No Email,{t}X1,CSE,2,A,,',                                # 3
        f'not-an-email,Bad Email,{t}X2,CSE,2,A,,',                   # 4
        f'{t}.ok@test.edu,Twice,{t}X3,CSE,2,A,,',                    # 5 same email as line 2
        f'{t}.other@test.edu,Same Usn,{t}OK,CSE,2,A,,',              # 6 USN of line 2
        f'{t}.thief@test.edu,Takes Usn,{t}TAKEN,CSE,2,A,,',          # 7 USN of an existing account
        f'{t}.cg@test.edu,Bad Cgpa,{t}X4,CSE,2,A,eleven,0',          # 8
        f'{t}.cg2@test.edu,High Cgpa,{t}X5,CSE,2,A,11,1.5',          # 9
        f"{d['people']['spoc']},A Staff Member,{t}X6,CSE,2,A,,",     # 10 a staff account
        f'{t}.extra@test.edu,Too Many,{t}X7,CSE,2,A,8,0,surplus',    # 11
        f'{t}.long@test.edu,{"N" * 151},{t}X8,CSE,2,A,,'))           # 12
    html = d['admin'].get(went.headers['Location']).get_data(as_text=True)
    assert _counts(html) == {'create': 1, 'update': 0, 'same': 0, 'skip': 10}
    rows = _rows(html)
    assert rows[2][0] == 'create' and all(rows[n][0] == 'skip' for n in range(3, 13))
    for line, why in ((3, 'No email address.'), (4, "isn't an email address"), (5, 'Same email as line 2'),
                      (6, 'is also on line 2 for another student'), (7, 'already belongs to another account'),
                      (8, "CGPA \"eleven\" isn't a number from 0 to 10"), (9, "CGPA \"11\" isn't a number from 0 to 10"),
                      (9, "Backlogs \"1.5\" isn't a whole number from 0 to 99"),
                      (10, "belongs to a staff account (ClubSPOC)"), (11, 'more values than the heading row'),
                      (12, 'Name is longer than 150 characters')):
        assert why in rows[line][1].replace('&#34;', '"').replace('&#39;', "'"), (line, rows[line][1])
    assert taken not in html and f'{t[:2]}***@test.edu' in html           # someone else's address isn't spelled out

    # the rows to fix, as a file
    got = d['admin'].get(went.headers['Location'] + '/problems.csv')
    lines = list(csv.reader(io.StringIO(got.get_data(as_text=True).lstrip('﻿'))))
    assert lines[0] == ['Line', 'Email', 'Name', 'USN', 'What is wrong'] and [r[0] for r in lines[1:]] == [str(n) for n in range(3, 13)]
    assert 'attachment' in got.headers['Content-Disposition'] and got.headers['Cache-Control'] == 'no-store'

    staff_before = _user_doc(d, d['people']['spoc'])
    done = d['admin'].post(went.headers['Location'] + '/confirm', data={'existing': 'update'}, follow_redirects=True)
    assert 'Roster imported: 1 new student added, 0 updated, 10 rows not used.' in done.get_data(as_text=True)
    assert _user_doc(d, f'{t}.ok@test.edu')['name'] == 'Fine Student'
    for gone in ('other', 'thief', 'cg', 'cg2', 'extra', 'long'):
        assert _user_doc(d, f'{t}.{gone}@test.edu') is None
    assert _user_doc(d, d['people']['spoc']) == staff_before and _user_doc(d, taken)['usn'] == f'{t}TAKEN'.upper()


def test_a_file_that_cannot_be_read_is_refused_with_the_reason(office):
    d = office
    for text, why in (('', 'Choose a CSV file first.'), ('   \n', 'The file is empty.'),
                      ('name,usn\nA,1\n', 'The file has no email column.'),
                      (HEAD + '\n', 'no students under it'),
                      (HEAD + '\n' + '\n'.join(f'x{n}@test.edu,,,,,,,' for n in range(roster.MAX_ROWS + 1)), 'takes up to 5000')):
        resp = d['admin'].post('/admin/users/import/check', content_type='multipart/form-data', follow_redirects=True,
                               data={'file': (io.BytesIO(text.encode()), 'r.csv' if text else '')})
        assert why in resp.get_data(as_text=True), why
    big = d['admin'].post('/admin/users/import/check', content_type='multipart/form-data', follow_redirects=True,
                          data={'file': (io.BytesIO(b'e' * (roster.MAX_BYTES + 1)), 'big.csv')})
    assert 'larger than 2 MB' in big.get_data(as_text=True)
    assert not list(d['db'].collection(roster.COLLECTION).stream())
    # headings in another order, with other names and capitals, and a column nobody reads
    checked = roster.check(d['db'], 'Roll No,Student Name,E-Mail,Email ID,Hostel\n1X,Asha,ignored,asha.%s@test.edu,H2\n' % d['tag'])
    assert checked['columns'] == ['Email', 'Name', 'USN'] and checked['ignored_columns'] == ['E-Mail', 'Hostel']
    assert checked['rows'][0]['email'] == f"asha.{d['tag']}@test.edu" and checked['rows'][0]['values']['usn'] == '1X'
    sample = d['admin'].get('/admin/users/import/sample.csv').get_data(as_text=True)
    assert sample.startswith(HEAD) and roster.check(d['db'], sample)['counts']['skip'] == 0


# ── Criterion 3: existing students: update or leave ─────────────────────────

def test_existing_students_are_updated_or_left_as_the_administrator_chooses(office):
    d = office
    t = d['tag']
    old = f'{t}.old@test.edu'
    _user(d['db'], old, 'Student')
    d['db'].collection('users').document(old).update({'name': 'Old Name', 'department': 'CSE'})
    text = _file(f'{old},New Name,,ECE,,,,', f'{t}.fresh@test.edu,Fresh,,CSE,,,,')
    went = _check(d['admin'], text)
    page = d['admin'].get(went.headers['Location']).get_data(as_text=True)
    assert 'id="ex-update" value="update" checked' in page and 'id="ex-leave" value="leave"' in page
    # no choice made: nothing happens
    d['admin'].post(went.headers['Location'] + '/confirm', data={})
    assert _user_doc(d, f'{t}.fresh@test.edu') is None
    done = d['admin'].post(went.headers['Location'] + '/confirm', data={'existing': 'leave'}, follow_redirects=True)
    assert 'Roster imported: 1 new student added, 0 updated, 1 existing left as they were.' in done.get_data(as_text=True)
    assert _user_doc(d, old)['name'] == 'Old Name' and _user_doc(d, old)['department'] == 'CSE'
    assert _user_doc(d, f'{t}.fresh@test.edu')['name'] == 'Fresh'

    # the same file again: the new student is now up to date, the old one still differs
    went = _check(d['admin'], text)
    assert _counts(d['admin'].get(went.headers['Location']).get_data(as_text=True)) == {'create': 0, 'update': 1, 'same': 1, 'skip': 0}
    d['admin'].post(went.headers['Location'] + '/confirm', data={'existing': 'update'})
    assert _user_doc(d, old)['name'] == 'New Name' and _user_doc(d, old)['department'] == 'ECE'
    assert len([u for u in d['db'].collection('users').stream() if u.id in (old, f'{t}.fresh@test.edu')]) == 2

    # a third time: nothing to import, and the page says so instead of offering it
    went = _check(d['admin'], text)
    page = d['admin'].get(went.headers['Location']).get_data(as_text=True)
    assert 'data-nothing-usable' in page and 'data-roster-confirm' not in page
    assert 'No row in this file can be used' in d['admin'].post(
        went.headers['Location'] + '/confirm', data={'existing': 'update'}, follow_redirects=True).get_data(as_text=True)


# ── Criterion 4: the waiting file belongs to its uploader ───────────────────

def test_only_the_uploader_confirms_and_the_waiting_file_does_not_linger(office):
    d = office
    t = d['tag']
    text = _file(f'{t}.wait@test.edu,Waiting,,CSE,,,,')
    went = _check(d['admin'], text)
    url = went.headers['Location']
    import_id = url.rsplit('/', 1)[1]

    # not an administrator: no way in
    for client in (d['spoc'], d['app'].test_client()):
        assert client.get(url).status_code in (302, 403) and 'Waiting' not in client.get(url).get_data(as_text=True)
        assert client.post(url + '/confirm', data={'existing': 'update'}).status_code in (302, 403)
        assert _check(client, text).status_code in (302, 403)
    assert _user_doc(d, f'{t}.wait@test.edu') is None
    # another administrator can't see or confirm this upload
    other = d['admin2'].get(url, follow_redirects=True).get_data(as_text=True)
    assert 'no longer waiting' in other and 'Waiting,' not in other and f'{t}.wait@test.edu' not in other
    d['admin2'].post(url + '/confirm', data={'existing': 'update'})
    assert d['admin2'].get(url + '/problems.csv').status_code == 302
    d['admin2'].post(url + '/cancel')
    assert _user_doc(d, f'{t}.wait@test.edu') is None and d['db'].collection(roster.COLLECTION).document(import_id).get().exists

    # the accounts changed while it waited: confirming uses what is true then
    _user(d['db'], f'{t}.wait@test.edu', 'ClubSPOC')
    page = d['admin'].get(url).get_data(as_text=True)
    assert _counts(page)['skip'] == 1 and 'belongs to a staff account' in page
    assert _user_doc(d, f'{t}.wait@test.edu')['role'] == 'ClubSPOC'

    # a new upload replaces the uploader's earlier one
    went2 = _check(d['admin'], _file(f'{t}.second@test.edu,Second,,CSE,,,,'))
    assert not d['db'].collection(roster.COLLECTION).document(import_id).get().exists
    assert len([x for x in d['db'].collection(roster.COLLECTION).stream()
                if x.to_dict().get('by') == d['people']['admin']]) == 1

    # cancelling deletes it and changes nothing
    cancelled = d['admin'].post(went2.headers['Location'] + '/cancel', follow_redirects=True).get_data(as_text=True)
    assert 'Upload cancelled. Nothing was changed.' in cancelled and _user_doc(d, f'{t}.second@test.edu') is None
    assert not [x for x in d['db'].collection(roster.COLLECTION).stream() if x.to_dict().get('by') == d['people']['admin']]

    # an upload older than an hour is gone
    went3 = _check(d['admin'], _file(f'{t}.third@test.edu,Third,,CSE,,,,'))
    third = went3.headers['Location'].rsplit('/', 1)[1]
    stale = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=roster.KEEP_MINUTES + 1)).isoformat()
    d['db'].collection(roster.COLLECTION).document(third).update({'created_at': stale})
    assert 'no longer waiting' in d['admin'].post(went3.headers['Location'] + '/confirm', data={'existing': 'update'},
                                                  follow_redirects=True).get_data(as_text=True)
    assert _user_doc(d, f'{t}.third@test.edu') is None
    assert not d['db'].collection(roster.COLLECTION).document(third).get().exists
    # an id that isn't one
    assert d['admin'].get('/admin/users/import/../../etc').status_code in (302, 404)


def test_the_users_page_sends_the_file_to_be_checked(office):
    d = office
    page = d['admin'].get('/admin/users').get_data(as_text=True)
    assert 'action="/admin/users/import/check"' in page and 'data-roster-upload' in page
    assert 'action="/admin/users/import_csv"' not in page and 'Check the file' in page
    assert roster.problems_csv({'rows': [{'line': 2, 'email': '=cmd()', 'values': {'name': '+1', 'usn': '@x'},
                                          'problems': ['x']}]}).splitlines()[1] == "2,'=cmd(),'+1,'@x,x"
