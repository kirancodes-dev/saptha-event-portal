"""
tests/test_certificate_award_participation.py — UPG-341: the SPOC gives the
participation certificate (in their own design) to one registered person the
attendance rule left out, a winning team's member who was never checked in,
from the Award row; once only; nobody else is touched.
"""
import html
import re

import services_certificates as certs
from tests.test_certificate_design import _upload, artwork, site  # noqa: F401
from tests.test_certificate_issuing import _audit, _flash


def _award(d, event_id, person, kind):
    d['clients']['owner'].post(f'/certificates/events/{event_id}/award', data={'person': person, 'kind': kind})
    return html.unescape(_flash(d['clients']['owner']))


def test_the_spoc_gives_a_winner_the_participation_certificate_in_their_design(site):  # noqa: F811
    d = site
    event_id = d['event']()
    _upload(d['clients']['owner'], event_id, artwork())          # own design, no signatory
    d['person'](event_id, 'Here Already')                        # checked in
    winner = d['person'](event_id, 'Wren Winner', attendance='')  # judged, never scanned
    certs.issue_event(d['db'], event_id, d['people']['owner'], only=['participation'])
    assert [c['name'] for c in certs.for_event(event_id)] == ['Here Already']

    page = d['clients']['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert re.search(r'<option value="participation" data-award-base>Participation \(your design\)</option>', page)
    award_button = re.search(r'<button type="submit"[^>]*>Award</button>', page).group(0)
    assert 'disabled' not in award_button

    people = {p['name']: p['person_key'] for p in certs.registered_people(d['db'], event_id)}
    assert 'Certificate of Participation' in _award(d, event_id, people['Wren Winner'], 'participation')
    [cert] = [c for c in certs.for_event(event_id) if c['email'] == winner]
    assert cert['cert_type'] == 'participation' and cert['data']['design']          # drawn on the SPOC's design
    assert _audit(d['db'], 'CERT_AWARDED', cert['number'])

    assert 'already has this certificate' in _award(d, event_id, people['Wren Winner'], 'participation')
    assert 'already has this certificate' in _award(d, event_id, people['Here Already'], 'participation')
    assert sorted(c['name'] for c in certs.for_event(event_id)) == ['Here Already', 'Wren Winner']   # once each


def test_merit_still_needs_a_signatory_and_other_types_are_refused(site):  # noqa: F811
    d = site
    event_id = d['event']()
    _upload(d['clients']['owner'], event_id, artwork())
    d['person'](event_id, 'Mo Merit')
    person = certs.registered_people(d['db'], event_id)[0]['person_key']
    assert 'signator' in _award(d, event_id, person, 'merit').lower()
    assert 'Choose merit or special mention' in _award(d, event_id, person, 'winner')
    assert certs.for_event(event_id) == []
