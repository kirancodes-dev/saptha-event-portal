"""
tests/test_certificate_changes.py — UPG-127 on the real database layer: name
corrections (asked for by the certificate's own person, approved as version 2
under the same number, after which version 1's file no longer verifies as
current; a rejected request changes nothing) and revocation (a reason
required, shown on verification with the date). Every issue, correction and
revocation is audit-logged.
"""
import json

import pytest

import certificate_pdf
import services_certificates as certs
from tests.test_certificate_delivery import mail  # noqa: F401  (the fixture)
from tests.test_certificate_types import _signature
from tests.test_integration_flow import _create_event, _login, _unique, _user
from utils_storage import get_private


@pytest.fixture
def issued(real_app, mail):  # noqa: F811
    import services_signatories
    flask_app, db = real_app
    spoc, other_spoc = f"{_unique('chspoc')}@test.edu", f"{_unique('chother')}@test.edu"
    student, stranger = f"{_unique('asha')}@test.edu", f"{_unique('stranger')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, other_spoc, 'ClubSPOC')
    _user(db, student, 'Student', name='Asha Rao')
    _user(db, stranger, 'Student')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(owner, db, _unique('Changed Event'), '2031-01-01', team=False)
    db.collection('events').document(event_id).update({'status': 'completed', 'staff': []})
    services_signatories.add(db, event_id, name='Dr. A. Kumar', title='Principal', image=_signature(), actor=spoc)
    db.collection('registrations').document(_unique('REG')).set({
        'event_id': event_id, 'lead_name': 'Asha Roa', 'lead_email': student, 'status': 'Confirmed',
        'attendance': 'Present'})
    certs.issue_event(db, event_id, spoc, only=['participation'])
    [cert] = [c for c in certs.for_event(event_id) if c['email'] == student]
    return {'app': flask_app, 'db': db, 'event_id': event_id, 'cert': cert, 'owner': owner, 'spoc': spoc,
            'other': _login(flask_app, other_spoc, 'ClubSPOC'), 'student': _login(flask_app, student, 'Student'),
            'stranger': _login(flask_app, stranger, 'Student'), 'student_email': student, 'mail': mail,
            'visitor': flask_app.test_client()}


def _flash(client):
    with client.session_transaction() as sess:
        return ' '.join(m for _, m in sess.get('_flashes', []))


def _audit(db, action, needle):
    return [a.to_dict() for a in db.collection('audit_log').stream()
            if a.to_dict().get('action') == action and needle in json.dumps(a.to_dict(), default=str)]


def _corrections(d):
    import services_certificate_changes as changes
    return changes.for_event(d['db'], d['event_id'], status=None)


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_a_correction_gives_version_2_with_the_same_number_and_version_1_stops_verifying(issued):
    d = issued
    number, v1 = d['cert']['number'], d['cert']
    v1_pdf = get_private(v1['pdf_key'])
    assert _audit(d['db'], 'CERT_ISSUED', number)                               # issuing is audit-logged

    d['stranger'].post(f'/certificates/c/{number}/correction', data={'new_name': 'Not Me'})
    assert 'Only the person a certificate was issued to' in _flash(d['stranger']) and _corrections(d) == []

    # Asked for, then rejected: nothing changes
    d['student'].post(f'/certificates/c/{number}/correction', data={'new_name': 'Asha Rao', 'reason': 'Typo'})
    assert "sent to the event's organiser" in _flash(d['student'])
    d['student'].post(f'/certificates/c/{number}/correction', data={'new_name': 'Asha R.'})
    assert 'already waiting' in _flash(d['student'])
    [request] = _corrections(d)
    page = d['owner'].get(f"/certificates/events/{d['event_id']}").get_data(as_text=True)
    assert 'Asha Roa' in page and 'Asha Rao' in page and 'Approve (issue version 2)' in page
    assert d['other'].post(f"/certificates/events/{d['event_id']}/corrections/{request['id']}/approve").status_code == 403
    d['owner'].post(f"/certificates/events/{d['event_id']}/corrections/{request['id']}/reject")
    after = certs.by_number(number)
    assert (after['version'], after['name'], after['pdf_sha256']) == (1, 'Asha Roa', v1['pdf_sha256'])
    assert _audit(d['db'], 'CERT_CORRECTION_REJECTED', number)

    # Asked again, approved: version 2, same number, new name, emailed
    d['student'].post(f'/certificates/c/{number}/correction', data={'new_name': 'Asha Rao'})
    [request] = [r for r in _corrections(d) if r['status'] == 'pending']
    before = len(d['mail'])
    d['owner'].post(f"/certificates/events/{d['event_id']}/corrections/{request['id']}/approve")
    assert f'{number} is now version 2' in _flash(d['owner'])
    v2 = certs.by_number(number)
    assert (v2['number'], v2['version'], v2['name'], v2['status']) == (number, 2, 'Asha Rao', 'valid')
    assert certs.by_number(number, 1)['status'] == 'superseded' and not certs.by_number(number, 1)['is_current']
    v2_pdf = get_private(v2['pdf_key'])
    assert 'Asha Rao' in certificate_pdf.text_of(v2_pdf) and v2['pdf_key'] != v1['pdf_key']
    assert [m['to'] for m in d['mail'][before:]] == [d['student_email']]
    assert _audit(d['db'], 'CERT_CORRECTED', number) and _audit(d['db'], 'CERT_CORRECTION_REQUESTED', number)

    # Version 1's file no longer verifies as current; version 2's does
    import io
    for data, expected in ((v1_pdf, 'version 1, which was replaced'), (v2_pdf, 'as issued (version 2)'),
                           (b'%PDF-1.4 forged', "doesn't match any version")):
        page = d['visitor'].post(f'/verify/{number}/file', data={'file': (io.BytesIO(data), 'c.pdf')},
                                 content_type='multipart/form-data').get_data(as_text=True)
        assert expected in page, expected
    assert 'Replaced certificate' in d['visitor'].get(f'/verify/{number}/v1').get_data(as_text=True)
    assert 'Asha Rao' in d['visitor'].get(f'/verify/{number}').get_data(as_text=True)
    mine = d['student'].get('/certificates/mine').get_data(as_text=True)
    assert 'version 2' in mine and number in mine


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_a_revocation_needs_a_reason_shows_on_verification_and_is_audited(issued):
    d = issued
    number = d['cert']['number']
    assert d['other'].post(f"/certificates/events/{d['event_id']}/revoke",
                           data={'number': number, 'reason': 'x'}).status_code == 403
    d['owner'].post(f"/certificates/events/{d['event_id']}/revoke", data={'number': number, 'reason': '   '})
    assert 'Give a reason' in _flash(d['owner']) and certs.by_number(number)['status'] == 'valid'

    d['owner'].post(f"/certificates/events/{d['event_id']}/revoke",
                    data={'number': number, 'reason': 'Attendance was marked by mistake'})
    cert = certs.by_number(number)
    assert cert['status'] == 'revoked' and cert['revoked_reason'] == 'Attendance was marked by mistake'
    page = d['visitor'].get(f'/verify/{number}').get_data(as_text=True)
    assert 'Revoked certificate' in page and f"revoked on {cert['revoked_at'].strftime('%d %B %Y')}" in page
    [entry] = _audit(d['db'], 'CERT_REVOKED', number)
    assert 'Attendance was marked by mistake' in entry['details']

    mine = d['student'].get('/certificates/mine').get_data(as_text=True)
    assert 'This certificate was revoked' in mine and f'/certificates/c/{number}/pdf' not in mine
    assert d['student'].get(f'/certificates/c/{number}/pdf').status_code == 410
    d['student'].post(f'/certificates/c/{number}/correction', data={'new_name': 'Asha Rao'})
    assert "revoked and can't be corrected" in _flash(d['student'])
    d['owner'].post(f"/certificates/events/{d['event_id']}/revoke", data={'number': number, 'reason': 'again'})
    assert 'already revoked' in _flash(d['owner'])
