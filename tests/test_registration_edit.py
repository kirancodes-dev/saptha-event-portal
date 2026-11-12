"""
tests/test_registration_edit.py — UPG-225 on the real database layer: the
team lead (their own registration, until check-in or the event's end) and the
event's organisers (any time) correct a registration's details, and every copy
of a detail follows: the registration, the members' rows, the form answers
(standard and hand-added questions), the form responses copy, the export, the
ticket and team pages. Nothing else on the registration changes.
"""
import datetime
import json

import pytest

import services_export
import services_team_confirm as confirm
from tests.test_integration_flow import _create_event, _login, _unique, _user

# A form like SAPTHAHACKS'26's, built in the builder: the lead's USN and phone
# are questions added by hand, with random ids
FORM = [
    {'id': 'full_name', 'type': 'text', 'label': 'Full Name', 'required': True},
    {'id': 'email', 'type': 'email', 'label': 'Email Address', 'required': True},
    {'id': 'f_usn001', 'type': 'text', 'label': 'USN', 'required': True},
    {'id': 'f_mob001', 'type': 'tel', 'label': 'Phone Number', 'required': True},
    {'id': 'f_head01', 'type': 'heading', 'label': 'About your project'},
    {'id': 'f_trk001', 'type': 'select', 'label': 'Track', 'options': ['AI', 'Web'], 'required': True},
    {'id': 'f_skil01', 'type': 'checkbox_group', 'label': 'Skills', 'options': ['Python', 'ML', 'Web']},
    {'id': 'f_shrt01', 'type': 'text', 'label': 'Project idea'},
]


@pytest.fixture
def team(real_app):
    flask_app, db = real_app
    owner, lead, coord = (f"{_unique(k)}@test.edu" for k in ('edspoc', 'edlead', 'edcoord'))
    hima, alif = f"{_unique('hima')}@test.edu", f"{_unique('alif')}@test.edu"
    _user(db, owner, 'ClubSPOC')
    _user(db, lead, 'Student', name='Lena Lead')
    _user(db, coord, 'EventCoordinator')
    spoc = _login(flask_app, owner, 'ClubSPOC')
    event_id = _create_event(spoc, db, _unique('Edit Hack'), datetime.date.today().isoformat(), team=True)
    db.collection('event_forms').document(event_id).set({'fields': FORM})
    db.collection('events').document(event_id).update({
        'form_chosen': True, 'form_member_fields': {'usn': 'optional', 'phone': 'optional'},
        'staff': [{'name': 'C', 'email': coord, 'role': 'EventCoordinator'}]})
    lead_client = _login(flask_app, lead, 'Student')
    resp = lead_client.post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Lena Lead', 'email': lead, 'f_usn001': '25suubeaml013',
        'f_mob001': '9000000001', 'f_trk001': 'AI', 'f_skil01': ['Python'], 'f_shrt01': 'A planner',
        'team_name': 'Apex', 'member_1_name': 'Hima TS', 'member_1_email': hima, 'member_1_usn': '25SUUBEAML231',
        'member_1_phone': '9000000003', 'member_2_name': 'Alif P', 'member_2_email': alif})
    assert resp.status_code == 302, resp.data[:300]
    regs = list(db.collection('registrations').where('event_id', '==', event_id).stream())
    assert len(regs) == 1
    return {'app': flask_app, 'db': db, 'event_id': event_id, 'reg_id': regs[0].id, 'lead': lead,
            'lead_client': lead_client, 'spoc': spoc, 'owner': owner, 'coord': coord, 'hima': hima, 'alif': alif}


def _reg(t):
    return t['db'].collection('registrations').document(t['reg_id']).get().to_dict()


def _member(reg, email):
    return next(m for m in reg['members'] if (m.get('email') or '').lower() == email)


def _form(t, **changes):
    """Everything the edit page sends as it stands, with `changes`."""
    data = {'lead_name': 'Lena Lead', 'lead_usn': '25SUUBEAML013', 'lead_phone': '9000000001', 'team_name': 'Apex',
            'm1_key': t['hima'], 'm1_name': 'Hima TS', 'm1_usn': '25SUUBEAML231', 'm1_phone': '9000000003',
            'm2_key': t['alif'], 'm2_name': 'Alif P', 'm2_usn': '', 'm2_phone': '',
            'q_f_trk001': 'AI', 'q_f_skil01': ['Python'], 'q_f_shrt01': 'A planner'}
    data.update(changes)
    return data


def _lead_url(t):
    return f"/participant/registration/{t['reg_id']}/edit"


def _spoc_url(t):
    return f"/coordinator/registrations/{t['event_id']}/edit/{t['reg_id']}"


def _audit(t):
    return [a.to_dict() for a in t['db'].collection('audit_log').stream()]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_lead_corrects_every_detail_and_each_copy_follows(team):
    t, db = team, team['db']
    page = t['lead_client'].get(_lead_url(t))
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    for shown in ('25SUUBEAML013', '9000000001', 'Hima TS', 'A planner', t['lead'], 'Track'):
        assert shown in html, shown
    assert 'name="q_f_usn001"' not in html and 'name="q_f_mob001"' not in html   # shown once, as the lead's
    before = _reg(t)

    resp = t['lead_client'].post(_lead_url(t), data=_form(
        t, lead_name='Lena Leader', lead_usn='25suubeaml014', lead_phone='9000000009', team_name='Apex Devs',
        m1_name='Hima T S', m1_usn='25suubeaml232', m1_phone='9000000004',
        q_f_trk001='Web', q_f_skil01=['Python', 'ML'], q_f_shrt01='A study planner'))
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f"/teams/{t['reg_id']}")

    reg = _reg(t)
    assert (reg['lead_name'], reg['lead_usn'], reg['lead_phone'], reg['team_name']) == \
        ('Lena Leader', '25SUUBEAML014', '9000000009', 'Apex Devs')
    lead_row, hima_row = _member(reg, t['lead']), _member(reg, t['hima'])
    assert (lead_row['name'], lead_row['usn'], lead_row['phone']) == ('Lena Leader', '25SUUBEAML014', '9000000009')
    assert (hima_row['name'], hima_row['usn'], hima_row['phone']) == ('Hima T S', '25SUUBEAML232', '9000000004')
    answers = reg['form_answers']
    assert (answers['full_name'], answers['f_usn001'], answers['f_mob001']) == \
        ('Lena Leader', '25SUUBEAML014', '9000000009')
    assert (answers['f_trk001'], answers['f_skil01'], answers['f_shrt01']) == ('Web', ['Python', 'ML'], 'A study planner')
    assert (answers['team_name'], answers['member_1_name'], answers['member_1_usn']) == \
        ('Apex Devs', 'Hima T S', '25SUUBEAML232')
    # The form responses page's copy
    sub = next(iter(db.collection('form_submissions').where('reg_id', '==', t['reg_id']).stream())).to_dict()
    assert sub['name'] == 'Lena Leader' and sub['answers']['f_shrt01'] == 'A study planner'
    # Nothing else changed
    for key in ('attendance', 'payment_status', 'status', 'team_code', 'registered_at', 'privacy_consent',
                'lead_email', 'event_id', 'is_eliminated'):
        assert reg.get(key) == before.get(key), key
    for key in ('confirm_email', 'confirm_nonce', 'confirm_sent_at', 'confirmed_at'):
        assert hima_row.get(key) == _member(before, t['hima']).get(key), key
    assert _member(reg, t['alif']) == _member(before, t['alif'])
    assert len(reg['members']) == len(before['members'])

    # The export, the ticket and the team page show the new details
    with t['app'].app_context():
        columns, rows = services_export.registration_table(db, t['event_id'])
    row = dict(zip(columns, rows[0]))
    assert (row['Lead Name'], row['Lead USN'], row['Lead Phone'], row['Team']) == \
        ('Lena Leader', '25SUUBEAML014', '9000000009', 'Apex Devs')
    assert (row['Member 2 Name'], row['Member 2 USN'], row['Track'], row['Skills']) == \
        ('Hima T S', '25SUUBEAML232', 'Web', 'Python, ML')
    ticket = t['lead_client'].get(f"/ticket/{t['reg_id']}")
    assert ticket.status_code == 200 and 'Lena Leader' in ticket.get_data(as_text=True)
    team_page = t['lead_client'].get(f"/teams/{t['reg_id']}").get_data(as_text=True)
    assert 'Hima T S' in team_page and 'data-edit-details' in team_page
    assert any('REGISTRATION_EDITED' in str(a.get('action')) and t['reg_id'] in str(a.get('details'))
               and 'Team name' in str(a.get('details')) for a in _audit(t))


def test_the_member_rows_own_columns_follow(team):
    """The SQL store's member columns (name, USN, phone), not only the row's copy."""
    t = team
    assert t['lead_client'].post(_lead_url(t), data=_form(t, m1_name='Hima T S', m1_usn='25SUUBEAML232',
                                                         m1_phone='9000000004')).status_code == 302
    from sqlalchemy.orm import Session

    from db_adapter import to_uuid
    from db_pg import get_engine
    from models_pg import TeamMember
    with Session(get_engine()) as s:
        row = s.query(TeamMember).filter(TeamMember.registration_id == to_uuid(t['reg_id']),
                                         TeamMember.email == t['hima']).one()
        assert (row.name, row.usn, row.phone) == ('Hima T S', '25SUUBEAML232', '9000000004')


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_spoc_and_a_coordinator_edit_also_after_check_in_and_others_cannot(team):
    t, db = team, team['db']
    listing = t['spoc'].get(f"/coordinator/registrations/{t['event_id']}").get_data(as_text=True)
    assert _spoc_url(t) in listing
    # Checked in at the gate: the lead can't any more, the organiser still can
    assert t['spoc'].post(f"/spoc/api/checkin/{t['event_id']}/{t['reg_id']}", json={'round': 1}).status_code == 200
    assert _reg(t)['attendance'] == 'Present'
    assert t['spoc'].get(_spoc_url(t)).status_code == 200
    resp = t['spoc'].post(_spoc_url(t), data=_form(t, lead_name='Lena Leader'))
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f"/coordinator/registrations/{t['event_id']}")
    assert _reg(t)['lead_name'] == 'Lena Leader' and _reg(t)['attendance'] == 'Present'

    coord = _login(t['app'], t['coord'], 'EventCoordinator')
    assert coord.post(_spoc_url(t), data=_form(t, lead_name='Lena Leader', team_name='Apex Devs')).status_code == 302
    assert _reg(t)['team_name'] == 'Apex Devs'

    # The lead is told, in the portal
    notices = [n.to_dict() for n in db.collection('notifications_v2').where('user_email', '==', t['lead']).stream()]
    assert any('Your registration was updated' in n.get('title', '') and 'Team name' in n.get('message', '')
               for n in notices)
    assert any('REGISTRATION_EDITED' in str(a.get('action')) and t['owner'] in str(a.get('details'))
               and 'Name' in str(a.get('details')) for a in _audit(t))

    # A SPOC of another event, and the lead after check-in, can't
    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    stranger = _login(t['app'], other, 'ClubSPOC')
    assert stranger.get(_spoc_url(t)).status_code == 403
    assert stranger.post(_spoc_url(t), data=_form(t, lead_name='Hacked')).status_code == 403
    assert t['lead_client'].get(_lead_url(t)).status_code == 302
    t['lead_client'].post(_lead_url(t), data=_form(t, lead_name='Late Change'))
    assert _reg(t)['lead_name'] == 'Lena Leader'


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_the_lead_edits_only_their_own_until_check_in_or_the_events_end(team):
    t, db = team, team['db']
    dashboard = t['lead_client'].get('/participant/dashboard').get_data(as_text=True)
    assert _lead_url(t) in dashboard

    # A member or anyone else can't
    _user(db, t['hima'], 'Student')
    member = _login(t['app'], t['hima'], 'Student')
    assert member.get(_lead_url(t)).status_code == 302
    member.post(_lead_url(t), data=_form(t, lead_name='Not Me'))
    assert _reg(t)['lead_name'] == 'Lena Lead'
    assert 'data-edit-details' not in member.get(f"/teams/{t['reg_id']}").get_data(as_text=True)

    # Once the event is over, the lead can't
    db.collection('events').document(t['event_id']).update({'status': 'completed'})
    assert t['lead_client'].get(_lead_url(t)).status_code == 302
    t['lead_client'].post(_lead_url(t), data=_form(t, lead_name='Too Late'))
    assert _reg(t)['lead_name'] == 'Lena Lead'
    db.collection('events').document(t['event_id']).update({'status': 'active'})

    # Nobody edits a cancelled registration
    db.collection('registrations').document(t['reg_id']).update({'status': 'Cancelled'})
    for client, url in ((t['lead_client'], _lead_url(t)), (t['spoc'], _spoc_url(t))):
        assert client.get(url).status_code == 302
        client.post(url, data=_form(t, lead_name='Cancelled Edit'))
    assert _reg(t)['lead_name'] == 'Lena Lead'
    assert _spoc_url(t) not in t['spoc'].get(f"/coordinator/registrations/{t['event_id']}").get_data(as_text=True)


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_a_wrong_value_is_refused_beside_its_field_and_nothing_is_saved(team):
    t = team
    before = _reg(t)
    resp = t['lead_client'].post(_lead_url(t), data=_form(
        t, lead_name='', lead_phone='12', q_f_trk001='Mobile', m1_name='', team_name='Apex Devs'))
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "&#39;Name&#39; is required." in html
    assert "must be a valid phone number" in html
    assert "Choose from the options given for &#39;Track&#39;" in html
    assert "&#39;Member 2 name&#39; is required." in html
    assert 'id="lead_phone-error"' in html and 'id="q_f_trk001-error"' in html
    assert 'value="Apex Devs"' in html            # what was typed stays on the page
    after = _reg(t)
    assert (after['team_name'], after['lead_name'], after['form_answers']) == \
        (before['team_name'], before['lead_name'], before['form_answers'])


def test_an_old_value_todays_rules_refuse_doesnt_block_another_correction(team):
    t, db = team, team['db']
    reg = _reg(t)
    answers = dict(reg['form_answers'], f_trk001='', f_mob001='123')   # saved before the rules, say
    db.collection('registrations').document(t['reg_id']).update({'form_answers': answers, 'lead_phone': '123'})
    resp = t['lead_client'].post(_lead_url(t), data=_form(t, lead_phone='123', q_f_trk001='', team_name='Apex Devs'))
    assert resp.status_code == 302
    after = _reg(t)
    assert after['team_name'] == 'Apex Devs' and after['lead_phone'] == '123' and after['form_answers']['f_trk001'] == ''


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_the_leads_email_stays_and_the_spoc_corrects_a_waiting_members_email(team):
    t, db = team, team['db']
    html = t['lead_client'].get(_lead_url(t)).get_data(as_text=True)
    assert 'name="email"' not in html and 'name="lead_email"' not in html
    t['lead_client'].post(_lead_url(t), data=_form(t, email='other@test.edu', lead_email='other@test.edu',
                                                   team_name='Apex Devs'))
    assert _reg(t)['lead_email'] == t['lead'] and _reg(t)['team_name'] == 'Apex Devs'

    spoc_page = t['spoc'].get(_spoc_url(t)).get_data(as_text=True)
    assert 'data-member-email' in spoc_page
    url = f"/coordinator/registrations/{t['event_id']}/member_email"
    alif2 = f"{_unique('alif2')}@test.edu"
    resp = t['spoc'].post(url, data={'reg_id': t['reg_id'], 'email': t['alif'], 'new_email': alif2})
    assert resp.status_code == 302 and resp.headers['Location'].endswith(_spoc_url(t))
    moved = _member(_reg(t), alif2)
    assert moved['email_corrected_from'] == t['alif'] and moved['confirm_email'] in ('sent', 'failed', 'limit')
    assert any(a.get('action') == 'TEAM_MEMBER_EMAIL_CORRECTED' for a in _audit(t))

    # A confirmed member's email isn't changed
    confirm.confirm(db, t['reg_id'], t['hima'], 'link')
    t['spoc'].post(url, data={'reg_id': t['reg_id'], 'email': t['hima'], 'new_email': 'x@test.edu'})
    assert _member(_reg(t), t['hima'])['email'] == t['hima']

    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    assert _login(t['app'], other, 'ClubSPOC').post(url, data={
        'reg_id': t['reg_id'], 'email': alif2, 'new_email': 'y@test.edu'}).status_code == 403


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_a_ticket_sent_before_the_change_still_checks_in_with_the_new_name(team):
    t = team
    from routes_ticket import ticket_token_for
    with t['app'].app_context():
        old_token = ticket_token_for(t['reg_id'], _reg(t))
    assert t['lead_client'].post(_lead_url(t), data=_form(t, lead_name='Lena Leader')).status_code == 302
    scan = t['spoc'].post('/ticket/api/checkin', json={'token': old_token, 'event_id': t['event_id']})
    assert scan.status_code == 200, scan.data
    assert scan.get_json()['status'] == 'success' and scan.get_json()['name'] == 'Lena Leader'
    assert _reg(t)['attendance'] == 'Present'


# ── Criterion 7 ─────────────────────────────────────────────────────────────

def test_a_member_who_joins_while_the_page_is_open_is_kept(team):
    t, db = team, team['db']
    assert t['lead_client'].get(_lead_url(t)).status_code == 200      # the page is open…
    joiner = f"{_unique('join')}@test.edu"
    _user(db, joiner, 'Student', name='Jo Iner')
    code = _reg(t)['team_code']
    assert _login(t['app'], joiner, 'Student').post('/teams/join', data={'join_code': code}).status_code == 302
    # …and the lead removes Alif from the team page meanwhile
    assert t['lead_client'].post(f"/teams/{t['reg_id']}/remove", data={'email': t['alif']}).status_code == 302

    resp = t['lead_client'].post(_lead_url(t), data=_form(t, m1_name='Hima T S', m2_name='Alif Pe'),
                                 follow_redirects=True)
    assert resp.status_code == 200
    assert 'no longer on the team' in resp.get_data(as_text=True)
    reg = _reg(t)
    assert _member(reg, joiner)['name'] == 'Jo Iner'
    assert _member(reg, t['hima'])['name'] == 'Hima T S'
    assert all((m.get('email') or '') != t['alif'] for m in reg['members'])
    assert json.dumps(reg['members']).count(joiner) == 1
