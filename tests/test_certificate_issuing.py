"""
tests/test_certificate_issuing.py — UPG-124 on the real database layer:
issuing in the background in chunks with progress and a retry, automatically
when results are published (unless switched off), not before the event ends,
by hand to one person, the organiser's list, and each stored PDF checked
against the SHA-256 on its record.
"""
import hashlib
import json

import pytest

import services_certificate_runs as runs
import services_certificates as certs
from tests.test_certificate_types import _signature
from tests.test_integration_flow import _create_event, _login, _unique, _user
from utils_storage import get_private, put_private


@pytest.fixture
def site(real_app, monkeypatch):
    flask_app, db = real_app
    import routes_coordinator
    import routes_spoc
    for mod in (routes_spoc, routes_coordinator):
        monkeypatch.setattr(mod, 'db', db, raising=False)
    monkeypatch.setattr(routes_coordinator, 'send_result_email', lambda *a, **k: None)
    monkeypatch.setenv('TASK_INLINE_TIMEOUT', '600')      # the inline "background" run finishes inside the request
    people = {k: f"{_unique('iss' + k)}@test.edu" for k in ('owner', 'other')}
    _user(db, people['owner'], 'ClubSPOC')
    _user(db, people['other'], 'ClubSPOC')
    owner = _login(flask_app, people['owner'], 'ClubSPOC')

    def event(signed=True, **fields):
        import services_signatories
        event_id = _create_event(owner, db, _unique('Issued Event'), '2031-05-05', team=False)
        db.collection('events').document(event_id).update(dict({'status': 'completed', 'staff': []}, **fields))
        if signed:
            services_signatories.add(db, event_id, name='Dr. A. Kumar', title='Principal', image=_signature(),
                                     actor=people['owner'])
        return event_id

    def reg(event_id, name, attendance='Present', **fields):
        reg_id = _unique('REG')
        db.collection('registrations').document(reg_id).set(dict({
            'event_id': event_id, 'lead_name': name, 'lead_email': f"{_unique('p')}@test.edu",
            'status': 'Confirmed', 'attendance': attendance}, **fields))
        return reg_id
    return {'app': flask_app, 'db': db, 'people': people, 'owner': owner,
            'other': _login(flask_app, people['other'], 'ClubSPOC'), 'event': event, 'reg': reg}


def _flash(client):
    with client.session_transaction() as sess:
        return ' '.join(m for _, m in sess.get('_flashes', []))


def _audit(db, action, event_id):
    return [a.to_dict() for a in db.collection('audit_log').stream()
            if a.to_dict().get('action') == action and event_id in json.dumps(a.to_dict(), default=str)]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_a_bulk_issue_for_1200_people_runs_in_chunks_reports_progress_and_retries(site, monkeypatch):
    d = site
    monkeypatch.setenv('CERT_CHUNK_SIZE', '100')
    event_id = d['event']()
    for i in range(1200):
        d['reg'](event_id, f'Person {i:04d}')
    broken = {'Person 0150', 'Person 0151', 'Person 1199'}
    real_render = certs.render
    monkeypatch.setattr(certs, 'render', lambda event, cert: (_ for _ in ()).throw(RuntimeError('printer jam'))
                        if cert['name'] in broken else b'%PDF-1.4 ' + cert['number'].encode())

    d['owner'].post(f'/certificates/events/{event_id}/issue')
    assert 'Issuing 1201 certificates' in _flash(d['owner'])             # 1,200 participants and the organiser
    [run] = runs.for_event(d['db'], event_id)
    p = runs.progress(run)
    assert (p['status'], p['total'], p['chunks_total'], p['chunks_done']) == ('failed', 1201, 13, 13)
    assert (p['done'], p['failed'], p['issued']) == (1198, 3, 1198)
    assert sorted(e['name'] for e in p['errors']) == sorted(broken) and 'printer jam' in p['errors'][0]['error']
    page = d['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert '1198 of 1201 done, 3 failed' in page and 'Retry the failed ones' in page
    progress = d['owner'].get(f"/certificates/events/{event_id}/runs/{run['id']}").get_json()
    assert progress['done'] == 1198 and progress['failed'] == 3

    monkeypatch.setattr(certs, 'render', lambda event, cert: b'%PDF-1.4 ' + cert['number'].encode())
    d['owner'].post(f"/certificates/events/{event_id}/runs/{run['id']}/retry")
    p = runs.progress(runs.get(d['db'], run['id']))
    assert (p['status'], p['done'], p['failed'], p['issued']) == ('done', 1201, 0, 1201)
    issued = [c for c in certs.for_event(event_id) if c['cert_type'] == 'participation']
    assert len(issued) == 1200 and len({c['person_key'] for c in issued}) == 1200
    assert len({c['number'] for c in issued}) == 1200

    again = runs.start(d['db'], event_id, d['people']['owner'])               # nothing twice
    p = runs.progress(runs.get(d['db'], again['id']))
    assert (p['issued'], p['done'], p['failed']) == (0, 1201, 0)
    assert len(certs.for_event(event_id)) == len(issued) + 1                  # + the organiser's own
    assert _audit(d['db'], 'CERT_RUN_STARTED', event_id) and _audit(d['db'], 'CERT_RUN_RETRIED', event_id)
    monkeypatch.setattr(certs, 'render', real_render)


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def _scored_event(d, **fields):
    event_id = d['event'](status='in_progress', **fields)
    for name, total in (('Gold Team', 95), ('Silver Team', 90), ('Bronze Team', 85), ('Fourth Team', 70)):
        d['reg'](event_id, f'{name} Lead', team_name=name, scores={'j1': {'total': total}})
    return event_id


def test_publishing_results_issues_the_position_certificates(site):
    d = site
    event_id = _scored_event(d)
    d['owner'].post(f'/spoc/publish_results/{event_id}')
    got = {(c['name'], c['cert_type'], c['position']) for c in certs.for_event(event_id)}
    assert got == {('Gold Team Lead', 'winner', 1), ('Silver Team Lead', 'runner_up', 2),
                   ('Bronze Team Lead', 'position', 3)}
    assert all(certs.file_check(c) == 'ok' for c in certs.for_event(event_id))


def test_with_the_automatic_issue_off_publishing_issues_nothing(site):
    d = site
    event_id = _scored_event(d)
    d['owner'].post(f'/certificates/events/{event_id}/auto', data={'auto': 'off'})
    assert d['db'].collection('events').document(event_id).get().to_dict()['cert_auto_issue'] is False
    assert 'Turn on' in d['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    d['owner'].post(f'/spoc/publish_results/{event_id}')
    assert certs.for_event(event_id) == []
    assert _audit(d['db'], 'CERT_AUTO_ISSUE', event_id)


def test_publishing_without_a_signatory_says_why_nothing_was_issued(site):
    d = site
    event_id = _scored_event(d, signed=False)
    d['owner'].post(f'/spoc/publish_results/{event_id}')
    assert "Position certificates weren't issued: Add at least one certificate signatory" in _flash(d['owner'])
    assert certs.for_event(event_id) == []


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_not_before_the_event_ends_then_by_hand_with_the_list(site):
    d = site
    event_id = d['event'](status='registration_open', date='2031-05-05')
    d['reg'](event_id, 'Early Ella')
    d['owner'].post(f'/certificates/events/{event_id}/issue')
    assert 'once the event has ended' in _flash(d['owner']) and certs.for_event(event_id) == []
    page = d['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert 'disabled aria-describedby="issue-problem"' in page and 'once the event has ended' in page
    assert d['other'].post(f'/certificates/events/{event_id}/issue').status_code == 403

    d['db'].collection('events').document(event_id).update({'status': 'completed'})
    late = d['reg'](event_id, 'Late Leo', attendance='Absent')
    assert all(r['name'] != 'Late Leo' for r in certs.recipients(d['db'], event_id))
    d['db'].collection('registrations').document(late).update({'attendance': 'Present'})   # attendance fixed later
    [leo] = [r for r in certs.recipients(d['db'], event_id) if r['name'] == 'Late Leo']
    pair = f"{leo['person_key']}|{leo['cert_type']}"
    assert d['other'].post(f'/certificates/events/{event_id}/issue_one', data={'pair': pair}).status_code == 403
    d['owner'].post(f'/certificates/events/{event_id}/issue_one', data={'pair': pair})
    [cert] = [c for c in certs.for_event(event_id) if c['name'] == 'Late Leo']
    assert f"Certificate {cert['number']} issued to Late Leo" in _flash(d['owner'])
    [entry] = _audit(d['db'], 'CERT_ISSUED_BY_HAND', event_id)
    assert cert['number'] in entry['details']
    d['owner'].post(f'/certificates/events/{event_id}/issue_one', data={'pair': pair})
    assert 'Late Leo already has this certificate' in _flash(d['owner'])
    d['owner'].post(f'/certificates/events/{event_id}/issue_one', data={'pair': 'nobody|participation'})
    assert "isn't owed that certificate" in _flash(d['owner'])

    page = d['owner'].get(f'/certificates/events/{event_id}').get_data(as_text=True)
    assert 'Late Leo' in page and cert['number'] in page and 'Certificate of Participation' in page
    assert 'Early Ella' in page and 'Not yet' in page                       # owed, not issued yet


def test_an_event_past_its_last_day_can_issue():
    assert certs.event_ended({'status': 'in_progress', 'date': '2020-01-01'})
    assert certs.event_ended({'status': 'registration_closed', 'date': '2020-01-01', 'end_date': '2020-01-03'})
    assert not certs.event_ended({'status': 'in_progress', 'date': '2999-01-01'})
    assert not certs.event_ended({'status': 'cancelled', 'date': '2020-01-01'})
    assert certs.event_ended({'status': 'completed', 'date': '2999-01-01'})


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_stored_pdf_matches_its_hash_and_a_changed_file_is_reported(site):
    d = site
    event_id = d['event']()
    d['reg'](event_id, 'Hash Hema')
    certs.issue_event(d['db'], event_id, d['people']['owner'], only=['participation'])
    [cert] = [c for c in certs.for_event(event_id) if c['name'] == 'Hash Hema']
    assert hashlib.sha256(get_private(cert['pdf_key'])).hexdigest() == cert['pdf_sha256']
    assert certs.file_check(cert) == 'ok'
    d['owner'].post(f'/certificates/events/{event_id}/check_files')
    assert 'All 1 certificate files match their records' in _flash(d['owner'])

    put_private(b'%PDF-1.4 tampered', cert['pdf_key'], 'application/pdf')
    assert certs.file_check(cert) == 'changed'
    d['owner'].post(f'/certificates/events/{event_id}/check_files')
    assert f"1 of 1 certificate files don't match their record: {cert['number']}" in _flash(d['owner'])


def test_a_failed_render_leaves_nothing_behind(site, monkeypatch):
    d = site
    event_id = d['event']()
    d['reg'](event_id, 'Retry Rita')
    real_render = certs.render
    monkeypatch.setattr(certs, 'render', lambda event, cert: (_ for _ in ()).throw(RuntimeError('font missing')))
    assert certs.issue_event(d['db'], event_id, '', only=['participation'])['failed'] == 1
    assert certs.for_event(event_id) == []                                     # the claim was released
    monkeypatch.setattr(certs, 'render', real_render)
    assert certs.issue_event(d['db'], event_id, '', only=['participation'])['issued'] == 1
