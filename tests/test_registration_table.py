"""
tests/test_registration_table.py — UPG-229 and UPG-226 on the real database
layer: the SPOC's registrations list is a table with one thing per column
(team and lead with the lead's USN, members, contact, status, login) and an
Actions column with Edit, Cancel and Delete. The hosting SPOC deletes a team
for good, unless something is kept about it elsewhere (a check-in, a payment,
a certificate, hackathon work); searching finds a lead's or member's USN.
"""
import uuid

from sqlalchemy.orm import Session

from db_pg import get_engine
from models_pg import Certificate, TeamMember
from db_adapter import to_uuid
from tests import test_spoc_cancel_team as _cancel
from tests.test_integration_flow import _login, _unique, _user

host = _cancel.host   # UPG-211's fixture: an event's hosting SPOC, register(), reg(), count()


def _page(client, event_id, q=''):
    resp = client.get(f'/coordinator/registrations/{event_id}' + (f'?q={q}' if q else ''))
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _delete(client, event_id, reg_id, confirm='yes'):
    data = {'reg_id': reg_id}
    if confirm:
        data['confirm'] = confirm
    return client.post(f'/coordinator/registrations/{event_id}/delete_team', data=data)


def _exists(h, reg_id):
    return h['db'].collection('registrations').document(reg_id).get().exists


def _audit(h):
    return [a.to_dict() for a in h['db'].collection('audit_log').stream()]


# ── UPG-229 criterion 1 / UPG-226 ───────────────────────────────────────────

def test_each_row_has_its_own_columns_and_the_three_actions(host):
    h = host
    event_id = h['event'](member_confirm=True)
    reg_id, lead, _mate = h['register'](event_id)
    html = _page(h['owner'], event_id)
    assert 'data-registrations-table' in html
    for header in ('>Team<', '>Members<', '>Contact<', '>Status<', '>Login<', '>Actions<'):
        assert header in html, header
    row = html[html.index(f'data-reg="{reg_id}"'):]
    row = row[:row.index('</tr>')]
    assert 'Byte Force' in row and 'Lena Lead' in row and lead in row and '9876543210' in row
    assert 'data-lead-usn>1SN22CS300<' in row                       # UPG-226: lead_usn shows
    assert 'Mo Mate' in row and 'data-member-status=' in row
    assert 'data-entry-state="not_selected"' in row and 'data-reg-status' in row
    assert 'data-edit-details' in row and f'data-bs-target="#cancel-{reg_id}"' in row
    assert f'data-bs-target="#delete-{reg_id}"' in row
    assert f'id="delete-{reg_id}"' in html and 'data-delete-team' in html and 'name="confirm"' in html
    assert f'id="cancel-{reg_id}"' in html and 'data-cancel-team' in html


def test_searching_finds_a_leads_or_members_usn_and_an_older_usn(host):
    h, db = host, host['db']
    event_id = h['event']()
    reg_id, _, _ = h['register'](event_id)
    other_id, _, _ = h['register'](event_id, team_name='Other Team')
    db.collection('registrations').document(other_id).update({'lead_usn': '', 'usn': '1SN20OLD999'})
    for q, found, not_found in (('1SN22CS300', reg_id, None), ('1sn22cs301', reg_id, None),
                                ('1SN20OLD999', other_id, reg_id), ('NOPE000', None, reg_id)):
        html = _page(h['owner'], event_id, q)
        if found:
            assert f'data-reg="{found}"' in html, q
        if not_found:
            assert f'data-reg="{not_found}"' not in html, q


# ── UPG-229 criterion 2 ─────────────────────────────────────────────────────

def test_the_hosting_spoc_deletes_a_team_for_good(host):
    h, db = host, host['db']
    event_id = h['event']()
    reg_id, lead, mate = h['register'](event_id)
    keep_id, _, _ = h['register'](event_id, team_name='Keepers')
    before = h['count'](event_id)
    assert list(db.collection('form_submissions').where('reg_id', '==', reg_id).stream())

    resp = _delete(h['owner'], event_id, reg_id)
    assert resp.status_code == 302
    assert not _exists(h, reg_id) and _exists(h, keep_id)
    assert not list(db.collection('form_submissions').where('reg_id', '==', reg_id).stream())
    assert not list(db.collection('tickets').where('registration_id', '==', reg_id).stream())
    with Session(get_engine()) as s:
        assert s.query(TeamMember).filter(TeamMember.registration_id == to_uuid(reg_id)).count() == 0
    assert h['count'](event_id) == before - 1
    for person in (lead, mate):
        assert any('Registration removed' in n.get('title', '') for n in _cancel._notices(db, person)), person
    assert any(a.get('action') == 'REGISTRATION_DELETED' and reg_id in str(a.get('details'))
               and h['spoc'] in str(a.get('details')) and lead in str(a.get('details')) for a in _audit(h))
    assert f'data-reg="{reg_id}"' not in _page(h['owner'], event_id)
    # The people's accounts stay
    assert db.collection('users').document(lead).get().exists


def test_deleting_an_already_cancelled_team_doesnt_lower_the_count_again(host):
    h, db = host, host['db']
    event_id = h['event']()
    reg_id, lead, _ = h['register'](event_id)
    assert h['cancel'](h['owner'], event_id, reg_id).status_code == 302
    after_cancel = h['count'](event_id)
    notices = len(_cancel._notices(db, lead))
    assert _delete(h['owner'], event_id, reg_id).status_code == 302
    assert not _exists(h, reg_id)
    assert h['count'](event_id) == after_cancel
    assert len(_cancel._notices(db, lead)) == notices          # nobody told twice


# ── UPG-229 criterion 3 ─────────────────────────────────────────────────────

def test_delete_is_refused_for_a_team_with_a_record_elsewhere(host):
    h, db = host, host['db']
    event_id = h['event']()

    checked, _, _ = h['register'](event_id, team_name='Checked')
    db.collection('registrations').document(checked).update({'attendance': 'Present'})
    paid, _, _ = h['register'](event_id, team_name='Paid')
    db.collection('registrations').document(paid).update({'payment_status': 'Paid'})
    certified, lead, _ = h['register'](event_id, team_name='Certified')
    with Session(get_engine()) as s, s.begin():
        s.add(Certificate(number=f'T-{uuid.uuid4().hex[:8]}', event_id=event_id, person_key=lead,
                          recipient_email=lead, recipient_name='Lena Lead', reg_id=certified,
                          cert_type='participation', data_json='{}'))
    submitted, _, _ = h['register'](event_id, team_name='Submitted')
    db.collection('project_submissions').document(str(uuid.uuid4())).set({
        'event_id': event_id, 'registration_id': submitted, 'team_name': 'Submitted', 'project_title': 'Planner'})

    html = _page(h['owner'], event_id)
    for reg_id, reason in ((checked, 'checked in'), (paid, 'payment'), (certified, 'certificate'),
                           (submitted, 'hackathon work')):
        row = html[html.index(f'data-reg="{reg_id}"'):]
        row = row[:row.index('</tr>')]
        assert 'data-delete-blocked' in row and reason in row, reason
        assert f'id="delete-{reg_id}"' not in html
        before = h['count'](event_id)
        resp = _delete(h['owner'], event_id, reg_id)
        assert resp.status_code == 302 and _exists(h, reg_id), reason
        assert h['count'](event_id) == before


def test_delete_needs_the_tick_the_hosting_spoc_and_the_events_own_team(host):
    h, db = host, host['db']
    event_id = h['event']()
    reg_id, _, _ = h['register'](event_id)
    before = h['count'](event_id)

    assert _delete(h['owner'], event_id, reg_id, confirm='').status_code == 302
    assert _exists(h, reg_id) and h['count'](event_id) == before

    coord_email = f"{_unique('coord')}@test.edu"
    _user(db, coord_email, 'EventCoordinator')
    db.collection('events').document(event_id).update(
        {'staff': [{'name': 'C', 'email': coord_email, 'role': 'EventCoordinator'}]})
    coord = _login(h['app'], coord_email, 'EventCoordinator')
    page = _page(coord, event_id)
    assert 'data-delete-team' not in page and f'#delete-{reg_id}' not in page and 'data-delete-blocked' not in page
    assert _delete(coord, event_id, reg_id).status_code == 403

    other = f"{_unique('otherspoc')}@test.edu"
    _user(db, other, 'ClubSPOC')
    assert _delete(_login(h['app'], other, 'ClubSPOC'), event_id, reg_id).status_code == 403

    second = h['event']()
    assert _delete(h['owner'], second, reg_id).status_code == 302      # not that event's team
    assert _exists(h, reg_id) and h['count'](event_id) == before


# ── UPG-229 criterion 4 ─────────────────────────────────────────────────────

def test_cancel_still_works_from_its_dialog(host):
    h = host
    event_id = h['event']()
    reg_id, _, _ = h['register'](event_id)
    html = _page(h['owner'], event_id)
    dialog = html[html.index(f'id="cancel-{reg_id}"'):]
    dialog = dialog[:dialog.index('</form>')]
    assert '/cancel_team' in dialog and f'value="{reg_id}"' in dialog and 'name="reason"' in dialog
    assert h['cancel'](h['owner'], event_id, reg_id).status_code == 302
    assert h['reg'](reg_id)['status'] == 'Cancelled'
    row = _page(h['owner'], event_id)
    row = row[row.index(f'data-reg="{reg_id}"'):]
    row = row[:row.index('</tr>')]
    assert 'Cancelled' in row and 'Duplicate team' in row and 'data-edit-details' not in row
    assert f'#cancel-{reg_id}' not in row and f'#delete-{reg_id}' in row     # can still be tidied away
