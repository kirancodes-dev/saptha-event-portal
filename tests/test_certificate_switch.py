"""
tests/test_certificate_switch.py — UPG-138 on the real database layer: ending
an event issues through services_certificates only (nothing written to the
old verified_certificates store, nothing issued twice); the participant's
certificate page and the ledger link the person's certificate; one issued
before the switch still opens. UPG-06's own checks moved with it
(tests/test_certificates.py).
"""
import uuid

import services_certificates as certs
from tests.test_certificates import ended, mail  # noqa: F401  (fixtures)
from tests.test_certificates import _reg, _student


def _old_store_rows(d):
    return [doc.id for doc in d['db'].collection('verified_certificates').stream()
            if (doc.to_dict() or {}).get('event_id') == d['event_id']]


def test_ending_the_event_issues_once_into_the_certificates_table_only(ended):  # noqa: F811
    d = ended
    d['owner'].post(f"/spoc/end_event/{d['event_id']}", data={'template_id': '1'})
    issued = [c for c in certs.for_event(d['event_id']) if c['cert_type'] == 'participation']
    assert sorted(c['name'] for c in issued) == ['Ana Attendee', 'Ben Attendee']        # Present only
    assert _old_store_rows(d) == []
    d['owner'].post(f"/spoc/end_event/{d['event_id']}", data={'template_id': '1'})
    assert len(certs.for_event(d['event_id'])) == len(issued) + 1                       # + the organiser, once


def test_the_page_and_ledger_link_the_certificate_and_an_older_one_still_opens(ended):  # noqa: F811
    d = ended
    d['owner'].post(f"/spoc/end_event/{d['event_id']}", data={'template_id': '1'})
    number = _reg(d, 'ben')['certificate_id']
    student = _student(d, 'ben')
    page = student.get(f"/participant/certificate/{d['people']['ben'][0]}").get_data(as_text=True)
    assert f'/certificates/c/{number}/pdf' in page and f'/verify/{number}"' in page
    assert f'/certificates/c/{number}/pdf' in student.get('/participant/ledger').get_data(as_text=True)
    assert student.get(f'/certificates/c/{number}/pdf').data[:4] == b'%PDF'

    # A certificate issued before the switch: its ID on the registration, its record in the old store
    old_id = uuid.uuid4().hex + uuid.uuid4().hex
    reg_id, email = d['people']['ana']
    d['db'].collection('verified_certificates').document(old_id).set({
        'hash': old_id, 'reg_id': reg_id, 'event_id': 'an-older-event', 'student_name': 'Ana Attendee',
        'event_title': 'An Older Event', 'cert_type': 'participation', 'issued_at': '2025-02-02T10:00:00',
        'status': 'Verified'})
    d['db'].collection('registrations').document(reg_id).update({'certificate_id': old_id})
    d['db'].collection('events').document(d['event_id']).update({'status': 'completed'})
    from db_pg import get_session
    from models_pg import Certificate
    with get_session() as s:      # as if this event's certificates came before the switch
        s.query(Certificate).filter(Certificate.event_id == d['event_id'],
                                    Certificate.recipient_email == email).delete()
    page = _student(d, 'ana').get(f'/participant/certificate/{reg_id}').get_data(as_text=True)
    assert f'/verify/{old_id}/download' in page
    visitor = d['app'].test_client()
    assert 'Ana Attendee' in visitor.get(f'/verify/{old_id}').get_data(as_text=True)
    assert visitor.get(f'/verify/{old_id}/download').data[:4] == b'%PDF'
