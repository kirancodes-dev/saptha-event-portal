"""
tests/test_hackathon_portal.py — Phase 1 of the Hack2skill-style hackathon,
on the real database layer (owner's request, 2026-11-05):

  * UPG-197: the login page offers Admin, SPOC, Event coordinator, Judge and
    Student; the older staff roles are hidden, and still log in.
  * UPG-195: a hackathon emails participants only at registration (with the
    WhatsApp group and "check the portal"), for passwords, and the final
    result to the lead; everything else is a portal notice.
  * UPG-190: problem statements added after registration, released now or
    at a set time, seen only by registered teams once released.
  * UPG-191: a submission form the SPOC builds, open between two times the
    server enforces, edited until the deadline, with deadline extensions.
  * UPG-196: the student's hackathon page: stages, countdowns, updates, team,
    WhatsApp link; refreshed by a 60-second poll.
"""
import datetime
import io
import re

import pytest

import services_hackathon as hk
import utils_email
from tests.test_integration_flow import _create_event, _login, _unique, _user

PDF = b'%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n'
UTC = datetime.timezone.utc


@pytest.fixture
def hack(real_app, monkeypatch, tmp_path):
    flask_app, db = real_app
    monkeypatch.setenv('PRIVATE_STORAGE_DIR', str(tmp_path / 'private'))
    clock = {'now': datetime.datetime(2026, 11, 20, 4, 30, tzinfo=UTC)}   # 10:00 IST
    monkeypatch.setattr(hk, '_now', lambda: clock['now'])
    sent = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html, *a, **k: sent.append(
        {'to': to, 'subject': subject, 'html': html}) or True)

    spoc, other_spoc = f"{_unique('hkspoc')}@test.edu", f"{_unique('hkother')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, other_spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    stranger = _login(flask_app, other_spoc, 'ClubSPOC')

    def event(kind='hackathon', group='https://chat.whatsapp.com/HackGroup123'):
        event_id = _create_event(owner, db, _unique('Portal Hack'), '2026-11-28', team=True)
        db.collection('events').document(event_id).update({
            'event_type': kind, 'status': 'registration_open', 'timezone': 'Asia/Kolkata',
            'reg_deadline': '2026-11-25', 'contact': {'phone': '', 'group_link': group}})
        return event_id

    def team(event_id, name='Alpha', members=()):
        lead = f"{_unique('hklead')}@test.edu"
        _user(db, lead, 'Student', name=f"{name} Lead")
        reg_id = _unique('REG')
        db.collection('registrations').document(reg_id).set({
            'event_id': event_id, 'lead_email': lead, 'lead_name': f"{name} Lead", 'lead_phone': '9876543210',
            'team_name': name, 'status': 'Confirmed', 'payment_status': 'Free', 'attendance': 'Pending',
            'current_round': 1, 'is_eliminated': False,
            'members': [{'role': 'Member', 'name': m, 'email': m} for m in members]})
        return {'lead': lead, 'reg_id': reg_id, 'client': _login(flask_app, lead, 'Student')}

    def ev(event_id):
        return db.collection('events').document(event_id).get().to_dict()

    def form(event_id, opens='2026-11-20T09:00', closes='2026-11-22T18:00', fields=None):
        data = {'opens_at': opens, 'closes_at': closes}
        fields = fields or [('Project title', 'text', True), ('Problem statement', 'problem', True),
                            ('GitHub repository', 'link', True), ('Presentation', 'pdf', True),
                            ('Approach', 'textarea', False)]
        for i, (label, kind, required) in enumerate(fields):
            data.update({f'field_{i}_label': label, f'field_{i}_kind': kind, f'field_{i}_max_mb': '1'})
            if required:
                data[f'field_{i}_required'] = 'on'
        return owner.post(f'/spoc/hackathon/{event_id}/form', data=data)

    def problem(event_id, title='Clean water', release='now', at='', pdf=None):
        data = {'title': title, 'description': f'{title}: build something useful.', 'track': 'Social',
                'release': release, 'release_at': at}
        if pdf is not None:
            data['pdf'] = (io.BytesIO(pdf), 'brief.pdf')
        return owner.post(f'/spoc/hackathon/{event_id}/problems', data=data, content_type='multipart/form-data')

    def field_ids(event_id):
        return {f['label']: f['id'] for f in hk.form(ev(event_id))['fields']}

    def submit(t, event_id, **answers):
        ids = field_ids(event_id)
        data = {}
        for label, value in answers.items():
            label = label.replace('_', ' ')
            key = f"f_{ids[label]}"
            data[key] = (io.BytesIO(value), 'deck.pdf') if isinstance(value, bytes) else value
        return t['client'].post(f'/hackathon/{event_id}/submit', data=data, content_type='multipart/form-data')

    def sub(t):
        return hk.submission_for(db, _reg_id(db, t))[1] or {}

    return {'app': flask_app, 'db': db, 'owner': owner, 'stranger': stranger, 'spoc': spoc, 'clock': clock,
            'sent': sent, 'event': event, 'team': team, 'ev': ev, 'form': form, 'problem': problem,
            'field_ids': field_ids, 'submit': submit, 'sub': sub}


def _reg_id(db, t):
    event_id = db.collection('registrations').document(t['reg_id']).get().to_dict()['event_id']
    reg_id = hk.team_for(db, event_id, t['lead'])[0]
    assert reg_id
    return reg_id


def _page(client, url):
    resp = client.get(url)
    assert resp.status_code == 200, (url, resp.status_code, resp.headers.get('Location'))
    return resp.get_data(as_text=True)


def _ist(day, clock):
    """An IST wall-clock time as UTC."""
    return datetime.datetime.fromisoformat(f"{day}T{clock}").replace(
        tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30))).astimezone(UTC)


# ═══ UPG-197: the login page ═══════════════════════════════════════════════

def test_the_login_page_offers_only_five_roles(real_app):
    # UPG-197 hid the older staff roles behind "Other staff role"; the owner
    # then asked for the five only (UPG-204, 2026-11-06), so the menu has no
    # other option, group or button
    flask_app, db = real_app
    page = flask_app.test_client().get('/login').get_data(as_text=True)
    found = re.search(r'<select name="role" id="roleSelect".*?</select>', page, re.S)
    assert found
    select = found.group(0)
    assert '<optgroup' not in select
    options = re.findall(r'<option value="(\w*)"[^>]*>([^<]+)</option>', select)
    assert options == [('', 'Choose your role...'), ('SuperAdmin', 'Admin'), ('ClubSPOC', 'SPOC'),
                       ('EventCoordinator', 'Event coordinator'), ('Judge', 'Judge'), ('Student', 'Student')]
    for gone in ('otherRolesBtn', 'otherRoles', 'Other staff role', 'Volunteer', 'IQACCoordinator', 'DepartmentAdmin'):
        assert gone not in page, gone
    js = open('static/js/pages/login.js', encoding='utf-8').read()
    assert 'otherRoles' not in js

    # Each of the five logs in with its role; the server still accepts an
    # older staff role posted directly, so those accounts aren't broken
    for role in ('ClubSPOC', 'EventCoordinator', 'Judge', 'Student', 'Volunteer', 'IQACCoordinator'):
        email = f"{_unique('role')}@test.edu"
        _user(db, email, role)
        _login(flask_app, email, role)


# ═══ UPG-205: no AI chat widget on the home page ═══════════════════════════

def test_the_home_page_has_no_ai_chat_widget(real_app):
    flask_app, _ = real_app
    page = flask_app.test_client().get('/').get_data(as_text=True)
    for gone in ('chat-fab', 'chatWin', 'chatPromptBubble', 'Sparky', 'AI Assistant', 'fa-robot'):
        assert gone not in page, gone
    js = open('static/js/pages/index.js', encoding='utf-8').read()
    assert '/chatbot/ask' not in js and 'initChatPrompt' not in js and 'toggleChat' not in js
    handlers = open('static/js/handlers/index.js', encoding='utf-8').read()
    assert 'toggleChat' not in handlers and 'sendChat' not in handlers


# ═══ UPG-195: two emails for a hackathon participant ═══════════════════════

def test_a_hackathon_registration_is_one_email_with_the_whatsapp_and_portal_instructions(hack, monkeypatch):
    h = hack
    import routes_forms
    monkeypatch.setattr(routes_forms, 'send_registration_confirmed_email', utils_email.send_registration_confirmed_email)
    eid = h['event']()
    assert hk.email_mode(h['ev'](eid)) == 'portal'   # the default for a hackathon

    # A new account: the set-password email carries the instructions
    lead, mate = f"{_unique('newlead')}@test.edu", f"{_unique('mate')}@test.edu"
    resp = h['app'].test_client().post(f'/forms/submit/{eid}', data={
        'privacy_consent': 'yes', 'full_name': 'Nia Lead', 'email': lead, 'phone': '9876543210', 'usn': '1SN22CS300',
        'team_name': 'New Team', 'member_1_name': 'Mo Mate', 'member_1_email': mate, 'member_1_usn': '1SN22CS301'})
    assert resp.status_code == 302, resp.data[:300]
    # The lead's one email; since UPG-207 (owner, 2026-11-09) the member the
    # lead listed also gets one, their confirmation link, and nothing else
    assert [m['to'] for m in h['sent']] == [lead, mate]
    assert '/teams/confirm/' in h['sent'][1]['html'] and 'chat.whatsapp.com' not in h['sent'][1]['html']
    html = h['sent'][0]['html']
    assert 'https://chat.whatsapp.com/HackGroup123' in html
    assert f'/hackathon/{eid}' in html and "won't email them" in html.replace('&#x27;', "'").replace('&#39;', "'")
    assert '/set_password/' in html

    # An existing account: one confirmation, with the same instructions
    old = f"{_unique('oldlead')}@test.edu"
    _user(db := h['db'], old, 'Student')
    h['sent'].clear()
    resp = h['app'].test_client().post(f'/forms/submit/{eid}', data={
        'privacy_consent': 'yes', 'full_name': 'Ola Lead', 'email': old, 'phone': '9876543211', 'usn': '1SN22CS302',
        'team_name': 'Old Team', 'member_1_name': 'Mia Mate', 'member_1_email': f"{_unique('m2')}@test.edu",
        'member_1_usn': '1SN22CS303'})
    assert resp.status_code == 302
    assert [m['to'] for m in h['sent']][:1] == [old] and len(h['sent']) == 2   # and the member's link (UPG-207)
    assert '/teams/confirm/' in h['sent'][1]['html']
    assert 'https://chat.whatsapp.com/HackGroup123' in h['sent'][0]['html']
    assert 'emailed to you <strong>1 day before' not in h['sent'][0]['html']
    assert db is h['db']


def test_round_results_in_portal_mode_are_portal_notices_not_emails(hack):
    h = hack
    eid = h['event']()
    h['db'].collection('events').document(eid).update({'status': 'in_progress', 'total_rounds': 2, 'active_round': 1})
    a, b = h['team'](eid, 'Alpha', members=[f"{_unique('ma')}@test.edu"]), h['team'](eid, 'Bravo')
    h['db'].collection('registrations').document(a['reg_id']).update({'scores': {'j@test.edu': {'total': 9}}})
    h['db'].collection('registrations').document(b['reg_id']).update({'scores': {'j@test.edu': {'total': 3}}})
    h['sent'].clear()
    resp = h['owner'].post(f'/spoc/advance_round/{eid}', data={'mode': 'top_n', 'top_n': '1', 'round': '1'})
    assert resp.status_code == 302
    assert h['sent'] == []
    page = _page(a['client'], f'/hackathon/{eid}')
    assert 'Round 1 results are out' in page
    notes = [d.to_dict() for d in h['db'].collection('notifications_v2').where('user_email', '==', a['lead']).stream()]
    assert any('Through to round 2' in n['title'] for n in notes)
    notes_b = [d.to_dict() for d in h['db'].collection('notifications_v2').where('user_email', '==', b['lead']).stream()]
    assert any('Round 1 result' in n['title'] for n in notes_b)


def test_portal_mode_sends_no_ticket_reminder_broadcast_certificate_or_waitlist_email(hack, monkeypatch):
    h = hack
    import tasks.email_tasks
    import tasks.scheduled_tasks as jobs
    queued: list = []
    monkeypatch.setattr(tasks.email_tasks.send_ticket_email_task, 'delay', lambda **k: queued.append(('ticket', k)))
    monkeypatch.setattr(tasks.email_tasks.send_generic_email_task, 'delay', lambda **k: queued.append(('generic', k)))
    monkeypatch.setattr(tasks.email_tasks.send_certificate_email, 'delay', lambda *a, **k: queued.append(('cert', a)))
    ist_today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()

    hack_eid, plain_eid = h['event'](), h['event'](kind='workshop')
    for eid, day in ((hack_eid, 1), (plain_eid, 1)):
        h['db'].collection('events').document(eid).update({
            'status': 'active', 'date': (ist_today + datetime.timedelta(days=day)).isoformat()})
    ht, pt = h['team'](hack_eid, 'Hackers'), h['team'](plain_eid, 'Workshoppers')
    jobs.send_24h_reminders()
    tickets = [k['to_email'] for kind, k in queued if kind == 'ticket']
    assert pt['lead'] in tickets and ht['lead'] not in tickets       # the other event is unchanged
    notes = [d.to_dict() for d in h['db'].collection('notifications_v2').where('user_email', '==', ht['lead']).stream()]
    assert any(n['link'].startswith('/ticket/') for n in notes)

    # 3-day reminder
    for eid in (hack_eid, plain_eid):
        h['db'].collection('events').document(eid).update({'date': (ist_today + datetime.timedelta(days=3)).isoformat()})
    queued.clear()
    jobs.send_3day_reminders()
    generic = [k['to_email'] for kind, k in queued if kind == 'generic']
    assert pt['lead'] in generic and ht['lead'] not in generic

    # The SPOC's blast becomes an update on the hackathon page; no email
    h['sent'].clear()
    resp = h['owner'].post(f'/spoc/blast_email/{hack_eid}', data={'subject': 'Venue moved', 'body': 'Lab 3 now.',
                                                                   'audience': 'all'})
    assert resp.status_code == 302 and h['sent'] == []
    assert 'Venue moved' in _page(ht['client'], f'/hackathon/{hack_eid}')

    # A certificate isn't emailed for the portal-only event
    import services_certificates
    queued.clear()
    services_certificates.deliver({'id': 'c1', 'email': ht['lead'], 'event_id': hack_eid})
    services_certificates.deliver({'id': 'c2', 'email': pt['lead'], 'event_id': plain_eid})
    assert [a for kind, a in queued if kind == 'cert'] == [('c2',)]

    # Senders' gate, kind by kind
    event = h['ev'](hack_eid)
    assert [k for k in ('registration', 'password', 'result') if hk.email_allowed(event, k)] == \
        ['registration', 'password', 'result']
    assert not any(hk.email_allowed(event, k) for k in
                   ('ticket', 'reminder', 'round', 'broadcast', 'room', 'certificate', 'team', 'waitlist',
                    'feedback', 'transfer', 'change'))


def test_forgot_password_and_the_result_still_email_the_lead(hack):
    h = hack
    eid = h['event']()
    t = h['team'](eid, 'Alpha', members=[f"{_unique('mm')}@test.edu"])
    h['sent'].clear()
    h['app'].test_client().post('/forgot_password', data={'email': t['lead'], 'role': 'Student'})
    assert [m['to'] for m in h['sent']] == [t['lead']] and '/reset_token/' in h['sent'][0]['html']

    # The coordinator's published results: the winner's lead only
    h['db'].collection('events').document(eid).update({'status': 'in_progress'})
    h['db'].collection('registrations').document(t['reg_id']).update(
        {'scores': {'j@test.edu': {'total': 9}}, 'attendance': 'Present'})
    h['sent'].clear()
    h['owner'].post(f'/coordinator/publish_results/{eid}')
    result_mails = [m for m in h['sent'] if 'Results' in m['subject']]
    assert result_mails and {m['to'] for m in result_mails} == {t['lead']}


def test_the_spoc_switches_the_email_mode_and_others_cant(hack):
    h = hack
    eid, plain = h['event'](), h['event'](kind='workshop')
    assert hk.email_mode(h['ev'](plain)) == 'all'
    assert h['stranger'].post(f'/spoc/hackathon/{eid}/emails', data={'mode': 'all'}).status_code == 403
    assert h['owner'].post(f'/spoc/hackathon/{eid}/emails', data={'mode': 'all'}).status_code == 302
    assert hk.email_mode(h['ev'](eid)) == 'all' and hk.email_allowed(h['ev'](eid), 'ticket')
    h['owner'].post(f'/spoc/hackathon/{eid}/emails', data={'mode': 'portal'})
    assert hk.email_mode(h['ev'](eid)) == 'portal'


# ═══ UPG-190: problem statements ═══════════════════════════════════════════

def test_problem_statements_show_to_registered_teams_only_after_release(hack):
    h = hack
    eid = h['event']()
    t = h['team'](eid)
    assert 'haven&#39;t been released yet' in _page(t['client'], f'/hackathon/{eid}') or \
        "haven't been released yet" in _page(t['client'], f'/hackathon/{eid}')

    assert h['problem'](eid, 'Clean water', pdf=PDF).status_code == 302
    assert h['problem'](eid, 'Smart grid', release='later', at='2026-11-21T09:00').status_code == 302
    page = _page(t['client'], f'/hackathon/{eid}')
    assert 'Clean water' in page and 'Smart grid' not in page
    assert 'Problem statement released: Clean water' in page        # on the updates feed

    smart = next(p for p in hk.problems(h['ev'](eid)) if p['title'] == 'Smart grid')
    clean = next(p for p in hk.problems(h['ev'](eid)) if p['title'] == 'Clean water')
    assert smart['release_at'] == _ist('2026-11-21', '09:00').isoformat()

    # The clock reaches the release time: it shows, without anyone pressing anything
    h['clock']['now'] = _ist('2026-11-21', '09:01')
    assert 'Smart grid' in _page(t['client'], f'/hackathon/{eid}')

    # The PDF: the registered team and staff, never anyone else
    assert t['client'].get(f'/hackathon/{eid}/problem/{clean["id"]}/pdf').data == PDF
    assert h['owner'].get(f'/hackathon/{eid}/problem/{clean["id"]}/pdf').status_code == 200
    outsider = f"{_unique('out')}@test.edu"
    _user(h['db'], outsider, 'Student')
    out = _login(h['app'], outsider, 'Student')
    assert out.get(f'/hackathon/{eid}/problem/{clean["id"]}/pdf').status_code == 403
    assert out.get(f'/hackathon/{eid}').status_code == 302          # no page for a non-registrant


def test_a_scheduled_pdf_is_refused_before_release_and_released_ones_cant_be_removed(hack):
    h = hack
    eid = h['event']()
    t = h['team'](eid)
    h['problem'](eid, 'Later one', release='later', at='2026-11-21T09:00', pdf=PDF)
    later = hk.problems(h['ev'](eid))[0]
    assert t['client'].get(f'/hackathon/{eid}/problem/{later["id"]}/pdf').status_code == 403
    assert 'Released on' in _page(t['client'], f'/hackathon/{eid}') or 'released on' in _page(t['client'], f'/hackathon/{eid}')

    # Release it now; then it can't be removed
    h['owner'].post(f'/spoc/hackathon/{eid}/problems/{later["id"]}/release')
    assert hk.is_released(hk.problems(h['ev'](eid))[0])
    h['owner'].post(f'/spoc/hackathon/{eid}/problems/{later["id"]}/delete')
    assert len(hk.problems(h['ev'](eid))) == 1

    # Not a PDF; a time in the past; no title: refused, nothing added
    h['problem'](eid, 'Fake', pdf=b'<html>not a pdf</html>')
    h['problem'](eid, 'Past', release='later', at='2026-11-01T09:00')
    h['owner'].post(f'/spoc/hackathon/{eid}/problems', data={'title': '', 'description': 'x'})
    assert [p['title'] for p in hk.problems(h['ev'](eid))] == ['Later one']


def test_another_spoc_cant_manage_the_hackathon(hack):
    h = hack
    eid = h['event']()
    h['problem'](eid, 'Mine')
    pid = hk.problems(h['ev'](eid))[0]['id']
    s = h['stranger']
    assert s.get(f'/spoc/hackathon/{eid}').status_code == 403
    for url, data in ((f'/spoc/hackathon/{eid}/problems', {'title': 'X', 'description': 'Y'}),
                      (f'/spoc/hackathon/{eid}/problems/{pid}/delete', {}),
                      (f'/spoc/hackathon/{eid}/form', {'opens_at': '2026-11-20T09:00', 'closes_at': '2026-11-22T09:00',
                                                       'field_0_label': 'A', 'field_0_kind': 'text'}),
                      (f'/spoc/hackathon/{eid}/extend', {'minutes': '60'}),
                      (f'/spoc/hackathon/{eid}/update', {'title': 'Hi'})):
        assert s.post(url, data=data).status_code == 403, url
    assert len(hk.problems(h['ev'](eid))) == 1 and not hk.has_form(h['ev'](eid))
    assert h['owner'].get(f'/spoc/hackathon/{eid}').status_code == 200


# ═══ UPG-191: the submission form and its deadline ═════════════════════════

def test_the_spoc_builds_a_form_and_the_lead_submits_and_edits_until_the_deadline(hack):
    h = hack
    eid = h['event']()
    h['problem'](eid, 'Clean water')
    pid = hk.problems(h['ev'](eid))[0]['id']
    assert h['form'](eid).status_code == 302
    form = hk.form(h['ev'](eid))
    assert [f['kind'] for f in form['fields']] == ['text', 'problem', 'link', 'pdf', 'textarea']
    assert form['opens_at'] == _ist('2026-11-20', '09:00').isoformat()
    assert form['closes_at'] == _ist('2026-11-22', '18:00').isoformat()
    assert form['fields'][3]['max_mb'] == 1

    t = h['team'](eid)
    resp = h['submit'](t, eid, Project_title='AquaSense', Problem_statement=pid,
                       GitHub_repository='https://github.com/team/aquasense', Presentation=PDF)
    assert resp.status_code == 302
    sub = h['sub'](t)
    ids = h['field_ids'](eid)
    assert sub['project_title'] == 'AquaSense' and sub['problem_id'] == pid and sub['problem_title'] == 'Clean water'
    assert sub['answers'][ids['GitHub repository']] == 'https://github.com/team/aquasense'
    pdf = sub['answers'][ids['Presentation']]
    assert pdf['name'] == 'deck.pdf' and pdf['size'] == len(PDF) and pdf['key'].startswith(f'hackathon/{eid}/')

    # Edit before the deadline: the PDF is kept when no new file comes
    h['clock']['now'] = _ist('2026-11-22', '17:59')
    resp = h['submit'](t, eid, Project_title='AquaSense 2', Problem_statement=pid,
                       GitHub_repository='https://github.com/team/aquasense2')
    assert resp.status_code == 302
    sub = h['sub'](t)
    assert sub['project_title'] == 'AquaSense 2' and sub['answers'][ids['Presentation']] == pdf
    assert sub['versions'] == 2
    assert len(hk.submissions(h['db'], eid)) == 1

    # The private PDF: the team and the SPOC; not another team's lead
    reg_id = _reg_id(h['db'], t)
    url = f"/hackathon/{eid}/file/{reg_id}/{ids['Presentation']}"
    assert t['client'].get(url).data == PDF
    assert h['owner'].get(url).status_code == 200
    other = h['team'](eid, 'Bravo')
    assert other['client'].get(url).status_code == 403
    assert 'AquaSense 2' in _page(h['owner'], f'/spoc/hackathon/{eid}')


def test_the_server_refuses_submissions_before_opening_and_after_the_deadline(hack):
    h = hack
    eid = h['event']()
    h['problem'](eid, 'Clean water')
    pid = hk.problems(h['ev'](eid))[0]['id']
    h['form'](eid, opens='2026-11-20T12:00', closes='2026-11-22T18:00')
    t = h['team'](eid)
    answers = dict(Project_title='Early', Problem_statement=pid, GitHub_repository='https://github.com/x/y',
                   Presentation=PDF)

    h['submit'](t, eid, **answers)                          # 10:00 IST: not open yet
    assert h['sub'](t) == {}
    h['clock']['now'] = _ist('2026-11-22', '18:00')         # exactly the deadline: closed
    h['submit'](t, eid, **answers)
    assert h['sub'](t) == {}
    page = _page(t['client'], f'/hackathon/{eid}')
    assert 'Submissions closed' in page and '<form method="POST" action="/hackathon/' not in page


def test_bad_answers_are_refused_and_nothing_is_saved(hack):
    h = hack
    eid = h['event']()
    h['problem'](eid, 'Released')
    h['problem'](eid, 'Scheduled', release='later', at='2026-11-23T09:00')
    released, scheduled = (p['id'] for p in hk.problems(h['ev'](eid)))
    h['form'](eid)
    t = h['team'](eid)
    ok = dict(Project_title='Fine', Problem_statement=released, GitHub_repository='https://github.com/a/b',
              Presentation=PDF)
    for bad in ({'Project_title': ''},                                   # required
                {'GitHub_repository': 'javascript:alert(1)'},            # not a link
                {'Presentation': b'<html></html>'},                      # not a PDF
                {'Presentation': PDF + b'0' * (1024 * 1024)},            # over its 1 MB
                {'Problem_statement': scheduled},                        # not released
                {'Project_title': 'x' * 201}):                           # too long
        h['submit'](t, eid, **{**ok, **bad})
        assert h['sub'](t) == {}, bad
    h['submit'](t, eid, **ok)
    assert h['sub'](t)['project_title'] == 'Fine'


def test_only_the_team_lead_submits(hack):
    h = hack
    eid = h['event']()
    h['form'](eid, fields=[('Title', 'text', True)])
    member = f"{_unique('member')}@test.edu"
    t = h['team'](eid, members=[member])
    _user(h['db'], member, 'Student')
    mc = _login(h['app'], member, 'Student')
    ids = h['field_ids'](eid)
    assert mc.post(f'/hackathon/{eid}/submit', data={f"f_{ids['Title']}": 'Sneaky'}).status_code == 403
    assert hk.submissions(h['db'], eid) == []

    # A team knocked out in a round can't submit either
    h['db'].collection('registrations').document(t['reg_id']).update({'is_eliminated': True})
    h['submit'](t, eid, Title='Out')
    assert hk.submissions(h['db'], eid) == []


def test_the_spoc_extends_the_deadline_and_late_teams_can_submit_again(hack):
    h = hack
    eid = h['event']()
    h['form'](eid, fields=[('Title', 'text', True)])
    t = h['team'](eid)
    h['clock']['now'] = _ist('2026-11-22', '18:30')          # 30 minutes past the deadline
    h['submit'](t, eid, Title='Too late')
    assert h['sub'](t) == {}

    # 15 minutes still ends in the past: refused, nothing changes
    h['owner'].post(f'/spoc/hackathon/{eid}/extend', data={'minutes': '15'})
    assert hk.form(h['ev'](eid))['closes_at'] == _ist('2026-11-22', '18:00').isoformat()

    # 2 hours from the old deadline: 20:00 IST
    h['owner'].post(f'/spoc/hackathon/{eid}/extend', data={'minutes': '120', 'reason': 'Wi-Fi outage'})
    form = hk.form(h['ev'](eid))
    assert form['closes_at'] == _ist('2026-11-22', '20:00').isoformat()
    assert form['extensions'][-1]['minutes'] == 120 and form['extensions'][-1]['reason'] == 'Wi-Fi outage'
    h['submit'](t, eid, Title='Made it')
    assert h['sub'](t)['project_title'] == 'Made it'
    page = _page(t['client'], f'/hackathon/{eid}')
    assert 'Deadline extended by 2 hours' in page and 'Wi-Fi outage' in page

    # A custom amount: 1 hour 30 minutes → 21:30 IST
    h['owner'].post(f'/spoc/hackathon/{eid}/extend', data={'minutes': 'custom', 'custom_hours': '1',
                                                            'custom_minutes': '30'})
    assert hk.form(h['ev'](eid))['closes_at'] == _ist('2026-11-22', '21:30').isoformat()
    for bad in ('0', '-5', str(8 * 24 * 60), 'abc'):
        h['owner'].post(f'/spoc/hackathon/{eid}/extend', data={'minutes': bad})
    assert len(hk.form(h['ev'](eid))['extensions']) == 2
    h['clock']['now'] = _ist('2026-11-22', '21:31')
    h['submit'](t, eid, Title='After the extension')
    assert h['sub'](t)['project_title'] == 'Made it'


def test_the_submit_page_reads_one_event_not_every_registration(hack, monkeypatch):
    h = hack
    eid, legacy = h['event'](), h['event']()
    h['form'](eid, fields=[('Title', 'text', True)])
    t = h['team'](eid)
    lt = h['team'](legacy)
    import db_adapter
    unfiltered = []
    real_stream = db_adapter.SQLQuery.stream

    def stream(self, *a, **k):     # a collection's own stream() comes through here too
        if self.collection.id in ('registrations', 'project_submissions') and not self.filters:
            unfiltered.append(self.collection.id)
        return real_stream(self, *a, **k)
    monkeypatch.setattr(db_adapter.SQLQuery, 'stream', stream)

    # With the SPOC's form, the old page sends the team to the hackathon page
    resp = t['client'].get(f'/hackathon/submit/{eid}')
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/hackathon/{eid}')
    _page(t['client'], f'/hackathon/{eid}')
    t['client'].post(f'/hackathon/{eid}/submit', data={f"f_{h['field_ids'](eid)['Title']}": 'One'})
    # Without one, the old fixed form still works, from this event's registrations
    assert lt['client'].get(f'/hackathon/submit/{legacy}').status_code == 200
    assert unfiltered == []


# ═══ UPG-196: the student's hackathon page ═════════════════════════════════

def test_the_page_tracks_the_stages_as_time_passes(hack):
    h = hack
    eid = h['event']()
    t = h['team'](eid, 'Alpha', members=[f"{_unique('mem')}@test.edu"])

    def states():
        reg = h['db'].collection('registrations').document(t['reg_id']).get().to_dict()
        return {s['key']: s['state'] for s in hk.stages(h['ev'](eid), reg, h['sub'](t) or None)}

    assert states() == {'registration': 'done', 'problems': 'upcoming', 'submission': 'upcoming',
                        'shortlist': 'upcoming', 'finale': 'upcoming', 'results': 'upcoming'}
    h['problem'](eid, 'Later', release='later', at='2026-11-20T12:00')
    assert states()['problems'] == 'current'                       # a countdown to the release
    page = _page(t['client'], f'/hackathon/{eid}')
    assert f'data-countdown="{_ist("2026-11-20", "12:00").isoformat()}"' in page

    h['form'](eid, opens='2026-11-20T09:00', closes='2026-11-22T18:00', fields=[('Title', 'text', True)])
    h['clock']['now'] = _ist('2026-11-20', '12:30')
    assert states()['problems'] == 'done' and states()['submission'] == 'current'
    page = _page(t['client'], f'/hackathon/{eid}')
    assert f'data-countdown="{_ist("2026-11-22", "18:00").isoformat()}"' in page

    h['clock']['now'] = _ist('2026-11-22', '18:01')
    assert states()['submission'] == 'done' and states()['shortlist'] == 'current'
    h['db'].collection('events').document(eid).update({'active_round': 2})
    assert states()['shortlist'] == 'done'
    h['db'].collection('events').document(eid).update({'results_published': True})
    assert states()['results'] == 'done' and states()['finale'] == 'done'


def test_the_page_shows_the_whatsapp_link_team_and_updates(hack):
    h = hack
    eid = h['event']()
    mate = f"{_unique('mate')}@test.edu"
    t = h['team'](eid, 'Alpha', members=[mate])
    h['db'].collection('registrations').document(t['reg_id']).update(
        {'members': [{'role': 'Member', 'name': 'Mira Mate', 'email': mate}]})
    h['owner'].post(f'/spoc/hackathon/{eid}/update', data={'title': 'Mentors at 3 PM', 'message': 'Room 204.'})
    page = _page(t['client'], f'/hackathon/{eid}')
    assert 'href="https://chat.whatsapp.com/HackGroup123"' in page
    assert 'Mira Mate' in page and 'Alpha Lead' in page
    assert 'Mentors at 3 PM' in page and 'Room 204.' in page

    # Escaped, never markup
    h['owner'].post(f'/spoc/hackathon/{eid}/update', data={'title': '<script>alert(1)</script>'})
    assert '<script>alert(1)</script>' not in _page(t['client'], f'/hackathon/{eid}')

    # The lead's dashboard links to the page
    assert f'href="/hackathon/{eid}"' in _page(t['client'], '/participant/dashboard')


def test_the_page_polls_a_version_that_changes_only_when_something_does(hack):
    h = hack
    eid = h['event']()
    h['form'](eid, fields=[('Title', 'text', True)])
    t = h['team'](eid)
    first = t['client'].get(f'/hackathon/{eid}/state').get_json()['version']
    assert t['client'].get(f'/hackathon/{eid}/state').get_json()['version'] == first
    h['owner'].post(f'/spoc/hackathon/{eid}/update', data={'title': 'News'})
    second = t['client'].get(f'/hackathon/{eid}/state').get_json()['version']
    assert second != first
    h['owner'].post(f'/spoc/hackathon/{eid}/extend', data={'minutes': '60'})
    assert t['client'].get(f'/hackathon/{eid}/state').get_json()['version'] != second

    outsider = f"{_unique('o')}@test.edu"
    _user(h['db'], outsider, 'Student')
    assert _login(h['app'], outsider, 'Student').get(f'/hackathon/{eid}/state').status_code == 403

    page = _page(t['client'], f'/hackathon/{eid}')
    assert 'src="/static/js/pages/hackathon__portal.js"' in page and f'data-state-url="/hackathon/{eid}/state"' in page
    js = open('static/js/pages/hackathon__portal.js', encoding='utf-8').read()
    assert 'setInterval(poll, 60000)' in js and 'EventSource' not in js
