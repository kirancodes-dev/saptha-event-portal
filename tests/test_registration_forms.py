"""
tests/test_registration_forms.py — UPG-01 on the real database layer: forms
from every template (and the seeded events) render every field with a name,
always ask for the registrant's identity once, store their answers, and a form
can't be saved with a field nobody can name.
"""
import datetime
import re

import pytest

from services_templates import TEMPLATES_CATALOG, TemplateService
from tests.test_integration_flow import _login, _unique, _user

TODAY = datetime.date.today()


def _template_event(db, template_id, owner):
    """An event made from a template the way API v1 makes them (field_name only)."""
    event = TemplateService.instantiate_event(
        db, template_id=template_id, title=_unique(f'{template_id.title()} Night'),
        date_str=(TODAY + datetime.timedelta(days=10)).isoformat(),
        deadline_str=(TODAY + datetime.timedelta(days=5)).isoformat(), created_by=owner)
    return event['id']


def _names(html):
    return re.findall(r'<(?:input|select|textarea)\b[^>]*\bname="([^"]*)"', html)


@pytest.fixture
def owner(real_app):
    flask_app, db = real_app
    email = f"{_unique('formspoc')}@test.edu"
    _user(db, email, 'ClubSPOC')
    return email


# ── Criterion 1 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('template_id', sorted(TEMPLATES_CATALOG))
def test_every_template_form_names_its_fields_and_asks_for_email_once(real_app, owner, template_id):
    flask_app, db = real_app
    event_id = _template_event(db, template_id, owner)
    stored = db.collection('event_forms').document(event_id).get().to_dict()['fields']
    assert stored and all('id' not in f for f in stored)  # what instantiate_event writes

    page = flask_app.test_client().get(f'/forms/register/{event_id}')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    names = [n for n in _names(html) if n != 'csrf_token']
    assert 'name=""' not in html and '' not in names
    assert names.count('email') == 1
    for identity in ('full_name', 'email', 'phone', 'usn'):
        assert identity in names, identity
    for field in stored:
        assert field['field_name'] in names, field['field_name']


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_a_template_form_submission_is_stored_and_shown_on_the_responses_page(real_app, owner):
    flask_app, db = real_app
    event_id = _template_event(db, 'hackathon', owner)   # a free template with its own fields
    student = f"{_unique('hacker')}@test.edu"
    _user(db, student, 'Student')
    client = _login(flask_app, student, 'Student')
    answers = {'full_name': 'Hana Hacker', 'email': student, 'phone': '9876543210', 'usn': '1SN22CS050',
               'team_name': 'Null Pointers', 'github_url': 'https://github.com/hana', 'tech_stack': 'Cloud & DevOps',
               'project_pitch': 'Edge inference on a budget', 'tshirt_size': 'M', 'dietary_preference': 'Vegan'}
    resp = client.post(f'/forms/submit/{event_id}', data=answers)
    assert resp.status_code == 302 and '/register' not in resp.headers['Location']

    reg = next(d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream())
    assert reg['lead_name'] == 'Hana Hacker' and reg['team_name'] == 'Null Pointers'
    submissions = [d.to_dict() for d in db.collection('form_submissions').where('event_id', '==', event_id).stream()]
    assert len(submissions) == 1
    for key in ('github_url', 'tech_stack', 'project_pitch', 'tshirt_size', 'dietary_preference'):
        assert submissions[0]['answers'][key] == answers[key], key

    page = _login(flask_app, owner, 'ClubSPOC').get(f'/forms/responses/{event_id}')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'https://github.com/hana' in html and 'Edge inference on a budget' in html


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_saving_a_field_with_no_id_is_refused(real_app, owner):
    flask_app, db = real_app
    event_id = _template_event(db, 'seminar', owner)
    client = _login(flask_app, owner, 'ClubSPOC')
    before = db.collection('event_forms').document(event_id).get().to_dict()

    resp = client.post(f'/forms/save/{event_id}', json={'fields': [
        {'id': 'email', 'type': 'email', 'label': 'Email'}, {'type': 'text', 'label': 'Nameless'}]})
    assert resp.status_code == 400 and 'Nameless' in resp.get_json()['message']
    assert db.collection('event_forms').document(event_id).get().to_dict() == before

    resp = client.post(f'/forms/save/{event_id}', json={'fields': [
        {'field_name': 'shirt', 'type': 'text', 'label': 'Shirt'}, {'type': 'heading', 'label': 'About you'}]})
    assert resp.status_code == 200
    saved = db.collection('event_forms').document(event_id).get().to_dict()['fields']
    assert [f['id'] for f in saved] == ['shirt', 'layout_1']


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_a_student_registers_for_the_seeded_conference_through_the_ui(real_app, monkeypatch):
    flask_app, db = real_app
    from seed_events_universal import seed_universal_portal
    seeded = seed_universal_portal(db)
    conference = next(e for e in seeded['events'] if e.get('event_type') == 'conference')
    event_id = conference['id']

    student = f"{_unique('delegate')}@test.edu"
    _user(db, student, 'Student')
    client = _login(flask_app, student, 'Student')
    page = client.get(f'/forms/register/{event_id}')
    assert page.status_code == 200
    names = [n for n in _names(page.get_data(as_text=True)) if n != 'csrf_token']
    assert names.count('email') == 1 and '' not in names

    form = {'full_name': 'Dee Delegate', 'email': student, 'phone': '9876543210', 'usn': '1SN21EC020'}
    for field in db.collection('event_forms').document(event_id).get().to_dict()['fields']:
        key = field['field_name']
        form.setdefault(key, (field.get('options') or ['Something'])[0])
    resp = client.post(f'/forms/submit/{event_id}', data=form)
    assert resp.status_code == 302

    if '/payment/checkout/' in resp.headers['Location']:  # the conference has a fee
        monkeypatch.setenv('PAYMENT_SIMULATION', 'true')
        assert client.get(resp.headers['Location']).status_code == 200
        assert client.post('/payment/process', data={'event_id': event_id}).status_code == 302
    regs = [d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream()
            if (d.to_dict() or {}).get('lead_email') == student]
    assert len(regs) == 1 and regs[0]['lead_name'] == 'Dee Delegate'
