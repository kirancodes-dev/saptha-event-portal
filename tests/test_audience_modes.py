"""
tests/test_audience_modes.py — UPG-270 on the real database layer: an event is
for this institution only, for invited institutions, or open to everyone; the
page says who may register before the form; the form holds an outside
participant of an invitation-only event to the invited email domains; and the
organiser's list tells inside from outside.
"""
import csv
import io
import re

import services_reach as reach
from tests import test_reach as _tr
from tests.test_integration_flow import _unique

site = _tr.site
INVITED = "City Engineering College, cityengg.edu.in\nLakeside Institute, lakeside.ac.in, students.lakeside.org"


def _guest_form(email, **extra):
    return dict({'privacy_consent': 'yes', 'full_name': 'Gita Guest', 'email': email, 'phone': '9876501111',
                 'participant_type': 'external', 'designation': 'Student', 'institution': 'Somewhere Else'}, **extra)


def _regs(d, event_id):
    return [r.to_dict() for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()]


def _who(html):
    """The access mode and the sentence a page shows, without its "Who can register" label."""
    found = re.search(r'data-eligibility="(\w+)"[^>]*>(.*?)</(?:p|li)>', html, re.S)
    if not found:
        return None, ''
    import html as _html
    text = ' '.join(_html.unescape(re.sub(r'<[^>]+>', ' ', found.group(2))).split())
    return found.group(1), re.sub(r'^Who can register:?\s*', '', text)


# ── Criterion 1: the list of invited institutions ───────────────────────────

def test_the_invited_list_is_read_line_by_line_and_says_what_is_wrong():
    good, problems = reach.parse_invited(INVITED + "\n\n")
    assert problems == [] and good == [
        {'name': 'City Engineering College', 'domains': ['cityengg.edu.in']},
        {'name': 'Lakeside Institute', 'domains': ['lakeside.ac.in', 'students.lakeside.org']}]
    assert reach.parse_invited("  Hill College ,  @HILL.edu ")[0] == [{'name': 'Hill College', 'domains': ['hill.edu']}]

    bad, problems = reach.parse_invited(
        "City Engineering College\nOpen College, gmail.com\nOdd College, not a domain\n"
        ", nowhere.edu\nFirst, twice.edu\nSecond, twice.edu")
    assert bad == [{'name': 'First', 'domains': ['twice.edu']}]
    assert [p.split(':')[0] for p in problems] == ['Line 1', 'Line 2', 'Line 3', 'Line 4', 'Line 6']
    assert 'email domain after a comma' in problems[0] and "anyone can have an @gmail.com address" in problems[1]
    assert "isn't an email domain" in problems[2] and 'name first' in problems[3]
    assert 'twice.edu is already on line 5' in problems[4]
    many = '\n'.join(f"College {n}, college{n}.edu" for n in range(reach.MAX_INVITED + 1))
    assert any('up to 50 invited institutions' in p for p in reach.parse_invited(many)[1])


# ── Criterion 2: the organiser chooses one of three ─────────────────────────

def test_the_organiser_chooses_who_can_register(site):
    d = site
    event_id = d['event']('Invitational')
    review = f'/spoc/event/{event_id}/review'
    page = d['owner'].get(review).get_data(as_text=True)
    assert 'data-audience-form' in page and re.search(r'id="aud-campus" value="campus" checked', page)
    for value in ('campus', 'invited', 'open'):
        assert f'id="aud-{value}"' in page
    assert _tr._ev(d, event_id).get('audience') in (None, '', 'campus') and reach.access_mode(_tr._ev(d, event_id)) == 'campus'

    # someone else's event: refused, nothing changes
    assert d['other'].post(f'/reach/events/{event_id}/audience',
                           data={'audience': 'invited', 'invited': INVITED}).status_code == 403
    assert reach.access_mode(_tr._ev(d, event_id)) == 'campus'

    # a list with a mistake isn't saved, and comes back to be fixed
    wrong = "City Engineering College, gmail.com"
    after = d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'invited', 'invited': wrong},
                            follow_redirects=True).get_data(as_text=True)
    assert "anyone can have an @gmail.com address" in after and wrong in after
    assert reach.access_mode(_tr._ev(d, event_id)) == 'campus' and not _tr._ev(d, event_id).get('invited_institutions')
    assert 'at least one invited institution' in d['owner'].post(
        f'/reach/events/{event_id}/audience', data={'audience': 'invited', 'invited': ''},
        follow_redirects=True).get_data(as_text=True)
    assert "Choose this institution only" in d['owner'].post(
        f'/reach/events/{event_id}/audience', data={'audience': 'anyone-at-all'},
        follow_redirects=True).get_data(as_text=True)

    # saved: the event takes outside participants, the list is kept, and it is in the audit log
    d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'invited', 'invited': INVITED})
    ev = _tr._ev(d, event_id)
    assert ev['audience'] == 'invited' and reach.access_mode(ev) == 'invited' and 'external' in ev['allowed_participants']
    assert [i['name'] for i in ev['invited_institutions']] == ['City Engineering College', 'Lakeside Institute']
    page = d['owner'].get(review).get_data(as_text=True)
    assert re.search(r'id="aud-invited" value="invited" checked', page) and 'City Engineering College, cityengg.edu.in' in page
    assert any(a.to_dict().get('action') == 'EVENT_AUDIENCE' and event_id in str(a.to_dict().get('details'))
               and 'City Engineering College' in str(a.to_dict().get('details'))
               for a in d['db'].collection('audit_log').stream())
    # an invitation-only event isn't on the public open-events page
    assert f'/event/{event_id}' not in d['visitor'].get('/open-events').get_data(as_text=True)

    d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'open'})
    assert reach.access_mode(_tr._ev(d, event_id)) == 'open'
    assert f'/event/{event_id}' in d['visitor'].get('/open-events').get_data(as_text=True)
    d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'campus'})
    assert reach.access_mode(_tr._ev(d, event_id)) == 'campus' and 'external' not in _tr._ev(d, event_id)['allowed_participants']


# ── Criterion 3: the page says who may register, before the form ────────────

def test_every_page_says_who_can_register_before_the_form(site):
    import services_institution
    d = site
    home = services_institution.profile(d['db'])['name']
    event_id = d['event']('Who Can Come')
    pages = (f'/event/{event_id}', f'/event/{event_id}?fragment=1', f'/forms/register/{event_id}')
    for url in pages:
        html = d['visitor'].get(url).get_data(as_text=True)
        assert _who(html) == ('campus', f'For students of {home} only.'), url

    d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'invited', 'invited': INVITED})
    line = (f"For students of {home}, and for participants from the invited institutions: City Engineering College, "
            "Lakeside Institute. Invited participants register with their institution's email address "
            "(@cityengg.edu.in, @lakeside.ac.in, @students.lakeside.org).")
    for url in pages:
        assert _who(d['visitor'].get(url).get_data(as_text=True)) == ('invited', line), url

    d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'open'})
    line = f"Open to students of {home}, and to participants from other colleges and organisations."
    for url in pages + ('/open-events?q=' + d['tag'].replace(' ', '+'),):
        assert _who(d['visitor'].get(url).get_data(as_text=True)) == ('open', line), url

    # the edit form's "who can register" boxes decide too: faculty only, with outsiders, is said as it is
    d['db'].collection('events').document(event_id).update({'allowed_participants': ['faculty', 'external'], 'audience': ''})
    assert _who(d['visitor'].get(pages[0]).get_data(as_text=True)) == (
        'open', f"Open to faculty of {home}, and to participants from other colleges and organisations.")
    d['db'].collection('events').document(event_id).update({'allowed_participants': ['external']})
    assert _who(d['visitor'].get(pages[0]).get_data(as_text=True))[1] == 'Open to participants from any college or organisation.'
    # invitation-only with nobody invited (set by hand): nobody outside gets in, and the page says so
    d['db'].collection('events').document(event_id).update(
        {'allowed_participants': ['student', 'external'], 'audience': 'invited', 'invited_institutions': []})
    assert 'No other institution has been invited yet.' in _who(d['visitor'].get(pages[0]).get_data(as_text=True))[1]


# ── Criterion 4: the form keeps to the invitation ───────────────────────────

def test_an_invitation_only_event_takes_outside_participants_from_the_invited_domains(site):
    d = site
    event_id = d['event']('Invited Hack')
    d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'invited', 'invited': INVITED})

    # an address that isn't on an invited domain: refused beside the email, nothing saved
    stranger = f"{_unique('stranger')}@othercollege.edu"
    refused = d['app'].test_client().post(f'/forms/submit/{event_id}', data=_guest_form(stranger), follow_redirects=True)
    text = refused.get_data(as_text=True)
    assert 'This event takes outside participants from the invited institutions only: City Engineering College, Lakeside Institute.' in text
    assert '@cityengg.edu.in' in text and _regs(d, event_id) == []
    assert not d['db'].collection('users').document(stranger).get().exists
    # a look-alike domain doesn't pass
    fake = f"{_unique('fake')}@notcityengg.edu.in"
    d['app'].test_client().post(f'/forms/submit/{event_id}', data=_guest_form(fake))
    assert _regs(d, event_id) == []

    # an invited address: registered, and the institution is the invited one, whatever was typed
    invited = f"{_unique('invited')}@cityengg.edu.in"
    d['app'].test_client().post(f'/forms/submit/{event_id}', data=_guest_form(invited))
    [reg] = _regs(d, event_id)
    assert reg['participant_type'] == 'external' and reg['institution'] == 'City Engineering College'
    # a sub-domain of an invited domain counts
    sub = f"{_unique('sub')}@mail.lakeside.ac.in"
    d['app'].test_client().post(f'/forms/submit/{event_id}', data=_guest_form(sub, full_name='Sub Domain'))
    assert sorted(r['institution'] for r in _regs(d, event_id)) == ['City Engineering College', 'Lakeside Institute']

    # the institution's own students still register as before, with any address
    own = f"{_unique('own')}@gmail.com"
    d['app'].test_client().post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Own Student', 'email': own, 'phone': '9876502222',
        'participant_type': 'student'})
    assert len(_regs(d, event_id)) == 3

    # open to everyone: the stranger's address is fine
    d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'open'})
    d['app'].test_client().post(f'/forms/submit/{event_id}', data=_guest_form(stranger, full_name='A Stranger'))
    assert len(_regs(d, event_id)) == 4
    # this institution only: nobody from outside
    d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'campus'})
    late = d['app'].test_client().post(f'/forms/submit/{event_id}', data=_guest_form(
        f"{_unique('late')}@cityengg.edu.in"), follow_redirects=True)
    assert 'This event is for students only' in late.get_data(as_text=True) and len(_regs(d, event_id)) == 4


# ── Criterion 5: the organiser tells inside from outside ────────────────────

def test_the_organiser_tells_inside_from_outside(site):
    d = site
    event_id = d['event']('Mixed Crowd')
    listing = f'/coordinator/registrations/{event_id}'
    # a campus-only event with nobody from outside offers no such filter
    assert 'data-filter="origin"' not in d['owner'].get(listing).get_data(as_text=True)

    d['owner'].post(f'/reach/events/{event_id}/audience', data={'audience': 'open'})
    guest = f"{_unique('mixguest')}@othercollege.edu"
    own = f"{_unique('mixown')}@test.edu"
    d['app'].test_client().post(f'/forms/submit/{event_id}', data=_guest_form(guest, institution='Far Away College'))
    d['app'].test_client().post(f'/forms/submit/{event_id}', data={
        'privacy_consent': 'yes', 'full_name': 'Own Student', 'email': own, 'phone': '9876502222',
        'participant_type': 'student'})
    assert len(_regs(d, event_id)) == 2

    page = d['owner'].get(listing).get_data(as_text=True)
    assert 'data-filter="origin"' in page and page.count('data-outside>') == 1 and 'Far Away College' in page
    assert re.search(r'data-outside-count>1 registration from outside this institution', page)
    outside = d['owner'].get(listing + '?origin=outside').get_data(as_text=True)
    assert 'Gita Guest' in outside and 'Own Student' not in outside and 'Showing 1 of 2.' in outside
    inside = d['owner'].get(listing + '?origin=inside').get_data(as_text=True)
    assert 'Own Student' in inside and 'Gita Guest' not in inside and 'data-outside>' not in inside
    assert 'Gita Guest' in d['owner'].get(listing + '?origin=nonsense').get_data(as_text=True)   # unknown: everyone

    # the filtered download holds the same people, with the type and the institution
    got = d['owner'].get(f'/coordinator/registrations/{event_id}/export_filtered?origin=outside')
    assert got.status_code == 200
    rows = list(csv.reader(io.StringIO(got.get_data(as_text=True).lstrip('﻿'))))
    body = [r for r in rows[1:] if any(r)]
    assert len(body) == 1 and 'Gita Guest' in ' '.join(body[0]) and 'Far Away College' in ' '.join(body[0])
    assert 'Own Student' not in got.get_data(as_text=True)

    # someone who doesn't run the event sees neither
    assert d['other'].get(listing + '?origin=outside').status_code in (302, 403)
    assert d['other'].get(f'/coordinator/registrations/{event_id}/export_filtered?origin=outside').status_code in (302, 403)
