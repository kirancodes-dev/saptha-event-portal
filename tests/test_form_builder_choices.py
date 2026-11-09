"""
tests/test_form_builder_choices.py — UPG-212 on the real database layer: the
registration form shows exactly what the SPOC built. Only name and email are
fixed (always asked, always required); every other question can be removed or
made optional or required; a choice answer must be one of the SPOC's options;
the SPOC chooses what each team member is asked besides name and email; the
builder refuses a form it couldn't show. Forms saved before UPG-212 keep phone
and USN, as before.
"""
import datetime
import re

import pytest

from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def fb(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('fbspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    owner = _login(flask_app, spoc, 'ClubSPOC')
    day = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()

    def event(team=False):
        event_id = _create_event(owner, db, _unique('Form Fest'), day, team=team)
        db.collection('events').document(event_id).update(
            {'status': 'registration_open', 'venue': 'Hall A', 'member_confirm': False})
        return event_id

    def save(event_id, fields, **extra):
        return owner.post(f'/forms/save/{event_id}', json=dict(
            {'form_type': 'custom', 'form_title': 'Sign up', 'form_desc': '', 'fields': fields, 'chosen': True},
            **extra))

    def page(event_id):
        return flask_app.test_client().get(f'/forms/register/{event_id}').get_data(as_text=True)

    def submit(event_id, **answers):
        client = flask_app.test_client()
        data = {'privacy_consent': 'yes'}
        data.update(answers)
        resp = client.post(f'/forms/submit/{event_id}', data=data)
        with client.session_transaction() as sess:
            errors = (sess.get('form_state') or {}).get('errors') or {}
        return resp, errors

    def regs(event_id):
        return [d.to_dict() for d in db.collection('registrations').where('event_id', '==', event_id).stream()]

    return {'app': flask_app, 'db': db, 'owner': owner, 'event': event, 'save': save, 'page': page,
            'submit': submit, 'regs': regs}


def _control(page, name):
    """The input, select or textarea named `name`, or None."""
    m = re.search(rf'<(?:input|select|textarea)\b[^>]*\bname="{re.escape(name)}"[^>]*>', page)
    return m.group(0) if m else None


def _required(page, name):
    tag = _control(page, name)
    return tag is not None and re.search(r'\brequired\b', tag) is not None


NAME = {'id': 'full_name', 'type': 'text', 'label': 'Full Name', 'required': True}
EMAIL = {'id': 'email', 'type': 'email', 'label': 'Email', 'required': True}
SHIRT = {'id': 'shirt', 'type': 'select', 'label': 'T-shirt size', 'required': True, 'options': ['S', 'M', 'L']}
YEAR = {'id': 'year_of_study', 'type': 'radio', 'label': 'Year', 'required': False, 'options': ['1', '2', '3', '4']}
SKILLS = {'id': 'skills', 'type': 'checkbox_group', 'label': 'Skills', 'required': True,
          'options': ['Web', 'ML', 'IoT']}


# ── Criterion 1 ─────────────────────────────────────────────────────────────

def test_the_form_shows_exactly_what_the_spoc_built_with_phone_and_usn_removed(fb):
    event_id = fb['event']()
    assert fb['save'](event_id, [NAME, EMAIL, SHIRT, YEAR, SKILLS]).status_code == 200
    page = fb['page'](event_id)
    for name in ('full_name', 'email', 'shirt', 'year_of_study', 'skills'):
        assert _control(page, name), name
    assert _control(page, 'phone') is None and _control(page, 'usn') is None    # removed stays removed
    assert _required(page, 'shirt') and not _required(page, 'year_of_study')

    # Registering needs no phone; the answers are kept
    resp, errors = fb['submit'](event_id, full_name='Ria Rao', email=f"{_unique('ria')}@test.edu",
                                shirt='M', skills=['Web', 'IoT'])
    assert resp.status_code == 302 and not errors, errors
    [reg] = fb['regs'](event_id)
    assert reg['form_answers']['shirt'] == 'M' and reg['form_answers']['skills'] == ['Web', 'IoT']

    # Required questions are enforced on the server, optional ones aren't
    resp, errors = fb['submit'](event_id, full_name='No Shirt', email=f"{_unique('ns')}@test.edu")
    assert set(errors) == {'shirt', 'skills'}


def test_a_question_can_be_made_optional_or_required_and_phone_required(fb):
    event_id = fb['event']()
    phone = {'id': 'phone', 'type': 'tel', 'label': 'Phone', 'required': False}
    fb['save'](event_id, [NAME, EMAIL, phone, dict(SHIRT, required=False)])
    page = fb['page'](event_id)
    assert _control(page, 'phone') and not _required(page, 'phone') and not _required(page, 'shirt')
    resp, errors = fb['submit'](event_id, full_name='Opt Out', email=f"{_unique('oo')}@test.edu")
    assert resp.status_code == 302 and not errors

    fb['save'](event_id, [NAME, EMAIL, dict(phone, required=True)])
    assert _required(fb['page'](event_id), 'phone')
    _, errors = fb['submit'](event_id, full_name='No Phone', email=f"{_unique('np')}@test.edu")
    assert set(errors) == {'phone'}


# ── Criterion 2 ─────────────────────────────────────────────────────────────

def test_name_and_email_are_always_asked_and_required(fb):
    event_id = fb['event']()
    # A form without them, and one that marks them optional
    fb['save'](event_id, [SHIRT])
    page = fb['page'](event_id)
    assert _required(page, 'full_name') and _required(page, 'email')
    fb['save'](event_id, [dict(NAME, required=False), dict(EMAIL, required=False), SHIRT])
    page = fb['page'](event_id)
    assert _required(page, 'full_name') and _required(page, 'email')
    _, errors = fb['submit'](event_id, shirt='S')
    assert {'full_name', 'email'} <= set(errors)

    builder = fb['owner'].get(f'/forms/builder/{event_id}').get_data(as_text=True)
    assert 'Name and email are always asked and required' in builder
    assert "const LOCKED_IDS = ['full_name', 'name', 'participant_name', 'email', 'email_address']" in builder


# ── Criterion 3 ─────────────────────────────────────────────────────────────

def test_a_choice_must_be_one_of_the_spocs_options(fb):
    event_id = fb['event']()
    fb['save'](event_id, [NAME, EMAIL, SHIRT, YEAR, SKILLS])
    for bad in ({'shirt': 'XXL', 'skills': ['Web']}, {'shirt': 'S', 'skills': ['Web', 'Hacking']},
                {'shirt': 'S', 'skills': ['ML'], 'year_of_study': '9'}):
        _, errors = fb['submit'](event_id, full_name='Odd One', email=f"{_unique('odd')}@test.edu", **bad)
        assert errors and all('Choose from the options' in m for m in errors.values()), bad
    assert fb['regs'](event_id) == []


# ── Criterion 4 ─────────────────────────────────────────────────────────────

def test_the_builder_refuses_a_form_it_could_not_show_and_keeps_the_last_one(fb):
    event_id = fb['event'](team=True)
    assert fb['save'](event_id, [NAME, EMAIL, SHIRT]).status_code == 200
    saved = fb['db'].collection('event_forms').document(event_id).get().to_dict()
    for fields, words in (
            ([NAME, EMAIL, {'id': 'x', 'type': 'colour', 'label': 'Colour'}], "type the form can't show"),
            ([NAME, EMAIL, dict(SHIRT, options=['', ' '])], 'needs at least one option'),
            ([NAME, EMAIL, SHIRT, dict(SHIRT, label='Again')], "share the id 'shirt'"),
            ([NAME, EMAIL, {'id': 'member_1_phone', 'type': 'tel', 'label': 'Member 2 phone'}], 'Team members'),
            ([NAME, EMAIL, {'id': 'q', 'type': 'text', 'label': '  '}], 'needs a label')):
        resp = fb['save'](event_id, fields)
        assert resp.status_code == 400 and words in resp.get_json()['message'], words
    assert fb['db'].collection('event_forms').document(event_id).get().to_dict() == saved

    # Blank and repeated options are dropped when saving
    fb['save'](event_id, [NAME, EMAIL, dict(SHIRT, options=['S', ' ', 'S', 'M'])])
    stored = fb['db'].collection('event_forms').document(event_id).get().to_dict()['fields']
    assert next(f for f in stored if f['id'] == 'shirt')['options'] == ['S', 'M']


# ── Criterion 5 ─────────────────────────────────────────────────────────────

def test_the_spoc_chooses_what_each_team_member_is_asked(fb):
    event_id = fb['event'](team=True)                   # 2 to 4 people
    fb['save'](event_id, [NAME, EMAIL], member_fields={'usn': 'required', 'phone': 'optional'})
    page = fb['page'](event_id)
    assert _required(page, 'member_1_usn') and _control(page, 'member_1_phone') \
        and not _required(page, 'member_1_phone')
    assert _control(page, 'member_2_usn') and not _required(page, 'member_2_usn')    # beyond the minimum

    lead = f"{_unique('lead')}@test.edu"
    base = {'full_name': 'Lena Lead', 'email': lead, 'team_name': 'Byte Force',
            'member_1_name': 'Mo Mate', 'member_1_email': f"{_unique('mo')}@test.edu"}
    _, errors = fb['submit'](event_id, **base)
    assert set(errors) == {'member_1_usn'}
    resp, errors = fb['submit'](event_id, **base, member_1_usn='1sn22cs009', member_1_phone='9876500001')
    assert resp.status_code == 302 and not errors, errors
    [reg] = fb['regs'](event_id)
    mate = next(m for m in reg['members'] if m.get('name') == 'Mo Mate')
    assert mate['usn'] == '1SN22CS009' and mate['phone'] == '9876500001'

    # Members asked nothing extra: no USN or phone rows at all
    fb['save'](event_id, [NAME, EMAIL], member_fields={'usn': 'off', 'phone': 'off'})
    page = fb['page'](event_id)
    assert _control(page, 'member_1_usn') is None and _control(page, 'member_1_phone') is None
    assert _required(page, 'member_1_name') and _required(page, 'member_1_email')

    builder = fb['owner'].get(f'/forms/builder/{event_id}').get_data(as_text=True)
    assert 'data-member-fields' in builder and 'data-member-field="phone"' in builder
    solo = fb['event']()
    assert 'data-member-fields' not in fb['owner'].get(f'/forms/builder/{solo}').get_data(as_text=True)


# ── Criterion 6 ─────────────────────────────────────────────────────────────

def test_a_form_saved_before_the_change_keeps_phone_and_usn_and_member_usn(fb):
    event_id = fb['event'](team=True)
    # Saved without `chosen` (the wizard and older builders): phone and USN come back, as before
    fb['owner'].post(f'/forms/save/{event_id}', json={'form_type': 'custom', 'form_title': 'Old',
                                                      'fields': [NAME, EMAIL, SHIRT]})
    page = fb['page'](event_id)
    assert _required(page, 'phone') and _control(page, 'usn') and not _required(page, 'usn')
    assert _control(page, 'member_1_usn') and not _required(page, 'member_1_usn')
    assert _control(page, 'member_1_phone') is None
