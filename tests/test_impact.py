"""
tests/test_impact.py — UPG-145 on the real database layer: the impact
dashboard counts records exactly, organisers' hours-saved estimates,
testimonials with permission to quote, the 2-page impact report and the
optional public page. The data sits in February 2018, a month no other test
uses, so the counts are exact.
"""
import datetime
import io
import re

import pypdfium2
import pytest
from PIL import Image

import certificate_pdf
import services_certificates as certs
import services_impact as impact
import services_naac as naac
from tests.test_integration_flow import PASSWORD, _create_event, _login, _unique, _user

MONTH = '2018-02'


def _png(colour):
    buf = io.BytesIO()
    Image.new('RGB', (80, 60), colour).save(buf, format='PNG')
    return buf.getvalue()


@pytest.fixture
def world(real_app, monkeypatch):
    import utils_email
    flask_app, db = real_app
    mail = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k:
                        mail.append({'to': to, 'subject': subject, 'html': html}) or True)
    monkeypatch.setattr(certs, 'render', lambda event, cert: b'%PDF-1.4 ' + cert['number'].encode())
    owner_email, admin_email = f"{_unique('impowner')}@test.edu", f"{_unique('impadmin')}@test.edu"
    _user(db, owner_email, 'ClubSPOC', name='Olga Organiser')
    _user(db, admin_email, 'SuperAdmin')
    admin = flask_app.test_client()
    admin.post('/login', data={'role': 'SuperAdmin', 'email': admin_email, 'password': PASSWORD,
                               'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    owner = _login(flask_app, owner_email, 'ClubSPOC')
    tag = _unique('Dept').upper()

    def event(title, day, **fields):
        event_id = _create_event(owner, db, _unique(title), '2031-01-01', team=False)
        db.collection('events').document(event_id).update(dict({
            'status': 'completed', 'date': f'{MONTH}-{day:02d}', 'end_datetime': f'{MONTH}-{day:02d}', 'end_date': '',
            'staff': []}, **fields))
        return event_id

    def reg(event_id, name, registered=f'{MONTH}-01 10:00:00', **fields):
        reg_id = _unique('REG')
        db.collection('registrations').document(reg_id).set(dict({
            'event_id': event_id, 'lead_name': name, 'lead_email': f"{_unique(name.split()[0].lower())}@test.edu",
            'status': 'Confirmed', 'attendance': 'Present', 'registered_at': registered}, **fields))
        return reg_id
    return {'app': flask_app, 'db': db, 'mail': mail, 'admin': admin, 'owner': owner, 'owner_email': owner_email,
            'event': event, 'reg': reg, 'tag': tag}


def _a_month_of_records(d):
    a = d['event']('Impact Seminar', 10, department=f"{d['tag']}-X")
    b = d['event']('Impact Hack', 20, department=f"{d['tag']}-Y", club=f"{d['tag']}-Club")
    d['reg'](a, 'Present Pia')
    d['reg'](a, 'Absent Abe', attendance='Absent')
    d['reg'](a, 'External Eve', participant_type='external')
    d['reg'](a, 'Old Walkin', registered=f'{MONTH}-10 09:15:00', payment_mode='Cash', checkin_time='09:15:30')
    d['reg'](b, 'Team Lead', team_name='T', members=[{'name': 'Mate', 'email': 'mate.imp@test.edu', 'attendance': 'Present'}])
    d['reg'](b, 'Desk Dev', registered=f'{MONTH}-20 08:00:00', source='walk_in')
    event_a = d['db'].collection('events').document(a).get().to_dict()
    for name in ('Cert One', 'Cert Two', 'Cert Three'):
        cert = certs.issue_one(a, event_a, {'name': name, 'email': f"{name.split()[1].lower()}.imp@test.edu",
                                            'person_key': _unique('pk'), 'cert_type': 'participation'})
        certs.update(cert['id'], issued_at=datetime.datetime(2018, 2, 12, tzinfo=datetime.timezone.utc))
    certs.update(cert['id'], status='revoked')
    d['db'].collection('naac_reports').document(a).set({'event_id': a, 'status': 'submitted',
                                                        'submitted_at': f'{MONTH}-15T10:00:00+00:00'})
    d['db'].collection('naac_reports').document(b).set({'event_id': b, 'status': 'draft'})
    return a, b


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_dashboard_counts_every_figure_exactly(world):
    d = world
    _a_month_of_records(d)
    data = impact.dashboard(d['db'], year='2018')
    [feb] = [m for m in data['months'] if m['month'] == MONTH]
    assert (feb['events'], feb['registrations'], feb['forms_saved']) == (2, 6, 4)          # 2 walk-ins aren't forms
    assert (feb['checkins'], feb['expected'], feb['attendance_rate']) == (6, 7, 85.7)
    assert (feb['certificates'], feb['naac_reports'], feb['external'], feb['units']) == (2, 1, 1, 3)
    assert '2018-01' not in [m['month'] for m in data['months']]                          # nothing invented
    year_2018 = next(y for y in data['years'] if y['year'] == '2018')
    assert year_2018['events'] >= 2 and year_2018['certificates'] >= 2
    page = d['admin'].get('/impact/dashboard?year=2018').get_data(as_text=True)
    assert MONTH in page and '85.7% <span class="text-muted small">(6 of 7)</span>' in page
    assert d['owner'].get('/impact/dashboard').status_code == 403


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_hours_saved_are_the_organisers_estimates(world):
    d = world
    a, b = _a_month_of_records(d)
    c = d['event']('Unanswered', 25)
    before = impact.time_saved(d['db'])
    d['owner'].post(f'/impact/events/{a}/hours', data={'hours_saved': '3'})
    d['owner'].post(f'/impact/events/{b}/hours', data={'hours_saved': '5.5'})
    d['owner'].post(f'/impact/events/{c}/hours', data={'hours_saved': '9999'})            # refused
    after = impact.time_saved(d['db'])
    assert after['events'] - before['events'] == 2 and after['total'] - before['total'] == 8.5
    assert after['average'] == round(after['total'] / after['events'], 1)
    assert 'organisers\' own estimates' in d['admin'].get('/impact/dashboard').get_data(as_text=True)
    assert 'About how many hours did SapthaEvent save you?' in d['owner'].get(f'/naac/events/{a}/report').get_data(as_text=True)


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_testimonials_are_asked_once_and_only_quotable_ones_can_be_approved(world, monkeypatch):
    d = world
    monkeypatch.setenv('TESTIMONIAL_SAMPLE', '2')
    event_id = d['event']('Asked Event', 5)
    for i in range(4):
        d['reg'](event_id, f'Attendee {i}')
    d['reg'](event_id, 'No Show', attendance='Absent')
    impact.request_testimonials(d['db'])
    asked = [m for m in d['mail'] if 'Asked Event' in m['subject']]
    assert len(asked) == 3 and d['owner_email'] in [m['to'] for m in asked]               # organiser + 2 of 4
    impact.request_testimonials(d['db'])
    assert len([m for m in d['mail'] if 'Asked Event' in m['subject']]) == 3              # once per event

    links = [re.search(r'(/impact/testimonial/[^\s"<]+)', m['html']).group(1) for m in asked]
    visitor = d['app'].test_client()
    assert visitor.get(links[0][:-2] + 'xx').status_code == 404                           # altered
    visitor.post(links[0], data={'rating': '5', 'comment': 'Check-in took seconds.', 'may_quote': 'on'})
    visitor.post(links[1], data={'rating': '4', 'comment': 'Keep this private please.'})
    rows = {r['comment']: r for r in impact.testimonials(d['db'])}
    quotable, private = rows['Check-in took seconds.'], rows['Keep this private please.']
    d['admin'].post(f"/impact/testimonials/{private['id']}/approve")
    assert private['id'] not in [r['id'] for r in impact.testimonials(d['db'], approved_only=True)]
    assert next(r for r in impact.testimonials(d['db']) if r['id'] == private['id'])['approved'] is False
    d['admin'].post(f"/impact/testimonials/{quotable['id']}/approve")
    assert quotable['id'] in [r['id'] for r in impact.testimonials(d['db'], approved_only=True)]
    d['admin'].post(f"/impact/testimonials/{quotable['id']}/withdraw")
    assert quotable['id'] not in [r['id'] for r in impact.testimonials(d['db'], approved_only=True)]


# ── Criteria 4 and 5 ────────────────────────────────────────────────────────

def test_the_impact_report_and_the_public_page_show_approved_material_only(world):
    d = world
    a, b = _a_month_of_records(d)
    naac.add_file(d['db'], a, 'photo', 'shared.png', _png('red'), d['owner_email'], shareable=True)
    naac.add_file(d['db'], a, 'photo', 'private.png', _png('blue'), d['owner_email'], shareable=False)
    claim = {'e': a, 'n': 'Quoted Quinn', 'r': 'Student'}
    ok = impact.save_testimonial(d['db'], dict(claim, m=f"{_unique('q')}@test.edu"), 5, 'A UNIQUE APPROVED LINE', True)
    impact.save_testimonial(d['db'], dict(claim, m=f"{_unique('n')}@test.edu"), 2, 'A NOT APPROVED LINE', True)
    impact.set_approved(d['db'], f"{a}:{ok['email']}", True, 'test')

    pdf = d['admin'].get(f'/impact/report.pdf?start={MONTH}&end={MONTH}').data
    assert len(pypdfium2.PdfDocument(pdf)) <= 2
    text = ' '.join(certificate_pdf.text_of(pdf).split())
    assert certificate_pdf.branding()['name'] in text and 'Events held' in text and 'Check-ins' in text
    assert 'A UNIQUE APPROVED LINE' in text and 'A NOT APPROVED LINE' not in text
    assert pdf.count(b'/Subtype /Image') == 1                                             # the shareable photo only
    assert d['owner'].get(f'/impact/report.pdf?start={MONTH}&end={MONTH}').status_code == 403

    visitor = d['app'].test_client()
    assert visitor.get('/impact').status_code == 404
    d['admin'].post('/impact/public', data={'public': 'on'})
    try:
        page = visitor.get('/impact').get_data(as_text=True)
        assert '2018' in page and 'A UNIQUE APPROVED LINE' in page and 'A NOT APPROVED LINE' not in page
        assert any(str(a_.to_dict().get('details', '')).endswith(': on') for a_ in d['db'].collection('audit_log').stream()
                   if a_.to_dict().get('action') == 'IMPACT_PUBLIC_PAGE')
    finally:
        d['admin'].post('/impact/public', data={'public': 'off'})
    assert visitor.get('/impact').status_code == 404
