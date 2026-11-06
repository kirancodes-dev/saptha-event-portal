"""
tests/test_naac.py — UPG-144 on the real database layer: the IQAC coordinator
and department admin roles, NAAC categories, the post-event report with
evidence, reminders, the yearly builder, its exports, and who may do what.
"""
import datetime
import io
import json
import zipfile

import openpyxl
import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

import services_certificates as certs
import services_naac as naac
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

CSE, MECH = 'Computer Science', 'Mechanical'


def _png():
    buf = io.BytesIO()
    Image.new('RGB', (40, 30), 'teal').save(buf, format='PNG')
    return buf.getvalue()


def _geotagged_jpeg():
    image = Image.new('RGB', (60, 40), 'navy')
    exif = image.getexif()
    exif[0x8825] = {1: 'N', 2: (12.0, 58.0, 30.0), 3: 'E', 4: (77.0, 35.0, 0.0)}
    buf = io.BytesIO()
    image.save(buf, format='JPEG', exif=exif)
    return buf.getvalue()


@pytest.fixture
def world(real_app, monkeypatch):
    import routes_admin
    import utils_email
    flask_app, db = real_app
    monkeypatch.setattr(routes_admin, 'db', db, raising=False)
    mail = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k:
                        mail.append({'to': to, 'subject': subject, 'html': html}) or True)
    monkeypatch.setattr(certs, 'render', lambda event, cert: b'%PDF-1.4 ' + cert['number'].encode())
    email = {k: f"{_unique('naac' + k)}@test.edu" for k in
             ('owner', 'other', 'admin', 'student', 'coord')}
    for key, role in (('owner', 'ClubSPOC'), ('other', 'ClubSPOC'), ('admin', 'SuperAdmin'), ('student', 'Student'),
                      ('coord', 'EventCoordinator')):
        _user(db, email[key], role)
    admin = flask_app.test_client()
    admin.post('/login', data={'role': 'SuperAdmin', 'email': email['admin'], 'password': PASSWORD,
                               'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    owner = _login(flask_app, email['owner'], 'ClubSPOC')
    today = datetime.date.today()

    def event(title, days_ago=10, department=CSE, **fields):
        event_id = _create_event(owner, db, _unique(title), '2031-01-01', team=False)
        held = (today - datetime.timedelta(days=days_ago)).isoformat()
        db.collection('events').document(event_id).update(dict({
            'status': 'completed', 'date': held, 'end_datetime': held, 'end_date': '',
            'department': department, 'staff': [], 'activity_hours': 2}, **fields))
        return event_id

    def person(event_id, name, attendance='Present', ptype='student', **fields):
        db.collection('registrations').document(_unique('REG')).set(dict({
            'event_id': event_id, 'lead_name': name, 'lead_email': f"{_unique('p')}@test.edu", 'status': 'Confirmed',
            'attendance': attendance, 'participant_type': ptype}, **fields))
    return {'app': flask_app, 'db': db, 'email': email, 'admin': admin, 'owner': owner, 'mail': mail,
            'other': _login(flask_app, email['other'], 'ClubSPOC'), 'student': _login(flask_app, email['student'], 'Student'),
            'coord': _login(flask_app, email['coord'], 'EventCoordinator'), 'event': event, 'person': person,
            'year': naac.academic_year(today - datetime.timedelta(days=10))}


def _appoint(d, key, role, department=''):
    """The Super Admin adds the account; the person sets their password; they log in."""
    address = f"{_unique(key)}@test.edu"
    resp = d['admin'].post('/admin/users/add', data={'name': key.title(), 'email': address, 'role': role,
                                                    'department': department})
    assert resp.status_code == 302, resp.data[:200]
    d['db'].collection('users').document(address).update({'password': generate_password_hash(PASSWORD)})
    return _login(d['app'], address, role)


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_super_admin_assigns_the_two_roles_and_they_land_on_naac(world):
    d = world
    for role in ('IQACCoordinator', 'DepartmentAdmin'):
        client = _appoint(d, role.lower(), role, department=CSE)
        resp = client.get('/', follow_redirects=False)
        assert resp.status_code == 302 and resp.headers['Location'].endswith('/naac/'), role
        assert client.get('/naac/').status_code == 200
    # The owner took the role off the login menu for now (UPG-204, 2026-11-06);
    # the logins above post it directly, which the server still accepts
    assert 'IQAC coordinator' not in d['app'].test_client().get('/login').get_data(as_text=True)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_categories_are_edited_by_the_super_admin_and_picked_by_the_organiser(world):
    d = world
    names = naac.categories(d['db'])
    assert 'Workshop' in names and 'Guest lecture' in names
    form = [('name', 'Workshop / hands-on training' if n == 'Workshop' else ('' if n == 'Placement' else n)) for n in names]
    from werkzeug.datastructures import MultiDict
    resp = d['admin'].post('/naac/categories', data=MultiDict(form + [('new', 'Hackathon')]))
    assert resp.status_code == 302
    names = naac.categories(d['db'])
    assert 'Workshop / hands-on training' in names and 'Placement' not in names and names[-1] == 'Hackathon'
    assert d['owner'].post('/naac/categories', data={'new': 'x'}).status_code == 403
    event_id = d['event']('Classified')
    d['owner'].post(f'/naac/events/{event_id}/report', data={'action': 'category', 'naac_category': 'Hackathon'})
    assert d['db'].collection('events').document(event_id).get().to_dict()['naac_category'] == 'Hackathon'
    d['owner'].post(f'/naac/events/{event_id}/report', data={'action': 'category', 'naac_category': 'Made up'})
    assert d['db'].collection('events').document(event_id).get().to_dict()['naac_category'] == 'Hackathon'


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_organiser_fills_and_submits_a_report_with_evidence(world):
    d = world
    event_id = d['event']('Reported Seminar')
    for name, ptype in (('Stu One', 'student'), ('Stu Two', 'student'), ('Dr. Fac', 'faculty'), ('Ext Erna', 'external')):
        d['person'](event_id, name, ptype=ptype)
    d['person'](event_id, 'Away Abe', attendance='Absent')
    d['person'](event_id, 'Team Lead', team_name='T', members=[{'name': 'Mem', 'email': 'mem@test.edu', 'attendance': 'Present'}])
    att = naac.attendance(d['db'], event_id, d['db'].collection('events').document(event_id).get().to_dict())
    assert (att['students'], att['faculty'], att['external'], att['total'], att['hours']) == (4, 1, 1, 6, 12.0)

    url = f'/naac/events/{event_id}/report'
    d['owner'].post(url, data={'action': 'submit', 'objectives': 'Teach AI'})
    assert 'Add a summary, outcomes before submitting' in _flash(d['owner'])
    up = f'/naac/events/{event_id}/files'
    d['owner'].post(up, data={'kind': 'photo', 'shareable': 'on', 'file': (io.BytesIO(_geotagged_jpeg()), 'stage.jpg')},
                    content_type='multipart/form-data')
    d['owner'].post(up, data={'kind': 'brochure', 'file': (io.BytesIO(b'%PDF-1.4 brochure'), 'brochure.pdf')},
                    content_type='multipart/form-data')
    gif = io.BytesIO()
    Image.new('RGB', (5, 5)).save(gif, format='GIF')
    d['owner'].post(up, data={'kind': 'photo', 'file': (io.BytesIO(gif.getvalue()), 'x.gif')}, content_type='multipart/form-data')
    assert 'Upload the photo as JPG, PNG' in _flash(d['owner'])
    d['owner'].post(up, data={'kind': 'evidence', 'file': (io.BytesIO(b'%PDF-' + b'0' * (11 * 1024 * 1024)), 'big.pdf')},
                    content_type='multipart/form-data')
    assert '10 MB or smaller' in _flash(d['owner'])
    d['owner'].post(url, data={'action': 'submit', 'objectives': 'Teach AI', 'summary': 'Two talks', 'outcomes': 'Skills',
                               'resource_name': 'Dr. R. Rao', 'resource_designation': 'Professor',
                               'resource_organisation': 'IISc', 'collaborator': 'IEEE Bangalore'})
    report = naac.get_report(d['db'], event_id)
    assert report['status'] == 'submitted' and report['resource_organisation'] == 'IISc'
    photo, brochure = report['files']
    assert photo['geotag'] == {'lat': 12.975, 'lon': 77.583333} and photo['shareable'] is True
    assert brochure['kind'] == 'brochure' and not brochure['shareable']
    resp = d['owner'].get(f"/naac/events/{event_id}/files/{photo['id']}")
    assert resp.status_code == 200 and resp.mimetype == 'image/jpeg'
    assert 'IEEE Bangalore' in d['owner'].get(url).get_data(as_text=True)


def _flash(client):
    with client.session_transaction() as sess:
        return ' '.join(m for _, m in sess.get('_flashes', []))


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_overdue_reports_get_one_reminder_a_day_and_the_iqac_coordinator_can_remind(world):
    d = world
    overdue = d['event']('Late Report', days_ago=10)
    not_yet = d['event']('Fresh Event', days_ago=2)
    first = naac.daily_reminders(d['db'])
    assert first['sent'] >= 1
    to_owner = [m for m in d['mail'] if m['to'] == d['email']['owner'] and 'Late Report' in m['subject']]
    assert len(to_owner) == 1 and f'/naac/events/{overdue}/report' in to_owner[0]['html']
    assert not [m for m in d['mail'] if 'Fresh Event' in m['subject']]                 # not due yet
    naac.daily_reminders(d['db'])                                                       # same day: nothing more
    assert len([m for m in d['mail'] if 'Late Report' in m['subject']]) == 1

    iqac = _appoint(d, 'iqacr', 'IQACCoordinator')
    page = iqac.get('/naac/').get_data(as_text=True)
    assert 'Late Report' in page and 'Overdue' in page and 'Fresh Event' in page
    iqac.post(f'/naac/events/{overdue}/remind')
    assert len([m for m in d['mail'] if 'Late Report' in m['subject']]) == 2
    d['owner'].post(f'/naac/events/{overdue}/report', data={'action': 'submit', 'objectives': 'a', 'summary': 'b',
                                                             'outcomes': 'c'})
    assert 'Late Report' not in iqac.get('/naac/').get_data(as_text=True)
    assert not_yet


# ── Criteria 5 and 6 ────────────────────────────────────────────────────────

def _year_of_data(d):
    seminar = d['event']('AI Seminar', naac_category='Seminar / conference', event_type='seminar')
    for name, ptype in (('S1', 'student'), ('F1', 'faculty'), ('E1', 'external')):
        d['person'](seminar, name, ptype=ptype)
    fdp = d['event']('FDP on ML', department=MECH, naac_category='FDP / professional development', event_type='fdp')
    d['person'](fdp, 'Dr. Meera Iyer', ptype='faculty', designation='Assistant Professor', institution='SNPSU')
    hack = d['event']('Code Sprint', naac_category='Technical competition', event_type='hackathon')
    d['person'](hack, 'Winner Wanda')
    event = d['db'].collection('events').document(hack).get().to_dict()
    certs.issue_one(hack, event, {'name': 'Winner Wanda', 'email': 'wanda@test.edu', 'person_key': 'wanda@test.edu',
                                  'cert_type': 'winner', 'position': 1})
    naac.save_report(d['db'], seminar, {'objectives': 'o', 'summary': 's', 'outcomes': 'u', 'resource_name': 'Dr. R. Rao',
                                        'resource_organisation': 'IISc'}, d['email']['owner'], submit=True)
    naac.add_file(d['db'], seminar, 'photo', 'hall.png', _png(), d['email']['owner'])
    naac.add_file(d['db'], fdp, 'evidence', 'attendance.pdf', b'%PDF-1.4 list', d['email']['owner'])
    return seminar, fdp, hack


def test_the_builder_summarises_details_awards_and_faculty_with_each_filter(world):
    d = world
    seminar, fdp, hack = _year_of_data(d)
    session = {'user_id': d['email']['admin'], 'role': 'SuperAdmin'}
    data = naac.build(d['db'], session, d['year'])
    mine = {s['category']: s for s in data['summary']}
    sem = mine['Seminar / conference']
    assert sem['events'] >= 1 and sem['students'] >= 1 and sem['faculty'] >= 1 and sem['external'] >= 1
    rows = {r['id']: r for rows in data['detail'].values() for r in rows}
    assert rows[seminar]['resource_person'] == 'Dr. R. Rao, IISc' and rows[seminar]['participants'] == 3
    assert rows[seminar]['report'] == 'submitted' and rows[fdp]['report'] == 'draft'
    assert any(a['name'] == 'Winner Wanda' and a['position'] == 1 for a in data['awards'])
    assert any(f['name'] == 'Dr. Meera Iyer' and f['institution'] == 'SNPSU' for f in data['faculty'])

    only_mech = naac.build(d['db'], session, d['year'], unit=MECH)
    assert {r['id'] for rows in only_mech['detail'].values() for r in rows} >= {fdp}
    assert seminar not in {r['id'] for rows in only_mech['detail'].values() for r in rows}
    by_cat = naac.build(d['db'], session, d['year'], category='Technical competition')
    assert list(by_cat['detail']) == ['Technical competition']
    by_type = naac.build(d['db'], session, d['year'], event_type='fdp')
    assert all(r['event_type'] == 'fdp' for rows in by_type['detail'].values() for r in rows)
    page = d['admin'].get(f"/naac/report?year={d['year']}").get_data(as_text=True)
    assert 'Seminar / conference' in page and 'Winner Wanda' in page and 'Dr. Meera Iyer' in page


def test_the_exports_follow_the_layout_file(world):
    import certificate_pdf
    d = world
    seminar, fdp, hack = _year_of_data(d)
    lay = json.load(open('config/naac_layout.json'))
    query = f"?year={d['year']}"
    book = openpyxl.load_workbook(io.BytesIO(d['admin'].get('/naac/report.xlsx' + query).data))
    assert {'Summary', 'Seminar  conference', 'FDP  professional development', 'Technical competition',
            'Awards', 'Faculty'} <= set(book.sheetnames)                       # a sheet per category
    assert [c.value for c in book['Summary'][1]] == [c['title'] for c in lay['summary']]
    cat_sheet = next(n for n in book.sheetnames if n.startswith('Seminar'))
    assert [c.value for c in book[cat_sheet][1]] == [c['title'] for c in lay['detail']]
    assert [c.value for c in book['Awards'][1]] == [c['title'] for c in lay['awards']]

    pdf = d['admin'].get('/naac/report.pdf' + query)
    text = ' '.join(certificate_pdf.text_of(pdf.data).split())
    assert pdf.mimetype == 'application/pdf' and certificate_pdf.branding()['name'] in text
    assert 'Summary by NAAC category' in text and 'Total:' in text and 'events' in text

    archive = zipfile.ZipFile(io.BytesIO(d['admin'].get('/naac/report.zip' + query).data))
    names = archive.namelist()
    assert any(n.startswith('Seminar _ conference/') and n.endswith('photo-hall.png') for n in names), names
    assert any(n.startswith('FDP _ professional development/') and 'evidence-attendance.pdf' in n for n in names), names


# ── Criterion 7 ─────────────────────────────────────────────────────────────

def test_each_role_may_do_only_its_part(world):
    d = world
    seminar, fdp, hack = _year_of_data(d)                  # seminar: CSE, owned by owner; fdp: Mechanical
    iqac = _appoint(d, 'iqacp', 'IQACCoordinator')
    dept_cse = _appoint(d, 'deptcse', 'DepartmentAdmin', department=CSE)
    dept_mech = _appoint(d, 'deptmech', 'DepartmentAdmin', department=MECH)
    report = f'/naac/events/{seminar}/report'
    edit = {'action': 'save', 'objectives': 'changed'}
    expect = {  # who: (view the report, edit it, builder, export, remind)
        'owner': (200, True, 403, 403, 403), 'other': (403, False, 403, 403, 403),
        'iqac': (200, False, 200, 200, 302), 'dept_cse': (200, False, 200, 200, 403),
        'dept_mech': (403, False, 200, 200, 403), 'admin': (200, True, 200, 200, 302),
        'student': (403, False, 403, 403, 403), 'coord': (403, False, 403, 403, 403)}
    clients = {'owner': d['owner'], 'other': d['other'], 'iqac': iqac, 'dept_cse': dept_cse, 'dept_mech': dept_mech,
               'admin': d['admin'], 'student': d['student'], 'coord': d['coord']}
    for who, (view, may_edit, builder, export, remind) in expect.items():
        c = clients[who]
        assert c.get(report).status_code == view, (who, 'view')
        before = naac.get_report(d['db'], seminar).get('objectives')
        status = c.post(report, data=edit).status_code
        assert (status == 302 and naac.get_report(d['db'], seminar).get('objectives') == 'changed') == may_edit, (who, 'edit')
        naac.save_report(d['db'], seminar, {'objectives': before}, 'reset')
        assert c.get(f"/naac/report?year={d['year']}").status_code == builder, (who, 'builder')
        assert c.get(f"/naac/report.xlsx?year={d['year']}").status_code == export, (who, 'export')
        assert c.post(f'/naac/events/{seminar}/remind').status_code == remind, (who, 'remind')
    # A department admin's builder holds only their department's events
    cse_rows = naac.build(d['db'], {'user_id': '', 'role': 'DepartmentAdmin'}, d['year'])
    assert cse_rows['detail'] == {}                       # no department on record: nothing
    page = dept_mech.get(f"/naac/report?year={d['year']}").get_data(as_text=True)
    assert 'FDP on ML' in page and 'AI Seminar' not in page
