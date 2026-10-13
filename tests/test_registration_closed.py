"""
tests/test_registration_closed.py — UPG-34 on the real database layer: every
registration route applies one "is registration open?" check
(routes_forms.registration_closed), the legacy /participant/public_register
included, and the public event page sends people to the checked form.
"""
import datetime
import re

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user

TODAY = datetime.date.today()


@pytest.fixture
def event(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('closedspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Closing Soon'),
                             (TODAY + datetime.timedelta(days=7)).isoformat(), team=False)
    db.collection('events').document(event_id).update({'status': 'registration_open',
                                                       'reg_deadline': (TODAY + datetime.timedelta(days=3)).isoformat()})
    return flask_app, db, event_id


def _form(email):
    return {'full_name': 'Late Larry', 'email': email, 'phone': '9876543210', 'usn': '1SN22CS777'}


def _regs(db, event_id):
    return [d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream()]


# ── Criterion 1 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('closed', [{'status': 'draft'}, {'status': 'registration_closed'}, {'status': 'cancelled'},
                                    {'status': 'pending_approval'}, {'deadline': '2000-01-01'}])
def test_the_legacy_route_refuses_a_closed_event_and_creates_nothing(event, closed):
    flask_app, db, event_id = event
    db.collection('events').document(event_id).update(closed)
    newcomer = f"{_unique('late')}@test.edu"

    resp = flask_app.test_client().post(f'/participant/public_register/{event_id}', data=_form(newcomer))
    assert resp.status_code == 302 and resp.headers['Location'].endswith(f'/event/{event_id}')
    assert _regs(db, event_id) == []
    assert not db.collection('users').document(newcomer).get().exists

    # The form route refuses it too, with the same check
    resp = flask_app.test_client().post(f'/forms/submit/{event_id}', data={**_form(newcomer), 'privacy_consent': 'yes'})
    assert resp.status_code == 302 and _regs(db, event_id) == []


def test_the_legacy_route_still_registers_for_an_open_event(event):
    flask_app, db, event_id = event
    newcomer = f"{_unique('ontime')}@test.edu"
    resp = flask_app.test_client().post(f'/participant/public_register/{event_id}', data=_form(newcomer))
    assert resp.status_code == 302
    assert [r['lead_email'] for r in _regs(db, event_id)] == [newcomer]


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_the_event_page_sends_registrants_to_the_checked_form(event):
    flask_app, db, event_id = event
    page = flask_app.test_client().get(f'/event/{event_id}')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert '/participant/public_register' not in html
    assert f'href="/forms/register/{event_id}"' in html

    form_page = flask_app.test_client().get(f'/forms/register/{event_id}').get_data(as_text=True)
    actions = re.findall(r'<form\b[^>]*action="([^"]+)"', form_page)
    assert f'/forms/submit/{event_id}' in actions
