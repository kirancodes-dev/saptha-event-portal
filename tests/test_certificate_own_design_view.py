"""
tests/test_certificate_own_design_view.py — UPG-339: on an event with the
SPOC's own certificate design, the student's Certificate button shows the
certificate actually issued to them (the design with their name), never the
built-in page; before it's issued they're told it isn't out yet. An event
without its own design keeps the built-in page.
"""
import html

from tests.test_certificate_design import _issue, _upload, artwork, site  # noqa: F401
from tests.test_integration_flow import _login, _user


def _student(d, event_id, name):
    email = d['person'](event_id, name)
    _user(d['db'], email, 'Student', name=name)
    reg_id = next(r.id for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()
                  if (r.to_dict() or {}).get('lead_email') == email)
    return _login(d['app'], email, 'Student'), reg_id, email


def test_the_student_sees_the_issued_certificate_in_the_spocs_design(site):  # noqa: F811
    d = site
    event_id = d['event']()
    _upload(d['clients']['owner'], event_id, artwork())
    client, reg_id, email = _student(d, event_id, 'Keerthana Design')

    # Not issued yet: no built-in certificate, a plain message instead
    early = client.get(f'/participant/certificate/{reg_id}')
    assert early.status_code == 302 and early.headers['Location'].endswith('/participant/dashboard')
    shown = html.unescape(client.get(f'/participant/certificate/{reg_id}', follow_redirects=True).get_data(as_text=True))
    assert "Your certificate hasn't been issued yet" in shown and 'This is proudly presented to' not in shown

    _issue(d, event_id)
    import services_certificates as certs
    [cert] = [c for c in certs.for_event(event_id) if c['email'] == email]
    page = client.get(f'/participant/certificate/{reg_id}').get_data(as_text=True)
    assert 'data-issued-certificate' in page and f'/certificates/c/{cert["number"]}/png' in page
    assert f'/certificates/c/{cert["number"]}/pdf' in page
    assert 'This is proudly presented to' not in page and 'Division SPOC' not in page
    image = client.get(f'/certificates/c/{cert["number"]}/png')
    assert image.status_code == 200 and image.data[:8] == b'\x89PNG\r\n\x1a\n'


def test_an_event_without_its_own_design_keeps_the_built_in_page(site):  # noqa: F811
    d = site
    event_id = d['event']()
    client, reg_id, _ = _student(d, event_id, 'Plain Student')
    page = client.get(f'/participant/certificate/{reg_id}')
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert 'This is proudly presented to' in text and 'data-issued-certificate' not in text
