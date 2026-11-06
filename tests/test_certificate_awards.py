"""
tests/test_certificate_awards.py — UPG-142 on the real database layer: the
organiser awards merit and special-mention certificates to registered people;
each is issued once, emailed and audit-logged; others get 403.
"""
import certificate_pdf
import services_certificates as certs
from tests.test_certificate_delivery import mail  # noqa: F401  (fixture)
from tests.test_certificate_issuing import _audit, _flash, site  # noqa: F401  (fixture)
from utils_storage import get_private


def test_the_organiser_awards_merit_and_special_mention(site, mail):  # noqa: F811
    d = site
    event_id = d['event']()
    d['reg'](event_id, 'Mira Merit', team_name='Byte Club',
             members=[{'name': 'Sam Special', 'email': 'sam.special@test.edu', 'attendance': 'Present'}])
    people = {p['name']: p['person_key'] for p in certs.registered_people(d['db'], event_id)}
    assert set(people) >= {'Mira Merit', 'Sam Special'}
    page = d['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert 'Award to' in page and 'Sam Special' in page

    url = f'/certificates/events/{event_id}/award'
    assert d['other'].post(url, data={'person': people['Mira Merit'], 'kind': 'merit'}).status_code == 403
    d['owner'].post(url, data={'person': people['Mira Merit'], 'kind': 'merit', 'note': 'for the best design in'})
    assert 'Certificate of Merit' in _flash(d['owner'])
    d['owner'].post(url, data={'person': people['Sam Special'], 'kind': 'special_mention'})
    issued = {c['name']: c for c in certs.for_event(event_id) if c['cert_type'] in certs.AWARD_TYPES}
    assert {n: c['cert_type'] for n, c in issued.items()} == {'Mira Merit': 'merit', 'Sam Special': 'special_mention'}
    assert 'for the best design in' in ' '.join(certificate_pdf.text_of(get_private(issued['Mira Merit']['pdf_key'])).split())

    d['owner'].post(url, data={'person': people['Mira Merit'], 'kind': 'merit'})            # once only
    assert 'already has this certificate' in _flash(d['owner'])
    assert len([c for c in certs.for_event(event_id) if c['cert_type'] == 'merit']) == 1
    assert sum(1 for m in mail if m['to'] == 'sam.special@test.edu') == 1                   # emailed
    for cert in issued.values():
        assert _audit(d['db'], 'CERT_AWARDED', cert['number'])

    d['owner'].post(url, data={'person': 'nobody|x', 'kind': 'merit'})
    assert 'Choose someone registered' in _flash(d['owner'])
    d['owner'].post(url, data={'person': people['Mira Merit'], 'kind': 'winner'})
    assert 'Choose merit or special mention' in _flash(d['owner'])
