"""
tests/test_certificate_participation.py — UPG-310: per event, the SPOC chooses
who gets the participation certificate (checked in, every member of a team
that submitted, or everyone registered) and whether it's in the portal only or
emailed too. An event that never chose behaves as before.
"""
import pytest

import services_certificates as certs
from tests.test_certificate_issuing import site  # noqa: F401  (the UPG-124 fixture)
from tests.test_integration_flow import _login, _unique, _user


@pytest.fixture
def queued(monkeypatch):
    import tasks.email_tasks
    out = []
    monkeypatch.setattr(tasks.email_tasks.send_certificate_email, 'delay', lambda *a, **k: out.append(a[0]))
    return out


def _people(d, event_id):
    """Checked in, absent, cancelled, and absent with a submission."""
    db = d['db']
    here = d['reg'](event_id, 'Here Person')
    away = d['reg'](event_id, 'Away Person', attendance='')
    gone = d['reg'](event_id, 'Gone Person', attendance='', status='cancelled')
    mate = f"{_unique('mate')}@test.edu"
    built = d['reg'](event_id, 'Builder Lead', attendance='', team_name='Builders',
                     members=[{'name': 'Builder Mate', 'email': mate}])
    db.collection('project_submissions').document(_unique('SUB')).set(
        {'event_id': event_id, 'registration_id': built, 'answers': {}})
    db.collection('events').document(event_id).update(
        {'hackathon': {'submission_form': {'fields': [{'id': 'f1', 'label': 'Repo', 'type': 'url'}]}}})
    return {'here': here, 'away': away, 'gone': gone, 'built': built, 'mate': mate}


def _owed(d, event_id):
    event = d['db'].collection('events').document(event_id).get().to_dict()
    return sorted(r['name'] for r in certs.recipients(d['db'], event_id, event) if r['cert_type'] == 'participation')


def _choose(d, event_id, who, how, client=None):
    return (client or d['owner']).post(f'/certificates/events/{event_id}/participation',
                                       data={'who': who, 'delivery': how})


# 1. Who gets the participation certificate
def test_the_spoc_chooses_who_gets_the_participation_certificate(site):  # noqa: F811
    d = site
    event_id = d['event']()
    _people(d, event_id)
    assert _owed(d, event_id) == ['Here Person']                                   # checked in: the default
    page = d['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert 'data-cert-participation' in page and 'Every member of a team that submitted' in page

    assert _choose(d, event_id, 'submitted', 'portal').status_code == 302
    assert _owed(d, event_id) == ['Builder Lead', 'Builder Mate']                  # the whole team, not checked in
    assert _choose(d, event_id, 'registered', 'portal').status_code == 302
    assert _owed(d, event_id) == ['Away Person', 'Builder Lead', 'Builder Mate', 'Here Person']   # not the cancelled
    assert _choose(d, event_id, 'present', 'portal').status_code == 302
    assert _owed(d, event_id) == ['Here Person']

    assert _choose(d, event_id, 'everyone!', 'portal').status_code == 302          # nonsense is refused
    assert d['db'].collection('events').document(event_id).get().to_dict()['cert_who'] == 'present'
    assert _choose(d, event_id, 'registered', 'email', client=d['other']).status_code == 403
    assert d['db'].collection('events').document(event_id).get().to_dict()['cert_who'] == 'present'


# 2. The portal only, or email too; each member sees theirs under My certificates
def test_in_the_portal_only_no_email_is_queued(site, queued):  # noqa: F811
    d = site
    event_id = d['event']()
    p = _people(d, event_id)
    _choose(d, event_id, 'submitted', 'portal')
    certs.issue_event(d['db'], event_id, d['people']['owner'], only=['participation'])
    issued = [c for c in certs.for_event(event_id) if c['cert_type'] == 'participation']
    assert sorted(c['name'] for c in issued) == ['Builder Lead', 'Builder Mate'] and queued == []
    _user(d['db'], p['mate'], 'Student', name='Builder Mate')
    mine = _login(d['app'], p['mate'], 'Student').get('/certificates/mine').get_data(as_text=True)
    [cert] = [c for c in issued if c['email'] == p['mate']]
    assert cert['number'] in mine

    # Email too: the next issue is queued
    other = d['event']()
    d['reg'](other, 'Mailed Person')
    _choose(d, other, 'present', 'email')
    certs.issue_event(d['db'], other, d['people']['owner'], only=['participation'])
    [mailed] = [c for c in certs.for_event(other) if c['cert_type'] == 'participation']
    assert queued == [mailed['id']]


def test_email_too_on_a_portal_only_hackathon_is_the_spocs_choice(site, queued):  # noqa: F811
    d = site
    event_id = d['event'](participant_emails='portal')           # the event's emails: portal only
    certs.deliver({'id': 'x1', 'email': 'a@test.edu', 'event_id': event_id})
    assert queued == []                                          # as before (UPG-195)
    _choose(d, event_id, 'present', 'email')
    certs.deliver({'id': 'x2', 'email': 'a@test.edu', 'event_id': event_id})
    assert queued == ['x2']
    _choose(d, event_id, 'present', 'portal')
    certs.deliver({'id': 'x3', 'email': 'a@test.edu', 'event_id': event_id})
    assert queued == ['x2']


# 3. An event that never chose: checked in only, emailed as the event's email mode says
def test_an_event_that_never_chose_behaves_as_before(site, queued):  # noqa: F811
    d = site
    event_id = d['event']()
    _people(d, event_id)
    event = d['db'].collection('events').document(event_id).get().to_dict()
    assert certs.who_gets(event) == 'present' and certs.delivery(event) == ''
    assert _owed(d, event_id) == ['Here Person']
    certs.issue_event(d['db'], event_id, d['people']['owner'], only=['participation'])
    [cert] = [c for c in certs.for_event(event_id) if c['cert_type'] == 'participation']
    assert queued == [cert['id']]
