"""
tests/test_scanner_team_members.py — UPG-318 on the real database layer.

The coordinator's scanner lists everyone on a team, the lead first and marked
as lead, whether or not they gave a USN (a team of 4 shows 4), and "Save
member attendance" saves each person by their place on the team, so a
ticked person with no USN is Present, not Absent.
"""
import os

from tests import test_checkin_unified as cu
from tests.test_checkin_unified import ROOT, _registration, _scan

gate = cu.gate

LEAD = {'role': 'Lead', 'name': 'Lena Lead', 'usn': ''}          # USN asked by a custom question (UPG-223)


def _team(d, members, **fields):
    for m in members:
        m.setdefault('email', f"{m['name'].split()[0].lower()}-{os.urandom(3).hex()}@test.edu")
    lead_email = next((m['email'] for m in members if m.get('role') == 'Lead'), 'lead-x@test.edu')
    return _registration(d, team_name='Four Of Us', lead_name='Lena Lead', lead_email=lead_email,
                         members=members, **fields)


def _people(d, token):
    body = _scan(d['staff'], token).get_json()
    assert body['success'], body
    return body['members']


def _save(d, reg_id, present):
    return d['staff'].post('/coordinator/mark_attendance_granular', json={'reg_id': reg_id, 'present': present})


def _reg(d, reg_id):
    return d['db'].collection('registrations').document(reg_id).get().to_dict()


# ── Criterion 1: the scanner lists the whole team ───────────────────────────

def test_a_team_of_4_shows_4_with_the_lead_first_even_without_a_usn(gate):
    d = gate
    reg_id, token = _team(d, [dict(LEAD), {'name': 'Mira One', 'usn': '1SN22CS101'},
                              {'name': 'Nikhil Two', 'usn': ''}, {'name': 'Omar Three', 'usn': '1SN22CS103'}])
    people = _people(d, token)
    assert [p['name'] for p in people] == ['Lena Lead', 'Mira One', 'Nikhil Two', 'Omar Three']
    assert [p['lead'] for p in people] == [True, False, False, False]
    assert [p['usn'] for p in people] == ['', '1SN22CS101', '', '1SN22CS103']
    assert [p['key'] for p in people] == ['0', '1', '2', '3']


def test_a_team_of_3_shows_3_and_the_lead_is_found_by_email_too(gate):
    d = gate
    reg_id, token = _registration(d, team_name='Three', lead_name='Pia Lead', lead_email='pia-lead@test.edu',
                                  members=[{'name': 'Raj Mate', 'email': 'raj@test.edu', 'usn': '1SN22CS201'},
                                           {'name': 'Pia Lead', 'email': 'pia-lead@test.edu', 'usn': ''},
                                           {'name': 'Sam Mate', 'email': 'sam@test.edu', 'usn': '1SN22CS202'}])
    people = _people(d, token)
    assert [p['name'] for p in people] == ['Pia Lead', 'Raj Mate', 'Sam Mate']   # the lead moved first
    assert [p['key'] for p in people] == ['1', '0', '2']                          # keys stay their places


def test_an_older_registration_without_the_lead_in_members_still_lists_the_lead(gate):
    d = gate
    reg_id, token = _registration(d, team_name='Old Style', lead_name='Quinn Lead', lead_usn='1SN22CS300',
                                  members=[{'name': 'Tia', 'usn': '1SN22CS301'}, {'name': 'Uma', 'usn': '1SN22CS302'},
                                           {'name': 'Vik', 'usn': '1SN22CS303'}])
    people = _people(d, token)
    assert [p['name'] for p in people] == ['Quinn Lead', 'Tia', 'Uma', 'Vik']
    assert people[0] == {'key': 'lead', 'name': 'Quinn Lead', 'usn': '1SN22CS300', 'attendance': '', 'lead': True}


def test_an_individual_lists_nobody(gate):
    d = gate
    _, token = _registration(d)
    assert _people(d, token) == []


# ── Criterion 2: the save goes by each person, USN or not ───────────────────

def test_saving_marks_each_ticked_person_present_with_or_without_a_usn(gate):
    d = gate
    reg_id, token = _team(d, [dict(LEAD), {'name': 'Mira One', 'usn': '1SN22CS101'},
                              {'name': 'Nikhil Two', 'usn': ''}, {'name': 'Omar Three', 'usn': ''}])
    _people(d, token)
    body = _save(d, reg_id, ['0', '2', '3']).get_json()
    assert body['status'] == 'success' and body['message'] == '3 members marked present.'
    members = _reg(d, reg_id)['members']
    assert [m['attendance'] for m in members] == ['Present', 'Absent', 'Present', 'Present']
    assert _reg(d, reg_id)['attendance'] == 'Present'
    # The next scan shows who was ticked
    assert [p['attendance'] for p in _people(d, token)] == ['Present', 'Absent', 'Present', 'Present']


def test_the_lead_key_counts_and_nobody_ticked_is_absent(gate):
    d = gate
    reg_id, _ = _registration(d, team_name='Old Style', lead_name='Quinn Lead',
                              members=[{'name': 'Tia', 'usn': ''}, {'name': 'Uma', 'usn': ''}])
    body = _save(d, reg_id, ['lead']).get_json()
    assert body['message'] == '1 member marked present.'
    reg = _reg(d, reg_id)
    assert reg['attendance'] == 'Present' and [m['attendance'] for m in reg['members']] == ['Absent', 'Absent']
    assert _save(d, reg_id, []).get_json()['status'] == 'success'
    assert _reg(d, reg_id)['attendance'] == 'Absent'
    # Places that aren't on the team count for nothing
    assert _save(d, reg_id, ['7', 'x']).get_json()['message'] == '0 members marked present.'


def test_the_older_usn_list_still_saves(gate):
    d = gate
    reg_id, _ = _team(d, [dict(LEAD, usn='1SN22CS100'), {'name': 'Mira One', 'usn': '1SN22CS101'}])
    resp = d['staff'].post('/coordinator/mark_attendance_granular',
                           json={'reg_id': reg_id, 'present_usns': ['1SN22CS101']})
    assert resp.get_json()['status'] == 'success'
    assert [m['attendance'] for m in _reg(d, reg_id)['members']] == ['Absent', 'Present']


# ── Criterion 3: the scanner page shows and sends every person ──────────────

def test_the_scanner_page_lists_everyone_and_sends_their_places():
    with open(os.path.join(ROOT, 'templates', 'coordinator', 'scan.html'), encoding='utf-8') as f:
        html = f.read()
    assert '.filter(m => m.usn)' not in html                       # nobody is left out for want of a USN
    assert "m.usn || 'No USN'" in html and "tag.textContent = 'Lead'" in html
    assert "box.name = 'present_member'" in html and 'box.value = m.key' in html
    assert "JSON.stringify({ reg_id: reg_id, present: present })" in html
